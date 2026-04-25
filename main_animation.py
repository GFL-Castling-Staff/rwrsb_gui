"""
main_animation.py  --  rwrsb_anim 动画工具入口
Commit 4: 粒子拾取/拖动 + drop 加载 + 关窗 dirty 守卫 + panel 布局调整
"""
import sys
import os
import logging
import functools
import time
import math
from pathlib import Path

# 日志系统必须在其他项目模块之前初始化
from logger_setup import init_logger
_LOG_DIR = init_logger()

import numpy as np
import glfw
import moderngl
import imgui
from imgui.integrations.glfw import GlfwRenderer

from camera       import OrbitCamera
from editor_state import EditorState
from renderer     import (VoxelRenderer, pick_particle_screen,
                          box_select_particles)
from ui_panels    import (UIState, draw_toolbar, draw_bone_panel,
                          draw_status_bar, draw_load_dialog, draw_save_dialog,
                          draw_box_select_overlay, draw_exit_dialog,
                          draw_toasts,
                          draw_animation_panel, draw_anim_source_picker,
                          draw_anim_exit_confirm, draw_invalid_binding_dialog)
from animation_io import (parse_animation_index, parse_single_animation,
                          parse_first_animation, Animation, AnimationFrame,
                          EXPECTED_PARTICLE_COUNT)
from resource_utils import resource_path

logger = logging.getLogger(__name__)

# ── globals ───────────────────────────────────

WIN_W, WIN_H  = 1280, 800
PANEL_W       = 280
TOOLBAR_H     = 38
STATUS_H      = 24
ANIM_PANEL_H  = 240

g_editor          = EditorState()
g_camera          = OrbitCamera(WIN_W, WIN_H)
g_ui              = UIState()
g_skeleton_sticks = [None]

g_mouse_x = g_mouse_y = 0.0
g_lmb_down    = False
g_particle_drag_active = False
g_drag_particle_idx = -1
g_drag_plane_normal = None
g_drag_grab_offset = None
g_drag_particle_origin = None
g_drag_origins = {}
g_grid_sig_cache = None

# 旋转拖动专用状态（与平移拖动互斥）
g_rotate_drag_active = False
g_rotate_drag_start_mx = 0.0      # 拖动起始鼠标 X（屏幕像素）
g_rotate_drag_snapshot = {}       # {idx: np.array([x, y, z])}，拖动前位置快照
g_rotate_drag_pivot = None        # np.array，旋转中心（世界坐标）
g_rotate_drag_axis = None         # "x" | "y" | "z"
g_voxel_color_mode_cache = None  # 缓存上次体素颜色模式，切换时触发全量重传
g_hover_particle_idx = -1
g_positions_np = None
g_renderer     = None
g_imgui_impl   = None


def _ui_layout_metrics():
    scale = max(0.8, min(1.75, getattr(g_ui, "ui_scale", 1.0)))
    panel_w = 0 if g_ui.app_mode == "animation" else int(round(PANEL_W * scale))
    toolbar_h = int(round(TOOLBAR_H * scale))
    status_h_base = int(round(STATUS_H * scale))
    if g_ui.app_mode == "animation":
        # 视口底部留出空间给状态栏 + 动画面板
        status_h = status_h_base + int(round(ANIM_PANEL_H * scale))
    else:
        status_h = status_h_base
    return panel_w, toolbar_h, status_h


def _configure_imgui_fonts():
    io = imgui.get_io()
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyh.ttf"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            try:
                io.fonts.add_font_from_file_ttf(
                    str(candidate),
                    16,
                    glyph_ranges=io.fonts.get_glyph_ranges_chinese_full(),
                )
                return str(candidate)
            except Exception:
                logger.exception("failed to load font %s", candidate)
    return None


def _apply_ui_scale():
    target_scale = max(0.8, min(1.75, getattr(g_ui, "ui_scale", 1.0)))
    if g_ui._applied_scale == target_scale:
        return
    io = imgui.get_io()
    io.font_global_scale = target_scale
    g_ui._applied_scale = target_scale


def _window_title():
    base = "RWR Animation Editor (rwrsb_anim)"
    if g_editor.current_animation:
        dirty = "*" if g_editor._anim_dirty else ""
        return f"{base} - {g_editor.current_animation.name}{dirty}"
    return base


def is_over_viewport(x, y):
    panel_w, toolbar_h, status_h = _ui_layout_metrics()
    return (0 <= x <= WIN_W - panel_w and
            toolbar_h <= y <= WIN_H - status_h)


def rebuild_positions_cache():
    global g_positions_np
    if not g_editor.particles:
        g_positions_np = None
        return
    g_positions_np = np.array(
        [(p["x"], p["y"], p["z"]) for p in g_editor.particles],
        dtype=np.float32,
    )


def _pick_particle(mx, my):
    if g_positions_np is None or len(g_positions_np) == 0:
        return -1
    panel_w, toolbar_h, status_h = _ui_layout_metrics()
    vp_w = WIN_W - panel_w
    vp_h = WIN_H - toolbar_h - status_h
    if vp_w <= 0 or vp_h <= 0:
        return -1
    local_x = mx
    local_y = my - toolbar_h
    mvp = g_camera.get_mvp()
    return pick_particle_screen(mvp, g_positions_np, local_x, local_y, vp_w, vp_h)


# ── 粒子拖动 ──────────────────────────────────

def _ray_plane_hit(ray_o, ray_d, plane_pt, plane_normal):
    ray_o = np.asarray(ray_o, dtype=np.float32)
    ray_d = np.asarray(ray_d, dtype=np.float32)
    plane_pt = np.asarray(plane_pt, dtype=np.float32)
    plane_normal = np.asarray(plane_normal, dtype=np.float32)
    denom = float(np.dot(plane_normal, ray_d))
    if abs(denom) < 1e-7:
        return None
    t = float(np.dot(plane_normal, plane_pt - ray_o)) / denom
    if t < 0:
        return None
    return ray_o + ray_d * t


def _start_particle_drag(mx, my, particle_idx):
    global g_particle_drag_active, g_drag_particle_idx
    global g_drag_plane_normal, g_drag_grab_offset, g_drag_particle_origin
    global g_drag_origins

    if g_editor.animation_mode and g_editor.playback_playing:
        g_editor.playback_playing = False

    p = g_editor.particles[particle_idx]
    g_drag_particle_origin = np.array([p["x"], p["y"], p["z"]], dtype=np.float32)

    # 拖动平面 = 过粒子、法线指向相机的平面（与 main.py _begin_particle_drag 一致）
    cam_pos = np.asarray(g_camera.get_position(), dtype=np.float32)
    plane_normal = g_drag_particle_origin - cam_pos
    norm = float(np.linalg.norm(plane_normal))
    if norm < 1e-6:
        plane_normal = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    else:
        plane_normal = plane_normal / norm
    g_drag_plane_normal = plane_normal

    # 多选拖动：备份所有选中点初始位置
    drag_set = (set(g_editor.selected_particles)
                if particle_idx in g_editor.selected_particles
                else {particle_idx})
    g_drag_origins = {}
    for idx in drag_set:
        if 0 <= idx < len(g_editor.particles):
            pp = g_editor.particles[idx]
            g_drag_origins[idx] = np.array(
                [pp["x"], pp["y"], pp["z"]], dtype=np.float32)

    # 屏幕到 3D 的初始 grab offset（OrbitCamera.get_ray 只需 sx, sy）
    _, toolbar_h, _ = _ui_layout_metrics()
    ray_o, ray_d = g_camera.get_ray(mx, my - toolbar_h)
    hit = _ray_plane_hit(
        np.asarray(ray_o, dtype=np.float32),
        np.asarray(ray_d, dtype=np.float32),
        g_drag_particle_origin,
        g_drag_plane_normal,
    )
    g_drag_grab_offset = (g_drag_particle_origin - hit) if hit is not None else np.zeros(3)

    g_drag_particle_idx = particle_idx
    g_particle_drag_active = True


def _rotate_drag_axis_from_camera():
    """从相机 forward 向量推断旋转轴：前视→Z，顶视→Y，侧视→X。"""
    fwd = np.asarray(g_camera.get_view_direction(), dtype=np.float32)
    norm = float(np.linalg.norm(fwd))
    if norm < 1e-6:
        return "y"
    fwd = fwd / norm
    idx = int(np.argmax(np.abs(fwd)))
    return ("x", "y", "z")[idx]


def _compute_rotate_pivot():
    """根据 g_ui.rotate_pivot_mode 计算旋转中心（世界坐标）。
    如果是 active 但 active 不在选择集中，fallback 到 centroid。
    """
    mode = g_ui.rotate_pivot_mode
    sel = g_editor.selected_particles
    if mode == "active":
        act = g_editor.active_particle_idx
        if act >= 0 and act in sel:
            p = g_editor.particles[act]
            return np.array([p["x"], p["y"], p["z"]], dtype=np.float32)
        # fallback: centroid
    if mode in ("active", "centroid") and sel:
        coords = np.array(
            [[g_editor.particles[i]["x"], g_editor.particles[i]["y"], g_editor.particles[i]["z"]]
             for i in sel],
            dtype=np.float32,
        )
        return coords.mean(axis=0)
    return np.zeros(3, dtype=np.float32)


def _start_rotate_drag(particle_idx):
    """旋转模式下开始拖动：保存快照，计算 pivot + 轴，推 undo。"""
    global g_rotate_drag_active, g_rotate_drag_start_mx
    global g_rotate_drag_snapshot, g_rotate_drag_pivot, g_rotate_drag_axis

    if not g_editor.selected_particles:
        return

    # 推 undo（在修改粒子之前推一次，拖动过程中不再推）
    if g_editor.animation_mode:
        g_editor._anim_push_undo()
    else:
        g_editor._push_undo()

    # 保存选中粒子位置快照
    g_rotate_drag_snapshot = {
        idx: np.array([g_editor.particles[idx]["x"],
                       g_editor.particles[idx]["y"],
                       g_editor.particles[idx]["z"]], dtype=np.float32)
        for idx in g_editor.selected_particles
        if 0 <= idx < len(g_editor.particles)
    }
    g_rotate_drag_pivot = _compute_rotate_pivot()
    g_rotate_drag_axis  = _rotate_drag_axis_from_camera()
    g_rotate_drag_start_mx = g_mouse_x
    g_rotate_drag_active = True


def _update_rotate_drag(mx):
    """旋转拖动每帧更新：从快照重算旋转，直接写入粒子坐标。"""
    if not g_rotate_drag_active or g_rotate_drag_pivot is None:
        return
    from editor_state import _rotation_matrix
    angle_deg = (mx - g_rotate_drag_start_mx) * 1.0   # 1px = 1°
    R = _rotation_matrix(g_rotate_drag_axis, float(np.radians(angle_deg)))
    pivot = g_rotate_drag_pivot
    for idx, p_orig in g_rotate_drag_snapshot.items():
        if 0 <= idx < len(g_editor.particles):
            p_new = pivot + R @ (p_orig - pivot)
            g_editor.particles[idx]["x"] = float(p_new[0])
            g_editor.particles[idx]["y"] = float(p_new[1])
            g_editor.particles[idx]["z"] = float(p_new[2])
    g_editor.skeleton_dirty = True


def _end_rotate_drag():
    """结束旋转拖动：动画模式下手动写回当前帧（不再推 undo）。"""
    global g_rotate_drag_active, g_rotate_drag_snapshot
    global g_rotate_drag_pivot, g_rotate_drag_axis

    if g_editor.animation_mode and g_editor.current_animation:
        frame_idx = g_editor.current_frame_idx
        frames = g_editor.current_animation.frames
        if 0 <= frame_idx < len(frames):
            frames[frame_idx].positions = [
                (float(p["x"]), float(p["y"]), float(p["z"]))
                for p in g_editor.particles
            ]
            g_editor._anim_dirty = True

    g_rotate_drag_active = False
    g_rotate_drag_snapshot = {}
    g_rotate_drag_pivot = None
    g_rotate_drag_axis = None


def _drag_axis_mask(window):
    """读取 GLFW 修饰键返回轴锁定模式：Shift=X, Ctrl=Y, Alt=Z, 无=None。"""
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


def _apply_particle_drag_rules_anim(pos, axis_mask):
    """轴锁定 + 可选网格吸附（anim 工具专用，使用 _grid_step 而非 grid_step_value）。"""
    from ui_panels import _grid_step
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
        step = _grid_step(g_ui)
        if axis_mask == "x":
            out[0] = round(float(out[0]) / step) * step
        elif axis_mask == "y":
            out[1] = round(float(out[1]) / step) * step
        elif axis_mask == "z":
            out[2] = round(float(out[2]) / step) * step
        else:
            out = np.round(out / step) * step
    return out


def _update_particle_drag(window, mx, my):
    if not g_particle_drag_active or g_drag_particle_origin is None:
        return
    _, toolbar_h, _ = _ui_layout_metrics()
    ray_o, ray_d = g_camera.get_ray(mx, my - toolbar_h)
    hit = _ray_plane_hit(
        np.asarray(ray_o, dtype=np.float32),
        np.asarray(ray_d, dtype=np.float32),
        g_drag_particle_origin,
        g_drag_plane_normal,
    )
    if hit is None:
        return
    # grab_offset = origin - initial_hit  →  new_anchor = hit + grab_offset
    new_anchor = hit + g_drag_grab_offset
    # 轴锁定：clamp new_anchor 到约束轴，再算 delta（多选跟随用同一个 delta）
    axis_mask = _drag_axis_mask(window)
    new_anchor = _apply_particle_drag_rules_anim(new_anchor, axis_mask)
    delta = new_anchor - g_drag_particle_origin
    from ui_panels import _grid_step
    step = _grid_step(g_ui) if g_ui.snap_particles_to_grid else 0.0
    for idx, origin in g_drag_origins.items():
        if 0 <= idx < len(g_editor.particles):
            target = origin + delta
            if step > 0.0:
                target = np.array([
                    round(float(target[0]) / step) * step,
                    round(float(target[1]) / step) * step,
                    round(float(target[2]) / step) * step,
                ], dtype=np.float32)
            g_editor.particles[idx]["x"] = float(target[0])
            g_editor.particles[idx]["y"] = float(target[1])
            g_editor.particles[idx]["z"] = float(target[2])
    g_editor.skeleton_dirty = True


def _end_particle_drag():
    global g_particle_drag_active, g_drag_particle_idx
    global g_drag_plane_normal, g_drag_grab_offset, g_drag_particle_origin
    global g_drag_origins

    if g_editor.animation_mode:
        try:
            g_editor.commit_particle_move_to_frame()
        except Exception:
            logger.exception("commit_particle_move_to_frame failed")

    g_particle_drag_active = False
    g_drag_particle_idx = -1
    g_drag_plane_normal = None
    g_drag_grab_offset = None
    g_drag_particle_origin = None
    g_drag_origins = {}


def _finish_particle_box_select(shift, ctrl):
    """框选结束：把框内粒子加入 / toggle / 替换选择集（anim 工具专用）。"""
    if g_editor.mirror_mode:
        return
    if g_positions_np is None or len(g_positions_np) == 0:
        return
    panel_w, toolbar_h, status_h = _ui_layout_metrics()
    vp_w = WIN_W - panel_w
    vp_h = WIN_H - toolbar_h - status_h
    if vp_w <= 0 or vp_h <= 0:
        return
    mvp = g_camera.get_mvp()
    indices = box_select_particles(
        mvp, g_positions_np,
        g_ui.box_x0, g_ui.box_y0 - toolbar_h,
        g_ui.box_x1, g_ui.box_y1 - toolbar_h,
        vp_w, vp_h)
    if ctrl:
        for i in indices:
            if i in g_editor.selected_particles:
                g_editor.selected_particles.discard(i)
            else:
                g_editor.selected_particles.add(i)
    elif shift:
        g_editor.selected_particles.update(indices)
    else:
        g_editor.replace_selected_particles(indices)
    if g_editor.selected_particles:
        if g_editor.active_particle_idx not in g_editor.selected_particles:
            g_editor.set_active_particle(next(iter(g_editor.selected_particles)))


# ── GLFW callbacks ────────────────────────────

def _safe_callback(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception("GLFW callback %s failed", fn.__name__)
    return wrapper


@_safe_callback
def on_mouse_button(window, button, action, mods):
    global g_lmb_down
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
            shift = bool(mods & glfw.MOD_SHIFT)
            ctrl = bool(mods & glfw.MOD_CONTROL)
            hit = _pick_particle(g_mouse_x, g_mouse_y)
            if hit >= 0:
                if shift:
                    g_editor.add_selected_particle(hit)
                    g_editor.set_active_particle(hit)
                elif ctrl:
                    in_set = g_editor.toggle_selected_particle(hit)
                    if in_set:
                        g_editor.set_active_particle(hit)
                else:
                    if hit not in g_editor.selected_particles:
                        g_editor.replace_selected_particles({hit})
                    g_editor.set_active_particle(hit)
                    if g_ui.anim_drag_mode == "rotate":
                        _start_rotate_drag(hit)
                    else:
                        _start_particle_drag(g_mouse_x, g_mouse_y, hit)
            else:
                # 未命中粒子：普通点击清空选择，所有情况都起框选
                if not (shift or ctrl):
                    g_editor.clear_selected_particles()
                    g_editor.active_particle_idx = -1
                g_ui.box_selecting = True
                g_ui.box_x0 = g_ui.box_x1 = g_mouse_x
                g_ui.box_y0 = g_ui.box_y1 = g_mouse_y
        else:
            if g_particle_drag_active:
                _end_particle_drag()
            if g_rotate_drag_active:
                _end_rotate_drag()
            if g_ui.box_selecting:
                g_ui.box_selecting = False
                _finish_particle_box_select(bool(mods & glfw.MOD_SHIFT),
                                            bool(mods & glfw.MOD_CONTROL))

    g_camera.on_mouse_button(button, action, mods, g_mouse_x, g_mouse_y)


@_safe_callback
def on_cursor_pos(window, xpos, ypos):
    global g_mouse_x, g_mouse_y, g_hover_particle_idx
    g_mouse_x = xpos
    g_mouse_y = ypos
    if g_particle_drag_active:
        _update_particle_drag(window, xpos, ypos)
    if g_rotate_drag_active:
        _update_rotate_drag(xpos)
    if g_ui.box_selecting:
        g_ui.box_x1 = xpos
        g_ui.box_y1 = ypos
    if is_over_viewport(xpos, ypos):
        hover_particle = _pick_particle(xpos, ypos)
        g_hover_particle_idx = hover_particle
        if g_renderer:
            g_renderer.highlight_particle_idx = hover_particle
    g_camera.on_mouse_move(xpos, ypos)


@_safe_callback
def on_scroll(window, dx, dy):
    if g_imgui_impl:
        g_imgui_impl.scroll_callback(window, dx, dy)
    io = imgui.get_io()
    if io.want_capture_mouse:
        return
    if is_over_viewport(g_mouse_x, g_mouse_y):
        g_camera.on_scroll(dy)


@_safe_callback
def on_key(window, key, scancode, action, mods):
    if g_imgui_impl:
        g_imgui_impl.keyboard_callback(window, key, scancode, action, mods)
    io = imgui.get_io()
    if io.want_capture_keyboard:
        return
    if action in (glfw.PRESS, glfw.REPEAT):
        ctrl = (mods & glfw.MOD_CONTROL)
        if ctrl and key == glfw.KEY_Z:
            undo_fn, _ = g_editor.get_effective_undo_redo()
            undo_fn()
        elif ctrl and key == glfw.KEY_Y:
            _, redo_fn = g_editor.get_effective_undo_redo()
            redo_fn()
        elif key == glfw.KEY_ESCAPE:
            g_editor.clear_selected_particles()
        elif key == glfw.KEY_F:
            if g_editor.particles:
                xs = [p["x"] for p in g_editor.particles]
                ys = [p["y"] for p in g_editor.particles]
                zs = [p["z"] for p in g_editor.particles]
                cx = (min(xs) + max(xs)) / 2
                cy = (min(ys) + max(ys)) / 2
                cz = (min(zs) + max(zs)) / 2
                span = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs), 1.0)
                g_camera.target = np.array([cx, cy, cz])
                g_camera.distance = span * 1.8
                g_camera.ortho_size = span * 0.6
        elif key == glfw.KEY_SPACE:
            if g_editor.animation_mode:
                g_editor.playback_playing = not g_editor.playback_playing


@_safe_callback
def on_char(window, codepoint):
    if g_imgui_impl:
        g_imgui_impl.char_callback(window, codepoint)


@_safe_callback
def on_drop(window, paths):
    if not paths:
        return
    path = paths[0]
    if not str(path).lower().endswith(".xml"):
        g_ui.push_toast("仅支持 .xml 文件", "warning")
        return

    def do_load_anim_or_skel():
        from editor_state import check_xml_voxel_bindings
        # 优先尝试当作 animation 文件
        try:
            doc = parse_animation_index(path)
            if doc.names:
                if len(doc.names) == 1:
                    anim = parse_first_animation(path)
                    g_editor.enter_animation_mode(anim)
                    g_ui.push_toast(f"已加载动画: {anim.name}", "success")
                else:
                    g_ui._anim_picker_doc = doc
                    g_ui._anim_picker_filter = ""
                    g_ui._anim_picker_selected = 0
                return
        except Exception:
            logger.info("not an animation file, try as skeleton: %s", path)
        # 不是 animation 文件 → 当作 skeleton XML（带 binding 校验）
        def after_load():
            try:
                g_editor.enter_animation_mode(
                    Animation(name="new_animation", end=1.0, speed=1.0))
            except Exception as exc:
                g_ui.push_toast(f"进入动画模式失败: {exc}", "error", exc_info=True)

        is_valid, reason, info = check_xml_voxel_bindings(path)
        if is_valid:
            try:
                if g_editor.animation_mode:
                    g_editor.exit_animation_mode(force=True)
                g_editor.load_skeleton_xml(path)
                after_load()
                g_ui.push_toast(f"已加载骨架", "success")
            except Exception as exc:
                g_ui.push_toast(f"加载失败: {exc}", "error", exc_info=True)
        else:
            # 非法 binding → 弹对话框
            g_ui._invalid_binding_show = True
            g_ui._invalid_binding_path = path
            g_ui._invalid_binding_reason = reason
            g_ui._invalid_binding_info = info
            g_ui._invalid_binding_after_load = after_load

    if g_editor.animation_mode and g_editor._anim_dirty:
        g_ui._anim_dirty_pending = do_load_anim_or_skel
    else:
        do_load_anim_or_skel()


@_safe_callback
def on_resize(window, width, height):
    global WIN_W, WIN_H
    WIN_W, WIN_H = width, height
    g_camera.resize(width, height)


@_safe_callback
def on_close(window):
    if g_editor.animation_mode and g_editor._anim_dirty:
        g_ui._anim_dirty_pending = lambda: glfw.set_window_should_close(window, True)
        glfw.set_window_should_close(window, False)


# ── main ──────────────────────────────────────

def main():
    global g_renderer, g_imgui_impl, WIN_W, WIN_H

    g_ui.app_mode = "animation"

    if not glfw.init():
        raise RuntimeError("GLFW init failed")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.SAMPLES, 4)

    window = glfw.create_window(WIN_W, WIN_H, _window_title(), None, None)
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
    glfw.set_window_close_callback(window, on_close)

    ctx = moderngl.create_context()
    ctx.enable(moderngl.DEPTH_TEST)

    g_renderer = VoxelRenderer(ctx)
    # 动画工具默认只显示 XZ 面网格，三平面密度太大（任务3）
    g_ui.show_grid_xy = False
    g_ui.show_grid_yz = False
    # 上传原点坐标轴 Gizmo 并默认开启（任务4）
    g_renderer.upload_origin_axes(length=8.0)
    g_renderer.show_origin_gizmo = True

    imgui.create_context()
    font_path = _configure_imgui_fonts()
    g_imgui_impl = GlfwRenderer(window, attach_callbacks=False)
    _apply_ui_scale()
    if font_path:
        logger.info("loaded font: %s", font_path)
    else:
        logger.warning("using default imgui font (no CJK font found)")

    # 启动时自动加载 vanilla skeleton
    try:
        preset_path = resource_path("presets", "human_skeleton.json")
        g_editor.load_skeleton_preset(preset_path)
        logger.info("loaded default human skeleton (%d particles)",
                    len(g_editor.particles))
    except Exception as exc:
        logger.exception("failed to load default skeleton")
        g_ui.push_toast(f"加载默认骨架失败: {exc}", "error", exc_info=True)

    # 自动进入动画模式
    try:
        new_anim = Animation(name="new_animation", loop=False, end=1.0, speed=1.0)
        g_editor.enter_animation_mode(new_anim)
    except Exception as exc:
        logger.exception("failed to enter animation mode")
        g_ui.push_toast(f"进入动画模式失败: {exc}", "error", exc_info=True)

    if g_editor.particles:
        xs = [p["x"] for p in g_editor.particles]
        ys = [p["y"] for p in g_editor.particles]
        zs = [p["z"] for p in g_editor.particles]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        cz = (min(zs) + max(zs)) / 2
        span = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs), 1.0)
        g_camera.target = np.array([cx, cy, cz])
        g_camera.distance = span * 1.8
        g_camera.ortho_size = span * 0.6

    rebuild_positions_cache()
    if g_renderer:
        g_renderer.upload_skeleton_lines(g_editor.particles, g_editor.sticks)
        g_editor.skeleton_dirty = False

    _last_loop_err = (None, None, 0)

    while not glfw.window_should_close(window):
        try:
            glfw.poll_events()
            g_imgui_impl.process_inputs()
            _apply_ui_scale()
            g_camera.invert_y = g_ui.invert_y_axis
            if g_renderer is not None:
                g_renderer.show_origin_gizmo = g_ui.show_origin_gizmo

            glfw.set_window_title(window, _window_title())
            # 同步 show_voxels 状态到 renderer
            if g_renderer is not None:
                g_renderer.show_voxels = g_ui.show_voxels

            imgui.new_frame()

            if g_editor.animation_mode and g_editor.playback_playing:
                anim = g_editor.current_animation
                if anim:
                    io = imgui.get_io()
                    dt_frame = io.delta_time
                    g_editor.playback_time += dt_frame * anim.speed
                    if g_editor.playback_loop_preview and anim.end > 0:
                        g_editor.playback_time = g_editor.playback_time % anim.end
                    elif g_editor.playback_time >= anim.end:
                        g_editor.playback_time = anim.end
                        g_editor.playback_playing = False
                    g_editor._apply_interpolated_to_particles(g_editor.playback_time)

            if g_editor.skeleton_dirty and g_renderer is not None:
                g_renderer.upload_skeleton_lines(g_editor.particles, g_editor.sticks)
                rebuild_positions_cache()
                g_editor.skeleton_dirty = False

            # voxel GPU buffer 更新
            if g_editor.voxels and g_renderer is not None:
                global g_voxel_color_mode_cache
                _color_mode = g_ui.show_voxel_original_colors
                _color_mode_changed = (_color_mode != g_voxel_color_mode_cache)
                if _color_mode_changed:
                    g_voxel_color_mode_cache = _color_mode
                    g_editor.gpu_dirty = True  # 颜色模式变化，强制全量重传

                if g_editor.gpu_dirty:
                    _n = len(g_editor.voxels)
                    if (g_editor.animation_mode and g_editor._voxel_groups
                            and g_renderer.n_voxels == _n
                            and not _color_mode_changed):
                        # 快速路径：VBO 已建好、体素数一致、颜色模式未变，仅更新位置
                        arr = np.array(g_editor.voxels, dtype=np.float32)
                        g_renderer.update_voxel_positions(arr[:, :3])
                        g_editor.gpu_dirty = False
                    else:
                        # 全量上传：首次加载、体素数变化或颜色模式切换
                        positions, colors, selected = g_editor.build_instance_arrays(
                            use_original_color=_color_mode)
                        g_renderer.upload_voxels(positions, colors, selected)

            # grid 上传（签名缓存，避免每帧重传）
            # 网格中心固定在世界原点 (0,0,0)，不跟随粒子
            if g_renderer is not None:
                global g_grid_sig_cache
                g_renderer.show_grid = bool(g_ui.show_grid)
                if g_ui.show_grid:
                    from ui_panels import _grid_step
                    step = _grid_step(g_ui)
                    center = (0.0, 0.0, 0.0)
                    # 相机 extent：覆盖当前可视范围
                    camera_extent = max(
                        g_camera.ortho_size * 1.2,
                        g_camera.distance * 0.35,
                        8.0,
                    )
                    # 动画模式下粒子随帧移动，不用粒子距离决定 extent（否则每帧触发重建）
                    if not g_editor.animation_mode and g_editor.particles:
                        max_dist = max(
                            math.sqrt(p["x"]**2 + p["y"]**2 + p["z"]**2)
                            for p in g_editor.particles
                        )
                        model_extent = max(max_dist * 1.5, 10.0)
                        extent = max(model_extent, camera_extent)
                    else:
                        extent = max(camera_extent, 10.0)
                    grid_sig = (
                        int(extent / 2) * 2, step,  # 每 2 单位才重建，防止动画播放时每帧重绘
                        g_ui.show_grid_xz, g_ui.show_grid_xy, g_ui.show_grid_yz,
                    )
                    if grid_sig != g_grid_sig_cache:
                        g_renderer.upload_grid(
                            np.array(center, dtype=np.float32),
                            extent,
                            step,
                            show_xz=g_ui.show_grid_xz,
                            show_xy=g_ui.show_grid_xy,
                            show_yz=g_ui.show_grid_yz,
                        )
                        g_grid_sig_cache = grid_sig

            # 5b：骨段长度违规检测，每帧更新 renderer
            if g_renderer is not None:
                if g_ui._anim_check_lengths and g_editor.animation_mode:
                    deviations = g_editor.compute_stick_length_deviations()
                    threshold = float(g_ui._anim_length_threshold_pct)
                    g_renderer.violation_stick_indices = [
                        i for (i, cur, ref, pct) in deviations if pct >= threshold
                    ]
                else:
                    g_renderer.violation_stick_indices = []

            fb_w, fb_h = glfw.get_framebuffer_size(window)
            ctx.viewport = (0, 0, max(fb_w, 1), max(fb_h, 1))
            ctx.clear(0.15, 0.15, 0.18, 1.0)

            panel_w, toolbar_h, status_h = _ui_layout_metrics()
            vp_w = WIN_W - panel_w
            vp_h = WIN_H - toolbar_h - status_h

            if vp_w > 0 and vp_h > 0 and fb_w > 0 and fb_h > 0:
                scale_x = fb_w / WIN_W
                scale_y = fb_h / WIN_H
                ctx.viewport = (
                    0,
                    int(status_h * scale_y),
                    int(vp_w * scale_x),
                    int(vp_h * scale_y),
                )
                g_camera.resize(vp_w, vp_h)
                mvp = g_camera.get_mvp()
                # active 粒子单独用青色渲染，从 selected 列表中排除避免颜色叠加
                act = g_editor.active_particle_idx
                g_renderer.highlight_active_particle_idx = act
                g_renderer.highlight_selected_particle_indices = [
                    i for i in g_editor.selected_particles if i != act
                ]
                g_renderer.render(mvp)

            ctx.viewport = (0, 0, max(fb_w, 1), max(fb_h, 1))

            # overlay
            imgui.set_next_window_position(0, 0)
            imgui.set_next_window_size(WIN_W, WIN_H)
            imgui.begin("##overlay",
                        flags=(imgui.WINDOW_NO_TITLE_BAR | imgui.WINDOW_NO_RESIZE |
                               imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_BACKGROUND |
                               imgui.WINDOW_NO_SAVED_SETTINGS |
                               imgui.WINDOW_NO_INPUTS))
            draw_box_select_overlay(g_ui)
            draw_list = imgui.get_window_draw_list()
            _, toolbar_h_toast, _ = _ui_layout_metrics()
            draw_toasts(g_ui, WIN_W, toolbar_h_toast, g_ui.ui_scale, draw_list)
            imgui.end()

            draw_toolbar(g_ui, g_editor, g_renderer, g_camera, WIN_W)
            draw_bone_panel(g_ui, g_editor, WIN_W, WIN_H,
                            g_renderer, g_skeleton_sticks, g_camera)

            draw_animation_panel(g_ui, g_editor, WIN_W, WIN_H)
            draw_anim_source_picker(g_ui, g_editor)
            draw_anim_exit_confirm(g_ui, g_editor)
            draw_invalid_binding_dialog(g_ui, g_editor)

            draw_status_bar(g_ui, g_editor, WIN_W, WIN_H)

            imgui.render()
            g_imgui_impl.render(imgui.get_draw_data())

            glfw.swap_buffers(window)

            if _last_loop_err[2] > 0:
                logger.error("previous error '%s: %s' repeated %d times",
                             _last_loop_err[0], _last_loop_err[1], _last_loop_err[2])
            _last_loop_err = (None, None, 0)

        except Exception as _loop_exc:
            typ, msg = type(_loop_exc).__name__, str(_loop_exc)
            if _last_loop_err[0] == typ and _last_loop_err[1] == msg:
                _last_loop_err = (typ, msg, _last_loop_err[2] + 1)
            else:
                if _last_loop_err[2] > 0:
                    logger.error("previous error '%s: %s' repeated %d times",
                                 _last_loop_err[0], _last_loop_err[1], _last_loop_err[2])
                logger.exception("main loop error")
                _last_loop_err = (typ, msg, 0)

    if hasattr(g_renderer, "release"):
        g_renderer.release()
    g_imgui_impl.shutdown()
    try:
        imgui.destroy_context()
    except RuntimeError:
        pass
    glfw.terminate()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("fatal error in main()")
        raise
