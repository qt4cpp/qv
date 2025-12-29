from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClippingState:
    """
    Immutable clipping state containing multiple clipping regions.

    Key points:
    - The underlying vtkImageData must NOT be modified.
    - We store the polygon in NDC coodinates (0..1) for stability across resizing.
    - We do Not store VTK objects here (vtkImplicitSelectionLoop, filters, etc.).
    - Those are derived artifacts and belong to the viewer/pipeline layer.
    """
    mask_zlib: bytes | None

    @property
    def enabled(self) -> bool:
        """Return True if any clipping region is defined."""
        return self.mask_zlib is not None

    @staticmethod
    def default() -> ClippingState:
        """Return a default clipping state."""
        return ClippingState(mask_zlib=None)
