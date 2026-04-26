"""
camera.py
轨道相机:右键旋转、滚轮缩放、中键平移
支持透视/正交投影切换,四视图快速切换

v2.4 变更:
  - 修复中键平移左右反(L63 符号错误,根因见下方注释)
  - 新增 is_ortho 正交投影开关 + ortho_size 参数
  - 新增 set_view_preset("front"|"side"|"top"|"perspective")
  - 正交模式下 get_ray 返回平行射线(方向恒为相机 forward)
"""
import math
import numpy as np


class OrbitCamera:
    """轨道相机，支持透视/正交投影切换和四视图快速切换。

    输入约定：右键拖动旋转，中键拖动平移，滚轮缩放。
    is_ortho=True 时切换为正交投影，get_ray 返回平行射线（方向恒为相机 forward）。
    set_view_preset 二次点击同一按钮会翻到反面视角（前↔后、侧↔反侧、顶↔底）；
    任何右键/中键/滚轮操作后重置翻面计数器，下次点击从正面开始。
    """
    def __init__(self, width, height):
        self.width = width
        self.height = height

        # 轨道参数
        self.azimuth = 45.0    # 水平角(度)
        self.elevation = 25.0  # 垂直角(度)
        self.distance = 120.0  # 距离目标点
        self.target = np.array([0.0, 25.0, 0.0], dtype=np.float64)

        # 投影:是否正交
        self.is_ortho = False
        # 正交"高度"(世界单位半高),缩放时同时调 distance 和 ortho_size 保持一致体验
        self.ortho_size = 40.0

        # 鼠标状态(由主循环更新)
        self._last_mouse = None
        self._rotating = False
        self._panning = False
        self.invert_y = False
        self._last_view_button = None
        self._last_view_flipped = False

        self._dirty = True

    def _reset_view_button_cycle(self):
        self._last_view_button = None
        self._last_view_flipped = False

    def _view_up(self):
        if self.elevation >= 89.999:
            return np.array([0.0, 0.0, -1.0], dtype=np.float32)
        if self.elevation <= -89.999:
            return np.array([0.0, 0.0, 1.0], dtype=np.float32)
        return np.array([0.0, 1.0, 0.0], dtype=np.float32)

    def resize(self, w, h):
        self.width = w
        self.height = h
        self._dirty = True

    # ── 输入处理 ──────────────────────────────

    def on_mouse_button(self, button, action, mods, xpos, ypos):
        """button: 0=左 1=右 2=中; action: 1=按下 0=松开"""
        if button == 1:  # 右键旋转
            self._rotating = (action == 1)
        if button == 2:  # 中键平移
            self._panning = (action == 1)
        if action == 1:
            if button in (1, 2):
                self._reset_view_button_cycle()
            self._last_mouse = (xpos, ypos)

    def on_mouse_move(self, xpos, ypos):
        if self._last_mouse is None:
            self._last_mouse = (xpos, ypos)
            return
        dx = xpos - self._last_mouse[0]
        dy = ypos - self._last_mouse[1]
        self._last_mouse = (xpos, ypos)
        orbit_dy = -dy if self.invert_y else dy

        if self._rotating:
            self.azimuth   -= dx * 0.4
            self.elevation -= orbit_dy * 0.4
            self.elevation  = max(-89.0, min(89.0, self.elevation))
            self._dirty = True

        if self._panning:
            # 注:_get_axes 里的 right 实际指向 "相机视角的左方"(因为 forward
            # 命名约定是 target→eye 方向,cross(forward, up) 得到反向 right),
            # 所以 pan 要 "target += right * dx" 才能让画面跟手。
            # 历史上这行是 "-=",导致左右反,已修正。
            right, up, _ = self._get_axes()
            if self.is_ortho:
                speed = self.ortho_size * 0.002
            else:
                speed = self.distance * 0.001
            self.target += right * dx * speed
            self.target += up    * dy * speed
            self._dirty = True

    def on_scroll(self, dy):
        self._reset_view_button_cycle()
        factor = 0.9 if dy > 0 else 1.1
        self.distance *= factor
        self.distance = max(5.0, min(2000.0, self.distance))
        # 正交下同步缩 ortho_size,保证缩放体验一致
        self.ortho_size *= factor
        self.ortho_size = max(2.0, min(800.0, self.ortho_size))
        self._dirty = True

    # ── 矩阵计算 ──────────────────────────────

    def _get_axes(self):
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        # 注意:这个方向向量是 target→eye(而非标准 look_at 的 eye→target),
        # 所以 cross(forward, up) 算出的 "right" 其实是视角空间的 左。
        # 本项目保留此约定,由调用方(pan 逻辑)负责方向修正。
        forward = np.array([
            math.cos(el) * math.sin(az),
            math.sin(el),
            math.cos(el) * math.cos(az),
        ])
        world_up = np.array([0.0, 1.0, 0.0])
        right = np.cross(forward, world_up)
        norm = np.linalg.norm(right)
        if norm < 1e-6:
            right = np.array([1.0, 0.0, 0.0])
        else:
            right /= norm
        up = np.cross(right, forward)
        return right, up, forward

    def get_position(self):
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        offset = np.array([
            math.cos(el) * math.sin(az),
            math.sin(el),
            math.cos(el) * math.cos(az),
        ]) * self.distance
        return self.target + offset

    def get_view_direction(self):
        pos = self.get_position()
        direction = self.target - pos
        norm = np.linalg.norm(direction)
        if norm < 1e-6:
            return np.array([0.0, 0.0, -1.0], dtype=np.float32)
        return (direction / norm).astype(np.float32)

    def get_view_matrix(self):
        pos = self.get_position()
        return look_at(pos, self.target, self._view_up())

    def get_proj_matrix(self, fov=45.0, near=0.5, far=5000.0):
        aspect = max(self.width, 1) / max(self.height, 1)
        if self.is_ortho:
            # 半高 = ortho_size,半宽 = ortho_size * aspect
            hh = self.ortho_size
            hw = self.ortho_size * aspect
            return orthographic(-hw, hw, -hh, hh, near, far)
        return perspective(math.radians(fov), aspect, near, far)

    def get_mvp(self):
        return self.get_proj_matrix() @ self.get_view_matrix()

    def reset_to_model(self, voxels):
        """根据模型包围盒自动对齐相机"""
        if not voxels:
            return
        xs = [v[0] for v in voxels]
        ys = [v[1] for v in voxels]
        zs = [v[2] for v in voxels]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        cz = (min(zs) + max(zs)) / 2
        span = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs))
        self.target = np.array([cx, cy, cz])
        self.distance = span * 1.8
        self.ortho_size = span * 0.6  # 让正交下初始视野约等于透视下画面
        self._reset_view_button_cycle()
        self._dirty = True

    def set_ortho_enabled(self, enabled):
        enabled = bool(enabled)
        if self.is_ortho != enabled:
            self.is_ortho = enabled
            self._reset_view_button_cycle()
            self._dirty = True

    def _apply_view_preset(self, preset):
        if preset == 'front':
            self.azimuth = 0.0
            self.elevation = 0.0
        elif preset == 'back':
            self.azimuth = 180.0
            self.elevation = 0.0
        elif preset == 'side':
            self.azimuth = 90.0
            self.elevation = 0.0
        elif preset == 'back_side':
            self.azimuth = -90.0
            self.elevation = 0.0
        elif preset == 'top':
            self.azimuth = 0.0
            self.elevation = 90.0
        elif preset == 'bottom':
            self.azimuth = 0.0
            self.elevation = -90.0
        elif preset == 'perspective':
            self.azimuth = 45.0
            self.elevation = 25.0

    def set_view_preset(self, preset):
        """
        切换到指定视图预设。不改变 target 和 distance/ortho_size,仅改 azimuth/elevation。
        对 front/side/top 按钮支持二次点击翻到反面。
        """
        opposite = {
            "front": "back",
            "side": "back_side",
            "top": "bottom",
        }
        if preset in opposite:
            if self._last_view_button == preset:
                self._last_view_flipped = not self._last_view_flipped
            else:
                self._last_view_button = preset
                self._last_view_flipped = False
            target_preset = opposite[preset] if self._last_view_flipped else preset
        else:
            self._last_view_button = preset
            self._last_view_flipped = False
            target_preset = preset

        self._apply_view_preset(target_preset)
        self._dirty = True

    # ── 屏幕坐标 → 射线(用于点选)────────────

    def get_ray(self, screen_x, screen_y):
        """
        返回世界空间射线 (origin, direction)
        screen_x/y: 屏幕像素坐标
        正交模式下所有射线方向都等于相机 forward,起点在远离物体的平面上。
        """
        ndc_x = (2.0 * screen_x / max(self.width, 1)) - 1.0
        ndc_y = 1.0 - (2.0 * screen_y / max(self.height, 1))

        if self.is_ortho:
            # 相机空间方向:恒为 -Z(look_at 约定视线沿 -Z)
            # 转到世界空间:用相机基向量
            cam_pos = self.get_position()
            view_dir = self.target - cam_pos
            n = np.linalg.norm(view_dir)
            if n > 1e-6:
                view_dir = view_dir / n
            else:
                view_dir = np.array([0.0, 0.0, -1.0])

            # 构造相机右/上方向(和 get_proj_matrix 的 aspect 对齐)
            aspect = max(self.width, 1) / max(self.height, 1)
            world_up = self._view_up()
            cam_right = np.cross(view_dir, world_up)
            nr = np.linalg.norm(cam_right)
            if nr > 1e-6:
                cam_right /= nr
            else:
                cam_right = np.array([1.0, 0.0, 0.0])
            cam_up = np.cross(cam_right, view_dir)

            # 起点:在 target 平面上,按 ndc 偏移后向相机后退一段,保证
            # 射线从物体前方射入
            offset = (cam_right * (ndc_x * self.ortho_size * aspect) +
                      cam_up    * (ndc_y * self.ortho_size))
            origin = self.target + offset - view_dir * 500.0  # 退到远处
            return origin.astype(np.float32), view_dir.astype(np.float32)

        # ── 透视原逻辑 ──
        proj = self.get_proj_matrix()
        view = self.get_view_matrix()
        inv_proj = np.linalg.inv(proj)
        inv_view = np.linalg.inv(view)

        ray_clip = np.array([ndc_x, ndc_y, -1.0, 1.0])
        ray_eye  = inv_proj @ ray_clip
        ray_eye  = np.array([ray_eye[0], ray_eye[1], -1.0, 0.0])
        ray_world = inv_view @ ray_eye
        direction = ray_world[:3]
        norm = np.linalg.norm(direction)
        if norm > 1e-6:
            direction /= norm

        origin = self.get_position()
        return origin, direction


# ── 数学工具函数 ──────────────────────────────

def look_at(eye, center, up):
    f = center - eye
    f /= np.linalg.norm(f)
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    m = np.eye(4, dtype=np.float64)
    m[0, :3] = r
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(r, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] =  np.dot(f, eye)
    return m.astype(np.float32)


def perspective(fov, aspect, near, far):
    f = 1.0 / math.tan(fov / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def orthographic(left, right, bottom, top, near, far):
    """标准 OpenGL 正交投影矩阵 (列主序下可用)"""
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = 2.0 / (right - left)
    m[1, 1] = 2.0 / (top - bottom)
    m[2, 2] = -2.0 / (far - near)
    m[0, 3] = -(right + left) / (right - left)
    m[1, 3] = -(top + bottom) / (top - bottom)
    m[2, 3] = -(far + near) / (far - near)
    m[3, 3] = 1.0
    return m
