"""Window settings for medical image display."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WindowSettings:
    """
    Immutable representation of window settings for medical image display.

    In medical imaging, a "window" is defined by:
    - level: The center value of the displayed range (also called "center")
    - width: The range of values to display

    The displayed range is [level - width/2, level + width/2].

    Attributes:
        level: The center value of the displayed range
        width: The range of values to display
    """
    level: float
    width: float

    MIN_WIDTH: float = 1.0

    def __post_init__(self) -> None:
        """Validate and normalize values after initialization."""
        if self.width < self.MIN_WIDTH:
            raise ValueError(f"Window width must be >= 1.0, got {self.width}.")



    def __str__(self) -> str:
        """Return a string representation of the window settings."""
        return f"Level: {self.level:.0f}, Width: {self.width:.0f}"

    def get_min(self) -> float:
        """Get the minimum value of the window."""
        return self.level - self.width / 2

    def get_max(self) -> float:
        """Get the maximum value of the window."""
        return self.level + self.width / 2

    def get_range(self) -> tuple[float, float]:
        """Get the minimum and maximum values of the window."""
        return self.get_min(), self.get_max()

    def clamp(self, scalar_range: tuple[float, float]) -> WindowSettings:
        """
        Return a new WindowSettings clamped to the scalar range.

        :param scalar_range: (min, max) scalar range.
        :return: New clamped WindowSettings instance
        """
        min_scalar, max_scalar = scalar_range
        max_width = max_scalar - min_scalar

        clamped_width = max(1.0, min(max_width, self.width))
        clamped_level = max(min_scalar, min(max_scalar, self.level))

        return WindowSettings(level=clamped_level, width=clamped_width)

    def adjust(self,
               delta_level: float,
               delta_width: float,
               scalar_range: tuple[float, float] = None
               ) -> WindowSettings:
        """
        Create a new WindowSettings with the given deltas applied.

        :param delta_level: Change in level (center)
        :param delta_width: Change in width (range)
        :param scalar_range: Optional scalar range for clamping.
        :return: New adjusted WindowSettings instance
        """
        new_level = self.level + delta_level
        new_width = self.width + delta_width

        try:
            adjusted = WindowSettings(level=new_level, width=new_width)
        except ValueError:
            return self

        if scalar_range is not None:
            adjusted = adjusted.clamp(scalar_range)

        return adjusted

    @classmethod
    def from_scalar_range(cls,
                          scalar_range: tuple[float, float],
                          level_fraction: float,
                          width_fraction: float
                          ) -> WindowSettings:
        """
        Create a WindowSettings instance from a scalar range and level/width.

        :param scalar_range: (min, max) scalar range.
        :param level_fraction: Center level of the window.
        :param width_fraction: Width of the window.
        :return: New WindowSettings instance
        """
        min_scalar, max_scalar = scalar_range
        full_range = max_scalar - min_scalar
        if full_range <= 0:
            return cls(level=min_scalar, width=cls.MIN_WIDTH)

        level = min_scalar + level_fraction * full_range
        width = max(cls.MIN_WIDTH, width_fraction * full_range)

        return cls(level=level, width=width)
