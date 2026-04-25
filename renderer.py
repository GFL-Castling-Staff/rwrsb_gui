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
_GRID_MINOR_COLOR = (0.28, 0.31, 0.38)
_GRID_MAJOR_COLOR = (0.52, 0.56, 0.66)
_MIRROR_PLANE_COLOR = (0.25, 0.90, 0.95)
_MIRROR_NORMAL_COLOR = (0.20, 1.00, 0.55)
_MIRROR_ORIGIN_COLOR = (1.0, 0.95, 0.35)
_MIRROR_ARROW_COLOR = (0.35, 1.0, 0.70)
_MIRROR_HANDLE_SIZE = 14.0
_MIRROR_ARROW_SIZE = 18.0


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
        # 原点坐标轴 Gizmo（任务4）
        self.origin_vbo = None
        self.origin_vao = None
        self.n_origin_vertices = 0
        self.show_origin_gizmo = False

    def upload_voxels(self, positions, colors, selected):
        n = len(positions)
        self.n_voxels = n
        if n == 0:
            return

        pos_bytes = positions.astype(np.float32).tobytes()
        col_bytes = colors.astype(np.float32).tobytes()
        sel_bytes = selected.astype(np.float32).tobytes()

        if self.inst_pos_vbo is None or self.inst_pos_vbo.size != len(pos_bytes):
            if self.inst_pos_vbo:
                self.inst_pos_vbo.release()
            if self.inst_color_vbo:
                self.inst_color_vbo.release()
            if self.inst_sel_vbo:
                self.inst_sel_vbo.release()
            self.inst_pos_vbo = self.ctx.buffer(pos_bytes, dynamic=True)
            self.inst_color_vbo = self.ctx.buffer(col_bytes, dynamic=True)
            self.inst_sel_vbo = self.ctx.buffer(sel_bytes, dynamic=True)
            self._rebuild_vao()
        else:
            self.inst_pos_vbo.write(pos_bytes)
            self.inst_color_vbo.write(col_bytes)
            self.inst_sel_vbo.write(sel_bytes)

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

    def upload_skeleton_lines(self, particles, sticks):
        self.stick_segments = []

        if not particles:
            self.n_lines = 0
            self.n_points = 0
            return

        id_to_particle = {p["id"]: p for p in particles}

        line_verts = []
        vtx_offset = 0
        for stick in sticks:
            pa = id_to_particle.get(stick.particle_a_id)
            pb = id_to_particle.get(stick.particle_b_id)
            if pa is None or pb is None:
                self.stick_segments.append((vtx_offset, 0))
                continue
            line_verts += [pa["x"], pa["y"], pa["z"], 1.0, 1.0, 1.0, 1.0]
            line_verts += [pb["x"], pb["y"], pb["z"], 1.0, 1.0, 1.0, 1.0]
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

            # 3) active 粒子（青色，与已选淡黄明显区分）
            if 0 <= self.highlight_active_particle_idx < self.n_points:
                self.ctx.point_size = _PARTICLE_SIZE_ACTIVE
                self.line_prog["u_color_mult"].value = _PARTICLE_ACTIVE_COLOR
                self.point_vao.render(
                    moderngl.POINTS, vertices=1, first=self.highlight_active_particle_idx
                )

            # 4) 悬停粒子（亮黄，覆盖 active 色提供额外反馈）
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


def box_select_voxels(vp_matrix, positions, box_x0, box_y0, box_x1, box_y1, screen_w, screen_h):
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


def pick_particle_screen(vp_matrix, positions, screen_x, screen_y, screen_w, screen_h, radius_px=14.0):
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

def box_select_particles(vp_matrix, positions, box_x0, box_y0, box_x1, box_y1, screen_w, screen_h):
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
