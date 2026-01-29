"""Base viewer with 3D camera controller."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6 import QtCore

from qv.app.app_settings_manager import AppSettingsManager
from qv.viewers.base_viewer import BaseViewer
from qv.viewers.camera.camera_state import CameraAngle
from qv.viewers.camera.camera_controller import CameraController


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class Camera3DViewer(BaseViewer):
    """
    Base viewer with 3D camera controller.

    Provides:
    - AppSettingsManager (self.setting)
    - CameraController (self.camera_controller)
    - cameraAngleChanged signal
    """

    cameraAngleChanged = QtCore.Signal(object)

    def __init__(self,
                 settings_manager: AppSettingsManager | None = None,
                 parent=None) -> None:
        super().__init__(parent=parent)

        self.setting = settings_manager or AppSettingsManager()

        self.camera_controller = CameraController(
            self.renderer.GetActiveCamera(),
            self.renderer
        )
        self.camera_controller.add_angle_changed_callback(self._on_camera_angle_changed)

        logger.debug("[Camera3DViewer] Initialized.")

    def _on_camera_angle_changed(self, new_angle: CameraAngle) -> None:
        self.cameraAngleChanged.emit(new_angle)