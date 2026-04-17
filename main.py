"""
main.py  --  rwrsb v2.0  (pyimgui + ModernGL + GLFW)
Usage: python main.py [optional_file.vox]
       or drag a .vox / .xml onto the window
"""
import sys
import os
import numpy as np
import glfw
import moderngl
import imgui
from imgui.integrations.glfw import GlfwRenderer

from camera       import OrbitCamera
from editor_state import EditorState
from renderer     import VoxelRenderer, pick_voxel, box_select_voxels, pick_particle_screen
from ui_panels    import (UIState, draw_toolbar, draw_bone_panel,
                          draw_status_bar, draw_load_dialog, draw_save_dialog,
                          draw_preset_dialog,
                          draw_box_select_overlay)

# ── globals ───────────────────────────────────

WIN_W, WIN_H  = 1280, 800
PANEL_W       = 280
TOOLBAR_H     = 38
STATUS_H      = 24

g_editor          = EditorState()
g_camera          = OrbitCamera(WIN_W, WIN_H)
g_ui              = UIState()
g_skeleton_sticks = [None]   # mutable ref: g_skeleton_sticks[0]

g_mouse_x = g_mouse_y = 0.0
g_lmb_down    = False
g_brush_active = False
g_particle_drag_active = False
g_drag_particle_idx = -1
g_drag_plane_normal = None
g_drag_grab_offset = None
g_drag_particle_origin = None
g_hover_particle_idx = -1
g_positions_np = None          # (N,3) float32 cache for picking
g_renderer     = None          # set in main()
g_imgui_impl   = None          # GlfwRenderer set in main()

g_first_upload_logged = False  # 诊断用：只在第一次 upload 时 log


def rebuild_positions_cache():
    global g_positions_np
    if g_editor.voxels:
        g_positions_np = np.array(
            [(v[0], v[1], v[2]) for v in g_editor.voxels], dtype=np.float32)
    else:
        g_positions_np = None


def is_over_viewport(x, y):
    return (x < WIN_W - PANEL_W and
            y > TOOLBAR_H and
            y < WIN_H - STATUS_H)


def particle_positions_np():
    if not g_editor.particles:
        return np.zeros((0, 3), dtype=np.float32)
    return np.array(
        [(p['x'], p['y'], p['z']) for p in g_editor.particles],
        dtype=np.float32
    )


def grid_step_value():
    if g_ui.grid_mode == 0:
        return 0.5
    if g_ui.grid_mode == 1:
        return 1.0
    return float(max(1, int(g_ui.grid_multiple)))


# ── interaction helpers ───────────────────────

def _do_brush_paint(sx, sy):
    if not g_ui.allow_skeleton_edit:
        return
    if g_positions_np is None or len(g_positions_np) == 0:
        return
    # 窗口坐标 → viewport 坐标（camera 的 width/height 每帧设为 vp_w/vp_h）
    vx = sx
    vy = sy - TOOLBAR_H
    origin, direction = g_camera.get_ray(vx, vy)
    hit = pick_voxel(origin, direction, g_positions_np)
    if hit >= 0:
        g_editor.bind_voxels([hit], g_editor.active_stick_idx)


def _finish_box_select():
    if g_positions_np is None or len(g_positions_np) == 0:
        return
    mvp  = g_camera.get_mvp()
    vp_w = WIN_W - PANEL_W
    vp_h = WIN_H - TOOLBAR_H - STATUS_H
    indices = box_select_voxels(
        mvp, g_positions_np,
        g_ui.box_x0, g_ui.box_y0 - TOOLBAR_H,
        g_ui.box_x1, g_ui.box_y1 - TOOLBAR_H,
        vp_w, vp_h)
    io = imgui.get_io()
    if not io.key_shift:
        g_editor.selected_voxels.clear()
    g_editor.selected_voxels.update(indices)
    g_editor.gpu_dirty = True


def _ray_plane_intersection(origin, direction, plane_point, plane_normal):
    denom = float(np.dot(direction, plane_normal))
    if abs(denom) < 1e-6:
        return None
    t = float(np.dot(plane_point - origin, plane_normal) / denom)
    return origin + direction * t


def _pick_particle(sx, sy):
    positions = particle_positions_np()
    if len(positions) == 0:
        return -1
    vp_w = WIN_W - PANEL_W
    vp_h = WIN_H - TOOLBAR_H - STATUS_H
    mvp = g_camera.get_mvp()
    return pick_particle_screen(mvp, positions, sx, sy - TOOLBAR_H, vp_w, vp_h)


def _begin_particle_drag(sx, sy, particle_idx):
    global g_particle_drag_active, g_drag_particle_idx, g_drag_plane_normal, g_drag_grab_offset, g_drag_particle_origin
    particle = g_editor.particles[particle_idx]
    plane_point = np.array([particle['x'], particle['y'], particle['z']], dtype=np.float32)
    cam_pos = np.asarray(g_camera.get_position(), dtype=np.float32)
    plane_normal = plane_point - cam_pos
    norm = np.linalg.norm(plane_normal)
    if norm < 1e-6:
        plane_normal = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    else:
        plane_normal /= norm

    origin, direction = g_camera.get_ray(sx, sy - TOOLBAR_H)
    hit = _ray_plane_intersection(
        np.asarray(origin, dtype=np.float32),
        np.asarray(direction, dtype=np.float32),
        plane_point,
        plane_normal,
    )
    if hit is None:
        hit = plane_point.copy()

    g_editor._push_undo()
    g_editor.set_active_particle(particle_idx)
    g_particle_drag_active = True
    g_drag_particle_idx = particle_idx
    g_drag_plane_normal = plane_normal
    g_drag_grab_offset = plane_point - hit
    g_drag_particle_origin = plane_point.copy()


def _drag_axis_mask(window):
    shift = (
        glfw.get_key(window, glfw.KEY_LEFT_SHIFT) == glfw.PRESS
        or glfw.get_key(window, glfw.KEY_RIGHT_SHIFT) == glfw.PRESS
    )
    ctrl = (
        glfw.get_key(window, glfw.KEY_LEFT_CONTROL) == glfw.PRESS
        or glfw.get_key(window, glfw.KEY_RIGHT_CONTROL) == glfw.PRESS
    )
    alt = (
        glfw.get_key(window, glfw.KEY_LEFT_ALT) == glfw.PRESS
        or glfw.get_key(window, glfw.KEY_RIGHT_ALT) == glfw.PRESS
    )
    if shift:
        return "x"
    if ctrl:
        return "y"
    if alt:
        return "z"
    return None


def _apply_particle_drag_rules(pos, axis_mask):
    out = np.array(pos, dtype=np.float32)
    if axis_mask == "x":
        out[1] = g_drag_particle_origin[1]
        out[2] = g_drag_particle_origin[2]
    elif axis_mask == "y":
        out[0] = g_drag_particle_origin[0]
        out[2] = g_drag_particle_origin[2]
    elif axis_mask == "z":
        out[0] = g_drag_particle_origin[0]
        out[1] = g_drag_particle_origin[1]

    if g_ui.snap_particles_to_grid:
        step = grid_step_value()
        if axis_mask == "x":
            out[0] = round(float(out[0]) / step) * step
        elif axis_mask == "y":
            out[1] = round(float(out[1]) / step) * step
        elif axis_mask == "z":
            out[2] = round(float(out[2]) / step) * step
        else:
            out = np.round(out / step) * step
    return out


def _update_particle_drag(window, sx, sy):
    if not g_particle_drag_active or g_drag_particle_idx < 0:
        return
    particle = g_editor.particles[g_drag_particle_idx]
    plane_point = np.array([particle['x'], particle['y'], particle['z']], dtype=np.float32)
    origin, direction = g_camera.get_ray(sx, sy - TOOLBAR_H)
    hit = _ray_plane_intersection(
        np.asarray(origin, dtype=np.float32),
        np.asarray(direction, dtype=np.float32),
        plane_point,
        g_drag_plane_normal,
    )
    if hit is None:
        return
    pos = hit + g_drag_grab_offset
    pos = _apply_particle_drag_rules(pos, _drag_axis_mask(window))
    g_editor.set_particle_position(g_drag_particle_idx, pos[0], pos[1], pos[2], push_undo=False)


def _end_particle_drag():
    global g_particle_drag_active, g_drag_particle_idx, g_drag_plane_normal, g_drag_grab_offset, g_drag_particle_origin
    g_particle_drag_active = False
    g_drag_particle_idx = -1
    g_drag_plane_normal = None
    g_drag_grab_offset = None
    g_drag_particle_origin = None


def _update_grid():
    if g_renderer is None:
        return
    g_renderer.show_grid = g_ui.show_grid
    if not g_ui.show_grid:
        g_renderer.upload_grid((0.0, 0.0, 0.0), 0.0, 0.0, 1, False, False, False)
        return

    points = []
    points.extend([(v[0], v[1], v[2]) for v in g_editor.voxels])
    points.extend([(p['x'], p['y'], p['z']) for p in g_editor.particles])
    if points:
        arr = np.array(points, dtype=np.float32)
        mins = arr.min(axis=0)
        maxs = arr.max(axis=0)
        center = (mins + maxs) * 0.5
        model_extent = max(float(np.max(maxs - mins)) * 0.75, 8.0)
    else:
        center = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        model_extent = 16.0

    if 0 <= g_editor.active_particle_idx < len(g_editor.particles):
        active = g_editor.particles[g_editor.active_particle_idx]
        center = np.array([active['x'], active['y'], active['z']], dtype=np.float32)

    camera_extent = max(float(g_camera.ortho_size) * 1.2, float(g_camera.distance) * 0.35, 8.0)
    extent = max(model_extent, camera_extent)
    step = grid_step_value()
    if g_ui.snap_particles_to_grid:
        center = np.round(center / step) * step
    major_every = 2 if step == 0.5 else 4
    g_renderer.upload_grid(
        center, extent, step, major_every,
        g_ui.show_grid_xz, g_ui.show_grid_xy, g_ui.show_grid_yz
    )


def _load_file(path):
    global g_first_upload_logged
    g_first_upload_logged = False   # 重新加载时允许再 log 一次
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == '.vox':
            g_editor.load_vox(path, g_ui.trans_bias)
            rebuild_positions_cache()
            g_camera.reset_to_model(g_editor.voxels)
        elif ext == '.xml':
            sk = g_editor.load_xml(path, g_ui.trans_bias)
            g_skeleton_sticks[0] = sk.get('sticks', [])
            g_renderer.upload_skeleton_lines(
                g_editor.particles, g_editor.sticks)
            rebuild_positions_cache()
            g_camera.reset_to_model(g_editor.voxels)

        # ── 诊断日志 ──
        if g_editor.voxels:
            xs = [v[0] for v in g_editor.voxels]
            ys = [v[1] for v in g_editor.voxels]
            zs = [v[2] for v in g_editor.voxels]
            print(f'[diag] voxel count = {len(g_editor.voxels)}')
            print(f'[diag] bbox x:[{min(xs):.1f},{max(xs):.1f}]  '
                  f'y:[{min(ys):.1f},{max(ys):.1f}]  '
                  f'z:[{min(zs):.1f},{max(zs):.1f}]')
            print(f'[diag] camera target={g_camera.target}  '
                  f'distance={g_camera.distance:.1f}')
            print(f'[diag] camera position={g_camera.get_position()}')
            # 前 3 个体素原始坐标 + 颜色
            for i, v in enumerate(g_editor.voxels[:3]):
                print(f'[diag] voxel[{i}] = {v}')
        else:
            print('[diag] voxel list is EMPTY after load')
    except Exception as e:
        import traceback
        print(f'[load] failed: {e}')
        traceback.print_exc()


# ── GLFW callbacks ────────────────────────────

def on_mouse_button(window, button, action, mods):
    global g_lmb_down, g_brush_active
    # let imgui consume first
    if g_imgui_impl:
        g_imgui_impl.mouse_callback(window, button, action, mods)
    io = imgui.get_io()
    if io.want_capture_mouse:
        return
    if not is_over_viewport(g_mouse_x, g_mouse_y):
        return

    pressed = (action == glfw.PRESS)
    if button == glfw.MOUSE_BUTTON_LEFT:
        g_lmb_down = pressed
        if pressed:
            hit_particle = _pick_particle(g_mouse_x, g_mouse_y)
            if hit_particle >= 0 and g_ui.allow_particle_edit:
                _begin_particle_drag(g_mouse_x, g_mouse_y, hit_particle)
            elif g_ui.allow_skeleton_edit and g_editor.tool_mode == 'brush' and g_editor.sticks:
                g_editor.begin_brush_stroke()
                _do_brush_paint(g_mouse_x, g_mouse_y)
                g_brush_active = True
            elif g_ui.allow_skeleton_edit and g_editor.tool_mode == 'select':
                g_ui.box_selecting = True
                g_ui.box_x0 = g_ui.box_x1 = g_mouse_x
                g_ui.box_y0 = g_ui.box_y1 = g_mouse_y
        else:
            if g_particle_drag_active:
                _end_particle_drag()
            if g_brush_active:
                g_editor.commit_brush_stroke()
                g_brush_active = False
            if g_ui.box_selecting:
                g_ui.box_selecting = False
                _finish_box_select()

    g_camera.on_mouse_button(button, action, mods, g_mouse_x, g_mouse_y)


def on_cursor_pos(window, xpos, ypos):
    global g_hover_particle_idx
    global g_mouse_x, g_mouse_y
    g_mouse_x, g_mouse_y = xpos, ypos
    if g_imgui_impl:
        g_imgui_impl.mouse_callback(window, 0, -1, 0)
    io = imgui.get_io()
    if io.want_capture_mouse:
        return
    if not is_over_viewport(xpos, ypos):
        g_hover_particle_idx = -1
        if g_renderer is not None:
            g_renderer.highlight_particle_idx = g_editor.active_particle_idx
        return
    hover_particle = _pick_particle(xpos, ypos)
    g_hover_particle_idx = hover_particle
    if g_renderer is not None:
        if g_particle_drag_active:
            g_renderer.highlight_particle_idx = g_drag_particle_idx
        else:
            g_renderer.highlight_particle_idx = hover_particle if hover_particle >= 0 else g_editor.active_particle_idx
    if g_particle_drag_active:
        _update_particle_drag(window, xpos, ypos)
        return
    if g_ui.allow_skeleton_edit and g_lmb_down and g_brush_active and g_editor.tool_mode == 'brush':
        _do_brush_paint(xpos, ypos)
    if g_ui.allow_skeleton_edit and g_lmb_down and g_ui.box_selecting and g_editor.tool_mode == 'select':
        g_ui.box_x1 = xpos
        g_ui.box_y1 = ypos
    g_camera.on_mouse_move(xpos, ypos)


def on_scroll(window, dx, dy):
    if g_imgui_impl:
        g_imgui_impl.scroll_callback(window, dx, dy)
    io = imgui.get_io()
    if io.want_capture_mouse:
        return
    if g_particle_drag_active:
        return
    if is_over_viewport(g_mouse_x, g_mouse_y):
        g_camera.on_scroll(dy)


def on_key(window, key, scancode, action, mods):
    if g_imgui_impl:
        g_imgui_impl.keyboard_callback(window, key, scancode, action, mods)
    io = imgui.get_io()
    if io.want_capture_keyboard:
        return
    if action in (glfw.PRESS, glfw.REPEAT):
        ctrl = (mods & glfw.MOD_CONTROL)
        if ctrl and key == glfw.KEY_Z:
            g_editor.undo()
        elif ctrl and key == glfw.KEY_Y:
            g_editor.redo()
        elif key == glfw.KEY_ESCAPE:
            g_editor.clear_selection()
        elif key == glfw.KEY_F:
            g_camera.reset_to_model(g_editor.voxels)
        elif key == glfw.KEY_B:
            if g_ui.allow_skeleton_edit:
                g_editor.tool_mode = 'brush'
        elif key == glfw.KEY_S and not ctrl:
            if g_ui.allow_skeleton_edit:
                g_editor.tool_mode = 'select'


def on_char(window, codepoint):
    if g_imgui_impl:
        g_imgui_impl.char_callback(window, codepoint)


def on_drop(window, paths):
    if paths:
        _load_file(paths[0])


def on_resize(window, width, height):
    global WIN_W, WIN_H
    WIN_W, WIN_H = width, height
    g_camera.resize(width, height)


# ── main ──────────────────────────────────────

def main():
    global g_renderer, g_imgui_impl, g_first_upload_logged, WIN_W, WIN_H

    if not glfw.init():
        raise RuntimeError("GLFW init failed")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.SAMPLES, 4)

    window = glfw.create_window(
        WIN_W, WIN_H, "rwrsb v2.0 -- RWR Skeleton Binder", None, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("Window creation failed")

    glfw.make_context_current(window)
    glfw.swap_interval(1)

    glfw.set_mouse_button_callback(window, on_mouse_button)
    glfw.set_cursor_pos_callback(window, on_cursor_pos)
    glfw.set_scroll_callback(window, on_scroll)
    glfw.set_key_callback(window, on_key)
    glfw.set_char_callback(window, on_char)
    glfw.set_drop_callback(window, on_drop)
    glfw.set_framebuffer_size_callback(window, on_resize)

    # ModernGL (shares the GLFW context)
    ctx = moderngl.create_context()
    ctx.enable(moderngl.DEPTH_TEST)

    g_renderer = VoxelRenderer(ctx)

    # pyimgui
    imgui.create_context()
    g_imgui_impl = GlfwRenderer(window, attach_callbacks=False)

    # load file from argv
    if len(sys.argv) > 1:
        _load_file(sys.argv[1])

    while not glfw.window_should_close(window):
        glfw.poll_events()
        g_imgui_impl.process_inputs()

        imgui.new_frame()

        _update_grid()
        if g_editor.skeleton_dirty and g_renderer is not None:
            g_renderer.upload_skeleton_lines(g_editor.particles, g_editor.sticks)
            g_editor.skeleton_dirty = False

        # update GPU buffers when dirty
        if g_editor.gpu_dirty and g_editor.voxels:
            positions, colors, selected = g_editor.build_instance_arrays()
            g_renderer.upload_voxels(positions, colors, selected)
            rebuild_positions_cache()
            if not g_first_upload_logged:
                print(f'[diag] uploaded {len(positions)} instances to GPU  '
                      f'(renderer.n_voxels={g_renderer.n_voxels})')
                g_first_upload_logged = True

        # 3-D scene: 先清整个 framebuffer，再把 viewport 限定在中央 3D 区域
        fb_w, fb_h = glfw.get_framebuffer_size(window)
        ctx.viewport = (0, 0, max(fb_w, 1), max(fb_h, 1))
        ctx.clear(0.15, 0.15, 0.18, 1.0)

        vp_w = WIN_W - PANEL_W
        vp_h = WIN_H - TOOLBAR_H - STATUS_H

        if (g_editor.voxels and vp_w > 0 and vp_h > 0
                and fb_w > 0 and fb_h > 0):
            # HiDPI：fb 尺寸可能比窗口尺寸大
            scale_x = fb_w / WIN_W
            scale_y = fb_h / WIN_H
            # OpenGL viewport 原点在左下；3D 区域位于状态栏之上、工具栏之下
            ctx.viewport = (
                0,
                int(STATUS_H * scale_y),
                int(vp_w * scale_x),
                int(vp_h * scale_y),
            )
            # 相机 aspect 与 viewport 一致，避免拉伸
            g_camera.resize(vp_w, vp_h)
            mvp = g_camera.get_mvp()
            g_renderer.render(mvp)

        # 恢复整个 framebuffer，供 imgui 绘制 UI
        ctx.viewport = (0, 0, max(fb_w, 1), max(fb_h, 1))

        # UI panels (use a full-screen invisible window for draw list overlay)
        imgui.set_next_window_position(0, 0)
        imgui.set_next_window_size(WIN_W, WIN_H)
        imgui.begin("##overlay",
                    flags=(imgui.WINDOW_NO_TITLE_BAR | imgui.WINDOW_NO_RESIZE |
                           imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_BACKGROUND |
                           imgui.WINDOW_NO_SAVED_SETTINGS |
                           imgui.WINDOW_NO_INPUTS))
        draw_box_select_overlay(g_ui)
        imgui.end()

        draw_toolbar(g_ui, g_editor, g_renderer, g_camera, WIN_W)
        draw_bone_panel(g_ui, g_editor, WIN_W, WIN_H,
                        g_renderer, g_skeleton_sticks)
        draw_status_bar(g_editor, WIN_W, WIN_H)

        draw_load_dialog(g_ui, g_editor, g_renderer,
                         g_skeleton_sticks, WIN_W, WIN_H)
        draw_save_dialog(g_ui, g_editor, g_skeleton_sticks, WIN_W, WIN_H)
        draw_preset_dialog(g_ui, g_editor, g_renderer,
                           g_skeleton_sticks, WIN_W, WIN_H)

        imgui.render()
        g_imgui_impl.render(imgui.get_draw_data())

        glfw.swap_buffers(window)

    g_renderer.release()
    g_imgui_impl.shutdown()
    imgui.destroy_context()
    glfw.terminate()


if __name__ == '__main__':
    main()
