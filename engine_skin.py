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
# 游戏里这段体素在 bind 姿态下就已错位（vanilla 为 0）
BIND_ERROR_WARN = 0.05
BIND_ERROR_BAD = 0.20
# bind 姿态下体素实际错位（体素单位）；相对误差不大但骨段上的体素离 a 端很远时同样明显
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
        return _WHOLE_BODY_NAMES.get(str(name).strip().lower())
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


def grade(info):
    """体检结果分级：0 正常 / 1 注意 / 2 异常。"""
    bind_error = info.get("bind_error", 0.0)
    bind_drift = info.get("bind_drift", 0.0)
    if (info["degenerate"] or info["sigma_min"] < SIGMA_BAD or info["distortion"] > DISTORTION_BAD
            or bind_error > BIND_ERROR_BAD or bind_drift > BIND_DRIFT_BAD):
        return 2
    if (info["sigma_min"] < SIGMA_WARN or info["distortion"] > DISTORTION_WARN
            or bind_error > BIND_ERROR_WARN or bind_drift > BIND_DRIFT_WARN):
        return 1
    return 0


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
    """bind 往返误差超阈值的 stick：[("bind_drift", {"sticks": "#4 27.1, #0 8.3"})] 或 []。

    only_sticks：只看这些 stick（通常是有体素绑定的）；None 表示全部。
    有体素时附上 bind 姿态下体素实际被挪开的最大距离（体素单位），否则附相对误差。
    """
    items = []
    for ci, err in enumerate(skin.bind_error):
        drift = skin.bind_drift[ci]
        if (err <= BIND_ERROR_WARN and drift <= BIND_DRIFT_WARN) or (
                only_sticks is not None and ci not in only_sticks):
            continue
        items.append((drift if drift > 0 else err, ci, f"#{ci} {drift:.1f}" if drift > 0 else f"#{ci} {err:.0%}"))
    if not items:
        return []
    items.sort(reverse=True)
    return [("bind_drift", {"sticks": ", ".join(label for _v, _c, label in items)})]
