"""
main.py  --  rwrsb_bind v1.0.0  (pyimgui + ModernGL + GLFW)
绑骨工具入口：骨架结构编辑、体素绑定、预设管理。
Usage: python main.py [optional_file.vox]
       or drag a .vox / .xml onto the window
"""
import sys
import os
import logging
import functools
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
from renderer     import (VoxelRenderer, pick_voxel, box_select_voxels,
                          pick_particle_screen, box_select_particles)
from ui_panels    import (UIState, draw_toolbar, draw_bone_panel,
                          draw_status_bar, draw_load_dialog, draw_save_dialog,
                          draw_preset_dialog,
                          draw_box_select_overlay, draw_exit_dialog,
                          draw_toasts)

import time
import math
line_count_est = 0
_grid_log_counter = 0
_grid_sig_cache = None
_mirror_sig_cache = None

logger = logging.getLogger(__name__)

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
g_drag_origins = {}  # dict[int, np.ndarray]: F5 多选整体平移的所有选中点初始位置
g_mirror_edit_drag_mode = None
g_mirror_edit_plane_normal = None
g_mirror_edit_grab_offset = None
g_hover_particle_idx = -1
g_positions_np = None          # (N,3) float32 cache for picking
g_renderer     = None          # set in main()
g_imgui_impl   = None          # GlfwRenderer set in main()
g_style_snapshot = None

g_first_upload_logged = False  # 诊断用：只在第一次 upload 时 log


def _ui_layout_metrics():
    scale = max(0.8, min(1.75, getattr(g_ui, "ui_scale", 1.0)))
    panel_w = int(round(PANEL_W * scale))
    toolbar_h = int(round(TOOLBAR_H * scale))
    status_h = int(round(STATUS_H * scale))
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
                continue
    io.fonts.add_font_default()
    return None


def _apply_ui_scale():
    global g_style_snapshot
    scale = max(0.8, min(1.75, g_ui.ui_scale))
    if g_ui._applied_scale == scale:
        return
    imgui.style_colors_dark()
    style = imgui.get_style()
    if g_style_snapshot is None:
        g_style_snapshot = {}
        for name in [
            "window_padding",
            "window_rounding",
            "window_border_size",
            "window_min_size",
            "window_title_align",
            "child_rounding",
            "child_border_size",
            "popup_rounding",
            "popup_border_size",
            "frame_padding",
            "frame_rounding",
            "frame_border_size",
            "item_spacing",
            "item_inner_spacing",
            "cell_padding",
            "touch_extra_padding",
            "indent_spacing",
            "columns_min_spacing",
            "scrollbar_size",
            "scrollbar_rounding",
            "grab_min_size",
            "grab_rounding",
            "log_slider_deadzone",
            "tab_rounding",
            "tab_border_size",
            "tab_min_width_for_close_button",
            "button_text_align",
            "selectable_text_align",
            "display_window_padding",
            "display_safe_area_padding",
            "mouse_cursor_scale",
        ]:
            if hasattr(style, name):
                value = getattr(style, name)
                g_style_snapshot[name] = tuple(value) if isinstance(value, (tuple, list)) else value

    for name, value in g_style_snapshot.items():
        if isinstance(value, tuple):
            setattr(style, name, tuple(float(v) * scale for v in value))
        else:
            try:
                setattr(style, name, float(value) * scale)
            except Exception:
                setattr(style, name, value)

    imgui.get_io().font_global_scale = scale
    g_ui._applied_scale = scale


def _window_title():
    if g_ui.language == "zh":
        return "rwrsb_bind v1.0.0 -- RWR 骨架绑定编辑器"
    return "rwrsb_bind v1.0.0 -- RWR Skeleton Binder"


def _prepare_save_dialog():
    g_ui.show_save_dialog = True
    path = g_editor.source_path or ""
    if path.lower().endswith(".vox"):
        path = path[:-4] + "_bound.xml"
    g_ui.save_path_buf = path
    g_ui._save_error = ""


def rebuild_positions_cache():
    global g_positions_np
    if g_editor.voxels:
        g_positions_np = np.array(
            [(v[0], v[1], v[2]) for v in g_editor.voxels], dtype=np.float32)
    else:
        g_positions_np = None


def is_over_viewport(x, y):
    panel_w, toolbar_h, status_h = _ui_layout_metrics()
    return (x < WIN_W - panel_w and
            y > toolbar_h and
            y < WIN_H - status_h)


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


def mirror_grid_step_value():
    if g_ui.mirror_grid_mode == 0:
        return 0.5
    if g_ui.mirror_grid_mode == 1:
        return 1.0
    return float(max(1, int(g_ui.mirror_grid_multiple)))


# ── interaction helpers ───────────────────────

def _do_brush_paint(sx, sy):
    if not g_ui.allow_skeleton_edit:
        return
    if g_positions_np is None or len(g_positions_np) == 0:
        return
    # 窗口坐标 → viewport 坐标（camera 的 width/height 每帧设为 vp_w/vp_h）
    vx = sx
    _, toolbar_h, _ = _ui_layout_metrics()
    vy = sy - toolbar_h
    origin, direction = g_camera.get_ray(vx, vy)
    hit = pick_voxel(origin, direction, g_positions_np)
    if hit >= 0:
        g_editor.bind_voxels([hit], g_editor.active_stick_idx)


def _finish_box_select():
    panel_w, toolbar_h, status_h = _ui_layout_metrics()
    vp_w = WIN_W - panel_w
    vp_h = WIN_H - toolbar_h - status_h
    mvp = g_camera.get_mvp()
    io = imgui.get_io()
    shift = io.key_shift
    ctrl = io.key_ctrl

    if g_editor.tool_mode == 'bone_edit':
        if g_editor.mirror_mode:
            return
        # F3: 粒子框选
        positions = particle_positions_np()
        if len(positions) == 0:
            return
        indices = box_select_particles(
            mvp, positions,
            g_ui.box_x0, g_ui.box_y0 - toolbar_h,
            g_ui.box_x1, g_ui.box_y1 - toolbar_h,
            vp_w, vp_h)
        alt = io.key_alt
        if shift and alt:
            # Shift+Alt: 减选
            for i in indices:
                g_editor.selected_particles.discard(int(i))
        elif ctrl:
            # Ctrl: toggle
            for i in indices:
                if i in g_editor.selected_particles:
                    g_editor.selected_particles.discard(i)
                else:
                    g_editor.selected_particles.add(i)
        elif shift:
            g_editor.selected_particles.update(indices)
        else:
            g_editor.replace_selected_particles(indices)
        # active 兜底：active 被减掉或不在集合中时重新选一个，空集则 -1
        if g_editor.selected_particles:
            if g_editor.active_particle_idx not in g_editor.selected_particles:
                g_editor.set_active_particle(next(iter(g_editor.selected_particles)))
        else:
            g_editor.active_particle_idx = -1
    elif g_editor.tool_mode == 'voxel_select':
        if g_positions_np is None or len(g_positions_np) == 0:
            return
        indices = box_select_voxels(
            mvp, g_positions_np,
            g_ui.box_x0, g_ui.box_y0 - toolbar_h,
            g_ui.box_x1, g_ui.box_y1 - toolbar_h,
            vp_w, vp_h)
        alt = io.key_alt
        if shift and alt:
            # Shift+Alt: 减选
            for i in indices:
                g_editor.selected_voxels.discard(int(i))
            g_editor.gpu_dirty = True
        elif ctrl:
            # Ctrl: toggle
            for i in indices:
                i = int(i)
                if i in g_editor.selected_voxels:
                    g_editor.selected_voxels.discard(i)
                else:
                    g_editor.selected_voxels.add(i)
            g_editor.gpu_dirty = True
        elif shift:
            # Shift: 加选
            g_editor.selected_voxels.update(int(i) for i in indices)
            g_editor.gpu_dirty = True
        else:
            # 替换
            g_editor.selected_voxels = {int(i) for i in indices}
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
    panel_w, toolbar_h, status_h = _ui_layout_metrics()
    vp_w = WIN_W - panel_w
    vp_h = WIN_H - toolbar_h - status_h
    mvp = g_camera.get_mvp()
    return pick_particle_screen(mvp, positions, sx, sy - toolbar_h, vp_w, vp_h)


def _begin_particle_drag(sx, sy, particle_idx, push_undo=True):
    global g_particle_drag_active, g_drag_particle_idx, g_drag_plane_normal, g_drag_grab_offset, g_drag_particle_origin, g_drag_origins
    particle = g_editor.particles[particle_idx]
    plane_point = np.array([particle['x'], particle['y'], particle['z']], dtype=np.float32)
    cam_pos = np.asarray(g_camera.get_position(), dtype=np.float32)
    plane_normal = plane_point - cam_pos
    norm = np.linalg.norm(plane_normal)
    if norm < 1e-6:
        plane_normal = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    else:
        plane_normal /= norm

    _, toolbar_h, _ = _ui_layout_metrics()
    origin, direction = g_camera.get_ray(sx, sy - toolbar_h)
    hit = _ray_plane_intersection(
        np.asarray(origin, dtype=np.float32),
        np.asarray(direction, dtype=np.float32),
        plane_point,
        plane_normal,
    )
    if hit is None:
        hit = plane_point.copy()

    if push_undo:
        g_editor._push_undo()
    g_editor.set_active_particle(particle_idx)
    g_particle_drag_active = True
    g_drag_particle_idx = particle_idx
    g_drag_plane_normal = plane_normal
    g_drag_grab_offset = plane_point - hit
    g_drag_particle_origin = plane_point.copy()
    # F5: 记录所有需要整体平移的粒子的起点
    global g_drag_origins
    drag_set = set(g_editor.selected_particles) if particle_idx in g_editor.selected_particles else {particle_idx}
    g_drag_origins = {
        i: np.array([g_editor.particles[i]['x'], g_editor.particles[i]['y'], g_editor.particles[i]['z']],
                    dtype=np.float32)
        for i in drag_set
    }

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


def _mirror_handle_length():
    if g_camera.is_ortho:
        return max(float(g_camera.ortho_size) * 0.35, 4.0)
    return max(float(g_camera.distance) * 0.18, 4.0)


def _mirror_plane_basis():
    normal = np.asarray(g_editor.mirror_plane_normal, dtype=np.float32)
    norm = float(np.linalg.norm(normal))
    if norm < 1e-6:
        normal = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    else:
        normal = normal / norm
    ref = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    if abs(float(np.dot(ref, normal))) > 0.95:
        ref = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    tangent = np.cross(normal, ref)
    tangent /= max(float(np.linalg.norm(tangent)), 1e-6)
    bitangent = np.cross(normal, tangent)
    bitangent /= max(float(np.linalg.norm(bitangent)), 1e-6)
    return tangent, bitangent, normal


def _mirror_handle_positions():
    origin = np.asarray(g_editor.mirror_plane_origin, dtype=np.float32)
    normal = np.asarray(g_editor.mirror_plane_normal, dtype=np.float32)
    arrow = origin + normal * _mirror_handle_length()
    return origin, arrow


def _pick_mirror_handle(sx, sy):
    if not (g_editor.mirror_mode and g_editor.mirror_edit_mode):
        return None
    positions = np.vstack(_mirror_handle_positions()).astype(np.float32)
    panel_w, toolbar_h, status_h = _ui_layout_metrics()
    vp_w = WIN_W - panel_w
    vp_h = WIN_H - toolbar_h - status_h
    mvp = g_camera.get_mvp()
    idx = pick_particle_screen(mvp, positions, sx, sy - toolbar_h, vp_w, vp_h, radius_px=18.0)
    if idx == 0:
        return "origin"
    if idx == 1:
        return "normal"
    return None


def _begin_mirror_edit_drag(sx, sy, mode):
    global g_mirror_edit_drag_mode, g_mirror_edit_plane_normal, g_mirror_edit_grab_offset
    g_mirror_edit_drag_mode = mode
    if mode == "origin":
        g_mirror_edit_plane_normal = np.asarray(g_editor.mirror_plane_normal, dtype=np.float32).copy()
    else:
        g_mirror_edit_plane_normal = np.asarray(g_camera.get_view_direction(), dtype=np.float32).copy()
    origin = np.asarray(g_editor.mirror_plane_origin, dtype=np.float32)
    _, toolbar_h, _ = _ui_layout_metrics()
    ray_origin, ray_dir = g_camera.get_ray(sx, sy - toolbar_h)
    if mode == "origin":
        hit = _ray_plane_intersection(
            np.asarray(ray_origin, dtype=np.float32),
            np.asarray(ray_dir, dtype=np.float32),
            origin,
            g_mirror_edit_plane_normal,
        )
        g_mirror_edit_grab_offset = origin - hit if hit is not None else np.zeros(3, dtype=np.float32)
    else:
        g_mirror_edit_grab_offset = None


def _update_mirror_edit_drag(sx, sy):
    if not g_mirror_edit_drag_mode:
        return
    origin = np.asarray(g_editor.mirror_plane_origin, dtype=np.float32)
    _, toolbar_h, _ = _ui_layout_metrics()
    ray_origin, ray_dir = g_camera.get_ray(sx, sy - toolbar_h)
    ray_origin = np.asarray(ray_origin, dtype=np.float32)
    ray_dir = np.asarray(ray_dir, dtype=np.float32)
    if g_mirror_edit_drag_mode == "origin":
        hit = _ray_plane_intersection(ray_origin, ray_dir, origin, g_mirror_edit_plane_normal)
        if hit is None:
            return
        new_origin = hit + g_mirror_edit_grab_offset
        g_editor.set_mirror_plane_origin(new_origin[0], new_origin[1], new_origin[2])
        return

    plane_point = np.array([origin[0], origin[1], origin[2]], dtype=np.float32)
    hit = _ray_plane_intersection(ray_origin, ray_dir, plane_point, g_mirror_edit_plane_normal)
    if hit is None:
        return
    vec = np.array([hit[0] - origin[0], hit[1] - origin[1], hit[2] - origin[2]], dtype=np.float32)
    length = float(np.linalg.norm(vec))
    if length < 1e-6:
        return
    g_editor.set_mirror_plane_normal(vec[0], vec[1], vec[2])


def _end_mirror_edit_drag():
    global g_mirror_edit_drag_mode, g_mirror_edit_plane_normal, g_mirror_edit_grab_offset
    g_mirror_edit_drag_mode = None
    g_mirror_edit_plane_normal = None
    g_mirror_edit_grab_offset = None


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


def _mirrored_particle_position(pos, axis):
    mirrored = np.array(pos, dtype=np.float32)
    normal = np.asarray(g_editor.mirror_plane_normal, dtype=np.float32)
    origin = np.asarray(g_editor.mirror_plane_origin, dtype=np.float32)
    denom = float(np.dot(normal, normal))
    if denom < 1e-6:
        return mirrored
    offset = mirrored - origin
    return mirrored - 2.0 * np.dot(offset, normal) / denom * normal


def _snap_to_mirror_grid(pos):
    if not (g_editor.mirror_mode and g_ui.snap_to_mirror_grid):
        return np.asarray(pos, dtype=np.float32)
    tangent, bitangent, normal = _mirror_plane_basis()
    origin = np.asarray(g_editor.mirror_plane_origin, dtype=np.float32)
    rel = np.asarray(pos, dtype=np.float32) - origin
    u = float(np.dot(rel, tangent))
    v = float(np.dot(rel, bitangent))
    w = float(np.dot(rel, normal))
    step = mirror_grid_step_value()
    u = round(u / step) * step
    v = round(v / step) * step
    return origin + tangent * u + bitangent * v + normal * w


def _sync_mirror_pair_from_particle(source_idx, push_undo=True):
    if (
        not g_editor.mirror_mode
        or not g_editor.mirror_pair
        or source_idx not in g_editor.mirror_pair
    ):
        return False

    pair_a, pair_b = g_editor.mirror_pair
    partner_idx = pair_b if source_idx == pair_a else pair_a
    source = g_editor.particles[source_idx]
    current = np.array([source["x"], source["y"], source["z"]], dtype=np.float32)
    mirrored = _mirrored_particle_position(current, g_editor.mirror_axis)
    partner = g_editor.particles[partner_idx]
    partner_pos = np.array([partner["x"], partner["y"], partner["z"]], dtype=np.float32)
    if np.allclose(partner_pos, mirrored, atol=1e-6):
        return False

    if push_undo:
        g_editor._push_undo()
    g_editor.set_particle_position(partner_idx, mirrored[0], mirrored[1], mirrored[2], push_undo=False)
    g_editor.set_active_particle(source_idx)
    return True


def _update_particle_drag(window, sx, sy):
    if not g_particle_drag_active or g_drag_particle_idx < 0:
        return
    particle = g_editor.particles[g_drag_particle_idx]
    plane_point = np.array([particle['x'], particle['y'], particle['z']], dtype=np.float32)
    _, toolbar_h, _ = _ui_layout_metrics()
    origin, direction = g_camera.get_ray(sx, sy - toolbar_h)
    hit = _ray_plane_intersection(
        np.asarray(origin, dtype=np.float32),
        np.asarray(direction, dtype=np.float32),
        plane_point,
        g_drag_plane_normal,
    )
    if hit is None:
        return
    pos = hit + g_drag_grab_offset
    # 被直接拖动的点先做轴约束和网格吸附
    pos = _apply_particle_drag_rules(pos, _drag_axis_mask(window))
    if (
        g_editor.mirror_mode
        and g_editor.mirror_pair
        and g_drag_particle_idx in g_editor.mirror_pair
    ):
        pos = _snap_to_mirror_grid(pos)
    # 应用到被拖点
    g_editor.set_particle_position(g_drag_particle_idx, pos[0], pos[1], pos[2], push_undo=False)
    if (
        g_editor.mirror_mode
        and g_editor.mirror_pair
        and g_drag_particle_idx in g_editor.mirror_pair
    ):
        pair_a, pair_b = g_editor.mirror_pair
        partner_idx = pair_b if g_drag_particle_idx == pair_a else pair_a
        mirrored = _mirrored_particle_position(pos, g_editor.mirror_axis)
        g_editor.set_particle_position(partner_idx, mirrored[0], mirrored[1], mirrored[2], push_undo=False)
        g_editor.set_active_particle(g_drag_particle_idx)
        return
    # F5: 其他选中点按相同 delta 跟随（不做各自吸附，以保持组内相对位置）
    if len(g_drag_origins) > 1:
        anchor_origin = g_drag_origins.get(g_drag_particle_idx)
        if anchor_origin is not None:
            delta = pos - anchor_origin
            for idx, origin_pos in g_drag_origins.items():
                if idx == g_drag_particle_idx:
                    continue
                new_p = origin_pos + delta
                g_editor.set_particle_position(idx, new_p[0], new_p[1], new_p[2], push_undo=False)
    g_editor.set_active_particle(g_drag_particle_idx)


def _end_particle_drag():
    global g_particle_drag_active, g_drag_particle_idx, g_drag_plane_normal, g_drag_grab_offset, g_drag_particle_origin
    g_particle_drag_active = False
    g_drag_particle_idx = -1
    g_drag_plane_normal = None
    g_drag_grab_offset = None
    g_drag_particle_origin = None
    g_drag_origins.clear()


def _update_grid():
    global _grid_sig_cache
    if g_renderer is None:
        return
    g_renderer.show_grid = g_ui.show_grid

    if not g_ui.show_grid:
        # 网格关闭：只在状态翻转时清一次
        if _grid_sig_cache != "OFF":
            g_renderer.upload_grid((0.0, 0.0, 0.0), 0.0, 0.0, 1, False, False, False)
            _grid_sig_cache = "OFF"
        return

    # 签名：去掉 active_particle_idx / active_pos（网格中心不再跟随粒子）
    sig = (
        bool(g_ui.show_grid_xz), bool(g_ui.show_grid_xy), bool(g_ui.show_grid_yz),
        int(g_ui.grid_mode), int(g_ui.grid_multiple),
        bool(g_ui.snap_particles_to_grid),
        len(g_editor.voxels), len(g_editor.particles),
        round(float(g_camera.ortho_size), 3),
        round(float(g_camera.distance), 3),
    )
    if sig == _grid_sig_cache:
        return
    _grid_sig_cache = sig

    # 网格中心固定在世界原点，与动画模式保持一致
    center = np.array([0.0, 0.0, 0.0], dtype=np.float32)

    # extent 取"覆盖原点到最远点的距离"和相机 extent 的较大者
    # 用 max(|arr|) 而非 AABB 对角，因为 center 固定为原点而非模型中心
    points = []
    points.extend([(v[0], v[1], v[2]) for v in g_editor.voxels])
    points.extend([(p['x'], p['y'], p['z']) for p in g_editor.particles])
    if points:
        arr = np.array(points, dtype=np.float32)
        model_extent = max(float(np.max(np.abs(arr))) * 1.2, 8.0)
    else:
        model_extent = 16.0

    camera_extent = max(float(g_camera.ortho_size) * 1.2, float(g_camera.distance) * 0.35, 8.0)
    extent = max(model_extent, camera_extent)
    step = grid_step_value()
    major_every = 2 if step == 0.5 else 4
    g_renderer.upload_grid(
        center, extent, step, major_every,
        g_ui.show_grid_xz, g_ui.show_grid_xy, g_ui.show_grid_yz
    )


def _update_mirror_indicator():
    global _mirror_sig_cache
    if g_renderer is None:
        return
    g_renderer.show_mirror_plane = bool(g_editor.mirror_mode)

    if not g_editor.mirror_mode:
        # 镜像关闭：只在状态翻转时清一次
        if _mirror_sig_cache != "OFF":
            g_renderer.upload_mirror_indicator((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0)
            _mirror_sig_cache = "OFF"
        return

    # 签名：包括所有影响 upload_mirror_indicator 输出的输入
    sig = (
        tuple(round(float(x), 3) for x in g_editor.mirror_plane_origin),
        tuple(round(float(x), 3) for x in g_editor.mirror_plane_normal),
        bool(g_editor.mirror_edit_mode),
        bool(g_ui.show_mirror_grid),
        round(float(mirror_grid_step_value()), 3),
        int(g_ui.mirror_grid_mode), int(g_ui.mirror_grid_multiple),
        len(g_editor.voxels), len(g_editor.particles),
        round(float(_mirror_handle_length()), 3),
    )
    if sig == _mirror_sig_cache:
        return
    _mirror_sig_cache = sig

    # —— 以下是原有的实际计算逻辑，保持不变 ——
    points = []
    points.extend([(v[0], v[1], v[2]) for v in g_editor.voxels])
    points.extend([(p['x'], p['y'], p['z']) for p in g_editor.particles])
    if points:
        arr = np.array(points, dtype=np.float32)
        mins = arr.min(axis=0)
        maxs = arr.max(axis=0)
        extent = max(float(np.max(maxs - mins)) * 0.75, 8.0)
    else:
        extent = 16.0

    g_renderer.upload_mirror_indicator(
        g_editor.mirror_plane_origin,
        g_editor.mirror_plane_normal,
        extent,
        show_handles=g_editor.mirror_edit_mode,
        handle_len=_mirror_handle_length(),
        show_grid=g_ui.show_mirror_grid,
        grid_step=mirror_grid_step_value(),
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
            logger.debug('voxel count = %d', len(g_editor.voxels))
            logger.debug('bbox x:[%.1f,%.1f]  y:[%.1f,%.1f]  z:[%.1f,%.1f]',
                         min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
            logger.debug('camera target=%s  distance=%.1f',
                         g_camera.target, g_camera.distance)
            logger.debug('camera position=%s', g_camera.get_position())
            for i, v in enumerate(g_editor.voxels[:3]):
                logger.debug('voxel[%d] = %s', i, v)
        else:
            logger.debug('voxel list is EMPTY after load')
        g_ui.push_toast(f"已加载: {Path(path).name}", "success")
        # _load_file try 块的成功分支末尾（诊断日志之前或之后都行）
        global _grid_sig_cache, _mirror_sig_cache
        _grid_sig_cache = None
        _mirror_sig_cache = None
    except Exception as e:
        g_ui.push_toast(f"加载失败: {e}", "error", exc_info=sys.exc_info())


# ── GLFW callbacks ────────────────────────────

def _safe_callback(fn):
    """装饰器：捕获回调里的业务异常，写 log 后 return，不让程序崩。"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception("GLFW callback %s failed", fn.__name__)
    return wrapper


@_safe_callback
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
            mirror_handle = _pick_mirror_handle(g_mouse_x, g_mouse_y)
            if mirror_handle is not None:
                _begin_mirror_edit_drag(g_mouse_x, g_mouse_y, mirror_handle)
                return
            if g_editor.mirror_mode and g_editor.mirror_edit_mode:
                return
            hit_particle = _pick_particle(g_mouse_x, g_mouse_y)
            shift = bool(mods & glfw.MOD_SHIFT)
            ctrl = bool(mods & glfw.MOD_CONTROL)

            # ── bone_edit 模式：点击粒子 → 选择 or 拖动 ──
            if g_editor.tool_mode == 'bone_edit' and g_ui.allow_skeleton_edit:
                if g_editor.mirror_mode:
                    mirror_pair = set(g_editor.mirror_pair or ())
                    if hit_particle in mirror_pair:
                        g_editor.set_active_particle(hit_particle)
                        source = g_editor.particles[hit_particle]
                        current = np.array([source["x"], source["y"], source["z"]], dtype=np.float32)
                        expected = _mirrored_particle_position(current, g_editor.mirror_axis)
                        pair_a, pair_b = g_editor.mirror_pair
                        partner_idx = pair_b if hit_particle == pair_a else pair_a
                        partner = g_editor.particles[partner_idx]
                        partner_pos = np.array([partner["x"], partner["y"], partner["z"]], dtype=np.float32)
                        need_undo = g_ui.allow_particle_edit or (not np.allclose(partner_pos, expected, atol=1e-6))
                        if need_undo:
                            g_editor._push_undo()
                        mirrored_now = _sync_mirror_pair_from_particle(
                            hit_particle,
                            push_undo=False,
                        )
                        if g_ui.allow_particle_edit:
                            _begin_particle_drag(
                                g_mouse_x,
                                g_mouse_y,
                                hit_particle,
                                push_undo=False,
                            )
                    return
                if hit_particle >= 0:
                    alt = bool(mods & glfw.MOD_ALT)
                    if shift and alt:
                        # Shift+Alt+点击: 从选集中减去
                        g_editor.selected_particles.discard(hit_particle)
                        if g_editor.active_particle_idx == hit_particle:
                            if g_editor.selected_particles:
                                g_editor.set_active_particle(next(iter(g_editor.selected_particles)))
                            else:
                                g_editor.active_particle_idx = -1
                    elif shift:
                        # Shift+点击：追加到选中，设为 active
                        g_editor.add_selected_particle(hit_particle)
                        g_editor.set_active_particle(hit_particle)
                    elif ctrl:
                        # Ctrl+点击：toggle，如新加入则设 active；如移除且是 active 则回退
                        was_added = g_editor.toggle_selected_particle(hit_particle)
                        if was_added:
                            g_editor.set_active_particle(hit_particle)
                        elif g_editor.active_particle_idx == hit_particle:
                            # 从集合里任选一个作为新 active（或 -1）
                            if g_editor.selected_particles:
                                g_editor.set_active_particle(next(iter(g_editor.selected_particles)))
                            else:
                                g_editor.active_particle_idx = -1
                    else:
                        # 普通点击：若点中当前多选成员则保留集合以支持整体拖拽，否则切换为单选
                        preserve_group = hit_particle in g_editor.selected_particles
                        if not preserve_group:
                            g_editor.replace_selected_particles([hit_particle])
                        if g_ui.allow_particle_edit:
                            _begin_particle_drag(g_mouse_x, g_mouse_y, hit_particle)
                        else:
                            g_editor.set_active_particle(hit_particle)
                else:
                    # 未命中粒子
                    if shift or ctrl:
                        # 起始框选（Shift/Ctrl 语义延续到 _finish_box_select）
                        g_ui.box_selecting = True
                        g_ui.box_x0 = g_ui.box_x1 = g_mouse_x
                        g_ui.box_y0 = g_ui.box_y1 = g_mouse_y
                    else:
                        # 普通点击空白：清空选择，同时起框选（用户可能想框选）
                        g_editor.clear_selected_particles()
                        g_editor.active_particle_idx = -1
                        g_ui.box_selecting = True
                        g_ui.box_x0 = g_ui.box_x1 = g_mouse_x
                        g_ui.box_y0 = g_ui.box_y1 = g_mouse_y

            # ── brush 模式：点粒子无反应、未命中则涂刷 ──
            elif g_editor.tool_mode == 'brush' and g_ui.allow_skeleton_edit and g_editor.sticks:
                g_editor.begin_brush_stroke()
                _do_brush_paint(g_mouse_x, g_mouse_y)
                g_brush_active = True

            # ── voxel_select 模式：体素框选（原 select 行为，点粒子无反应）──
            elif g_editor.tool_mode == 'voxel_select' and g_ui.allow_skeleton_edit:
                g_ui.box_selecting = True
                g_ui.box_x0 = g_ui.box_x1 = g_mouse_x
                g_ui.box_y0 = g_ui.box_y1 = g_mouse_y
        else:
            if g_mirror_edit_drag_mode:
                _end_mirror_edit_drag()
            if g_particle_drag_active:
                _end_particle_drag()
            if g_brush_active:
                g_editor.commit_brush_stroke()
                g_brush_active = False
            if g_ui.box_selecting:
                g_ui.box_selecting = False
                _finish_box_select()

    g_camera.on_mouse_button(button, action, mods, g_mouse_x, g_mouse_y)


@_safe_callback
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
            g_renderer.highlight_selected_particle_indices = list(g_editor.selected_particles)
        return
    hover_particle = _pick_particle(xpos, ypos)
    g_hover_particle_idx = hover_particle
    if g_renderer is not None:
        if g_particle_drag_active:
            g_renderer.highlight_particle_idx = g_drag_particle_idx
            g_renderer.highlight_selected_particle_indices = list(g_editor.selected_particles)
        else:
            g_renderer.highlight_particle_idx = hover_particle if hover_particle >= 0 else g_editor.active_particle_idx
            g_renderer.highlight_selected_particle_indices = list(g_editor.selected_particles)
    if g_mirror_edit_drag_mode:
        _update_mirror_edit_drag(xpos, ypos)
        return
    if g_particle_drag_active:
        _update_particle_drag(window, xpos, ypos)
        return
    if g_ui.allow_skeleton_edit and g_lmb_down and g_brush_active and g_editor.tool_mode == 'brush':
        _do_brush_paint(xpos, ypos)
    if g_ui.allow_skeleton_edit and g_lmb_down and g_ui.box_selecting and g_editor.tool_mode in ('voxel_select', 'bone_edit'):
        g_ui.box_x1 = xpos
        g_ui.box_y1 = ypos
    g_camera.on_mouse_move(xpos, ypos)


@_safe_callback
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
            g_editor.undo()
        elif ctrl and key == glfw.KEY_Y:
            g_editor.redo()
        elif key == glfw.KEY_ESCAPE:
            g_editor.clear_selection()
            if g_editor.tool_mode == 'bone_edit':
                g_editor.clear_selected_particles()
                g_editor.exit_mirror_mode()
        elif key == glfw.KEY_F:
            g_camera.reset_to_model(g_editor.voxels)
        elif key == glfw.KEY_B:
            if g_ui.allow_skeleton_edit:
                g_editor.set_tool_mode('brush')
        elif key == glfw.KEY_V:
            if g_ui.allow_skeleton_edit:
                g_editor.set_tool_mode('voxel_select')
        elif key == glfw.KEY_E:
            if g_ui.allow_skeleton_edit:
                g_editor.set_tool_mode('bone_edit')


@_safe_callback
def on_char(window, codepoint):
    if g_imgui_impl:
        g_imgui_impl.char_callback(window, codepoint)


@_safe_callback
def on_drop(window, paths):
    if paths:
        _load_file(paths[0])


@_safe_callback
def on_resize(window, width, height):
    global WIN_W, WIN_H
    WIN_W, WIN_H = width, height
    g_camera.resize(width, height)


# ── main ──────────────────────────────────────

def main():
    global g_renderer, g_imgui_impl, g_first_upload_logged, WIN_W, WIN_H
    
    # 显式声明这是绑骨入口（默认值就是 "skeleton"，但写出来让意图清晰，
    # 与 main_animation.py 形成对照）
    g_ui.app_mode = "skeleton"

    if not glfw.init():
        raise RuntimeError("GLFW init failed")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.SAMPLES, 4)

    window = glfw.create_window(
        WIN_W, WIN_H, _window_title(), None, None)
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
    font_path = _configure_imgui_fonts()
    g_imgui_impl = GlfwRenderer(window, attach_callbacks=False)
    _apply_ui_scale()
    if font_path:
        logger.info("loaded font: %s", font_path)
    else:
        logger.warning("using default imgui font (no CJK font found)")

    # load file from argv
    if len(sys.argv) > 1:
        _load_file(sys.argv[1])

    _last_loop_err = (None, None, 0)   # (type_name, msg, repeat_count)
    # 放在 while 循环开始之前，和 _last_loop_err 那行附近
    _fps_accum_t = time.time()
    _fps_frames = 0
    # grid / mirror indicator 的脏检查签名缓存
    _grid_sig_cache = None
    _mirror_sig_cache = None

    while not glfw.window_should_close(window):
        try:
            glfw.poll_events()
            if glfw.window_should_close(window) and g_editor.is_dirty and not g_ui.show_exit_dialog and not g_ui.pending_exit_after_save:
                glfw.set_window_should_close(window, False)
                g_ui.show_exit_dialog = True
            g_imgui_impl.process_inputs()
            _apply_ui_scale()
            g_camera.invert_y = g_ui.invert_y_axis
            if g_ui._language_dirty:
                glfw.set_window_title(window, _window_title())
                g_ui._language_dirty = False

            imgui.new_frame()

            _update_grid()
            _update_mirror_indicator()
            if g_editor.skeleton_dirty and g_renderer is not None:
                g_renderer.upload_skeleton_lines(g_editor.particles, g_editor.sticks)
                g_editor.skeleton_dirty = False

            # update GPU buffers when dirty
            if g_editor.gpu_dirty and g_editor.voxels:
                positions, colors, selected = g_editor.build_instance_arrays()
                g_renderer.upload_voxels(positions, colors, selected)
                rebuild_positions_cache()
                if not g_first_upload_logged:
                    logger.debug('uploaded %d instances to GPU (renderer.n_voxels=%d)',
                                 len(positions), g_renderer.n_voxels)
                    g_first_upload_logged = True

            # 3-D scene: 先清整个 framebuffer，再把 viewport 限定在中央 3D 区域
            fb_w, fb_h = glfw.get_framebuffer_size(window)
            ctx.viewport = (0, 0, max(fb_w, 1), max(fb_h, 1))
            ctx.clear(0.15, 0.15, 0.18, 1.0)

            panel_w, toolbar_h, status_h = _ui_layout_metrics()
            vp_w = WIN_W - panel_w
            vp_h = WIN_H - toolbar_h - status_h

            if (g_editor.voxels and vp_w > 0 and vp_h > 0
                    and fb_w > 0 and fb_h > 0):
                # HiDPI：fb 尺寸可能比窗口尺寸大
                scale_x = fb_w / WIN_W
                scale_y = fb_h / WIN_H
                # OpenGL viewport 原点在左下；3D 区域位于状态栏之上、工具栏之下
                ctx.viewport = (
                    0,
                    int(status_h * scale_y),
                    int(vp_w * scale_x),
                    int(vp_h * scale_y),
                )
                # 相机 aspect 与 viewport 一致，避免拉伸
                g_camera.resize(vp_w, vp_h)
                mvp = g_camera.get_mvp()
                g_renderer.highlight_selected_particle_indices = list(g_editor.selected_particles)
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
            draw_list = imgui.get_window_draw_list()
            _, toolbar_h_toast, _ = _ui_layout_metrics()
            draw_toasts(g_ui, WIN_W, toolbar_h_toast, g_ui.ui_scale, draw_list)
            imgui.end()

            draw_toolbar(g_ui, g_editor, g_renderer, g_camera, WIN_W)
            draw_bone_panel(g_ui, g_editor, WIN_W, WIN_H,
                            g_renderer, g_skeleton_sticks, g_camera)
            draw_status_bar(g_ui, g_editor, WIN_W, WIN_H)

            draw_load_dialog(g_ui, g_editor, g_renderer,
                             g_skeleton_sticks, WIN_W, WIN_H)
            draw_save_dialog(g_ui, g_editor, g_skeleton_sticks, WIN_W, WIN_H)
            draw_preset_dialog(g_ui, g_editor, g_renderer,
                               g_skeleton_sticks, WIN_W, WIN_H)
            exit_action = draw_exit_dialog(g_ui, WIN_W, WIN_H)
            if exit_action == "discard":
                glfw.set_window_should_close(window, True)
            elif exit_action == "save":
                if g_editor.source_path and g_editor.source_path.lower().endswith(".xml"):
                    try:
                        g_editor.save_xml(g_editor.source_path, g_skeleton_sticks[0])
                        glfw.set_window_should_close(window, True)
                    except Exception as exc:
                        g_ui._save_error = str(exc)
                        _prepare_save_dialog()
                        g_ui.pending_exit_after_save = True
                else:
                    _prepare_save_dialog()
                    g_ui.pending_exit_after_save = True

            if g_ui.pending_exit_after_save and not g_editor.is_dirty and not g_ui.show_save_dialog:
                g_ui.pending_exit_after_save = False
                glfw.set_window_should_close(window, True)

            imgui.render()
            g_imgui_impl.render(imgui.get_draw_data())

            glfw.swap_buffers(window)
            
            # _fps_frames += 1
            # _now = time.time()
            # if _now - _fps_accum_t >= 1.0:
            #     logger.info("FPS=%d extent_active=%s", _fps_frames,
            #                 "yes" if g_editor.active_particle_idx >= 0 else "no")
            #     _fps_frames = 0
            #     _fps_accum_t = _now

            # 正常帧：如果之前有累积错误，补写一条汇总
            if _last_loop_err[2] > 0:
                logger.error("previous error '%s: %s' repeated %d times",
                             _last_loop_err[0], _last_loop_err[1], _last_loop_err[2])
            _last_loop_err = (None, None, 0)

        except Exception as _loop_exc:
            typ, msg = type(_loop_exc).__name__, str(_loop_exc)
            if _last_loop_err[0] == typ and _last_loop_err[1] == msg:
                # 与上一帧相同：累计，不重复写 log
                _last_loop_err = (typ, msg, _last_loop_err[2] + 1)
            else:
                # 新错误：先 flush 之前累积的
                if _last_loop_err[2] > 0:
                    logger.error("previous error '%s: %s' repeated %d times",
                                 _last_loop_err[0], _last_loop_err[1], _last_loop_err[2])
                logger.exception("main loop error")
                _last_loop_err = (typ, msg, 0)

    g_renderer.release()
    g_imgui_impl.shutdown()
    try:
        imgui.destroy_context()
    except RuntimeError:
        pass
    glfw.terminate()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logger.exception("fatal error in main()")
        raise
