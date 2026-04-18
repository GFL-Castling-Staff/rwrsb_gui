"""
logger_setup.py
日志初始化模块 —— 文件轮转 + 控制台 + 未捕获异常 hook
在 main.py 任何其他项目模块 import 之前调用 init_logger()
"""
import logging
import logging.handlers
import os
import sys
import tempfile
from pathlib import Path


def init_logger() -> Path:
    """
    初始化 root logger。返回实际使用的日志目录（供 UI 展示）。
    在 main.py 任何其他 import 之前调用。
    """
    log_dir = _pick_log_dir()
    log_file = log_dir / "rwrsb.log"

    # 支持环境变量覆盖日志级别
    level_name = os.environ.get("RWRSB_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # 文件 handler（轮转）
    try:
        fh = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=5_000_000,
            backupCount=5,
            encoding="utf-8",
            delay=True,
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass  # 日志系统本身不能把程序搞崩

    # 控制台 handler（源码运行时有用；打包 console=False 会被吞）
    try:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    except Exception:
        pass

    # 未捕获异常 hook（仅对主线程 Python 异常有效；GLFW 回调异常靠各自 try/except）
    def _excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("rwrsb").critical(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_tb)
        )

    sys.excepthook = _excepthook

    logger = logging.getLogger("rwrsb")
    logger.info("rwrsb_gui started, log dir: %s", log_dir)
    return log_dir


def _pick_log_dir() -> Path:
    """依次尝试候选目录，选择第一个可写的。"""
    candidates = []

    # 1. 可执行文件/源码同级的 logs/
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "logs")
    else:
        candidates.append(Path(__file__).parent / "logs")

    # 2. LOCALAPPDATA（或 home）下的 rwrsb_gui/logs
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        candidates.append(Path(localappdata) / "rwrsb_gui" / "logs")
    else:
        candidates.append(Path.home() / "rwrsb_gui" / "logs")

    # 3. 系统临时目录
    candidates.append(Path(tempfile.gettempdir()) / "rwrsb_gui" / "logs")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".write_test"
            test_file.touch()
            test_file.unlink()
            return candidate
        except Exception:
            continue

    # 最终兜底：返回 temp 路径（即使不可写也不抛异常）
    return Path(tempfile.gettempdir()) / "rwrsb_gui" / "logs"
