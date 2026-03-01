from __future__ import annotations

import enum
import logging

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
    """MPR viewer class."""

    def setup_interactor(self) -> None:
        raise NotImplementedError

    def load_mpr(self, *args, **kwargs) -> None:
        raise NotImplementedError
