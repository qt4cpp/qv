"""Tests for VolumeViewer transfer function compatibility."""

from __future__ import annotations

from qv.core.window_settings import WindowSettings
from qv.operations.clipping.clipping_operation import CLIPPED_SCALAR
from qv.viewers.transfer_functions import (
    build_transfer_function_points,
    get_transfer_function_preset,
)


def test_default_linear_transfer_function_matches_existing_window_mapping():
    """
    default_linear must preserve the current VolumeViewer behavior.

    Existing behavior:
    - CLIPPED_SCALAR is black and fully transparent
    - window min is black and transparent
    - window max is white and opaque
    """
    preset = get_transfer_function_preset("default_linear")
    settings = WindowSettings(level=100.0, width=400.0)

    points = build_transfer_function_points(
        preset=preset,
        window_settings=settings,
        clipped_scalar=CLIPPED_SCALAR,
    )

    assert points.color_points == (
        (CLIPPED_SCALAR, 0.0, 0.0, 0.0),
        (-100.0, 0.0, 0.0, 0.0),
        (300.0, 1.0, 1.0, 1.0),
    )

    assert points.opacity_points == (
        (CLIPPED_SCALAR, 0.0),
        (-100.0, 0.0),
        (300.0, 1.0),
    )


def test_default_linear_transfer_function_uses_active_window_settings():
    """
    default_linear points should be derived from the active WindowSettings.

    This prevents accidentally hardcoding a fixed CT range when refactoring the
    current VolumeViewer transfer function path.
    """
    preset = get_transfer_function_preset("default_linear")
    settings = WindowSettings(level=40.0, width=80.0)

    points = build_transfer_function_points(
        preset=preset,
        window_settings=settings,
        clipped_scalar=CLIPPED_SCALAR,
    )

    assert points.color_points[1:] == (
        (0.0, 0.0, 0.0, 0.0),
        (80.0, 1.0, 1.0, 1.0),
    )
    assert points.opacity_points[1:] == (
        (0.0, 0.0),
        (80.0, 1.0),
    )


def test_default_linear_transfer_function_keeps_clipped_scalar_transparent():
    """Clipped voxels must remain hidden after moving TF logic into presets."""
    preset = get_transfer_function_preset("default_linear")
    settings = WindowSettings(level=40.0, width=80.0)

    points = build_transfer_function_points(
        preset=preset,
        window_settings=settings,
        clipped_scalar=CLIPPED_SCALAR,
    )

    assert points.color_points[0] == (CLIPPED_SCALAR, 0.0, 0.0, 0.0)
    assert points.opacity_points[0] == (CLIPPED_SCALAR, 0.0)
