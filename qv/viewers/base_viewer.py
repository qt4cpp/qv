"""Base viewer class for VTK-based viewers"""
from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING

import vtk
from PySide6 import QtWidgets, QtCore

from qv.app.app_settings_manager import AppSettingsManager
from qv.core.window_settings import WindowSettings
from qv.viewers.camera.camera_state import CameraAngle
from qv.viewers.camera.camera_controller import CameraController

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
    windowSettingsChanged = QtCore.Signal(object)

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

        # Shared WW/WL state and HUD actor.
        self._window_settings: WindowSettings | None = None
        self._window_overlay_actor: vtk.vtkTextActor | None = None

        self._setup_ui()
        self._setup_vtk_rendering()
        self._init_window_overlay()
        self._sync_window_overlay_text()

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

    # =====================================================
    # Shared WW/WL Overlay (task 1)
    # =====================================================

    def _init_window_overlay(self) -> None:
        """Create a shared bottom-right HUD text actor for window settings."""
        actor = vtk.vtkTextActor()
        actor.SetInput("")

        text_prop = actor.GetTextProperty()
        text_prop.SetFontFamilyToCourier()  # Stable width for compact numeric display
        text_prop.SetFontSize(18)
        text_prop.SetColor(1.0, 1.0, 1.0)
        text_prop.SetBold(False)
        text_prop.SetItalic(False)
        text_prop.SetShadow(True)
        text_prop.SetJustificationToRight()
        text_prop.SetVerticalJustificationToBottom()

        # Keep actor anchored to bottom-right on resize.
        actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        actor.SetPosition(0.95, 0.05)
        actor.VisibilityOff()

        self.overlay_renderer.AddActor(actor)
        self._window_overlay_actor = actor

    def _set_window_overlay_text(self, text: str) -> None:
        """
        Update HUD text content.

        Empty text hides the HUD.
        """
        if self._window_overlay_actor is None:
            return

        safe_text = text.strip()
        self._window_overlay_actor.SetInput(safe_text)
        self._window_overlay_actor.SetVisibility(1 if safe_text else 0)

    def _show_window_overlay(self, visible: bool) -> None:
        """Explicitly show or hide the HUD."""
        if self._window_overlay_actor is None:
            return
        self._window_overlay_actor.SetVisibility(1 if visible else 0)

    # =====================================================
    # Window Settings Interface
    # =====================================================

    def _format_window_overlay_text(self, settings: WindowSettings | None) -> str:
        """Convert window settings to HUD text format."""
        if settings is None:
            return ""
        return f"WW {settings.width:4d} WL {settings.level:4d}"

    def _sync_window_overlay_text(self) -> None:
        """Sync HUD text from current shared window settings."""
        self._set_window_overlay_text(
            self._format_window_overlay_text(self.setting.shared_window_settings)
        )

    def _apply_window_settings(self, settings: WindowSettings) -> bool:
        """
        Hook for subclasses to apply WW/WL to their VTK pipeline.

        Returns:
            bool: True if settings were applied successfully, False otherwise.
        Base implementation returns False.
        """
        return False

    def set_window_settings(
            self,
            settings: WindowSettings,
            *,
            emit_signal: bool = True,
            render: bool = True,
    ) -> None:
        """
        Shared WW/WL entrypoint.

        - Store settings
        - Update HUD text
        - Delegate actual pipeline to subclass hook
        - Emit common signal
        """
        if self._window_settings == settings:
            return

        self._window_settings = settings
        self._sync_window_overlay_text()

        changed = self._apply_window_settings(settings)

        if emit_signal:
            self.windowSettingsChanged.emit(settings)

        if render and changed:
            self.update_view()

    @property
    def window_settings(self) -> WindowSettings | None:
        """Return the current window settings."""
        return self._window_settings

    @window_settings.setter
    def window_settings(self, value: WindowSettings) -> None:
        """Set WW/WL through shared entrypoint."""
        self.set_window_settings(value)

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
        self.vtk_widget.Render()

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
