import logging
import logging.config
import os
import queue
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path

from app_settings_manager import AppSettingsManager, RunMode


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
