from __future__ import annotations
import os, time, traceback, logging
from typing import Optional
from PySide6.QtWidgets import QApplication, QMessageBox, QErrorMessage
from PySide6.QtCore import QObject, QTimer, Qt


logger = logging.getLogger(__name__)


class ErrorNotifier(QObject):
    _instance: Optional[ErrorNotifier] = None

    def __init__(self):
        super().__init__()
        self.dev_mode = str(os.getenv("QV_DEV", "")).lower() in ("1", "true", "yes")
        self._last_shown: dict[str, float] = {}  # msg -> timestamp
        self._suppress_window = QErrorMessage()  # 重複抑制に強い標準にダイアログ

    @classmethod
    def instance(cls) -> ErrorNotifier:
        if cls._instance is None:
            cls._instance = ErrorNotifier()
        return cls._instance

    def notify(self,
               title: str,
               msg: str,
               *,
               detail: Optional[str] = None,
               exc_info: Optional[tuple] = None,
               severity: str = "error",
               dedup_seconds: float = 2.0,
               ) -> None:
        if exc_info:
            logger.exception("%s: %s", title, msg, exc_info=exc_info)
        else:
            if severity in ("error", "critical"):
                logger.error("%s: %s", title, msg)
            elif severity == "warning":
                logger.warning("%s: %s", title, msg)
            else:
                logger.info("%s: %s", title, msg)

        # 重複抑制
        now = time.monotonic()
        key = f"{severity}:{title}:{msg}"
        last = self._last_shown.get(key, 0.0)
        if now - last < dedup_seconds:
            return
        self._last_shown[key] = now

        # execute on GUI thread
        def _show():
            if severity in ("error", "critical"):
                box = QMessageBox()
                box.setIcon(QMessageBox.Critical if severity == "critical"
                            else QErrorMessage.Warning)
                box.setWindowTitle(title)
                box.setText(msg)

                det = detail
                if exc_info and not det:
                    det = "".join(traceback.format_exception(*exc_info))
                if det:
                    box.setDetailedText(det)
                    if self.dev_mode:
                        box.setTextInteractionFlags(Qt.TextSelectableByMouse)
                box.exec()
            elif severity == "warning":
                self._suppress_window.showMessage(f"{title}: {msg}")
            else:
                app: QApplication = QApplication.instance()
                w = app.activeWindow() if app else None
                if hasattr(w, "statusBar"):
                    try:
                        w.statusBar().showMessage(f"{title}: {msg}", 5000)
                    except Exception:
                        pass

        QTimer.singleShot(0, _show)
