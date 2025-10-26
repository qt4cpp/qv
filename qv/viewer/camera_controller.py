from __future__ import annotations
from typing import Literal, TYPE_CHECKING

import vtk
import logging


if TYPE_CHECKING:
    from qv.utils import vtk_helpers

logger = logging.getLogger(__name__)

ViewDirection = Literal['front', 'back', 'left', 'right', 'top', 'bottom']

class CameraPreset:
    """Camera preset configuration for standard views."""

    # Preset directions for each view (unit sphere)
    DIRECTIONS: dict[ViewDirection, tuple[float, float, float]] = {
        'front': (0.0, 1.0, 0.0),
        'back': (0.0, -1.0, 0.0),
        'left': (1.0, 0.0, 0.0),
        'right': (-1.0, 0.0, 0.0),
        'top': (0.0, 0.0, -1.0),
        'bottom': (0.0, 0.0, 1.0),
    }

    # Up vectors to keep orientation
    VIEWUPS = {
        'front': (0.0, 0.0, -1.0),
        'back': (0.0, 0.0, -1.0),
        'left': (0.0, 0.0, -1.0),
        'right': (0.0, 0.0, -1.0),
        'top': (0.0, -1.0, 0.0),
        'bottom': (0.0, 1.0, 0.0),
    }

    # Azimuth and elevation angles for status display.
    ANGLES = {
        'front': (0.0, 0.0),
        'back': (180, 0.0),
        'left': (90, 0.0),
        'right': (270, 0.0),
        'top': (0.0, 90.0),
        'bottom': (0.0, 270.0),
    }



class CameraController:
    """Handles camera operations."""

    def __init__(self, camera: vtk.vtkCamera, renderer: vtk.vtkRenderer) -> None:
        self.camera = camera
        self.renderer = renderer
        self._azimuth: float = 0.0
        self._elevation: float = 0.0
        self._patient_matrix: vtk.vtkMatrix4x4 | None = None

    @property
    def azimuth(self) -> float:
        """Current azimuth angle in degrees."""
        return self._azimuth

    @azimuth.setter
    def azimuth(self, value: float):
        self._azimuth = value % 360

    @property
    def elevation(self) -> float:
        """Current elecation angle in degrees."""
        return self._elevation

    @elevation.setter
    def elevation(self, value: float):
        self._elevation = value % 360

    def set_patient_matrix(self, matrix: vtk.vtkMatrix4x4) -> None:
        """Set the patient matrix for the camera."""
        self._patient_matrix = matrix

    def extract_patient_matrix_from_volume(self, volume: vtk.vtkVolume) -> None:
        """Extract the patient matrix from the volume."""
        if volume is None:
            self._patient_matrix = None
            return

        mapper = volume.GetMapper()
        if mapper is None:
            self._patient_matrix = None
            return

        image = mapper.GetInput()
        if hasattr(image, "GetDirectionMatrix"):
            self._patient_matrix = image.GetDirectionMatrix()
        else:
            self._patient_matrix = None

    def reset_camera(self) -> None:
        """Reset the camera to the default position."""

    def rotate(self, delta_azimuth: float, delta_elevation: float):
        """Rotate the camera by delta angles"""
        self.camera.Azimuth(delta_azimuth)
        self.camera.Elevation(delta_elevation)
        self.camera.OrthogonalizeViewUp()
        self.renderer.ResetCameraClippingRange()

        self._azimuth = (self._azimuth + delta_azimuth) % 360
        self._elevation = (self._elevation + delta_elevation) % 360

        self.renderer.ResetCameraClippingRange()

        return self._azimuth, self._elevation

    def set_preset_view(self, view: ViewDirection) -> tuple[float, float]:
        """
        Set the camera to a preset view angle.

        Handles patient coordinate transformation for DICOM images.
        """
        view = view.lower()

        if view not in CameraPreset.DIRECTIONS:
            logger.warning(f"Invalid view direction: {view}")
            return self._azimuth, self._elevation

        direction = CameraPreset.DIRECTIONS[view]
        view_up = CameraPreset.VIEWUPS[view]
        target_angles = CameraPreset.ANGLES[view]

        fp = self.camera.GetFocalPoint()
        pos = self.camera.GetPosition()
        distance = vtk_helpers.calculate_distance(fp, pos)

        if self._patient_matrix:
            direction = vtk_helpers.transform_vector(direction, self._patient_matrix)
            view_up = vtk_helpers.transform_vector(view_up, self._patient_matrix)

        new_pos = tuple(fp[i] + direction[i] * distance for i in range(3))

        self.camera.SetPosition(*new_pos)
        self.camera.SetFocalPoint(*fp)
        self.camera.SetViewUp(*view_up)

        self._azimuth, self._elevation = target_angles[0], target_angles[1]
        self.renderer.ResetCameraClippingRange()

        return self._azimuth, self._elevation

    def set_zoom(self, factor: float, default_distance: float | None = None) -> None:
        """
        Set the camera zoom level.

        :param factor: zoom factor  (1.0 = default, 2.0 = 2x zoom)
        :param default_distance: Default distance for factor = 1.0
        """
        fp = self.camera.GetFocalPoint()
        pos = self.camera.GetPosition()
        direction = vtk_helpers.direction_vector(fp, pos)
        norm = vtk_helpers.calculate_norm(direction)

        if norm == 0:
            logger.warning("Camera direction vector has zero length. Aborting set_zoom().")
            return

        unit_direction = tuple(d / norm for d in direction)

        if default_distance is None:
            default_distance = norm

        new_distance = default_distance / factor

        new_position = tuple(fp[i] + unit_direction[i] * new_distance for i in range(3))
        self.camera.SetPosition(*new_position)
        self.renderer.ResetCameraClippingRange()

        logger.debug(f"Camera zoom factor: {factor}, new distance: {new_distance}")

    def reset_to_bounds(self, bounds: tuple[float, float, float, float, float, float],
                        view: ViewDirection = 'front') -> None:
        """Reset the camera to the bounds of the volume."""
        center = (
            0.5 * (bounds[0] + bounds[1]),
            0.5 * (bounds[2] + bounds[3]),
            0.5 * (bounds[4] + bounds[5]),
        )

        # Calculate appropriate distance
        max_dim = max(
            bounds[1] - bounds[0],
            bounds[3] - bounds[2],
            bounds[5] - bounds[4],
        )
        distance = 2.0 * max_dim

        self.camera.SetFocalPoint(*center)
        self._set_preset_view_with_distance(view, center, distance)

    def _set_preset_view_with_distance(self, view: ViewDirection,
                                       focal_point: tuple[float, float, float],
                                       distance: float) -> None:
        """
        Set the camera preset view with a specified distance.
        :param view: Preset view name
        :param focal_point: Focal point to sue
        :param distance: Focals point to the focal point
        :return:
        """
        view = view.lower()

        if view not in CameraPreset.DIRECTIONS:
            logger.warning(f"Invalid view direction: {view}")
            return

        direction = CameraPreset.DIRECTIONS[view]
        view_up = CameraPreset.VIEWUPS[view]
        target_angles = CameraPreset.ANGLES[view]

        if self._patient_matrix:
            direction = vtk_helpers.transform_vector(direction, self._patient_matrix)
            view_up = vtk_helpers.transform_vector(view_up, self._patient_matrix)

        new_position = tuple(
            focal_point[i] + direction[i] * distance for i in range(3)
        )

        self.camera.SetPosition(*new_position)
        self.camera.SetFocalPoint(*focal_point)
        self.camera.SetViewUp(*view_up)

        self._azimuth, self._elevation = target_angles[0], target_angles[1]
        self.renderer.ResetCameraClippingRange()

    def get_position(self) -> tuple[float, float, float]:
        """Get the current camera position."""
        return tuple(self.camera.GetPosition())

    def get_focal_point(self) -> tuple[float, float, float]:
        """Get the current camera focal point."""
        return tuple(self.camera.GetFocalPoint())

    def get_view_up(self) -> tuple[float, float, float]:
        """Get the current camera view up vector."""
        return tuple(self.camera.GetViewUp())

    def get_distance(self) -> float:
        """Get the distance between the camera position and focal point."""
        fp = self.camera.GetFocalPoint()
        pos = self.camera.GetPosition()
        return vtk_helpers.calculate_distance(fp, pos)
