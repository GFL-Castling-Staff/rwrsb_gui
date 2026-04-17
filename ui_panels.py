"""
ui_panels.py
"""
import os

import imgui


class UIState:
    def __init__(self):
        self.show_load_dialog = False
        self.show_save_dialog = False
        self.show_preset_dialog = False
        self.load_path_buf = ""
        self.save_path_buf = ""
        self.load_mode = "vox"

        self.trans_bias = 127
        self.show_skeleton_lines = True

        self.box_selecting = False
        self.box_x0 = self.box_y0 = 0
        self.box_x1 = self.box_y1 = 0

        self.new_stick_a = 0
        self.new_stick_b = 0
        self.preset_selected = 0
        self.preset_name_buf = ""

        self._load_error = ""
        self._save_error = ""
        self._bone_error = ""


FIXED_FLAGS = (
    imgui.WINDOW_NO_TITLE_BAR
    | imgui.WINDOW_NO_RESIZE
    | imgui.WINDOW_NO_MOVE
    | imgui.WINDOW_NO_SAVED_SETTINGS
)


def _push_green():
    imgui.push_style_color(imgui.COLOR_BUTTON, 0.2, 0.6, 0.2, 1.0)


def _push_blue():
    imgui.push_style_color(imgui.COLOR_BUTTON, 0.2, 0.4, 0.7, 1.0)


def _push_red():
    imgui.push_style_color(imgui.COLOR_BUTTON, 0.6, 0.15, 0.15, 1.0)


def _clamp_index(value, count):
    if count <= 0:
        return 0
    return min(max(int(value), 0), count - 1)


def draw_toolbar(ui_state, editor_state, renderer, camera, WIN_W):
    imgui.set_next_window_position(0, 0)
    imgui.set_next_window_size(WIN_W, 38)
    imgui.begin("##toolbar", flags=FIXED_FLAGS | imgui.WINDOW_NO_SCROLLBAR)

    if imgui.button("Open VOX"):
        ui_state.show_load_dialog = True
        ui_state.load_path_buf = ""
        ui_state.load_mode = "vox"
        ui_state._load_error = ""
    imgui.same_line()
    if imgui.button("Open XML"):
        ui_state.show_load_dialog = True
        ui_state.load_path_buf = ""
        ui_state.load_mode = "xml"
        ui_state._load_error = ""
    imgui.same_line()

    dirty = "*" if editor_state.is_dirty else ""
    if imgui.button(f"Save XML{dirty}"):
        ui_state.show_save_dialog = True
        path = editor_state.source_path or ""
        if path.lower().endswith(".vox"):
            path = path[:-4] + "_bound.xml"
        ui_state.save_path_buf = path
        ui_state._save_error = ""
    imgui.same_line()
    imgui.separator()
    imgui.same_line()

    is_brush = editor_state.tool_mode == "brush"
    if is_brush:
        _push_green()
    if imgui.button("Brush [B]"):
        editor_state.tool_mode = "brush"
    if is_brush:
        imgui.pop_style_color()

    imgui.same_line()
    is_sel = editor_state.tool_mode == "select"
    if is_sel:
        _push_blue()
    if imgui.button("Select [S]"):
        editor_state.tool_mode = "select"
    if is_sel:
        imgui.pop_style_color()

    imgui.same_line()
    imgui.separator()
    imgui.same_line()

    _, ui_state.show_skeleton_lines = imgui.checkbox("Skeleton", ui_state.show_skeleton_lines)
    renderer.show_skeleton = ui_state.show_skeleton_lines
    imgui.same_line()
    imgui.separator()
    imgui.same_line()

    if imgui.button("Undo"):
        editor_state.undo()
    imgui.same_line()
    if imgui.button("Redo"):
        editor_state.redo()

    imgui.same_line()
    imgui.separator()
    imgui.same_line()
    if imgui.button("Center"):
        camera.reset_to_model(editor_state.voxels)
    imgui.same_line()

    is_ortho = bool(camera.is_ortho)
    if is_ortho:
        _push_blue()
    if imgui.button("Ortho"):
        camera.is_ortho = not camera.is_ortho
        camera._dirty = True
    if is_ortho:
        imgui.pop_style_color()
    imgui.same_line()

    if imgui.button("Front"):
        camera.set_view_preset("front")
    imgui.same_line()
    if imgui.button("Side"):
        camera.set_view_preset("side")
    imgui.same_line()
    if imgui.button("Top"):
        camera.set_view_preset("top")
    imgui.same_line()
    if imgui.button("3/4"):
        camera.set_view_preset("perspective")

    imgui.end()


def _draw_stick_list(ui_state, editor_state):
    sticks = editor_state.sticks
    particles_by_id = {p["id"]: p for p in editor_state.particles}
    to_unbind = -1

    for idx, stick in enumerate(sticks):
        imgui.push_id(f"stick-{idx}")

        cr, cg, cb = stick.color
        changed, new_col = imgui.color_edit3(
            "##c",
            cr,
            cg,
            cb,
            flags=(imgui.COLOR_EDIT_NO_INPUTS | imgui.COLOR_EDIT_NO_LABEL | imgui.COLOR_EDIT_NO_TOOLTIP),
        )
        if changed:
            stick.color = tuple(new_col)
            editor_state.gpu_dirty = True
        imgui.same_line()

        vis = "o" if stick.visible else "-"
        if imgui.button(vis + "##v"):
            stick.visible = not stick.visible
            editor_state.gpu_dirty = True
        imgui.same_line()

        is_active = editor_state.active_stick_idx == idx
        if is_active:
            _push_green()
        label = f"[{idx}] {stick.name}"
        if len(label) > 18:
            label = label[:17] + "~"
        if imgui.button(label + "##b", width=118):
            editor_state.active_stick_idx = idx
            editor_state.select_stick_voxels(idx)
        if is_active:
            imgui.pop_style_color()

        if imgui.is_item_hovered():
            pa = particles_by_id.get(stick.particle_a_id, {})
            pb = particles_by_id.get(stick.particle_b_id, {})
            n_bound = sum(1 for c in editor_state.bindings.values() if c == idx)
            imgui.set_tooltip(
                f"ci={idx}\n"
                f"{pa.get('name', '?')} ({stick.particle_a_id})\n"
                f"-> {pb.get('name', '?')} ({stick.particle_b_id})\n"
                f"bound voxels: {n_bound}"
            )
        imgui.same_line()

        _push_red()
        if imgui.button("-##u"):
            to_unbind = idx
        imgui.pop_style_color()
        if imgui.is_item_hovered():
            imgui.set_tooltip("Unbind all voxels from this stick")

        imgui.pop_id()

    if to_unbind >= 0:
        editor_state.unbind_stick_voxels(to_unbind)


def _draw_particle_editor(ui_state, editor_state):
    if not imgui.collapsing_header("Particles", flags=imgui.TREE_NODE_DEFAULT_OPEN)[0]:
        return

    if imgui.button("Add Particle", width=-1):
        try:
            editor_state.add_particle()
            ui_state._bone_error = ""
        except Exception as exc:
            ui_state._bone_error = str(exc)

    for idx, particle in enumerate(editor_state.particles):
        imgui.push_id(f"particle-{idx}")
        if imgui.tree_node(f"{particle['name']} ({particle['id']})##node"):
            changed_name, new_name = imgui.input_text("Name", particle["name"], 128)
            changed_id, new_id = imgui.input_int("Id", int(particle["id"]))
            changed_mass, new_mass = imgui.input_float("InvMass", float(particle["invMass"]), 0.0, 0.0, "%.3f")
            changed_hint, new_hint = imgui.input_int("BodyHint", int(particle["bodyAreaHint"]))
            changed_x, new_x = imgui.input_float("X", float(particle["x"]), 0.0, 0.0, "%.3f")
            changed_y, new_y = imgui.input_float("Y", float(particle["y"]), 0.0, 0.0, "%.3f")
            changed_z, new_z = imgui.input_float("Z", float(particle["z"]), 0.0, 0.0, "%.3f")

            if changed_name or changed_id or changed_mass or changed_hint or changed_x or changed_y or changed_z:
                try:
                    editor_state.update_particle(
                        idx,
                        name=new_name,
                        id=new_id,
                        invMass=new_mass,
                        bodyAreaHint=max(0, new_hint),
                        x=new_x,
                        y=new_y,
                        z=new_z,
                    )
                    ui_state._bone_error = ""
                except Exception as exc:
                    ui_state._bone_error = str(exc)

            _push_red()
            if imgui.button("Delete Particle", width=-1):
                editor_state.delete_particle(idx)
                ui_state._bone_error = ""
                imgui.tree_pop()
                imgui.pop_id()
                return
            imgui.pop_style_color()
            imgui.tree_pop()
        imgui.pop_id()


def _draw_active_stick_editor(ui_state, editor_state):
    if not imgui.collapsing_header("Active Stick", flags=imgui.TREE_NODE_DEFAULT_OPEN)[0]:
        return

    if not editor_state.sticks:
        imgui.text_disabled("No stick yet")
        return

    options = editor_state.get_particle_options()
    ui_state.new_stick_a = _clamp_index(ui_state.new_stick_a, len(options))
    ui_state.new_stick_b = _clamp_index(ui_state.new_stick_b, len(options))

    stick = editor_state.sticks[editor_state.active_stick_idx]
    particles_by_id = {p["id"]: i for i, p in enumerate(editor_state.particles)}
    a_idx = particles_by_id.get(stick.particle_a_id, 0)
    b_idx = particles_by_id.get(stick.particle_b_id, 0)

    changed_name, new_name = imgui.input_text("Stick Name", stick.name, 128)
    changed_a, a_idx = imgui.combo("Particle A", a_idx, options)
    changed_b, b_idx = imgui.combo("Particle B", b_idx, options)

    if changed_name or changed_a or changed_b:
        try:
            editor_state.update_stick(
                editor_state.active_stick_idx,
                particle_a_id=editor_state.particles[a_idx]["id"],
                particle_b_id=editor_state.particles[b_idx]["id"],
                name=new_name,
            )
            ui_state._bone_error = ""
        except Exception as exc:
            ui_state._bone_error = str(exc)

    if imgui.button("Auto Rename", width=-1):
        editor_state.rename_sticks_from_particles()

    _push_red()
    if imgui.button("Delete Active Stick", width=-1):
        editor_state.delete_stick(editor_state.active_stick_idx)
    imgui.pop_style_color()


def _draw_add_stick(ui_state, editor_state):
    if not imgui.collapsing_header("Create Stick", flags=imgui.TREE_NODE_DEFAULT_OPEN)[0]:
        return

    if len(editor_state.particles) < 2:
        imgui.text_disabled("Need at least 2 particles")
        return

    options = editor_state.get_particle_options()
    ui_state.new_stick_a = _clamp_index(ui_state.new_stick_a, len(options))
    ui_state.new_stick_b = _clamp_index(ui_state.new_stick_b, len(options))

    changed_a, ui_state.new_stick_a = imgui.combo("New A", ui_state.new_stick_a, options)
    changed_b, ui_state.new_stick_b = imgui.combo("New B", ui_state.new_stick_b, options)
    if imgui.button("Add Stick", width=-1):
        try:
            editor_state.add_stick(
                editor_state.particles[ui_state.new_stick_a]["id"],
                editor_state.particles[ui_state.new_stick_b]["id"],
            )
            ui_state._bone_error = ""
        except Exception as exc:
            ui_state._bone_error = str(exc)


def draw_bone_panel(ui_state, editor_state, WIN_W, WIN_H, renderer, skeleton_sticks_ref):
    PANEL_W = 280
    TOOLBAR_H = 38
    STATUS_H = 24

    imgui.set_next_window_position(WIN_W - PANEL_W, TOOLBAR_H)
    imgui.set_next_window_size(PANEL_W, WIN_H - TOOLBAR_H - STATUS_H)
    imgui.begin("##bones", flags=FIXED_FLAGS)

    renderer.highlight_stick_idx = editor_state.active_stick_idx if editor_state.sticks else -1

    if imgui.button("Presets", width=-1):
        ui_state.show_preset_dialog = True

    imgui.separator()
    bound, total = editor_state.stats()
    imgui.text_colored(f"Voxels: {bound}/{total} bound", 0.7, 0.7, 0.7, 1.0)
    imgui.text(f"Particles: {len(editor_state.particles)}")
    imgui.text(f"Sticks: {len(editor_state.sticks)}")
    imgui.separator()
    imgui.text("Stick List")
    _draw_stick_list(ui_state, editor_state)

    imgui.separator()
    if editor_state.tool_mode == "select" and editor_state.selected_voxels:
        imgui.text(f"Selected: {len(editor_state.selected_voxels)}")
        if imgui.button("Bind to active stick", width=-1):
            editor_state.bind_selection(editor_state.active_stick_idx)
        if imgui.button("Unbind", width=-1):
            editor_state.unbind_selection()
        if imgui.button("Clear selection", width=-1):
            editor_state.clear_selection()
    elif editor_state.tool_mode == "brush" and editor_state.sticks:
        active = editor_state.sticks[editor_state.active_stick_idx]
        imgui.text_colored("Brush active:", 0.4, 0.9, 0.4, 1.0)
        imgui.text(active.name)

    if imgui.button("Select unbound", width=-1):
        editor_state.tool_mode = "select"
        editor_state.select_unbound()

    imgui.separator()
    _draw_active_stick_editor(ui_state, editor_state)
    _draw_add_stick(ui_state, editor_state)
    _draw_particle_editor(ui_state, editor_state)

    imgui.separator()
    if imgui.collapsing_header("Advanced")[0]:
        imgui.text("trans_bias (reload to apply):")
        imgui.set_next_item_width(80)
        _, ui_state.trans_bias = imgui.input_int("##tbias", ui_state.trans_bias)

    if ui_state._bone_error:
        imgui.separator()
        imgui.text_colored(ui_state._bone_error, 1.0, 0.3, 0.3, 1.0)

    imgui.end()


def draw_status_bar(editor_state, WIN_W, WIN_H):
    imgui.set_next_window_position(0, WIN_H - 24)
    imgui.set_next_window_size(WIN_W, 24)
    imgui.begin("##status", flags=FIXED_FLAGS | imgui.WINDOW_NO_SCROLLBAR)
    src = editor_state.source_path or "(no file)"
    bound, total = editor_state.stats()
    ns = len(editor_state.sticks)
    mode = "Brush" if editor_state.tool_mode == "brush" else "Select"
    dirty = " [unsaved]" if editor_state.is_dirty else ""
    imgui.text(f"  {src}  |  {total} voxels  |  {ns} sticks  |  bound {bound}  |  {mode}{dirty}")
    imgui.end()


def draw_load_dialog(ui_state, editor_state, renderer, skeleton_sticks_ref, WIN_W, WIN_H):
    if not ui_state.show_load_dialog:
        return
    imgui.open_popup("Open file")
    imgui.set_next_window_position(WIN_W // 2 - 270, WIN_H // 2 - 60)
    imgui.set_next_window_size(540, 120)
    opened, _ = imgui.begin_popup_modal("Open file", flags=imgui.WINDOW_NO_RESIZE)
    if opened:
        fmt = "VOX" if ui_state.load_mode == "vox" else "XML"
        imgui.text(f"Enter {fmt} file path (or drag-drop onto window):")
        imgui.set_next_item_width(-1)
        _, ui_state.load_path_buf = imgui.input_text("##lp", ui_state.load_path_buf, 1024)

        if imgui.button("OK", width=80):
            path = ui_state.load_path_buf.strip().strip('"')
            if os.path.isfile(path):
                try:
                    if ui_state.load_mode == "vox":
                        editor_state.load_vox(path, ui_state.trans_bias)
                    else:
                        sk = editor_state.load_xml(path, ui_state.trans_bias)
                        skeleton_sticks_ref[0] = sk.get("sticks", [])
                        renderer.upload_skeleton_lines(editor_state.particles, editor_state.sticks)
                    editor_state.gpu_dirty = True
                    ui_state._load_error = ""
                except Exception as exc:
                    ui_state._load_error = str(exc)
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
            imgui.text_colored(f"Error: {ui_state._load_error}", 1.0, 0.3, 0.3, 1.0)
        imgui.end_popup()
    else:
        ui_state.show_load_dialog = False


def draw_save_dialog(ui_state, editor_state, skeleton_sticks_ref, WIN_W, WIN_H):
    if not ui_state.show_save_dialog:
        return
    imgui.open_popup("Save XML")
    imgui.set_next_window_position(WIN_W // 2 - 270, WIN_H // 2 - 60)
    imgui.set_next_window_size(540, 120)
    opened, _ = imgui.begin_popup_modal("Save XML", flags=imgui.WINDOW_NO_RESIZE)
    if opened:
        imgui.text("Output XML path:")
        imgui.set_next_item_width(-1)
        _, ui_state.save_path_buf = imgui.input_text("##sp", ui_state.save_path_buf, 1024)

        if imgui.button("Save", width=80):
            path = ui_state.save_path_buf.strip().strip('"')
            if path:
                try:
                    editor_state.save_xml(path, skeleton_sticks_ref[0])
                    ui_state._save_error = ""
                    ui_state.show_save_dialog = False
                    imgui.close_current_popup()
                except Exception as exc:
                    ui_state._save_error = str(exc)
        imgui.same_line()
        if imgui.button("Cancel", width=80):
            ui_state.show_save_dialog = False
            imgui.close_current_popup()
        if ui_state._save_error:
            imgui.text_colored(f"Error: {ui_state._save_error}", 1.0, 0.3, 0.3, 1.0)
        imgui.end_popup()
    else:
        ui_state.show_save_dialog = False


def draw_preset_dialog(ui_state, editor_state, renderer, skeleton_sticks_ref, WIN_W, WIN_H):
    if not ui_state.show_preset_dialog:
        return
    imgui.open_popup("Preset Manager")
    imgui.set_next_window_position(WIN_W // 2 - 240, WIN_H // 2 - 150)
    imgui.set_next_window_size(480, 300)
    opened, _ = imgui.begin_popup_modal("Preset Manager", flags=imgui.WINDOW_NO_RESIZE)
    if opened:
        presets = editor_state.list_skeleton_presets()
        preset_labels = [f"{p['name']} [{p['particles']}p/{p['sticks']}s]" for p in presets] or ["(no presets)"]
        ui_state.preset_selected = _clamp_index(ui_state.preset_selected, len(preset_labels))

        imgui.text("Load, save, and delete skeleton presets.")
        imgui.text("Loading keeps current voxel bindings.")
        imgui.separator()

        imgui.text("Available presets:")
        changed, ui_state.preset_selected = imgui.combo("##preset_combo", ui_state.preset_selected, preset_labels)
        if presets:
            selected = presets[ui_state.preset_selected]
            imgui.text(f"File: {selected['file']}")
        else:
            imgui.text_disabled("Preset folder is empty")

        if imgui.button("Load Selected", width=140):
            if presets:
                try:
                    data = editor_state.load_skeleton_preset(presets[ui_state.preset_selected]["path"])
                    skeleton_sticks_ref[0] = data.get("sticks", [])
                    renderer.upload_skeleton_lines(editor_state.particles, editor_state.sticks)
                    editor_state.gpu_dirty = True
                    ui_state._bone_error = ""
                except Exception as exc:
                    ui_state._bone_error = str(exc)
        imgui.same_line()
        if imgui.button("Delete Selected", width=140):
            if presets:
                try:
                    editor_state.delete_skeleton_preset(presets[ui_state.preset_selected]["path"])
                    ui_state.preset_selected = max(0, ui_state.preset_selected - 1)
                    ui_state._bone_error = ""
                except Exception as exc:
                    ui_state._bone_error = str(exc)

        imgui.separator()
        imgui.text("Save current skeleton as preset:")
        imgui.set_next_item_width(-1)
        _, ui_state.preset_name_buf = imgui.input_text("##preset_name", ui_state.preset_name_buf, 128)

        if imgui.button("Save New Preset", width=140):
            try:
                editor_state.save_skeleton_preset(ui_state.preset_name_buf or "Custom Skeleton", overwrite=False)
                ui_state._bone_error = ""
            except Exception as exc:
                ui_state._bone_error = str(exc)
        imgui.same_line()
        if imgui.button("Overwrite Selected", width=140):
            if presets:
                try:
                    selected = presets[ui_state.preset_selected]
                    editor_state.save_skeleton_preset(
                        ui_state.preset_name_buf or selected["name"],
                        file_name=selected["file"],
                        overwrite=True,
                    )
                    ui_state._bone_error = ""
                except Exception as exc:
                    ui_state._bone_error = str(exc)

        if ui_state._bone_error:
            imgui.separator()
            imgui.text_colored(ui_state._bone_error, 1.0, 0.3, 0.3, 1.0)

        imgui.separator()
        if imgui.button("Close", width=100):
            ui_state.show_preset_dialog = False
            imgui.close_current_popup()
        imgui.end_popup()
    else:
        ui_state.show_preset_dialog = False


def draw_box_select_overlay(ui_state):
    if not ui_state.box_selecting:
        return
    draw_list = imgui.get_window_draw_list()
    x0, y0 = ui_state.box_x0, ui_state.box_y0
    x1, y1 = ui_state.box_x1, ui_state.box_y1
    draw_list.add_rect(
        x0,
        y0,
        x1,
        y1,
        imgui.get_color_u32_rgba(0.4, 0.7, 1.0, 0.9),
        thickness=1.5,
    )
    draw_list.add_rect_filled(
        x0,
        y0,
        x1,
        y1,
        imgui.get_color_u32_rgba(0.4, 0.7, 1.0, 0.12),
    )
