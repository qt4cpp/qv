from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from qv.app.app_settings_manager import AppSettingsManager
from qv.utils.log_util import logger
from qv.viewers.mpr_viewer import MprPlane, MprViewer
from qv.viewers.volume_viewer import VolumeViewer


class MultiViewerPanel(QtWidgets.QWidget):
    """
    Container widget for multiple viewers.

    Phase 1 keeps the responsibility intentionally narrow:
    - create one VR viewer and three fixed MPR viewers.
    - arrange them in a stable 2x2 layout
    - distribute the shared vtkImageData to allMPR viewers after volume load
    """

    def __init__(self,
                 settings_mgr: AppSettingsManager | None = None,
                 parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setting = settings_mgr or AppSettingsManager()

        self._viewers: dict[str, QtWidgets.QWidget] = {}
        self.mpr_viewers: dict[MprPlane, MprViewer] = {}

        self._build_layout()
        self._create_viewers()

        self.volume_viewer.dataLoaded.connect(self._on_volume_data_loaded)

        QtCore.QTimer.singleShot(0, self._initialize_splitter_sizes)

    def _build_layout(self) -> None:
        """Create nested splitters that form a resizable 2x2 grid."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        self.top_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self.splitter)
        self.bottom_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self.splitter)

        for splitter in (self.splitter, self.top_splitter, self.bottom_splitter):
            splitter.setChildrenCollapsible(False)
            splitter.setHandleWidth(5)
            splitter.setOpaqueResize(True)

        self.splitter.addWidget(self.top_splitter)
        self.splitter.addWidget(self.bottom_splitter)

        layout.addWidget(self.splitter)

    def _create_viewers(self) -> None:
        """Create the VR viewer and three fixed-plane MPR viewers."""
        self.volume_viewer = VolumeViewer(settings_manager=self.setting, parent=self)

        self.mpr_axial_viewer = MprViewer(
            settings_manager=self.setting,
            parent=self,
            plane=MprPlane.AXIAL,
        )

        self.mpr_coronal_viewer = MprViewer(
            settings_manager=self.setting,
            parent=self,
            plane=MprPlane.CORONAL,
        )

        self.mpr_sagittal_viewer = MprViewer(
            settings_manager=self.setting,
            parent=self,
            plane=MprPlane.SAGITTAL,
        )

        # Keep compatibility alias while the surrounding UI is migrated away
        # from the former single-MPR assumption.
        self.mpr_viewer = self.mpr_axial_viewer

        self.mpr_viewers = {
            MprPlane.AXIAL: self.mpr_axial_viewer,
            MprPlane.CORONAL: self.mpr_coronal_viewer,
            MprPlane.SAGITTAL: self.mpr_sagittal_viewer,
        }

        self.add_viewer(self.volume_viewer, "volume", self.top_splitter)
        self.add_viewer(self.mpr_axial_viewer, "mpr_axial", self.top_splitter)
        self.add_viewer(self.mpr_coronal_viewer, "mpr_coronal", self.bottom_splitter)
        self.add_viewer(self.mpr_sagittal_viewer, "mpr_sagittal", self.bottom_splitter)

        self.top_splitter.setStretchFactor(0, 1)
        self.top_splitter.setStretchFactor(1, 1)
        self.bottom_splitter.setStretchFactor(0, 1)
        self.bottom_splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)

        for viewer in self._viewers.values():
            # Keep each pane usable even before the user resizes splitters.
            viewer.setMinimumSize(240, 180)

    def add_viewer(
            self,
            viewer: QtWidgets.QWidget,
            name: str,
            container: QtWidgets.QSplitter
    ) -> None:
        """
        Add a viewer widget into the requested splitter container.

        This remains generic so later phases can reshuffle the layout without
        changing the external panel API.
        """
        if name in self._viewers:
            raise ValueError(f"Viewer with name '{name}' already exists.")

        self._viewers[name] = viewer
        container.addWidget(viewer)

    def _initialize_splitter_sizes(self) -> None:
        """Start all panes with an even split in both directions."""
        width = max(self.width() // 2, 320)
        height = max(self.height() // 2, 240)

        self.top_splitter.setSizes([width, width])
        self.bottom_splitter.setSizes([width, width])
        self.splitter.setSizes([height, height])


    def _on_volume_data_loaded(self) -> None:
        """Push loaded vtkImageData to MPR viewer"""
        logger.info("[MultiViewerPanel] Volume data load.")
        image = self.volume_viewer.source_image
        if image is None:
            return
        self.mpr_viewer.set_image_data(image)
