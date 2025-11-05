"""Camera state management separated from UI concerns."""
from __future__ import annotations
from dataclasses import dataclass
import logging


@dataclass
class CameraAngle:
    "Immutable representation of camera angles in degrees."
    azimuth: float
    elevation: float

    def __post_init__(self):
        self.azimuth = self.azimuth % 360
        self.elevation = self.elevation % 360

    def __str__(self) -> str:
        return f"Azimuth: {self.azimuth:.1f}, Elevation: {self.elevation:.1f}"


class CameraStateManager:
    """
    Manages camera state (angles, position) independently.

    Responsible for:
    - Tracking camera angles and position.
    - Callbacks for camera state changes.
    - Don't have concerns about UI.
    """

    def __init__(self):
        self._angle: CameraAngle = CameraAngle(0.0, 0.0)
        self._on_angle_changed_callbacks: list[callable] = []

    @property
    def angle(self) -> CameraAngle:
        """Get current camera angle."""
        return self._angle

    @property
    def azimuth(self) -> float:
        """Get current camera azimuth angle."""
        return self._angle.azimuth

    @property
    def elevation(self) -> float:
        """Get current camera elevation angle."""
        return self._angle.elevation

    def set_angle(self, angle: CameraAngle | float, elevation: float | None = None) -> None:
        """
        Set camera angle.

        :param angle: CameraAngle object or azimuthvalue
        :param elevation:
        """
        if isinstance(angle, CameraAngle):
            new_angle = angle
        else:
            if elevation is None:
                raise TypeError("Elevation is required when angle is not a CameraAngle object.")
            new_angle = CameraAngle(angle, elevation)

        if new_angle.azimuth != self._angle.azimuth or \
            new_angle.elevation != self._angle.elevation:
            self._angle = new_angle
            self._notify_angle_changed()

    def add_angle_changed_callback(self, callback: callable) -> None:
        """
        Add a callback for camera angle changes.

        Callback signature: callback(angle: CameraAngle)-> None
        """
        self._on_angle_changed_callbacks.append(callback)

    def remove_angle_changed_callback(self, callback: callable) -> None:
        """Remove a callback for camera angle changes."""
        self._on_angle_changed_callbacks.remove(callback)

    def _notify_angle_changed(self) -> None:
        """Notify callbacks of camera angle changes."""
        for callback in self._on_angle_changed_callbacks:
            try:
                callback(self._angle)
            except Exception as e:
                logging.exception(f"Error in callback: {e}")
