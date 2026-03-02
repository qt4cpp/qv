from __future__ import annotations

import enum
import logging

import vtk
from PySide6 import QtCore

from qv.core.window_settings import WindowSettings
from qv.viewers.base_viewer import BaseViewer

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
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
    ),
    MprPlane.CORONAL: (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        -1.0,
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
        self._window_settings: WindowSettings = WindowSettings(level=300.0, width=30.0)

        self._image_actor: vtk.vtkImageActor | None = None
        self._interactor_style: vtk.vtkInteractorStyleImage | None = None

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
        self._wl_map.SetWindow(self._window_settings.width)
        self._wl_map.SetLevel(self._window_settings.level)

        self._image_actor = vtk.vtkImageActor()
        self._image_actor.GetMapper().SetInputConnection(self._wl_map.GetOutputPort())

        self.renderer.AddActor(self._image_actor)
        self.renderer.ResetCamera()

    def setup_interactor_style(self) -> None:
        """Use image interactor style (observer wiring will be added later)."""
        self._interactor_style = vtk.vtkInteractorStyleImage()
        self.interactor.SetInteractorStyle(self._interactor_style)

    def load_data(self, image_data: vtk.vtkImageData) -> None:
        """BaseViewer abstract method implementation."""
        self.set_image_data(image_data)

    def set_image_data(self, image_data: vtk.vtkImageData) -> None:
        """Set the image data."""
        if self._reslice is None or self._wl_map is None:
            return

        self._image_data = image_data
        self._reslice.SetInputData(image_data)
        logger.info("MPR image data loaded")

        smin, smax = image_data.GetScalarRange()
        width = max(1.0, min(float(smax - smin), 1024.0))
        level = (float(smin) + float(smax)) / 2.0
        self._window_settings = WindowSettings(level=level, width=width)
        self._wl_map.SetWindow(self._window_settings.width)
        self._wl_map.SetLevel(self._window_settings.level)

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
        camera.SetViewUp(0.0, 1.0, 0.0)

        self.renderer.ResetCamera()
        self.renderer.ResetCameraClippingRange()
