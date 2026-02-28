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
    """Rendering quality/performance preset.

    This profile controls mapper/property parameters for:
    - normal (idle) rendering
    - interactive (mouse drag, rotate, etc.) rendering
    """

    # Preset identifier
    name: str

    # Enable shading in normal mode
    # True: better depth perception, but heavier rendering.
    # False: faster, flatter appearance.
    shade_enabled: bool

    # Screen-space image sampling distance for normal mode.
    # 1.0 means full internal render resolution.
    # > 1.0 reduces internal resolution (faster, lower quality).
    # < 1.0 can improve quality at the cost of performance.
    image_sample_distance: float

    # Let VTK dynamically adjust sample distances by frame time/load.
    # True: adaptive performance.
    # False: keep explicit sample distance settings.
    auto_adjust_sample_distances: bool

    # Screen-space image sampling distance while interacting.
    # Usually larger than normal mode to prioritize responsiveness.
    # Recommend: >= 1.0
    interactive_image_sample_distance: float

    # Enable shading while interacting.
    # True: better depth perception, but heavier rendering.
    # False: faster, flatter appearance.
    interactive_shade_enabled: bool

    # Enable ray jittering in normal mode.
    # True: reduces structured banding artifacts at the cost of slight noise.
    use_jittering: bool

    # Enable ray jittering while interacting.
    # Usually disabled for responsiveness.
    interactive_use_jittering: bool

    def __post_init__(self) -> None:
        if self.image_sample_distance <= 0.0:
            raise ValueError("Image sample distance must be > 0.")
        if self.interactive_image_sample_distance <= 0.0:
            raise ValueError("Interactive image sample distance must be > 0.")

_PRESETS: Final[dict[str, PerformanceProfile]] = {
    "speed": PerformanceProfile(
        name="speed",
        shade_enabled=False,
        image_sample_distance=1.5,
        auto_adjust_sample_distances=True,
        interactive_image_sample_distance=2.5,
        interactive_shade_enabled=False,
        use_jittering=False,
        interactive_use_jittering=False,
    ),
    "balanced": PerformanceProfile(
        name="balanced",
        shade_enabled=True,
        image_sample_distance=1.0,
        auto_adjust_sample_distances=True,
        interactive_image_sample_distance=2.0,
        interactive_shade_enabled=False,
        use_jittering=False,
        interactive_use_jittering=False,
    ),
    "quality": PerformanceProfile(
        name="quality",
        shade_enabled=True,
        image_sample_distance=1.0,
        auto_adjust_sample_distances=False,
        interactive_image_sample_distance=1.0,
        interactive_shade_enabled=True,
        use_jittering=True,
        interactive_use_jittering=True,
    ),
}


def get_profile(name: str = "balanced") -> PerformanceProfile:
    """Return a preset profile by name."""
    key = name.lower().strip()
    if key not in _PRESETS:
        valid = ", ".join(sorted(_PRESETS.keys()))
        raise ValueError(f"Invalid profile name: {name}. Valid profiles: {valid}")
    return _PRESETS[key]
