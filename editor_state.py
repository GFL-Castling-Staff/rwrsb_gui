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


def _rotation_matrix(axis, angle_rad):
    """构造绕世界坐标轴旋转的 3×3 矩阵。axis: 'x' | 'y' | 'z'。"""
    c, s = float(np.cos(angle_rad)), float(np.sin(angle_rad))
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float32)
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float32)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float32)


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

        # 5b：各 stick 的参考长度（进入动画模式时记录）
        self._anim_reference_lengths = {}

        # 半身基准 pose（P2）
        self._baseline_positions = None  # list[tuple[float,float,float]] | None
        self._baseline_name = ""
        self._baseline_locked_indices: set = set()

        # 蒙皮 bind pose：每个绑定 voxel 在其 stick 局部坐标系里的固定坐标
        # key = voxel_index, value = np.ndarray shape (3,)
        self._voxel_local_offsets = {}
        # 预分组：ci -> (vis: list[int], locals_arr: np.ndarray (n,3))
        # record_voxel_bind_pose 时填充，update_voxel_positions_from_skeleton 时使用
        self._voxel_groups = {}

        # 骨架树（P3）
        self._tree_parent: dict = {}       # particle idx -> parent idx；root 的 parent 是 None
        self._tree_root_idx: int = -1      # 当前 root 的 particle idx；-1 表示树未构建
        self._tree_dirty: bool = True      # True 时下次访问前需要重建

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
        self._tree_dirty = True

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
        # 蒙皮：骨架变形时同步更新 voxel 世界位置（gpu_dirty 已经在上面设好）
        self.update_voxel_positions_from_skeleton()

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
        self._tree_dirty = True

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

    def rotate_selected_particles(self, angle_x_deg, angle_y_deg, angle_z_deg, pivot_mode="active"):
        """绕指定 pivot 按 X→Y→Z 顺序旋转所有 selected_particles。

        pivot_mode: "active" | "centroid" | "world_origin"
        角度单位：度（deg）。全为 0 时 no-op。
        """
        if not self.selected_particles:
            raise ValueError("至少选择 1 个粒子")

        if pivot_mode == "active":
            if self.active_particle_idx < 0 or self.active_particle_idx not in self.selected_particles:
                raise ValueError("Active 粒子必须在选择集中")
            pa = self.particles[self.active_particle_idx]
            pivot = np.array([pa["x"], pa["y"], pa["z"]], dtype=np.float32)
        elif pivot_mode == "centroid":
            coords = np.array(
                [[self.particles[i]["x"], self.particles[i]["y"], self.particles[i]["z"]]
                 for i in self.selected_particles],
                dtype=np.float32,
            )
            pivot = coords.mean(axis=0)
        elif pivot_mode == "world_origin":
            pivot = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        else:
            raise ValueError(f"未知 pivot_mode: {pivot_mode}")

        if abs(angle_x_deg) < 1e-9 and abs(angle_y_deg) < 1e-9 and abs(angle_z_deg) < 1e-9:
            return

        if self.animation_mode:
            self._anim_push_undo()
        else:
            self._push_undo()

        # 按 X→Y→Z 顺序应用旋转（矩阵从右向左累乘：R = Rz @ Ry @ Rx）
        R = np.eye(3, dtype=np.float32)
        if abs(angle_x_deg) >= 1e-9:
            R = _rotation_matrix("x", np.radians(angle_x_deg)) @ R
        if abs(angle_y_deg) >= 1e-9:
            R = _rotation_matrix("y", np.radians(angle_y_deg)) @ R
        if abs(angle_z_deg) >= 1e-9:
            R = _rotation_matrix("z", np.radians(angle_z_deg)) @ R

        for idx in self.selected_particles:
            p = self.particles[idx]
            p_old = np.array([p["x"], p["y"], p["z"]], dtype=np.float32)
            p_new = pivot + R @ (p_old - pivot)
            p["x"] = float(p_new[0])
            p["y"] = float(p_new[1])
            p["z"] = float(p_new[2])

        self._mark_skeleton_changed()

        if self.animation_mode:
            self.commit_particle_move_to_frame()

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
        self._tree_dirty = True

        # 如果加载了 voxels 且 bindings 存在，记录 bind pose
        if self.voxels and self.bindings:
            self.record_voxel_bind_pose()

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
        self._tree_dirty = True
        return data
    
    def load_skeleton_xml(self, path):
        """从 RWR XML 文件加载 skeleton（particles + sticks）及 voxels/bindings。
        仅供动画工具用。force-exit 动画模式的责任由调用方承担。
        """
        from xml_io import parse_xml

        voxels, skeleton, bindings = parse_xml(path)
        # 保留 voxels 和 bindings（供蒙皮用）
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
        self._tree_dirty = True

        # 如果加载了 voxels 且 bindings 存在，记录 bind pose
        if self.voxels and self.bindings:
            self.record_voxel_bind_pose()

        logger.info("loaded skeleton XML: %s (%d voxels, %d particles, %d sticks)",
                    path, len(self.voxels), len(self.particles), len(self.sticks))
        return skeleton
    
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
        self._tree_dirty = True
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
        self._tree_dirty = True
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
        self._tree_dirty = True
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
        self._tree_dirty = True
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

    def build_instance_arrays(self, use_original_color=False):
        n = len(self.voxels)
        positions = np.zeros((n, 3), dtype=np.float32)
        colors = np.zeros((n, 4), dtype=np.float32)
        selected = np.zeros((n, 1), dtype=np.float32)

        if use_original_color:
            for i, (x, y, z, r, g, b, _) in enumerate(self.voxels):
                positions[i] = (x, y, z)
                colors[i] = (r, g, b, 1.0)
                selected[i] = 1.0 if i in self.selected_voxels else 0.0
        else:
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

        # 蒙皮：以 still pose（_particle_positions_before_anim）作为 bind pose
        # 必须在 _apply_frame_to_particles 之前调用，否则 bind pose 会变成动画第 0 帧
        if self.voxels and self.bindings:
            still_particles = []
            for i, (x, y, z) in enumerate(self._particle_positions_before_anim):
                if i < len(self.particles):
                    p = dict(self.particles[i])
                    p["x"], p["y"], p["z"] = x, y, z
                    still_particles.append(p)
            self.record_voxel_bind_pose(particle_positions=still_particles)

        # 视觉上 particle 位置变成第 0 帧
        self._apply_frame_to_particles(0)
        self._record_reference_lengths()
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
        self._anim_reference_lengths = {}
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
        # 半身锁定：强制覆盖锁定粒子到基准位置（必须在 voxel 重算之前）
        self.apply_baseline_lock_to_particles()
        self.skeleton_dirty = True
        # 蒙皮：粒子位置变了，重算 voxel 世界位置
        self.update_voxel_positions_from_skeleton()
        self.gpu_dirty = True

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
        # 半身锁定：强制覆盖锁定粒子到基准位置（必须在 voxel 重算之前）
        self.apply_baseline_lock_to_particles()
        self.skeleton_dirty = True
        # 蒙皮：粒子位置变了，重算 voxel 世界位置
        self.update_voxel_positions_from_skeleton()
        self.gpu_dirty = True

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
        # 防御：commit 前确保锁定粒子在 baseline 位置，避免意外写入错误坐标
        self.apply_baseline_lock_to_particles()
        self._anim_push_undo()  # 已经设了 _anim_dirty
        frame = self.current_animation.frames[self.current_frame_idx]
        frame.positions = [
            (float(p['x']), float(p['y']), float(p['z'])) for p in self.particles
        ]
        
    # ──────────────────────────────────────────────
    # 动画编辑：关键帧 / 时间 / header / control 事件
    # ──────────────────────────────────────────────

    def anim_set_header(self, name=None, end=None, speed=None, loop=None,
                        speed_spread=None):
        """改 animation header 字段（push undo + 标 dirty）。"""
        if not self.animation_mode or not self.current_animation:
            return
        a = self.current_animation
        if (name is not None and name == a.name and
                end is not None and abs(end - a.end) < 1e-9 and
                speed is not None and abs(speed - a.speed) < 1e-9 and
                loop is not None and bool(loop) == bool(a.loop)):
            return  # no-op，避免每帧拖 slider 都 push undo
        self._anim_push_undo()
        if name is not None:
            a.name = str(name)
        if end is not None:
            a.end = float(max(0.0, end))
        if speed is not None:
            a.speed = float(speed)
        if loop is not None:
            a.loop = bool(loop)
        if speed_spread is not None:
            a.speed_spread = float(speed_spread) if speed_spread != 0 else None

    def anim_add_frame_at(self, time):
        """在指定 time 处加一帧，positions = 当前 particle 姿态。
        返回新帧的 sorted-after index（current_frame_idx 切到该帧）。"""
        from animation_io import AnimationFrame
        if not self.animation_mode or not self.current_animation:
            return -1
        self._anim_push_undo()
        positions = [
            (float(p['x']), float(p['y']), float(p['z'])) for p in self.particles
        ]
        new_frame = AnimationFrame(time=float(time), positions=positions)
        self.current_animation.frames.append(new_frame)
        self.current_animation.frames.sort(key=lambda f: f.time)
        new_idx = self.current_animation.frames.index(new_frame)
        self.current_frame_idx = new_idx
        return new_idx

    def anim_delete_frame(self, frame_idx):
        """删除指定帧。最后一帧禁删（返回 False）。"""
        if not self.animation_mode or not self.current_animation:
            return False
        frames = self.current_animation.frames
        if len(frames) <= 1:
            return False
        if frame_idx < 0 or frame_idx >= len(frames):
            return False
        self._anim_push_undo()
        del frames[frame_idx]
        # 调整 current_frame_idx
        if self.current_frame_idx >= len(frames):
            self.current_frame_idx = len(frames) - 1
        self._apply_frame_to_particles(self.current_frame_idx)
        return True

    def anim_set_frame_time(self, frame_idx, new_time):
        """改某帧的 time，结束后排序并校正 current_frame_idx。"""
        if not self.animation_mode or not self.current_animation:
            return
        frames = self.current_animation.frames
        if frame_idx < 0 or frame_idx >= len(frames):
            return
        if abs(frames[frame_idx].time - float(new_time)) < 1e-9:
            return
        self._anim_push_undo()
        target_frame = frames[frame_idx]
        target_frame.time = float(max(0.0, new_time))
        frames.sort(key=lambda f: f.time)
        self.current_frame_idx = frames.index(target_frame)

    def anim_select_frame(self, frame_idx):
        """选中某帧，把 particle 应用到该帧（不入 undo）。"""
        if not self.animation_mode or not self.current_animation:
            return
        if frame_idx < 0 or frame_idx >= len(self.current_animation.frames):
            return
        self.current_frame_idx = frame_idx
        self.playback_time = self.current_animation.frames[frame_idx].time
        self._apply_frame_to_particles(frame_idx)

    def anim_duplicate_current_frame(self):
        """复制当前帧（time 在原基础上 +0.05s，避免重叠）。"""
        from animation_io import AnimationFrame
        if not self.animation_mode or not self.current_animation:
            return
        frames = self.current_animation.frames
        if self.current_frame_idx < 0 or self.current_frame_idx >= len(frames):
            return
        src = frames[self.current_frame_idx]
        new_time = src.time + 0.05
        # 如果会和现有帧 time 重叠，找一个不冲突的
        existing_times = {round(f.time, 6) for f in frames}
        while round(new_time, 6) in existing_times:
            new_time += 0.05
        self._anim_push_undo()
        new_frame = AnimationFrame(
            time=new_time,
            positions=list(src.positions),
            controls=list(src.controls),
        )
        frames.append(new_frame)
        frames.sort(key=lambda f: f.time)
        self.current_frame_idx = frames.index(new_frame)
        self._apply_frame_to_particles(self.current_frame_idx)

    def anim_add_control(self, frame_idx, key="shoot", value=1):
        if not self.animation_mode or not self.current_animation:
            return
        frames = self.current_animation.frames
        if frame_idx < 0 or frame_idx >= len(frames):
            return
        self._anim_push_undo()
        frames[frame_idx].controls.append((str(key), int(value)))

    def anim_remove_control(self, frame_idx, control_idx):
        if not self.animation_mode or not self.current_animation:
            return
        frames = self.current_animation.frames
        if frame_idx < 0 or frame_idx >= len(frames):
            return
        if control_idx < 0 or control_idx >= len(frames[frame_idx].controls):
            return
        self._anim_push_undo()
        del frames[frame_idx].controls[control_idx]

    def anim_set_control(self, frame_idx, control_idx, key=None, value=None):
        if not self.animation_mode or not self.current_animation:
            return
        frames = self.current_animation.frames
        if frame_idx < 0 or frame_idx >= len(frames):
            return
        if control_idx < 0 or control_idx >= len(frames[frame_idx].controls):
            return
        old_key, old_value = frames[frame_idx].controls[control_idx]
        new_key = old_key if key is None else str(key)
        new_value = old_value if value is None else int(value)
        if new_key == old_key and new_value == old_value:
            return
        self._anim_push_undo()
        frames[frame_idx].controls[control_idx] = (new_key, new_value)

    def _record_reference_lengths(self):
        """记录当前 skeleton 各 stick 长度作为参考基准（enter_animation_mode 时调用）。"""
        self._anim_reference_lengths = {}
        id_to_p = {p["id"]: p for p in self.particles}
        for i, s in enumerate(self.sticks):
            pa = id_to_p.get(s.particle_a_id)
            pb = id_to_p.get(s.particle_b_id)
            if pa is None or pb is None:
                continue
            dx = pa["x"] - pb["x"]
            dy = pa["y"] - pb["y"]
            dz = pa["z"] - pb["z"]
            self._anim_reference_lengths[i] = (dx*dx + dy*dy + dz*dz) ** 0.5

    def compute_stick_length_deviations(self):
        """返回 list[(stick_idx, current_length, ref_length, abs_pct_dev)]。无参考的 stick 不返回。"""
        out = []
        id_to_p = {p["id"]: p for p in self.particles}
        for i, s in enumerate(self.sticks):
            ref = self._anim_reference_lengths.get(i, 0.0)
            pa = id_to_p.get(s.particle_a_id)
            pb = id_to_p.get(s.particle_b_id)
            if pa is None or pb is None or ref <= 0:
                continue
            dx = pa["x"] - pb["x"]
            dy = pa["y"] - pb["y"]
            dz = pa["z"] - pb["z"]
            cur = (dx*dx + dy*dy + dz*dz) ** 0.5
            pct = abs(cur - ref) / ref * 100.0
            out.append((i, cur, ref, pct))
        return out

    # ──────────────────────────────────────────────
    # 蒙皮（单骨刚性 LBS）
    # ──────────────────────────────────────────────

    def validate_voxel_bindings(self):
        """校验当前加载的 voxels 是否全部绑了有效的 stick。

        返回 (is_valid, reason)：
            is_valid=True  → reason=""
            is_valid=False → reason 说明哪里不合法
        """
        n_voxels = len(self.voxels)
        n_sticks = len(self.sticks)
        n_bindings = len(self.bindings)

        if n_voxels == 0:
            return True, ""

        if n_bindings != n_voxels:
            return False, f"{n_voxels - n_bindings} 个 voxel 未绑骨"

        invalid_bindings = [
            vi for vi, ci in self.bindings.items()
            if ci < 0 or ci >= n_sticks
        ]
        if invalid_bindings:
            return False, f"{len(invalid_bindings)} 个 binding 引用了不存在的 stick"

        return True, ""

    def discard_voxels_keep_skeleton(self):
        """丢弃 voxels 和 bindings，保留 particles + sticks。
        用于"非法 voxel 绑定"对话框的"只加载骨架"分支。
        """
        self.voxels = []
        self.bindings = {}
        self.selected_voxels = set()
        self._voxel_local_offsets = {}
        self._voxel_groups = {}
        self.gpu_dirty = True

    def _compute_stick_frame(self, particle_a, particle_b):
        """计算 stick 的局部坐标系。

        返回 (origin, R)：
            origin: np.ndarray shape (3,) —— stick 中点
            R: np.ndarray shape (3, 3) —— 列向量是 [u, v, w] 三个正交单位轴
        """
        a = np.array([particle_a["x"], particle_a["y"], particle_a["z"]], dtype=np.float32)
        b = np.array([particle_b["x"], particle_b["y"], particle_b["z"]], dtype=np.float32)
        origin = (a + b) * 0.5

        diff = b - a
        length = float(np.linalg.norm(diff))
        if length < 1e-6:
            return origin, np.eye(3, dtype=np.float32)
        u = diff / length

        # 辅助参考：默认世界 Y，主轴接近 Y 时 fallback 到世界 X
        if abs(float(u[1])) > 0.95:
            ref = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        else:
            ref = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        v = np.cross(u, ref)
        v_len = float(np.linalg.norm(v))
        if v_len < 1e-6:
            return origin, np.eye(3, dtype=np.float32)
        v = v / v_len

        w = np.cross(u, v)
        R = np.column_stack([u, v, w]).astype(np.float32)
        return origin, R

    def record_voxel_bind_pose(self, particle_positions=None):
        """记录所有绑定 voxel 在其 stick 局部坐标系里的固定坐标。
        同时预分组（按 stick 分）供 update_voxel_positions_from_skeleton 向量化使用。

        particle_positions: 可选，list[dict]，结构同 self.particles。
            如果传入，使用这份位置作为 bind pose。
            如果不传，使用 self.particles 当前位置。
        """
        self._voxel_local_offsets = {}
        self._voxel_groups = {}
        if not self.voxels or not self.bindings:
            return

        particles = particle_positions if particle_positions is not None else self.particles
        if particle_positions is not None and len(particle_positions) != len(self.particles):
            particles = self.particles

        id_to_p = {int(p["id"]): p for p in particles}

        # 每根 stick 只算一次坐标系
        stick_frames = {}
        for vi, ci in self.bindings.items():
            if ci < 0 or ci >= len(self.sticks):
                continue
            if ci not in stick_frames:
                stick = self.sticks[ci]
                pa = id_to_p.get(int(stick.particle_a_id))
                pb = id_to_p.get(int(stick.particle_b_id))
                if pa is not None and pb is not None:
                    stick_frames[ci] = self._compute_stick_frame(pa, pb)

            frame = stick_frames.get(ci)
            if frame is None:
                continue
            if vi < 0 or vi >= len(self.voxels):
                continue

            origin, R = frame
            v_world = np.array(self.voxels[vi][:3], dtype=np.float32)
            v_local = R.T @ (v_world - origin)
            self._voxel_local_offsets[vi] = v_local

        # 预分组：ci -> (vis, locals_arr)，供 update 时向量化批量乘
        groups_temp = {}
        for vi, v_local in self._voxel_local_offsets.items():
            ci = self.bindings.get(vi, -1)
            if 0 <= ci < len(self.sticks):
                if ci not in groups_temp:
                    groups_temp[ci] = []
                groups_temp[ci].append((vi, v_local))
        for ci, items in groups_temp.items():
            vis = [it[0] for it in items]
            locals_arr = np.stack([it[1] for it in items])  # (n, 3)
            self._voxel_groups[ci] = (vis, locals_arr)

    def update_voxel_positions_from_skeleton(self):
        """根据当前 skeleton 重新计算所有绑定 voxel 的世界位置。

        使用预分组 _voxel_groups：每根 stick 只计算一次坐标系，然后向量化批量应用。
        调用方负责标 self.gpu_dirty = True。
        """
        if not self._voxel_groups or not self.voxels:
            return

        id_to_p = {int(p["id"]): p for p in self.particles}

        for ci, (vis, locals_arr) in self._voxel_groups.items():
            if ci >= len(self.sticks):
                continue
            stick = self.sticks[ci]
            pa = id_to_p.get(int(stick.particle_a_id))
            pb = id_to_p.get(int(stick.particle_b_id))
            if pa is None or pb is None:
                continue

            origin, R = self._compute_stick_frame(pa, pb)
            # 批量计算：locals_arr (n,3) → worlds_arr (n,3)
            worlds_arr = locals_arr @ R.T + origin

            for k, vi in enumerate(vis):
                if vi < len(self.voxels):
                    old = self.voxels[vi]
                    self.voxels[vi] = (
                        float(worlds_arr[k, 0]), float(worlds_arr[k, 1]), float(worlds_arr[k, 2]),
                        old[3], old[4], old[5], old[6],
                    )


    # ──────────────────────────────────────────────
    # 半身基准 pose（P2）
    # ──────────────────────────────────────────────

    def load_baseline_pose(self, source, **kwargs):
        """加载基准 pose。

        source: "vanilla_still" | "current_frame" | "file"

        kwargs:
            vanilla_path (str): source="vanilla_still" 时必传（vanilla soldier_animations.xml 路径）
            file_path (str):    source="file" 时必传

        成功设置 self._baseline_positions 和 self._baseline_name；失败抛 ValueError。
        """
        if source == "vanilla_still":
            path = kwargs.get("vanilla_path")
            if not path:
                raise ValueError("未设置 vanilla 路径")
            positions = self._parse_animation_first_frame(path, animation_name="still")
            if positions is None:
                raise ValueError("在 vanilla 文件中未找到 still 动画")
            self._baseline_positions = positions
            self._baseline_name = "Vanilla Still Pose"

        elif source == "current_frame":
            if not self.particles:
                raise ValueError("当前没有粒子")
            self._baseline_positions = [
                (float(p["x"]), float(p["y"]), float(p["z"]))
                for p in self.particles
            ]
            self._baseline_name = f"当前帧 ({len(self.particles)} 粒子)"

        elif source == "file":
            path = kwargs.get("file_path")
            if not path:
                raise ValueError("未指定文件路径")
            positions = self._parse_animation_first_frame(path)
            if positions is None:
                raise ValueError("文件中未找到任何动画帧")
            self._baseline_positions = positions
            import os
            self._baseline_name = f"文件: {os.path.basename(path)}"

        else:
            raise ValueError(f"未知 source: {source}")

    def _parse_animation_first_frame(self, xml_path, animation_name=None):
        """解析 animation XML，返回指定动画第 0 帧的 positions。

        animation_name: 可选，None 时取文件第一个动画。
        返回 list[tuple[float,float,float]] 或 None（找不到时）。
        """
        from animation_io import parse_animation_index, parse_single_animation
        try:
            doc = parse_animation_index(xml_path)
        except Exception as exc:
            raise ValueError(f"解析动画文件失败: {exc}") from exc

        if animation_name is not None:
            idx = doc.name_to_index.get(animation_name)
            if idx is None:
                return None
            anim = parse_single_animation(xml_path, idx)
        else:
            if not doc.names:
                return None
            anim = parse_single_animation(xml_path, 0)

        if not anim.frames:
            return None
        return list(anim.frames[0].positions)

    def clear_baseline_pose(self):
        """清空基准 pose，同时清空锁定集合。"""
        self._baseline_positions = None
        self._baseline_name = ""
        self._baseline_locked_indices = set()

    def set_baseline_locked_indices(self, indices):
        """设置锁定的 particle idx 集合（覆盖式）。"""
        self._baseline_locked_indices = set(int(i) for i in indices)

    def apply_baseline_lock_to_particles(self):
        """把所有锁定 idx 强制覆盖为 baseline pose 的对应位置。

        baseline 未加载或锁定集合为空时 no-op。
        调用方负责设 skeleton_dirty / gpu_dirty 并调用 update_voxel_positions_from_skeleton。
        """
        if self._baseline_positions is None:
            return
        if not self._baseline_locked_indices:
            return
        for idx in self._baseline_locked_indices:
            if 0 <= idx < len(self.particles) and 0 <= idx < len(self._baseline_positions):
                x, y, z = self._baseline_positions[idx]
                self.particles[idx]["x"] = float(x)
                self.particles[idx]["y"] = float(y)
                self.particles[idx]["z"] = float(z)

    def fill_baseline_to_selected_across_frames(self):
        """把 selected_particles 里所有粒子在所有关键帧的位置统一覆写为 baseline 对应值。

        P6 决策：selected 里有任何 idx 越界（>= len(_baseline_positions)）时整体拒绝。
        """
        if not self.animation_mode or self.current_animation is None:
            raise ValueError("不在动画模式下")
        if self._baseline_positions is None:
            raise ValueError("未加载 baseline pose")
        if not self.selected_particles:
            raise ValueError("未选择任何粒子")

        n_baseline = len(self._baseline_positions)
        out_of_range = [i for i in self.selected_particles if i >= n_baseline or i < 0]
        if out_of_range:
            raise ValueError(
                f"选中的粒子中有 {len(out_of_range)} 个越界"
                f"（baseline 只有 {n_baseline} 个粒子）"
            )

        self._anim_push_undo()

        for frame in self.current_animation.frames:
            positions = list(frame.positions)
            for idx in self.selected_particles:
                if 0 <= idx < len(positions):
                    positions[idx] = tuple(self._baseline_positions[idx])
            frame.positions = positions

        # 立即刷新当前帧视觉
        self._apply_frame_to_particles(self.current_frame_idx)

    # ──────────────────────────────────────────────
    # 骨架树（P3）
    # ──────────────────────────────────────────────

    def _build_skeleton_tree(self, root_idx):
        """从 root_idx 出发用 BFS 构建有向树，结果写入 self._tree_parent。

        BFS tie-breaking 规则：
        1. 距 root 距离更近的 parent 优先（BFS 自然满足）
        2. 同距离时，sticks 列表里更早出现的 stick 对应的 parent 优先
        """
        self._tree_parent = {}
        self._tree_root_idx = -1
        if not self.particles:
            self._tree_dirty = False
            return
        if root_idx < 0 or root_idx >= len(self.particles):
            self._tree_dirty = False
            return

        id_to_idx = {int(p["id"]): i for i, p in enumerate(self.particles)}
        adj = {i: [] for i in range(len(self.particles))}
        for so, s in enumerate(self.sticks):
            ai = id_to_idx.get(int(s.particle_a_id))
            bi = id_to_idx.get(int(s.particle_b_id))
            if ai is None or bi is None:
                continue
            adj[ai].append((bi, so))
            adj[bi].append((ai, so))

        for i in adj:
            adj[i].sort(key=lambda x: x[1])

        from collections import deque
        visited = {root_idx}
        self._tree_parent[root_idx] = None
        queue = deque([root_idx])
        while queue:
            cur = queue.popleft()
            for nb, _so in adj[cur]:
                if nb in visited:
                    continue
                visited.add(nb)
                self._tree_parent[nb] = cur
                queue.append(nb)

        self._tree_root_idx = root_idx
        self._tree_dirty = False

    def get_skeleton_tree(self):
        """返回当前骨架树（parent_dict, root_idx）。
        parent_dict: dict[int, int|None] — particle idx -> parent idx；root 的 parent 为 None
        root_idx: int — -1 表示树无效
        """
        if self._tree_dirty:
            target = self._tree_root_idx if 0 <= self._tree_root_idx < len(self.particles) else 8
            if target >= len(self.particles):
                target = 0 if self.particles else -1
            if target >= 0:
                self._build_skeleton_tree(target)
            else:
                self._tree_parent = {}
                self._tree_root_idx = -1
                self._tree_dirty = False
        return self._tree_parent, self._tree_root_idx

    def set_skeleton_tree_root(self, root_idx):
        """改变 root 并重建树。无效 idx raise ValueError。"""
        if root_idx < 0 or root_idx >= len(self.particles):
            raise ValueError(f"root_idx 越界: {root_idx}")
        self._build_skeleton_tree(root_idx)

    def collect_subtree_indices(self, start_idx):
        """从 start_idx 出发，沿 parent→child 方向收集整棵子树的 particle idx 集合（含 start_idx 本身）。
        start_idx 不在当前树里时 raise ValueError。
        """
        parent, _ = self.get_skeleton_tree()
        if start_idx not in parent:
            raise ValueError(f"start_idx={start_idx} 不在当前骨架树里")
        children = {}
        for child, par in parent.items():
            if par is None:
                continue
            children.setdefault(par, []).append(child)
        result = {start_idx}
        stack = [start_idx]
        while stack:
            cur = stack.pop()
            for c in children.get(cur, []):
                if c not in result:
                    result.add(c)
                    stack.append(c)
        return result

    def apply_length_clamp_to_drag(self, delta, drag_idx_set):
        """对正在被拖动的整组粒子应用 length clamp（PBD 迭代松弛）。

        输入：
            delta: np.ndarray (3,) — 鼠标拟应用的整组平移量
            drag_idx_set: set[int] — 被拖动的 particle idx 集合（已剔除 locked）
        返回：
            修正后的 delta（np.ndarray (3,)）
        """
        if not self._anim_reference_lengths or not drag_idx_set:
            return delta
        if not self.sticks:
            return delta

        id_to_idx = {int(p["id"]): i for i, p in enumerate(self.particles)}
        boundary = []
        for si, s in enumerate(self.sticks):
            ai = id_to_idx.get(int(s.particle_a_id))
            bi = id_to_idx.get(int(s.particle_b_id))
            if ai is None or bi is None:
                continue
            in_a = ai in drag_idx_set
            in_b = bi in drag_idx_set
            if in_a == in_b:
                continue
            ref = self._anim_reference_lengths.get(si, 0.0)
            if ref <= 0:
                continue
            inner_idx = ai if in_a else bi
            outer_idx = bi if in_a else ai
            boundary.append((si, inner_idx, outer_idx, ref))

        if not boundary:
            return delta

        delta = np.asarray(delta, dtype=np.float32).copy()
        MAX_ITER = 5
        for _ in range(MAX_ITER):
            violations = []
            for si, inner_idx, outer_idx, ref in boundary:
                inner_p = self.particles[inner_idx]
                outer_p = self.particles[outer_idx]
                inner_new = np.array(
                    [float(inner_p["x"]) + delta[0],
                     float(inner_p["y"]) + delta[1],
                     float(inner_p["z"]) + delta[2]],
                    dtype=np.float32,
                )
                outer_pos = np.array(
                    [float(outer_p["x"]), float(outer_p["y"]), float(outer_p["z"])],
                    dtype=np.float32,
                )
                diff = inner_new - outer_pos
                cur_len = float(np.linalg.norm(diff))
                if cur_len <= ref + 1e-5:
                    continue
                overshoot = cur_len - ref
                if cur_len > 1e-6:
                    correction = (diff / cur_len) * overshoot
                    violations.append(correction)
            if not violations:
                break
            avg_corr = np.mean(np.stack(violations), axis=0)
            delta = delta - avg_corr

        return delta


# ──────────────────────────────────────────────
# 模块级辅助：XML voxel binding 合法性预校验
# ──────────────────────────────────────────────

def check_xml_voxel_bindings(path):
    """校验 XML 文件的 voxel binding 合法性，不修改任何 EditorState。

    返回 (is_valid, reason, info)：
        is_valid: bool
        reason: 不合法时的简短原因（中文，给用户看）
        info: dict，包含 n_voxels / n_sticks / n_bindings 用于对话框展示
    """
    from xml_io import parse_xml
    try:
        voxels, skeleton, bindings = parse_xml(path)
    except Exception as exc:
        return False, f"解析失败: {exc}", {}

    n_voxels = len(voxels)
    n_sticks = len(skeleton.get("sticks", []))
    n_bindings = len(bindings)
    info = {"n_voxels": n_voxels, "n_sticks": n_sticks, "n_bindings": n_bindings}

    if n_voxels == 0:
        return True, "", info

    if n_bindings != n_voxels:
        return False, f"{n_voxels - n_bindings} 个 voxel 未绑骨", info

    invalid = [vi for vi, ci in bindings.items() if ci < 0 or ci >= n_sticks]
    if invalid:
        return False, f"{len(invalid)} 个 binding 引用了不存在的 stick", info

    return True, "", info
