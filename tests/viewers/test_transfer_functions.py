"""Tests for transfer function preset validation.

These tests define the public contract for qv.viewers.transfer_functions before
the implementation exists. They are expected to fail until the registry module is
added in the next commit.
"""

from __future__ import annotations

import json
from pathlib import Path

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


def _write_user_preset_json(path: Path, payload: dict) -> None:
    """Write a user preset JSON file in the expected external format."""
    path.write_text(json.dumps(payload), encoding="utf-8")


def _valid_user_preset_payload(*, name: str = "user_abdomen_custom") -> dict:
    """Build a minimal valid user preset JSON payload."""
    return {
        "name": name,
        "display_name": "User Abdomen Custom",
        "default_window": {
            "level": 40.0,
            "width": 350.0,
        },
        "color_points": [
            [-1000.0, 0.0, 0.0, 0.0],
            [300.0, 1.0, 0.8, 0.6],
        ],
        "opacity_points": [
            [-1000.0, 0.0],
            [300.0, 0.6],
        ],
        "gradient_opacity_points": [],
        "scalar_opacity_unit_distance": 1.2,
    }


def _make_user_preset(
        *,
        name: str = "user_saved",
        display_name: str = "User Saved",
        source: str = "user",
        opacity_points: tuple[tuple[float, float], ...] = (
            (-1000.0, 0.0),
            (300.0, 0.6),
        )
) -> TransferFunctionPreset:
    """Build a valid user preset for save/load tests."""
    return TransferFunctionPreset(
        name=name,
        display_name=display_name,
        default_window=WindowSettings(level=40.0, width=350.0),
        color_points=(
            (-1000.0, 0.0, 0.0, 0.0),
            (300.0, 1.0, 0.8, 0.6),
        ),
        opacity_points=opacity_points,
        gradient_opacity_points=(
            (0.0, 0.0),
            (120.0, 0.4),
        ),
        scalar_opacity_unit_distance=1.2,
        source=source,
    )

def test_load_user_transfer_function_presets_loads_valid_json(tmp_path: Path):
    """Valid user preset JSON should load as user-sourced presets."""
    from qv.viewers.transfer_functions import load_user_transfer_function_presets

    path = tmp_path / "transfer_function_presets.json"
    _write_user_preset_json(
        path,
        {
            "schema_version": 1,
            "presets": [
                _valid_user_preset_payload(),
            ],
        },
    )

    presets = load_user_transfer_function_presets(path)

    assert len(presets) == 1
    assert presets[0].name == "user_abdomen_custom"
    assert presets[0].display_name == "User Abdomen Custom"
    assert presets[0].default_window == WindowSettings(level=40.0, width=350.0)
    assert presets[0].source == "user"


def test_load_user_transfer_function_presets_rejects_unsupported_schema_version(
        tmp_path: Path,
):
    """Unsupported user preset schema versions should fail explicitly."""
    from qv.viewers.transfer_functions import load_user_transfer_function_presets

    path = tmp_path / "transfer_function_presets.json"
    _write_user_preset_json(
        path,
        {
            "schema_version": 999,
            "presets": [
                _valid_user_preset_payload(),
            ],
        },
    )

    with pytest.raises(ValueError, match="schema_version|schema version"):
        load_user_transfer_function_presets(path)


def test_load_user_transfer_function_presets_rejects_builtin_name_collision(
        tmp_path: Path,
):
    """User presets must not override builtin preset names."""
    from qv.viewers.transfer_functions import load_user_transfer_function_presets

    path = tmp_path / "transfer_function_presets.json"
    _write_user_preset_json(
        path,
        {
            "schema_version": 1,
            "presets": [
                _valid_user_preset_payload(name="default_linear"),
            ],
        },
    )

    with pytest.raises(ValueError, match="default_linear|builtin|collision"):
        load_user_transfer_function_presets(path)


def test_load_user_transfer_function_presets_rejects_duplicate_user_names(
        tmp_path: Path,
):
    """Duplicate user preset names should be rejected instead of using last-wins."""
    from qv.viewers.transfer_functions import load_user_transfer_function_presets

    path = tmp_path / "transfer_function_presets.json"
    _write_user_preset_json(
        path,
        {
            "schema_version": 1,
            "presets": [
                _valid_user_preset_payload(name="user_duplicate"),
                _valid_user_preset_payload(name="user_duplicate"),
            ],
        },
    )

    with pytest.raises(ValueError, match="Duplicate|duplicate|user_duplicate"):
        load_user_transfer_function_presets(path)


def test_build_transfer_function_registry_falls_back_to_builtin_on_broken_json(
        tmp_path: Path,
):
    """Broken user JSON should not make builtin presets unavailable."""
    from qv.viewers.transfer_functions import build_transfer_function_registry

    path = tmp_path / "transfer_function_presets.json"
    path.write_text("{ broken json", encoding="utf-8")

    registry = build_transfer_function_registry(user_preset_path=path)

    preset = registry.get("default_linear")
    assert preset is not None
    assert preset.name == "default_linear"
    assert preset.source == "builtin"


def test_save_user_transfer_function_presets_round_trips_presets(
        tmp_path: Path,
):
    """Saved user presets should load back as equivalent user presets."""
    from qv.viewers.transfer_functions import (
        load_user_transfer_function_presets,
        save_user_transfer_function_presets,
    )

    path = tmp_path / "transfer_function_presets.json"
    preset = _make_user_preset()

    save_user_transfer_function_presets(path, (preset,))
    loaded_presets = load_user_transfer_function_presets(path)
    assert loaded_presets == (preset,)


def test_save_user_transfer_function_presets_writes_schema_version_and_stable_order(
        tmp_path: Path,
):
    """Saved JSON should include schema_version and preserve preset order."""
    from qv.viewers.transfer_functions import save_user_transfer_function_presets

    path = tmp_path / "transfer_function_presets.json"
    first = _make_user_preset(name="user_first", display_name="User First")
    second = _make_user_preset(name="user_second", display_name="User Second")

    save_user_transfer_function_presets(path, (first, second))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert [item["name"] for item in payload["presets"]] == [
        "user_first",
        "user_second",
    ]


def test_save_user_transfer_function_presets_validates_before_writing(
        tmp_path: Path,
):
    """Invalid user presets should fail before producing a JSON file."""
    from qv.viewers.transfer_functions import save_user_transfer_function_presets

    path = tmp_path / "transfer_function_presets.json"
    invalid = _make_user_preset(name="")

    with pytest.raises(ValueError, match="name"):
        save_user_transfer_function_presets(path, (invalid,))

    assert not path.exists()


def test_save_user_transfer_function_presets_excludes_builtin_presets(
        tmp_path: Path,
):
    """Builtin presets should not be written to the user preset JSON file."""
    from qv.viewers.transfer_functions import save_user_transfer_function_presets

    path = tmp_path / "transfer_function_presets.json"
    builtin = get_transfer_function_preset("default_linear")
    user_preset = _make_user_preset()

    save_user_transfer_function_presets(path, (builtin, user_preset))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [item["name"] for item in payload["presets"]] == ["user_saved"]
