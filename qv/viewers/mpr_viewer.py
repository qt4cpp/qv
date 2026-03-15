from __future__ import annotations

import enum
import logging

import vtk
from PySide6 import QtCore

from qv.core.window_settings import WindowSettings
from qv.viewers.base_viewer import BaseViewer
from qv.viewers.interactor_styles.mpr_interactor_style import MprInteractorStyle

logger = logging.getLogger(__name__)


class MprPlane(enum.Enum):
    """MPR plane enumeration."""

    AXIAL = "axial"
    CORONAL = "coronal"
    SAGITTAL = "sagittal"


# Direction cosines for vtkImageReslice.SetResliceAxesDirectionCosines(...)
# (x_axis, y_axis, z_axis) as 3x3 row-major values.
PLANE_AXES: dict[MprPlane, tuple[float, float, float, float, float, float, float, float, float]] = {
    MprPlane.AXIAL: (
        1.0,
        0.0,
        0.0,
        0.0,
        -1.0,
        0.0,
        0.0,
        0.0,
        -1.0,
    ),
    MprPlane.CORONAL: (
        -1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        1.0,
        0.0,
    ),
    MprPlane.SAGITTAL: (
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        1.0,
        0.0,
        0.0,
    ),
}


PLANE_AXES_INDEX: dict[MprPlane, int] = {
    MprPlane.AXIAL: 2,
    MprPlane.CORONAL: 1,
    MprPlane.SAGITTAL: 0,
}


class MprViewer(BaseViewer):
    """2D MPR viewer."""

    sliceChanged = QtCore.Signal(object, int)

    def __init__(self, settings_manager=None, parent=None) -> None:
        self._image_data: vtk.vtkImageData | None = None
        self._plane: MprPlane = MprPlane.AXIAL
        self._slice_index: int = 0
        self._slice_min: int = 0
        self._slice_max: int = 0

        self._reslice: vtk.vtkImageReslice | None = None
        self._wl_map: vtk.vtkImageMapToWindowLevelColors | None = None

        self._image_actor: vtk.vtkImageActor | None = None
        self._interactor_style: vtk.vtkInteractorStyleImage | None = None
        self.delta_per_pixel: float = 1.0

        super().__init__(settings_manager, parent)
        self._setup_pipeline()

    def _setup_pipeline(self) -> None:
        """Build VTK image pipeline for MPR viewer."""
        self._reslice = vtk.vtkImageReslice()
        self._reslice.SetOutputDimensionality(2)
        self._reslice.SetInterpolationModeToLinear()
        self._reslice.SetAutoCropOutput(True)

        # Prevent warnings from unset input during startup.
        dummy = vtk.vtkImageData()
        dummy.SetDimensions(1, 1, 1)
        dummy.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
        self._reslice.SetInputData(dummy)

        self._wl_map = vtk.vtkImageMapToWindowLevelColors()
        self._wl_map.SetInputConnection(self._reslice.GetOutputPort())

        self._image_actor = vtk.vtkImageActor()
        self._image_actor.GetMapper().SetInputConnection(self._wl_map.GetOutputPort())

        self.renderer.AddActor(self._image_actor)
        self.renderer.ResetCamera()

    def setup_interactor_style(self) -> None:
        """Use image interactor style and bindd mouse-wheel slice navigation."""
        self._interactor_style = MprInteractorStyle(self)
        self.interactor.SetInteractorStyle(self._interactor_style)


    def load_data(self, image_data: vtk.vtkImageData) -> None:
        """BaseViewer abstract method implementation."""
        self.set_image_data(image_data)

    def _apply_window_settings(self, setting: WindowSettings) -> bool:
        if self._wl_map is None:
            return False

        self._wl_map.SetWindow(setting.width)
        self._wl_map.SetLevel(setting.level)
        self._wl_map.Modified()
        logger.debug("WL/WW map applied: %.1f, %.1f",
                     self._wl_map.GetLevel(), self._wl_map.GetWindow())
        return True

    @property
    def image_data(self) -> vtk.vtkImageData | None:
        """Expose loaded image  data for interactor-style checks."""
        return self._image_data

    def _get_scalar_range(self) -> tuple[float, float] | None:
        """Return the current scalar range when image data is loaded."""
        if self._image_data is None:
            return None
        return self._image_data.GetScalarRange()

    def _build_initial_window_settings(
            self,
            scalar_range: tuple[float, float],
    ) -> WindowSettings:
        """Create initial WW/WL using the same policy as VolumeViewer."""
        min_scalar, max_scalar = scalar_range
        scalar_width = max(1.0, max_scalar - min_scalar)
        level = round((min_scalar + max_scalar) / 2.0)
        width = round(max(1.0, min(scalar_width, 1024.0)))
        return WindowSettings(level=level, width=width)

    def set_window_settings(
            self,
            settings: WindowSettings,
            *,
            emit_signal: bool = True,
            render: bool = True,
    ) -> None:
        """Set WW/WL via BaseViewer contract after clamping to loaded image data."""
        scalar_range = self._get_scalar_range()
        if scalar_range is None:
            logger.warning("Cannot set window settings: image not loaded.")
            return

        clamped = settings.clamp(scalar_range)
        if clamped == self._window_settings:
            return

        super().set_window_settings(clamped, emit_signal=emit_signal, render=render)

    def set_image_data(self, image_data: vtk.vtkImageData) -> None:
        """Set the image data."""
        if self._reslice is None or self._wl_map is None:
            return

        self._image_data = image_data
        self._reslice.SetInputData(image_data)
        logger.info("MPR image data loaded")

        self.set_window_settings(
            self._build_initial_window_settings(self._image_data.GetScalarRange()),
            emit_signal=False,
            render=False,
        )

        self._recompute_slice_range()
        self._slice_index = (self._slice_min + self._slice_max) // 2

        self._update_reslice()
        self._setup_camera(self._plane)
        self.update_view()
        self.dataLoaded.emit()

    def _recompute_slice_range(self) -> None:
        """Recompute valid slice index range from current image and plane."""
        if self._image_data is None:
            self._slice_min = 0
            self._slice_max = 0
            return

        extent = self._image_data.GetExtent()
        axis = PLANE_AXES_INDEX[self._plane]
        self._slice_min = int(extent[2 * axis])
        self._slice_max = int(extent[2 * axis + 1])

    def set_plane(self, plane: MprPlane) -> None:
        """Switch current MPR plane and reset slice to center."""
        if self._image_data is None:
            self._plane = plane
            return

        if self._plane == plane:
            return

        self._plane = plane
        self._recompute_slice_range()
        self._slice_index = (self._slice_min + self._slice_max) // 2

        self._update_reslice()
        out = self._reslice.GetOutput()
        logger.debug("reslice output bounds: %s", out.GetBounds() if out else None)
        logger.debug("reslice output extent: %s", out.GetExtent() if out else None)
        logger.debug("image_actor bounds: %s", self._image_actor.GetBounds())

        self._setup_camera(self._plane)
        self.update_view()
        self.sliceChanged.emit(self._plane, self._slice_index)

    def _update_reslice(self) -> None:
        """Update the reslice parameters."""
        if self._reslice is None or self._image_data is None:
            return

        self._reslice.SetResliceAxesDirectionCosines(*PLANE_AXES[self._plane])

        extent = self._image_data.GetExtent()
        spacing = self._image_data.GetSpacing()
        origin = self._image_data.GetOrigin()

        cx = origin[0] + (extent[0] + extent[1]) / 2.0 * spacing[0]
        cy = origin[1] + (extent[2] + extent[3]) / 2.0 * spacing[1]
        cz = origin[2] + (extent[4] + extent[5]) / 2.0 * spacing[2]

        world_origin = [cx, cy, cz]

        axis = PLANE_AXES_INDEX[self._plane]
        world_origin[axis] = origin[axis] + self._slice_index * spacing[axis]

        self._reslice.SetResliceAxesOrigin(world_origin[0], world_origin[1], world_origin[2])
        self._reslice.Modified()
        self._reslice.Update()

        # Display Extent をリセットして全体を表示させる
        if self._image_actor is not None:
            out = self._reslice.GetOutput()
            if out is not None:
                we = out.GetExtent()
                self._image_actor.SetDisplayExtent(we[0], we[1], we[2], we[3], we[4], we[5])

    def _setup_camera(self, plane: MprPlane) -> None:
        """Configure the camera for the given plane."""
        if self._image_data is None:
            return

        bounds = self._image_data.GetBounds()
        bx = bounds[1] - bounds[0]
        by = bounds[3] - bounds[2]

        if max(bx, by) < 1e-6:
            return

        # ボリュームの物理的な中心を計算
        cx = 0.5 * (bounds[0] + bounds[1])
        cy = 0.5 * (bounds[2] + bounds[3])
        cz = 0.5 * (bounds[4] + bounds[5])

        dist = max(bx, by, 1.0) * 2.0

        camera = self.renderer.GetActiveCamera()
        camera.SetParallelProjection(True)
        camera.SetFocalPoint(cx, cy, cz)
        camera.SetPosition(cx, cy, cz + dist)
        # Keep camera direction on +Z (stable), and flip vertical orientation only.
        camera.SetViewUp(0.0, -1.0, 0.0)
        camera.OrthogonalizeViewUp()

        self.renderer.ResetCamera()
        self.renderer.ResetCameraClippingRange()

    def set_slice_index(self, index: int) -> None:
        """Set the current slice index for the active plane and refresh the view.

        The inpt index is clamped to the valid range: [_slice_min, _slice_max].
        """
        if self._image_data is None:
            logger.debug("set_slice_index ignored because imag is not loaded.")
            return

        clamped_index = max(self._slice_min, min(int(index), self._slice_max))

        if clamped_index == self._slice_index:
            return

        self._slice_index = clamped_index
        self._update_reslice()
        self.update_view()
        self.sliceChanged.emit(self._plane, self._slice_index)

    def scroll_slice(self, delta: int) -> None:
        """Move slice index by a relative amount (e.g. +1, -1). """
        if self._image_data is None:
            logger.debug("scroll_slice ignored because imag is not loaded.")
            return

        self.set_slice_index(self._slice_index + int(delta))

    def get_slice_count(self) -> int:
        """Return the number of slices in the current plane."""
        if self._image_data is None:
            return 0

        # extent は両端を含むため、枚数は(max - min + 1)
        return self._slice_max - self._slice_min + 1

    def adjust_window_settings(self, dx: int, dy: int) -> None:
        """Adjust window settings by drag delta (dx -> width, dy -> level)."""
        scalar_range = self._get_scalar_range()
        if scalar_range is None:
            return

        current = self.window_settings
        if current is None:
            return

        adjusted = self._window_settings.adjust(
            delta_width=dx * self.delta_per_pixel,
            delta_level=-dy * self.delta_per_pixel,
            scalar_range=scalar_range,
        )
        self.set_window_settings(adjusted)
