"""
animation_io.py
RWR animation XML parsing and writing.

文件格式:
    <animations>
      <animation loop="0|1" end="<秒>" speed="<倍率>" [speed_spread="<秒>"] comment="<逻辑名>">
        <frame time="<秒>">
          <position x=".." y=".." z=".."/>   # 恰好 15 个，按 skeleton particle 下标对应
          ...
          <control key="..." value="..."/>    # 0 个或多个
        </frame>
        ...
      </animation>
      ...
    </animations>

本模块是纯函数 + 数据类，不持有 EditorState 引用，不依赖 imgui/ModernGL。
"""
import logging
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

# RWR 引擎硬编码：每帧必须正好 15 个 position，对应 vanilla 标准 skeleton 的 15 个 particle
EXPECTED_PARTICLE_COUNT = 15


@dataclass
class AnimationFrame:
    time: float
    # 15 个 (x, y, z)，按 skeleton particle 下标对应
    positions: List[Tuple[float, float, float]] = field(default_factory=list)
    # 0 个或多个 (key, value)
    controls: List[Tuple[str, int]] = field(default_factory=list)


@dataclass
class Animation:
    name: str                              # = XML comment 属性
    loop: bool = False
    end: float = 0.0
    speed: float = 1.0
    speed_spread: Optional[float] = None
    frames: List[AnimationFrame] = field(default_factory=list)


@dataclass
class AnimationDocIndex:
    """大文件懒索引，只记 animation 名和位置，不解析 frames。

    name_to_index 的 value 是文件中 <animation> 的 0-based 真实序号；
    UI 选定某个 name 后调 parse_single_animation(path, name_to_index[name]) 拿完整数据。
    """
    path: str
    names: List[str]
    name_to_index: dict


# ──────────────────────────────────────────────
# 解析
# ──────────────────────────────────────────────

def parse_animation_index(path) -> AnimationDocIndex:
    """扫描动画文件，只提取每个 animation 的 comment 名。

    重名时自动加 _1 / _2 后缀（vanilla soldier_animations.xml 实测无重名，
    但兼容自定义文件防御性处理）。
    """
    raw = Path(path).read_text(encoding='utf-8', errors='replace')
    root = ET.fromstring(raw)
    if root.tag != 'animations':
        raise ValueError(f"Expected root <animations>, got <{root.tag}>")

    names: List[str] = []
    name_to_index: dict = {}
    for i, anim in enumerate(root.iterfind('animation')):
        name = anim.get('comment', f'anim_{i}')
        # 重名去重
        if name in name_to_index:
            suffix = 1
            while f"{name}_{suffix}" in name_to_index:
                suffix += 1
            name = f"{name}_{suffix}"
        names.append(name)
        name_to_index[name] = i  # i 是文件序号，不是 names 列表下标（虽然实际相等）

    logger.info("indexed %d animations from %s", len(names), path)
    return AnimationDocIndex(path=str(path), names=names, name_to_index=name_to_index)


def parse_single_animation(path, animation_index: int) -> Animation:
    """加载文件并解析指定 0-based 序号的动画。

    animation_index 必须是文件中 <animation> 元素的真实序号
    （即 AnimationDocIndex.name_to_index 的 value）。
    """
    raw = Path(path).read_text(encoding='utf-8', errors='replace')
    root = ET.fromstring(raw)
    anim_elems = list(root.iterfind('animation'))
    if animation_index < 0 or animation_index >= len(anim_elems):
        raise ValueError(
            f"animation index out of range: {animation_index} "
            f"(file has {len(anim_elems)} animations)"
        )
    return _parse_animation_element(anim_elems[animation_index])


def parse_first_animation(path) -> Animation:
    """便利函数：解析文件中的第一个动画。

    rwrac.exe 输出的是单 animation 文件（comment 通常带 .dae 后缀），
    常用此入口快速加载。
    """
    return parse_single_animation(path, 0)


def _parse_animation_element(anim_elem) -> Animation:
    name = anim_elem.get('comment', 'unnamed')
    loop = anim_elem.get('loop', '0') == '1'
    end = float(anim_elem.get('end', '0.0'))
    speed = float(anim_elem.get('speed', '1.0'))
    speed_spread = anim_elem.get('speed_spread')
    speed_spread_f = float(speed_spread) if speed_spread is not None else None

    anim = Animation(name=name, loop=loop, end=end, speed=speed,
                     speed_spread=speed_spread_f)

    for frame_elem in anim_elem.iterfind('frame'):
        time = float(frame_elem.get('time', '0.0'))

        positions: List[Tuple[float, float, float]] = []
        for pos_elem in frame_elem.iterfind('position'):
            x = float(pos_elem.get('x', '0'))
            y = float(pos_elem.get('y', '0'))
            z = float(pos_elem.get('z', '0'))
            positions.append((x, y, z))
        if len(positions) != EXPECTED_PARTICLE_COUNT:
            logger.warning(
                "animation '%s' frame %.3f has %d positions (expected %d)",
                name, time, len(positions), EXPECTED_PARTICLE_COUNT,
            )

        controls: List[Tuple[str, int]] = []
        for ctrl_elem in frame_elem.iterfind('control'):
            key = ctrl_elem.get('key', '')
            value_str = ctrl_elem.get('value', '0')
            try:
                value = int(value_str)
            except ValueError:
                logger.warning(
                    "animation '%s' frame %.3f control key='%s' has non-int value '%s', defaulting to 0",
                    name, time, key, value_str,
                )
                value = 0
            controls.append((key, value))

        anim.frames.append(AnimationFrame(time=time, positions=positions, controls=controls))

    return anim


# ──────────────────────────────────────────────
# 写出
# ──────────────────────────────────────────────

def write_single_animation(path, animation: Animation):
    """把一个 Animation 导出为 XML 文件。

    格式：外层 <animations> 包一个 <animation>，便于复制粘贴到大文件。
    采用 Tab 缩进、无 XML 声明头，与 vanilla 格式一致。
    """
    root = ET.Element('animations')
    anim_attrs = {
        'loop': '1' if animation.loop else '0',
        'end': f'{animation.end:.6f}',
        'speed': f'{animation.speed:.6f}',
        'comment': animation.name,
    }
    if animation.speed_spread is not None:
        anim_attrs['speed_spread'] = f'{animation.speed_spread:.6f}'
    anim_elem = ET.SubElement(root, 'animation', anim_attrs)

    for frame in animation.frames:
        frame_elem = ET.SubElement(anim_elem, 'frame', {'time': f'{frame.time:.6f}'})
        for (x, y, z) in frame.positions:
            ET.SubElement(frame_elem, 'position', {
                'x': f'{x:.6f}', 'y': f'{y:.6f}', 'z': f'{z:.6f}',
            })
        for (key, value) in frame.controls:
            ET.SubElement(frame_elem, 'control', {
                'key': key, 'value': str(int(value)),
            })

    xml_str = ET.tostring(root, encoding='unicode')
    pretty = minidom.parseString(xml_str).toprettyxml(indent='\t')
    # 去掉 minidom 自动加的 <?xml?> 声明首行（RWR 不需要）+ 空行
    lines = pretty.split('\n')
    if lines and lines[0].startswith('<?xml'):
        lines = lines[1:]
    pretty = '\n'.join(line for line in lines if line.strip())
    Path(path).write_text(pretty, encoding='utf-8')
    logger.info("wrote animation '%s' to %s (%d frames)",
                animation.name, path, len(animation.frames))


# ──────────────────────────────────────────────
# 插值
# ──────────────────────────────────────────────

def interpolate_positions(animation: Animation, t: float,
                          n_particles: int = EXPECTED_PARTICLE_COUNT):
    """给定时间 t 秒，返回 n_particles 个 (x, y, z) 的插值位置。

    边界处理：
      - 无 frame：返回全 0
      - t 在第一帧之前：返回第一帧
      - t 在最后一帧之后且 loop=True 且 end>0：模运算后再插值
      - t 在最后一帧之后且 loop=False：返回最后一帧
      - 中间：线性插值前后两帧

    注：每次调用都对 frames 排序（O(n log n)），RWR 动画典型 5-30 帧，
    可以忽略。如果未来需要逐帧高频调用且帧数很大再优化。
    """
    if not animation.frames:
        return [(0.0, 0.0, 0.0)] * n_particles

    frames_sorted = sorted(animation.frames, key=lambda f: f.time)

    if animation.loop and animation.end > 0:
        t = t % animation.end

    if t <= frames_sorted[0].time:
        return list(frames_sorted[0].positions)
    if t >= frames_sorted[-1].time:
        return list(frames_sorted[-1].positions)

    for i in range(len(frames_sorted) - 1):
        f0 = frames_sorted[i]
        f1 = frames_sorted[i + 1]
        if f0.time <= t <= f1.time:
            span = f1.time - f0.time
            if span < 1e-9:
                return list(f0.positions)
            alpha = (t - f0.time) / span
            out = []
            for (x0, y0, z0), (x1, y1, z1) in zip(f0.positions, f1.positions):
                out.append((
                    x0 + (x1 - x0) * alpha,
                    y0 + (y1 - y0) * alpha,
                    z0 + (z1 - z0) * alpha,
                ))
            return out

    # 理论上 unreachable（前面已覆盖所有区间），保险返回最后一帧
    return list(frames_sorted[-1].positions)
