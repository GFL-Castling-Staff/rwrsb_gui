"""
renderer.py
ModernGL instanced rendering for voxels + skeleton lines + picking
"""
import numpy as np
import moderngl
from pathlib import Path


# 单位立方体（每个面2个三角形，共12个三角形/36顶点）
def _make_cube_vbo():
    """返回 (vertices, normals) 每行 3+3 float"""
    faces = [
        # 法线          顶点（单位立方体中心在 0.5,0.5,0.5）
        ( 0, 0, 1, [(0,0,1),(1,0,1),(1,1,1),(0,0,1),(1,1,1),(0,1,1)]),  # +Z
        ( 0, 0,-1, [(1,0,0),(0,0,0),(0,1,0),(1,0,0),(0,1,0),(1,1,0)]),  # -Z
        ( 1, 0, 0, [(1,0,0),(1,0,1),(1,1,1),(1,0,0),(1,1,1),(1,1,0)]),  # +X
        (-1, 0, 0, [(0,0,1),(0,0,0),(0,1,0),(0,0,1),(0,1,0),(0,1,1)]),  # -X
        ( 0, 1, 0, [(0,1,1),(1,1,1),(1,1,0),(0,1,1),(1,1,0),(0,1,0)]),  # +Y
        ( 0,-1, 0, [(0,0,0),(1,0,0),(1,0,1),(0,0,0),(1,0,1),(0,0,1)]),  # -Y
    ]
    verts = []
    for nx, ny, nz, quadverts in faces:
        for vx, vy, vz in quadverts:
            # 中心偏移 -0.5，让体素以整数坐标为中心
            verts += [vx - 0.5, vy - 0.5, vz - 0.5, nx, ny, nz]
    return np.array(verts, dtype=np.float32)


class VoxelRenderer:
    def __init__(self, ctx: moderngl.Context):
        self.ctx = ctx
        self._shader_dir = Path(__file__).parent / 'shaders'

        # 读取 shader
        vert_src = (self._shader_dir / 'voxel.vert').read_text(encoding='utf-8')
        frag_src = (self._shader_dir / 'voxel.frag').read_text(encoding='utf-8')
        self.prog = ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)

        line_vert = (self._shader_dir / 'line.vert').read_text(encoding='utf-8')
        line_frag = (self._shader_dir / 'line.frag').read_text(encoding='utf-8')
        self.line_prog = ctx.program(vertex_shader=line_vert, fragment_shader=line_frag)

        # 单位立方体 VBO（静态，所有实例共享）
        cube_data = _make_cube_vbo()
        self.cube_vbo = ctx.buffer(cube_data.tobytes())

        # 实例 VBO（动态，每帧或脏时更新）
        self.inst_pos_vbo    = None   # (N,3) float32
        self.inst_color_vbo  = None   # (N,4) float32
        self.inst_sel_vbo    = None   # (N,1) float32
        self.vao             = None
        self.n_voxels        = 0

        # 骨骼连线 VAO
        self.line_vbo  = None
        self.line_vao  = None
        self.n_lines   = 0

        self.show_skeleton = True

    def upload_voxels(self, positions, colors, selected):
        """
        positions: (N,3) float32
        colors:    (N,4) float32
        selected:  (N,1) float32
        """
        n = len(positions)
        self.n_voxels = n
        if n == 0:
            return

        pos_bytes  = positions.astype(np.float32).tobytes()
        col_bytes  = colors.astype(np.float32).tobytes()
        sel_bytes  = selected.astype(np.float32).tobytes()

        # 重新创建或更新 buffer
        if self.inst_pos_vbo is None or self.inst_pos_vbo.size != len(pos_bytes):
            if self.inst_pos_vbo: self.inst_pos_vbo.release()
            if self.inst_color_vbo: self.inst_color_vbo.release()
            if self.inst_sel_vbo: self.inst_sel_vbo.release()
            self.inst_pos_vbo   = self.ctx.buffer(pos_bytes,  dynamic=True)
            self.inst_color_vbo = self.ctx.buffer(col_bytes,  dynamic=True)
            self.inst_sel_vbo   = self.ctx.buffer(sel_bytes,  dynamic=True)
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
                # 立方体顶点数据（per-vertex）
                (self.cube_vbo, '3f 3f', 'in_vert', 'in_normal'),
                # 实例数据（per-instance）
                (self.inst_pos_vbo,   '3f/i', 'i_pos'),
                (self.inst_color_vbo, '4f/i', 'i_color'),
                (self.inst_sel_vbo,   '1f/i', 'i_selected'),
            ]
        )

    def update_colors(self, colors, selected):
        """仅更新颜色/选中状态（坐标不变，更快）"""
        if self.inst_color_vbo is None:
            return
        self.inst_color_vbo.write(colors.astype(np.float32).tobytes())
        self.inst_sel_vbo.write(selected.astype(np.float32).tobytes())

    def upload_skeleton_lines(self, particles, sticks):
        """
        particles: list of particle dict  (来自 editor_state.particles)
        sticks:    list of StickEntry     (来自 editor_state.sticks)
        """
        if not particles or not sticks:
            self.n_lines = 0
            return

        # 建立 id → particle dict 的映射
        id_to_particle = {p['id']: p for p in particles}

        verts = []
        for stick in sticks:
            pa = id_to_particle.get(stick.particle_a_id)
            pb = id_to_particle.get(stick.particle_b_id)
            if pa is None or pb is None:
                continue
            # 连线颜色用白色
            verts += [pa['x'], pa['y'], pa['z'], 1.0, 1.0, 1.0,
                    pb['x'], pb['y'], pb['z'], 1.0, 1.0, 1.0]

    def render(self, mvp):
        if self.n_voxels == 0 or self.vao is None:
            return

        # GLSL 按列主序读取 mat4；NumPy 是行主序，需要转置后再 flatten
        mvp_bytes = mvp.astype(np.float32).T.tobytes()
        self.prog['u_mvp'].write(mvp_bytes)
        self.prog['u_light_dir'].value = (0.6, 1.0, 0.4)

        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.CULL_FACE)

        self.vao.render(moderngl.TRIANGLES, instances=self.n_voxels)

        # 骨骼连线
        if self.show_skeleton and self.n_lines > 0 and self.line_vao:
            self.line_prog['u_mvp'].write(mvp_bytes)
            self.ctx.line_width = 2.0
            self.line_vao.render(moderngl.LINES, vertices=self.n_lines)

    def release(self):
        for obj in [self.cube_vbo, self.inst_pos_vbo, self.inst_color_vbo,
                    self.inst_sel_vbo, self.vao, self.line_vbo, self.line_vao,
                    self.prog, self.line_prog]:
            if obj:
                obj.release()


# ── CPU 端体素拾取（射线-AABB）────────────────

def pick_voxel(ray_origin, ray_dir, positions, radius=0.5):
    """
    返回命中的最近体素 index，未命中返回 -1
    positions: (N,3) numpy float32 array
    radius: 体素半径（体素边长1 → 半边长0.5）
    """
    if len(positions) == 0:
        return -1

    ro = np.asarray(ray_origin, dtype=np.float32)
    rd = np.asarray(ray_dir,    dtype=np.float32)

    # ── 粗筛：轴线距离剔除 ──
    rel  = positions - ro                              # (N,3)  float32
    dot  = rel @ rd                                    # (N,)
    proj = np.outer(dot, rd)                           # (N,3)
    perp2 = np.einsum('ij,ij->i', rel - proj, rel - proj)  # (N,) 比 sum 快
    CULL_R = np.float32(radius * 2.5)
    mask = (dot > np.float32(-radius)) & (perp2 < CULL_R * CULL_R)
    indices = np.where(mask)[0]

    if len(indices) == 0:
        return -1

    sub = positions[indices]   # 已是 float32

    # ── 精确 AABB slab test（全 float32）──
    safe = np.where(np.abs(rd) > np.float32(1e-6), rd, np.float32(1e-6))
    inv  = np.float32(1.0) / safe                      # (3,)

    r = np.float32(radius)
    t1 = (sub - r - ro) * inv
    t2 = (sub + r - ro) * inv

    tmin = np.max(np.minimum(t1, t2), axis=1)
    tmax = np.min(np.maximum(t1, t2), axis=1)

    INF = np.float32(1e18)
    hit_mask     = (tmax >= tmin) & (tmax > np.float32(0))
    tmin_clipped = np.where(hit_mask,
                            np.where(tmin > np.float32(0), tmin, np.float32(0)),
                            INF)

    best_local = int(np.argmin(tmin_clipped))
    if tmin_clipped[best_local] >= INF * np.float32(0.5):
        return -1
    return int(indices[best_local])


def box_select_voxels(vp_matrix, positions, box_x0, box_y0, box_x1, box_y1,
                      screen_w, screen_h):
    """
    框选：将体素投影到屏幕，返回落在框内的 indices
    vp_matrix: (4,4) float32 view-projection
    """
    if len(positions) == 0:
        return []

    n = len(positions)
    ones = np.ones((n, 1), dtype=np.float32)
    pos_h = np.hstack([positions, ones])           # (N,4)
    clip = (vp_matrix @ pos_h.T).T                  # (N,4)

    # 透视除法
    w = clip[:, 3:4]
    w = np.where(np.abs(w) < 1e-6, 1e-6, w)
    ndc = clip[:, :3] / w                            # (N,3)

    sx = (ndc[:, 0] + 1.0) * 0.5 * screen_w
    sy = (1.0 - ndc[:, 1]) * 0.5 * screen_h

    x0, x1 = min(box_x0, box_x1), max(box_x0, box_x1)
    y0, y1 = min(box_y0, box_y1), max(box_y0, box_y1)

    in_box = (sx >= x0) & (sx <= x1) & (sy >= y0) & (sy <= y1) & (w[:, 0] > 0)
    return list(np.where(in_box)[0])
