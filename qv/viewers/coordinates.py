from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QtDisplayPoint:
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class VtkDisplayPoint:
    x: int
    y: int


def qt_to_vtk_display(point: QtDisplayPoint, *, widget_height: int) -> VtkDisplayPoint:
    """
    Convert a Qt widget-local mouse position into VTK display coordinates.

    Qt:
    - origin at top-left
    - y grows downward

    VtK display:
    - origin at bottom-left
    - y grows upward
    """
    return VtkDisplayPoint(
        x=int(point.x),
        y=int(widget_height - 1 - point.y),
    )


def vtk_to_qt_display(point: VtkDisplayPoint, *, widget_height: int) -> QtDisplayPoint:
    """Convert a VTK display point into Qt widget-local coordinates."""
    return QtDisplayPoint(
        x=int(point.x),
        y=int(widget_height - 1 - point.y),
    )