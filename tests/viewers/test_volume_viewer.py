"""Tests for VolumeViewer transfer function compatibility."""

from __future__ import annotations

import pytest

from qv.core.window_settings import WindowSettings
from qv.viewers.volume_viewer import VolumeViewer
import qv.viewers.volume_viewer as volume_viewer_module
from qv.operations.clipping.clipping_operation import CLIPPED_SCALAR
from qv.viewers.transfer_functions import (
    TransferFunctionPreset,
    build_transfer_function_points,
    get_transfer_function_preset,
)


class _SpyTransferFunction:
    """
    Test double for vtkTransferFunction/vtkColorTransferFunction.

    The real VTK objects do not expose a .points attribute. This spy stores
    AddPoint/AddRGBPoint calls so tests can assert the generated TF data without
    depending on VTK internals.
    """

    def __init__(self) -> None:
        self.points: list[tuple[float, ...]] = []
        self.remove_all_points_calls = 0

    def RemoveAllPoints(self) -> None:
        self.remove_all_points_calls += 1
        self.points.clear()

    def AddRGBPoint(self, scalar: float, red: float, green: float, blue: float) -> None:
        self.points.append((scalar, red, green, blue))

    def AddPoint(self, scalar: float, opacity: float) -> None:
        self.points.append((scalar, opacity))


class _SpyVolumeProperty:
    """Collect volume property calls used by transfer function application."""

    def __init__(self) -> None:
        self.scalar_opacity_unit_distance: float | None = None
        self.gradient_opacity = None
        self.disable_gradient_opacity_on_calls = 0
        self.disable_gradient_opacity_off_calls = 0
        self.modified_calls = 0

    def SetScalarOpacityUnitDistance(self, distance: float) -> None:
        self.scalar_opacity_unit_distance = distance

    def SetGradientOpacity(self, func) -> None:
        self.gradient_opacity = func

    def DisableGradientOpacityOn(self) -> None:
        self.disable_gradient_opacity_on_calls += 1

    def DisableGradientOpacityOff(self) -> None:
        self.disable_gradient_opacity_off_calls += 1

    def Modified(self) -> None:
        self.modified_calls += 1


def _make_volume_viewer_transfer_function_stub(
        *,
        preset_name: str = "ct_abdomen_soft_tissue",
        scalar_range: tuple[float, float] = (-1000.0, 3000.0),
):
    """Build a lightweight viewer for testing _apply_window_settings directly."""
    viewer = VolumeViewer.__new__(VolumeViewer)
    viewer._transfer_function_preset_name = preset_name
    viewer.scalar_range = scalar_range
    viewer.color_func = _SpyTransferFunction()
    viewer.opacity_func = _SpyTransferFunction()
    viewer.gradient_opacity_func = None
    viewer.volume_property = _SpyVolumeProperty()
    viewer._default_scalar_opacity_unit_distance = 1.0
    return viewer


def test_apply_window_settings_applies_scalar_opacity_unit_distance():
    """Preset ScalarOpacityUnitDistance should be forwarded to vtkVolumeProperty."""
    viewer = _make_volume_viewer_transfer_function_stub(
        preset_name="ct_abdomen_soft_tissue",
    )

    changed = viewer._apply_window_settings(WindowSettings(level=40.0, width=350.0))

    assert changed is True
    assert viewer.volume_property.scalar_opacity_unit_distance == 1.2
    assert viewer.volume_property.modified_calls == 1


def test_apply_window_settings_disables_gradient_opacity_when_preset_has_no_points():
    """A preset without gradient opacity should not leave stale gradient opacity active."""
    viewer = _make_volume_viewer_transfer_function_stub(
        preset_name="ct_abdomen_soft_tissue",
    )

    changed = viewer._apply_window_settings(WindowSettings(level=40.0, width=350.0))

    assert changed is True
    assert viewer.gradient_opacity_func is None
    assert viewer.volume_property.disable_gradient_opacity_on_calls == 1
    assert viewer.volume_property.disable_gradient_opacity_off_calls == 0


def test_apply_window_settings_applies_gradient_opacity_points(monkeypatch):
    """Gradient opacity points should be converted to a VTK piecewise function."""
    preset = TransferFunctionPreset(
        name="test_gradient",
        display_name="Test Gradient",
        default_window=WindowSettings(level=40.0, width=350.0),
        color_points=(
            (-1000.0, 0.0, 0.0, 0.0),
            (300.0, 1.0, 1.0, 1.0),
        ),
        opacity_points=(
            (-1000.0, 0.0),
            (300.0, 0.6),
        ),
        gradient_opacity_points=(
            (0.0, 0.0),
            (120.0, 0.35),
            (600.0, 1.0),
        ),
        scalar_opacity_unit_distance=1.4,
    )

    monkeypatch.setattr(volume_viewer_module,
                        "get_transfer_function_preset",
                        lambda _: preset)
    monkeypatch.setattr(volume_viewer_module.vtk,
                        "vtkPiecewiseFunction",
                        lambda: _SpyTransferFunction(), )

    viewer = _make_volume_viewer_transfer_function_stub(
        preset_name="test_gradient",
    )

    changed = viewer._apply_window_settings(WindowSettings(level=40.0, width=350.0))

    assert changed is True
    assert viewer.volume_property.scalar_opacity_unit_distance == 1.4
    assert viewer.gradient_opacity_func is viewer.volume_property.gradient_opacity
    assert viewer.volume_property.disable_gradient_opacity_off_calls == 1
    assert viewer.volume_property.disable_gradient_opacity_on_calls == 0

    gradient_points = viewer.gradient_opacity_func.points
    assert gradient_points == [
        (0.0, 0.0),
        (120.0, 0.35),
        (600.0, 1.0),
    ]


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


def _make_volume_viewer_api_stub(
        *,
        scalar_range: tuple[float, float] | None = (-1000.0, 3000.0),
        window_settings: WindowSettings | None = WindowSettings(level=100.0, width=400.0),
):
    """
    Build a lightweight VolumeViewer instance for API tests.

    The real constructor initializes Qt/VTK state. These tests only need the
    preset switching contract, so they attach the minimal state and method spies.
    """
    viewer = VolumeViewer.__new__(VolumeViewer)
    viewer._transfer_function_preset_name = "default_linear"
    viewer.scalar_range = scalar_range
    viewer._window_settings = window_settings

    calls: dict[str, list] = {
        "set_window_settings": [],
        "apply_window_settings": [],
        "update_view": [],
    }

    def fake_set_window_settings(
            settings: WindowSettings,
            *,
            emit_signal: bool = True,
            render: bool = True,
    ) -> None:
        calls["set_window_settings"].append(
            {
                "settings": settings,
                "emit_signal": emit_signal,
                "render": render,
            }
        )
        viewer._window_settings = settings

    def fake_apply_window_settings(settings: WindowSettings):
        calls["apply_window_settings"].append(settings)
        return True

    def fake_update_view():
        calls["update_view"].append(True)

    viewer.set_window_settings = fake_set_window_settings
    viewer._apply_window_settings = fake_apply_window_settings
    viewer.update_view = fake_update_view

    return viewer, calls


def test_available_transfer_function_presets_exposes_builtin_names():
    """VolumeViewer should expose preset names for future UI use."""
    viewer, _calls = _make_volume_viewer_api_stub()

    names = viewer.available_transfer_function_presets()
    assert "default_linear" in names
    assert "ct_abdomen_soft_tissue" in names
    assert "ct_head_brain" in names


def test_current_transfer_function_preset_name_defaults_to_default_linear():
    """The viewer should start from the compatibility preset."""
    viewer, _calls = _make_volume_viewer_api_stub()

    assert viewer.current_transfer_function_preset_name == "default_linear"


def test_set_transfer_function_preset_updates_name_before_volume_load():
    """Preset selection should be allowed before volume data is loaded."""
    viewer, calls = _make_volume_viewer_api_stub(scalar_range=None)

    viewer.set_transfer_function_preset("ct_head_brain")

    assert viewer.current_transfer_function_preset_name == "ct_head_brain"
    assert calls["set_window_settings"] == []
    assert calls["apply_window_settings"] == []
    assert calls["update_view"] == []


def test_set_transfer_function_preset_applies_default_window_and_rerenders():
    """Preset changes on loaded data should apply the preset default window."""
    viewer, calls = _make_volume_viewer_api_stub()

    viewer.set_transfer_function_preset("ct_abdomen_soft_tissue")

    assert viewer.current_transfer_function_preset_name == "ct_abdomen_soft_tissue"
    assert calls["set_window_settings"] == [
        {
            "settings": WindowSettings(level=40.0, width=350.0),
            "emit_signal": True,
            "render": False,
        }
    ]
    assert calls["apply_window_settings"] == [WindowSettings(level=40.0, width=350.0)]
    assert calls["update_view"] == [True]


def test_transfer_function_preset_can_return_to_default_linear():
    """Preset switching should allow returning to the compatibility preset."""
    viewer, calls = _make_volume_viewer_api_stub(
        window_settings=WindowSettings(level=40.0, width=80.0),
    )
    viewer._transfer_function_preset_name = "ct_head_brain"

    viewer.set_transfer_function_preset("default_linear")

    assert viewer.current_transfer_function_preset_name == "default_linear"

    # default_linear has no preset default_window, so it should preserve the
    # active WindowSettings and only rebuild transfer functions from it.
    assert calls["set_window_settings"] == []
    assert calls["apply_window_settings"] == [
        WindowSettings(level=40.0, width=80.0),
    ]
    assert calls["update_view"] == [True]


def test_set_transfer_function_preset_can_skip_render():
    """Callers should be able to batch preset changes without immediate render."""
    viewer, calls = _make_volume_viewer_api_stub()

    viewer.set_transfer_function_preset("ct_head_brain", render=False)

    assert viewer.current_transfer_function_preset_name == "ct_head_brain"
    assert calls["set_window_settings"][0]["settings"] == WindowSettings(
        level=40.0,
        width=80.0,
    )
    assert calls["apply_window_settings"] == [
        WindowSettings(level=40.0, width=80.0),
    ]
    assert calls["update_view"] == []


def test_set_transfer_function_preset_rejects_unknown_name_without_state_change():
    """Invalid preset names should not modify the active preset."""
    viewer, calls = _make_volume_viewer_api_stub()

    with pytest.raises(ValueError, match="unknown preset"):
        viewer.set_transfer_function_preset("unknown_preset")

    assert viewer.current_transfer_function_preset_name == "default_linear"
    assert calls["set_window_settings"] == []
    assert calls["apply_window_settings"] == []
    assert calls["update_view"] == []


def test_apply_window_settings_restores_default_scalar_opacity_unit_distance():
    """Presets without ScalarOpacityUnitDistance should restore the VTK default."""
    viewer = _make_volume_viewer_transfer_function_stub(
        preset_name="default_linear",
    )

    viewer.volume_property.scalar_opacity_unit_distance = 1.6

    changed = viewer._apply_window_settings(WindowSettings(level=40.0, width=80.0))

    assert changed is True
    assert viewer.volume_property.scalar_opacity_unit_distance == 1.0
