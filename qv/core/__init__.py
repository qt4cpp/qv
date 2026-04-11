"""Core components layer - shared, view-independent functionality."""
from __future__ import annotations

from typing import TYPE_CHECKING

from qv.viewers.camera.camera_state import CameraAngle, CameraStateManager
from qv.core.geometry_utils import (
    calculate_distance,
    calculate_norm,
    direction_vector,
    transform_vector,
)

if TYPE_CHECKING:
    from qv.viewers.controllers.interaction_controller import InteractionController


__all__ = [
    "CameraAngle",
    "CameraStateManager",
    "calculate_distance",
    "calculate_norm",
    "direction_vector",
    "transform_vector",
    "InteractionController",
]


def __getattr__(name: str):
    if name == "InteractionController":
        from qv.viewers.controllers.interaction_controller import InteractionController
        return InteractionController
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
