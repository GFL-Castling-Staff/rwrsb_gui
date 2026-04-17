"""
editor_state.py
绑骨编辑状态、骨骼列表、Undo/Redo 栈

数据模型 (v2.3):
  RWR 的 skeletonVoxelBindings.group.constraintIndex 指向 *stick* 下标,
  不是 particle 下标。一个 stick 连接两个 particle(两端),体素跟随整根 stick 运动。
  因此状态里同时维护:
    self.particles : 完整 particle 列表(来自 XML <particle> 或 preset),
                     序列化回 XML 用,同时供渲染骨骼线查坐标。
    self.sticks    : list of StickEntry,下标即 constraintIndex。
    self.bindings  : {voxel_index: constraint_index (== stick 下标)}。
"""
import json
import copy
import numpy as np
from pathlib import Path

# 自动分配给骨骼的高对比度颜色表（RGB float 0-1）
BONE_COLORS = [
    (0.95, 0.30, 0.30),  # 红
    (0.30, 0.75, 0.95),  # 青
    (0.40, 0.90, 0.40),  # 绿
    (0.95, 0.85, 0.20),  # 黄
    (0.90, 0.50, 0.10),  # 橙
    (0.70, 0.35, 0.95),  # 紫
    (0.95, 0.50, 0.75),  # 粉
    (0.20, 0.60, 0.40),  # 深绿
    (0.20, 0.30, 0.90),  # 蓝
    (0.90, 0.20, 0.60),  # 洋红
    (0.55, 0.85, 0.65),  # 薄荷
    (0.95, 0.65, 0.40),  # 杏
    (0.40, 0.65, 0.95),  # 天蓝
    (0.75, 0.95, 0.30),  # 黄绿
    (0.60, 0.40, 0.25),  # 棕
    (0.75, 0.75, 0.75),  # 灰（兜底）
]

UNBOUND_COLOR = (0.45, 0.45, 0.45)  # 未绑定体素显示颜色


class StickEntry:
    """
    单根 stick 条目,对应 XML <stick a=... b=.../>
    constraint_index 等同于此 stick 在 self.sticks 列表里的下标。
    """
    def __init__(self, constraint_index, particle_a_id, particle_b_id,
                 name, color=None):
        self.constraint_index = constraint_index
        self.particle_a_id = particle_a_id
        self.particle_b_id = particle_b_id
        self.name = name                  # 默认 "a_name_b_name",可覆盖
        self.color = color or BONE_COLORS[constraint_index % len(BONE_COLORS)]
        self.visible = True

    def display_name(self):
        return f"[{self.constraint_index}] {self.name}"


def _make_stick_name(particles_by_id, pa_id, pb_id):
    """生成 stick 的默认 name: pa_name_pb_name"""
    pa = particles_by_id.get(pa_id, {})
    pb = particles_by_id.get(pb_id, {})
    na = pa.get('name', f'p{pa_id}')
    nb = pb.get('name', f'p{pb_id}')
    return f"{na}_{nb}"


class EditorState:
    def __init__(self):
        self.voxels = []          # list of (x,y,z,r,g,b,a)  原始颜色
        self.particles = []       # list of particle dict(含 id,name,invMass,x,y,z,...)
        self.sticks = []          # list of StickEntry,下标 == constraint_index
        self.bindings = {}        # {voxel_index: constraint_index}

        self.source_path = None   # 当前加载的文件路径
        self.trans_bias = 127     # 坐标变换 bias,可配置

        # 选中状态
        self.selected_voxels = set()   # set of voxel_index
        self.active_stick_idx = 0      # 当前激活 stick 的下标(== ci)

        # 工具模式
        self.tool_mode = 'brush'   # 'brush' | 'select'

        # Undo 栈:每条记录是 bindings 的深拷贝
        self._undo_stack = []
        self._redo_stack = []
        self._dirty = False        # 有未保存修改

        # GPU 端需要刷新的标志
        self.gpu_dirty = True

    # ── 文件加载 ──────────────────────────────

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
        # VOX 路径没有骨架信息,清空骨架。用户需手动 Load Preset。
        self.particles = []
        self.sticks = []
        self.active_stick_idx = 0
        print(f'[state] 已加载 VOX: {path}  ({len(self.voxels)} 体素)')

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

        # 从 XML skeleton 重建 particles + sticks
        self.particles = list(skeleton.get('particles', []))
        self._rebuild_sticks_from_raw(skeleton.get('sticks', []))
        self.active_stick_idx = 0

        print(f'[state] 已加载 XML: {path}  '
              f'({len(self.voxels)} 体素, '
              f'{len(self.particles)} particles, '
              f'{len(self.sticks)} sticks)')
        return skeleton  # 返回原始 skeleton(保留旧接口兼容性)

    def load_skeleton_preset(self, preset_path=None):
        """加载骨骼预设(json),覆盖当前 particles + sticks。不影响 bindings。"""
        if preset_path is None:
            preset_path = Path(__file__).parent / 'presets' / 'human_skeleton.json'
        data = json.loads(Path(preset_path).read_text(encoding='utf-8'))
        self.particles = list(data.get('particles', []))
        self._rebuild_sticks_from_raw(data.get('sticks', []))
        self.active_stick_idx = 0
        self.gpu_dirty = True
        return data  # 保留旧接口:返回完整 data

    def _rebuild_sticks_from_raw(self, raw_sticks):
        """
        从原始 stick dict 列表(含 'a','b' 为 particle id)构建 StickEntry 列表。
        调用方负责先填充 self.particles。
        """
        particles_by_id = {p['id']: p for p in self.particles}
        self.sticks = []
        for ci, s in enumerate(raw_sticks):
            pa_id = int(s['a'])
            pb_id = int(s['b'])
            name = _make_stick_name(particles_by_id, pa_id, pb_id)
            self.sticks.append(StickEntry(ci, pa_id, pb_id, name))

    # ── stick 操作 ────────────────────────────
    # 本工具不支持添加/删除 stick(骨架结构由动画系统约束,不能随便改)。
    # 删除按钮的语义改为:解绑这根 stick 上的所有体素。

    def unbind_stick_voxels(self, stick_idx):
        """把绑定到指定 stick 的所有体素解绑。stick 本身保留。"""
        if stick_idx < 0 or stick_idx >= len(self.sticks):
            return
        self._push_undo()
        to_unbind = [vi for vi, ci in self.bindings.items() if ci == stick_idx]
        for vi in to_unbind:
            del self.bindings[vi]
        self._dirty = True
        self.gpu_dirty = True

    # ── 绑骨操作 ──────────────────────────────

    def bind_voxels(self, voxel_indices, stick_idx):
        """将一批体素绑定到指定 stick。stick_idx == constraint_index。"""
        if not voxel_indices or stick_idx < 0 or stick_idx >= len(self.sticks):
            return
        for vi in voxel_indices:
            self.bindings[vi] = stick_idx
        self._dirty = True
        self.gpu_dirty = True

    def unbind_voxels(self, voxel_indices):
        """解绑一批体素"""
        for vi in voxel_indices:
            if vi in self.bindings:
                del self.bindings[vi]
        self._dirty = True
        self.gpu_dirty = True

    def bind_selection(self, stick_idx):
        """将当前选中体素绑定到 stick"""
        self._push_undo()
        self.bind_voxels(list(self.selected_voxels), stick_idx)

    def unbind_selection(self):
        self._push_undo()
        self.unbind_voxels(list(self.selected_voxels))

    def begin_brush_stroke(self):
        """画笔模式:按下鼠标时推入 undo 快照(操作前)"""
        self._push_undo()

    def commit_brush_stroke(self):
        """画笔模式:松开鼠标(保留空实现,快照已在 begin 时推入)"""
        pass

    # ── 颜色查询(供 renderer 使用)──────────

    def get_voxel_color(self, voxel_index):
        """返回体素应渲染的颜色 (r,g,b)"""
        ci = self.bindings.get(voxel_index, -1)
        if ci < 0 or ci >= len(self.sticks):
            # 未绑定或绑到不存在的 stick:显示原始颜色(略暗)
            ox, oy, oz, r, g, b, a = self.voxels[voxel_index]
            return (r * 0.5, g * 0.5, b * 0.5)
        stick = self.sticks[ci]
        if not stick.visible:
            ox, oy, oz, r, g, b, a = self.voxels[voxel_index]
            return (r * 0.5, g * 0.5, b * 0.5)
        return stick.color

    def build_instance_arrays(self):
        """
        构建 GPU instancing 所需的 numpy 数组,仅在 gpu_dirty 时调用。
        返回:
          positions: (N,3) float32
          colors:    (N,4) float32
          selected:  (N,1) float32
        """
        n = len(self.voxels)
        positions = np.zeros((n, 3), dtype=np.float32)
        colors    = np.zeros((n, 4), dtype=np.float32)
        selected  = np.zeros((n, 1), dtype=np.float32)

        for i, (x, y, z, r, g, b, a) in enumerate(self.voxels):
            positions[i] = (x, y, z)
            cr, cg, cb = self.get_voxel_color(i)
            colors[i] = (cr, cg, cb, 1.0)
            selected[i] = 1.0 if i in self.selected_voxels else 0.0

        self.gpu_dirty = False
        return positions, colors, selected

    # ── 选择操作 ──────────────────────────────

    def select_stick_voxels(self, stick_idx):
        """选中某 stick 的全部体素"""
        if stick_idx < 0 or stick_idx >= len(self.sticks):
            return
        self.selected_voxels = {vi for vi, c in self.bindings.items()
                                if c == stick_idx}
        self.gpu_dirty = True

    def clear_selection(self):
        self.selected_voxels.clear()
        self.gpu_dirty = True

    def select_unbound(self):
        bound = set(self.bindings.keys())
        self.selected_voxels = set(range(len(self.voxels))) - bound
        self.gpu_dirty = True

    # ── Undo / Redo ───────────────────────────

    def _push_undo(self):
        self._undo_stack.append(copy.deepcopy(self.bindings))
        self._redo_stack.clear()
        if len(self._undo_stack) > 64:
            self._undo_stack.pop(0)

    def undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(copy.deepcopy(self.bindings))
        self.bindings = self._undo_stack.pop()
        self._dirty = True
        self.gpu_dirty = True

    def redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(copy.deepcopy(self.bindings))
        self.bindings = self._redo_stack.pop()
        self._dirty = True
        self.gpu_dirty = True

    # ── 保存 ──────────────────────────────────

    def save_xml(self, path, skeleton_sticks=None):
        """
        skeleton_sticks 参数保留给旧调用方;若为 None 或空,则从 self.sticks
        反序列化出 [{'a':..,'b':..},...] 写出。
        """
        from xml_io import write_xml
        if skeleton_sticks:
            out_sticks = list(skeleton_sticks)
        else:
            out_sticks = [{'a': s.particle_a_id, 'b': s.particle_b_id}
                          for s in self.sticks]
        skeleton = {
            'particles': list(self.particles),
            'sticks': out_sticks,
        }
        write_xml(path, self.voxels, skeleton, self.bindings)
        self._dirty = False

    @property
    def is_dirty(self):
        return self._dirty

    def stats(self):
        bound = len(self.bindings)
        total = len(self.voxels)
        return bound, total

    # ── 兼容性别名 ────────────────────────────
    # 为了让旧的 main.py 不改也能跑,提供 bones / active_bone_idx 的只读别名。
    # 新代码应直接用 sticks / active_stick_idx。

    @property
    def bones(self):
        return self.sticks

    @property
    def active_bone_idx(self):
        return self.active_stick_idx

    @active_bone_idx.setter
    def active_bone_idx(self, value):
        self.active_stick_idx = value
