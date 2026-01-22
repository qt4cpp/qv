from __future__ import annotations

import logging
import logging.config
import os
import queue
import sys
import traceback
import warnings
from dataclasses import dataclass
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from dataclasses import dataclass, asdict

import faulthandler

from qv.app.app_settings_manager import AppSettingsManager, RunMode


@dataclass(frozen=True)
class LogPaths:
    log_file: Path
    crash_file: Path
    log_dir: Path

@dataclass(frozen=True)
class FileLogSettings:
    filename: str
    maxBytes: int
    backupCount: int
    encoding: str
    format: str
    datefmt: str


LOG_FORMAT = "%(asctime)s.%(msecs)03d [%(levelname)s] %(process)d %(threadName)s %(name)s %(message)s"
LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"
STARTUP_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


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
    Logging setup while startup.
    - Rotating file handler
    - uncaught exception logging
    - faulthandler (crash logging)
    """
    log_dir = _find_writable_log_dir(app_name)
    log_file = log_dir / f"{app_name}.log"
    crash_file = log_dir / f"{app_name}.crash.log"

    root = logging.getLogger()
    root.setLevel(min(level_file, level_console))

    # Prevent duplicate registration of handlers.
    if root.handlers:
        for h in list(root.handlers):
            root.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass

    fmt = logging.Formatter(STARTUP_LOG_FORMAT)

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
        logging.getLogger(__name__).exception("Failed to enable faulthandler.")

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


def _compute_levels_from_settings(settings: AppSettingsManager) -> tuple[int, int, int]:
    """Compute (root, console, file) levels from run_mode with optional env overriedes.

    Single source of truth for log level policy.

    Env (non-persistent):
      - QV_LOG_LEVEL : override root+console
      - QV_LOG_CONSOLE_LEVEL : override console only
      - QV_LOG_FILE_LEVEL : override file only

    Returns:
        (root_level, console_level, file_level) as logging.DEBUG/INFO/etc.
    """
    mode = settings.run_mode

    if mode in (RunMode.DEVELOPMENT, RunMode.VERBOSE):
        root = logging.DEBUG
        console = logging.DEBUG
        file = logging.DEBUG
    else:  # PRODUCTION
        root = logging.INFO
        console = logging.INFO
        file = logging.DEBUG

    def _env_level(name: str) -> int | None:
        v = os.getenv(name)
        if not v:
            return None
        return getattr(logging, v.upper(), None)

    env_root = _env_level("QV_LOG_LEVEL")
    if env_root is not None:
        logging.debug("QV_LOG_LEVEL=%s", env_root)
        root = env_root
        console = env_root

    env_console = _env_level("QV_LOG_CONSOLE_LEVEL")
    if env_console is not None:
        logging.debug("QV_LOG_CONSOLE_LEVEL=%s", env_console)
        console = env_console

    env_file = _env_level("QV_LOG_FILE_LEVEL")
    if env_file is not None:
        logging.debug("QV_LOG_FILE_LEVEL=%s", env_file)
        file = env_file

    root = min(root, console, file)
    return root, console, file


def build_config(
        app_name: str,
        root_level: int,
        console_level: int,
        log_dir: Path | None = None,
) -> dict:
    """Build a logging config dict (wiring only, no policy logic).

    Args:
          app_name: Application name
          root_level: Root logger level
          console_level: Console handler level
          log_dir: Log directory. Defaults to default_log_dir(app_name)

    Returns:
          Dict config for logging.config.dictConfig()
    """
    log_dir = log_dir or default_log_dir(app_name)
    log_file = str(log_dir / f"{app_name}.log")

    fmt = LOG_FORMAT
    datefmt = LOG_DATEFMT

    # Convert int level to string for dictConfig
    root_level_name = logging.getLevelName(root_level)
    console_level_name = logging.getLevelName(console_level)

    file_settings = FileLogSettings(
        filename=log_file,
        maxBytes=1024 * 1024 * 5,
        backupCount=int(os.getenv("QV_LOG_BACKUP_COUNT", 5)),
        encoding="utf-8",
        format=fmt,
        datefmt=datefmt,
    )

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
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": console_level_name},
        },
        "root": {"level": root_level_name, "handlers": ["queue", "console"]},
        # キュー先でファイルに書き込む
        "_file_settings": asdict(file_settings),
    }


class LogSystem:
    """QueueListener を持つ薄いラッパ

    - 通常経路: settings からログレベルを決定
    - 例外経路: テスト/ツール向けに from_levels を用意
    """

    def __init__(self, app_name: str, *, settings: AppSettingsManager):
        """Initialize LogSystem with settings (production path).

        Args:
            app_name: Application name
            settings: AppSettingsManager to derive log levels from run_mode
        """
        root_level, console_level, file_level = _compute_levels_from_settings(settings)

        logging.info(
            "LogSystem initialized: run_mode=%s -> root=%s, console=%s, file=%s",
            settings.run_mode,
            logging.getLevelName(root_level),
            logging.getLevelName(console_level),
            logging.getLevelName(file_level)
        )
        self._init_with_levels(app_name, root_level, console_level, file_level)

    @classmethod
    def from_levels(
            cls,
            app_name: str,
            *,
            root_level: int = logging.INFO,
            console_level: int = logging.INFO,
            file_level: int = logging.DEBUG
    ) -> "LogSystem":
        """Create LogSystem with explicit levels (test/tool escape hatch).

        Args:
            app_name: Application name
            root_level: Root logger level
            console_level: Console handler level
            file_level: File handler level

        Returns:
            LogSystem instance
        """
        instance = cls.__new__(cls)
        instance._init_with_levels(app_name, root_level, console_level, file_level)
        return instance

    def _init_with_levels(
            self,
            app_name: str,
            root_level: int,
            console_level: int,
            file_level: int
    ) -> None:
        """Internal initialization with explicit levels."""

        # Clear existing handlers Before dictConfig to avoid conflicts
        root_logger = logging.getLogger()
        if root_logger.handlers:
            for h in list(root_logger.handlers):
                root_logger.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass

        cfg = build_config(app_name, root_level, console_level)
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
            # QueueHandler 以外のStreamHandler を探す
            if isinstance(h, logging.StreamHandler) and not isinstance(h, QueueHandler):
                self._console_handler = h
                break

        # ファイル側ハンドラを準備する
        file_settings = cfg["_file_settings"]
        file_handler = RotatingFileHandler(
            file_settings["filename"],
            maxBytes=file_settings["maxBytes"],
            backupCount=file_settings["backupCount"],
            encoding=file_settings["encoding"],
        )
        file_handler.setFormatter(logging.Formatter(file_settings["format"], file_settings["datefmt"]))
        file_handler.setLevel(file_level)
        self._file_handler = file_handler

        self.listener = QueueListener(qh.queue, file_handler, respect_handler_level=True)
        self.listener.start()

    def apply_levels(self, root_level: int, console_level:int | None = None, file_level: int | None = None) -> None:
        """起動後にログレベルを更新する（主にテスト･デバッグ用）"""
        logging.getLogger().setLevel(root_level)
        if self._console_handler is not None and console_level is not None:
            self._console_handler.setLevel(console_level)
        if self._file_handler is not None and file_level is not None:
            self._file_handler.setLevel(file_level)
        logging.debug("Log levels updated: root=%s, console=%s, file=%s", root_level, console_level, file_level)

    def stop(self):
        self.listener.stop()


def apply_logging_policy(logs: LogSystem, settings: AppSettingsManager) -> None:
    """Deprecated: LogSystemの初期化時にsettings を渡すことを推奨。

    後方互換性のため残しているが、新規コードでは使用しない。
    代わりに、 LogSystem(app_name, settings=settings) を使用する。
    """
    warnings.warn(
        "apply_logging_policy() is deprecated."
        "Pass settings to LogSystem(app_name, settings=...) instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    root, console, file = _compute_levels_from_settings(settings)
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
