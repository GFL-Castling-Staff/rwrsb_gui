"""
xml_io.py
VOX 解析、XML 读写、最终合并输出
坐标变换 trans_bias 可配置（默认127，武器模型可改49）
"""
import logging
import struct
import re
import numpy as np
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 坐标变换（与 rwrwc.py 保持一致，bias 可配置）
# ──────────────────────────────────────────────

# VOX → 工具内部坐标  (读入时使用)
def vox_to_world(x, y, z, trans_bias=127):
    """
    MagicaVoxel 坐标系 → RWR 世界坐标系
    先减 bias，再做旋转矩阵（rwrwc.py TransformationReverse）
    """
    vx = x - trans_bias
    vy = y - trans_bias
    vz = z - trans_bias
    # matrix inverse of rwrcw.py Transformation:
    #   Transformation: [x, -z, y] + bias
    #   Reverse:        [x, z, -y]
    return (vx, vz, -vy)

# 工具内部坐标 → VOX  (写出时使用，供调试/重新导出用)
def world_to_vox(x, y, z, trans_bias=127):
    return (int(x) + trans_bias,
            int(-z) + trans_bias,
            int(y) + trans_bias)

# XML 坐标直接就是 RWR 世界坐标，无需变换
def xml_to_world(x, y, z):
    return (float(x), float(y), float(z))

def world_to_xml(x, y, z):
    return (x, y, z)


# ──────────────────────────────────────────────
# VOX 二进制解析（格式版本150，兼容MV旧版）
# ──────────────────────────────────────────────

def parse_vox(path: str | Path, trans_bias: int = 127) -> list[tuple[float, ...]]:
    """
    解析 .vox 文件，返回:
      voxels: list of (wx, wy, wz, r, g, b, a)  float rgb [0,1]
    """
    data = Path(path).read_bytes()
    arr = np.frombuffer(data, dtype=np.uint8)

    # 检查魔数
    magic = bytes(arr[0:4])
    if magic != b'VOX ':
        raise ValueError(f"不是有效的 .vox 文件: {path}")

    def read_uint32(offset):
        return struct.unpack_from('<I', arr, offset)[0]

    def read_str(offset, n):
        return bytes(arr[offset:offset+n]).decode('ascii', errors='replace')

    # 遍历 chunk
    addr = 8
    fsize = len(arr)
    chunks = {}

    while addr < fsize:
        if addr + 12 > fsize:
            break
        tag = read_str(addr, 4)
        size_content = read_uint32(addr + 4)
        # size_subcont = read_uint32(addr + 8)
        start = addr + 12
        end = start + size_content
        chunks[tag] = (start, end)
        addr = end

    if 'XYZI' not in chunks or 'RGBA' not in chunks:
        raise ValueError("VOX 文件缺少 XYZI 或 RGBA chunk")

    # 解析 XYZI
    xi_start, xi_end = chunks['XYZI']
    num_voxels = read_uint32(xi_start)
    xyzi_raw = arr[xi_start+4 : xi_start+4 + num_voxels*4].reshape(num_voxels, 4)

    # 解析 RGBA 调色板 (256色，每色4字节 RGBA uint8)
    ra_start, ra_end = chunks['RGBA']
    rgba_raw = arr[ra_start : ra_start + 1024].reshape(256, 4).astype(float) / 255.0

    # 组装体素列表
    voxels = []
    for vx, vy, vz, ci in xyzi_raw:
        wx, wy, wz = vox_to_world(int(vx), int(vy), int(vz), trans_bias)
        r, g, b, a = rgba_raw[ci - 1]   # 调色板索引从1开始
        voxels.append((wx, wy, wz, float(r), float(g), float(b), float(a)))

    return voxels


# ──────────────────────────────────────────────
# XML 解析
# ──────────────────────────────────────────────

def parse_xml(path: str | Path) -> tuple[list[tuple[float, ...]], dict[str, list], dict[int, int]]:
    """
    解析 RWR 模型 XML，返回:
      voxels:   list of (x, y, z, r, g, b, a)  float
      skeleton: {'particles': [...], 'sticks': [...]}
      bindings: dict {voxel_index: bone_constraint_index}
                bone_constraint_index 是 skeleton particles 列表中的顺序索引

    容错：部分旧工具产出的 XML 会在每个 `>` 之后、换行之前注入 1-2 个垃圾字符
    （如 "GG"/"FF"/":"/"C" 等）。RWR 模型 XML 所有元素都是容器或自闭合/属性式，
    没有 inline text content，所以可以安全地把 `>` 到行尾的非 `<` 非空白
    字符清除掉；对正常 XML 此操作是 no-op。
    """
    raw = Path(path).read_text(encoding='utf-8', errors='replace')
    cleaned = re.sub(r'>([^\r\n<>]+)(?=[\r\n])', '>', raw)
    if cleaned != raw:
        logger.info("已清理 XML 尾部垃圾字符: %s", path)

    root = ET.fromstring(cleaned)

    # ── 体素 ──
    voxels = []
    for v in root.iterfind('voxels/voxel'):
        x, y, z = float(v.get('x')), float(v.get('y')), float(v.get('z'))
        r, g, b, a = float(v.get('r')), float(v.get('g')), float(v.get('b')), float(v.get('a', '1.0'))
        voxels.append((x, y, z, r, g, b, a))

    # ── 骨骼 ──
    skeleton = {'particles': [], 'sticks': []}
    skel_elem = root.find('skeleton')
    if skel_elem is not None:
        for p in skel_elem.iterfind('particle'):
            skeleton['particles'].append({
                'id':           int(p.get('id')),
                'name':         p.get('name', ''),
                'invMass':      float(p.get('invMass', '10')),
                'bodyAreaHint': int(p.get('bodyAreaHint', '1')),
                'x': float(p.get('x', '0')),
                'y': float(p.get('y', '0')),
                'z': float(p.get('z', '0')),
            })
        for s in skel_elem.iterfind('stick'):
            skeleton['sticks'].append({
                'a': int(s.get('a')),
                'b': int(s.get('b')),
            })

    # ── 绑骨 ──
    # constraintIndex 是 particles 列表的顺序索引（0-based）
    bindings = {}
    svb = root.find('skeletonVoxelBindings')
    if svb is not None:
        for group in svb.iterfind('group'):
            ci = int(float(group.get('constraintIndex', '-1')))
            for vox in group.iterfind('voxel'):
                idx = int(vox.get('index'))
                bindings[idx] = ci

    return voxels, skeleton, bindings


# ──────────────────────────────────────────────
# XML 输出（合并完整文件）
# ──────────────────────────────────────────────

def write_xml(path: str | Path, voxels: list, skeleton: dict, bindings: dict) -> None:
    """
    输出合并后完整 XML。
    voxels:   list of (x,y,z,r,g,b,a)
    skeleton: {'particles': [...], 'sticks': [...]}
    bindings: dict {voxel_index: constraint_index}
    """
    root = ET.Element('model')

    # ── voxels ──
    voxels_elem = ET.SubElement(root, 'voxels')
    for x, y, z, r, g, b, a in voxels:
        ET.SubElement(voxels_elem, 'voxel', {
            'r': f'{r:.6f}', 'g': f'{g:.6f}', 'b': f'{b:.6f}', 'a': f'{a:.6f}',
            'x': str(int(round(x))),
            'y': str(int(round(y))),
            'z': str(int(round(z))),
        })

    # ── skeleton ──
    skel_elem = ET.SubElement(root, 'skeleton')
    for p in skeleton.get('particles', []):
        ET.SubElement(skel_elem, 'particle', {
            'bodyAreaHint': str(p['bodyAreaHint']),
            'id':           str(p['id']),
            'invMass':      f"{p['invMass']:.6f}",
            'name':         p['name'],
            'x':            f"{p['x']:.6f}",
            'y':            f"{p['y']:.6f}",
            'z':            f"{p['z']:.6f}",
        })
    for s in skeleton.get('sticks', []):
        ET.SubElement(skel_elem, 'stick', {
            'a': str(s['a']),
            'b': str(s['b']),
        })

    # ── skeletonVoxelBindings ──
    svb_elem = ET.SubElement(root, 'skeletonVoxelBindings')
    # 按 constraintIndex 分组
    groups = {}
    for vox_idx, ci in bindings.items():
        groups.setdefault(ci, []).append(vox_idx)

    for ci in sorted(groups.keys()):
        grp = ET.SubElement(svb_elem, 'group', {'constraintIndex': str(ci)})
        for vi in sorted(groups[ci]):
            ET.SubElement(grp, 'voxel', {'index': str(vi)})

    # 美化输出
    xml_str = ET.tostring(root, encoding='unicode')
    pretty = minidom.parseString(xml_str).toprettyxml(indent='\t')
    # 去掉 minidom 自动加的 <?xml?> 声明首行（RWR不需要）
    lines = pretty.split('\n')
    if lines[0].startswith('<?xml'):
        lines = lines[1:]
    pretty = '\n'.join(lines)

    Path(path).write_text(pretty, encoding='utf-8')
    logger.info("已写出: %s  (%d 体素, %d 已绑定)", path, len(voxels), len(bindings))
