"""Performance profile for volume rendering.

This module provides a performance profiling tool for volume rendering applications.
It allows users to monitor and analyze the performance characteristics of rendering operations,
such as rendering time, memory usage, and frame rate, to optimize rendering performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class PerformanceProfile:
    """Rendering quality profile for normal and interactive states."""
    name: str
    shade_enabled: bool
    image_sample_distance: float
    auto_adjust_sample_distance: bool
    interactive_image_sample_distance: float
    interactive_shade_enabled: bool

    def __post_init__(self) -> None:
        if self.image_sample_distance <= 0.0:
            raise ValueError("Image sample distance must be > 0.")
        if self.interactive_image_sample_distance <= 0.0:
            raise ValueError("Interactive image sample distance must be > 0.")

_PRESETS: Final[dict[str, PerformanceProfile]] = {
    "speed": PerformanceProfile(
        name="speed",
        shade_enabled=False,
        image_sample_distance=2.0,
        auto_adjust_sample_distance=True,
        interactive_image_sample_distance=4.0,
        interactive_shade_enabled=False,
    ),
    "balanced": PerformanceProfile(
        name="balanced",
        shade_enabled=True,
        image_sample_distance=1.0,
        auto_adjust_sample_distance=True,
        interactive_image_sample_distance=2.5,
        interactive_shade_enabled=False,
    ),
    "quality": PerformanceProfile(
        name="quality",
        shade_enabled=True,
        image_sample_distance=0.5,
        auto_adjust_sample_distance=False,
        interactive_image_sample_distance=1.5,
        interactive_shade_enabled=True,
    ),
}


def get_profile(name: str = "balanced") -> PerformanceProfile:
    """Return a preset profile by name."""
    key = name.lower().strip()
    if key not in _PRESETS:
        valid = ", ".join(sorted(_PRESETS.keys()))
        raise ValueError(f"Invalid profile name: {name}. Valid profiles: {valid}")
    return _PRESETS[key]
