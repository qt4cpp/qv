import logging
import logging.config
import os
import queue
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone


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
    print(level)
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

    def stop(self):
        self.listener.stop()
