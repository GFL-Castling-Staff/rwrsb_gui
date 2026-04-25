"""
editor_state.py
Editing state for voxel binding and skeleton structure.
"""
import copy
import json
import logging
import re
from pathlib import Path

import numpy as np

from resource_utils import resource_path

logger = logging.getLogger(__name__)


BONE_COLORS = [
    (0.95, 0.30, 0.30),
    (0.30, 0.75, 0.95),
    (0.40, 0.90, 0.40),
    (0.95, 0.85, 0.20),
    (0.90, 0.50, 0.10),
    (0.70, 0.35, 0.95),
    (0.95, 0.50, 0.75),
    (0.20, 0.60, 0.40),
    (0.20, 0.30, 0.90),
    (0.90, 0.20, 0.60),
    (0.55, 0.85, 0.65),
    (0.95, 0.65, 0.40),
    (0.40, 0.65, 0.95),
    (0.75, 0.95, 0.30),
    (0.60, 0.40, 0.25),
    (0.75, 0.75, 0.75),
]


class StickEntry:
    def __init__(self, constraint_index, particle_a_id, particle_b_id, name, color=None):
        self.constraint_index = int(constraint_index)
        self.particle_a_id = int(particle_a_id)
        self.particle_b_id = int(particle_b_id)
        self.name = name
        self.color = color or BONE_COLORS[self.constraint_index % len(BONE_COLORS)]
        self.visible = True

    def display_name(self):
        return f"[{self.constraint_index}] {self.name}"

    def clone(self):
        cloned = StickEntry(
            self.constraint_index,
            self.particle_a_id,
            self.particle_b_id,
            self.name,
            tuple(self.color),
        )
        # visible 是 UI 状态，不进克隆（undo 里靠 _snapshot visible_by_pair 机制保留）
        return cloned


def _make_stick_name(particles_by_id, pa_id, pb_id):
    pa = particles_by_id.get(pa_id, {})
    pb = particles_by_id.get(pb_id, {})
    na = pa.get("name", f"p{pa_id}")
    nb = pb.get("name", f"p{pb_id}")
    return f"{na}_{nb}"


class EditorState:
    def __init__(self):
        self.voxels = []
        self.particles = []
        self.sticks = []
        self.bindings = {}

        self.source_path = None
        self.trans_bias = 127
        self.selected_voxels = set()
        self.selected_particles = set()
        self.active_stick_idx = 0
        self.active_particle_idx = -1
        self.tool_mode = "brush"
        self.mirror_mode = False
        self.mirror_edit_mode = False
        self.mirror_axis = "x"
        self.mirror_pair = None
        self.mirror_plane_origin = np.zeros(3, dtype=np.float32)
        self.mirror_plane_normal = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        self._undo_stack = []
        self._redo_stack = []
        self._dirty = False

        self.gpu_dirty = True
        self.skeleton_dirty = True

        # ── 动画编辑状态 ──
        self.animation_mode = False
        self.current_animation = None              # animation_io.Animation | None
        self.animation_source_doc = None           # AnimationDocIndex | None
        self.animation_source_idx = -1
        self.current_frame_idx = -1
        self.playback_time = 0.0
        self.playback_playing = False
        self.playback_loop_preview = True          # 预览循环开关（独立于 anim.loop）

        # 进入动画模式前的 particle 位置备份
        self._particle_positions_before_anim = None
        self._anim_dirty = False                   # 动画数据是否有未保存修改

        # 动画模式独立 undo 栈
        self._anim_undo_stack = []
        self._anim_redo_stack = []

    def _preset_dir(self):
        return resource_path("presets")

    def _clone_sticks(self):
        return [stick.clone() for stick in self.sticks]

    def _snapshot(self):
        return {
            "particles": copy.deepcopy(self.particles),
            "sticks": self._clone_sticks(),
            "bindings": copy.deepcopy(self.bindings),
            "active_stick_idx": self.active_stick_idx,
            "active_particle_idx": self.active_particle_idx,
            # 独立保留可视状态，按 particle pair 做 key（constraint_index 在 snapshot 间不稳定）
            "visible_by_pair": {
                (s.particle_a_id, s.particle_b_id): s.visible for s in self.sticks
            },
        }

    def _restore_snapshot(self, snapshot):
        self.particles = copy.deepcopy(snapshot["particles"])
        self.sticks = [stick.clone() for stick in snapshot["sticks"]]
        self.bindings = copy.deepcopy(snapshot["bindings"])
        self.active_stick_idx = int(snapshot["active_stick_idx"])
        self.active_particle_idx = int(snapshot.get("active_particle_idx", -1))
        self._normalize_stick_indices()

        # 恢复可视状态（按 particle pair 匹配，不按 constraint_index）
        vis_map = snapshot.get("visible_by_pair", {})
        for s in self.sticks:
            key = (s.particle_a_id, s.particle_b_id)
            if key in vis_map:
                s.visible = vis_map[key]
            elif (s.particle_b_id, s.particle_a_id) in vis_map:
                s.visible = vis_map[(s.particle_b_id, s.particle_a_id)]
            # 没匹配到（如新增的 stick）默认保持 True

        self._dirty = True
        self.gpu_dirty = True
        self.skeleton_dirty = True

    def _push_undo(self):
        self._undo_stack.append(self._snapshot())
        self._redo_stack.clear()
        if len(self._undo_stack) > 64:
            self._undo_stack.pop(0)

    def _mark_bindings_changed(self):
        self._dirty = True
        self.gpu_dirty = True

    def _mark_skeleton_changed(self):
        self._dirty = True
        self.gpu_dirty = True
        self.skeleton_dirty = True

    def _normalize_stick_indices(self):
        for ci, stick in enumerate(self.sticks):
            stick.constraint_index = ci
        if self.sticks:
            self.active_stick_idx = min(max(self.active_stick_idx, 0), len(self.sticks) - 1)
        else:
            self.active_stick_idx = 0

    def _next_particle_id(self):
        used = {int(p["id"]) for p in self.particles}
        candidate = 1
        while candidate in used:
            candidate += 1
        return candidate

    def _rebuild_sticks_from_raw(self, raw_sticks):
        particles_by_id = {p["id"]: p for p in self.particles}
        self.sticks = []
        for ci, stick in enumerate(raw_sticks):
            pa_id = int(stick["a"])
            pb_id = int(stick["b"])
            name = _make_stick_name(particles_by_id, pa_id, pb_id)
            self.sticks.append(StickEntry(ci, pa_id, pb_id, name))
        self.skeleton_dirty = True

    def exit_mirror_mode(self):
        self.mirror_mode = False
        self.mirror_edit_mode = False
        self.mirror_pair = None

    def set_mirror_edit_mode(self, enabled):
        self.mirror_edit_mode = bool(enabled) and self.mirror_mode

    def set_mirror_axis(self, axis):
        axis = str(axis).lower()
        if axis in ("x", "y", "z"):
            self.mirror_axis = axis
            if axis == "x":
                self.mirror_plane_normal = np.array([1.0, 0.0, 0.0], dtype=np.float32)
            elif axis == "y":
                self.mirror_plane_normal = np.array([0.0, 1.0, 0.0], dtype=np.float32)
            else:
                self.mirror_plane_normal = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    def set_mirror_plane_origin(self, x=None, y=None, z=None):
        origin = np.array(self.mirror_plane_origin, dtype=np.float32)
        if x is not None:
            origin[0] = float(x)
        if y is not None:
            origin[1] = float(y)
        if z is not None:
            origin[2] = float(z)
        self.mirror_plane_origin = origin

    def set_mirror_plane_normal(self, x=None, y=None, z=None):
        normal = np.array(self.mirror_plane_normal, dtype=np.float32)
        if x is not None:
            normal[0] = float(x)
        if y is not None:
            normal[1] = float(y)
        if z is not None:
            normal[2] = float(z)
        length = float(np.linalg.norm(normal))
        if length < 1e-6:
            raise ValueError("Mirror plane normal cannot be zero")
        self.mirror_plane_normal = normal / length
        axis_map = {0: "x", 1: "y", 2: "z"}
        dominant = int(np.argmax(np.abs(self.mirror_plane_normal)))
        axis_value = abs(float(self.mirror_plane_normal[dominant]))
        self.mirror_axis = axis_map[dominant] if axis_value > 0.999 else "custom"

    def normalize_mirror_plane_normal(self):
        self.set_mirror_plane_normal(
            self.mirror_plane_normal[0],
            self.mirror_plane_normal[1],
            self.mirror_plane_normal[2],
        )

    def set_mirror_origin_from_pair_midpoint(self):
        pair = self.mirror_pair if self.mirror_pair else tuple(sorted(self.selected_particles))
        if len(pair) != 2:
            raise ValueError("Need exactly 2 particles to use pair midpoint")
        pa = self.particles[pair[0]]
        pb = self.particles[pair[1]]
        midpoint = np.array(
            [
                (float(pa["x"]) + float(pb["x"])) * 0.5,
                (float(pa["y"]) + float(pb["y"])) * 0.5,
                (float(pa["z"]) + float(pb["z"])) * 0.5,
            ],
            dtype=np.float32,
        )
        self.mirror_plane_origin = midpoint

    def enter_mirror_mode(self):
        if len(self.selected_particles) != 2:
            raise ValueError("Mirror mode requires exactly 2 selected particles")
        pair = tuple(sorted(self.selected_particles))
        self.selected_particles = set(pair)
        if self.active_particle_idx not in self.selected_particles:
            self.active_particle_idx = pair[0]
        self.mirror_pair = pair
        self.mirror_mode = True
        self.mirror_edit_mode = False

    def set_mirror_plane_from_camera(self, view_dir, target=None):
        view_dir = np.asarray(view_dir, dtype=np.float32)
        horizontal = np.array([view_dir[0], 0.0, view_dir[2]], dtype=np.float32)
        length = float(np.linalg.norm(horizontal))
        if length < 1e-6:
            raise ValueError("Camera view is too close to top/bottom for vertical mirror plane")
        horizontal /= length
        plane_normal = np.cross(np.array([0.0, 1.0, 0.0], dtype=np.float32), horizontal)
        self.set_mirror_plane_normal(plane_normal[0], plane_normal[1], plane_normal[2])
        if target is not None:
            target = np.asarray(target, dtype=np.float32)
            self.set_mirror_plane_origin(target[0], target[1], target[2])

    def align_selected_particles(self, axis):
        axis = str(axis).lower()
        if axis not in ("x", "y", "z"):
            raise ValueError(f"Unsupported axis: {axis}")
        if len(self.selected_particles) < 2:
            raise ValueError("Need at least 2 selected particles")
        if self.active_particle_idx not in self.selected_particles:
            raise ValueError("Active particle must be part of the selection")

        anchor = float(self.particles[self.active_particle_idx][axis])
        self._push_undo()
        for idx in sorted(self.selected_particles):
            self.particles[idx][axis] = anchor
        self._mark_skeleton_changed()
        
    def set_tool_mode(self, mode):
        """切换工具模式。离开 bone_edit 时清空 selected_particles。"""
        valid = ("brush", "voxel_select", "bone_edit")
        if mode not in valid:
            return
        if self.tool_mode == "bone_edit" and mode != "bone_edit":
            self.selected_particles.clear()
            self.active_particle_idx = -1
            self.exit_mirror_mode()
        self.tool_mode = mode

    def load_vox(self, path, trans_bias=None):
        from xml_io import parse_vox
        
        # 防御性退出动画模式（避免 _particle_positions_before_anim 错位）
        if self.animation_mode:
            self.exit_animation_mode(force=True)

        if trans_bias is not None:
            self.trans_bias = trans_bias
        self.voxels = parse_vox(path, self.trans_bias)
        self.bindings = {}
        self.selected_voxels = set()
        self.selected_particles = set()
        self.exit_mirror_mode()
        self.source_path = str(path)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._dirty = False
        self.gpu_dirty = True
        self.particles = []
        self.sticks = []
        self.active_stick_idx = 0
        self.active_particle_idx = -1
        self.skeleton_dirty = True
        logger.info("loaded VOX: %s (%d voxels)", path, len(self.voxels))

    def load_xml(self, path, trans_bias=None):
        from xml_io import parse_xml
        
        # 防御性退出动画模式
        if self.animation_mode:
            self.exit_animation_mode(force=True)

        if trans_bias is not None:
            self.trans_bias = trans_bias
        voxels, skeleton, bindings = parse_xml(path)
        self.voxels = voxels
        self.bindings = bindings
        self.selected_voxels = set()
        self.selected_particles = set()
        self.exit_mirror_mode()
        self.source_path = str(path)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._dirty = False
        self.gpu_dirty = True

        self.particles = list(skeleton.get("particles", []))
        self._rebuild_sticks_from_raw(skeleton.get("sticks", []))
        self.active_stick_idx = 0
        self.active_particle_idx = -1

        logger.info("loaded XML: %s (%d voxels, %d particles, %d sticks)",
                    path, len(self.voxels), len(self.particles), len(self.sticks))
        return skeleton

    def load_skeleton_preset(self, preset_path=None):
        # 防御性退出动画模式
        if self.animation_mode:
            self.exit_animation_mode(force=True)
            
        if preset_path is None:
            preset_path = resource_path("presets", "human_skeleton.json")
        data = json.loads(Path(preset_path).read_text(encoding="utf-8"))
        self.particles = list(data.get("particles", []))
        self._rebuild_sticks_from_raw(data.get("sticks", []))
        self.active_stick_idx = 0
        self.active_particle_idx = -1
        self.exit_mirror_mode()
        self.gpu_dirty = True
        self.skeleton_dirty = True
        return data

    def list_skeleton_presets(self):
        preset_dir = self._preset_dir()
        preset_dir.mkdir(parents=True, exist_ok=True)
        presets = []
        for path in sorted(preset_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            presets.append(
                {
                    "file": path.name,
                    "path": str(path),
                    "name": data.get("name", path.stem),
                    "particles": len(data.get("particles", [])),
                    "sticks": len(data.get("sticks", [])),
                }
            )
        return presets

    def current_skeleton_data(self, name=None):
        return {
            "name": name or "Custom Skeleton",
            "particles": copy.deepcopy(self.particles),
            "sticks": [{"a": s.particle_a_id, "b": s.particle_b_id} for s in self.sticks],
        }

    def save_skeleton_preset(self, preset_name, file_name=None, overwrite=False):
        preset_name = str(preset_name).strip()
        if not preset_name:
            raise ValueError("Preset name is required")
        if not self.particles:
            raise ValueError("No particles to save")
        if not self.sticks:
            raise ValueError("No sticks to save")

        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (file_name or preset_name).strip()).strip("._")
        if not safe_stem:
            raise ValueError("Preset file name is invalid")
        if not safe_stem.lower().endswith(".json"):
            safe_stem += ".json"

        preset_dir = self._preset_dir()
        preset_dir.mkdir(parents=True, exist_ok=True)
        out_path = preset_dir / safe_stem
        if out_path.exists() and not overwrite:
            raise ValueError(f"Preset already exists: {out_path.name}")

        data = self.current_skeleton_data(name=preset_name)
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return str(out_path)

    def delete_skeleton_preset(self, preset_path):
        path = Path(preset_path)
        preset_dir = self._preset_dir().resolve()
        resolved = path.resolve()
        if preset_dir not in resolved.parents:
            raise ValueError("Preset path is outside presets directory")
        if not resolved.exists():
            raise ValueError("Preset does not exist")
        resolved.unlink()

    def get_particle_options(self):
        return [f"{p['name']} ({p['id']})" for p in self.particles]

    def set_active_particle(self, particle_index):
        if 0 <= particle_index < len(self.particles):
            self.active_particle_idx = int(particle_index)
        else:
            self.active_particle_idx = -1
            
    def clear_selected_particles(self):
        self.selected_particles.clear()

    def toggle_selected_particle(self, idx):
        """Ctrl+点击语义：如果已选则移除，否则加入。返回最终是否在集合里。"""
        if idx < 0 or idx >= len(self.particles):
            return False
        if idx in self.selected_particles:
            self.selected_particles.remove(idx)
            return False
        self.selected_particles.add(idx)
        return True

    def add_selected_particle(self, idx):
        """Shift+点击语义：追加到集合（不 toggle）。"""
        if 0 <= idx < len(self.particles):
            self.selected_particles.add(idx)

    def replace_selected_particles(self, indices):
        """普通点击/普通框选语义：替换整个集合。"""
        self.selected_particles = {i for i in indices if 0 <= i < len(self.particles)}        

    def set_particle_position(self, particle_index, x, y, z, push_undo=False):
        if particle_index < 0 or particle_index >= len(self.particles):
            return
        if push_undo:
            self._push_undo()
        particle = self.particles[particle_index]
        particle["x"] = float(x)
        particle["y"] = float(y)
        particle["z"] = float(z)
        self.active_particle_idx = particle_index
        self._mark_skeleton_changed()

    def add_particle(self, name=None, x=0.0, y=0.0, z=0.0, invMass=10.0, bodyAreaHint=1, particle_id=None):
        self._push_undo()
        pid = self._next_particle_id() if particle_id is None else int(particle_id)
        if any(int(p["id"]) == pid for p in self.particles):
            raise ValueError(f"Particle id already exists: {pid}")
        self.particles.append(
            {
                "id": pid,
                "name": name or f"particle_{pid}",
                "invMass": float(invMass),
                "bodyAreaHint": int(bodyAreaHint),
                "x": float(x),
                "y": float(y),
                "z": float(z),
            }
        )
        self._mark_skeleton_changed()
        return len(self.particles) - 1

    def update_particle(self, particle_index, **fields):
        if particle_index < 0 or particle_index >= len(self.particles):
            return
        particle = self.particles[particle_index]
        old_id = int(particle["id"])
        new_id = int(fields.get("id", old_id))
        if new_id != old_id and any(int(p["id"]) == new_id for i, p in enumerate(self.particles) if i != particle_index):
            raise ValueError(f"Particle id already exists: {new_id}")

        self._push_undo()
        for key, value in fields.items():
            if key in ("invMass", "x", "y", "z"):
                particle[key] = float(value)
            elif key in ("bodyAreaHint", "id"):
                particle[key] = int(value)
            elif key == "name":
                particle[key] = str(value)

        if new_id != old_id:
            for stick in self.sticks:
                if stick.particle_a_id == old_id:
                    stick.particle_a_id = new_id
                if stick.particle_b_id == old_id:
                    stick.particle_b_id = new_id
        self.rename_sticks_from_particles(push_undo=False)
        self._mark_skeleton_changed()

    def delete_particle(self, particle_index):
        if particle_index < 0 or particle_index >= len(self.particles):
            return
        self._push_undo()
        removed_id = int(self.particles[particle_index]["id"])
        del self.particles[particle_index]

        remap = {}
        kept = []
        next_ci = 0
        for old_ci, stick in enumerate(self.sticks):
            if stick.particle_a_id == removed_id or stick.particle_b_id == removed_id:
                continue
            stick.constraint_index = next_ci
            kept.append(stick)
            remap[old_ci] = next_ci
            next_ci += 1
        self.sticks = kept
        self.bindings = {vi: remap[ci] for vi, ci in self.bindings.items() if ci in remap}
        self.rename_sticks_from_particles(push_undo=False)
        self._normalize_stick_indices()
        # 清理 selected_particles，移除被删的 index，并对剩余 index 做重映射
        new_selected = set()
        for old_idx in self.selected_particles:
            if old_idx == particle_index:
                continue
            new_selected.add(old_idx - 1 if old_idx > particle_index else old_idx)
        self.selected_particles = new_selected
        if self.active_particle_idx == particle_index:
            self.active_particle_idx = -1
        elif self.active_particle_idx > particle_index:
            self.active_particle_idx -= 1
        if self.mirror_pair and particle_index in self.mirror_pair:
            self.exit_mirror_mode()
        self._mark_skeleton_changed()

    def add_stick(self, particle_a_id, particle_b_id, name=None):
        pa_id = int(particle_a_id)
        pb_id = int(particle_b_id)
        if pa_id == pb_id:
            raise ValueError("Stick endpoints must be different particles")
        particle_ids = {int(p["id"]) for p in self.particles}
        if pa_id not in particle_ids or pb_id not in particle_ids:
            raise ValueError("Stick endpoint particle does not exist")
        if any({s.particle_a_id, s.particle_b_id} == {pa_id, pb_id} for s in self.sticks):
            raise ValueError("Stick already exists")

        self._push_undo()
        particles_by_id = {p["id"]: p for p in self.particles}
        ci = len(self.sticks)
        stick_name = name or _make_stick_name(particles_by_id, pa_id, pb_id)
        self.sticks.append(StickEntry(ci, pa_id, pb_id, stick_name))
        self.active_stick_idx = ci
        self._mark_skeleton_changed()

    def update_stick(self, stick_idx, particle_a_id=None, particle_b_id=None, name=None):
        if stick_idx < 0 or stick_idx >= len(self.sticks):
            return
        stick = self.sticks[stick_idx]
        pa_id = stick.particle_a_id if particle_a_id is None else int(particle_a_id)
        pb_id = stick.particle_b_id if particle_b_id is None else int(particle_b_id)
        if pa_id == pb_id:
            raise ValueError("Stick endpoints must be different particles")
        particle_ids = {int(p["id"]) for p in self.particles}
        if pa_id not in particle_ids or pb_id not in particle_ids:
            raise ValueError("Stick endpoint particle does not exist")

        self._push_undo()
        stick.particle_a_id = pa_id
        stick.particle_b_id = pb_id
        if name is None:
            particles_by_id = {p["id"]: p for p in self.particles}
            stick.name = _make_stick_name(particles_by_id, pa_id, pb_id)
        else:
            stick.name = str(name)
        self._mark_skeleton_changed()

    def delete_stick(self, stick_idx):
        if stick_idx < 0 or stick_idx >= len(self.sticks):
            return
        self._push_undo()
        del self.sticks[stick_idx]
        remap = {}
        for old_ci in range(len(self.sticks) + 1):
            if old_ci < stick_idx:
                remap[old_ci] = old_ci
            elif old_ci > stick_idx:
                remap[old_ci] = old_ci - 1
        self.bindings = {vi: remap[ci] for vi, ci in self.bindings.items() if ci in remap}
        self._normalize_stick_indices()
        self._mark_skeleton_changed()

    def rename_sticks_from_particles(self, push_undo=True):
        if push_undo:
            self._push_undo()
        particles_by_id = {p["id"]: p for p in self.particles}
        for stick in self.sticks:
            stick.name = _make_stick_name(particles_by_id, stick.particle_a_id, stick.particle_b_id)
        self._mark_skeleton_changed()

    def set_all_sticks_visible(self, visible: bool):
        """批量设置所有 stick 的 visible。触发 GPU 重传，不入 undo 栈。"""
        for s in self.sticks:
            s.visible = bool(visible)
        self.gpu_dirty = True

    def all_sticks_visibility_state(self):
        """返回 'all' | 'none' | 'mixed' | 'empty'，用于 UI 三态按钮。"""
        if not self.sticks:
            return "empty"
        vis_count = sum(1 for s in self.sticks if s.visible)
        if vis_count == 0:
            return "none"
        if vis_count == len(self.sticks):
            return "all"
        return "mixed"

    def unbind_stick_voxels(self, stick_idx):
        if stick_idx < 0 or stick_idx >= len(self.sticks):
            return
        self._push_undo()
        to_unbind = [vi for vi, ci in self.bindings.items() if ci == stick_idx]
        for vi in to_unbind:
            del self.bindings[vi]
        self._mark_bindings_changed()

    def bind_voxels(self, voxel_indices, stick_idx):
        if not voxel_indices or stick_idx < 0 or stick_idx >= len(self.sticks):
            return
        for vi in voxel_indices:
            self.bindings[vi] = stick_idx
        self._mark_bindings_changed()

    def unbind_voxels(self, voxel_indices):
        for vi in voxel_indices:
            if vi in self.bindings:
                del self.bindings[vi]
        self._mark_bindings_changed()

    def bind_selection(self, stick_idx):
        self._push_undo()
        self.bind_voxels(list(self.selected_voxels), stick_idx)

    def unbind_selection(self):
        self._push_undo()
        self.unbind_voxels(list(self.selected_voxels))

    def begin_brush_stroke(self):
        self._push_undo()

    def commit_brush_stroke(self):
        pass

    def get_voxel_color(self, voxel_index):
        ci = self.bindings.get(voxel_index, -1)
        if ci < 0 or ci >= len(self.sticks):
            _, _, _, r, g, b, _ = self.voxels[voxel_index]
            return (r * 0.5, g * 0.5, b * 0.5)
        stick = self.sticks[ci]
        if not stick.visible:
            _, _, _, r, g, b, _ = self.voxels[voxel_index]
            return (r * 0.5, g * 0.5, b * 0.5)
        return stick.color

    def build_instance_arrays(self):
        n = len(self.voxels)
        positions = np.zeros((n, 3), dtype=np.float32)
        colors = np.zeros((n, 4), dtype=np.float32)
        selected = np.zeros((n, 1), dtype=np.float32)

        for i, (x, y, z, r, g, b, _) in enumerate(self.voxels):
            positions[i] = (x, y, z)
            cr, cg, cb = self.get_voxel_color(i)
            colors[i] = (cr, cg, cb, 1.0)
            selected[i] = 1.0 if i in self.selected_voxels else 0.0

        self.gpu_dirty = False
        return positions, colors, selected

    def select_stick_voxels(self, stick_idx):
        if stick_idx < 0 or stick_idx >= len(self.sticks):
            return
        self.selected_voxels = {vi for vi, ci in self.bindings.items() if ci == stick_idx}
        self.gpu_dirty = True

    def clear_selection(self):
        self.selected_voxels.clear()
        self.gpu_dirty = True

    def select_unbound(self):
        bound = set(self.bindings.keys())
        self.selected_voxels = set(range(len(self.voxels))) - bound
        self.gpu_dirty = True

    def undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        self._restore_snapshot(self._undo_stack.pop())

    def redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self._restore_snapshot(self._redo_stack.pop())

    def save_xml(self, path, skeleton_sticks=None):
        from xml_io import write_xml

        if skeleton_sticks:
            out_sticks = list(skeleton_sticks)
        else:
            out_sticks = [{"a": s.particle_a_id, "b": s.particle_b_id} for s in self.sticks]
        skeleton = {
            "particles": list(self.particles),
            "sticks": out_sticks,
        }
        write_xml(path, self.voxels, skeleton, self.bindings)
        self._dirty = False

    @property
    def is_dirty(self):
        return self._dirty

    def stats(self):
        return len(self.bindings), len(self.voxels)

    @property
    def bones(self):
        return self.sticks

    @property
    def active_bone_idx(self):
        return self.active_stick_idx

    @active_bone_idx.setter
    def active_bone_idx(self, value):
        self.active_stick_idx = value
        
    # ──────────────────────────────────────────────
    # 动画模式：进入 / 退出 / 帧应用
    # ──────────────────────────────────────────────

    def enter_animation_mode(self, animation):
        """进入动画模式，载入 animation 作为编辑目标。

        要求 particle 数 = EXPECTED_PARTICLE_COUNT (15)，否则抛 ValueError。
        如果 animation.frames 为空，自动加一帧 = 当前 particle 姿态。
        """
        from animation_io import EXPECTED_PARTICLE_COUNT, AnimationFrame
        if len(self.particles) != EXPECTED_PARTICLE_COUNT:
            raise ValueError(
                f"Animation editing requires {EXPECTED_PARTICLE_COUNT} particles, "
                f"current skeleton has {len(self.particles)}"
            )

        if not animation.frames:
            # 无关键帧，自动加一帧 = 当前姿态
            init_positions = [
                (float(p['x']), float(p['y']), float(p['z']))
                for p in self.particles
            ]
            animation.frames.append(AnimationFrame(time=0.0, positions=init_positions))
            if animation.end <= 0:
                animation.end = 1.0

        # 备份原始 particle 位置（exit 时用于恢复）
        self._particle_positions_before_anim = [
            (float(p['x']), float(p['y']), float(p['z'])) for p in self.particles
        ]

        # 进入模式时清空 selected_particles 和镜像
        self.selected_particles.clear()
        self.exit_mirror_mode()

        self.animation_mode = True
        self.current_animation = animation
        self.current_frame_idx = 0
        self.playback_time = 0.0
        self.playback_playing = False
        self._anim_dirty = False
        self._anim_undo_stack.clear()
        self._anim_redo_stack.clear()

        # 视觉上 particle 位置变成第 0 帧
        self._apply_frame_to_particles(0)
        logger.info("entered animation mode: %s (%d frames)",
                    animation.name, len(animation.frames))

    def exit_animation_mode(self, force=False):
        """退出动画模式。

        返回：
            None — 已退出
            "dirty_needs_confirmation" — 有脏状态且 force=False，UI 层应弹 confirm
        """
        if not self.animation_mode:
            return None
        if self._anim_dirty and not force:
            return "dirty_needs_confirmation"

        # 恢复 particle 位置
        if self._particle_positions_before_anim:
            for i, (x, y, z) in enumerate(self._particle_positions_before_anim):
                if i < len(self.particles):
                    self.particles[i]['x'] = x
                    self.particles[i]['y'] = y
                    self.particles[i]['z'] = z

        self.animation_mode = False
        self.current_animation = None
        self.animation_source_doc = None
        self.animation_source_idx = -1
        self.current_frame_idx = -1
        self.playback_time = 0.0
        self.playback_playing = False
        self._anim_dirty = False
        self._anim_undo_stack.clear()
        self._anim_redo_stack.clear()
        self._particle_positions_before_anim = None
        self.skeleton_dirty = True
        logger.info("exited animation mode")
        return None

    def _apply_frame_to_particles(self, frame_idx):
        """把指定 frame 的 position 写入 self.particles（视觉用，不入 undo）。"""
        if not self.current_animation:
            return
        if frame_idx < 0 or frame_idx >= len(self.current_animation.frames):
            return
        frame = self.current_animation.frames[frame_idx]
        for i, (x, y, z) in enumerate(frame.positions):
            if i < len(self.particles):
                self.particles[i]['x'] = float(x)
                self.particles[i]['y'] = float(y)
                self.particles[i]['z'] = float(z)
        self.skeleton_dirty = True

    def _apply_interpolated_to_particles(self, t):
        """播放时：用插值 position 写入 self.particles。"""
        from animation_io import interpolate_positions
        if not self.current_animation:
            return
        positions = interpolate_positions(
            self.current_animation, t, n_particles=len(self.particles)
        )
        for i, (x, y, z) in enumerate(positions):
            if i < len(self.particles):
                self.particles[i]['x'] = float(x)
                self.particles[i]['y'] = float(y)
                self.particles[i]['z'] = float(z)
        self.skeleton_dirty = True

    # ──────────────────────────────────────────────
    # 动画模式：独立 undo 栈
    # ──────────────────────────────────────────────

    def _anim_snapshot(self):
        if not self.current_animation:
            return None
        return {
            "animation": copy.deepcopy(self.current_animation),
            "current_frame_idx": self.current_frame_idx,
        }

    def _anim_push_undo(self):
        snap = self._anim_snapshot()
        if snap is None:
            return
        self._anim_undo_stack.append(snap)
        self._anim_redo_stack.clear()
        if len(self._anim_undo_stack) > 64:
            self._anim_undo_stack.pop(0)
        self._anim_dirty = True

    def _anim_restore_snapshot(self, snap):
        self.current_animation = copy.deepcopy(snap["animation"])
        self.current_frame_idx = int(snap["current_frame_idx"])
        if 0 <= self.current_frame_idx < len(self.current_animation.frames):
            self._apply_frame_to_particles(self.current_frame_idx)
        self.skeleton_dirty = True

    def anim_undo(self):
        if not self._anim_undo_stack:
            return
        cur = self._anim_snapshot()
        if cur:
            self._anim_redo_stack.append(cur)
        self._anim_restore_snapshot(self._anim_undo_stack.pop())

    def anim_redo(self):
        if not self._anim_redo_stack:
            return
        cur = self._anim_snapshot()
        if cur:
            self._anim_undo_stack.append(cur)
        self._anim_restore_snapshot(self._anim_redo_stack.pop())

    def get_effective_undo_redo(self):
        """根据当前模式返回 (undo_fn, redo_fn)。UI 按钮统一用此入口。"""
        if self.animation_mode:
            return (self.anim_undo, self.anim_redo)
        return (self.undo, self.redo)

    def commit_particle_move_to_frame(self):
        """粒子拖动结束后，把当前 particle 位置写回当前帧。

        Commit 4 在 main_animation.py 的 mouse_up 回调里调用。
        """
        if not self.animation_mode or not self.current_animation:
            return
        if (self.current_frame_idx < 0
                or self.current_frame_idx >= len(self.current_animation.frames)):
            return
        self._anim_push_undo()  # 已经设了 _anim_dirty
        frame = self.current_animation.frames[self.current_frame_idx]
        frame.positions = [
            (float(p['x']), float(p['y']), float(p['z'])) for p in self.particles
        ]
