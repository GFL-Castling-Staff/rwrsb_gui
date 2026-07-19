"""
Helpers for locating bundled resources in source and PyInstaller builds.
"""
from pathlib import Path
import sys


def app_root():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent


def resource_path(*parts):
    return app_root().joinpath(*parts)


def app_version(default="dev"):
    """读取根目录 VERSION 文件。

    版本号只此一处来源，避免再出现代码里硬编码、发版时忘了同步的情况。
    VERSION 需由 .spec 打进包内，缺失时返回 default 而不是抛异常——
    版本号显示不出来不该拦住程序启动。
    """
    try:
        return resource_path("VERSION").read_text(encoding="utf-8").strip() or default
    except OSError:
        return default
