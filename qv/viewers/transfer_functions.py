"""Transfer function preset definitions for volume rendering."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Final, Iterable, Mapping

from qv.core.window_settings import WindowSettings


logger = logging.getLogger(__name__)

USER_PRESET_SCHEMA_VERSION: Final[int] = 1
SOURCE_BUILTIN: Final[str] = "builtin"
SOURCE_USER: Final[str] = "user"
VALID_SOURCES: Final[Iterable[str]] = (SOURCE_BUILTIN, SOURCE_USER)


@dataclass(frozen=True)
class TransferFunctionPreset:
    """
    Immutable transfer function preset definition.

    color_points and opacity_points use scalar coordinates. For CT presets these
    coordinates are expected to be HU values. The default_linear preset is a
    compatibility preset and is interpreted against the active WindwSettings.
    """

    name: str
    display_name: str
    default_window: WindowSettings | None
    color_points: tuple[tuple[float, float, float, float], ...]
    opacity_points: tuple[tuple[float, float], ...]
    gradient_opacity_points: tuple[tuple[float, float], ...] = ()
    scalar_opacity_unit_distance: float | None = None
    source: str = SOURCE_BUILTIN


@dataclass(frozen=True)
class TransferFunctionPoints:
    """
    Concrete transfer function points ready to be applied to VTK functions.

    color_points are `(scalar, r, g, b)` tuples.
    opacity_points and gradient_opacity_points are `(scalar, opacity)` tuples.
    """

    color_points: tuple[tuple[float, float, float, float], ...]
    opacity_points: tuple[tuple[float, float], ...]
    gradient_opacity_points: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class TransferFunctionRegistry:
    """Immutable transfer function preset registry."""

    presets: tuple[TransferFunctionPreset, ...]

    def get(self, name: str) -> TransferFunctionPreset | None:
        """Return a preset by stable name, or None when absent."""
        key = name.strip().lower()
        return self._preset_by_name().get(key)

    def names(self) -> tuple[str, ...]:
        """Return preset names in registry order."""
        return tuple(preset.name for preset in self.presets)

    def _preset_by_name(self) -> dict[str, TransferFunctionPreset]:
        return {preset.name.strip().lower(): preset for preset in self.presets}


def _preset_from_user_json(item: object) -> TransferFunctionPreset:
    """Convert one user preset JSON object into a TransferFunctionPreset."""

    if not isinstance(item, Mapping):
        raise ValueError("User transfer function preset JSON must be an object.")

    try:
        name = str(item["name"])
        display_name = str(item["display_name"])
        default_window = _window_settings_from_json(item.get("default_window"))
        color_points = _color_points_from_json(item["color_points"])
        opacity_points = _opacity_points_from_json(item["opacity_points"])
    except KeyError as exc:
        raise ValueError(
            f"User transfer function preset is missing required field: {exc.args[0]}"
        ) from exc

    gradient_opacity_points = _opacity_points_from_json(
        item.get("gradient_opacity_points", [])
    )

    scalar_opacity_unit_distance = item.get("scalar_opacity_unit_distance")
    if scalar_opacity_unit_distance is not None:
        scalar_opacity_unit_distance = float(scalar_opacity_unit_distance)

    preset = TransferFunctionPreset(
        name=name,
        display_name=display_name,
        default_window=default_window,
        color_points=color_points,
        opacity_points=opacity_points,
        gradient_opacity_points=gradient_opacity_points,
        scalar_opacity_unit_distance=scalar_opacity_unit_distance,
        source=SOURCE_USER,
    )

    validate_transfer_function_preset(preset)
    return preset


def _window_settings_from_json(item: object) -> WindowSettings | None:
    """Convert a default_window JSON object into WindowSettings."""
    if item is None:
        return None

    if not isinstance(item, Mapping):
        raise ValueError("default_window must be an object or null.")

    try:
        return WindowSettings(
            level=float(item["level"]),
            width=float(item["width"]),
        )
    except KeyError as exc:
        raise ValueError(
            f"default_window is missing required field: {exc.args[0]}."
        ) from exc


def _color_points_from_json(
        items: object,
) -> tuple[tuple[float, float, float, float], ...]:
    """Convert JSON color points into normalized scalar/RGB tuples."""
    if not isinstance(items, list):
        raise ValueError("color_points must be a list.")

    points: list[tuple[float, float, float, float]] = []
    for item in items:
        if not isinstance(item, list | tuple) or len(item) != 4:
            raise ValueError("color point must be [scalar, r, g, b].")

        scalar, red, green, blue = item
        points.append((
            float(scalar),
            float(red),
            float(green),
            float(blue),
        ))

    return tuple(points)


def _opacity_points_from_json(
        items: object,
) -> tuple[tuple[float, float], ...]:
    """Convert JSON opacity-like points into scalar/opacity tuples."""
    if not isinstance(items, list):
        raise ValueError("opacity_points must be a list.")

    points: list[tuple[float, float]] = []
    for item in items:
        if not isinstance(item, list | tuple) or len(item) != 2:
            raise ValueError("opacity point must be [scalar, opacity].")

        scalar, opacity = item
        points.append((float(scalar), float(opacity)))

    return tuple(points)


def _validate_user_presets(presets: tuple[TransferFunctionPreset, ...]) -> None:
    """Validate user preset names against builtin and other user presets."""
    builtin_names = {preset.name.strip().lower() for preset in _BUILTIN_PRESETS}

    for preset in presets:
        key = preset.name.strip().lower()
        if key in builtin_names:
            raise ValueError(
                f"User transfer function preset collides with builtin preset: "
                f"{preset.name}"
            )

    _validate_unique_names(presets)


def validate_transfer_function_preset(preset: TransferFunctionPreset) -> None:
    """Validate a transfer function preset and raise ValueError on failure."""
    if not preset.name.strip():
        raise ValueError("Transfer function preset name must not be empty.")

    if not preset.display_name.strip():
        raise ValueError(
            f"Transfer function preset display_name must not be  empty: {preset.name}"
        )

    if preset.source not in VALID_SOURCES:
        raise ValueError(
            f"Transfer function preset source is invalid: {preset.name}={preset.source}"
        )

    if not preset.color_points:
        raise ValueError(f"Transfer function preset color points are empty: {preset.name}")

    if not preset.opacity_points:
        raise ValueError(f"Transfer function preset opacity points are empty: {preset.name}")

    _validate_color_points(preset.name, preset.color_points)
    _validate_opacity_points(preset.name, preset.opacity_points, "opacity")
    _validate_opacity_points(
        preset.name,
        preset.gradient_opacity_points,
        "gradient opacity",
        allow_empty=True,
    )

    if (
            preset.scalar_opacity_unit_distance is not None
            and preset.scalar_opacity_unit_distance <= 0.0
    ):
        raise ValueError(
            f"Transfer function preset ScalarOpacityUnitDistance must be > 0.0: "
            f"{preset.name}={preset.scalar_opacity_unit_distance}"
        )


def _validate_color_points(
        preset_name: str,
        points: Iterable[tuple[float, float, float, float]],
) -> None:
    """Validate color point shape and normalized RGB ranges."""
    previous_scalar: float | None = None

    for point in points:
        if len(point) != 4:
            raise ValueError(
                f"Transfer function preset color point must be (scalar, r, g, b): "
                f"{preset_name}={point}"
            )

        scalar, red, green, blue = point
        _validate_monotonic_scalar(preset_name, "color", previous_scalar, scalar)
        previous_scalar = scalar

        for channel_name, value in (
            ("red", red),
            ("green", green),
            ("blue", blue),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"Transfer function preset color point channel {channel_name} must be "
                    f"in 0..1: {preset_name}={value}"
                )


def _validate_opacity_points(
        preset_name: str,
        points: Iterable[tuple[float, float]],
        label: str,
        *,
        allow_empty: bool = False,
) -> None:
    """Validate opacity-like point shape and normalized value ranges."""
    points = tuple(points)
    if not points and allow_empty:
        return

    previous_scalar: float | None = None

    for point in points:
        if len(point) != 2:
            raise ValueError(
                f"Transfer function preset {label} point must be (scalar, opacity): "
                f"{preset_name}"
            )

        scalar, opacity = point
        _validate_monotonic_scalar(preset_name, label, previous_scalar, scalar)
        previous_scalar = scalar
        if not 0.0 <= opacity <= 1.0:
            raise ValueError(
                f"Transfer function preset {label} point opacity must be in 0..1: "
                f"{preset_name}={opacity}"
            )


def _validate_monotonic_scalar(
        preset_name: str,
        label: str,
        previous_scalar: float | None,
        scalar: float,
) -> None:
    """
    Keep points sorted by scalar value.

    VTK can accept pints in many orders, but sorted preset data is easier to
    review and makes JSON import/export deterministic later.
    """
    if previous_scalar is not None and scalar < previous_scalar:
        raise ValueError(
            f"Transfer function preset {label} point scalar must be sorted by scalar: "
            f"{preset_name}"
        )


def list_transfer_function_presets() -> tuple[TransferFunctionPreset, ...]:
    """Return built-in transfer function presets in stable UI order."""
    return _BUILTIN_PRESETS


def get_transfer_function_preset(name: str) -> TransferFunctionPreset:
    """Return transfer function preset by stable name."""
    key = name.strip().lower()
    try:
        return _BUILTIN_PRESET_BY_NAME[key]
    except KeyError as exc:
        valid = ", ".join(sorted(_BUILTIN_PRESET_BY_NAME))
        raise ValueError(
            f"unknown preset: {name}. Valid presets: {valid}"
        ) from exc


def load_user_transfer_function_presets(
        path: str | Path,
) -> tuple[TransferFunctionPreset, ...]:
    """
    Load user transfer function presets from JSON

    This  function is intentionally strict. Broken or invalid user preset files
    should be handled by build_transfer_function_registry(), which can fall back
    to builtin preset.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, Mapping):
        raise ValueError("Transfer function preset JSON root must be an object.")

    schema_version = payload.get("schema_version")
    if schema_version != USER_PRESET_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported transfer function preset schema_version: {schema_version}"
        )

    raw_presets = payload.get("presets")
    if not isinstance(raw_presets, list):
        raise ValueError("Transfer function preset JSON must contain a presets list.")

    presets = tuple(_preset_from_user_json(item) for item in raw_presets)
    _validate_user_presets(presets)

    return presets


def build_transfer_function_registry(
        user_preset_path: str | Path | None = None,
) -> TransferFunctionRegistry:
    """
    Build a runtime transfer function preset registry.

    Invalid user preset files are ignored so builtin presets remain available.
    """
    user_presets: tuple[TransferFunctionPreset, ...] = ()

    if user_preset_path is not None:
        try:
            user_presets = load_user_transfer_function_presets(user_preset_path)
        except Exception:
            logger.exception(
                "Failed to load user transfer function presets: %s",
                user_preset_path,
            )
            user_presets = ()

    presets = (*_BUILTIN_PRESETS, *user_presets)
    _validate_unique_names(presets)

    return TransferFunctionRegistry(presets=presets)


def build_transfer_function_points(
        *,
        preset: TransferFunctionPreset,
        window_settings: WindowSettings,
        clipped_scalar: float,
) -> TransferFunctionPoints:
    """
    Build concrete TF points from a preset and active window settings.

    default_linear is intentionally special-cased to preserve the previous
    VolumeViewer behavior exactly: window min maps to black/transparent and
    window max maps to white/opaque.
    """
    if preset.name == "default_linear":
        min_val, max_val = window_settings.get_range()
        return TransferFunctionPoints(
            color_points=(
                (clipped_scalar, 0.0, 0.0, 0.0),
                (min_val, 0.0, 0.0, 0.0),
                (max_val, 1.0, 1.0, 1.0),
            ),
            opacity_points=(
                (clipped_scalar, 0.0),
                (min_val, 0.0),
                (max_val, 1.0),
            ),
        )

    return TransferFunctionPoints(
        color_points=(
            (clipped_scalar, 0.0, 0.0, 0.0),
            *preset.color_points,
        ),
        opacity_points=(
            (clipped_scalar, 0.0),
            *preset.opacity_points,
        ),
        gradient_opacity_points=preset.gradient_opacity_points,
    )


def _validate_unique_names(presets: Iterable[TransferFunctionPreset]) -> None:
    """Validate regstry-level uniqueness."""
    seen: set[str] = set()
    for preset in presets:
        key = preset.name.strip().lower()
        if key in seen:
            raise ValueError(f"Duplicate transfer function preset name: {preset.name}")
        seen.add(key)


def _validate_builtin_presets(presets: tuple[TransferFunctionPreset, ...]) -> None:
    """Validate all built-in presets at import time."""
    _validate_unique_names(presets)
    for preset in presets:
        validate_transfer_function_preset(preset)
        if preset.source != SOURCE_BUILTIN:
            raise ValueError(
                f"Built-in transfer function preset has invalid source: {preset.name}"
            )


_BUILTIN_PRESETS: Final[tuple[TransferFunctionPreset, ...]] = (
    TransferFunctionPreset(
        name="default_linear",
        display_name="Default Linear",
        default_window=None,
        # Interpreted as normalized endpoints against the active window.
        color_points=(
            (0.0, 0.0, 0.0, 0.0),
            (1.0, 1.0, 1.0, 1.0),
        ),
        opacity_points=(
            (0.0, 0.0),
            (1.0, 1.0),
        ),
        source=SOURCE_BUILTIN,
    ),
    TransferFunctionPreset(
        name="ct_abdomen_soft_tissue",
        display_name="CT Abdomen Soft Tissue",
        default_window=WindowSettings(level=40.0, width=350.0),
        color_points=(
            (-1000.0, 0.0, 0.0, 0.0),
            (-150.0, 0.20, 0.16, 0.12),
            (40.0, 0.78, 0.58, 0.42),
            (300.0, 1.0, 0.86, 0.68),
            (1000.0, 1.0, 1.0, 0.95),
        ),
        opacity_points=(
            (-1000.0, 0.0),
            (-150.0, 0.0),
            (40.0, 0.08),
            (300.0, 0.30),
            (1000.0, 0.75),
        ),
        scalar_opacity_unit_distance=1.2,
        source=SOURCE_BUILTIN,
    ),
    TransferFunctionPreset(
        name="ct_liver",
        display_name="CT Liver",
        default_window=WindowSettings(level=70.0, width=150.0),
        color_points=(
            (-1000.0, 0.0, 0.0, 0.0),
            (0.0, 0.25, 0.14, 0.10),
            (70.0, 0.82, 0.45, 0.30),
            (160, 1.0, 0.78, 0.52),
            (500.0, 1.0, 0.95, 0.82),
        ),
        opacity_points=(
            (-1000.0, 0.0),
            (0.0, 0.0),
            (70.0, 0.12),
            (160.0, 0.32),
            (500.0, 0.65),
        ),
        scalar_opacity_unit_distance=1.4,
        source=SOURCE_BUILTIN,
    ),
    TransferFunctionPreset(
        name="ct_head_brain",
        display_name="CT Head Brain",
        default_window=WindowSettings(level=40.0, width=80.0),
        color_points=(
            (-1000.0, 0.0, 0.0, 0.0),
            (0.0, 0.12, 0.12, 0.12),
            (40.0, 0.62, 0.58, 0.52),
            (80.0, 0.90, 0.86, 0.78),
            (300.0, 1.0, 1.0, 0.95),
        ),
        opacity_points=(
            (-1000.0, 0.0),
            (0.0, 0.0),
            (40.0, 0.10),
            (80.0, 0.22),
            (300.0, 0.55),
        ),
        scalar_opacity_unit_distance=1.5,
        source=SOURCE_BUILTIN,
    ),
    TransferFunctionPreset(
        name="ct_head_bone",
        display_name="CT Head Bone",
        default_window=WindowSettings(level=350.0, width=1800.0),
        color_points=(
            (-1000.0, 0.0, 0.0, 0.0),
            (150.0, 0.15, 0.12, 0.10),
            (350.0, 0.72, 0.62, 0.50),
            (1200.0, 1.0, 0.96, 0.86),
            (2500.0, 1.0, 1.0, 1.0),
        ),
        opacity_points=(
            (-1000.0, 0.0),
            (150.0, 0.0),
            (350.0, 0.18),
            (1200.0, 0.68),
            (2500.0, 0.95),
        ),
        scalar_opacity_unit_distance=1.0,
        source=SOURCE_BUILTIN,
    ),
    TransferFunctionPreset(
        name="ct_bone",
        display_name="CT Bone",
        default_window=WindowSettings(level=300.0, width=2000.0),
        color_points=(
            (-1000.0, 0.0, 0.0, 0.0),
            (150.0, 0.12, 0.10, 0.08),
            (300.0, 0.70, 0.60, 0.48),
            (1000.0, 1.0, 0.95, 0.82),
            (3000.0, 1.0, 1.0, 1.0),
        ),
        opacity_points=(
            (-1000.0, 0.0),
            (150.0, 0.0),
            (300.0, 0.15),
            (1000.0, 0.65),
            (3000.0, 0.95),
        ),
        scalar_opacity_unit_distance=1.0,
        source=SOURCE_BUILTIN,
    ),
    TransferFunctionPreset(
        name="ct_lung",
        display_name="CT Lung",
        default_window=WindowSettings(level=-600.0, width=1500.0),
        color_points=(
            (-1000.0, 0.02, 0.02, 0.03),
            (-800.0, 0.10, 0.10, 0.10),
            (-600.0, 0.35, 0.42, 0.50),
            (-200.0, 0.75, 0.70, 0.62),
            (400.0, 1.0, 0.92, 0.80),
        ),
        opacity_points=(
            (-1000.0, 0.0),
            (-800.0, 0.05),
            (-600.0, 0.08),
            (-200.0, 0.20),
            (400.0, 0.55),
        ),
        scalar_opacity_unit_distance=1.6,
        source=SOURCE_BUILTIN,
    ),
    TransferFunctionPreset(
        name="ct_vessel",
        display_name="CT Vessel",
        default_window=WindowSettings(level=200.0, width=700.0),
        color_points=(
            (-1000.0, 0.0, 0.0, 0.0),
            (80.0, 0.18, 0.12, 0.10),
            (180.0, 0.95, 0.35, 0.20),
            (350.0, 1.0, 0.85, 0.35),
            (1000.0, 1.0, 1.0, 0.85),
        ),
        opacity_points=(
            (-1000.0, 0.0),
            (80.0, 0.0),
            (180.0, 0.18),
            (350.0, 0.55),
            (1000.0, 0.85),
        ),
    ),
)


_validate_builtin_presets(_BUILTIN_PRESETS)

_BUILTIN_PRESET_BY_NAME: Final[dict[str, TransferFunctionPreset]] = {
    preset.name.strip().lower(): preset for preset in _BUILTIN_PRESETS
}
