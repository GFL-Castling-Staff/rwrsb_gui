"""
ui_panels.py  --  pyimgui version (v2.3)

变更说明:
  - 列表项展示的是 stick(不是单个骨骼节点),每项对应一个 constraintIndex
  - 删除按钮(原 "x")改为解绑按钮(现 "-"),仅清空该 stick 上的体素绑定,
    保留 stick 本身不变(RWR 动画系统要求 stick 数量稳定,不能随意增删)
  - Add Bone 相关 UI 全部移除
"""
import os
import imgui


class UIState:
    def __init__(self):
        self.show_load_dialog    = False
        self.show_save_dialog    = False
        self.show_preset_dialog  = False
        self.load_path_buf       = ""
        self.save_path_buf       = ""
        self.load_mode           = 'vox'

        self.trans_bias          = 127
        self.show_skeleton_lines = True

        self.box_selecting = False
        self.box_x0 = self.box_y0 = 0
        self.box_x1 = self.box_y1 = 0

        self._load_error = ""
        self._save_error = ""


# ── helpers ──────────────────────────────────

FIXED_FLAGS = (imgui.WINDOW_NO_TITLE_BAR | imgui.WINDOW_NO_RESIZE |
               imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_SAVED_SETTINGS)


def _push_green():
    imgui.push_style_color(imgui.COLOR_BUTTON, 0.2, 0.6, 0.2, 1.0)

def _push_blue():
    imgui.push_style_color(imgui.COLOR_BUTTON, 0.2, 0.4, 0.7, 1.0)

def _push_red():
    imgui.push_style_color(imgui.COLOR_BUTTON, 0.6, 0.15, 0.15, 1.0)


# ── toolbar ───────────────────────────────────

def draw_toolbar(ui_state, editor_state, renderer, camera, WIN_W):
    imgui.set_next_window_position(0, 0)
    imgui.set_next_window_size(WIN_W, 38)
    imgui.begin("##toolbar", flags=FIXED_FLAGS | imgui.WINDOW_NO_SCROLLBAR)

    if imgui.button("Open VOX"):
        ui_state.show_load_dialog = True
        ui_state.load_path_buf    = ""
        ui_state.load_mode        = 'vox'
        ui_state._load_error      = ""
    imgui.same_line()
    if imgui.button("Open XML"):
        ui_state.show_load_dialog = True
        ui_state.load_path_buf    = ""
        ui_state.load_mode        = 'xml'
        ui_state._load_error      = ""
    imgui.same_line()

    dirty = "*" if editor_state.is_dirty else ""
    if imgui.button(f"Save XML{dirty}"):
        ui_state.show_save_dialog = True
        p = editor_state.source_path or ""
        if p.lower().endswith('.vox'):
            p = p[:-4] + '_bound.xml'
        ui_state.save_path_buf = p
        ui_state._save_error   = ""
    imgui.same_line()
    imgui.separator()
    imgui.same_line()

    is_brush = editor_state.tool_mode == 'brush'
    if is_brush: _push_green()
    if imgui.button("Brush [B]"):
        editor_state.tool_mode = 'brush'
    if is_brush: imgui.pop_style_color()

    imgui.same_line()
    is_sel = editor_state.tool_mode == 'select'
    if is_sel: _push_blue()
    if imgui.button("Select [S]"):
        editor_state.tool_mode = 'select'
    if is_sel: imgui.pop_style_color()

    imgui.same_line()
    imgui.separator()
    imgui.same_line()

    _, ui_state.show_skeleton_lines = imgui.checkbox(
        "Skeleton", ui_state.show_skeleton_lines)
    renderer.show_skeleton = ui_state.show_skeleton_lines
    imgui.same_line()
    imgui.separator()
    imgui.same_line()

    if imgui.button("Undo"):
        editor_state.undo()
    imgui.same_line()
    if imgui.button("Redo"):
        editor_state.redo()

    # ── 视图控制 (最右侧) ──
    imgui.same_line()
    imgui.separator()
    imgui.same_line()
    if imgui.button("Center"):
        camera.reset_to_model(editor_state.voxels)
    imgui.same_line()

    # 正交 / 透视 toggle
    is_ortho = bool(camera.is_ortho)
    if is_ortho: _push_blue()
    if imgui.button("Ortho"):
        camera.is_ortho = not camera.is_ortho
        camera._dirty = True
    if is_ortho: imgui.pop_style_color()
    imgui.same_line()

    if imgui.button("Front"):
        camera.set_view_preset('front')
    imgui.same_line()
    if imgui.button("Side"):
        camera.set_view_preset('side')
    imgui.same_line()
    if imgui.button("Top"):
        camera.set_view_preset('top')
    imgui.same_line()
    if imgui.button("3/4"):
        camera.set_view_preset('perspective')

    imgui.end()


# ── stick panel ───────────────────────────────

def draw_bone_panel(ui_state, editor_state, WIN_W, WIN_H, renderer,
                    skeleton_sticks_ref):
    """
    注:函数名保留为 draw_bone_panel 以减少 main.py 侧改动,
    但面板内容展示的是 sticks。
    skeleton_sticks_ref 参数保留用于 dialog 间共享(preset dialog 会用),
    但本函数内部已不直接依赖它。
    """
    PANEL_W  = 240
    TOOLBAR_H = 38
    STATUS_H  = 24

    imgui.set_next_window_position(WIN_W - PANEL_W, TOOLBAR_H)
    imgui.set_next_window_size(PANEL_W, WIN_H - TOOLBAR_H - STATUS_H)
    imgui.begin("##bones", flags=FIXED_FLAGS)

    # 同步选中高亮到 renderer(每帧一次,覆盖所有路径对 active_stick_idx 的改动)
    if editor_state.sticks:
        renderer.highlight_stick_idx = editor_state.active_stick_idx
    else:
        renderer.highlight_stick_idx = -1

    if imgui.button("Load Human Preset", width=-1):
        ui_state.show_preset_dialog = True

    imgui.separator()
    bound, total = editor_state.stats()
    imgui.text_colored(f"Voxels: {bound}/{total} bound", 0.7, 0.7, 0.7, 1.0)
    imgui.separator()
    imgui.text("Sticks  (click = activate)")

    sticks = editor_state.sticks
    # 建立 id -> particle 方便 tooltip 显示
    particles_by_id = {p['id']: p for p in editor_state.particles}

    to_unbind = -1
    for idx, stick in enumerate(sticks):
        imgui.push_id(str(idx))

        # color picker (small swatch)
        cr, cg, cb = stick.color
        changed, new_col = imgui.color_edit3(
            "##c", cr, cg, cb,
            flags=(imgui.COLOR_EDIT_NO_INPUTS | imgui.COLOR_EDIT_NO_LABEL |
                   imgui.COLOR_EDIT_NO_TOOLTIP))
        if changed:
            stick.color = tuple(new_col)
            editor_state.gpu_dirty = True
        imgui.same_line()

        # visibility toggle
        vis = "o" if stick.visible else "-"
        if imgui.button(vis + "##v"):
            stick.visible = not stick.visible
            editor_state.gpu_dirty = True
        imgui.same_line()

        # name button (activate + select)
        is_active = (editor_state.active_stick_idx == idx)
        if is_active: _push_green()
        label = f"[{idx}]{stick.name}"
        if len(label) > 16:
            label = label[:15] + "~"
        if imgui.button(label + "##b", width=118):
            editor_state.active_stick_idx = idx
            editor_state.select_stick_voxels(idx)
        if imgui.is_item_hovered():
            pa = particles_by_id.get(stick.particle_a_id, {})
            pb = particles_by_id.get(stick.particle_b_id, {})
            na = pa.get('name', f'?{stick.particle_a_id}')
            nb = pb.get('name', f'?{stick.particle_b_id}')
            n_bound = sum(1 for c in editor_state.bindings.values() if c == idx)
            imgui.set_tooltip(
                f"ci={idx}\n"
                f"{na} (id={stick.particle_a_id})\n"
                f"   ↕\n"
                f"{nb} (id={stick.particle_b_id})\n"
                f"bound voxels: {n_bound}")
        if is_active: imgui.pop_style_color()
        imgui.same_line()

        # 解绑按钮("-"):清空该 stick 的所有体素绑定,stick 本身保留
        _push_red()
        if imgui.button("-##u"):
            to_unbind = idx
        imgui.pop_style_color()
        if imgui.is_item_hovered():
            imgui.set_tooltip("Unbind all voxels from this stick\n"
                              "(stick itself is preserved)")

        imgui.pop_id()

    if to_unbind >= 0:
        editor_state.unbind_stick_voxels(to_unbind)

    imgui.separator()

    # selection actions
    if editor_state.tool_mode == 'select' and editor_state.selected_voxels:
        n_sel = len(editor_state.selected_voxels)
        imgui.text(f"Selected: {n_sel}")
        if imgui.button("Bind to active stick", width=-1):
            editor_state.bind_selection(editor_state.active_stick_idx)
        if imgui.button("Unbind", width=-1):
            editor_state.unbind_selection()
        if imgui.button("Clear selection", width=-1):
            editor_state.clear_selection()
    elif editor_state.tool_mode == 'brush' and sticks:
        active = sticks[editor_state.active_stick_idx]
        imgui.text_colored("Brush active:", 0.4, 0.9, 0.4, 1.0)
        imgui.text(f"  {active.name}")

    imgui.separator()
    if imgui.button("Select unbound", width=-1):
        editor_state.tool_mode = 'select'
        editor_state.select_unbound()

    imgui.separator()
    if imgui.collapsing_header("Advanced"):
        imgui.text("trans_bias (reload to apply):")
        imgui.set_next_item_width(80)
        changed, ui_state.trans_bias = imgui.input_int(
            "##tbias", ui_state.trans_bias)

    imgui.end()


# ── status bar ────────────────────────────────

def draw_status_bar(editor_state, WIN_W, WIN_H):
    imgui.set_next_window_position(0, WIN_H - 24)
    imgui.set_next_window_size(WIN_W, 24)
    imgui.begin("##status",
                flags=FIXED_FLAGS | imgui.WINDOW_NO_SCROLLBAR)
    src    = editor_state.source_path or "(no file)"
    b, t   = editor_state.stats()
    ns     = len(editor_state.sticks)
    mode   = "Brush" if editor_state.tool_mode == 'brush' else "Select"
    dirty  = " [unsaved]" if editor_state.is_dirty else ""
    imgui.text(f"  {src}  |  {t} voxels  |  {ns} sticks  |"
               f"  bound {b}  |  {mode}{dirty}")
    imgui.end()


# ── dialogs ───────────────────────────────────

def draw_load_dialog(ui_state, editor_state, renderer,
                     skeleton_sticks_ref, WIN_W, WIN_H):
    if not ui_state.show_load_dialog:
        return
    imgui.open_popup("Open file")
    imgui.set_next_window_position(WIN_W // 2 - 270, WIN_H // 2 - 60)
    imgui.set_next_window_size(540, 120)
    opened, _ = imgui.begin_popup_modal(
        "Open file", flags=imgui.WINDOW_NO_RESIZE)
    if opened:
        fmt = "VOX" if ui_state.load_mode == 'vox' else "XML"
        imgui.text(f"Enter {fmt} file path (or drag-drop onto window):")
        imgui.set_next_item_width(-1)
        _, ui_state.load_path_buf = imgui.input_text(
            "##lp", ui_state.load_path_buf, 1024)

        if imgui.button("OK", width=80):
            path = ui_state.load_path_buf.strip().strip('"')
            if os.path.isfile(path):
                try:
                    if ui_state.load_mode == 'vox':
                        editor_state.load_vox(path, ui_state.trans_bias)
                    else:
                        sk = editor_state.load_xml(path, ui_state.trans_bias)
                        skeleton_sticks_ref[0] = sk.get('sticks', [])
                        renderer.upload_skeleton_lines(
                            editor_state.particles, editor_state.sticks)
                    editor_state.gpu_dirty = True
                    ui_state._load_error = ""
                except Exception as e:
                    ui_state._load_error = str(e)
            else:
                ui_state._load_error = "File not found"
            if not ui_state._load_error:
                ui_state.show_load_dialog = False
                imgui.close_current_popup()

        imgui.same_line()
        if imgui.button("Cancel", width=80):
            ui_state.show_load_dialog = False
            imgui.close_current_popup()

        if ui_state._load_error:
            imgui.text_colored(f"Error: {ui_state._load_error}",
                               1.0, 0.3, 0.3, 1.0)
        imgui.end_popup()
    else:
        ui_state.show_load_dialog = False


def draw_save_dialog(ui_state, editor_state, skeleton_sticks_ref,
                     WIN_W, WIN_H):
    if not ui_state.show_save_dialog:
        return
    imgui.open_popup("Save XML")
    imgui.set_next_window_position(WIN_W // 2 - 270, WIN_H // 2 - 60)
    imgui.set_next_window_size(540, 120)
    opened, _ = imgui.begin_popup_modal(
        "Save XML", flags=imgui.WINDOW_NO_RESIZE)
    if opened:
        imgui.text("Output XML path:")
        imgui.set_next_item_width(-1)
        _, ui_state.save_path_buf = imgui.input_text(
            "##sp", ui_state.save_path_buf, 1024)

        if imgui.button("Save", width=80):
            path = ui_state.save_path_buf.strip().strip('"')
            if path:
                try:
                    # save_xml 现在优先用 self.sticks 反序列化,
                    # skeleton_sticks_ref[0] 仅作兜底
                    editor_state.save_xml(path, skeleton_sticks_ref[0])
                    ui_state._save_error = ""
                    ui_state.show_save_dialog = False
                    imgui.close_current_popup()
                except Exception as e:
                    ui_state._save_error = str(e)
        imgui.same_line()
        if imgui.button("Cancel", width=80):
            ui_state.show_save_dialog = False
            imgui.close_current_popup()
        if ui_state._save_error:
            imgui.text_colored(f"Error: {ui_state._save_error}",
                               1.0, 0.3, 0.3, 1.0)
        imgui.end_popup()
    else:
        ui_state.show_save_dialog = False


def draw_preset_dialog(ui_state, editor_state, renderer,
                       skeleton_sticks_ref, WIN_W, WIN_H):
    if not ui_state.show_preset_dialog:
        return
    imgui.open_popup("Load Preset")
    imgui.set_next_window_position(WIN_W // 2 - 170, WIN_H // 2 - 55)
    imgui.set_next_window_size(340, 110)
    opened, _ = imgui.begin_popup_modal(
        "Load Preset", flags=imgui.WINDOW_NO_RESIZE)
    if opened:
        imgui.text("Load standard human skeleton (15 particles, 17 sticks).")
        imgui.text("Existing bindings are kept.")
        imgui.spacing()
        if imgui.button("Confirm", width=100):
            data = editor_state.load_skeleton_preset()
            skeleton_sticks_ref[0] = data.get('sticks', [])
            renderer.upload_skeleton_lines(
                editor_state.particles, editor_state.sticks)
            editor_state.gpu_dirty = True
            ui_state.show_preset_dialog = False
            imgui.close_current_popup()
        imgui.same_line()
        if imgui.button("Cancel", width=80):
            ui_state.show_preset_dialog = False
            imgui.close_current_popup()
        imgui.end_popup()
    else:
        ui_state.show_preset_dialog = False


def draw_box_select_overlay(ui_state):
    if not ui_state.box_selecting:
        return
    dl = imgui.get_window_draw_list()
    x0, y0 = ui_state.box_x0, ui_state.box_y0
    x1, y1 = ui_state.box_x1, ui_state.box_y1
    dl.add_rect(x0, y0, x1, y1, imgui.get_color_u32_rgba(0.4, 0.7, 1.0, 0.9),
                thickness=1.5)
    dl.add_rect_filled(x0, y0, x1, y1,
                       imgui.get_color_u32_rgba(0.4, 0.7, 1.0, 0.12))
