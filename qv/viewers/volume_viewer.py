"""Volume viewer widget for 3d DICOM images."""
import logging
import math

import numpy as np
import vtk
from PySide6 import QtCore
from PySide6.QtCore import QEvent
from vtkmodules.util.numpy_support import vtk_to_numpy

import qv.utils.vtk_helpers as vtk_helpers
from app_settings_manager import AppSettingsManager
from core import geometry_utils
from core.window_settings import WindowSettings
from qv.utils.log_util import log_io
from clipping_function import QVVolumeClipper, ClippingInteractorStyle
from viewers.base_viewer import BaseViewer
from volumeviewer_interactor_style import VolumeViewerInteractorStyle

logger = logging.getLogger(__name__)


class VolumeViewer(BaseViewer):
    """
    Volume viewer widget for 3d DICOM images.

    Profiveds 3d-specific functionality:
    - Volume rendering with window/level.
    - 3D camera operations (rotation, preset views)
    - Clipping functionality
    - Zoom operations specific to volume bounds
    """

    windowSettingsChanged = QtCore.Signal(object)  # window, level

    def __init__(self,
                 settings_manager: AppSettingsManager | None = None,
                 parent=None) -> None:
        """
        Initialize the volume viewer widget.

        :param settings_manager: Application settings manager.
        :param parent:
        """
        # Volume-specific attributes
        self.image: vtk.vtkImageData | None = None
        self.volume: vtk.vtkVolume | None = None
        self.volume_property: vtk.vtkVolumeProperty | None = None
        self.scalar_range: tuple[float, float] | None = None
        self.color_func: vtk.vtkColorTransferFunction | None = None
        self.opacity_func: vtk.vtkPiecewiseFunction | None = None

        # Window/level attributes
        self._window_settings = WindowSettings(level=0.0, width=1.0)
        self.delta_per_pixel: float = 1

        super().__init__(settings_manager=settings_manager, parent=parent)
        self.vtk_widget.installEventFilter(self)
        self._setup_clipping()

    def setup_interactor_style(self) -> None:
        """Setup the interactor style for volume viewer."""
        self._default_interactor_style = VolumeViewerInteractorStyle(self)
        self.interactor.SetInteractorStyle(self._default_interactor_style)

    def _setup_clipping(self) -> None:
        """Setup clipping functionality and visualization."""
        self._clipping_interactor_style = ClippingInteractorStyle(self)
        self.clipper = QVVolumeClipper(self, self.overlay_renderer)

        self.clipper_actor = vtk.vtkActor()
        self.clipper_polydata = vtk.vtkPolyData()
        self.clipper_mapper = vtk.vtkPolyDataMapper()
        self.clipper_mapper.SetInputData(self.clipper_polydata)
        self.clipper_actor.SetMapper(self.clipper_mapper)

        # Configure clipper visual properties
        prop = self.clipper_actor.GetProperty()
        prop.SetColor(1, 1, 0)
        prop.SetLineWidth(3)
        prop.SetOpacity(1.0)
        prop.SetRenderLinesAsTubes(True)
        prop.RenderPointsAsSpheresOn()
        prop.SetPointSize(6)

        self._clipper_overlay_observer = self.interactor.AddObserver(
            "EndInteractionEvent", self._on_camera_interaction
        )

    def eventFilter(self, obj, event):
        """Handle double-click events on VTK widgets."""
        if obj == self.vtk_widget:
            if event.type() == QEvent.MouseButtonDblClick:
                logger.debug("Mouse double click event detected ->  LeftButtonDoubleClickEvent")
                self.interactor.InvokeEvent("LeftButtonDoubleClickEvent")
                return True
        return super().eventFilter(obj, event)

    # =====================================================
    # 3D Camea Operations (VolumeViewer specific)
    # =====================================================

    def set_camera_view(self, view: str) -> None:
        """
        Set the camera to a preset 3D view angle.

        :param view: View direction ('front', 'back', 'left', 'right', 'top', 'bottom')
        """
        self.camera_controller.set_preset_view(view)
        self.update_view()

    def front_view(self) -> None:
        """Set the camera to a front view angle."""
        self.set_camera_view('front')

    def back_view(self) -> None:
        """Set the camera to a back view angle."""
        self.set_camera_view('back')

    def left_view(self) -> None:
        """Set the camera to a left view angle."""
        self.set_camera_view('left')

    def right_view(self) -> None:
        """Set the camera to a right view angle."""
        self.set_camera_view('right')

    def top_view(self) -> None:
        """Set the camera to a top view angle."""
        self.set_camera_view('top')

    def bottom_view(self) -> None:
        """Set the camera to a bottom view angle."""
        self.set_camera_view('bottom')

    def rotate_camera(self, dx: int, dy: int) -> None:
        """
        Rotate the camera in 3D
        :param dx: Horizontal mouse movement (pixels)
        :param dy: Vertical mouse movement (pixels)
        """
        rotation_factor = self.setting.rotation_step_deg
        da = -dx * rotation_factor
        de = -dy * rotation_factor

        self.camera_controller.rotate(da, de)
        self.update_view()

    # =====================================================
    # Volume-specific Utility Method
    # =====================================================

    def get_volume_center(self) -> tuple[float, float, float]:
        """
        Get the center of the volume.

        :return: (x, y, z) coordinates of the center
        :raise RuntimeError: If the volume is not loaded
        """
        if self.volume is None:
            raise RuntimeError("Volume not loaded")

        bounds = self.volume.GetBounds()
        center = (
            0.5 * (bounds[0] + bounds[1]),
            0.5 * (bounds[2] + bounds[3]),
            0.5 * (bounds[4] + bounds[5]),
        )
        return center

    def get_default_distance(self) -> float:
        """
        Get teh default camera distance for tthe volume.

        :return: Default disntace value
        :raise RuntimeError: If the volume is not loaded
        """
        if self.volume is None:
            raise RuntimeError("Volume not loaded")

        bounds = self.volume.GetBounds()
        max_dim = max(
            bounds[1] - bounds[0],
            bounds[3] - bounds[2],
            bounds[5] - bounds[4]
        )
        return max_dim * 2.0

    # =====================================================
    # Data Loading
    # =====================================================

    @log_io(level=logging.INFO)
    def load_data(self, dicom_dir: str) -> None:
        """
        Load a volume from a DICOM directory.

        :param dicom_dir: Path to directory containig DICOM files
        """
        self.load_volume(dicom_dir)

    def load_volume(self, dicon_dir: str) -> None:
        """
        Load a volume from a DICOM directory.

        :param dicon_dir: Path to directory containing DICOM files
        """
        logger.info(f"Loading volume from {dicon_dir}")

        self.image = vtk_helpers.load_dicom_series(dicon_dir)
        self.scalar_range = self.image.GetScalarRange()

        level = round(min(4096.0, sum(self.scalar_range) / 2.0))
        width = round(min(level / 2.0, 1024.0))
        self._window_settings = WindowSettings(level=level, width=width)

        mapper = vtk.vtkGPUVolumeRayCastMapper()
        mapper.SetInputData(self.image)

        self.color_func = vtk.vtkColorTransferFunction()
        self.opacity_func = vtk.vtkPiecewiseFunction()

        self.volume_property = vtk.vtkVolumeProperty()
        self.volume_property.SetColor(self.color_func)
        self.volume_property.SetScalarOpacity(self.opacity_func)
        self.volume_property.ShadeOn()
        self.volume_property.SetInterpolationTypeToLinear()

        self.volume = vtk.vtkVolume()
        self.volume.SetMapper(mapper)
        self.volume.SetProperty(self.volume_property)

        self.renderer.AddVolume(self.volume)

        self.camera_controller.extract_patient_matrix_from_volume(self.volume)
        self.camera_controller.reset_to_bounds(self.volume.GetBounds(), view='front')

        self.update_transfer_functions()
        self.update_view()

        self.dataLoaded.emit()
        self.windowSettingsChanged.emit(self._window_settings)

        logger.info(
            "Volume loaded: extent=%s spacing=%s origin=%s",
            self.image.GetExtent(), self.image.GetSpacing(), self.image.GetOrigin()
        )

    # =====================================================
    # Transfer Function (Window Settings)
    # =====================================================

    def update_transfer_functions(self) -> None:
        """Update color and opacity transfer functions based on window settings."""
        if self.color_func is None or self.opacity_func is None:
            return

        min_val, max_val = self._window_settings.get_range()

        self.color_func.RemoveAllPoints()
        self.color_func.AddRGBPoint(min_val, 0.0, 0.0, 0.0)
        self.color_func.AddRGBPoint(max_val, 1.0, 1.0, 1.0)

        self.opacity_func.RemoveAllPoints()
        self.opacity_func.AddPoint(min_val, 0.0)
        self.opacity_func.AddPoint(max_val, 1.0)

        self.update_view()
        self.windowSettingsChanged.emit(self._window_settings)

    def adjust_window_settings(self, dx:int, dy:int) -> None:
        """
        Adjust the window settings according to the mouse movement.

        :param dx: Horizontal mouse delta (affects width)
        :param dy: Vertical mouse delta (affects level)
        """
        if self.scalar_range is None:
            return

        delta_width = dx * self.delta_per_pixel
        delta_level = -dy * self.delta_per_pixel

        adjusted = self._window_settings.adjust(
            delta_width=delta_width,
            delta_level=delta_level,
            scalar_range=self.scalar_range,
        )

        if adjusted != self._window_settings:
            self._window_settings = adjusted
            self.update_transfer_functions()

    def set_window_settings(self, window_settings: WindowSettings) -> None:
        """
        Set the window settings for the volume.

        """
        if self.scalar_range is None:
            logger.warning("Cannot set window settings: volume not loaded")
            return

        clamped = window_settings.clamp(self.scalar_range)

        if clamped != self._window_settings:
            self._window_settings = clamped
            self.update_transfer_functions()

    @property
    def window_settings(self) -> WindowSettings:
        """Get current window settings."""
        return self._window_settings

    @window_settings.setter
    def window_settings(self, value: WindowSettings) -> None:
        """Set the window settings."""
        self.set_window_settings(value)

    # =====================================================
    # Zoom Operations (Volume-specific)
    # =====================================================

    def set_zoom_factor(self, factor: float) -> None:
        """
        Set camera zoom by factor relative to volume bounds.

        :param factor: Zoom factor (1.0 = default, 2.0 = 2x zoom)
        """
        if self.volume is None:
            return

        default_distance = self.get_default_distance()
        self.camera_controller.set_zoom(factor, default_distance=default_distance)
        self.update_view()

    def set_zoom_2x(self) -> None:
        self.set_zoom_factor(2.0)

    def set_zoom_half(self) -> None:
        self.set_zoom_factor(0.5)

    def reset_zoom(self) -> None:
        self.set_zoom_factor(1.0)

    def reset_center(self) -> None:
        """Reset camera focal point to volume center."""
        center = self.get_volume_center()
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(*center)
        self.update_view()

    # =====================================================
    # Clipping Operations
    # =====================================================

    def enter_clip_mode(self) -> None:
        """Enter clipping mode"""
        logger.debug("Entering clipping mode")
        self.interactor.SetInteractorStyle(self._clipping_interactor_style)
        self.clipper.start_region_selection()
        self.update_view()

    def exit_clip_mode(self) -> None:
        """Exit clipping mode"""
        logger.debug("Exiting clipping mode")
        self.interactor.SetInteractorStyle(self._default_interactor_style)
        self.clipper.stop_region_selection()

    def apply_clipping(self) -> None:
        """Apply the current clipping region."""
        self.clipper.apply()

    def cancel_clipping(self) -> None:
        self.clipper.cancel()

    def add_clip_point(self,
                       display_xy: tuple[float, float],
                       world_pt: tuple[float, float, float]) -> None:
        """Add a point tothe clipping region."""
        self.clipper_add_selection_point(display_xy, world_pt)
        self.update_clipper_visualization()

    def _on_camera_interaction(self, obj, event):
        """Handle camera interaction events."""
        self.clipper.on_camera_updated()

    def update_clipper_visualization(self) -> None:
        """Update the visual representation of the clipping region."""
        world_points = self.clipper.get_preview_world_points()
        if not world_points:
            self.clipper_polydata.Initialize()
            self.update_view()
            return

        cam = self.renderer.GetActiveCamera()
        cam_pos = cam.GetPosition()
        bounds = self.renderer.ComputeVisiblePropBounds()
        diag = math.sqrt(
            sum(bounds[2 * i + 1] - bounds[2 * i] ** 2 for i in range(3))
        ) or 1.0
        offset = 0.002 * diag

        points = vtk.vtkPoints()
        verts = vtk.vtkCellArray()
        lines = vtk.vtkCellArray()

        n = len(world_points)
        for i, pt in enumerate(world_points):
            to_cam = [cam_pos[j] - pt[j] for j in range(3)]
            length = geometry_utils.calculate_norm(to_cam)
            if length:
                disp_pt = [pt[j] + to_cam[j] / length * offset for j in range(3)]
            else:
                disp_pt = pt
            points.InsertNextPoint(*disp_pt)

            verts.InsertNextCell(1)
            verts.InsertCellPoint(i)

            if i > 0:
                lines.InsertNextCell(2)
                lines.InsertCellPoint(i - 1)
                lines.InsertCellPoint(i)

        # Close the loop for polygons
        if n >= 3:
            lines.InsertNextCell(2)
            lines.InsertCellPoint(n - 1)
            lines.InsertCellPoint(0)

        self.clipper_polydata.SetPoints(points)
        self.clipper_polydata.SetVerts(verts)
        self.clipper_polydata.SetLines(lines)

        self.update_view()
