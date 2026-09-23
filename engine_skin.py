"""
engine_skin.py
与游戏一致的士兵体素蒙皮（动画模式预览用）。

游戏的做法：
- 每根 stick 的坐标系按它在 XML 里的下标（0–16）查一张固定的表；参考方向取自
  固定粒子下标 1、2、3、4、5、8、9、10、11、12 组成的"身体参考系"，与粒子 id、
  名字无关——粒子和 stick 的顺序本身有语义。
- 原点是 stick 的 a 端粒子；缩放恒为 1，骨段拉长时体素跟着 a 端走、不被拉伸。
- 每个体素只属于一根 stick（刚性单骨），bind 姿态取模型 XML 里的骨架。
- 四元数运算沿用 OGRE 1.7：FromAxes 不正交化输入、结果不归一化，四元数可能非单位，
  于是体素会有轻度非刚性变形。这是游戏里真实存在的效果，这里照样复刻。

纯函数 + numpy，不依赖 imgui / ModernGL / EditorState。四元数统一写作 [w, x, y, z]。
"""
import re

import numpy as np

# 身体参考系会按下标访问到粒子 12
MIN_PARTICLES = 13
# 着色器里骨骼矩阵数组长度：binding 下标必须 < 17
MAX_GPU_STICKS = 17

# 体检分级阈值：按 vanilla 常用动画标定，正常姿势约 0.3% 的骨段帧会到"注意"，没有"异常"
SIGMA_WARN = 0.35        # FromAxes 输入最小奇异值低于此值：参考方向接近平行
SIGMA_BAD = 0.15
DISTORTION_WARN = 0.10   # 相对 bind 的拉伸/压扁超过 10%
DISTORTION_BAD = 0.30
# bind 往返误差 ‖M(q)·M(q⁻¹) − I‖：bind 四元数非单位时两者不抵消，
# 游戏里这段体素在 bind 姿态下就已错位（vanilla 为 0）。它是相对量，约等于 错位 / 体素到 a 端的距离，
# 看得出来与否取决于它——150 体素长的腿偏 4.5 体素（3%）几乎看不出，20 体素的手臂偏 4.5 体素就很明显
BIND_ERROR_WARN = 0.05
BIND_ERROR_BAD = 0.15
# bind 姿态下体素实际错位（体素单位）只当"看得见"的下限：相对误差再大，不到半个体素也看不出
BIND_DRIFT_WARN = 0.5
BIND_DRIFT_BAD = 2.0

# ── 游戏外观：点精灵尺寸与相机 ──
# 材质里点精灵按档位写死像素边长，距离衰减是关掉的：镜头拉近体素不会变大。
# (描边像素, 本体像素)
GAME_SPRITE_PRESETS = {
    "high": (4.2, 2.6),
    "low": (3.6, 2.4),
}
GAME_SPRITE_PX_MAX = 10.0        # 显卡上报的 Max Point Size
# 相机：scene.xml direction="-0.3 -1.7 1.0"（俯角 58.4°）、distance="36" 世界单位。
# 体素按 1/32 缩放，所以换算成编辑器的体素单位是 36 * 32。
GAME_CAMERA_DISTANCE = 36.0 * 32.0
GAME_CAMERA_ELEVATION_DEG = 58.4

# ── 整段播放的动画 ──
# 游戏有两个动画通道：通道 0 是整副骨架的基础动画，通道 1 是可选的上身层
# （只替换 bodyAreaHint == 2 的粒子，按粒子 8 对齐）。通道 1 为空时整段合成都跳过。
# 下面这些是以写死下标播到通道 0 的动作，游戏里不叠上身层；
# 上身层的动画下标要按"部位 / 槽位"去武器动画表里查，所以跟着武器变。
WHOLE_BODY_ANIMATIONS = {
    5: "throwing self over",
    6: "falling",
    7: "arriving ground",
    8: "jumping",
    9: "lifting up",
    17: "going prone",
    19: "leaving prone",
    22: "climbing ladder",
    23: "climbing ladder, still",
    25: "swimming still",
    26: "swimming forwards",
    38: "surrender",
    46: "dive",
    49: "stunned",
    65: "skydiving",
    66: "wounded, still",
    67: "wounded, moving forwards",
}
_WHOLE_BODY_NAMES = {v.lower(): v for v in WHOLE_BODY_ANIMATIONS.values()}


def whole_body_animation(index=None, name=None):
    """这个动画在游戏里是不是整段播（不叠上身层）？是则返回 vanilla 的名字，否则 None。

    有来源文件时按下标判定（引擎只认下标）；没有下标就退回按 vanilla 的注释名匹配。
    """
    if index is not None and index in WHOLE_BODY_ANIMATIONS:
        return WHOLE_BODY_ANIMATIONS[index]
    if index is None and name:
        # vanilla 有几个注释名带下标后缀（如 "skydiving, 65"），比对前去掉
        key = re.sub(r",\s*\d+\s*$", "", str(name).strip().lower())
        return _WHOLE_BODY_NAMES.get(key)
    return None


VANILLA_PARTICLE_NAMES = (
    "head", "neck", "rightshoulder", "leftshoulder", "rightelbow", "leftelbow",
    "righthand", "lefthand", "midspine", "righthip", "lefthip",
    "rightknee", "leftknee", "rightfoot", "leftfoot",
)

# 以下文案会显示在界面上；UI 字体的字形表不含箭头、数学符号，统一用 ASCII（->、>=）

# 引擎语义粒子：下标 -> (中文, English)
SEMANTIC_PARTICLES = {
    1: ("颈：胸廓向上参考（midspine -> 颈）", "neck: chest-up reference (midspine -> neck)"),
    2: ("右肩：肩线、右上臂参考", "right shoulder: shoulder line, right upper arm"),
    3: ("左肩：肩线、左上臂参考", "left shoulder: shoulder line, left upper arm"),
    4: ("右肘：右上臂方向（2 -> 4）", "right elbow: right upper arm direction (2 -> 4)"),
    5: ("左肘：左上臂方向（3 -> 5）", "left elbow: left upper arm direction (3 -> 5)"),
    8: ("midspine：骨盆/胸廓参考、上半身层对齐锚点", "midspine: pelvis/chest reference, upper-layer anchor"),
    9: ("右胯：胯线、右腿参考", "right hip: hip line, right leg"),
    10: ("左胯：胯线、左腿参考", "left hip: hip line, left leg"),
    11: ("右膝：右腿外摆判定（9 -> 11）", "right knee: right leg swing (9 -> 11)"),
    12: ("左膝：左腿外摆判定（10 -> 12）", "left knee: left leg swing (10 -> 12)"),
}

# stick 下标 -> (中文, English, 引用的粒子下标, 中文短标签, 英文短标签)
_LEG_R = ("右腿：胯线与骨盆法向按大腿外摆程度混合", "right leg: hip line / pelvis normal blended by thigh swing",
          (8, 9, 10, 11), "右腿·外摆混合", "R leg: swing blend")
_LEG_L = ("左腿：胯线与骨盆法向按大腿外摆程度混合", "left leg: hip line / pelvis normal blended by thigh swing",
          (8, 9, 10, 12), "左腿·外摆混合", "L leg: swing blend")
_PELVIS = ("骨盆法向", "pelvis normal", (8, 9, 10), "骨盆法向", "pelvis normal")
_CHEST = ("胸廓法向", "chest normal", (1, 2, 3, 8), "胸廓法向", "chest normal")
STICK_RULES = {
    0: _LEG_R,
    1: _LEG_R,
    2: ("胯横骨：骨盆法向（反向）", "hip bar: pelvis normal (negated)", (8, 9, 10),
        "骨盆法向（反）", "-pelvis normal"),
    3: _LEG_L,
    4: _LEG_L,
    5: _PELVIS,
    6: _CHEST,
    7: ("肩横骨：胸廓向上", "shoulder bar: chest up", (1, 8), "胸廓向上", "chest up"),
    8: _PELVIS,
    9: _CHEST,
    10: ("左上臂：朝向取自粒子 3 -> 5，不看本骨段端点",
         "left upper arm: orientation from particles 3 -> 5, not its own endpoints",
         (1, 2, 3, 5, 8), "左上臂·取自 3-5", "L upper arm: from 3-5"),
    11: ("左前臂：继承左上臂坐标系", "left forearm: inherits the left upper arm frame", (1, 2, 3, 5, 8),
         "继承左上臂", "inherits L upper arm"),
    12: ("右上臂：朝向取自粒子 2 -> 4，不看本骨段端点",
         "right upper arm: orientation from particles 2 -> 4, not its own endpoints",
         (1, 2, 3, 4, 8), "右上臂·取自 2-4", "R upper arm: from 2-4"),
    13: ("右前臂：继承右上臂坐标系", "right forearm: inherits the right upper arm frame", (1, 2, 3, 4, 8),
         "继承右上臂", "inherits R upper arm"),
    14: _CHEST,
    15: _CHEST,
    16: ("颈 -> 头：肩线（反向）", "neck -> head: shoulder line (negated)", (2, 3), "肩线（反）", "-shoulder line"),
}
DEFAULT_RULE = ("超出 17 根：世界 +Z 最短弧，扭转无约束", "beyond 17: shortest arc from world +Z, roll unconstrained",
                (), "最短弧（无约束）", "shortest arc (free roll)")

# 上臂 stick 的朝向不看自身端点，而是取固定粒子对：stick 下标 -> (起点, 终点)
UPPER_ARM_SOURCE = {10: (3, 5), 12: (2, 4)}

UNIT_X = np.array([1.0, 0.0, 0.0])
UNIT_Y = np.array([0.0, 1.0, 0.0])
UNIT_Z = np.array([0.0, 0.0, 1.0])
_IDENTITY_Q = np.array([1.0, 0.0, 0.0, 0.0])


def stick_rule(index):
    return STICK_RULES.get(int(index), DEFAULT_RULE)


class EngineSkinUnavailable(ValueError):
    """骨架不满足引擎蒙皮前提（粒子太少、端点缺失等）。"""


# ──────────────────────────────────────────────
# OGRE 1.7 向量 / 四元数运算
# ──────────────────────────────────────────────

def normalise(v):
    """长度 ≤ 1e-8 时原样返回（与 OGRE 一致，零向量保持为零）。"""
    n = float(np.sqrt(v @ v))
    return v / n if n > 1e-08 else v


def from_rotation_matrix(m):
    """Shoemake 算法；非正交输入不做修正。平方根参数 ≤ 0（退化）时返回 None。"""
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0.0:
        root = np.sqrt(trace + 1.0)
        w = 0.5 * root
        root = 0.5 / root
        return np.array([w,
                         (m[2, 1] - m[1, 2]) * root,
                         (m[0, 2] - m[2, 0]) * root,
                         (m[1, 0] - m[0, 1]) * root])
    i = 0
    if m[1, 1] > m[0, 0]:
        i = 1
    if m[2, 2] > m[i, i]:
        i = 2
    j = (1, 2, 0)[i]
    k = (1, 2, 0)[j]
    arg = m[i, i] - m[j, j] - m[k, k] + 1.0
    if not arg > 1e-12:
        return None
    root = np.sqrt(arg)
    xyz = [0.0, 0.0, 0.0]
    xyz[i] = 0.5 * root
    root = 0.5 / root
    w = (m[k, j] - m[j, k]) * root
    xyz[j] = (m[j, i] + m[i, j]) * root
    xyz[k] = (m[k, i] + m[i, k]) * root
    return np.array([w, xyz[0], xyz[1], xyz[2]])


def q_normalise(q):
    n = float(q @ q)
    return q / np.sqrt(n) if n > 0.0 else q


def q_inverse(q):
    n = float(q @ q)
    if n <= 0.0:
        return np.zeros(4)
    return np.array([q[0], -q[1], -q[2], -q[3]]) / n


def q_mul_vec(q, v):
    """OGRE 的 Quaternion * Vector3；非单位四元数时不是纯旋转。"""
    qv = q[1:]
    uv = np.cross(qv, v)
    uuv = np.cross(qv, uv)
    return v + uv * (2.0 * q[0]) + uuv * 2.0


def q_to_matrix(q):
    """OGRE 的 ToRotationMatrix。对非单位 q 结果为 (1-|q|²)I + |q|²R，与 q_mul_vec 等价。"""
    w, x, y, z = q
    tx, ty, tz = 2.0 * x, 2.0 * y, 2.0 * z
    twx, twy, twz = tx * w, ty * w, tz * w
    txx, txy, txz = tx * x, ty * x, tz * x
    tyy, tyz, tzz = ty * y, tz * y, tz * z
    return np.array([
        [1.0 - (tyy + tzz), txy - twz, txz + twy],
        [txy + twz, 1.0 - (txx + tzz), tyz - twx],
        [txz - twy, tyz + twx, 1.0 - (txx + tyy)],
    ])


def get_rotation_to(src, dest, fallback):
    v0 = normalise(np.asarray(src, dtype=float))
    v1 = normalise(np.asarray(dest, dtype=float))
    d = float(v0 @ v1)
    if d >= 1.0:
        return _IDENTITY_Q.copy()
    if d < (1e-6 - 1.0):
        axis = normalise(np.asarray(fallback, dtype=float))
        return np.array([0.0, axis[0], axis[1], axis[2]])  # 绕 fallback 转 180°
    s = np.sqrt((1.0 + d) * 2.0)
    c = np.cross(v0, v1) / s
    return q_normalise(np.array([s * 0.5, c[0], c[1], c[2]]))


def nearest_rotation(m):
    """极分解取最近的正交旋转（给 oriented cube 用，避免立方体被剪切）；输入非有限时返回单位阵。"""
    if not np.all(np.isfinite(m)):
        return np.eye(3)
    try:
        u, _s, vt = np.linalg.svd(m)
    except np.linalg.LinAlgError:
        return np.eye(3)
    r = u @ vt
    if np.linalg.det(r) < 0.0:
        u[:, -1] = -u[:, -1]
        r = u @ vt
    return r


def distortion(m):
    """σmax/σmin − 1：0 为刚性，越大拉伸/压扁越明显；奇异或非有限时返回 inf。"""
    if not np.all(np.isfinite(m)):
        return float("inf")
    try:
        sv = np.linalg.svd(m, compute_uv=False)
    except np.linalg.LinAlgError:
        return float("inf")
    return float(sv[0] / sv[-1] - 1.0) if sv[-1] > 1e-12 else float("inf")


# ──────────────────────────────────────────────
# 身体参考系与按下标查表
# ──────────────────────────────────────────────

def _blend_axes(z, ref2, ref1):
    """x = norm(ref1·(1−|d|) − ref2·d)，d = ref1·z；不做 Gram-Schmidt。"""
    d = float(ref1 @ z)
    x = normalise(ref1 * (1.0 - abs(d)) - ref2 * d)
    return x, np.cross(z, x), z


def _leg_ref(knee, hip, fa, fc, flip):
    """腿部参考：大腿越往外摆，越从 −胯线 偏向 ±骨盆法向。"""
    n = normalise(knee - hip)
    s = -1.0 if flip else 1.0
    e = max(0.0, float(n @ (fa * s)))
    return normalise(fc * (e * s) + (-fa) * (1.0 - e))


def _quat_from_axes(x, y, z, renormalise=False):
    q = from_rotation_matrix(np.column_stack([x, y, z]))
    if q is None:
        return None
    return q_normalise(q) if renormalise else q


def body_frame(P):
    """P: (N,3) 按粒子下标排列，N ≥ MIN_PARTICLES。"""
    P = np.asarray(P, dtype=float)
    if len(P) < MIN_PARTICLES:
        raise EngineSkinUnavailable(f"引擎蒙皮需要至少 {MIN_PARTICLES} 个粒子，当前 {len(P)} 个")
    fa = normalise(P[9] - P[10])                      # 胯线，指向右
    fb = normalise(P[8] - (P[9] + P[10]) * 0.5)       # 胯中点 → midspine
    fc = np.cross(fb, fa)                             # 骨盆法向（不归一化）
    fe = _leg_ref(P[11], P[9], fa, fc, False)         # 右腿参考
    fd = _leg_ref(P[12], P[10], fa, fc, True)         # 左腿参考
    ff = normalise(P[2] - P[3])                       # 肩线，指向右
    fg = normalise(P[1] - P[8])                       # midspine → 颈
    fh = np.cross(fg, ff)                             # 胸廓法向（不归一化）
    q1_axes = _blend_axes(normalise(P[4] - P[2]), fh, ff)   # 右上臂
    q2_axes = _blend_axes(normalise(P[5] - P[3]), fh, ff)   # 左上臂
    return {
        "a": fa, "b": fb, "c": fc, "d": fd, "e": fe, "f": ff, "g": fg, "h": fh,
        "q1_axes": q1_axes, "q2_axes": q2_axes,
        "q1": _quat_from_axes(*q1_axes, renormalise=True),
        "q2": _quat_from_axes(*q2_axes, renormalise=True),
    }


def _rule_axes(index, u, F):
    """返回 (x, y, z, renormalise)；下标 10/12 直接复用上臂坐标系。"""
    if index in (0, 1):
        return F["e"], np.cross(u, F["e"]), u, False
    if index in (3, 4):
        return F["d"], np.cross(u, F["d"]), u, False
    if index == 2:
        return -F["c"], np.cross(u, -F["c"]), u, False
    if index in (5, 8):
        return F["c"], np.cross(u, F["c"]), u, False
    if index in (6, 9):
        return np.cross(F["h"], u), F["h"], u, False
    if index == 7:
        return np.cross(F["g"], u), F["g"], u, False
    if index == 10:
        return (*F["q2_axes"], True)
    if index == 12:
        return (*F["q1_axes"], True)
    if index in (11, 13):
        q = F["q2"] if index == 11 else F["q1"]
        if q is None:
            return None
        x_ref = q_mul_vec(q, UNIT_X if index == 11 else -UNIT_X)
        return (*_blend_axes(u, q_mul_vec(q, UNIT_Z), x_ref), True)
    if index in (14, 15):
        return F["h"], np.cross(u, F["h"]), u, False
    if index == 16:
        return -F["f"], np.cross(u, -F["f"]), u, False
    return None


def stick_orientation(index, pa, pb, F, diagnose=False):
    """返回四元数 q；diagnose=True 时返回 (q, info)。

    info["sigma_min"]：传给 FromAxes 的三列矩阵最小奇异值（1 = 理想，→0 = 退化）
    info["degenerate"]：参考方向退化、游戏里这段体素会塌缩或翻转；此时 q 退回世界 +Z 最短弧
    """
    u = normalise(np.asarray(pb, dtype=float) - np.asarray(pa, dtype=float))
    idx = int(index)
    if idx >= MAX_GPU_STICKS:
        q = get_rotation_to(UNIT_Z, u, UNIT_Y)
        return (q, {"sigma_min": 1.0, "degenerate": False}) if diagnose else q

    axes = _rule_axes(idx, u, F)
    q = None
    sigma = 0.0
    if axes is not None:
        x, y, z, renorm = axes
        q = _quat_from_axes(x, y, z, renormalise=renorm)
        if diagnose:
            sigma = float(np.linalg.svd(np.column_stack([x, y, z]), compute_uv=False)[-1])
    degenerate = q is None or not np.all(np.isfinite(q)) or float(q @ q) < 1e-12
    if degenerate:
        q = get_rotation_to(UNIT_Z, u, UNIT_Y)
        sigma = 0.0
    if diagnose:
        return q, {"sigma_min": sigma, "degenerate": bool(degenerate)}
    return q


# ──────────────────────────────────────────────
# 绑定与每帧姿态
# ──────────────────────────────────────────────

class EngineSkinBinding:
    """用 bind 姿态记录每个体素在所属 stick 局部坐标系里的位置。

    bind_positions: (N,3) 粒子位置，按粒子下标
    stick_pairs:    [(a 下标, b 下标)]，按 stick 下标
    voxels_xyz:     (V,3)
    bindings:       {体素下标: stick 下标}
    """

    def __init__(self, bind_positions, stick_pairs, voxels_xyz, bindings):
        P = np.asarray(bind_positions, dtype=float)
        n = len(P)
        if n < MIN_PARTICLES:
            raise EngineSkinUnavailable(f"引擎蒙皮需要至少 {MIN_PARTICLES} 个粒子，当前 {n} 个")
        self.stick_pairs = [(int(a), int(b)) for a, b in stick_pairs]
        for ci, (a, b) in enumerate(self.stick_pairs):
            if not (0 <= a < n and 0 <= b < n):
                raise EngineSkinUnavailable(f"stick {ci} 的端点粒子不存在")
        self.n_particles = n
        V = np.asarray(voxels_xyz, dtype=float).reshape(-1, 3)
        F = body_frame(P)
        # 每根 stick 的 bind 逆矩阵（与 q_mul_vec(q⁻¹, ·) 等价），体检算畸变也要用。
        # bind_error = ‖M(q)·M(q⁻¹) − I‖（谱范数）：bind 四元数非单位时两者不抵消，
        # 游戏里这段体素在 bind 姿态下就会错位，错位量约为 bind_error × 体素到 a 端的距离
        self.bind_inv = []
        self.bind_error = []
        for ci, (a, b) in enumerate(self.stick_pairs):
            q = stick_orientation(ci, P[a], P[b], F)
            inv = q_to_matrix(q_inverse(q))
            self.bind_inv.append(inv)
            roundtrip = q_to_matrix(q) @ inv - np.eye(3)
            self.bind_error.append(float(np.linalg.norm(roundtrip, 2)) if np.all(np.isfinite(roundtrip))
                                   else float("inf"))

        by_stick = {}
        for vi, ci in bindings.items():
            vi, ci = int(vi), int(ci)
            if 0 <= vi < len(V) and 0 <= ci < len(self.stick_pairs):
                by_stick.setdefault(ci, []).append(vi)
        self.groups = {}
        # 每根 stick 的体素在 bind 姿态下实际被挪开的最大距离（体素单位；无体素为 0）
        self.bind_drift = [0.0] * len(self.stick_pairs)
        for ci, vis in by_stick.items():
            vis = np.array(sorted(vis), dtype=np.int64)
            a = self.stick_pairs[ci][0]
            local = (V[vis] - P[a]) @ self.bind_inv[ci].T
            self.groups[ci] = (vis, local)
            q = stick_orientation(ci, P[a], P[self.stick_pairs[ci][1]], F)
            back = local @ q_to_matrix(q).T + P[a]
            self.bind_drift[ci] = float(np.max(np.linalg.norm(back - V[vis], axis=1)))

    def stick_matrices(self, P, F=None):
        """每根 stick 的 (M_now, 原点)。M_now @ local + 原点 = 世界坐标。"""
        P = np.asarray(P, dtype=float)
        if F is None:
            F = body_frame(P)
        out = []
        for ci, (a, b) in enumerate(self.stick_pairs):
            q = stick_orientation(ci, P[a], P[b], F)
            out.append((q_to_matrix(q), P[a]))
        return out

    def pose(self, P):
        """返回 ({stick 下标: (体素下标数组, 世界坐标 (n,3))}, [每根 stick 相对 bind 的线性变换 3x3])。"""
        P = np.asarray(P, dtype=float)
        mats = self.stick_matrices(P)
        worlds = {}
        for ci, (vis, local) in self.groups.items():
            m, origin = mats[ci]
            worlds[ci] = (vis, local @ m.T + origin)
        deltas = [m @ self.bind_inv[ci] for ci, (m, _o) in enumerate(mats)]
        return worlds, deltas

    def diagnose(self, P):
        """逐 stick 体检：[{"sigma_min", "degenerate", "distortion", "bind_error", "bind_drift"}]。

        distortion 相对 bind；bind_error / bind_drift 与姿态无关，来自 bind 时的计算。
        """
        P = np.asarray(P, dtype=float)
        F = body_frame(P)
        out = []
        for ci, (a, b) in enumerate(self.stick_pairs):
            q, info = stick_orientation(ci, P[a], P[b], F, diagnose=True)
            info["distortion"] = distortion(q_to_matrix(q) @ self.bind_inv[ci])
            info["bind_error"] = self.bind_error[ci]
            info["bind_drift"] = self.bind_drift[ci]
            out.append(info)
        return out


def frame_grade(info):
    """本帧姿态的分级（参考方向退化、相对 bind 的变形）：0 正常 / 1 注意 / 2 异常。"""
    if info["degenerate"] or info["sigma_min"] < SIGMA_BAD or info["distortion"] > DISTORTION_BAD:
        return 2
    if info["sigma_min"] < SIGMA_WARN or info["distortion"] > DISTORTION_WARN:
        return 1
    return 0


def bind_grade(bind_error, bind_drift):
    """静止错位（与姿态无关）的分级：相对误差够大，且错位体素数达到看得见的下限才报。"""
    if not np.isfinite(bind_error):
        return 2
    if bind_error > BIND_ERROR_BAD and bind_drift >= BIND_DRIFT_BAD:
        return 2
    if bind_error > BIND_ERROR_WARN and bind_drift >= BIND_DRIFT_WARN:
        return 1
    return 0


def grade(info):
    """综合分级：本帧与静止错位取较重者。"""
    return max(frame_grade(info), bind_grade(info.get("bind_error", 0.0), info.get("bind_drift", 0.0)))


def static_warnings(n_particles, stick_pairs, bindings, body_hints=None):
    """与姿态无关的结构检查，返回 [(code, params)]，文案由 UI 层翻译。

    code:
      too_few_particles   粒子 < 13，引擎会越界（推断，待实测）
      binding_over_17     有体素绑在下标 ≥ 17 的 stick 上，游戏的骨骼矩阵放不下
      arm_source_mismatch 上臂 stick 端点与引擎取朝向的粒子对不一致
      anchor_not_lower    粒子 8 的 bodyAreaHint 是 2：它会随上半身层跟瞄准方向转（vanilla 为 1）
      no_upper_layer      没有 bodyAreaHint = 2 的粒子，上半身动画层不起作用
    （bind 往返误差需要 EngineSkinBinding，见 bind_warnings）
    """
    out = []
    if n_particles < MIN_PARTICLES:
        out.append(("too_few_particles", {"n": n_particles, "min": MIN_PARTICLES}))
    over = sorted({int(ci) for ci in bindings.values() if int(ci) >= MAX_GPU_STICKS})
    if over:
        out.append(("binding_over_17", {"sticks": over}))
    for ci, (src_a, src_b) in UPPER_ARM_SOURCE.items():
        if ci < len(stick_pairs) and {int(v) for v in stick_pairs[ci]} != {src_a, src_b}:
            out.append(("arm_source_mismatch", {"stick": ci, "a": src_a, "b": src_b}))
    if body_hints is not None:
        # 游戏只把 hint == 2 当上半身层，其它值都是下半身层
        if len(body_hints) > 8 and int(body_hints[8]) == 2:
            out.append(("anchor_not_lower", {"hint": int(body_hints[8])}))
        if not any(int(h) == 2 for h in body_hints):
            out.append(("no_upper_layer", {}))
    return out


def bind_warnings(skin, only_sticks=None):
    """静止错位看得出来的 stick：[("bind_drift", {"sticks": "#4 27.1 (48%), #0 8.3 (16%)"})] 或 []。

    only_sticks：只看这些 stick（通常是有体素绑定的）；None 表示全部。
    判定见 bind_grade：没绑体素（错位 0）的 stick 不报——没有体素就看不见错位。
    """
    items = []
    for ci, err in enumerate(skin.bind_error):
        drift = skin.bind_drift[ci]
        if bind_grade(err, drift) == 0 or (only_sticks is not None and ci not in only_sticks):
            continue
        items.append((err, ci, f"#{ci} {drift:.1f} ({err:.0%})"))
    if not items:
        return []
    items.sort(reverse=True)
    return [("bind_drift", {"sticks": ", ".join(label for _v, _c, label in items)})]


# ──────────────────────────────────────────────
# 左右对称
# ──────────────────────────────────────────────
# 姿态严格镜像（x 取反、左右粒子互换）后逐体素比较，下面这些槽位对两侧结果严格镜像（两侧方向一致时）：
# 腿规则 (0|1 ↔ 3|4)、上臂 (12,10)、前臂 (13,11)、胸廓 (6,9)。(5,8)、(14,15) 两侧用同一条规则，
# FromAxes 输入不正交时两侧算出来不一样，改方向也救不回来。
# 但只看对称不够：同一对骨段放进不同槽位，渲染方向偏离骨段的程度（跟随）差别很大，所以要一起算代价。
# 每项 (右槽, 左槽)；右 = x 为负的一侧，与 vanilla 的 right* 粒子一致
MIRROR_PAIR_SLOTS = ((0, 4), (1, 3), (6, 9), (12, 10), (5, 8), (14, 15), (13, 11))
MIRROR_CENTER_SLOTS = (2, 7, 16)
_MX = np.diag([-1.0, 1.0, 1.0])

SYM_MIN_VOXELS = 20       # 体素少于此数的骨段不计代价：零星体素挪到哪都行
SYM_PERCENTILE = 95       # 按姿态取分位数，避免个别极端帧主导
SYM_ASYM_WEIGHT = 2.0     # 左右不一样一眼就是 bug；两侧一起偏不显眼，所以不对称按两倍计
SYM_MAX_DRIFT = 5.0       # 新位置的静止错位上限（体素）：待机时一直看得见，超过就不考虑
SYM_KEEP_BONUS = 2.0      # 改动至少要换来这么多体素才做，避免为一点点提升大挪骨段
# 结构检查：镜像骨段对的左右偏差（P95）超过这段体素尺寸的 10%、且至少 2 体素才提示。
# 考虑角色朝向后几乎没有哪对是严格 0，按绝对值报会满屏都是
SYM_WARN_REL = 0.10
SYM_WARN_MIN = 2.0


def mirror_particle_map(P, tol=0.51):
    """bind 骨架关于 x = 0 镜像对称时返回 {粒子下标: 镜像粒子下标}，否则 None。"""
    P = np.asarray(P, dtype=float)
    if len(P) < MIN_PARTICLES:
        return None
    pm = {}
    for k in range(len(P)):
        d = np.linalg.norm(P - _MX @ P[k], axis=1)
        j = int(np.argmin(d))
        if d[j] > tol:
            return None
        pm[k] = j
    # 必须一一对应：两个粒子贴得很近时可能映到同一个镜像粒子，镜像姿态就会漏写一行
    if len(set(pm.values())) != len(pm):
        return None
    return pm


def mirror_pose(P, pm):
    """姿态关于 x = 0 镜像并左右互换粒子。"""
    P = np.asarray(P, dtype=float)
    Q = np.empty_like(P)
    for k, j in pm.items():
        Q[j] = _MX @ P[k]
    return Q


def classify_mirror_sticks(stick_pairs, pm, P0):
    """返回 (镜像对 [(右, 左)], 居中 [s], 落单 [s])。

    镜像对：端点集合互为镜像的两根 stick；居中：端点集合镜像后是它自己；落单：找不到镜像的。
    """
    P0 = np.asarray(P0, dtype=float)
    sets = [frozenset(int(v) for v in ab) for ab in stick_pairs]
    used, mpairs, centers, lonely = set(), [], [], []
    for s, ab in enumerate(sets):
        if s in used:
            continue
        m = frozenset(pm[x] for x in ab)
        if m == ab:
            centers.append(s)
            used.add(s)
            continue
        partners = [t for t in range(len(sets)) if t not in used and t != s and sets[t] == m]
        if not partners:
            lonely.append(s)
            used.add(s)
            continue
        t = partners[0]
        used |= {s, t}
        xs = P0[list(stick_pairs[s])].mean(0)[0]
        mpairs.append((s, t) if xs <= 0 else (t, s))
    return mpairs, centers, lonely


# 胸廓参考系用到的粒子（颈、两肩、midspine）：真实动作里基本一起刚性运动
SYM_CORE_PARTICLES = (1, 2, 3, 8)


def synthetic_poses(P0, n=32, seed=0):
    """没有动画时的测试姿态（固定种子，结果稳定）：躯干整体随机转动、平移，其余粒子再各自扰动。

    躯干保持刚性更接近真实动作：前臂槽 (13,11) 只在胸廓不变形时两侧对称，每个粒子独立扰动
    会把它误判成不对称。偏差多大、跟随和变形多少取决于真实动作，只能当估计。
    """
    P0 = np.asarray(P0, dtype=float)
    rng = np.random.default_rng(seed)
    scale = 0.12 * float(np.mean(np.linalg.norm(P0 - P0.mean(0), axis=1)))
    core = [i for i in SYM_CORE_PARTICLES if i < len(P0)]
    centre = P0[core].mean(0)
    out = []
    for _ in range(n):
        axis = normalise(rng.normal(size=3))
        half = 0.5 * np.radians(rng.uniform(0.0, 25.0))
        R = q_to_matrix(np.concatenate([[np.cos(half)], axis * np.sin(half)]))
        P = (P0 - centre) @ R.T + centre + rng.normal(0.0, 0.3 * scale, 3)
        noise = rng.normal(0.0, scale, P0.shape)
        noise[core] = 0.0
        out.append(P + noise)
    return out


# 评估时角色的朝向（绕竖直轴，度）。游戏先按角色朝向把粒子写进世界坐标，再用世界坐标算每根骨段的朝向；
# bind 却用模型 XML 里未旋转的骨架。坐标轴不正交时 FromRotationMatrix 不随旋转协变，
# 所以同一个动作面朝不同方向时蒙皮结果不同（vanilla 中位 0.05 体素，异形骨可达几十体素）。
# 只看朝向 0 会高估"严格对称"：腿槽在 0° / 180° 两侧一致，45° / 90° 时就不一致了。
# 180°–315° 与 0°–135° 的结果相近，取这四个足够。
SYM_HEADINGS = (0.0, 45.0, 90.0, 135.0)


def heading_matrix(deg):
    """绕竖直轴（y）转 deg 度。"""
    t = np.radians(float(deg))
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


class SymmetryEvaluator:
    """评估 stick 放进某槽位、以某端为原点时的可见误差（体素）。

    stick 的朝向只取决于槽位规则、自己的端点和身体参考系，身体参考系只看粒子位置，
    与 stick 怎么分配无关，所以每种放法的代价可以单独算，分配就成了指派问题。
    每个模型空间姿态都按 headings 里的朝向转到世界坐标再算（bind 仍在模型空间，与游戏一致），
    镜像比较时镜像面随朝向一起转。
    """

    def __init__(self, bind_positions, stick_pairs, voxels_xyz, bindings, poses, pm, headings=SYM_HEADINGS):
        self.P0 = np.asarray(bind_positions, dtype=float)
        self.pairs = [(int(a), int(b)) for a, b in stick_pairs]
        self.pm = pm
        self.vox = np.asarray(voxels_xyz, dtype=float).reshape(-1, 3)
        self.vox_of = {}
        for vi, ci in bindings.items():
            vi, ci = int(vi), int(ci)
            if 0 <= vi < len(self.vox):
                self.vox_of.setdefault(ci, []).append(vi)
        self.F0 = body_frame(self.P0)
        self.poses, self.mposes, self.mirrors = [], [], []
        for deg in headings:
            R = heading_matrix(deg)
            for P in poses:
                P = np.asarray(P, dtype=float)
                self.poses.append(P @ R.T)
                self.mposes.append(mirror_pose(P, pm) @ R.T)
                self.mirrors.append(R @ _MX @ R.T)        # 镜像面随朝向转
        self.Fs = [body_frame(P) for P in self.poses]
        self.mFs = [body_frame(Q) for Q in self.mposes]
        self._cache = {}

    def other_end(self, stick, a):
        x, y = self.pairs[stick]
        return y if a == x else x

    def n_voxels(self, stick):
        return len(self.vox_of.get(stick, ()))

    def _series(self, slot, a, b, mirrored=False):
        """每个姿态的 T = M(q_pose)·M(q_bind⁻¹)（与游戏同样不归一化），以及 bind 往返矩阵。"""
        key = ("T", slot, a, b, mirrored)
        if key not in self._cache:
            q0 = stick_orientation(slot, self.P0[a], self.P0[b], self.F0)
            inv0 = q_to_matrix(q_inverse(q0))
            rt = q_to_matrix(q0) @ inv0
            Ps, Fs = (self.mposes, self.mFs) if mirrored else (self.poses, self.Fs)
            Ts = np.array([q_to_matrix(stick_orientation(slot, P[a], P[b], F)) @ inv0
                           for P, F in zip(Ps, Fs)]).reshape(-1, 3, 3)
            self._cache[key] = (Ts, rt)
        return self._cache[key]

    def placement(self, stick, slot, a):
        """stick 放进 slot、以粒子 a 为原点：(每姿态跟随误差, 每姿态变形, 静止错位, 变换序列)，单位体素。"""
        key = ("P", stick, slot, a)
        if key in self._cache:
            return self._cache[key]
        b = self.other_end(stick, a)
        Ts, rt = self._series(slot, a, b)
        V = self.vox[self.vox_of.get(stick, [])]
        n = len(self.poses)
        if len(V) < SYM_MIN_VOXELS:
            out = (np.zeros(n), np.zeros(n), 0.0, Ts)
        else:
            loc = V - self.P0[a]
            reach = float(np.max(np.linalg.norm(loc, axis=1)))
            drift = float(np.max(np.linalg.norm(loc @ (rt - np.eye(3)).T, axis=1)))
            dist = np.array([distortion(T) for T in Ts]) * reach
            u0 = self.P0[b] - self.P0[a]
            u0 = u0 / max(float(np.linalg.norm(u0)), 1e-9)
            track = np.zeros(n)
            for i, (T, P) in enumerate(zip(Ts, self.poses)):
                u = P[b] - P[a]
                v = T @ u0
                nu, nv = float(np.linalg.norm(u)), float(np.linalg.norm(v))
                if nu > 1e-9:
                    track[i] = reach if nv < 1e-9 else float(np.linalg.norm(v / nv - u / nu)) * reach
            out = (track, np.nan_to_num(dist, nan=reach, posinf=reach), drift, Ts)
        self._cache[key] = out
        return out

    def mirror_gap(self, stick, slot, a, partner, partner_slot, pa):
        """stick 的体素在姿态 P 下的位置镜像后，与其镜像体素（在 partner 上、以 pa 为原点）
        在镜像姿态 P̄ 下的位置之差，逐姿态取最大（体素）。"""
        V = self.vox[self.vox_of.get(stick, [])]
        n = len(self.poses)
        if len(V) < SYM_MIN_VOXELS:
            return np.zeros(n)
        Ts = self.placement(stick, slot, a)[3]
        Tm, _ = self._series(partner_slot, pa, self.other_end(partner, pa), mirrored=True)
        loc = V - self.P0[a]
        locm = V @ _MX.T - self.P0[pa]
        out = np.empty(n)
        for i, (P, Q, Mi) in enumerate(zip(self.poses, self.mposes, self.mirrors)):
            w = (P[a] + loc @ Ts[i].T) @ Mi.T
            wm = Q[pa] + locm @ Tm[i].T
            out[i] = float(np.max(np.linalg.norm(w - wm, axis=1)))
        return np.nan_to_num(out, nan=1e6, posinf=1e6)

    @staticmethod
    def _agg(per_pose, static=0.0):
        v = float(np.percentile(per_pose, SYM_PERCENTILE)) if len(per_pose) else 0.0
        return max(v, float(static))

    def pair_cost(self, right, left, slot_r, slot_l, a_r, a_l):
        """镜像对放进 (slot_r, slot_l)、原点分别为 a_r / a_l。返回 (代价, 明细)，单位体素。"""
        tr, sr, dr, _ = self.placement(right, slot_r, a_r)
        tl, sl, dl, _ = self.placement(left, slot_l, a_l)
        asym = self.mirror_gap(right, slot_r, a_r, left, slot_l, a_l)
        detail = {"asym": self._agg(asym), "track": self._agg(np.maximum(tr, tl)),
                  "dist": self._agg(np.maximum(sr, sl)), "drift": max(dr, dl)}
        cost = self._agg(np.maximum.reduce([asym * SYM_ASYM_WEIGHT, tr, tl, sr, sl]), max(dr, dl))
        return cost, detail

    def single_cost(self, stick, slot, a, mirror_self=True):
        """单根 stick（居中或落单）。居中骨段镜像后还是它自己，同样要求左右对称。"""
        t, s, d, _ = self.placement(stick, slot, a)
        asym = self.mirror_gap(stick, slot, a, stick, slot, a) if mirror_self else np.zeros(len(self.poses))
        detail = {"asym": self._agg(asym), "track": self._agg(t), "dist": self._agg(s), "drift": d}
        return self._agg(np.maximum.reduce([asym * SYM_ASYM_WEIGHT, t, s]), d), detail


def current_slot_plan(ev, mpairs, centers, lonely=()):
    """现状作为一份方案（与 optimise_slots 的结果同格式），并算好代价。"""
    plan = [{"sticks": [r, l], "slots": [r, l], "a_ends": [ev.pairs[r][0], ev.pairs[l][0]]} for r, l in mpairs]
    plan += [{"sticks": [s], "slots": [s], "a_ends": [ev.pairs[s][0]]} for s in list(centers) + list(lonely)]
    return evaluate_slot_plan(ev, plan, centers=set(centers))


def evaluate_slot_plan(ev, plan, centers=None):
    out = []
    for item in plan:
        st, sl, ae = item["sticks"], item["slots"], item["a_ends"]
        if len(st) == 2:
            cost, det = ev.pair_cost(st[0], st[1], sl[0], sl[1], ae[0], ae[1])
        else:
            is_center = centers is None or st[0] in centers
            cost, det = ev.single_cost(st[0], sl[0], ae[0], mirror_self=is_center)
        out.append({**item, "cost": cost, "detail": det})
    return out


def optimise_slots(ev, mpairs, centers, lonely=(), keep_bonus=SYM_KEEP_BONUS, max_drift=SYM_MAX_DRIFT):
    """槽位指派：镜像对 -> 槽位对（含哪侧进右槽、以哪端为原点），其余骨段 -> 剩下的槽位。

    目标是代价总和最小。新位置静止错位超过 max_drift 的不考虑（原位置不受限）；
    维持原样的放法少算 keep_bonus，避免为一点点提升大挪骨段。
    返回方案列表；骨段数不是 17、镜像对多于槽位对时返回 None。
    """
    n_sticks = len(ev.pairs)
    if n_sticks != MAX_GPU_STICKS or len(mpairs) > len(MIRROR_PAIR_SLOTS):
        return None
    import itertools

    def adj(cost, det, unchanged):
        penalty = 1000.0 if (det["drift"] > max_drift and not unchanged) else 0.0
        return cost + penalty - (keep_bonus if unchanged else 0.0)

    pair_opt = {}
    for pi, (r, l) in enumerate(mpairs):
        for si, (sr, sl) in enumerate(MIRROR_PAIR_SLOTS):
            cands = [(rr, ll, a_r, ev.pm[a_r]) for rr, ll in ((r, l), (l, r))
                     for a_r in ev.pairs[rr] if ev.pm[a_r] in ev.pairs[ll]]
            if {sr, sl} == {r, l}:
                # 维持原样（两侧方向可能不一致，也照样列为候选）：此时槽位 sr 上的骨段就是 sr 本身
                cands.append((sr, sl, ev.pairs[sr][0], ev.pairs[sl][0]))
            best = None
            for rr, ll, a_r, a_l in cands:
                cost, det = ev.pair_cost(rr, ll, sr, sl, a_r, a_l)
                unchanged = (rr, ll) == (sr, sl) and (a_r, a_l) == (ev.pairs[rr][0], ev.pairs[ll][0])
                cand = (adj(cost, det, unchanged), cost, det, rr, ll, a_r, a_l)
                if best is None or cand[0] < best[0]:
                    best = cand
            pair_opt[(pi, si)] = best

    singles = list(centers) + list(lonely)
    center_set = set(centers)
    single_cache = {}

    def single_opt(s, k):
        key = (s, k)
        if key not in single_cache:
            best = None
            for a in ev.pairs[s]:
                cost, det = ev.single_cost(s, k, a, mirror_self=s in center_set)
                unchanged = k == s and a == ev.pairs[s][0]
                cand = (adj(cost, det, unchanged), cost, det, s, a)
                if best is None or cand[0] < best[0]:
                    best = cand
            single_cache[key] = best
        return single_cache[key]

    free_cache = {}

    def best_singles(free_slots):
        """剩下的槽位给居中 / 落单骨段：各自代价互不影响，是指派问题。
        按"已用了哪些空槽"做状态压缩 DP（穷举排列是阶乘级，镜像对少、居中骨段多时算不完）；按空槽集合记忆化。"""
        key = tuple(sorted(free_slots))
        if key not in free_cache:
            m = len(key)
            if len(singles) != m:
                free_cache[key] = None
                return None
            # dp[mask] = (前 popcount(mask) 根单独骨段用掉 mask 这些空槽时的最小代价, 回溯用的上一个 mask, 槽位)
            dp = {0: (0.0, None, None)}
            for mask in range(1 << m):
                if mask not in dp:
                    continue
                i = bin(mask).count("1")
                if i == len(singles):
                    continue
                base = dp[mask][0]
                for j in range(m):
                    if mask & (1 << j):
                        continue
                    nm = mask | (1 << j)
                    cand = base + single_opt(singles[i], key[j])[0]
                    if nm not in dp or cand < dp[nm][0]:
                        dp[nm] = (cand, mask, key[j])
            full = (1 << m) - 1
            perm = []
            mask = full
            while mask:
                _c, prev, slot = dp[mask]
                perm.append(slot)
                mask = prev
            free_cache[key] = (dp[full][0], tuple(reversed(perm)))
        return free_cache[key]

    best = None
    n_slot_pairs = len(MIRROR_PAIR_SLOTS)
    for perm in itertools.permutations(range(n_slot_pairs), len(mpairs)):
        total = sum(pair_opt[(pi, si)][0] for pi, si in enumerate(perm))
        used = {k for si in perm for k in MIRROR_PAIR_SLOTS[si]}
        free = [k for k in range(n_sticks) if k not in used]
        if len(free) != len(singles):
            continue
        sub = best_singles(free)
        if sub is None:
            continue
        total += sub[0]
        if best is None or total < best[0]:
            best = (total, perm, sub[1])
    if best is None:
        return None
    _total, perm, single_slots = best
    plan = []
    for pi, si in enumerate(perm):
        _adj, cost, det, rr, ll, a_r, a_l = pair_opt[(pi, si)]
        plan.append({"sticks": [rr, ll], "slots": list(MIRROR_PAIR_SLOTS[si]), "a_ends": [a_r, a_l],
                     "cost": cost, "detail": det})
    for s, k in zip(singles, single_slots):
        _adj, cost, det, _s, a = single_opt(s, k)
        plan.append({"sticks": [s], "slots": [k], "a_ends": [a], "cost": cost, "detail": det})
    return plan


def plan_is_identity(plan, stick_pairs):
    """方案是否等于现状（槽位与原点都不变）。"""
    for item in plan:
        for s, k, a in zip(item["sticks"], item["slots"], item["a_ends"]):
            if s != k or a != stick_pairs[s][0]:
                return False
    return True


def symmetry_warnings(ev, mpairs, estimate=False):
    """镜像骨段对左右偏差（P95）明显的（见 SYM_WARN_REL / SYM_WARN_MIN）：[("asymmetric_pairs", {"pairs": ...})]。

    estimate=True（合成姿态）时数值前加 "~"：会不会不对称可靠，偏多少取决于真实动作。
    """
    items = []
    for r, l in mpairs:
        if ev.n_voxels(r) < SYM_MIN_VOXELS and ev.n_voxels(l) < SYM_MIN_VOXELS:
            continue
        _cost, det = ev.pair_cost(r, l, r, l, ev.pairs[r][0], ev.pairs[l][0])
        V = ev.vox[ev.vox_of.get(r, [])]
        reach = float(np.max(np.linalg.norm(V - ev.P0[ev.pairs[r][0]], axis=1))) if len(V) else 0.0
        if det["asym"] >= SYM_WARN_MIN and det["asym"] > SYM_WARN_REL * reach:
            items.append((det["asym"], f"#{r}/#{l} ~{det['asym']:.0f}" if estimate
                          else f"#{r}/#{l} {det['asym']:.1f}"))
    if not items:
        return []
    items.sort(reverse=True)
    return [("asymmetric_pairs", {"pairs": ", ".join(label for _v, label in items)})]
