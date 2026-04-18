"""
ui_panels.py
"""
import os

import imgui


_TEXT = {
    "en": {
        "open_vox": "Open VOX",
        "open_xml": "Open XML",
        "save_xml": "Save XML",
        "brush": "Brush [B]",
        "voxel_select": "Voxels [V]",
        "bone_edit": "Bones [E]",
        "skeleton": "Skeleton",
        "undo": "Undo",
        "redo": "Redo",
        "center": "Center",
        "ortho": "Ortho",
        "front": "Front",
        "side": "Side",
        "top": "Top",
        "perspective": "3/4",
        "presets": "Presets",
        "voxels_bound": "Voxels: {bound}/{total} bound",
        "particles_count": "Particles: {count}",
        "sticks_count": "Sticks: {count}",
        "active_particle": "Active particle: {name} ({pid})",
        "active_particle_none": "Active particle: none",
        "stick_list": "Stick List",
        "selected": "Selected: {count}",
        "bind_to_active": "Bind to active stick",
        "unbind": "Unbind",
        "clear_selection": "Clear selection",
        "brush_active": "Brush active:",
        "select_unbound": "Select unbound",
        "active_stick": "Active Stick",
        "stick_edit_disabled": "Stick editing is disabled",
        "no_stick_yet": "No stick yet",
        "stick_name": "Stick Name",
        "particle_a": "Particle A",
        "particle_b": "Particle B",
        "auto_rename": "Auto Rename",
        "delete_active_stick": "Delete Active Stick",
        "create_stick": "Create Stick",
        "need_two_particles": "Need at least 2 particles",
        "new_a": "New A",
        "new_b": "New B",
        "add_stick": "Add Stick",
        "particles": "Particles",
        "particle_edit_disabled": "Particle editing is disabled",
        "add_particle": "Add Particle",
        "name": "Name",
        "id": "Id",
        "inv_mass": "InvMass",
        "body_hint": "BodyHint",
        "x": "X",
        "y": "Y",
        "z": "Z",
        "delete_particle": "Delete Particle",
        "advanced": "Advanced",
        "allow_skeleton_edit": "Allow skeleton edit",
        "allow_stick_edit": "Allow stick edit",
        "allow_particle_edit": "Allow particle edit",
        "disabled_by_master_stick": "Allow stick edit: disabled by master switch",
        "disabled_by_master_particle": "Allow particle edit: disabled by master switch",
        "show_grid": "Show grid",
        "grid_xz": "Grid XZ",
        "grid_xy": "Grid XY",
        "grid_yz": "Grid YZ",
        "snap_grid": "Snap particle to grid",
        "grid_unit": "Grid unit",
        "grid_half": "0.5 voxel",
        "grid_one": "1 voxel",
        "grid_n": "N voxels",
        "grid_n_label": "Grid N",
        "current_step": "Current step: {step:.3f}",
        "trans_bias": "trans_bias (reload to apply):",
        "language": "Language",
        "language_en": "English",
        "language_zh": "Chinese",
        "ui_scale": "UI scale",
        "invert_y": "Invert Y axis",
        "tip_drag": "Tip: drag orange particle points in the viewport.",
        "tip_axis": "Shift=X  Ctrl=Y  Alt=Z",
        "status": "  {src}  |  {total} voxels  |  {sticks} sticks  |  bound {bound}  |  {mode}{dirty}",
        "mode_brush": "Brush",
        "mode_voxel_select": "Voxels",
        "mode_bone_edit": "Bones",
        "unsaved": " [unsaved]",
        "open_file": "Open file",
        "enter_file_path": "Enter {fmt} file path (or drag-drop onto window):",
        "ok": "OK",
        "cancel": "Cancel",
        "error": "Error: {message}",
        "file_not_found": "File not found",
        "save_xml_title": "Save XML",
        "output_xml_path": "Output XML path:",
        "save": "Save",
        "save_and_exit": "Save and Exit",
        "discard_and_exit": "Discard and Exit",
        "cancel_exit": "Cancel",
        "unsaved_changes_title": "Unsaved Changes",
        "unsaved_changes_body": "You have unsaved changes. Save before exit?",
        "preset_manager": "Preset Manager",
        "preset_desc": "Load, save, and delete skeleton presets.",
        "preset_desc_keep": "Loading keeps current voxel bindings.",
        "available_presets": "Available presets:",
        "preset_file": "File: {file}",
        "preset_folder_empty": "Preset folder is empty",
        "load_selected": "Load Selected",
        "delete_selected": "Delete Selected",
        "save_preset_as": "Save current skeleton as preset:",
        "save_new_preset": "Save New Preset",
        "overwrite_selected": "Overwrite Selected",
        "close": "Close",
        "preset_none": "(no presets)",
        "tooltip_bound_voxels": "bound voxels: {count}",
        "tooltip_unbind_stick": "Unbind all voxels from this stick",
        "selected_particles_count": "Selected particles: {count}",
        "multi_edit": "Multi-select",
        "align_x": "Align X",
        "align_y": "Align Y",
        "align_z": "Align Z",
        "align_hint": "Need 2+ selected particles and an active particle inside the selection",
        "mirror_axis": "Mirror axis",
        "mirror_mode_enter": "Enter Mirror Mode",
        "mirror_mode_exit": "Exit Mirror Mode",
        "mirror_requires_two": "Mirror mode requires exactly 2 selected particles",
        "mirror_locked": "Mirror mode locks the active pair for editing",
        "mirror_active": "Mirror mode: {axis}-axis",
        "mirror_plane_origin": "Plane origin",
        "mirror_plane_normal": "Plane normal",
        "mirror_normal_x": "Normal X",
        "mirror_normal_y": "Normal Y",
        "mirror_normal_z": "Normal Z",
        "mirror_from_camera": "From Camera",
        "mirror_use_midpoint": "Use Pair Midpoint",
        "mirror_normalize": "Normalize Normal",
        "mirror_edit_plane": "Edit Mirror Plane",
        "mirror_finish_edit": "Done Editing Plane",
        "mirror_show_grid": "Show Mirror Grid",
        "mirror_snap_grid": "Snap To Mirror Grid",
        "mirror_grid_unit": "Mirror Grid Unit",
        "mirror_grid_n_label": "Mirror Grid N",
        "mirror_current_step": "Mirror step: {step:.3f}",
    },
    "zh": {
        "open_vox": "打开 VOX",
        "open_xml": "打开 XML",
        "save_xml": "保存 XML",
        "brush": "涂刷 [B]",
        "voxel_select": "选体素 [V]",
        "bone_edit": "选骨点 [E]",
        "skeleton": "骨架",
        "undo": "撤销",
        "redo": "重做",
        "center": "居中",
        "ortho": "正交",
        "front": "前视",
        "side": "侧视",
        "top": "顶视",
        "perspective": "3/4",
        "presets": "预设",
        "voxels_bound": "体素: {bound}/{total} 已绑定",
        "particles_count": "粒子: {count}",
        "sticks_count": "骨段: {count}",
        "active_particle": "当前粒子: {name} ({pid})",
        "active_particle_none": "当前粒子: 无",
        "stick_list": "骨段列表",
        "selected": "已选择: {count}",
        "bind_to_active": "绑定到当前骨段",
        "unbind": "解绑",
        "clear_selection": "清空选择",
        "brush_active": "当前涂刷:",
        "select_unbound": "选择未绑定",
        "active_stick": "当前骨段",
        "stick_edit_disabled": "骨段编辑已禁用",
        "no_stick_yet": "还没有骨段",
        "stick_name": "骨段名称",
        "particle_a": "粒子 A",
        "particle_b": "粒子 B",
        "auto_rename": "自动命名",
        "delete_active_stick": "删除当前骨段",
        "create_stick": "创建骨段",
        "need_two_particles": "至少需要 2 个粒子",
        "new_a": "新 A",
        "new_b": "新 B",
        "add_stick": "添加骨段",
        "particles": "粒子",
        "particle_edit_disabled": "粒子编辑已禁用",
        "add_particle": "添加粒子",
        "name": "名称",
        "id": "ID",
        "inv_mass": "逆质量",
        "body_hint": "身体区域",
        "x": "X",
        "y": "Y",
        "z": "Z",
        "delete_particle": "删除粒子",
        "advanced": "高级",
        "allow_skeleton_edit": "允许骨架编辑",
        "allow_stick_edit": "允许骨段编辑",
        "allow_particle_edit": "允许粒子编辑",
        "disabled_by_master_stick": "允许骨段编辑: 被总开关禁用",
        "disabled_by_master_particle": "允许粒子编辑: 被总开关禁用",
        "show_grid": "显示网格",
        "grid_xz": "XZ 网格",
        "grid_xy": "XY 网格",
        "grid_yz": "YZ 网格",
        "snap_grid": "粒子吸附到网格",
        "grid_unit": "网格单位",
        "grid_half": "0.5 体素",
        "grid_one": "1 体素",
        "grid_n": "N 体素",
        "grid_n_label": "网格 N",
        "current_step": "当前步长: {step:.3f}",
        "trans_bias": "trans_bias（重新加载后生效）:",
        "language": "语言",
        "language_en": "英文",
        "language_zh": "中文",
        "ui_scale": "界面缩放",
        "invert_y": "反转 Y 轴",
        "tip_drag": "提示: 可在视口中拖动橙色粒子点。",
        "tip_axis": "Shift=X  Ctrl=Y  Alt=Z",
        "status": "  {src}  |  {total} 个体素  |  {sticks} 条骨段  |  已绑定 {bound}  |  {mode}{dirty}",
        "mode_brush": "涂刷",
        "mode_voxel_select": "选体素",
        "mode_bone_edit": "选骨点",
        "unsaved": " [未保存]",
        "open_file": "打开文件",
        "enter_file_path": "输入 {fmt} 文件路径（或拖拽到窗口）:",
        "ok": "确定",
        "cancel": "取消",
        "error": "错误: {message}",
        "file_not_found": "文件不存在",
        "save_xml_title": "保存 XML",
        "output_xml_path": "输出 XML 路径:",
        "save": "保存",
        "preset_manager": "预设管理",
        "preset_desc": "加载、保存和删除骨架预设。",
        "preset_desc_keep": "加载时会保留当前体素绑定。",
        "available_presets": "可用预设:",
        "preset_file": "文件: {file}",
        "preset_folder_empty": "预设目录为空",
        "load_selected": "加载所选",
        "delete_selected": "删除所选",
        "save_preset_as": "将当前骨架保存为预设:",
        "save_new_preset": "保存新预设",
        "overwrite_selected": "覆盖所选",
        "close": "关闭",
        "preset_none": "(没有预设)",
        "tooltip_bound_voxels": "已绑定体素: {count}",
        "tooltip_unbind_stick": "解绑该骨段上的所有体素",
        "selected_particles_count": "已选粒子: {count}",
        "multi_edit": "多选操作",
        "align_x": "对齐 X",
        "align_y": "对齐 Y",
        "align_z": "对齐 Z",
        "align_hint": "需要至少 2 个已选粒子，且当前粒子必须在选择集中",
        "mirror_axis": "镜像轴",
        "mirror_mode_enter": "进入镜像模式",
        "mirror_mode_exit": "退出镜像模式",
        "mirror_requires_two": "镜像模式需要恰好选中 2 个粒子",
        "mirror_locked": "镜像模式会锁定当前这一对粒子",
        "mirror_active": "镜像模式: {axis} 轴",
        "mirror_plane_origin": "镜像平面原点",
        "mirror_plane_normal": "镜像平面法线",
        "mirror_normal_x": "法线 X",
        "mirror_normal_y": "法线 Y",
        "mirror_normal_z": "法线 Z",
        "mirror_from_camera": "从当前相机设置",
        "mirror_use_midpoint": "使用当前配对中点",
        "mirror_normalize": "归一化法线",
        "mirror_edit_plane": "编辑镜像平面",
        "mirror_finish_edit": "完成平面编辑",
        "mirror_show_grid": "显示镜像网格",
        "mirror_snap_grid": "吸附到镜像网格",
        "mirror_grid_unit": "镜像网格单位",
        "mirror_grid_n_label": "镜像网格 N",
        "mirror_current_step": "镜像步长: {step:.3f}",
    },
}


class UIState:
    def __init__(self):
        self.show_load_dialog = False
        self.show_save_dialog = False
        self.show_preset_dialog = False
        self.show_exit_dialog = False
        self.load_path_buf = ""
        self.save_path_buf = ""
        self.load_mode = "vox"
        self.pending_exit_after_save = False

        self.trans_bias = 127
        self.show_skeleton_lines = True

        self.box_selecting = False
        self.box_x0 = self.box_y0 = 0
        self.box_x1 = self.box_y1 = 0

        self.new_stick_a = 0
        self.new_stick_b = 0
        self.preset_selected = 0
        self.preset_name_buf = ""
        self.allow_stick_edit = True
        self.allow_particle_edit = True
        self.allow_skeleton_edit = True
        self.show_grid = True
        self.show_grid_xz = True
        self.show_grid_xy = True
        self.show_grid_yz = True
        self.snap_particles_to_grid = False
        self.grid_mode = 0
        self.grid_multiple = 2
        self.show_mirror_grid = False
        self.snap_to_mirror_grid = False
        self.mirror_grid_mode = 0
        self.mirror_grid_multiple = 2
        self.language = "zh"
        self.ui_scale = 1.0
        self.invert_y_axis = False
        self._applied_scale = None
        self._language_dirty = True

        self._load_error = ""
        self._save_error = ""
        self._bone_error = ""


FIXED_FLAGS = (
    imgui.WINDOW_NO_TITLE_BAR
    | imgui.WINDOW_NO_RESIZE
    | imgui.WINDOW_NO_MOVE
    | imgui.WINDOW_NO_SAVED_SETTINGS
)


def tr(ui_state, key, **kwargs):
    lang = getattr(ui_state, "language", "en")
    table = _TEXT.get(lang, _TEXT["en"])
    text = table.get(key, _TEXT["en"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text


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


def _grid_step(ui_state):
    if ui_state.grid_mode == 0:
        return 0.5
    if ui_state.grid_mode == 1:
        return 1.0
    return float(max(1, int(ui_state.grid_multiple)))


def _mirror_grid_step(ui_state):
    if ui_state.mirror_grid_mode == 0:
        return 0.5
    if ui_state.mirror_grid_mode == 1:
        return 1.0
    return float(max(1, int(ui_state.mirror_grid_multiple)))


def draw_toolbar(ui_state, editor_state, renderer, camera, WIN_W):
    imgui.set_next_window_position(0, 0)
    imgui.set_next_window_size(WIN_W, 38 * ui_state.ui_scale)
    imgui.begin("##toolbar", flags=FIXED_FLAGS | imgui.WINDOW_NO_SCROLLBAR)

    if imgui.button(tr(ui_state, "open_vox") + "##open_vox"):
        ui_state.show_load_dialog = True
        ui_state.load_path_buf = ""
        ui_state.load_mode = "vox"
        ui_state._load_error = ""
    imgui.same_line()
    if imgui.button(tr(ui_state, "open_xml") + "##open_xml"):
        ui_state.show_load_dialog = True
        ui_state.load_path_buf = ""
        ui_state.load_mode = "xml"
        ui_state._load_error = ""
    imgui.same_line()

    dirty = "*" if editor_state.is_dirty else ""
    if imgui.button(f"{tr(ui_state, 'save_xml')}{dirty}##save_xml"):
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
    if imgui.button(tr(ui_state, "brush") + "##brush"):
        if ui_state.allow_skeleton_edit:
            editor_state.set_tool_mode("brush")
    if is_brush:
        imgui.pop_style_color()

    imgui.same_line()
    is_vsel = editor_state.tool_mode == "voxel_select"
    if is_vsel:
        _push_blue()
    if imgui.button(tr(ui_state, "voxel_select") + "##voxel_select"):
        if ui_state.allow_skeleton_edit:
            editor_state.set_tool_mode("voxel_select")
    if is_vsel:
        imgui.pop_style_color()

    imgui.same_line()
    is_bone = editor_state.tool_mode == "bone_edit"
    if is_bone:
        _push_blue()  # 可以换个颜色；本轮先复用
    if imgui.button(tr(ui_state, "bone_edit") + "##bone_edit"):
        if ui_state.allow_skeleton_edit:
            editor_state.set_tool_mode("bone_edit")
    if is_bone:
        imgui.pop_style_color()

    imgui.same_line()
    imgui.separator()
    imgui.same_line()

    _, ui_state.show_skeleton_lines = imgui.checkbox(tr(ui_state, "skeleton") + "##skeleton", ui_state.show_skeleton_lines)
    renderer.show_skeleton = ui_state.show_skeleton_lines
    imgui.same_line()
    imgui.separator()
    imgui.same_line()

    if imgui.button(tr(ui_state, "undo") + "##undo"):
        editor_state.undo()
    imgui.same_line()
    if imgui.button(tr(ui_state, "redo") + "##redo"):
        editor_state.redo()

    imgui.same_line()
    imgui.separator()
    imgui.same_line()
    if imgui.button(tr(ui_state, "center") + "##center"):
        camera.reset_to_model(editor_state.voxels)
    imgui.same_line()

    is_ortho = bool(camera.is_ortho)
    if is_ortho:
        _push_blue()
    if imgui.button(tr(ui_state, "ortho") + "##ortho"):
        camera.set_ortho_enabled(not camera.is_ortho)
    if is_ortho:
        imgui.pop_style_color()
    imgui.same_line()

    if imgui.button(tr(ui_state, "front") + "##front"):
        camera.set_view_preset("front")
    imgui.same_line()
    if imgui.button(tr(ui_state, "side") + "##side"):
        camera.set_view_preset("side")
    imgui.same_line()
    if imgui.button(tr(ui_state, "top") + "##top"):
        camera.set_view_preset("top")
    imgui.same_line()
    if imgui.button(tr(ui_state, "perspective") + "##persp"):
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
        if imgui.button(label + "##b", width=118 * ui_state.ui_scale):
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
                f"{tr(ui_state, 'tooltip_bound_voxels', count=n_bound)}"
            )
        imgui.same_line()

        _push_red()
        if imgui.button("-##u"):
            to_unbind = idx
        imgui.pop_style_color()
        if imgui.is_item_hovered():
            imgui.set_tooltip(tr(ui_state, "tooltip_unbind_stick"))

        imgui.pop_id()

    if to_unbind >= 0:
        editor_state.unbind_stick_voxels(to_unbind)


def _draw_particle_editor(ui_state, editor_state):
    if not imgui.collapsing_header(tr(ui_state, "particles"), flags=imgui.TREE_NODE_DEFAULT_OPEN)[0]:
        return

    if not ui_state.allow_particle_edit:
        imgui.text_disabled(tr(ui_state, "particle_edit_disabled"))
        return

    if imgui.button(tr(ui_state, "add_particle"), width=-1):
        try:
            editor_state.add_particle()
            ui_state._bone_error = ""
        except Exception as exc:
            ui_state._bone_error = str(exc)

    for idx, particle in enumerate(editor_state.particles):
        imgui.push_id(f"particle-{idx}")
        if imgui.tree_node(f"{particle['name']} ({particle['id']})##node"):
            editor_state.set_active_particle(idx)
            changed_name, new_name = imgui.input_text(tr(ui_state, "name"), particle["name"], 128)
            changed_id, new_id = imgui.input_int(tr(ui_state, "id"), int(particle["id"]))
            changed_mass, new_mass = imgui.input_float(tr(ui_state, "inv_mass"), float(particle["invMass"]), 0.0, 0.0, "%.3f")
            changed_hint, new_hint = imgui.input_int(tr(ui_state, "body_hint"), int(particle["bodyAreaHint"]))
            changed_x, new_x = imgui.input_float(tr(ui_state, "x"), float(particle["x"]), 0.0, 0.0, "%.3f")
            changed_y, new_y = imgui.input_float(tr(ui_state, "y"), float(particle["y"]), 0.0, 0.0, "%.3f")
            changed_z, new_z = imgui.input_float(tr(ui_state, "z"), float(particle["z"]), 0.0, 0.0, "%.3f")

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
            if imgui.button(tr(ui_state, "delete_particle"), width=-1):
                editor_state.delete_particle(idx)
                ui_state._bone_error = ""
                imgui.tree_pop()
                imgui.pop_id()
                return
            imgui.pop_style_color()
            imgui.tree_pop()
        imgui.pop_id()


def _draw_active_stick_editor(ui_state, editor_state):
    if not imgui.collapsing_header(tr(ui_state, "active_stick"), flags=imgui.TREE_NODE_DEFAULT_OPEN)[0]:
        return

    if not ui_state.allow_stick_edit:
        imgui.text_disabled(tr(ui_state, "stick_edit_disabled"))
        return

    if not editor_state.sticks:
        imgui.text_disabled(tr(ui_state, "no_stick_yet"))
        return

    options = editor_state.get_particle_options()
    ui_state.new_stick_a = _clamp_index(ui_state.new_stick_a, len(options))
    ui_state.new_stick_b = _clamp_index(ui_state.new_stick_b, len(options))

    stick = editor_state.sticks[editor_state.active_stick_idx]
    particles_by_id = {p["id"]: i for i, p in enumerate(editor_state.particles)}
    a_idx = particles_by_id.get(stick.particle_a_id, 0)
    b_idx = particles_by_id.get(stick.particle_b_id, 0)

    changed_name, new_name = imgui.input_text(tr(ui_state, "stick_name"), stick.name, 128)
    changed_a, a_idx = imgui.combo(tr(ui_state, "particle_a"), a_idx, options)
    changed_b, b_idx = imgui.combo(tr(ui_state, "particle_b"), b_idx, options)

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

    if imgui.button(tr(ui_state, "auto_rename"), width=-1):
        editor_state.rename_sticks_from_particles()

    _push_red()
    if imgui.button(tr(ui_state, "delete_active_stick"), width=-1):
        editor_state.delete_stick(editor_state.active_stick_idx)
    imgui.pop_style_color()


def _draw_add_stick(ui_state, editor_state):
    if not imgui.collapsing_header(tr(ui_state, "create_stick"), flags=imgui.TREE_NODE_DEFAULT_OPEN)[0]:
        return

    if not ui_state.allow_stick_edit:
        imgui.text_disabled(tr(ui_state, "stick_edit_disabled"))
        return

    if len(editor_state.particles) < 2:
        imgui.text_disabled(tr(ui_state, "need_two_particles"))
        return

    options = editor_state.get_particle_options()
    ui_state.new_stick_a = _clamp_index(ui_state.new_stick_a, len(options))
    ui_state.new_stick_b = _clamp_index(ui_state.new_stick_b, len(options))

    _, ui_state.new_stick_a = imgui.combo(tr(ui_state, "new_a"), ui_state.new_stick_a, options)
    _, ui_state.new_stick_b = imgui.combo(tr(ui_state, "new_b"), ui_state.new_stick_b, options)
    if imgui.button(tr(ui_state, "add_stick"), width=-1):
        try:
            editor_state.add_stick(
                editor_state.particles[ui_state.new_stick_a]["id"],
                editor_state.particles[ui_state.new_stick_b]["id"],
            )
            ui_state._bone_error = ""
        except Exception as exc:
            ui_state._bone_error = str(exc)


def draw_bone_panel(ui_state, editor_state, WIN_W, WIN_H, renderer, skeleton_sticks_ref, camera):
    panel_w = int(280 * ui_state.ui_scale)
    toolbar_h = int(38 * ui_state.ui_scale)
    status_h = int(24 * ui_state.ui_scale)

    imgui.set_next_window_position(WIN_W - panel_w, toolbar_h)
    imgui.set_next_window_size(panel_w, WIN_H - toolbar_h - status_h)
    imgui.begin("##bones", flags=FIXED_FLAGS)

    renderer.highlight_stick_idx = editor_state.active_stick_idx if editor_state.sticks else -1
    if imgui.button(tr(ui_state, "presets"), width=-1):
        ui_state.show_preset_dialog = True

    imgui.separator()
    bound, total = editor_state.stats()
    imgui.text_colored(tr(ui_state, "voxels_bound", bound=bound, total=total), 0.7, 0.7, 0.7, 1.0)
    imgui.text(tr(ui_state, "particles_count", count=len(editor_state.particles)))
    imgui.text(tr(ui_state, "sticks_count", count=len(editor_state.sticks)))
    if 0 <= editor_state.active_particle_idx < len(editor_state.particles):
        active_particle = editor_state.particles[editor_state.active_particle_idx]
        imgui.text(tr(ui_state, "active_particle", name=active_particle["name"], pid=active_particle["id"]))
        if editor_state.tool_mode == "bone_edit" and editor_state.selected_particles:
            imgui.text(tr(ui_state, "selected_particles_count", count=len(editor_state.selected_particles)))
    else:
        imgui.text(tr(ui_state, "active_particle_none"))

    if editor_state.tool_mode == "bone_edit":
        imgui.separator()
        imgui.text(tr(ui_state, "multi_edit"))
        can_align = (
            len(editor_state.selected_particles) >= 2
            and editor_state.active_particle_idx in editor_state.selected_particles
        )
        if can_align:
            if imgui.button(tr(ui_state, "align_x") + "##align_x"):
                try:
                    editor_state.align_selected_particles("x")
                    ui_state._bone_error = ""
                except Exception as exc:
                    ui_state._bone_error = str(exc)
            imgui.same_line()
            if imgui.button(tr(ui_state, "align_y") + "##align_y"):
                try:
                    editor_state.align_selected_particles("y")
                    ui_state._bone_error = ""
                except Exception as exc:
                    ui_state._bone_error = str(exc)
            imgui.same_line()
            if imgui.button(tr(ui_state, "align_z") + "##align_z"):
                try:
                    editor_state.align_selected_particles("z")
                    ui_state._bone_error = ""
                except Exception as exc:
                    ui_state._bone_error = str(exc)
        else:
            imgui.text_disabled(tr(ui_state, "align_hint"))

        if imgui.button(tr(ui_state, "mirror_normal_x") + "##mirror_preset_x"):
            editor_state.set_mirror_axis("x")
        imgui.same_line()
        if imgui.button(tr(ui_state, "mirror_normal_y") + "##mirror_preset_y"):
            editor_state.set_mirror_axis("y")
        imgui.same_line()
        if imgui.button(tr(ui_state, "mirror_normal_z") + "##mirror_preset_z"):
            editor_state.set_mirror_axis("z")

        if imgui.button(tr(ui_state, "mirror_from_camera") + "##mirror_from_camera", width=-1):
            try:
                editor_state.set_mirror_plane_from_camera(camera.get_view_direction(), camera.target)
                ui_state._bone_error = ""
            except Exception as exc:
                ui_state._bone_error = str(exc)
        if imgui.button(tr(ui_state, "mirror_use_midpoint") + "##mirror_midpoint", width=-1):
            try:
                editor_state.set_mirror_origin_from_pair_midpoint()
                ui_state._bone_error = ""
            except Exception as exc:
                ui_state._bone_error = str(exc)
        if imgui.button(tr(ui_state, "mirror_normalize") + "##mirror_normalize", width=-1):
            try:
                editor_state.normalize_mirror_plane_normal()
                ui_state._bone_error = ""
            except Exception as exc:
                ui_state._bone_error = str(exc)

        _, ui_state.show_mirror_grid = imgui.checkbox(tr(ui_state, "mirror_show_grid"), ui_state.show_mirror_grid)
        _, ui_state.snap_to_mirror_grid = imgui.checkbox(tr(ui_state, "mirror_snap_grid"), ui_state.snap_to_mirror_grid)
        _, ui_state.mirror_grid_mode = imgui.combo(
            tr(ui_state, "mirror_grid_unit"),
            ui_state.mirror_grid_mode,
            [tr(ui_state, "grid_half"), tr(ui_state, "grid_one"), tr(ui_state, "grid_n")],
        )
        if ui_state.mirror_grid_mode == 2:
            _, ui_state.mirror_grid_multiple = imgui.input_int(
                tr(ui_state, "mirror_grid_n_label"),
                ui_state.mirror_grid_multiple,
            )
            ui_state.mirror_grid_multiple = max(1, ui_state.mirror_grid_multiple)
        imgui.text(tr(ui_state, "mirror_current_step", step=_mirror_grid_step(ui_state)))

        if editor_state.mirror_mode:
            label = "mirror_finish_edit" if editor_state.mirror_edit_mode else "mirror_edit_plane"
            if imgui.button(tr(ui_state, label) + "##mirror_edit_toggle", width=-1):
                editor_state.set_mirror_edit_mode(not editor_state.mirror_edit_mode)

        if editor_state.mirror_edit_mode:
            imgui.text(tr(ui_state, "mirror_plane_origin"))
            origin = editor_state.mirror_plane_origin
            changed_x, ox = imgui.input_float("##mirror_origin_x", float(origin[0]), format="%.3f")
            imgui.same_line()
            changed_y, oy = imgui.input_float("##mirror_origin_y", float(origin[1]), format="%.3f")
            imgui.same_line()
            changed_z, oz = imgui.input_float("##mirror_origin_z", float(origin[2]), format="%.3f")
            if changed_x or changed_y or changed_z:
                editor_state.set_mirror_plane_origin(
                    ox if changed_x else origin[0],
                    oy if changed_y else origin[1],
                    oz if changed_z else origin[2],
                )

            imgui.text(tr(ui_state, "mirror_plane_normal"))
            normal = editor_state.mirror_plane_normal
            changed_nx, nx = imgui.input_float("##mirror_normal_x", float(normal[0]), format="%.3f")
            imgui.same_line()
            changed_ny, ny = imgui.input_float("##mirror_normal_y", float(normal[1]), format="%.3f")
            imgui.same_line()
            changed_nz, nz = imgui.input_float("##mirror_normal_z", float(normal[2]), format="%.3f")
            if changed_nx or changed_ny or changed_nz:
                try:
                    editor_state.set_mirror_plane_normal(
                        nx if changed_nx else normal[0],
                        ny if changed_ny else normal[1],
                        nz if changed_nz else normal[2],
                    )
                    ui_state._bone_error = ""
                except Exception as exc:
                    ui_state._bone_error = str(exc)

        if editor_state.mirror_mode:
            imgui.text_colored(
                tr(ui_state, "mirror_active", axis=editor_state.mirror_axis.upper()),
                0.95, 0.85, 0.30, 1.0,
            )
            imgui.text_disabled(tr(ui_state, "mirror_locked"))
            if imgui.button(tr(ui_state, "mirror_mode_exit") + "##mirror_exit", width=-1):
                editor_state.exit_mirror_mode()
        else:
            can_enter_mirror = len(editor_state.selected_particles) == 2
            if imgui.button(tr(ui_state, "mirror_mode_enter") + "##mirror_enter", width=-1):
                if can_enter_mirror:
                    try:
                        editor_state.enter_mirror_mode()
                        ui_state._bone_error = ""
                    except Exception as exc:
                        ui_state._bone_error = str(exc)
            if not can_enter_mirror:
                imgui.text_disabled(tr(ui_state, "mirror_requires_two"))
    imgui.separator()
    imgui.text(tr(ui_state, "stick_list"))
    _draw_stick_list(ui_state, editor_state)

    imgui.separator()
    if editor_state.tool_mode == "voxel_select" and editor_state.selected_voxels:
        imgui.text(tr(ui_state, "selected", count=len(editor_state.selected_voxels)))
        if imgui.button(tr(ui_state, "bind_to_active"), width=-1):
            editor_state.bind_selection(editor_state.active_stick_idx)
        if imgui.button(tr(ui_state, "unbind"), width=-1):
            editor_state.unbind_selection()
        if imgui.button(tr(ui_state, "clear_selection"), width=-1):
            editor_state.clear_selection()
    elif editor_state.tool_mode == "brush" and editor_state.sticks:
        active = editor_state.sticks[editor_state.active_stick_idx]
        imgui.text_colored(tr(ui_state, "brush_active"), 0.4, 0.9, 0.4, 1.0)
        imgui.text(active.name)

    if imgui.button(tr(ui_state, "select_unbound"), width=-1):
        if ui_state.allow_skeleton_edit:
            editor_state.set_tool_mode("voxel_select")
            editor_state.select_unbound()

    imgui.separator()
    _draw_active_stick_editor(ui_state, editor_state)
    _draw_add_stick(ui_state, editor_state)
    _draw_particle_editor(ui_state, editor_state)

    imgui.separator()
    if imgui.collapsing_header(tr(ui_state, "advanced"))[0]:
        _, ui_state.allow_skeleton_edit = imgui.checkbox(tr(ui_state, "allow_skeleton_edit"), ui_state.allow_skeleton_edit)
        if not ui_state.allow_skeleton_edit:
            ui_state.allow_stick_edit = False
            ui_state.allow_particle_edit = False
            editor_state.set_tool_mode("voxel_select")
            editor_state.clear_selection()
        else:
            if not ui_state.allow_stick_edit and not ui_state.allow_particle_edit:
                ui_state.allow_stick_edit = True
                ui_state.allow_particle_edit = True
        if ui_state.allow_skeleton_edit:
            _, ui_state.allow_stick_edit = imgui.checkbox(tr(ui_state, "allow_stick_edit"), ui_state.allow_stick_edit)
            _, ui_state.allow_particle_edit = imgui.checkbox(tr(ui_state, "allow_particle_edit"), ui_state.allow_particle_edit)
        else:
            imgui.text_disabled(tr(ui_state, "disabled_by_master_stick"))
            imgui.text_disabled(tr(ui_state, "disabled_by_master_particle"))

        languages = [tr(ui_state, "language_en"), tr(ui_state, "language_zh")]
        lang_idx = 0 if ui_state.language == "en" else 1
        changed_lang, lang_idx = imgui.combo(tr(ui_state, "language"), lang_idx, languages)
        if changed_lang:
            ui_state.language = "en" if lang_idx == 0 else "zh"
            ui_state._language_dirty = True

        changed_scale, ui_state.ui_scale = imgui.slider_float(tr(ui_state, "ui_scale"), ui_state.ui_scale, 0.8, 1.75, "%.2f")
        ui_state.ui_scale = min(max(ui_state.ui_scale, 0.8), 1.75)
        if changed_scale:
            ui_state._applied_scale = None

        _, ui_state.invert_y_axis = imgui.checkbox(tr(ui_state, "invert_y"), ui_state.invert_y_axis)

        _, ui_state.show_grid = imgui.checkbox(tr(ui_state, "show_grid"), ui_state.show_grid)
        if ui_state.show_grid:
            _, ui_state.show_grid_xz = imgui.checkbox(tr(ui_state, "grid_xz"), ui_state.show_grid_xz)
            _, ui_state.show_grid_xy = imgui.checkbox(tr(ui_state, "grid_xy"), ui_state.show_grid_xy)
            _, ui_state.show_grid_yz = imgui.checkbox(tr(ui_state, "grid_yz"), ui_state.show_grid_yz)
        else:
            imgui.text_disabled(tr(ui_state, "grid_xz"))
            imgui.text_disabled(tr(ui_state, "grid_xy"))
            imgui.text_disabled(tr(ui_state, "grid_yz"))
        _, ui_state.snap_particles_to_grid = imgui.checkbox(tr(ui_state, "snap_grid"), ui_state.snap_particles_to_grid)
        _, ui_state.grid_mode = imgui.combo(
            tr(ui_state, "grid_unit"),
            ui_state.grid_mode,
            [tr(ui_state, "grid_half"), tr(ui_state, "grid_one"), tr(ui_state, "grid_n")],
        )
        if ui_state.grid_mode == 2:
            _, ui_state.grid_multiple = imgui.input_int(tr(ui_state, "grid_n_label"), ui_state.grid_multiple)
            ui_state.grid_multiple = max(1, ui_state.grid_multiple)
        imgui.text(tr(ui_state, "current_step", step=_grid_step(ui_state)))
        imgui.text(tr(ui_state, "trans_bias"))
        imgui.set_next_item_width(80 * ui_state.ui_scale)
        _, ui_state.trans_bias = imgui.input_int("##tbias", ui_state.trans_bias)

    if ui_state._bone_error:
        imgui.separator()
        imgui.text_colored(ui_state._bone_error, 1.0, 0.3, 0.3, 1.0)

    imgui.separator()
    imgui.text_disabled(tr(ui_state, "tip_drag"))
    imgui.text_disabled(tr(ui_state, "tip_axis"))

    imgui.end()


def draw_status_bar(ui_state, editor_state, WIN_W, WIN_H):
    status_h = int(24 * ui_state.ui_scale)
    imgui.set_next_window_position(0, WIN_H - status_h)
    imgui.set_next_window_size(WIN_W, status_h)
    imgui.begin("##status", flags=FIXED_FLAGS | imgui.WINDOW_NO_SCROLLBAR)
    src = editor_state.source_path or "(no file)"
    bound, total = editor_state.stats()
    ns = len(editor_state.sticks)
    if editor_state.tool_mode == "brush":
        mode = tr(ui_state, "mode_brush")
    elif editor_state.tool_mode == "voxel_select":
        mode = tr(ui_state, "mode_voxel_select")
    else:
        mode = tr(ui_state, "mode_bone_edit")
    dirty = tr(ui_state, "unsaved") if editor_state.is_dirty else ""
    imgui.text(tr(ui_state, "status", src=src, total=total, sticks=ns, bound=bound, mode=mode, dirty=dirty))
    imgui.end()


def draw_load_dialog(ui_state, editor_state, renderer, skeleton_sticks_ref, WIN_W, WIN_H):
    if not ui_state.show_load_dialog:
        return
    title = tr(ui_state, "open_file")
    imgui.open_popup(title)
    imgui.set_next_window_position(WIN_W // 2 - 270, WIN_H // 2 - 60)
    imgui.set_next_window_size(540 * ui_state.ui_scale, 120 * ui_state.ui_scale)
    opened, _ = imgui.begin_popup_modal(title, flags=imgui.WINDOW_NO_RESIZE)
    if opened:
        fmt = "VOX" if ui_state.load_mode == "vox" else "XML"
        imgui.text(tr(ui_state, "enter_file_path", fmt=fmt))
        imgui.set_next_item_width(-1)
        _, ui_state.load_path_buf = imgui.input_text("##lp", ui_state.load_path_buf, 1024)

        if imgui.button(tr(ui_state, "ok"), width=80 * ui_state.ui_scale):
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
                ui_state._load_error = tr(ui_state, "file_not_found")
            if not ui_state._load_error:
                ui_state.show_load_dialog = False
                imgui.close_current_popup()

        imgui.same_line()
        if imgui.button(tr(ui_state, "cancel"), width=80 * ui_state.ui_scale):
            ui_state.show_load_dialog = False
            imgui.close_current_popup()

        if ui_state._load_error:
            imgui.text_colored(tr(ui_state, "error", message=ui_state._load_error), 1.0, 0.3, 0.3, 1.0)
        imgui.end_popup()
    else:
        ui_state.show_load_dialog = False


def draw_save_dialog(ui_state, editor_state, skeleton_sticks_ref, WIN_W, WIN_H):
    if not ui_state.show_save_dialog:
        return
    title = tr(ui_state, "save_xml_title")
    imgui.open_popup(title)
    imgui.set_next_window_position(WIN_W // 2 - 270, WIN_H // 2 - 60)
    imgui.set_next_window_size(540 * ui_state.ui_scale, 120 * ui_state.ui_scale)
    opened, _ = imgui.begin_popup_modal(title, flags=imgui.WINDOW_NO_RESIZE)
    if opened:
        imgui.text(tr(ui_state, "output_xml_path"))
        imgui.set_next_item_width(-1)
        _, ui_state.save_path_buf = imgui.input_text("##sp", ui_state.save_path_buf, 1024)

        if imgui.button(tr(ui_state, "save"), width=80 * ui_state.ui_scale):
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
        if imgui.button(tr(ui_state, "cancel"), width=80 * ui_state.ui_scale):
            ui_state.show_save_dialog = False
            ui_state.pending_exit_after_save = False
            imgui.close_current_popup()
        if ui_state._save_error:
            imgui.text_colored(tr(ui_state, "error", message=ui_state._save_error), 1.0, 0.3, 0.3, 1.0)
        imgui.end_popup()
    else:
        ui_state.show_save_dialog = False


def draw_exit_dialog(ui_state, WIN_W, WIN_H):
    if not ui_state.show_exit_dialog:
        return None
    title = tr(ui_state, "unsaved_changes_title")
    imgui.open_popup(title)
    imgui.set_next_window_position(WIN_W // 2 - 220, WIN_H // 2 - 70)
    imgui.set_next_window_size(440 * ui_state.ui_scale, 140 * ui_state.ui_scale)
    opened, _ = imgui.begin_popup_modal(title, flags=imgui.WINDOW_NO_RESIZE)
    if opened:
        imgui.text_wrapped(tr(ui_state, "unsaved_changes_body"))
        imgui.separator()

        if imgui.button(tr(ui_state, "save_and_exit"), width=120 * ui_state.ui_scale):
            ui_state.show_exit_dialog = False
            imgui.close_current_popup()
            imgui.end_popup()
            return "save"
        imgui.same_line()
        if imgui.button(tr(ui_state, "discard_and_exit"), width=140 * ui_state.ui_scale):
            ui_state.show_exit_dialog = False
            ui_state.pending_exit_after_save = False
            imgui.close_current_popup()
            imgui.end_popup()
            return "discard"
        imgui.same_line()
        if imgui.button(tr(ui_state, "cancel_exit"), width=100 * ui_state.ui_scale):
            ui_state.show_exit_dialog = False
            ui_state.pending_exit_after_save = False
            imgui.close_current_popup()
            imgui.end_popup()
            return "cancel"
        imgui.end_popup()
    else:
        ui_state.show_exit_dialog = False
    return None


def draw_preset_dialog(ui_state, editor_state, renderer, skeleton_sticks_ref, WIN_W, WIN_H):
    if not ui_state.show_preset_dialog:
        return
    title = tr(ui_state, "preset_manager")
    imgui.open_popup(title)
    imgui.set_next_window_position(WIN_W // 2 - 240, WIN_H // 2 - 150)
    imgui.set_next_window_size(480 * ui_state.ui_scale, 300 * ui_state.ui_scale)
    opened, _ = imgui.begin_popup_modal(title, flags=imgui.WINDOW_NO_RESIZE)
    if opened:
        presets = editor_state.list_skeleton_presets()
        preset_labels = [f"{p['name']} [{p['particles']}p/{p['sticks']}s]" for p in presets] or [tr(ui_state, "preset_none")]
        ui_state.preset_selected = _clamp_index(ui_state.preset_selected, len(preset_labels))

        imgui.text(tr(ui_state, "preset_desc"))
        imgui.text(tr(ui_state, "preset_desc_keep"))
        imgui.separator()

        imgui.text(tr(ui_state, "available_presets"))
        _, ui_state.preset_selected = imgui.combo("##preset_combo", ui_state.preset_selected, preset_labels)
        if presets:
            selected = presets[ui_state.preset_selected]
            imgui.text(tr(ui_state, "preset_file", file=selected["file"]))
        else:
            imgui.text_disabled(tr(ui_state, "preset_folder_empty"))

        if imgui.button(tr(ui_state, "load_selected"), width=140 * ui_state.ui_scale):
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
        if imgui.button(tr(ui_state, "delete_selected"), width=140 * ui_state.ui_scale):
            if presets:
                try:
                    editor_state.delete_skeleton_preset(presets[ui_state.preset_selected]["path"])
                    ui_state.preset_selected = max(0, ui_state.preset_selected - 1)
                    ui_state._bone_error = ""
                except Exception as exc:
                    ui_state._bone_error = str(exc)

        imgui.separator()
        imgui.text(tr(ui_state, "save_preset_as"))
        imgui.set_next_item_width(-1)
        _, ui_state.preset_name_buf = imgui.input_text("##preset_name", ui_state.preset_name_buf, 128)

        if imgui.button(tr(ui_state, "save_new_preset"), width=140 * ui_state.ui_scale):
            try:
                editor_state.save_skeleton_preset(ui_state.preset_name_buf or "Custom Skeleton", overwrite=False)
                ui_state._bone_error = ""
            except Exception as exc:
                ui_state._bone_error = str(exc)
        imgui.same_line()
        if imgui.button(tr(ui_state, "overwrite_selected"), width=140 * ui_state.ui_scale):
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
        if imgui.button(tr(ui_state, "close"), width=100 * ui_state.ui_scale):
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
        thickness=max(1.0, 1.5 * ui_state.ui_scale),
    )
    draw_list.add_rect_filled(
        x0,
        y0,
        x1,
        y1,
        imgui.get_color_u32_rgba(0.4, 0.7, 1.0, 0.12),
    )
