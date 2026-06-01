from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from qv.app.app_settings_manager import (
    AppSettingsManager,
    SliceNavigationDirectionMode,
)


ORG = "QVTests.org"


@pytest.fixture(autouse=True)
def isolate_qsettings(tmp_path: Path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    yield


def _clear_settings(app_name: str) -> None:
    settings = QSettings(ORG, app_name)
    settings.clear()
    settings.sync()


def _manager(settings_dir: Path, app_name: str) -> AppSettingsManager:
    settings_dir.mkdir(parents=True, exist_ok=True)
    return AppSettingsManager(
        org_domain=ORG,
        app_name=app_name,
        settings_dir=settings_dir,
    )


def test_mpr_direction_defaults_to_patient_orientation(tmp_path: Path) -> None:
    app_name = "Defaults"
    _clear_settings(app_name)

    manager = _manager(tmp_path / "settings", app_name)

    assert manager.mpr_slice_drag_direction_mode is (
        SliceNavigationDirectionMode.PATIENT_ORIENTATION
    )
    assert manager.mpr_wheel_slice_direction_mode is (
        SliceNavigationDirectionMode.PATIENT_ORIENTATION
    )


def test_mpr_direction_can_be_loaded_from_viewer_json(tmp_path: Path) -> None:
    app_name = "ViewerJSON"
    _clear_settings(app_name)
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()

    (settings_dir / "viewer.json").write_text(
        json.dumps({
            "mpr": {
                "slice_drag_direction_mode": "slice_index",
                "wheel_slice_direction_mode": "slice_index",
            }
        }),
        encoding="utf-8",
    )
    manager = _manager(settings_dir, app_name)

    assert manager.mpr_slice_drag_direction_mode is SliceNavigationDirectionMode.SLICE_INDEX
    assert manager.mpr_wheel_slice_direction_mode is SliceNavigationDirectionMode.SLICE_INDEX


def test_qsettings_overrides_mpr_json_defaults(tmp_path: Path) -> None:
    app_name = "QSettingsOverrides"
    _clear_settings(app_name)
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()

    (settings_dir / "viewer.json").write_text(
        json.dumps({
            "mpr": {
                "slice_drag_direction_mode": "patient_orientation",
                "wheel_slice_direction_mode": "patient_orientation",
            }
        }),
        encoding="utf-8",
    )

    settings = QSettings(ORG, app_name)
    settings.setValue("mpr/slice_drag_direction_mode", "slice_index")
    settings.setValue("mpr/wheel_slice_direction_mode", "slice_index")
    settings.sync()

    manager = _manager(settings_dir, app_name)

    assert manager.mpr_slice_drag_direction_mode is SliceNavigationDirectionMode.SLICE_INDEX
    assert manager.mpr_wheel_slice_direction_mode is SliceNavigationDirectionMode.SLICE_INDEX


def test_invalid_mpr_direction_falls_back_to_default(tmp_path: Path) -> None:
    app_name = "InvalidMpr"
    _clear_settings(app_name)

    settings = QSettings(ORG, app_name)
    settings.setValue("mpr/slice_drag_direction_mode", "invalid")
    settings.setValue("mpr/wheel_slice_direction_mode", "invalid")
    settings.sync()

    manager = _manager(tmp_path / "settings", app_name)

    assert manager.mpr_slice_drag_direction_mode is (
        SliceNavigationDirectionMode.PATIENT_ORIENTATION
    )
    assert manager.mpr_wheel_slice_direction_mode is (
        SliceNavigationDirectionMode.PATIENT_ORIENTATION
    )


def test_mpr_direction_setters_persist_to_qsettings(tmp_path: Path) -> None:
    app_name = "Setters"
    _clear_settings(app_name)
    manager = _manager(tmp_path / "settings", app_name)

    manager.set_mpr_slice_drag_direction_mode(SliceNavigationDirectionMode.SLICE_INDEX)
    manager.set_mpr_wheel_slice_direction_mode("slice_index")

    assert manager.mpr_slice_drag_direction_mode is SliceNavigationDirectionMode.SLICE_INDEX
    assert manager.mpr_wheel_slice_direction_mode is SliceNavigationDirectionMode.SLICE_INDEX

    settings = QSettings(ORG, app_name)
    assert settings.value("mpr/slice_drag_direction_mode") == "slice_index"
    assert settings.value("mpr/wheel_slice_direction_mode") == "slice_index"


def test_reset_mpr_section_preserves_other_settings(tmp_path: Path) -> None:
    app_name = "ResetMpr"
    _clear_settings(app_name)
    manager = _manager(tmp_path / "settings", app_name)

    manager.set_rotation_step_deg(7.0)
    manager.set_mpr_slice_drag_direction_mode("slice_index")
    manager.set_mpr_wheel_slice_direction_mode("slice_index")

    manager.reset_section("mpr")

    assert manager.rotation_step_deg == 7.0
    assert manager.mpr_slice_drag_direction_mode is (
        SliceNavigationDirectionMode.PATIENT_ORIENTATION
    )
    assert manager.mpr_wheel_slice_direction_mode is (
        SliceNavigationDirectionMode.PATIENT_ORIENTATION
    )


def test_to_dict_serializes_mpr_enum_values(tmp_path: Path) -> None:
    app_name = "ToDict"
    _clear_settings(app_name)
    manager = _manager(tmp_path / "settings", app_name)

    data = manager.to_dict()

    assert data["mpr"] == {
        "slice_drag_direction_mode": "patient_orientation",
        "wheel_slice_direction_mode": "patient_orientation",
    }
