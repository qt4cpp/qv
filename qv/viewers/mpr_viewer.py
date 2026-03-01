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


class MprViewer(BaseViewer):
    """2D MPR viewer."""

    def __init__(self, settings_manager_=None, parent=None) -> None:
        self._image_data: vtk.vtkImageData | None = None
        self._plane: MprPlane = MprPlane.AXIAL
        self._slice_index: int = 0

        self._reslice: vtk.vtkImageReslice | None = None
        self._color_map: vtk.vtkWindowLevelLookupTable | None = None
        self._image_actor: vtk.vtkImageActor | None = None

        self._window_settings: WindowSettings = WindowSettings(level=300.0, width=30.0)
        self._interactor_style: vtk.vtkInteractorStyleImage | None = None

        super().__init__(settings_manager_, parent)
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
        self._image_data = image_data
        if self._reslice is None:
            return
        self._reslice.SetInputData(image_data)
        self.update_view()

