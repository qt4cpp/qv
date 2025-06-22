from dataclasses import dataclass
from typing import Callable


@dataclass
class StatusField:
    label: str
    fmt: str = "{}"
    formatter: Callable[[any], str] = None
    value: float | int = 0.0

    def __post_init__(self):
        if self.formatter is None:
            self.formatter = lambda v, fmt = self.fmt: fmt.format(v)



def format_azimuth(azimuth: float) -> str:
    """
    Format the azimuth angle on vtk in degrees.
    + -> LAO
    - -> RAO
    """
    angle = abs(azimuth)
    if azimuth >= 0:
        return f"LAO {angle:.2f}"
    else:
        return f"RAO {angle:.2f}"


def format_elevation(elevation: float) -> str:
    """
    Format the elevation angle on vtk in degrees.
    + -> CAU
    - -> CRA
    """
    angle = abs(elevation)
    if elevation >= 0:
        return f"CAU {angle:.2f}"
    else:
        return f"CRA {angle:.2f}"


STATUS_FIELDS = {
    "window_level": StatusField(label="WL", fmt="{:.2f}"),
    "window_width": StatusField(label="WW", fmt="{:.2f}"),
    "azimuth": StatusField(label="Azimuth", formatter=format_azimuth),
    "elevation": StatusField(label="Elevation", formatter=format_elevation),
}

