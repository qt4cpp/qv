from __future__ import annotations

from dataclasses import dataclass, field

from operations.clipping.clipping_operation import ClipMode


@dataclass(frozen=True)
class ClipRegion:
    """A single clipping region."""
    mode: ClipMode
    polygon_world: tuple[tuple[float, float, float], ...]
    normal_world: tuple[float, float, float]


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
    regions: tuple[ClipRegion, ...] = field(default_factory=tuple)

    @property
    def enabled(self) -> bool:
        """Return True if any clipping region is defined."""
        return bool(self.regions)

    def add_region(
            self,
            mode: ClipMode,
            polygon_world: tuple[tuple[float, float, float], ...],
            normal_world: tuple[float, float, float],
    ) -> ClippingState:
        """Add a new clipping region."""
        new_region = ClipRegion(mode=mode, polygon_world=polygon_world, normal_world=normal_world)
        return ClippingState(regions=self.regions + (new_region,))

    @staticmethod
    def default() -> ClippingState:
        """Return a default clipping state."""
        return ClippingState(regions=())
