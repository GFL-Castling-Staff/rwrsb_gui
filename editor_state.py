"""
editor_state.py
Editing state for voxel binding and skeleton structure.
"""
import copy
import json
import re
from pathlib import Path

import numpy as np


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
        cloned.visible = self.visible
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
        self.active_stick_idx = 0
        self.active_particle_idx = -1
        self.tool_mode = "brush"

        self._undo_stack = []
        self._redo_stack = []
        self._dirty = False

        self.gpu_dirty = True
        self.skeleton_dirty = True

    def _preset_dir(self):
        return Path(__file__).parent / "presets"

    def _clone_sticks(self):
        return [stick.clone() for stick in self.sticks]

    def _snapshot(self):
        return {
            "particles": copy.deepcopy(self.particles),
            "sticks": self._clone_sticks(),
            "bindings": copy.deepcopy(self.bindings),
            "active_stick_idx": self.active_stick_idx,
            "active_particle_idx": self.active_particle_idx,
        }

    def _restore_snapshot(self, snapshot):
        self.particles = copy.deepcopy(snapshot["particles"])
        self.sticks = [stick.clone() for stick in snapshot["sticks"]]
        self.bindings = copy.deepcopy(snapshot["bindings"])
        self.active_stick_idx = int(snapshot["active_stick_idx"])
        self.active_particle_idx = int(snapshot.get("active_particle_idx", -1))
        self._normalize_stick_indices()
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

    def load_vox(self, path, trans_bias=None):
        from xml_io import parse_vox

        if trans_bias is not None:
            self.trans_bias = trans_bias
        self.voxels = parse_vox(path, self.trans_bias)
        self.bindings = {}
        self.selected_voxels = set()
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
        print(f"[state] loaded VOX: {path} ({len(self.voxels)} voxels)")

    def load_xml(self, path, trans_bias=None):
        from xml_io import parse_xml

        if trans_bias is not None:
            self.trans_bias = trans_bias
        voxels, skeleton, bindings = parse_xml(path)
        self.voxels = voxels
        self.bindings = bindings
        self.selected_voxels = set()
        self.source_path = str(path)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._dirty = False
        self.gpu_dirty = True

        self.particles = list(skeleton.get("particles", []))
        self._rebuild_sticks_from_raw(skeleton.get("sticks", []))
        self.active_stick_idx = 0
        self.active_particle_idx = -1

        print(
            f"[state] loaded XML: {path} "
            f"({len(self.voxels)} voxels, {len(self.particles)} particles, {len(self.sticks)} sticks)"
        )
        return skeleton

    def load_skeleton_preset(self, preset_path=None):
        if preset_path is None:
            preset_path = Path(__file__).parent / "presets" / "human_skeleton.json"
        data = json.loads(Path(preset_path).read_text(encoding="utf-8"))
        self.particles = list(data.get("particles", []))
        self._rebuild_sticks_from_raw(data.get("sticks", []))
        self.active_stick_idx = 0
        self.active_particle_idx = -1
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
