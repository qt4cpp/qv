import logging
from pathlib import Path

from PySide6 import QtCore
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QSplitter,
                               QHBoxLayout, QLabel, QPushButton)

from qv.app.app_settings_manager import AppSettingsManager
from qv.utils.resource_paths import settings_dir
from qv.viewers.camera.camera_state import CameraAngle
from qv.core.window_settings import WindowSettings
from qv.utils.log_util import log_io
from qv.app.status import STATUS_FIELDS, StatusField
from qv.app.shortcut_manager import ShortcutManager
from qv.viewers.mpr_viewer import MprViewer, MprPlane
from qv.ui.widgets.histgram_widget import HistogramWidget
from qv.ui.widgets.multi_viewer_panel import MultiViewerPanel
import qv.utils.vtk_helpers as vtk_helpers
import copy

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window containing viewers and UI components."""

    def __init__(self, settings_mgr: AppSettingsManager | None = None):
        """
        Initialize the main window.

        :param settings_mgr: Application settings manager.
        """
        super().__init__()

        self.setting = settings_mgr or AppSettingsManager()

        # Setup shortcuts
        config_path = settings_dir()
        self.shortcut_mgr = ShortcutManager(
            parent=self,
            config_path=config_path,
            settings_manager=self.setting,
        )

        # Status fields
        self.status_fields: dict[str, StatusField] = {
            k: copy.deepcopy(v) for k, v in STATUS_FIELDS.items()
        }
        self._status_label: dict[str, QLabel] = {}

        # Setup UI
        self.setWindowTitle("QV - DICOM Viewer")
        self._setup_ui()
        self._setup_menus()
        self._setup_status_bar()

        self._register_shortcuts()

        self.show()

    def _setup_ui(self) -> None:
        """Setup the main UI layout"""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # Create splietter for viewer and histgram
        splitter = QSplitter(QtCore.Qt.Vertical)

        self.multi_viewer_panel = MultiViewerPanel(
            settings_mgr=self.setting,
            parent=central_widget,
        )

        # Keep compatibility with existing MainWindow code paths.
        self.volume_viewer = self.multi_viewer_panel.volume_viewer
        self.mpr_viewer = self.multi_viewer_panel.mpr_viewer

        self.histgram_widget = HistogramWidget()
        self.histgram_widget.setMinimumHeight(100)

        splitter.addWidget(self.multi_viewer_panel)
        splitter.addWidget(self.histgram_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)
        self.setGeometry(100, 100, 1200, 800)

        # Connect signals
        self.volume_viewer.cameraAngleChanged.connect(self._on_camera_angle_changed)
        self.volume_viewer.windowSettingsChanged.connect(self._on_window_settings_changed)
        self.volume_viewer.dataLoaded.connect(self._on_data_loaded)

    def _setup_menus(self) -> None:
        """Create the menus for the main window."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction("&Open", self.open_file)
        file_menu.addSeparator()
        file_menu.addAction("&Quit", self.close)

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction("&Reset View", self.volume_viewer.reset_camera)
        view_menu.addAction("Front view", self.volume_viewer.front_view)
        view_menu.addAction("Back view", self.volume_viewer.back_view)
        view_menu.addAction("Left view", self.volume_viewer.left_view)
        view_menu.addAction("Right view", self.volume_viewer.right_view)
        view_menu.addAction("Top view", self.volume_viewer.top_view)
        view_menu.addAction("Bottom view", self.volume_viewer.bottom_view)
        view_menu.addSeparator()
        view_menu.addAction("Reset Zoom", self.volume_viewer.reset_zoom)
        view_menu.addAction("2x zoom", self.volume_viewer.set_zoom_2x)
        view_menu.addAction("0.5x zoom", self.volume_viewer.set_zoom_half)
        view_menu.addSeparator()
        mpr_menu = view_menu.addMenu("MPR")

        self._mpr_plane_group = QActionGroup(self)
        self._mpr_plane_group.setExclusive(True)
        self._mpr_plane_actions: dict[str, QAction] = {}

        for label, plane in (
            ("Axial", MprPlane.AXIAL),
            ("Coronal", MprPlane.CORONAL),
            ("Sagittal", MprPlane.SAGITTAL),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, p=plane: self._on_select_mpr_plane(p, checked)
            )
            self._mpr_plane_group.addAction(action)
            self._mpr_plane_actions[plane] = action
            mpr_menu.addAction(action)

        self._mpr_plane_actions[MprPlane.AXIAL].setChecked(True)

        view_menu.addSeparator()
        perf_menu = view_menu.addMenu("Performance Profile")

        self._perf_profile_group = QActionGroup(self)
        self._perf_profile_group.setExclusive(True)
        self._perf_profile_actions: dict[str, QAction] = {}

        for profile_name in ("speed", "balanced", "quality"):
            action = QAction(profile_name.capitalize(), self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked, name=profile_name: self._on_select_perf_profile(name, checked)
            )
            self._perf_profile_group.addAction(action)
            self._perf_profile_actions[profile_name] = action
            perf_menu.addAction(action)

        # 初期チェック
        current_profile = self.volume_viewer.current_profile_name
        if current_profile in self._perf_profile_actions:
            self._perf_profile_actions[current_profile].setChecked(True)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction("&Clip inside", self._start_clip_inside)
        edit_menu.addAction("&Clip outside", self._start_clip_outside)

        edit_menu.addSeparator()

        self.undo_action = QAction("&Undo", self)
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.triggered.connect(self._undo)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction("&Redo", self)
        self.redo_action.setShortcut("Ctrl+Y")
        self.redo_action.triggered.connect(self._redo)
        edit_menu.addAction(self.redo_action)

        self._update_undo_redo_enabled()

    def _on_select_perf_profile(self, profile_name: str, checked: bool) -> None:
        if not checked:
            return
        self.volume_viewer.set_profile(profile_name)

    def _on_select_mpr_plane(self, plane: MprPlane, checked: bool) -> None:
        if not checked:
            return
        self.mpr_viewer.set_plane(plane)

    def _update_undo_redo_enabled(self):
        """Synchronize the enabled status of Undo/Redo actions with the history manager."""
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(self.volume_viewer.history.can_undo())
        if hasattr(self, "redo_action"):
            self.redo_action.setEnabled(self.volume_viewer.history.can_redo())

    def _undo(self) -> None:
        """Trigger undo operation."""
        self.volume_viewer.undo()
        self._update_undo_redo_enabled()

    def _redo(self) -> None:
        """Trigger redo operation."""
        self.volume_viewer.redo()
        self._update_undo_redo_enabled()

    # --- Button Hnadler ---
    # These handlers must call _update_undo_redo_enabled because they modify history.

    @log_io(level=logging.INFO)
    def _apply_clipping(self) -> None:
        """Confirm the selection and push to history."""
        self.volume_viewer.apply_clipping()
        self.clip_button_widget.hide()
        self._update_undo_redo_enabled()

    def _cancel_clippping(self) -> None:
        """Cancel the current clipping operation and restore the original volume."""
        self.volume_viewer.cancel_clipping()
        self._update_undo_redo_enabled()

    def _setup_status_bar(self) -> None:
        """Setup the status bar."""
        status_bar = self.statusBar()

        for key, field in self.status_fields.items():
            if not field.visible:
                self._status_label[key] = None
                continue
            label = QLabel("", self)
            status_bar.addPermanentWidget(label)
            self._status_label[key] = label

        # Clipping buttons (initially hidden)
        self.clip_button_widget = QWidget()
        layout = QHBoxLayout()
        self.apply_clip_button = QPushButton("Apply", self)
        self.cancel_clip_button = QPushButton("Cancel", self)
        layout.addWidget(self.apply_clip_button)
        layout.addWidget(self.cancel_clip_button)
        self.clip_button_widget.setLayout(layout)
        self.clip_button_widget.hide()

        status_bar.addPermanentWidget(self.clip_button_widget)

        self.apply_clip_button.clicked.connect(self._apply_clipping)
        self.cancel_clip_button.clicked.connect(self._cancel_clippping)

    def _register_shortcuts(self) -> None:
        """Register keyboard shortcuts."""
        self.shortcut_mgr.add_callback("front_view", self.volume_viewer.front_view)
        self.shortcut_mgr.add_callback("back_view", self.volume_viewer.back_view)
        self.shortcut_mgr.add_callback("left_view", self.volume_viewer.left_view)
        self.shortcut_mgr.add_callback("right_view", self.volume_viewer.right_view)
        self.shortcut_mgr.add_callback("top_view", self.volume_viewer.top_view)
        self.shortcut_mgr.add_callback("bottom_view", self.volume_viewer.bottom_view)
        self.shortcut_mgr.add_callback("open_file", self.open_file)

    # =====================================================
    # Menu Actions
    # =====================================================

    @log_io(level=logging.INFO)
    def open_file(self) -> None:
        dicom_dir = vtk_helpers.select_dicom_directory()
        if dicom_dir is None:
            return
        self.volume_viewer.load_data(dicom_dir)

    def _start_clip_inside(self) -> None:
        """
        Start `clip inside` mode.

        This sets up the volumeviewer to remove voxels inside the region
        and shows up Apply/Cancel buttons.
        """
        self.volume_viewer.start_clip_inside()
        self.clip_button_widget.show()

    def _start_clip_outside(self) -> None:
        """
        Start `clip outside` mode.

        This sets up the volumeviewer to remove voxels outside the region
        and shows up Apply/Cancel buttons.
        """
        self.volume_viewer.start_clip_outside()
        self.clip_button_widget.show()

    def _enter_clip_mode(self) -> None:
        """Enter clipping mode."""
        self.volume_viewer.enter_clip_mode()
        self.clip_button_widget.show()

    # =====================================================
    # Signal Handlers
    # =====================================================

    def _on_camera_angle_changed(self, angle: CameraAngle) -> None:
        """
        Handle camera angle change.

        :param angle: New camera angle
        """
        self._update_status("azimuth", angle.azimuth)
        self._update_status("elevation", angle.elevation)

    def _on_window_settings_changed(self, window_settings: WindowSettings) -> None:
        """Handle window level/width change."""
        self._update_status("window_level", window_settings.level)
        self._update_status("window_width", window_settings.width)

        if self.volume_viewer.opacity_func:
            self.histgram_widget.update_opacity_curve(self.volume_viewer.opacity_func)

    def _update_status(self, key: str, value) -> None:
        """Update status bar label."""
        label = self._status_label.get(key)
        if label is None:
            return

        field = self.status_fields.get(key)
        if field is None:
            return

        field.value = value
        try:
            text = field.formatter(value)
            label.setText(text)
        except Exception as e:
            logger.warning(f"Error formatting status field {key}: {e}")
            label.setText(str(value))

    def _on_data_loaded(self) -> None:
        """Handle data loaded event."""
        logger.debug("Data loaded, updating histogram")

        if self.volume_viewer._source_image is None:
            return

        n_points = int(self.volume_viewer._source_image.GetNumberOfPoints())
        target_samples = 2_000_000
        sampling = max(1, int((n_points + target_samples - 1) / target_samples))
        logger.info(
            "Histogram sampling: n_points=%s sampling=%s (~%s samples)",
            n_points,
            sampling,
            max(1, n_points // sampling),
        )
        self.histgram_widget.set_data(
            vtk_helpers.vtk_image_to_numpy(self.volume_viewer._source_image, sampling=sampling)
        )

        if self.volume_viewer.volume_property:
            self.histgram_widget.update_opacity_curve(
                self.volume_viewer.volume_property.GetScalarOpacity()
            )

        self._update_undo_redo_enabled()
