# NOTE:
# Startup diagnostics (logging / Qt plugin checks) must be executed
#  before creating QApplication instance.

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s %(message)s")

from qv.app.logging_setup import setup_startup_logging, install_qt_message_handler, LogSystem
from qv.app.app_settings_manager import AppSettingsManager

settings_mgr = AppSettingsManager()

# run_mode に応じて startup_logging のレベルを決定
from qv.app.app_settings_manager import RunMode
if settings_mgr.run_mode in (RunMode.DEVELOPMENT, RunMode.VERBOSE):
    startup_console_level = logging.DEBUG
else:
    startup_console_level = logging.INFO

setup_startup_logging(app_name="qv", level_console=startup_console_level)
install_qt_message_handler()

from PySide6 import QtWidgets
from qv.ui.mainwindow import MainWindow
from qv.ui.dialogs.error_notifier import ErrorNotifier

logger = logging.getLogger(__name__)


def main():
    # 既存の QApplication インスタンスを取得。なければ新規作成。
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    # Initialize AppSettingsManager from settings
    logger.info("App start (run_mode=%s)", settings_mgr.run_mode)

    # Initialize LogSystem from settings
    logs = LogSystem("qv", settings=settings_mgr)

    ErrorNotifier.configure(settings_mgr)

    main_window = MainWindow(settings_mgr)

    # Qt 終了時にログを確実に止める
    app.aboutToQuit.connect(logs.stop)
    try:
        rc = app.exec()
        logger.info("App exit (rc=%s)", rc)
        sys.exit(rc)
    finally:
        logs.stop()  # 念のため


if __name__ == "__main__":
    main()
