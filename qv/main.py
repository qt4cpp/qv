import logging
import sys

from PySide6 import QtWidgets

from viewer.volume_viewer import VolumeViewer
from app_settings_manager import AppSettingsManager
from logging_setup import LogSystem, apply_logging_policy
from ui.error_notifier import ErrorNotifier
from vtk_helpers import return_dicom_dir

logger = logging.getLogger(__name__)



def main():
    logs = LogSystem("qv")

    # 未処理例外はログを残す
    def excepthook(exctype, value, tb):
        logging.getLogger("qv").exception("Uncaught exception", exc_info=(exctype, value, tb))
    sys.excepthook = excepthook

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
    viewer = VolumeViewer(return_dicom_dir(), settings_mgr)

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
