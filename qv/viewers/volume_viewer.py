"""Volume viewer widget for 3d DICOM images."""
import logging
import math
from typing import Sequence

import vtk
from PySide6 import QtCore
from PySide6.QtCore import QEvent
from fontTools.colorLib import geometry

import qv.utils.vtk_helpers as vtk_helpers
from app.app_settings_manager import AppSettingsManager
from core import geometry_utils
from core.window_settings import WindowSettings
from qv.utils.log_util import log_io
from operations.clipping.clipping_operation import ClippingOperation, CLIPPED_SCALAR, ClipMode
from viewers.interactor_styles.clipping_interactor_style import ClippingInteractorStyle
from viewers.base_viewer import BaseViewer
from viewers.interactor_styles.volume_interactor_style import VolumeViewerInteractorStyle

from vtkmodules.vtkCommonDataModel import vtkImplicitSelectionLoop

from qv.core.history import Command, HistoryManager
from qv.core.states import ClippingState


logger = logging.getLogger(__name__)


class VolumeViewer(BaseViewer):
    """
    Volume viewer widget for 3d DICOM images.

    Provides 3d-specific functionality:
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
        :param parent: Parent Widget
        """

        # Volume-specific attributes
        self._source_image: vtk.vtkImageData | None = None
        self.volume: vtk.vtkVolume | None = None
        self.volume_property: vtk.vtkVolumeProperty | None = None
        self.scalar_range: tuple[float, float] | None = None
        self.color_func: vtk.vtkColorTransferFunction | None = None
        self.opacity_func: vtk.vtkPiecewiseFunction | None = None
        self.mask_image: vtk.vtkImageData | None = None

        # Window/level attributes
        self._window_settings = WindowSettings(level=0.0, width=1.0)
        self.delta_per_pixel: float = 1

        # -- Undo/Redo + non-destructive clipping state --
        # Keep on immutable state and a pure-Python history stack
        self._source_image: vtk.vtkImageData | None = None
        self.clipping_state: ClippingState = ClippingState.default()
        self.history: HistoryManager = HistoryManager(max_undo=10)

        # Keep reference to pipeline objects to avoid premature GC.
        # Some VTK pipelines can break if intermediate objects are garbage collected.
        self._clipping_loop: vtkImplicitSelectionLoop | None = None
        self._clipping_stenciler: vtk.vtkImplicitFunctionToImageStencil | None = None
        self._clipping_image_stencil: vtk.vtkImageStencil | None = None

        # Clipping operation and visualization
        self.clipping_operation: ClippingOperation | None = None
        self._clipping_interactor_style: ClippingInteractorStyle | None = None
        self.clipper_actor = vtk.vtkActor()
        self.clipper_polydata = vtk.vtkPolyData()
        self.clipper_mapper = vtk.vtkPolyDataMapper()
        self.preview_extrude_actor: vtk.vtkActor | None = None

        super().__init__(settings_manager=settings_manager, parent=parent)
        self.vtk_widget.installEventFilter(self)
        self._setup_clipping()

    def setup_interactor_style(self) -> None:
        """Set up the interactor style for volume viewer."""
        self._default_interactor_style = VolumeViewerInteractorStyle(self)
        self.interactor.SetInteractorStyle(self._default_interactor_style)

    def _setup_clipping(self) -> None:
        """Setup clipping functionality and visualization."""
        logger.debug("[VolumeViewer] Setting up clipping operations")

        self.clipping_operation = ClippingOperation(
            viewer=self,
            overlay_renderer=self.overlay_renderer,
        )

        self._clipping_interactor_style = ClippingInteractorStyle(
            renderer=self.renderer,
            clipping_operation=self.clipping_operation)

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

        self.renderer.AddActor(self.clipper_actor)

        self._clipper_overlay_observer = self.interactor.AddObserver(
            "EndInteractionEvent",
            self._on_camera_interaction
        )

        logger.debug("[VolumeViewer] Clipping operations setup complete")

    def eventFilter(self, obj, event):
        """Handle double-click events on VTK widgets."""
        if obj == self.vtk_widget:
            if event.type() == QEvent.MouseButtonDblClick:
                logger.debug("Mouse double click event detected ->  LeftButtonDoubleClickEvent")
                self.interactor.InvokeEvent("LeftButtonDoubleClickEvent")
                return True
        return super().eventFilter(obj, event)

    # =====================================================
    # 3D Camera Operations (VolumeViewer specific)
    # =====================================================

    def set_camera_view(self, view: str) -> None:
        """
        Set the camera to a preset 3D view angle.

        :param view: View direction ('front', 'back', 'left', 'right', 'top', 'bottom')
        """
        self.camera_controller.set_preset_view(view)
        self._set_camera_parallel_from_current()
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
        Get the default camera distance for the volume.

        :return: Default distance value
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

        :param dicom_dir: Path to a directory containing DICOM files
        """
        self.load_volume(dicom_dir)

    def load_volume(self, dicon_dir: str) -> None:
        """
        Load a volume from a DICOM directory.

        :param dicon_dir: Path to a directory containing DICOM files
        """
        logger.info(f"Loading volume from {dicon_dir}")

        self._source_image = vtk_helpers.load_dicom_series(dicon_dir)
        self.scalar_range = self._source_image.GetScalarRange()

        level = round(min(4096.0, sum(self.scalar_range) / 2.0))
        width = round(min(level / 2.0, 1024.0))
        self._window_settings = WindowSettings(level=level, width=width)

        mapper = vtk.vtkGPUVolumeRayCastMapper()
        mapper.SetInputData(self._source_image)

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
        self._set_camera_parallel_from_current()

        self.update_transfer_functions()
        self.update_view()

        # Reset history and clipping state when data changes (spec requirement)
        self.history.clear()
        self.set_clipping_state(ClippingState.default())

        self.dataLoaded.emit()
        self.windowSettingsChanged.emit(self._window_settings)

        logger.info(
            "Volume loaded: extent=%s spacing=%s origin=%s",
            self._source_image.GetExtent(), self._source_image.GetSpacing(), self._source_image.GetOrigin()
        )

    # =====================================================
    # Undo / Redo
    # =====================================================

    def can_undo(self) -> bool:
        """Return True if undo is possible."""
        return self.history.can_undo()

    def can_redo(self) -> bool:
        """Return True if redo is possible."""
        return self.history.can_redo()

    def undo(self) -> None:
        """
        Undo the last applied clipping state.
        """
        try:
            self.history.undo(self.set_clipping_state)
        except Exception:
            logger.exception("[VolumeViewer] Undo failed (ignored).")

    def redo(self) -> None:
        """
        Redo the last undone clipping state.
        """
        try:
            self.history.redo(self.set_clipping_state)
        except Exception:
            logger.exception("[VolumeViewer] Redo failed (ignored).")

    # =====================================================
    # Transfer Function (Window Settings)
    # =====================================================

    def update_transfer_functions(self) -> None:
        """Update color and opacity transfer functions based on window settings."""
        if self.color_func is None or self.opacity_func is None:
            return

        min_val, max_val = self._window_settings.get_range()

        self.color_func.RemoveAllPoints()
        self.color_func.AddRGBPoint(CLIPPED_SCALAR, 0.0, 0.0, 0.0)
        self.color_func.AddRGBPoint(min_val, 0.0, 0.0, 0.0)
        self.color_func.AddRGBPoint(max_val, 1.0, 1.0, 1.0)

        self.opacity_func.RemoveAllPoints()
        self.opacity_func.AddPoint(CLIPPED_SCALAR, 0.0)
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
        """Reset camera focal point to center."""
        center = self.get_volume_center()
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(*center)
        self.update_view()

    # =====================================================
    # Clipping Operations
    # =====================================================

    def start_clip_inside(self) -> None:
        """
        Start clipping-inside mode.
        """
        if self.clipping_operation is None:
            logger.warning("[VolumeViewer] Clipping operation not initialized")
            return
        self.clipping_operation.set_mode(ClipMode.REMOVE_INSIDE)
        self.enter_clip_mode()

    def start_clip_outside(self) -> None:
        """
        Start clipping-outside mode.
        """
        if self.clipping_operation is None:
            logger.warning("[VolumeViewer] Clipping operation not initialized")
            return
        self.clipping_operation.set_mode(ClipMode.REMOVE_OUTSIDE)
        self.enter_clip_mode()

    def enter_clip_mode(self) -> None:
        """Enter clipping mode"""
        if self.clipping_operation is None:
            logger.warning("[VolumeViewer] Clipping operation not initialized")
            return

        logger.debug("[VolumeViewer] Entering clipping mode")
        self.interactor.SetInteractorStyle(self._clipping_interactor_style)
        logger.debug("[VolumeViewer] Switch interactor style to %s",
                     type(self.interactor.GetInteractorStyle()).__name__)
        self.clipping_operation.start()
        self.update_view()

    def exit_clip_mode(self) -> None:
        """Exit clipping mode"""
        if self.clipping_operation is None:
            return

        logger.debug("[VolumeViewer] Exiting clipping mode")
        self.interactor.SetInteractorStyle(self._default_interactor_style)
        logger.debug("[VolumeViewer] Switch interactor style to %s",
                     type(self.interactor.GetInteractorStyle()).__name__)

        # =====================================================
        # Clipping Operations
        # =====================================================

    def apply_clipping(self) -> None:
        """
        Convert the current preview region into a presistent state and
         record it in the history.
        """
        if self.clipping_operation is None:
            logger.warning("[VolumeViewer] Clipping operation not initialized")
            return

        # Fetch the polygon points collected by the interaction layer.
        disp_pts = list(getattr(self.clipping_operation, 'clip_points_display', []) or [])
        if len(disp_pts) < 3:
            logger.info("[VolumeViewer] Polygon is incomplete; skipping apply.")
            self.exit_clip_mode()
            return

        before = self.clipping_state
        polygon_ndc = self._display_points_to_ndc(disp_pts)

        after = ClippingState(
            enabled=True,
            mode=getattr(self.clipping_operation, 'clip_mode', ClipMode.REMOVE_INSIDE),
            polygon_ndc=polygon_ndc,
        )

        logger.info("[VolumeViewer] Applying clipping state via history manager.")
        try:
            self.history.do(Command(before=before, after=after), self.set_clipping_state)
        except Exception:
            logger.exception("[VolumeViewer] Failed to apply clipping state.")

        # Cleanup preview actors and mode state
        self._clear_clipper_visualization()
        try:
            self.clipping_operation.reset()
        except Exception:
            logger.exception("[VolumeViewer] Failed to reset clipping operation.")
        self.exit_clip_mode()

    def cancel_clipping(self) -> None:
        """Discard the current selection without recording any history."""
        if self.clipping_operation is None:
            logger.warning("[VolumeViewer] Clipping operation not initialized")
            return

        logger.info("[VolumeViewer] Canceling clipping operation.")
        try:
            self.clipping_operation.reset()
        except Exception:
            logger.debug("[VolumeViewer] Clipping operation reset failed.")

        self._clear_clipper_visualization()
        self.exit_clip_mode()

    def set_clipping_state(self, state: ClippingState) -> None:
        """
        Construct and apply the VTK clipping pipeline based on the provided state.

        This method handles coordinate transformation (NDC -> World) and
         updates the voluem mapper input.
        """
        self.clipping_state = state

        if self.volume is None or self._source_image is None:
            return

        mapper = self.volume.GetMapper()
        if mapper is None:
            return

        try:
            if (not state.enabled) or (not state.polygon_ndc):
                mapper.SetInputData(self._source_image)
                self._drop_clipping_pipeline_refs()
                self.update_view()
                return

            # Step 1: Recover screen pixels from NDC
            disp_pts = self._ndc_points_to_display(state.polygon_ndc)

            # Step 2: Project points to 3D. We use the 'center plane' approach
            # to ensure the world-space polygon matches the user's screen-space drawing.
            camera = self.renderer.GetActiveCamera()
            world_pts = self._project_display_to_center_plane(disp_pts, )
            if len(world_pts) < 3:
                mapper.SetInputData(self._source_image)
                self._drop_clipping_pipeline_refs()
                self.update_view()
                return

            # Step 3: Define the clipping boundary using on implicit selection loop.
            camera = self.renderer.GetActiveCamera()
            fp = camera.GetFocalPoint()
            view_vec = geometry_utils.direction_vector(camera.GetPosition(), fp)
            norm = geometry_utils.calculate_norm(view_vec) or 1.0
            view_dir = [v / norm for v in view_vec]

            vtk_points = vtk.vtkPoints()
            for p in world_pts:
                vtk_points.InsertNextPoint(*p)

            loop = vtk.vtkImplicitSelectionLoop()
            loop.SetLoop(vtk_points)
            loop.SetNormal(*view_dir)
            loop.AutomaticNormalGenerationOff()

            # Step 4: ;build the stencil pipeline.
            # This creates a binary mask in the shape of our extruded polygon.
            stenciler = vtk.vtkImplicitFunctionToImageStencil()
            stenciler.SetInput(loop)
            stenciler.SetOutputSpacing(self._source_image.GetSpacing())
            stenciler.SetOutputOrigin(self._source_image.GetOrigin())
            stenciler.SetOutputWholeExtent(self._source_image.GetExtent())
            stenciler.Update()

            # Step 5: Mask the source image.
            # Voxels inside/outside the stencil are replaced with CLIPPED_SCALAR.
            img_stencil = vtk.vtkImageStencil()
            img_stencil.SetInputData(self._source_image)
            img_stencil.SetStencilConnection(stenciler.GetOutputPort())

            if state.mode is ClipMode.REMOVE_INSIDE:
                img_stencil.ReverseStencilOn()
            else:
                img_stencil.ReverseStencilOff()

            img_stencil.SetBackgroundValue(CLIPPED_SCALAR)
            img_stencil.Update()

            self._clipping_loop = loop
            self._clipping_stenciler = stenciler
            self._clipping_image_stencil = img_stencil

            # Update the rendering pipeline.
            mapper.SetInputConnection(img_stencil.GetOutputPort())
            mapper.Modified()
            self.update_view()

        except Exception:
            logger.exception(
                "[VolumeViewer] Rendering pipeline failed; falling back to original image.")
            mapper.SetInputData(self._source_image)
            self._drop_clipping_pipeline_refs()
            self.update_view()

    def _drop_clipping_pipeline_refs(self) -> None:
        """Clear the reference to the active clipping filters."""
        self._clipping_loop = None
        self._clipping_stenciler = None
        self._clipping_img_stencil = None

    def _display_points_to_ndc(
            self,
            display_points: Sequence[tuple[float, float]],
    ) -> tuple[tuple[float, float], ...]:
        """Convert pixel coordinates to 0..1 range (origin bottom-left)."""
        size = self.vtk_widget.size()
        w = max(1, int(size.width()))
        h = max(1, int(size.height()))
        return tuple((float(x) / w, float(y) / h) for x, y in display_points)

    def _ndc_points_to_display(
            self,
            ndc_points: Sequence[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        """Restore pixel coordinates from 0..1 range (origin bottom-left)."""
        size = self.vtk_widget.size()
        w = max(1, int(size.width()))
        h = max(1, int(size.height()))
        return [(float(nx) * w, float(ny) * h) for nx, ny in ndc_points]

    def _project_display_to_center_plane(
            self,
            display_points: Sequence[tuple[float, float]],
    ) -> list[tuple[float, float, float]]:
        """
        Project screen pixels onto a 3D plane passing through the volume's center.
        Ensures the restored world-space polygon matches the user's initial screen selection.
        """
        if not display_points:
            return []

        center = self.get_volume_center()

        # Get the screen depth (Z-buffer value) of the volume center.
        self.renderer.SetWorldPoint(center[0], center[1], center[2], 1.0)
        self.renderer.WorldToDisplay()
        _, _, depth = self.renderer.GetDisplayPoint()

        projected: list[tuple[float, float, float]] = []
        for x, y in display_points:
            self.renderer.SetDisplayPoint(float(x), float(y), float(depth))
            self.renderer.DisplayToWorld()
            wx, wy, wz, w = self.renderer.GetWorldPoint()
            if w != 0.0:
                wx /= w
                wy /= w
                wz /= w
            projected.append((float(wx), float(wy), float(wz)))
        return projected

    def _clear_clipper_visualization(self) -> None:
        """Clear the clipping region visualization."""
        logger.debug("[VolumeViewer] Clearing clipping region visualization")
        self.clipper_polydata.Initialize()
        self.update_view()

    def enter_clip_result_mode(self) -> None:
        """
        Enter clip result mode

        This mode is entered after finalizing the clip region,
        allowing the user to apply or cancel the clipping operation.
        """
        logger.debug("[VolumeViewer] Entering clip result mode")
        self.interactor.SetInteractorStyle(self._default_interactor_style)
        logger.debug("[VolumeViewer] Switch interactor style to %s",
                     type(self.interactor.GetInteractorStyle()).__name__)

        self.update_clipper_visualization()
        self.update_view()

    def _on_camera_interaction(self, obj, event):
        """Handle camera interaction events."""
        if self.clipping_operation is None:
            return
        self.clipping_operation.on_camera_updated()

    def update_clipper_visualization(self) -> None:
        """Update the visual representation of the clipping region."""
        if self.clipping_operation is None:
            return

        world_points = self.clipping_operation.get_preview_world_points()

        if not world_points:
            self.clipper_polydata.Initialize()
            self.update_view()
            return

        camera = self.renderer.GetActiveCamera()
        cam_pos = camera.GetPosition()
        bounds = self.renderer.ComputeVisiblePropBounds()
        diag = math.sqrt(
            sum((bounds[2 * i + 1] - bounds[2 * i]) ** 2 for i in range(3))
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
        
    # =====================================================
    # Camera helpers
    # =====================================================

    def _set_camera_parallel_from_current(self) -> None:
        """
        Helper to switch the active camera to parallel projection,
        computing a suitable parallel scale from the perspective camera parameters or
        visible bounds.
        """
        cam: vtk.vtkCamera = self.renderer.GetActiveCamera()
        pos = cam.GetPosition()
        fp = cam.GetFocalPoint()
        dist = math.dist(pos, fp)
        if dist == 0.0:
            dist = 1.0
        angle_rad = math.radians(cam.GetViewAngle())
        if angle_rad > 1e-6:
            parallel_scale = dist * math.tan(angle_rad / 2.0)
        else:
            bounds = self.renderer.ComputeVisiblePropBounds()
            diag = math.sqrt(
                sum((bounds[2 * i + 1] - bounds[2 * i]) ** 2 for i in range(3))
            ) or 1.0
            parallel_scale = diag * 0.5
        cam.ParallelProjectionOn()
        cam.SetParallelScale(parallel_scale)
        self.renderer.ResetCameraClippingRange()
