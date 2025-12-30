# NOTE:
# Startup diagnostics (logging / Qt plugin checks) must be executed
#  before creating QApplication instance.

from qv.app.logging_setup import setup_startup_logging, install_qt_message_handler

setup_startup_logging(app_name="qv")
install_qt_message_handler()

import logging
import sys

from PySide6 import QtWidgets

from ui.mainwindow import MainWindow
from app.app_settings_manager import AppSettingsManager
from app.logging_setup import apply_logging_policy, LogSystem, install_qt_message_handler
from ui.dialogs.error_notifier import ErrorNotifier

logger = logging.getLogger(__name__)


def main():
    logs = LogSystem("qv")

    # 既存の QApplication インスタンスを取得。なければ新規作成。
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    # ビューアーを起動
    # viewer = VolumeViewer(dicom_dir)
    # 暫定的に自動的にDICOM画像を読み込むようにする。
    logger.info("App start")
    settings_mgr = AppSettingsManager()
    apply_logging_policy(logs, settings_mgr)
    ErrorNotifier.configure(settings_mgr)

    main_window = MainWindow(settings_mgr)

    # Qt 終了次にログを確実に止める
    app.aboutToQuit.connect(logs.stop)
    try:
        rc = app.exec()
        logger.info("App exit (rc=%s)", rc)
        sys.exit(rc)
    finally:
        logs.stop()  # 念のため


if __name__ == "__main__":
    main()
