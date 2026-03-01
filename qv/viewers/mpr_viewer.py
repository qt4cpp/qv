from __future__ import annotations

import enum
import logging

import vtk

from qv.core.window_settings import WindowSettings
from qv.viewers.base_viewer import BaseViewer

logger = logging.getLogger(__name__)


class MprPlane(enum.Enum):
    """MPR plane enumeration."""

    AXIAL = "axial"
    CORONAL = "coronal"
    SAGITTAL = "sagittal"


# Direction cosines for vtkImageReslice.SetResliceAxesDirectionCoines(...)
# (x_axis, y_axis, z_axis) as 3x3 row-major values.
PLANE_AXES: dict[MprPlane, tuple[float, float, float, float, float, float, float, float, float]] = {
    MprPlane.AXIAL: (
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
    ),
    MprPlane.CORONAL: (
        1.0, 0.0, 0.0,
        0.0, 0.0, 1.0,
        0.0, -1.0, 0.0,
    ),
    MprPlane.SAGITTAL: (
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
        1.0, 0.0, 0.0,
    ),
}


PLANE_AXES_INDEX: deict[MprPlane, int] = {
    MprPlane.AXIAL: 2,
    MprPlane.CORONAL: 1,
    MprPlane.SAGITTAL: 0,
}


class MprViewer(BaseViewer):
    """2D MPR viewer."""

    def __init__(self, settings_manager=None, parent=None) -> None:
        self._image_data: vtk.vtkImageData | None = None
        self._plane: MprPlane = MprPlane.AXIAL
        self._slice_index: int = 0

        self._reslice: vtk.vtkImageReslice | None = None
        self._color_map: vtk.vtkWindowLevelLookupTable | None = None
        self._image_actor: vtk.vtkImageActor | None = None

        self._window_settings: WindowSettings = WindowSettings(level=300.0, width=30.0)
        self._interactor_style: vtk.vtkInteractorStyleImage | None = None

        super().__init__(settings_manager, parent)
        self._setup_pipeline()

    def _setup_pipeline(self) -> None:
        """Build VTK image pipeline for MPR viewer."""
        self._reslice = vtk.vtkImageReslice()
        self._reslice.SetOutputDimensionality(2)
        self._reslice.SetInterpolationModeToLinear()

        self._color_map = vtk.vtkWindowLevelLookupTable()
        self._color_map.SetWindow(self._window_settings.width)
        self._color_map.SetLevel(self._window_settings.level)
        self._color_map.Build()

        map_to_color = vtk.vtkImageMapToColors()
        map_to_color.SetLookupTable(self._color_map)
        map_to_color.SetInputConnection(self._reslice.GetOutputPort())

        self._image_actor = vtk.vtkImageActor()
        self._image_actor.GetMapper().SetInputConnection(map_to_color.GetOutputPort())

        self.renderer.AddActor(self._image_actor)
        self.renderer.ResetCamera()
        self.update_view()

    def setup_interactor(self) -> None:
        """Use image interactor style (observer wiring will be added later)."""
        self._interactor_style = vtk.vtkInteractorStyleImage()
        self.interactor.SetInteractorStyle(self._interactor_style)

    def load_data(self, image_data: vtk.vtkImageData) -> None:
        """BaseViewer abstract method implementation."""
        self.set_image_data(image_data)

    def set_image_data(self, image_data: vtk.vtkImageData) -> None:
        """Set the image data."""
        if self._reslice is None:
            return

        self._image_data = image_data
        self._reslice.SetInputData(image_data)

        extent = image_data.GetExtent()
        axis = PLANE_AXES_INDEX[self._plane]
        self._slice_min = int(extent[2 * axis])
        self._slice_max = int(extent[2 * axis + 1])
        self._slice_index = (self._slice_min + self._slice_max) // 2

        self._setup_camera(self._plane)
        self._update_reslice()
        self.update_view()
        self.dataLoaded.emit()

    def _update_reslice(self) -> None:
        """Update the reslice parameters."""
        if self._reslice is None:
            return

        extent = self._image_data.GetExtent()
        spacing = self._image_data.GetSpacing()
        origin = self._image_data.GetOrigin()

        center_idx =[
            (extent[0] + extent[1]) / 2.0,
            (extent[2] + extent[3]) / 2.0,
            (extent[4] + extent[5]) / 2.0,
        ]
        world_origin = [
            origin[0] + center_idx[0] * spacing[0],
            origin[1] + center_idx[1] * spacing[1],
            origin[2] + center_idx[2] * spacing[2],
        ]

        axis = PLANE_AXES_INDEX[self._plane]
        world_origin[axis] = origin[axis] + self._slice_index * spacing[axis]

        self._reslice.SetResliceAxesOrigin(world_origin[0], world_origin[1], world_origin[2])
        self._reslice.Modified()

    def _setup_camera(self, plane: MprPlane) -> None:
        """Configure the camera for the given plane."""
        if self._image_data is None:
            return

        bounds = self._image_actor.GetBounds()
        if bounds is None:
            return

        center = (
            0.5 * (bounds[0] + bounds[1]),
            0.5 * (bounds[2] + bounds[3]),
            0.5 * (bounds[4] + bounds[5]),
        )
        max_dim = max(
            bounds[1] - bounds[0],
            bounds[3] - bounds[2],
            bounds[5] - bounds[4],
            1.0
        )
        dist = max_dim * 2.0

        camera = self.renderer.GetActiveCamera()
        camera.SetParallelProjection(True)
        camera.SetFocalPoint(*center)

        if plane == MprPlane.AXIAL:
            camera.SetPosition(center[0], center[1], center[2] + dist)
            camera.SetViewUp(0.0, 1.0, 0.0)
        elif plane == MprPlane.CORONAL:
            camera.SetPosition(center[0], center[1] - dist, center[2])
            camera.SetViewUp(0.0, 0.0, 1.0)
        else: # SAGITTAL
            camera.SetPosition(center[0] + dist, center[1], center[2])
            camera.SetViewUp(0.0, 0.0, 1.0)

        self.renderer.ResetCamera()
        self.renderer.ResetCameraClippingRange()