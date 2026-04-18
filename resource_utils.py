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
