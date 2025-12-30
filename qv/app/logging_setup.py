from __future__ import annotations

import logging
import logging.config
import os
import queue
import sys
import traceback
from dataclasses import dataclass
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path

import faulthandler

from app.app_settings_manager import AppSettingsManager, RunMode


@dataclass(frozen=True)
class LogPaths:
    log_file: Path
    crash_file: Path
    log_dir: Path


def _project_root_from_package() -> Path:
    """
    In development, this function returns the path to the project root directory.
    If the project structure is different, override this function.
    """
    # qv/app/loggin_setup.py -> parents[2] is assumed to be the project root.
    #   parents[0] = app
    #   parents[1] = qv
    #   parents[2] = project root
    return Path(__file__).resolve().parents[2]


def _app_base_dir() -> Path:
    """
    In frozen mode, this function returns the path to the app directory.
      (in onedir mode, this is the same as the dist directory,
       in onedir mode, in place of the exe file.)
    In development, this function returns the path to the project root directory.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _project_root_from_package()


def _find_writable_log_dir(app_name: str) -> Path:
    """
    First, app_base_dir/logs
    Second, user's home directory
    """
    candidates = [
        _app_base_dir() / "logs",
        Path.home() / f".{app_name.lower()}" / "logs",
    ]
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            test = d / ".write_test"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            return d
        except Exception:
            continue
    # Finally, current directory.
    d = Path.cwd() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_startup_logging(
        app_name: str,
        *,
        level_file: int = logging.DEBUG,
        level_console: int = logging.INFO,
        max_bytes: int = 2_000_000,
        backup_count: int = 5,
    ) -> LogPaths:
    """
    Startup logging setup.
    - Rotating file handler
    - uncaught exception logging
    - faulthandler (crash logging)
    """
    log_dir = _find_writable_log_dir(app_name)
    log_file = log_dir / f"{app_name}.log"
    crash_file = log_dir / f"{app_name}.crash.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Prevent duplicate registration of handlers.
    if root.handlers:
        root.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # File (rotating)
    fh = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    fh.setLevel(level_file)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level_console)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # crash log
    try:
        crash_file.parent.mkdir(parents=True, exist_ok=True)
        f = open(crash_file, "w", encoding="utf-8")
        faulthandler.enable(file=f)
        # Prevent GC keeping reference to the file object.
        root._qv_crash_fh = f
    except Exception:
        pass

    # logging uncaught exception
    def _excepthook(exc_type, exc, tb):
        logging.critical(
            "Uncaught exception: \n%s",
            "".join(traceback.format_exception(exc_type, exc, tb)),
        )

    sys.excepthook = _excepthook

    # Diagnostic info after launch
    logging.info("=================================================")
    logging.info("%s starting...", app_name)
    logging.info("frozen=%s", getattr(sys, "frozen", False))
    logging.info("sys.executable=%s", sys.executable)
    logging.info("cwd=%s", os.getcwd())
    logging.info("log_file=%s", log_file)
    logging.info("crash_file=%s", crash_file)
    logging.info("app_base_dir=%s", _app_base_dir())
    logging.info("sys.path[0:5]=%s", sys.path[:5])
    logging.info("=================================================")

    return LogPaths(log_file=log_file, crash_file=crash_file, log_dir=log_dir)


def default_log_dir(app_name: str) -> Path:
    base = Path.home() / "Library" / "Logs" / app_name
    base.mkdir(parents=True, exist_ok=True)
    return base


def build_config(app_name: str, level: str = None, log_dir: Path | None = None) -> dict:
    """Build a logging config dict."""
    level = level or os.getenv("QV_LOG_LEVEL", "INFO").upper()
    log_dir = log_dir or default_log_dir(app_name)
    log_file = str(log_dir / f"{app_name}.log")

    fmt = "%(asctime)s.%(msecs)03dZ %(levelname)s %(process)d %(threadName)s %(name)s %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": fmt, "datefmt": datefmt,
            },
        },
        "handlers": {
            # キューを使う
            "queue": {"class": "logging.handlers.QueueHandler", "queue": queue.Queue(-1)},
            "console": {"class": "logging.StreamHandler", "formatter": "standard", "level": "INFO"},
        },
        "root": {"level": level, "handlers": ["queue", "console"]},
        # キュー先でファイルに書き込む
        "_file_settings": {
            "filename": log_file,
            "maxBytes": 1024 * 1024 * 5,
            "backupCount": int(os.getenv("QV_LOG_BACKUP_COUNT", 5)),
            "encoding": "utf-8",
            "format": fmt,
            "datefmt": datefmt
        },
    }


class LogSystem:
    """QueueListener を持つ薄いラッパ"""
    def __init__(self, app_name: str, level: str | None = None):
        cfg = build_config(app_name, level)
        logging.config.dictConfig(cfg)

        # dictConfigでは QueueHandler の queue取得が面倒なので探す
        qh: QueueHandler | None = None
        for h in logging.getLogger().handlers:
            if isinstance(h, QueueHandler):
                qh = h
                break
        if qh is None:
            raise RuntimeError("QueueHandler not found.")

        # 後からレベルを変更するための変数
        self._console_handler = None
        self._file_handler = None

        root_logger = logging.getLogger()
        for h in root_logger.handlers:
            if self._console_handler is None and isinstance(h, logging.StreamHandler):
                self._console_handler = h
            if self._file_handler is None and isinstance(h, logging.FileHandler):
                self._file_handler = h

        # ファイル側ハンドラを準備する
        file_settings = cfg["_file_settings"]
        file_handler = RotatingFileHandler(
            file_settings["filename"],
            maxBytes=file_settings["maxBytes"],
            backupCount=file_settings["backupCount"],
            encoding=file_settings["encoding"],
        )
        file_handler.setFormatter(logging.Formatter(file_settings["format"], file_settings["datefmt"]))

        self.listener = QueueListener(qh.queue, file_handler, respect_handler_level=True)
        self.listener.start()

    def apply_levels(self, root_level: int, console_level:int | None = None, file_level: int | None = None) -> None:
        """起動後にログレベルを更新する"""
        logging.getLogger().setLevel(root_level)
        if self._console_handler is not None and console_level is not None:
            self._console_handler.setLevel(console_level)
        if self._file_handler is not None and file_level is not None:
            self._file_handler.setLevel(file_level)

    def stop(self):
        self.listener.stop()


def apply_logging_policy(logs: LogSystem, settings: AppSettingsManager) -> None:
    """環境に応じて、ログの出力レベルを切り替える"""
    mode = getattr(settings, "run_mode", None)
    if mode is None:
        mode = RunMode.DEVELOPMENT if getattr(settings, "dev_mode", False) else RunMode.PRODUCTION

    if mode == RunMode.DEVELOPMENT or mode == RunMode.VERBOSE:
        root = logging.DEBUG
        console = logging.DEBUG
        file = logging.DEBUG
    else:
        root = logging.DEBUG
        console = logging.INFO
        file = logging.DEBUG

    logs.apply_levels(root_level=root, console_level=console, file_level=file)


def install_qt_message_handler():
    try:
        from PySide6.QtCore import qInstallMessageHandler

        def handler(msg_type, context, message):
            logging.getLogger("Qt").error(message)

        qInstallMessageHandler(handler)
        logging.getLogger("Qt").info("Qt message handler installed.")
    except Exception:
        logging.getLogger(__name__).exception("Failed to install Qt message handler.")
