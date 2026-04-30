from __future__ import annotations

import enum

import vtk
from PySide6 import QtCore, QtWidgets

from qv.app.app_settings_manager import AppSettingsManager
from qv.core.patient_geometry import PatientFrame

from qv.utils.log_util import logger
from  qv.viewers.controllers.mpr_sync_controller import MprSyncController
from qv.viewers.mpr_viewer import MprPlane, MprViewer
from qv.viewers.volume_viewer import VolumeViewer


class ViewerLayoutMode(enum.Enum):
    """Supported viewer-layout modes."""

    SINGLE_MPR = "single_mpr"
    QUAD = 'quad'


class MultiViewerPanel(QtWidgets.QWidget):
    """
    Container widget for multiple viewers.

    Responsibilities:
    - own the viewer instances
    - manage layout switching
    - distribute the shared vtkImageData to relevant MPR viewers
    -  crosshair overlays ssynchronized.
    """

    def __init__(self,
                 settings_mgr: AppSettingsManager | None = None,
                 parent: QtWidgets.QWidget | None = None,
                 *,
                 layout_mode: ViewerLayoutMode = ViewerLayoutMode.QUAD
    ) -> None:
        super().__init__(parent)
        self.setting = settings_mgr or AppSettingsManager()

        self._layout_mode = layout_mode
        self._shared_image: vtk.vtkImageData | None = None
        self._viewers: dict[str, QtWidgets.QWidget] = {}
        self.mpr_viewers: dict[MprPlane, MprViewer] = {}
        self._mpr_sync_controller = MprSyncController()
        self._shared_patient_frame: PatientFrame | None = None

        self._build_shell()
        self._create_viewers()
        self._register_mpr_viewers()
        self._connect_mpr_signal()
        self._apply_layout(layout_mode)

        self.volume_viewer.dataLoaded.connect(self._on_volume_data_loaded)
        QtCore.QTimer.singleShot(0, self._initialize_splitter_sizes)

    def _build_shell(self) -> None:
        """Create a root layout and a placeholder container for dynamic layouts."""
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self._content_layout = QtWidgets.QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addLayout(self._content_layout)

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

        self.mpr_viewers = {
            MprPlane.AXIAL: self.mpr_axial_viewer,
            MprPlane.CORONAL: self.mpr_coronal_viewer,
            MprPlane.SAGITTAL: self.mpr_sagittal_viewer,
        }

        # Backward-compatible alias
        # In SINGLE_MPR mode this is the visible MPR viewer.
        # In QUAD mode old code should stop depending on this.
        self.mpr_viewer = self.mpr_axial_viewer

    def _connect_mpr_signal(self) -> None:
        """Connect viewer-local slice changes to panel-level crosshair sync."""
        for viewer in self.mpr_viewers.values():
            viewer.sliceChanged.connect(self._on_mpr_slice_changed)
            viewer.syncRequested.connect(self._mpr_sync_controller.handle_sync_request)

    def _register_mpr_viewers(self) -> None:
        """Register all MPR viewers to the sync controller."""
        for viewer in self.mpr_viewers.values():
            self._mpr_sync_controller.register_viewer(viewer)

    @property
    def layout_mode(self) -> ViewerLayoutMode:
        """Return the current layout mode."""
        return self._layout_mode

    def set_layout_mode(self, mode: ViewerLayoutMode) -> None:
        """
        Switch the panel layout without changing the underlying loaded  data.

        The shared image is redistributed after the layout swap so the visible
        viewers always have valid input data.
        """
        if mode == self._layout_mode:
            return

        self._apply_layout(mode)
        self._layout_mode = mode
        self._redistribute_image_data()
        self._initialize_splitter_sizes()

    def set_image_data(
            self,
            image_data: vtk.vtkImageData | None,
            patient_frame: PatientFrame | None
    ) -> None:
        """
        Store the shared image and distribute it to the active MPR viewers.

        Keeping this API at the panel layer avoids coupling image distribution
        to VolumeVieewer internals.
        """
        self._shared_image = image_data
        self._shared_patient_frame = patient_frame
        self._redistribute_image_data()

    def _clear_content_layout(self) -> None:
        """Detach previous layout widgets before rebuilding the UI structure."""
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()

            if widget is not None:
                widget.setParent(None)
            elif child_layout is not None:
                self._delete_layout(child_layout)

    def _delete_layout(self, layout: QtWidgets.QLayout) -> None:
        """Recursively detach child widgets/layouts."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()

            if widget is not None:
                widget.setParent(None)
            elif child_layout is not None:
                self._delete_layout(child_layout)

    def _apply_layout(self, mode: ViewerLayoutMode):
        """Rebuild the visible layout around the exsting viewer instances."""
        self._clear_content_layout()

        if mode == ViewerLayoutMode.SINGLE_MPR:
            self._build_single_mpr_layout()
        else:
            self._build_quad_layout()

    def _build_single_mpr_layout(self) -> None:
        """Build the 2-pane layout.

        For now the single visible MPR is axial. If you later want menu-driven
        plane switching again, call ``self.mpr_viewer.set_plane(...)``.
        """
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.volume_viewer)
        self.main_splitter.addWidget(self.mpr_viewer)

        self._content_layout.addWidget(self.main_splitter)

    def _build_quad_layout(self) -> None:
        """Build 2x2 VR + three-MPR layout."""
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        self.main_splitter.setChildrenCollapsible(False)

        self.top_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self.main_splitter)
        self.bottom_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self.main_splitter)

        for  splitter in (self.main_splitter, self.top_splitter, self.bottom_splitter):
            splitter.setChildrenCollapsible(False)
            splitter.setHandleWidth(6)
            splitter.setOpaqueResize(True)

        self.top_splitter.addWidget(self.volume_viewer)
        self.top_splitter.addWidget(self.mpr_axial_viewer)
        self.bottom_splitter.addWidget(self.mpr_coronal_viewer)
        self.bottom_splitter.addWidget(self.mpr_sagittal_viewer)

        self._content_layout.addWidget(self.main_splitter)

    def _visible_mpr_viewers(self) -> list[MprViewer]:
        """Return the MPR viewers that should currently receive image data."""
        if self._layout_mode == ViewerLayoutMode.SINGLE_MPR:
            return [self.mpr_viewer]
        return list(self.mpr_viewers.values())

    def _redistribute_image_data(self) -> None:
        """
        Distribute the latest shared image to the currently active MPR viewers.

        Hidden viewers are intentionally skipped to keep mode-switch behavior
        explicit and easier to reason about.
        """
        if self._shared_image is None:
            logger.debug("[MultiViewerPanel] No image data to distribute.")
            self._synchronize_crosshair_state()
            return

        for viewer in self._visible_mpr_viewers():
            viewer.set_image_data(self._shared_image, patient_frame=self._shared_patient_frame,)

        self._synchronize_crosshair_state()

    def _initialize_splitter_sizes(self) -> None:
        """Start all panes with an even split in both directions."""
        width = max(self.width() // 2, 320)
        height = max(self.height() // 2, 240)

        self.top_splitter.setSizes([width, width])
        self.bottom_splitter.setSizes([width, width])
        self.main_splitter.setSizes([height, height])

    def _synchronize_crosshair_state(self) -> None:
        """
        Push slice positions into each MPR viewer's crosshair overlay state

        This is phase 3 behavior:
        - overlay only
        - no sibling slice mutation
        """
        visible_viewers = self._visible_mpr_viewers()
        show_crosshair = (self._layout_mode == ViewerLayoutMode.QUAD and
                          len(visible_viewers) == 3)

        # In non-quad layouts the crosshair overlay shoudl not appear
        for viewer in self.mpr_viewers.values():
            viewer.set_crosshair_visible(show_crosshair, render=False)

            if not show_crosshair:
                for viewer in self.mpr_viewers.values():
                    viewer.clear_crosshair_reference(render=False)
                for viewer in visible_viewers:
                    viewer.update_view()
                return

        slice_state = {
            plane: viewer.slice_index for plane, viewer in self.mpr_viewers.items()
        }

        logger.debug("[MultiViewerPanel] Synchronizing crosshair state: %s", slice_state)

        for target_viewer in visible_viewers:
            for source_plane, source_slice in slice_state.items():
                target_viewer.set_crosshair_slice_reference(
                    source_plane,
                    source_slice,
                    render=False,
                )
            target_viewer.update_view()

    def _on_volume_data_loaded(self) -> None:
        """Push loaded vtkImageData to MPR viewer"""
        logger.info("[MultiViewerPanel] Volume data load.")

        image = self.volume_viewer.source_image
        if image is None:
            logger.debug("[MultiViewerPanel] No image data to load.")
            return

        self.set_image_data(image, patient_frame=self.volume_viewer.patient_frame)

    def _on_mpr_slice_changed(self, plane: MprPlane, slice_index: int) -> None:
        """
        Update crosshair overlays after a user-driven slice change.

        The source viewer's own slice is already updated locally. This handler
        only redistributes the new slice index as display state for the other
        viewers' overlays.
        """
        logger.debug(
            "[MultiViewerPanel] Slice change: %s -> %s",
            plane.value,
            slice_index,
        )
        self._synchronize_crosshair_state()
