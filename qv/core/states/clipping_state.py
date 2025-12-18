from __future__ import annotations

from dataclasses import dataclass

from operations.clipping.clipping_operation import ClipMode


@dataclass(frozen=True)
class ClippingState:
    """
    Immutable clipping state.

    Key points:
    - The underlying vtkImageData must NOT be modified.
    - We store the polygon in NDC coodinates (0..1) for stability across resizing.
    - We do Not store VTK objects here (vtkImplicitSelectionLoop, filters, etc.).
    - Those are derived artifacts and belong to the viewer/pipeline layer.
    """
    enabled: bool
    mode: ClipMode
    polygon_ndc: tuple[tuple[float, float], ...] | None

    @staticmethod
    def default() -> ClippingState:
        """Return a default clipping state."""
        return ClippingState(enabled=False, mode=ClipMode.REMOVE_INSIDE, polygon_ndc=None)
