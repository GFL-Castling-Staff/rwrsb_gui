"""
camera.py
轨道相机：右键旋转、滚轮缩放、中键平移
"""
import math
import numpy as np


class OrbitCamera:
    def __init__(self, width, height):
        self.width = width
        self.height = height

        # 轨道参数
        self.azimuth = 45.0    # 水平角（度）
        self.elevation = 25.0  # 垂直角（度）
        self.distance = 120.0  # 距离目标点
        self.target = np.array([0.0, 25.0, 0.0], dtype=np.float64)

        # 鼠标状态（由主循环更新）
        self._last_mouse = None
        self._rotating = False
        self._panning = False

        self._proj = None
        self._view = None
        self._dirty = True

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
            self._last_mouse = (xpos, ypos)

    def on_mouse_move(self, xpos, ypos):
        if self._last_mouse is None:
            self._last_mouse = (xpos, ypos)
            return
        dx = xpos - self._last_mouse[0]
        dy = ypos - self._last_mouse[1]
        self._last_mouse = (xpos, ypos)

        if self._rotating:
            self.azimuth   -= dx * 0.4
            self.elevation -= dy * 0.4
            self.elevation  = max(-89.0, min(89.0, self.elevation))
            self._dirty = True

        if self._panning:
            # 在相机平面内平移 target
            right, up, _ = self._get_axes()
            speed = self.distance * 0.001
            self.target -= right * dx * speed
            self.target += up   * dy * speed
            self._dirty = True

    def on_scroll(self, dy):
        self.distance *= (0.9 if dy > 0 else 1.1)
        self.distance = max(5.0, min(2000.0, self.distance))
        self._dirty = True

    # ── 矩阵计算 ──────────────────────────────

    def _get_axes(self):
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        # 相机位置方向
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

    def get_view_matrix(self):
        pos = self.get_position()
        return look_at(pos, self.target, np.array([0.0, 1.0, 0.0]))

    def get_proj_matrix(self, fov=45.0, near=0.5, far=5000.0):
        aspect = max(self.width, 1) / max(self.height, 1)
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
        self._dirty = True

    # ── 屏幕坐标 → 射线（用于点选）────────────

    def get_ray(self, screen_x, screen_y):
        """
        返回世界空间射线 (origin, direction)
        screen_x/y: 屏幕像素坐标
        """
        # NDC
        ndc_x = (2.0 * screen_x / self.width) - 1.0
        ndc_y = 1.0 - (2.0 * screen_y / self.height)

        proj = self.get_proj_matrix()
        view = self.get_view_matrix()

        # 逆投影
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
