"""Tests for transfer function preset validation.

These tests define the public contract for qv.viewers.transfer_functions before
the implementation exists. They are expected to fail until the registry module is
added in the next commit.
"""

from __future__ import annotations

import pytest

from qv.core.window_settings import WindowSettings
from qv.viewers.transfer_functions import (
TransferFunctionPreset,
get_transfer_function_preset,
list_transfer_function_presets,
validate_transfer_function_preset,
)


def _make_preset(*,
                 name: str = "test_preset",
                 color_points: tuple[tuple[float, float, float, float], ...] = (
                     (-1000.0, 0.0, 0.0, 0.0),
                     (300.0, 1.0, 0.8, 0.6),
                 ),
                 opacity_points: tuple[tuple[float, float], ...] = (
                     (-1000.0, 0.0),
                     (300.0, 0.6),
                 ),
                 scalar_opacity_unit_distance: float | None = 1.2,
) -> TransferFunctionPreset:
    """
    Build a minimal valid preset for validation tests.

    The point values intentionally use CT-like HU coordinates, but these tests
    only verify preset structure and value ranges, not clinical suitability.
    """
    return TransferFunctionPreset(
        name=name,
        display_name="Test Preset",
        default_window=WindowSettings(level=40.0, width=350.0),
        color_points=color_points,
        opacity_points=opacity_points,
        gradient_opacity_points=(),
        scalar_opacity_unit_distance=scalar_opacity_unit_distance,
        source="builtin",
    )


def test_validate_transfer_function_preset_accepts_valid_preset():
    """A structurally  valid preset should pass without raising."""
    preset = _make_preset()

    validate_transfer_function_preset(preset)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
    ],
)
def test_validate_transfer_function_preset_rejects_empty_name(name: str):
    """Preset names are stable identifiers, so empty names must be rejected."""
    preset = _make_preset(name=name)

    with pytest.raises(ValueError, match="name"):
        validate_transfer_function_preset(preset)


@pytest.mark.parametrize(
    "color_points",
    [
        ((0.0, -0.1, 0.0, 0.0),),
        ((0.0, 0.0, 1.1, 0.0),),
        ((0.0, 0.0, 0.0, 2.0),),
    ],
)
def test_validate_transfer_function_preset_rejects_color_values_outside_unit_range(
        color_points
):
    """VTK color channels should be normalized RGB values in the 0..1 range."""
    preset = _make_preset(color_points=color_points)

    with pytest.raises(ValueError, match="color"):
        validate_transfer_function_preset(preset)


@pytest.mark.parametrize(
    "opacity_points",
    [
        ((0.0, -0.1),),
        ((0.0, 1.1),),
    ],
)
def test_validate_transfer_function_preset_rejects_opacity_outside_unit_range(
        opacity_points,
):
    """Opacity values outside 0..1 make the preset invalid."""
    preset = _make_preset(opacity_points=opacity_points)

    with pytest.raises(ValueError, match="opacity"):
        validate_transfer_function_preset(preset)


@pytest.mark.parametrize(
    "scalar_opacity_unit_distance",
    [
        0.0,
        -1.0,
    ],
)
def test_validate_transfer_function_preset_rejects_non_positive_scalar_opacity_unit_distance(
        scalar_opacity_unit_distance,
):
    """ScalarOpacityUnitDistance is only meaningful as a positive distance."""
    preset = _make_preset(
        scalar_opacity_unit_distance=scalar_opacity_unit_distance,
    )

    with pytest.raises(ValueError, match="ScalarOpacityUnitDistance|unit distance"):
        validate_transfer_function_preset(preset)


def test_list_transfer_function_presets_has_unique_names():
    """The runtime registry must not expose duplicate preset identifiers."""
    presets = list_transfer_function_presets()
    names = [preset.name for preset in presets]

    assert len(names) == len(set(names))


def test_list_transfer_function_presets_includes_default_linear():
    """The compatibility preset must always be available."""
    names = {preset.name for preset in list_transfer_function_presets()}

    assert "default_linear" in names


def test_get_transfer_function_preset_returns_default_linear():
    """The default preset should be retrievable by stable name."""
    preset = get_transfer_function_preset("default_linear")

    assert preset.name == "default_linear"
    assert preset.source == "builtin"


def test_get_transfer_function_preset_rejects_unknown_name():
    """Unknown preset names should fail explicitly instead of silently falling back."""
    with pytest.raises(ValueError, match="unknown_preset"):
        get_transfer_function_preset("unknown_preset")
