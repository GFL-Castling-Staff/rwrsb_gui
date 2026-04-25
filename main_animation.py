"""
main_animation.py  --  rwrsb_anim 动画工具入口

和 rwrsb_gui.exe 同代码库,但启动后:
  - app_mode = "animation"
  - 自动加载 vanilla 标准 skeleton(presets/human_skeleton.json)
  - 自动进入动画模式(空白 animation)
  - 不渲染体素(voxels 列表始终为空,VoxelRenderer.render 内部守卫自动跳过)

本文件刻意复制 main.py 的大部分基础设施(GLFW 回调 / 字体 / 错误恢复 / overlay)
而不抽公共代码,避免两个 entry 互相牵扯。如果将来真的需要再抽。
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
                          draw_anim_exit_confirm)
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

g_editor          = EditorState()
g_camera          = OrbitCamera(WIN_W, WIN_H)
g_ui              = UIState()
g_skeleton_sticks = [None]   # mutable ref: g_skeleton_sticks[0]

g_mouse_x = g_mouse_y = 0.0
g_lmb_down    = False
g_particle_drag_active = False
g_drag_particle_idx = -1
g_drag_plane_normal = None
g_drag_grab_offset = None
g_drag_particle_origin = None
g_drag_origins = {}  # dict[int, np.ndarray]: 多选整体平移的所有选中点初始位置
g_hover_particle_idx = -1
g_positions_np = None          # (N,3) float32 cache for picking
g_renderer     = None          # set in main()
g_imgui_impl   = None          # GlfwRenderer set in main()


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
        return f"{base} — {g_editor.current_animation.name}"
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
    arr = np.array(
        [(p["x"], p["y"], p["z"]) for p in g_editor.particles],
        dtype=np.float32,
    )
    g_positions_np = arr


def _pick_particle(mx, my):
    if g_positions_np is None or len(g_positions_np) == 0:
        return -1
    panel_w, toolbar_h, status_h = _ui_layout_metrics()
    vp_w = WIN_W - panel_w
    vp_h = WIN_H - toolbar_h - status_h
    if vp_w <= 0 or vp_h <= 0:
        return -1
    # 把视口空间坐标转给 picker
    local_x = mx
    local_y = my - toolbar_h
    mvp = g_camera.get_mvp()
    return pick_particle_screen(mvp, g_positions_np, local_x, local_y, vp_w, vp_h)


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
    global g_lmb_down
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
        # commit 4 在这里实现粒子拾取/拖动/box select；commit 3 暂不接

    g_camera.on_mouse_button(button, action, mods, g_mouse_x, g_mouse_y)


@_safe_callback
def on_cursor_pos(window, xpos, ypos):
    global g_mouse_x, g_mouse_y, g_hover_particle_idx
    g_mouse_x = xpos
    g_mouse_y = ypos
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
            # 居中到 skeleton bbox（voxels 为空，reset_to_model 会 no-op，
            # 这里手工算 skeleton bbox 当作居中）
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
                g_camera._dirty = True


@_safe_callback
def on_char(window, codepoint):
    if g_imgui_impl:
        g_imgui_impl.char_callback(window, codepoint)


@_safe_callback
def on_drop(window, paths):
    # commit 4 实现：拖入 .xml 自动判定（skeleton XML / animation XML）
    if paths:
        logger.info("drop received: %s (handler not yet implemented)", paths[0])


@_safe_callback
def on_resize(window, width, height):
    global WIN_W, WIN_H
    WIN_W, WIN_H = width, height
    g_camera.resize(width, height)


# ── main ──────────────────────────────────────

def main():
    global g_renderer, g_imgui_impl, WIN_W, WIN_H

    # 显式声明这是动画工具 entry
    g_ui.app_mode = "animation"

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

    # ── 启动时自动加载 vanilla skeleton ──
    try:
        preset_path = resource_path("presets", "human_skeleton.json")
        g_editor.load_skeleton_preset(preset_path)
        logger.info("loaded default human skeleton (%d particles)",
                    len(g_editor.particles))
    except Exception as exc:
        logger.exception("failed to load default skeleton")
        g_ui.push_toast(f"加载默认骨架失败: {exc}", "error", exc_info=True)

    # ── 自动进入动画模式 ──
    try:
        new_anim = Animation(name="new_animation", loop=False, end=1.0, speed=1.0)
        # enter_animation_mode 会自动加第 0 帧
        g_editor.enter_animation_mode(new_anim)
    except Exception as exc:
        logger.exception("failed to enter animation mode")
        g_ui.push_toast(f"进入动画模式失败: {exc}", "error", exc_info=True)

    # ── 居中到 skeleton ──
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
            if g_ui._language_dirty:
                glfw.set_window_title(window, _window_title())
                g_ui._language_dirty = False

            imgui.new_frame()

            # ── commit 4：动画播放推进 ──
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

            # 上传 skeleton lines（如果 dirty）
            if g_editor.skeleton_dirty and g_renderer is not None:
                g_renderer.upload_skeleton_lines(g_editor.particles, g_editor.sticks)
                rebuild_positions_cache()
                g_editor.skeleton_dirty = False

            # ── 3D 场景 ──
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
                # 动画模式下 g_editor.voxels 永远为空，render() 内部 n_voxels=0 守卫
                # 自动跳过体素绘制；skeleton 正常渲染。
                g_renderer.highlight_selected_particle_indices = list(
                    g_editor.selected_particles
                )
                g_renderer.render(mvp)

            ctx.viewport = (0, 0, max(fb_w, 1), max(fb_h, 1))

            # ── UI ──
            # overlay（toast / box select 浮层）
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

            # 工具栏（内部按 app_mode 分流）
            draw_toolbar(g_ui, g_editor, g_renderer, g_camera, WIN_W)

            # bone panel：动画模式下内部 early return
            draw_bone_panel(g_ui, g_editor, WIN_W, WIN_H,
                            g_renderer, g_skeleton_sticks, g_camera)

            # 动画面板（commit 4 实现主体）
            draw_animation_panel(g_ui, g_editor, WIN_W, WIN_H)
            draw_anim_source_picker(g_ui, g_editor)
            draw_anim_exit_confirm(g_ui, g_editor)

            draw_status_bar(g_ui, g_editor, WIN_W, WIN_H)

            # 复用现有对话框（commit 4 改造为接 anim 的 source_path / save_path）
            draw_load_dialog(g_ui, g_editor, g_renderer,
                             g_skeleton_sticks, WIN_W, WIN_H)
            draw_save_dialog(g_ui, g_editor, g_skeleton_sticks, WIN_W, WIN_H)

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

    g_renderer.release() if hasattr(g_renderer, "release") else None
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
