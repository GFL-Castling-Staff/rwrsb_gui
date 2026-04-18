"""
file_dialogs.py
Windows 原生文件对话框（ctypes + comdlg32 GetOpenFileNameW / GetSaveFileNameW）。
非 Windows 平台函数返回 None，调用方应保留文本输入框作为兜底。
"""
import ctypes
import ctypes.wintypes as wt
import sys
import logging
from typing import Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


def _is_supported() -> bool:
    return sys.platform == "win32"


# OPENFILENAMEW 结构体（参考 Win32 CommDlg.h）
class _OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize",       wt.DWORD),
        ("hwndOwner",         wt.HWND),
        ("hInstance",         wt.HINSTANCE),
        ("lpstrFilter",       wt.LPCWSTR),
        ("lpstrCustomFilter", wt.LPWSTR),
        ("nMaxCustFilter",    wt.DWORD),
        ("nFilterIndex",      wt.DWORD),
        ("lpstrFile",         wt.LPWSTR),
        ("nMaxFile",          wt.DWORD),
        ("lpstrFileTitle",    wt.LPWSTR),
        ("nMaxFileTitle",     wt.DWORD),
        ("lpstrInitialDir",   wt.LPCWSTR),
        ("lpstrTitle",        wt.LPCWSTR),
        ("Flags",             wt.DWORD),
        ("nFileOffset",       wt.WORD),
        ("nFileExtension",    wt.WORD),
        ("lpstrDefExt",       wt.LPCWSTR),
        ("lCustData",         ctypes.c_void_p),
        ("lpfnHook",          ctypes.c_void_p),
        ("lpTemplateName",    wt.LPCWSTR),
        ("pvReserved",        ctypes.c_void_p),
        ("dwReserved",        wt.DWORD),
        ("FlagsEx",           wt.DWORD),
    ]


# Flags
_OFN_FILEMUSTEXIST   = 0x00001000
_OFN_PATHMUSTEXIST   = 0x00000800
_OFN_HIDEREADONLY    = 0x00000004
_OFN_EXPLORER        = 0x00080000
_OFN_OVERWRITEPROMPT = 0x00000002


def _build_filter(filters: Sequence[Tuple[str, str]]) -> ctypes.Array:
    """
    filters = [("VOX files", "*.vox"), ("All files", "*.*")]
    返回 ctypes wide buffer，格式 "VOX files\\0*.vox\\0All files\\0*.*\\0\\0"
    注意：双 null 结尾，不能用 c_wchar_p（会在第一个 \\0 截断）
    """
    parts = []
    for label, pattern in filters:
        parts.append(label)
        parts.append(pattern)
    s = "\0".join(parts) + "\0\0"   # 末尾 double null
    buf = ctypes.create_unicode_buffer(s, len(s))
    return buf


def _common_ofn(title: str, filters, initial_path: str = "") -> "_OPENFILENAMEW":
    path_buf = ctypes.create_unicode_buffer(1024)
    if initial_path:
        init = initial_path[:1023]
        for i, ch in enumerate(init):
            path_buf[i] = ch
    filter_buf = _build_filter(filters)

    ofn = _OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(_OPENFILENAMEW)
    ofn.hwndOwner = None
    ofn.lpstrFilter = ctypes.cast(filter_buf, wt.LPCWSTR)
    ofn.lpstrFile = ctypes.cast(path_buf, wt.LPWSTR)
    ofn.nMaxFile = 1024
    ofn.lpstrTitle = title
    ofn.Flags = _OFN_EXPLORER | _OFN_HIDEREADONLY

    # 持有引用防止 GC 在调用 API 前回收 buffer
    ofn._path_buf = path_buf
    ofn._filter_buf = filter_buf
    return ofn


def open_file_dialog(
    title: str,
    filters: Sequence[Tuple[str, str]],
    initial_path: str = "",
) -> Optional[str]:
    """
    弹 Windows 原生"打开文件"对话框。返回用户选择的路径；用户取消返回 None。
    filters: [("VOX files", "*.vox"), ...]
    非 Windows 平台直接返回 None。
    """
    if not _is_supported():
        return None

    try:
        comdlg32 = ctypes.windll.comdlg32
    except (OSError, AttributeError):
        logger.warning("comdlg32 not available, falling back to text input")
        return None

    ofn = _common_ofn(title, filters, initial_path)
    ofn.Flags |= _OFN_FILEMUSTEXIST | _OFN_PATHMUSTEXIST

    GetOpenFileNameW = comdlg32.GetOpenFileNameW
    GetOpenFileNameW.argtypes = [ctypes.POINTER(_OPENFILENAMEW)]
    GetOpenFileNameW.restype = wt.BOOL

    ok = GetOpenFileNameW(ctypes.byref(ofn))
    if not ok:
        err = comdlg32.CommDlgExtendedError()
        if err != 0:
            logger.warning("GetOpenFileNameW failed, CommDlgExtendedError=%d", err)
        return None  # 用户取消或错误

    return ofn._path_buf.value


def save_file_dialog(
    title: str,
    filters: Sequence[Tuple[str, str]],
    initial_path: str = "",
    default_ext: str = "",
) -> Optional[str]:
    """
    弹 Windows 原生"保存文件"对话框。返回用户选择的路径；用户取消返回 None。
    default_ext 例如 "xml"，会自动补后缀（不需要带点）。
    """
    if not _is_supported():
        return None

    try:
        comdlg32 = ctypes.windll.comdlg32
    except (OSError, AttributeError):
        logger.warning("comdlg32 not available, falling back to text input")
        return None

    ofn = _common_ofn(title, filters, initial_path)
    ofn.Flags |= _OFN_OVERWRITEPROMPT | _OFN_PATHMUSTEXIST
    if default_ext:
        ofn.lpstrDefExt = default_ext

    GetSaveFileNameW = comdlg32.GetSaveFileNameW
    GetSaveFileNameW.argtypes = [ctypes.POINTER(_OPENFILENAMEW)]
    GetSaveFileNameW.restype = wt.BOOL

    ok = GetSaveFileNameW(ctypes.byref(ofn))
    if not ok:
        err = comdlg32.CommDlgExtendedError()
        if err != 0:
            logger.warning("GetSaveFileNameW failed, CommDlgExtendedError=%d", err)
        return None

    return ofn._path_buf.value
