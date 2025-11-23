"""Base viewer class for VTK-based viewers"""
from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING

import vtk
from PySide6 import QtWidgets, QtCore

from app.app_settings_manager import AppSettingsManager
from viewers.camera.camera_state import CameraAngle
from viewers.camera.camera_controller import CameraController

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ABCQtMeta(ABCMeta, type(QtWidgets.QWidget)):
    """
    Metaclass that combines ABCMeta and type(QWidget)
    """
    pass


class BaseViewer(QtWidgets.QWidget, metaclass=ABCQtMeta):
    """
    Base class for VTK-based viewers

    Provides common functionality:
    - VTK rendering setup (renderer, interactor)
    - Camera control
    - Status bar management
    - Shortcut handling
    - Basic camera operations

    Subclasses should implement:
    - load_data(): Load and display specific data types
    - register_commands(): Register commands for the viewer
    - setup_interactor_style(): Set up the interactor style
    """

    # Signals
    cameraAngleChanged = QtCore.Signal(object)
    dataLoaded = QtCore.Signal()

    def __init__(
            self,
            settings_manager: AppSettingsManager | None = None,
            parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """
        Initialize the base viewer.
        :param settings_manager: Application settings manager
        :param parent: Parent widget
        """
        super().__init__(parent)
        self.setting = settings_manager or AppSettingsManager()
        self._setup_ui()
        self._setup_vtk_rendering()

        self.camera_controller = CameraController(
            self.renderer.GetActiveCamera(),
            self.renderer)
        self.camera_controller.add_angle_changed_callback(self._on_camera_angle_changed)

        self.setup_interactor_style()
        self.interactor.Initialize()

    def _setup_ui(self) -> None:
        """Setup the UI."""
        # Main Layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
        self.vtk_widget = QVTKRenderWindowInteractor(self)
        layout.addWidget(self.vtk_widget)

        self.setLayout(layout)

        logging.debug("Base viewer UI created.")

    def _setup_vtk_rendering(self) -> None:
        """Setup the VTK rendering components."""
        render_window = self.vtk_widget.GetRenderWindow()

        # Main renderer (layer 0)
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetLayer(0)
        render_window.AddRenderer(self.renderer)
        render_window.SetNumberOfLayers(2)

        # Overlay renderer (layer 1) - for annotations, overlays, etc.
        self.overlay_renderer = vtk.vtkRenderer()
        self.overlay_renderer.SetLayer(1)
        self.overlay_renderer.SetInteractive(False)
        if hasattr(self.overlay_renderer, "SetBackgroundAlpha"):
            self.overlay_renderer.SetBackgroundAlpha(0.0)
        if hasattr(self.overlay_renderer, "SetUseDepth"):
            self.overlay_renderer.SetUseDepth(0)
        render_window.AddRenderer(self.overlay_renderer)

        self.interactor = render_window.GetInteractor()

        logger.debug("VTK rendering components initialized.")

    @abstractmethod
    def setup_interactor_style(self) -> None:
        """
        Setup the interactor style for user interaction.

        Subclasses should implement this method to configure their specific
         interactor style.
        Example:
        style = CustomInteractorStyle(self)
        self.interactor.SetInteractorStyle(style)
        """
        pass

    @abstractmethod
    def load_data(self, *args, **kwargs) -> None:
        """
        Load and display data.

        Subclasses should implement this method to load and display data.
        Should emit dataLoaded signal when data is loaded.
        """
        pass

    # =====================================================
    # Camera Callbacks
    # =====================================================

    def _on_camera_angle_changed(self, angle: CameraAngle) -> None:
        """
        Callback for when the camera angle changes.

        :param angle: New camera angle
        :return:
        """
        self.cameraAngleChanged.emit(angle)

    # =====================================================
    # Rendering
    # =====================================================

    def update_view(self) -> None:
        """Trigger a render."""
        self.vtk_widget.GetRenderWindow().Render()

    def reset_camera(self) -> None:
        """Reset the camera to the default position."""
        self.renderer.ResetCamera()
        self.update_view()

    # =====================================================
    # Lifecycle
    # =====================================================

    def closeEvent(self, event) -> None:
        """Handle close event."""
        if hasattr(self, "interactor") and self.interactor:
            self.interactor.TerminateApp()
        super().closeEvent(event)
