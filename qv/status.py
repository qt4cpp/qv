from dataclasses import dataclass
from typing import Callable


@dataclass
class StatusField:
    """
    Represents a status field containing a label, format, formatter function, and a value.

    This class is used to model a field for status representation, allowing formatted
    output through a customizable formatter function. It provides an interface for
    defining labels, formatting strings, and managing a value of type float or int.

    :ivar label: The label/name of the status field.
    :type label: str
    :ivar fmt: The format string used for formatting the field's value.
    :type fmt: str
    :ivar formatter: Callable function to format the field value. Defaults to a formatter
        using the provided `fmt` string, unless explicitly specified.
    :type formatter: Callable[[any], str]
    :ivar value: The numerical value associated with the status field, either a float or int.
    :type value: float | int
    """
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


# If you want to add a new value, add field and then,
# you should add property and setter for the field in VolumeViewer class.
STATUS_FIELDS = {
    "window_level": StatusField(label="WL", fmt="{:.2f}"),
    "window_width": StatusField(label="WW", fmt="{:.2f}"),
    "delta_per_pixel": StatusField(label="dp/px", fmt="{}"),
    "azimuth": StatusField(label="Azimuth", formatter=format_azimuth),
    "elevation": StatusField(label="Elevation", formatter=format_elevation),
}

