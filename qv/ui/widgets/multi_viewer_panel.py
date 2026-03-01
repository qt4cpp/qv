from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from qv.app.app_settings_manager import AppSettingsManager
from qv.viewers.mpr_viewer import MprViewer
from qv.viewers.volume_viewer import VolumeViewer


class MultiViewerPanel(QtWidgets.QWidget):
    """Container widget for multiple viewers."""

    def __init__(self, settings_mgr: AppSettingsManager | None = None,
                 parent: QtWidgets.QWidget | None = None,
                 ) -> None:
        super().__init__(parent)
        self.setting = settings_mgr or AppSettingsManager()

        self._viewers: dict[str, QtWidgets.QWidget] = {}

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)

        self.volume_viewer = VolumeViewer(settings_manager=self.setting, parent=self)
        self.mpr_viewer = MprViewer(settings_manager=self.setting, parent=self)

        self.add_viewer(self.volume_viewer, "volume")
        self.add_viewer(self.mpr_viewer, "mpr_axial")

        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        layout.addWidget(self.splitter)

    def add_viewer(self, viewer: QtWidgets.QWidget, name: str) -> None:
        """
        Add Viewer widget into panel

        This API is kept generic for future 3/4-view expansion.
        """
        if name in self._viewers:
            raise ValueError(f"Viewer with name '{name}' already exists.")

        self._viewers[name] = viewer
        self.splitter.addWidget(viewer)
