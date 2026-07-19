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
# VOX 二进制写出
# ──────────────────────────────────────────────

_VOX_MAX_PALETTE = 255      # 色号 1..255，0 保留给空体素


def _build_palette(voxels: list) -> tuple[list, list]:
    """按首次出现顺序建调色板。

    返回 (palette, indices)：
      palette — list of (r,g,b,a) uint8，最多 255 项
      indices — 与 voxels 等长，值为 1-based 色号

    RWR 的 XML 颜色本身就是 uint8 调色板的浮点表示（值精确等于 n/255），
    所以这里是精确反查而非近似量化。颜色数超过 255 时直接抛错：正常模型
    远达不到这个量级（实测武器模型 73 色），触发说明数据来路异常，
    此时静默改色比报错更危险。
    """
    palette = []
    lookup = {}
    indices = []
    for v in voxels:
        a = v[6] if len(v) > 6 else 1.0
        key = tuple(max(0, min(255, int(round(float(c) * 255.0))))
                    for c in (v[3], v[4], v[5], a))
        idx = lookup.get(key)
        if idx is None:
            if len(palette) >= _VOX_MAX_PALETTE:
                raise ValueError(
                    f"颜色数超过 {_VOX_MAX_PALETTE}，VOX 调色板放不下，请先减色")
            palette.append(key)
            idx = len(palette)          # 1-based，与 parse_vox 的 rgba_raw[ci-1] 对齐
            lookup[key] = idx
        indices.append(idx)
    return palette, indices


def _vox_chunk(tag: bytes, content: bytes, children: bytes = b'') -> bytes:
    """拼一个 VOX chunk：tag + 内容长度 + 子块长度 + 内容 + 子块。"""
    return tag + struct.pack('<II', len(content), len(children)) + content + children


def write_vox(path: str | Path, voxels: list, trans_bias: int = 127) -> None:
    """把体素写成 MagicaVoxel .vox（格式版本 150）。

    只输出几何与颜色 —— .vox 装不下骨架和绑定关系，调用方需自行提示用户。
    坐标经 world_to_vox 反变换回 MagicaVoxel 空间，必须落在 0..255 内，
    否则通常是 trans_bias 选错了（人形 127 / 武器 49）。
    """
    if not voxels:
        raise ValueError("没有体素可导出")

    palette, indices = _build_palette(voxels)

    coords = []
    for v in voxels:
        vx, vy, vz = world_to_vox(round(v[0]), round(v[1]), round(v[2]), trans_bias)
        if not (0 <= vx <= 255 and 0 <= vy <= 255 and 0 <= vz <= 255):
            raise ValueError(
                f"体素 ({v[0]:g}, {v[1]:g}, {v[2]:g}) 变换后超出 VOX 范围 "
                f"({vx}, {vy}, {vz})；请检查 trans_bias（当前 {trans_bias}，"
                f"人形应为 127，武器应为 49）")
        coords.append((vx, vy, vz))

    # SIZE 取 max+1 而非紧包围盒：坐标是含 bias 的绝对值，
    # 缩包围盒会让读回时整体偏移，破坏 round-trip
    size = tuple(max(c[i] for c in coords) + 1 for i in range(3))

    xyzi = bytearray(struct.pack('<I', len(coords)))
    for (vx, vy, vz), ci in zip(coords, indices):
        xyzi += bytes((vx, vy, vz, ci))

    # RGBA 恒 256 项定长；palette[i] 对应色号 i+1，尾部补零
    pal = bytearray()
    for entry in palette:
        pal += bytes(entry)
    pal += b'\x00' * (1024 - len(pal))

    children = (_vox_chunk(b'SIZE', struct.pack('<III', *size))
                + _vox_chunk(b'XYZI', bytes(xyzi))
                + _vox_chunk(b'RGBA', bytes(pal)))
    blob = b'VOX ' + struct.pack('<I', 150) + _vox_chunk(b'MAIN', b'', children)

    Path(path).write_bytes(blob)
    logger.info("已写出: %s  (%d 体素, %d 色, size=%s)",
                path, len(coords), len(palette), size)


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
