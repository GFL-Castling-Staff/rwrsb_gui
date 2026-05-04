"""
renderer.py
ModernGL instanced rendering for voxels, skeleton lines, and particle handles.
"""
import moderngl
import numpy as np

from resource_utils import resource_path


_LINE_ALPHA_OCCLUDED = 0.25
_LINE_ALPHA_VISIBLE = 0.95
_LINE_WIDTH = 2.0
_LINE_WIDTH_HIGHLIGHT = 4.0
_HIGHLIGHT_COLOR = (1.0, 0.95, 0.25)
_PARTICLE_COLOR = (0.95, 0.35, 0.20)
_PARTICLE_SIZE = 10.0
_PARTICLE_SIZE_HIGHLIGHT = 16.0
_PARTICLE_SIZE_SELECTED = 13.0
_PARTICLE_SELECTED_COLOR = (1.0, 0.85, 0.35, 1.0)  # 次亮淡黄（已选非 active）
_PARTICLE_SIZE_ACTIVE = 15.0
_PARTICLE_ACTIVE_COLOR = (0.25, 0.95, 1.0, 1.0)    # 青色，与淡黄明显区分
_PARTICLE_LOCKED_COLOR = (0.45, 0.55, 0.75, 0.7)   # 半透明灰蓝（锁定粒子，P2）
_GRID_MINOR_COLOR = (0.28, 0.31, 0.38)
_GRID_MAJOR_COLOR = (0.52, 0.56, 0.66)
_MIRROR_PLANE_COLOR = (0.25, 0.90, 0.95)
_MIRROR_NORMAL_COLOR = (0.20, 1.00, 0.55)
_MIRROR_ORIGIN_COLOR = (1.0, 0.95, 0.35)
_MIRROR_ARROW_COLOR = (0.35, 1.0, 0.70)
_MIRROR_HANDLE_SIZE = 14.0
_MIRROR_ARROW_SIZE = 18.0

# 选区 gizmo（Blender 风格 3 轴箭头 + 3 圆环 + 中心球）
_GIZMO_AXIS_COLORS = {
    "x": (1.00, 0.30, 0.35, 1.0),   # 红
    "y": (0.30, 0.95, 0.35, 1.0),   # 绿
    "z": (0.30, 0.55, 1.00, 1.0),   # 蓝
}
_GIZMO_HOVER_COLOR = (1.0, 0.95, 0.25, 1.0)   # 黄
_GIZMO_CENTER_COLOR = (0.85, 0.85, 0.85, 1.0)
_GIZMO_HIT_THRESHOLD_PX = 10.0
_GIZMO_CENTER_HIT_PX = 8.0


def _point_to_segment_dist_2d(px, py, ax, ay, bx, by):
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    ab_len2 = abx * abx + aby * aby
    if ab_len2 < 1e-9:
        return float(np.hypot(px - ax, py - ay))
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab_len2))
    cx = ax + t * abx
    cy = ay + t * aby
    return float(np.hypot(px - cx, py - cy))


def _project_world_to_screen(world_pt, mvp, screen_w, screen_h):
    """世界点 → 屏幕坐标（top-left origin），返回 (sx, sy) 或 None。"""
    p = np.array([world_pt[0], world_pt[1], world_pt[2], 1.0], dtype=np.float32)
    clip = mvp @ p
    if abs(clip[3]) < 1e-6:
        return None
    ndc = clip[:3] / clip[3]
    sx = (ndc[0] + 1.0) * 0.5 * screen_w
    sy = (1.0 - ndc[1]) * 0.5 * screen_h
    return (float(sx), float(sy))


def _make_cube_vbo():
    faces = [
        (0, 0, 1, [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 0, 1), (1, 1, 1), (0, 1, 1)]),
        (0, 0, -1, [(1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)]),
        (1, 0, 0, [(1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 0, 0), (1, 1, 1), (1, 1, 0)]),
        (-1, 0, 0, [(0, 0, 1), (0, 0, 0), (0, 1, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1)]),
        (0, 1, 0, [(0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 1), (1, 1, 0), (0, 1, 0)]),
        (0, -1, 0, [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 0), (1, 0, 1), (0, 0, 1)]),
    ]
    verts = []
    for nx, ny, nz, quadverts in faces:
        for vx, vy, vz in quadverts:
            verts += [vx - 0.5, vy - 0.5, vz - 0.5, nx, ny, nz]
    return np.array(verts, dtype=np.float32)


class VoxelRenderer:
    def __init__(self, ctx: moderngl.Context):
        self.ctx = ctx
        shader_dir = resource_path("shaders")

        vert_src = (shader_dir / "voxel.vert").read_text(encoding="utf-8")
        frag_src = (shader_dir / "voxel.frag").read_text(encoding="utf-8")
        self.prog = ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)

        line_vert = (shader_dir / "line.vert").read_text(encoding="utf-8")
        line_frag = (shader_dir / "line.frag").read_text(encoding="utf-8")
        self.line_prog = ctx.program(vertex_shader=line_vert, fragment_shader=line_frag)

        self.cube_vbo = ctx.buffer(_make_cube_vbo().tobytes())

        self.inst_pos_vbo = None
        self.inst_color_vbo = None
        self.inst_sel_vbo = None
        self.inst_bone_idx_vbo = None
        self.vao = None
        self.n_voxels = 0

        self.line_vbo = None
        self.line_vao = None
        self.n_lines = 0
        self.stick_segments = []

        self.point_vbo = None
        self.point_vao = None
        self.n_points = 0

        self.grid_vbo = None
        self.grid_vao = None
        self.n_grid_vertices = 0
        self.mirror_vbo = None
        self.mirror_vao = None
        self.n_mirror_vertices = 0
        self.mirror_point_vbo = None
        self.mirror_point_vao = None
        self.n_mirror_points = 0

        self.show_voxels = True
        self.show_skeleton = True
        self.highlight_stick_idx = -1
        self.highlight_particle_idx = -1          # 悬停粒子
        self.highlight_active_particle_idx = -1   # active 粒子（青色，独立于悬停）
        self.highlight_selected_particle_indices = []  # list[int]，已选非 active
        self.show_grid = True
        self.show_mirror_plane = False
        self.show_mirror_handles = False
        # 5b：长度违规 stick 索引列表，驱动红色额外 draw call
        self.violation_stick_indices = []
        # P2：锁定粒子索引列表，渲染为灰蓝色（P5a：locked 覆盖 selected）
        self.locked_particle_indices: list = []
        # 原点坐标轴 Gizmo（任务4）
        self.origin_vbo = None
        self.origin_vao = None
        self.n_origin_vertices = 0
        self.show_origin_gizmo = False

        # 选区 gizmo（动画工具，bone_edit + 选中粒子时显示）
        self.gizmo_vbo = None
        self.gizmo_vao = None
        self.gizmo_n_vertices = 0
        # hit test 缓存：prepare 时填，pick 时读
        self.gizmo_pivot = None                # np.ndarray(3,) 或 None
        self.gizmo_handle_endpoints = {}       # {handle_name: (start_w, end_w)}
        self.gizmo_ring_data = {}              # {handle_name: (center_w, axis_letter, radius_w)}
        self.gizmo_arrow_world_length = 0.0

    def upload_voxels(self, positions, colors, selected, bone_indices):
        n = len(positions)
        self.n_voxels = n
        if n == 0:
            return

        pos_bytes = positions.astype(np.float32).tobytes()
        col_bytes = colors.astype(np.float32).tobytes()
        sel_bytes = selected.astype(np.float32).tobytes()
        bidx_bytes = bone_indices.astype(np.float32).tobytes()

        if self.inst_pos_vbo is None or self.inst_pos_vbo.size != len(pos_bytes):
            if self.inst_pos_vbo:
                self.inst_pos_vbo.release()
            if self.inst_color_vbo:
                self.inst_color_vbo.release()
            if self.inst_sel_vbo:
                self.inst_sel_vbo.release()
            if self.inst_bone_idx_vbo:
                self.inst_bone_idx_vbo.release()
            self.inst_pos_vbo = self.ctx.buffer(pos_bytes, dynamic=True)
            self.inst_color_vbo = self.ctx.buffer(col_bytes, dynamic=True)
            self.inst_sel_vbo = self.ctx.buffer(sel_bytes, dynamic=True)
            self.inst_bone_idx_vbo = self.ctx.buffer(bidx_bytes, dynamic=True)
            self._rebuild_vao()
        else:
            self.inst_pos_vbo.write(pos_bytes)
            self.inst_color_vbo.write(col_bytes)
            self.inst_sel_vbo.write(sel_bytes)
            self.inst_bone_idx_vbo.write(bidx_bytes)

    def _rebuild_vao(self):
        if self.vao:
            self.vao.release()
        self.vao = self.ctx.vertex_array(
            self.prog,
            [
                (self.cube_vbo, "3f 3f", "in_vert", "in_normal"),
                (self.inst_pos_vbo, "3f/i", "i_pos"),
                (self.inst_color_vbo, "4f/i", "i_color"),
                (self.inst_sel_vbo, "1f/i", "i_selected"),
                # 1 float = 骨段槽位下标（slot 0 是 identity 哨位）
                (self.inst_bone_idx_vbo, "1f/i", "i_bone_idx"),
            ],
        )

    def update_colors(self, colors, selected):
        if self.inst_color_vbo is None:
            return
        self.inst_color_vbo.write(colors.astype(np.float32).tobytes())
        self.inst_sel_vbo.write(selected.astype(np.float32).tobytes())

    def update_voxel_positions(self, positions):
        """仅更新位置 VBO，不重建颜色/selection。动画蒙皮专用快速路径。"""
        if self.inst_pos_vbo is None or len(positions) != self.n_voxels:
            return
        self.inst_pos_vbo.write(positions.astype(np.float32).tobytes())

    def update_voxel_bone_indices(self, bone_indices):
        """更新 per-voxel bone idx VBO（bindings 变化后调用）。"""
        if self.inst_bone_idx_vbo is None or len(bone_indices) != self.n_voxels:
            return
        self.inst_bone_idx_vbo.write(bone_indices.astype(np.float32).tobytes())

    def update_bone_orientations(self, bone_orientations):
        """上传 per-bone orientation uniform 数组（每帧动画蒙皮后调用，~8 KB）。"""
        if "u_bone_orientations" not in self.prog:
            return
        self.prog["u_bone_orientations"].write(
            bone_orientations.astype(np.float32).tobytes()
        )

    def upload_skeleton_lines(self, particles, sticks, dummy_indices=None, skip_dummy=False):
        self.stick_segments = []

        if not particles:
            self.n_lines = 0
            self.n_points = 0
            return

        id_to_particle = {p["id"]: p for p in particles}

        _dummy = dummy_indices if dummy_indices is not None else set()
        line_verts = []
        vtx_offset = 0
        for stick in sticks:
            pa = id_to_particle.get(stick.particle_a_id)
            pb = id_to_particle.get(stick.particle_b_id)
            if pa is None or pb is None:
                self.stick_segments.append((vtx_offset, 0))
                continue
            is_dummy = stick.constraint_index in _dummy
            if skip_dummy and is_dummy:
                self.stick_segments.append((vtx_offset, 0))
                continue
            if is_dummy:
                r, g, b, a = 0.4, 0.4, 0.4, 0.35
            else:
                r, g, b, a = 1.0, 1.0, 1.0, 1.0
            line_verts += [pa["x"], pa["y"], pa["z"], r, g, b, a]
            line_verts += [pb["x"], pb["y"], pb["z"], r, g, b, a]
            self.stick_segments.append((vtx_offset, 2))
            vtx_offset += 2

        if self.line_vbo:
            self.line_vbo.release()
            self.line_vbo = None
        if self.line_vao:
            self.line_vao.release()
            self.line_vao = None

        if line_verts:
            line_arr = np.array(line_verts, dtype=np.float32)
            self.line_vbo = self.ctx.buffer(line_arr.tobytes())
            self.line_vao = self.ctx.vertex_array(
                self.line_prog,
                [(self.line_vbo, "3f 4f", "in_vert", "in_color")],
            )
            self.n_lines = len(line_verts) // 7
        else:
            self.n_lines = 0

        point_verts = []
        for particle in particles:
            point_verts += [
                particle["x"],
                particle["y"],
                particle["z"],
                1.0,
                1.0,
                1.0,
                1.0,
            ]

        if self.point_vbo:
            self.point_vbo.release()
            self.point_vbo = None
        if self.point_vao:
            self.point_vao.release()
            self.point_vao = None

        if point_verts:
            point_arr = np.array(point_verts, dtype=np.float32)
            self.point_vbo = self.ctx.buffer(point_arr.tobytes())
            self.point_vao = self.ctx.vertex_array(
                self.line_prog,
                [(self.point_vbo, "3f 4f", "in_vert", "in_color")],
            )
            self.n_points = len(point_verts) // 7
        else:
            self.n_points = 0

    def upload_grid(self, center, extent, step, major_every=4,
                    show_xz=True, show_xy=True, show_yz=True):
        if self.grid_vbo:
            self.grid_vbo.release()
            self.grid_vbo = None
        if self.grid_vao:
            self.grid_vao.release()
            self.grid_vao = None
        self.n_grid_vertices = 0

        step = float(step)
        if step <= 0.0:
            return

        major_every = max(1, int(major_every))
        half = max(step * 4.0, float(extent))
        min_x = np.floor((center[0] - half) / step) * step
        max_x = np.ceil((center[0] + half) / step) * step
        min_y = np.floor((center[1] - half) / step) * step
        max_y = np.ceil((center[1] + half) / step) * step
        min_z = np.floor((center[2] - half) / step) * step
        max_z = np.ceil((center[2] + half) / step) * step
        verts = []

        def add_segment(ax, ay, az, bx, by, bz, line_index):
            is_major = (line_index % major_every) == 0
            color = _GRID_MAJOR_COLOR if is_major else _GRID_MINOR_COLOR
            verts.extend([ax, ay, az, color[0], color[1], color[2], 1.0])
            verts.extend([bx, by, bz, color[0], color[1], color[2], 1.0])

        if show_xz:
            x = min_x
            xi = 0
            while x <= max_x + 1e-6:
                add_segment(x, center[1], min_z, x, center[1], max_z, xi)
                x += step
                xi += 1

            z = min_z
            zi = 0
            while z <= max_z + 1e-6:
                add_segment(min_x, center[1], z, max_x, center[1], z, zi)
                z += step
                zi += 1

        if show_xy:
            x = min_x
            xi = 0
            while x <= max_x + 1e-6:
                add_segment(x, min_y, center[2], x, max_y, center[2], xi)
                x += step
                xi += 1

            y = min_y
            yi = 0
            while y <= max_y + 1e-6:
                add_segment(min_x, y, center[2], max_x, y, center[2], yi)
                y += step
                yi += 1

        if show_yz:
            y = min_y
            yi = 0
            while y <= max_y + 1e-6:
                add_segment(center[0], y, min_z, center[0], y, max_z, yi)
                y += step
                yi += 1

            z = min_z
            zi = 0
            while z <= max_z + 1e-6:
                add_segment(center[0], min_y, z, center[0], max_y, z, zi)
                z += step
                zi += 1

        if not verts:
            return

        grid_arr = np.array(verts, dtype=np.float32)
        self.grid_vbo = self.ctx.buffer(grid_arr.tobytes())
        self.grid_vao = self.ctx.vertex_array(
            self.line_prog,
            [(self.grid_vbo, "3f 4f", "in_vert", "in_color")],
        )
        self.n_grid_vertices = len(verts) // 7

    def upload_origin_axes(self, length=8.0):
        """生成 RGB 三轴线段上传 GPU（XYZ → 红绿蓝）。"""
        if self.origin_vbo:
            self.origin_vbo.release()
            self.origin_vbo = None
        if self.origin_vao:
            self.origin_vao.release()
            self.origin_vao = None
        self.n_origin_vertices = 0

        L = float(length)
        verts = [
            0.0, 0.0, 0.0,  0.95, 0.30, 0.30, 1.0,   # X 轴起点
            L,   0.0, 0.0,  0.95, 0.30, 0.30, 1.0,   # X 轴终点（红）
            0.0, 0.0, 0.0,  0.30, 0.85, 0.30, 1.0,   # Y 轴起点
            0.0, L,   0.0,  0.30, 0.85, 0.30, 1.0,   # Y 轴终点（绿）
            0.0, 0.0, 0.0,  0.35, 0.45, 0.95, 1.0,   # Z 轴起点
            0.0, 0.0, L,    0.35, 0.45, 0.95, 1.0,   # Z 轴终点（蓝）
        ]
        arr = np.array(verts, dtype=np.float32)
        self.origin_vbo = self.ctx.buffer(arr.tobytes())
        self.origin_vao = self.ctx.vertex_array(
            self.line_prog,
            [(self.origin_vbo, "3f 4f", "in_vert", "in_color")],
        )
        self.n_origin_vertices = 6

    def upload_mirror_indicator(self, origin, normal, extent, show_handles=False, handle_len=None,
                                show_grid=False, grid_step=1.0):
        if self.mirror_vbo:
            self.mirror_vbo.release()
            self.mirror_vbo = None
        if self.mirror_vao:
            self.mirror_vao.release()
            self.mirror_vao = None
        if self.mirror_point_vbo:
            self.mirror_point_vbo.release()
            self.mirror_point_vbo = None
        if self.mirror_point_vao:
            self.mirror_point_vao.release()
            self.mirror_point_vao = None
        self.n_mirror_vertices = 0
        self.n_mirror_points = 0
        self.show_mirror_handles = bool(show_handles)

        normal = np.asarray(normal, dtype=np.float32)
        norm = float(np.linalg.norm(normal))
        if norm < 1e-6:
            return
        normal = normal / norm
        origin = np.asarray(origin, dtype=np.float32)
        size = max(float(extent) * 0.6, 4.0)

        ref = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        if abs(float(np.dot(ref, normal))) > 0.95:
            ref = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        tangent = np.cross(normal, ref)
        tangent_norm = float(np.linalg.norm(tangent))
        if tangent_norm < 1e-6:
            return
        tangent = tangent / tangent_norm
        bitangent = np.cross(normal, tangent)
        bitangent = bitangent / max(float(np.linalg.norm(bitangent)), 1e-6)

        c0 = origin + tangent * size + bitangent * size
        c1 = origin - tangent * size + bitangent * size
        c2 = origin - tangent * size - bitangent * size
        c3 = origin + tangent * size - bitangent * size
        normal_len = float(handle_len) if handle_len is not None else max(size * 0.35, 2.0)
        n0 = origin - normal * normal_len
        n1 = origin + normal * normal_len
        verts = []
        point_verts = []

        def add_line(a, b, color):
            verts.extend([a[0], a[1], a[2], color[0], color[1], color[2], 1.0])
            verts.extend([b[0], b[1], b[2], color[0], color[1], color[2], 1.0])

        if show_grid and grid_step > 0.0:
            span = max(size, float(grid_step) * 2.0)
            line_count = int(span / float(grid_step))
            for i in range(-line_count, line_count + 1):
                off = i * float(grid_step)
                color = _GRID_MAJOR_COLOR if (i % 4) == 0 else _GRID_MINOR_COLOR
                add_line(
                    origin + tangent * off - bitangent * span,
                    origin + tangent * off + bitangent * span,
                    color,
                )
                add_line(
                    origin + bitangent * off - tangent * span,
                    origin + bitangent * off + tangent * span,
                    color,
                )

        add_line(c0, c1, _MIRROR_PLANE_COLOR)
        add_line(c1, c2, _MIRROR_PLANE_COLOR)
        add_line(c2, c3, _MIRROR_PLANE_COLOR)
        add_line(c3, c0, _MIRROR_PLANE_COLOR)
        add_line(origin - tangent * size, origin + tangent * size, _MIRROR_PLANE_COLOR)
        add_line(origin - bitangent * size, origin + bitangent * size, _MIRROR_PLANE_COLOR)
        if show_handles:
            add_line(origin, n1, _MIRROR_NORMAL_COLOR)
            point_verts.extend([origin[0], origin[1], origin[2], *_MIRROR_ORIGIN_COLOR, 1.0])
            point_verts.extend([n1[0], n1[1], n1[2], *_MIRROR_ARROW_COLOR, 1.0])

        mirror_arr = np.array(verts, dtype=np.float32)
        self.mirror_vbo = self.ctx.buffer(mirror_arr.tobytes())
        self.mirror_vao = self.ctx.vertex_array(
            self.line_prog,
            [(self.mirror_vbo, "3f 4f", "in_vert", "in_color")],
        )
        self.n_mirror_vertices = len(verts) // 7
        if point_verts:
            point_arr = np.array(point_verts, dtype=np.float32)
            self.mirror_point_vbo = self.ctx.buffer(point_arr.tobytes())
            self.mirror_point_vao = self.ctx.vertex_array(
                self.line_prog,
                [(self.mirror_point_vbo, "3f 4f", "in_vert", "in_color")],
            )
            self.n_mirror_points = len(point_verts) // 7

    # ──────────────────────────────────────────────
    # 选区 gizmo（Blender 风格 3 轴箭头 + 圆环 + 中心球）
    # ──────────────────────────────────────────────

    def prepare_gizmo(self, pivot, mvp, screen_w, screen_h,
                      arrow_pixels=80, hover_handle=None):
        """根据 pivot + 当前 MVP 重建 gizmo 几何，做屏幕空间恒定缩放。

        每帧调用：cheap，~200 个顶点。同时缓存把手数据供 pick_gizmo_handle 使用。
        """
        if pivot is None:
            self.gizmo_pivot = None
            self.gizmo_n_vertices = 0
            return

        pivot_arr = np.asarray(pivot, dtype=np.float32)
        p2d_pivot = _project_world_to_screen(pivot_arr, mvp, screen_w, screen_h)
        if p2d_pivot is None:
            self.gizmo_pivot = None
            self.gizmo_n_vertices = 0
            return
        # 投影 3 个世界单位向量，取屏幕距离最大者作为 pixels-per-world。
        # 单一轴（如世界 X）在侧视图下会与视线平行、屏幕距离趋零，导致 arrow_length 爆炸；
        # 三轴里至少有一个垂直于视线，max 方案对所有视角稳定。
        pixels_per_world = 1e-3
        for tv in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
            p2d = _project_world_to_screen(
                pivot_arr + np.array(tv, dtype=np.float32),
                mvp, screen_w, screen_h,
            )
            if p2d is None:
                continue
            d = float(np.hypot(p2d[0] - p2d_pivot[0], p2d[1] - p2d_pivot[1]))
            if d > pixels_per_world:
                pixels_per_world = d
        arrow_world_length = float(arrow_pixels) / pixels_per_world

        axes = {
            "x": np.array([1.0, 0.0, 0.0], dtype=np.float32),
            "y": np.array([0.0, 1.0, 0.0], dtype=np.float32),
            "z": np.array([0.0, 0.0, 1.0], dtype=np.float32),
        }

        verts = []        # 每条 7f：x y z r g b a
        self.gizmo_handle_endpoints = {}
        self.gizmo_ring_data = {}

        # 箭头：杆 + 4 段头部短线（X 形）
        head_len = arrow_world_length * 0.18
        head_off = arrow_world_length * 0.10
        for axis_letter, axis_vec in axes.items():
            handle_name = f"{axis_letter}_arrow"
            color = (_GIZMO_HOVER_COLOR if hover_handle == handle_name
                     else _GIZMO_AXIS_COLORS[axis_letter])
            end = pivot_arr + axis_vec * arrow_world_length
            # 杆
            verts.extend([*pivot_arr, *color])
            verts.extend([*end, *color])
            # 头部 X：用另两轴方向做一对短线
            other = [axes[a] for a in "xyz" if a != axis_letter]
            for perp in other:
                base = end - axis_vec * head_len
                tip_a = base + perp * head_off
                tip_b = base - perp * head_off
                verts.extend([*tip_a, *color])
                verts.extend([*end, *color])
                verts.extend([*tip_b, *color])
                verts.extend([*end, *color])
            self.gizmo_handle_endpoints[handle_name] = (pivot_arr.copy(), end.copy())

        # 圆环：32 段折线（闭合）
        ring_radius = arrow_world_length * 0.85
        n_seg = 32
        for axis_letter, axis_vec in axes.items():
            handle_name = f"{axis_letter}_ring"
            color = (_GIZMO_HOVER_COLOR if hover_handle == handle_name
                     else _GIZMO_AXIS_COLORS[axis_letter])
            other = [axes[a] for a in "xyz" if a != axis_letter]
            u_basis, v_basis = other[0], other[1]
            prev_pt = None
            for i in range(n_seg + 1):
                ang = 2.0 * np.pi * i / n_seg
                pt = pivot_arr + (np.cos(ang) * u_basis + np.sin(ang) * v_basis) * ring_radius
                if prev_pt is not None:
                    verts.extend([*prev_pt, *color])
                    verts.extend([*pt, *color])
                prev_pt = pt
            self.gizmo_ring_data[handle_name] = (pivot_arr.copy(), axis_letter, ring_radius)

        # 中心：3 根十字短线
        center_size = arrow_world_length * 0.10
        center_color = (_GIZMO_HOVER_COLOR if hover_handle == "center"
                        else _GIZMO_CENTER_COLOR)
        for axis_vec in axes.values():
            verts.extend([*(pivot_arr - axis_vec * center_size), *center_color])
            verts.extend([*(pivot_arr + axis_vec * center_size), *center_color])

        arr = np.array(verts, dtype=np.float32)
        nbytes = arr.nbytes
        if self.gizmo_vbo is None or self.gizmo_vbo.size != nbytes:
            if self.gizmo_vbo:
                self.gizmo_vbo.release()
            if self.gizmo_vao:
                self.gizmo_vao.release()
            self.gizmo_vbo = self.ctx.buffer(arr.tobytes(), dynamic=True)
            self.gizmo_vao = self.ctx.vertex_array(
                self.line_prog,
                [(self.gizmo_vbo, "3f 4f", "in_vert", "in_color")],
            )
        else:
            self.gizmo_vbo.write(arr.tobytes())

        self.gizmo_n_vertices = len(arr) // 7
        self.gizmo_pivot = pivot_arr.copy()
        self.gizmo_arrow_world_length = arrow_world_length

    def draw_gizmo(self, mvp):
        """画 gizmo（深度测试关，画在最上层）。"""
        if self.gizmo_vao is None or self.gizmo_n_vertices == 0:
            return
        mvp_bytes = mvp.astype(np.float32).T.tobytes()
        self.line_prog["u_mvp"].write(mvp_bytes)
        self.line_prog["u_color_mult"].value = (1.0, 1.0, 1.0, 1.0)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
        self.ctx.disable(moderngl.DEPTH_TEST)
        self.ctx.line_width = 2.5
        self.gizmo_vao.render(moderngl.LINES, vertices=self.gizmo_n_vertices)
        self.ctx.line_width = 1.0
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.BLEND)

    def pick_gizmo_handle(self, mouse_x, mouse_y, mvp, screen_w, screen_h):
        """屏幕空间命中测试，返回 'x_arrow' / 'y_ring' / 'center' 等或 None。"""
        if self.gizmo_pivot is None:
            return None

        pivot_2d = _project_world_to_screen(self.gizmo_pivot, mvp, screen_w, screen_h)
        if pivot_2d is None:
            return None

        candidates = []  # (priority, dist, name)；priority 数字小者优先

        # 中心：单独阈值，最高优先级（优先级 0）
        center_d = float(np.hypot(mouse_x - pivot_2d[0], mouse_y - pivot_2d[1]))
        if center_d < _GIZMO_CENTER_HIT_PX:
            candidates.append((0, center_d, "center"))

        # 箭头：到屏幕空间线段的距离
        for name, (start_w, end_w) in self.gizmo_handle_endpoints.items():
            s2d = _project_world_to_screen(start_w, mvp, screen_w, screen_h)
            e2d = _project_world_to_screen(end_w, mvp, screen_w, screen_h)
            if s2d is None or e2d is None:
                continue
            d = _point_to_segment_dist_2d(mouse_x, mouse_y, s2d[0], s2d[1], e2d[0], e2d[1])
            if d < _GIZMO_HIT_THRESHOLD_PX:
                # 箭头优先级 1（高于圆环，低于中心）
                candidates.append((1, d, name))

        # 圆环：采样 24 点找最近距离
        axes = {
            "x": np.array([1.0, 0.0, 0.0], dtype=np.float32),
            "y": np.array([0.0, 1.0, 0.0], dtype=np.float32),
            "z": np.array([0.0, 0.0, 1.0], dtype=np.float32),
        }
        for name, (ctr_w, axis_letter, radius) in self.gizmo_ring_data.items():
            other = [axes[a] for a in "xyz" if a != axis_letter]
            u_basis, v_basis = other[0], other[1]
            min_d = float("inf")
            for i in range(24):
                ang = 2.0 * np.pi * i / 24
                pt = ctr_w + (np.cos(ang) * u_basis + np.sin(ang) * v_basis) * radius
                p2d = _project_world_to_screen(pt, mvp, screen_w, screen_h)
                if p2d is None:
                    continue
                d = float(np.hypot(mouse_x - p2d[0], mouse_y - p2d[1]))
                if d < min_d:
                    min_d = d
            if min_d < _GIZMO_HIT_THRESHOLD_PX:
                candidates.append((2, min_d, name))

        if not candidates:
            return None
        candidates.sort(key=lambda c: (c[0], c[1]))
        return candidates[0][2]

    def render(self, mvp):
        mvp_bytes = mvp.astype(np.float32).T.tobytes()
        if self.show_voxels and self.vao is not None and self.n_voxels > 0:
            self.prog["u_mvp"].write(mvp_bytes)
            self.prog["u_light_dir"].value = (0.6, 1.0, 0.4)

        if self.show_grid and self.n_grid_vertices > 0 and self.grid_vao:
            self.line_prog["u_mvp"].write(mvp_bytes)
            self.ctx.enable(moderngl.BLEND)
            self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
            self.ctx.disable(moderngl.DEPTH_TEST)
            self.ctx.line_width = 1.0
            self.line_prog["u_color_mult"].value = (1.0, 1.0, 1.0, 0.55)
            self.grid_vao.render(moderngl.LINES, vertices=self.n_grid_vertices)
            self.line_prog["u_color_mult"].value = (1.0, 1.0, 1.0, 1.0)
            self.ctx.disable(moderngl.BLEND)
            self.ctx.enable(moderngl.DEPTH_TEST)

        if self.show_origin_gizmo and self.n_origin_vertices > 0 and self.origin_vao:
            self.line_prog["u_mvp"].write(mvp_bytes)
            self.ctx.enable(moderngl.DEPTH_TEST)
            self.ctx.line_width = 3.0
            self.line_prog["u_color_mult"].value = (1.0, 1.0, 1.0, 1.0)
            self.origin_vao.render(moderngl.LINES, vertices=self.n_origin_vertices)
            self.ctx.line_width = 1.0

        if self.show_voxels and self.vao is not None and self.n_voxels > 0:
            self.ctx.enable(moderngl.DEPTH_TEST)
            self.ctx.disable(moderngl.CULL_FACE)
            self.ctx.disable(moderngl.BLEND)
            self.vao.render(moderngl.TRIANGLES, instances=self.n_voxels)

        if self.show_skeleton and self.n_lines > 0 and self.line_vao:
            self.line_prog["u_mvp"].write(mvp_bytes)
            self.ctx.enable(moderngl.BLEND)
            self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
            self.ctx.line_width = _LINE_WIDTH

            self.line_prog["u_color_mult"].value = (1.0, 1.0, 1.0, _LINE_ALPHA_OCCLUDED)
            self.ctx.disable(moderngl.DEPTH_TEST)
            self.line_vao.render(moderngl.LINES, vertices=self.n_lines)

            self.line_prog["u_color_mult"].value = (1.0, 1.0, 1.0, _LINE_ALPHA_VISIBLE)
            self.ctx.enable(moderngl.DEPTH_TEST)
            self.line_vao.render(moderngl.LINES, vertices=self.n_lines)

            if 0 <= self.highlight_stick_idx < len(self.stick_segments):
                off, cnt = self.stick_segments[self.highlight_stick_idx]
                if cnt > 0:
                    hr, hg, hb = _HIGHLIGHT_COLOR
                    self.line_prog["u_color_mult"].value = (hr, hg, hb, 1.0)
                    self.ctx.disable(moderngl.DEPTH_TEST)
                    self.ctx.line_width = _LINE_WIDTH_HIGHLIGHT
                    self.line_vao.render(moderngl.LINES, vertices=cnt, first=off)
                    self.ctx.line_width = _LINE_WIDTH

            # 5b：长度违规 stick 红色覆盖
            if self.violation_stick_indices and self.stick_segments:
                self.line_prog["u_color_mult"].value = (1.0, 0.25, 0.25, 1.0)
                self.ctx.disable(moderngl.DEPTH_TEST)
                self.ctx.line_width = _LINE_WIDTH_HIGHLIGHT
                for vi in self.violation_stick_indices:
                    if 0 <= vi < len(self.stick_segments):
                        off, cnt = self.stick_segments[vi]
                        if cnt > 0:
                            self.line_vao.render(moderngl.LINES, vertices=cnt, first=off)
                self.ctx.line_width = _LINE_WIDTH

            self.line_prog["u_color_mult"].value = (1.0, 1.0, 1.0, 1.0)
            self.ctx.disable(moderngl.BLEND)
            self.ctx.enable(moderngl.DEPTH_TEST)

        if self.show_mirror_plane and self.n_mirror_vertices > 0 and self.mirror_vao:
            self.line_prog["u_mvp"].write(mvp_bytes)
            self.ctx.enable(moderngl.BLEND)
            self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
            self.ctx.disable(moderngl.DEPTH_TEST)
            self.ctx.line_width = 2.0 if not self.show_mirror_handles else 2.5
            self.line_prog["u_color_mult"].value = (1.0, 1.0, 1.0, 0.55 if not self.show_mirror_handles else 0.9)
            self.mirror_vao.render(moderngl.LINES, vertices=self.n_mirror_vertices)
            self.line_prog["u_color_mult"].value = (1.0, 1.0, 1.0, 1.0)
            if self.show_mirror_handles and self.n_mirror_points > 0 and self.mirror_point_vao:
                self.ctx.point_size = _MIRROR_HANDLE_SIZE
                self.mirror_point_vao.render(moderngl.POINTS, vertices=1, first=0)
                self.ctx.point_size = _MIRROR_ARROW_SIZE
                self.mirror_point_vao.render(moderngl.POINTS, vertices=1, first=1)
            self.ctx.disable(moderngl.BLEND)
            self.ctx.enable(moderngl.DEPTH_TEST)

        if self.show_skeleton and self.n_points > 0 and self.point_vao:
            self.line_prog["u_mvp"].write(mvp_bytes)
            self.ctx.enable(moderngl.BLEND)
            self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
            self.ctx.disable(moderngl.DEPTH_TEST)

            # 1) 全量默认色
            self.ctx.point_size = _PARTICLE_SIZE
            self.line_prog["u_color_mult"].value = (
                _PARTICLE_COLOR[0],
                _PARTICLE_COLOR[1],
                _PARTICLE_COLOR[2],
                0.95,
            )
            self.point_vao.render(moderngl.POINTS, vertices=self.n_points)

            # 2) selected 次亮（淡黄，不含 active）
            if self.highlight_selected_particle_indices:
                self.ctx.point_size = _PARTICLE_SIZE_SELECTED
                self.line_prog["u_color_mult"].value = _PARTICLE_SELECTED_COLOR
                for idx in self.highlight_selected_particle_indices:
                    if 0 <= idx < self.n_points:
                        self.point_vao.render(moderngl.POINTS, vertices=1, first=idx)

            # 3) locked 粒子（灰蓝，P5a：覆盖 selected 色，但被 active 覆盖）
            if self.locked_particle_indices:
                self.ctx.point_size = _PARTICLE_SIZE_SELECTED
                self.line_prog["u_color_mult"].value = _PARTICLE_LOCKED_COLOR
                for idx in self.locked_particle_indices:
                    if 0 <= idx < self.n_points:
                        self.point_vao.render(moderngl.POINTS, vertices=1, first=idx)

            # 4) active 粒子（青色，与已选淡黄明显区分）
            if 0 <= self.highlight_active_particle_idx < self.n_points:
                self.ctx.point_size = _PARTICLE_SIZE_ACTIVE
                self.line_prog["u_color_mult"].value = _PARTICLE_ACTIVE_COLOR
                self.point_vao.render(
                    moderngl.POINTS, vertices=1, first=self.highlight_active_particle_idx
                )

            # 5) 悬停粒子（亮黄，覆盖 active 色提供额外反馈）
            if 0 <= self.highlight_particle_idx < self.n_points:
                self.ctx.point_size = _PARTICLE_SIZE_HIGHLIGHT
                self.line_prog["u_color_mult"].value = (1.0, 1.0, 0.25, 1.0)
                self.point_vao.render(moderngl.POINTS, vertices=1, first=self.highlight_particle_idx)
                
            self.ctx.disable(moderngl.BLEND)
            self.ctx.enable(moderngl.DEPTH_TEST)

    def release(self):
        for obj in [
            self.cube_vbo,
            self.inst_pos_vbo,
            self.inst_color_vbo,
            self.inst_sel_vbo,
            self.vao,
            self.line_vbo,
            self.line_vao,
            self.point_vbo,
            self.point_vao,
            self.grid_vbo,
            self.grid_vao,
            self.origin_vbo,
            self.origin_vao,
            self.mirror_vbo,
            self.mirror_vao,
            self.mirror_point_vbo,
            self.mirror_point_vao,
            self.prog,
            self.line_prog,
        ]:
            if obj:
                obj.release()


def pick_voxel(ray_origin, ray_dir, positions, radius=0.5):
    if len(positions) == 0:
        return -1

    ro = np.asarray(ray_origin, dtype=np.float32)
    rd = np.asarray(ray_dir, dtype=np.float32)

    rel = positions - ro
    dot = rel @ rd
    proj = np.outer(dot, rd)
    perp2 = np.einsum("ij,ij->i", rel - proj, rel - proj)
    cull_r = np.float32(radius * 2.5)
    mask = (dot > np.float32(-radius)) & (perp2 < cull_r * cull_r)
    indices = np.where(mask)[0]
    if len(indices) == 0:
        return -1

    sub = positions[indices]
    safe = np.where(np.abs(rd) > np.float32(1e-6), rd, np.float32(1e-6))
    inv = np.float32(1.0) / safe

    r = np.float32(radius)
    t1 = (sub - r - ro) * inv
    t2 = (sub + r - ro) * inv
    tmin = np.max(np.minimum(t1, t2), axis=1)
    tmax = np.min(np.maximum(t1, t2), axis=1)

    inf = np.float32(1e18)
    hit_mask = (tmax >= tmin) & (tmax > np.float32(0))
    tmin_clipped = np.where(hit_mask, np.where(tmin > np.float32(0), tmin, np.float32(0)), inf)
    best_local = int(np.argmin(tmin_clipped))
    if tmin_clipped[best_local] >= inf * np.float32(0.5):
        return -1
    return int(indices[best_local])


def box_select_voxels(
    vp_matrix: np.ndarray, positions: np.ndarray,
    box_x0: float, box_y0: float, box_x1: float, box_y1: float,
    screen_w: int, screen_h: int,
) -> list[int]:
    if len(positions) == 0:
        return []

    n = len(positions)
    ones = np.ones((n, 1), dtype=np.float32)
    pos_h = np.hstack([positions, ones])
    clip = (vp_matrix @ pos_h.T).T
    w = clip[:, 3:4]
    w = np.where(np.abs(w) < 1e-6, 1e-6, w)
    ndc = clip[:, :3] / w

    sx = (ndc[:, 0] + 1.0) * 0.5 * screen_w
    sy = (1.0 - ndc[:, 1]) * 0.5 * screen_h
    x0, x1 = min(box_x0, box_x1), max(box_x0, box_x1)
    y0, y1 = min(box_y0, box_y1), max(box_y0, box_y1)

    in_box = (
        (sx >= x0)
        & (sx <= x1)
        & (sy >= y0)
        & (sy <= y1)
        & (w[:, 0] > 0)
        & (ndc[:, 2] > -1.0)
        & (ndc[:, 2] < 1.0)
    )
    return list(np.where(in_box)[0])


def pick_particle_screen(
    vp_matrix: np.ndarray, positions: np.ndarray,
    screen_x: float, screen_y: float,
    screen_w: int, screen_h: int,
    radius_px: float = 14.0,
) -> int:
    if len(positions) == 0:
        return -1

    n = len(positions)
    ones = np.ones((n, 1), dtype=np.float32)
    pos_h = np.hstack([positions, ones])
    clip = (vp_matrix @ pos_h.T).T
    w = clip[:, 3:4]
    w = np.where(np.abs(w) < 1e-6, 1e-6, w)
    ndc = clip[:, :3] / w

    valid = (w[:, 0] > 0) & (ndc[:, 2] > -1.0) & (ndc[:, 2] < 1.0)
    if not np.any(valid):
        return -1

    sx = (ndc[:, 0] + 1.0) * 0.5 * screen_w
    sy = (1.0 - ndc[:, 1]) * 0.5 * screen_h
    dist2 = (sx - screen_x) ** 2 + (sy - screen_y) ** 2
    dist2 = np.where(valid, dist2, np.float32(1e18))

    best = int(np.argmin(dist2))
    if float(dist2[best]) > float(radius_px * radius_px):
        return -1
    return best

def pick_stick_screen(
    vp_matrix: np.ndarray,
    particles: list,
    sticks: list,
    screen_x: float, screen_y: float,
    screen_w: int, screen_h: int,
    threshold_px: float = 5.0,
) -> int:
    """点击拾取 stick：把每根 stick 的两端粒子投影到屏幕，求点-线段最短距离。

    返回距离最近且 < threshold_px 的 stick 数组下标；都不命中返回 -1。
    任一端点投影越界（NDC z 出界 / w<=0）的 stick 视为不可拾取。
    阈值偏小是有意：避免误中刚生成的 chain stick，让"点空白清选择"语义稳定。
    """
    if not sticks or not particles:
        return -1

    id_to_idx = {int(p["id"]): i for i, p in enumerate(particles)}
    pos = np.array([(p["x"], p["y"], p["z"]) for p in particles], dtype=np.float32)
    n = len(pos)
    if n == 0:
        return -1

    ones = np.ones((n, 1), dtype=np.float32)
    pos_h = np.hstack([pos, ones])
    clip = (vp_matrix @ pos_h.T).T
    w = clip[:, 3]
    w_safe = np.where(np.abs(w) < 1e-6, 1e-6, w)
    ndc = clip[:, :3] / w_safe[:, None]
    sx = (ndc[:, 0] + 1.0) * 0.5 * screen_w
    sy = (1.0 - ndc[:, 1]) * 0.5 * screen_h
    valid = (w > 0) & (ndc[:, 2] > -1.0) & (ndc[:, 2] < 1.0)

    best_idx = -1
    best_dist2 = float(threshold_px * threshold_px)
    px = float(screen_x)
    py = float(screen_y)
    for ci, stick in enumerate(sticks):
        a_idx = id_to_idx.get(int(stick.particle_a_id), -1)
        b_idx = id_to_idx.get(int(stick.particle_b_id), -1)
        if a_idx < 0 or b_idx < 0:
            continue
        if not (valid[a_idx] and valid[b_idx]):
            continue
        ax, ay = float(sx[a_idx]), float(sy[a_idx])
        bx, by = float(sx[b_idx]), float(sy[b_idx])
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        if seg_len2 < 1e-6:
            d2 = (px - ax) ** 2 + (py - ay) ** 2
        else:
            t = ((px - ax) * dx + (py - ay) * dy) / seg_len2
            t = max(0.0, min(1.0, t))
            cx = ax + dx * t
            cy = ay + dy * t
            d2 = (px - cx) ** 2 + (py - cy) ** 2
        if d2 < best_dist2:
            best_dist2 = d2
            best_idx = ci
    return best_idx


def box_select_particles(
    vp_matrix: np.ndarray, positions: np.ndarray,
    box_x0: float, box_y0: float, box_x1: float, box_y1: float,
    screen_w: int, screen_h: int,
) -> list[int]:
    """
    Particle 版框选。算法和 box_select_voxels 一致：NDC → 屏幕坐标 → 盒内筛选。
    返回 particle 的 index 列表。
    """
    if len(positions) == 0:
        return []

    n = len(positions)
    ones = np.ones((n, 1), dtype=np.float32)
    pos_h = np.hstack([positions, ones])
    clip = (vp_matrix @ pos_h.T).T
    w = clip[:, 3:4]
    w = np.where(np.abs(w) < 1e-6, 1e-6, w)
    ndc = clip[:, :3] / w

    sx = (ndc[:, 0] + 1.0) * 0.5 * screen_w
    sy = (1.0 - ndc[:, 1]) * 0.5 * screen_h
    x0, x1 = min(box_x0, box_x1), max(box_x0, box_x1)
    y0, y1 = min(box_y0, box_y1), max(box_y0, box_y1)

    in_box = (
        (sx >= x0) & (sx <= x1)
        & (sy >= y0) & (sy <= y1)
        & (w[:, 0] > 0)
        & (ndc[:, 2] > -1.0) & (ndc[:, 2] < 1.0)
    )
    return list(np.where(in_box)[0])
