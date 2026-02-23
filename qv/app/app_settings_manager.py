from __future__ import annotations
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional
from PySide6.QtCore import QSettings
import logging
import json
from pathlib import Path

from qv.utils.json_loader import deep_merge as _deep_merge
from qv.utils.json_loader import truthy_env as _truthy_env
from qv.utils.json_loader import read_json_dict as _read_json_dict


logger = logging.getLogger(__name__)


class RunMode(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    VERBOSE = "verbose"

    def __str__(self):
        return self.value
    def __repr__(self):
        return self.value


# ----------------------
# デフォルト設定
# ----------------------
base_defaults: Dict[str, Any] = {
    "general": {
        "run_mode": RunMode.DEVELOPMENT.value,
        "logging_level": "INFO",  # "DEBUG", "INFO", "WARNING", "ERROR"
    },
    "view": {
        "rotation_step_deg": 5.0,
    },
}

class SettingsError(RuntimeError):
    """Raised when strict settings loading fails (dev/CI)."""

# ---------------------
# Data model
# ---------------------
@dataclass
class GeneralConfig:
    run_mode: RunMode = RunMode.PRODUCTION
    logging_level: str = "INFO"

@dataclass
class ViewConfig:
    rotation_step_deg: float = 5.0

@dataclass
class AppSettingsData:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    view: ViewConfig = field(default_factory=ViewConfig)

# ----------------------
# Utility
# ----------------------
def _truthy(s: str) -> bool:
    return s.strip().lower() in ("1", "true", "yes", "on")


def _validate_run_mode(v: Any) -> RunMode:
    if isinstance(v, RunMode):
        return v
    mode = str(v).strip().lower()
    try:
        return RunMode(mode)
    except ValueError:
        return RunMode(base_defaults["general"]["run_mode"])

def _validate_logging_level(v: str) -> str:
    """Validate and normalize logging level

    Returns one of DEBUG/INFO/WARNING/ERROR.
    Falls back to base_defaults['general']['logging_level'] if invalid.
    """
    fallback = str(base_defaults["general"]["logging_level"]).upper()
    level = str(v).upper()
    return level if level in ("DEBUG", "INFO", "WARNING", "ERROR") else fallback

def _validate_rotation_step(v: Any) -> float:
    """Validate and normalize rotation step in degree.

    Always returns a safe float value. Falls back to
     base_defaults['view']['rotation_step_deg'] if invalid.
    """
    fallback = float(base_defaults["view"]["rotation_step_deg"])
    try:
        f = float(v)
    except Exception:
        return fallback
    return f if (0 < f <= 90) else fallback


# ---------------------
# AppSettingManager
# ---------------------
class AppSettingsManager:
    """
    アプリケーションの一般設定を管理するクラス。
    デフォルトのコード内のDEFAULTS を読み込む。
    読み込み時はに検証し、範囲外の値はフォールバック
    set_* は設定すると QSettings に即時保存される。
    """
    def __init__(self,
                 org_domain: str = "TedApp.org",
                 app_name: str = "QV",
                 settings_dir: Path | None = None,):
        """
        :param org_domain: setting for QSettings.
        :param app_name:  setting for QSettings.
        :param settings_dir:  Base dir for packaged defaults JSON)
        """
        self._settings = QSettings(org_domain, app_name)
        if settings_dir is None:
            settings_dir = Path(__file__).resolve().parents[2] / "settings"
        self._settings_dir = settings_dir
        self._warnings: list[str] = []  # Non-fatal settings load problems
        self._data = self._load_effective()

    # 読み取り
    @property
    def data(self) -> AppSettingsData:
        return self._data

    @property
    def run_mode(self) -> RunMode:
        return self._data.general.run_mode

    @property
    def dev_mode(self) -> bool:
        """Backward compatible boolean view of the run mode."""
        return self.run_mode is RunMode.DEVELOPMENT

    @property
    def logging_level(self) -> str:
        return self._data.general.logging_level

    @property
    def rotation_step_deg(self) -> float:
        return self._data.view.rotation_step_deg

    @property
    def warnings(self) -> tuple[str, ...]:
        """Non-fatal settings load problems (production fallback path)."""
        return tuple(self._warnings)

    @property
    def had_fallback(self) -> bool:
        return bool(self._warnings)

    # 書き込み
    def set_run_mode(self, v: str | RunMode) -> None:
        mode = _validate_run_mode(v)
        self._settings.setValue("general/run_mode", mode.value)
        self._data.general.run_mode = mode

    def set_dev_mode(self, v: bool) -> None:
        """Compatibility shim for legacy callers."""
        self.set_run_mode(RunMode.DEVELOPMENT if v else RunMode.PRODUCTION)

    def set_logging_level(self, v: str) -> None:
        level = _validate_logging_level(v)
        self._settings.setValue("general/logging_level", level)
        self._data.general.logging_level = level

    def set_rotation_step_deg(self, v: float):
        rot = _validate_rotation_step(v)
        self._settings.setValue("view/rotation_step_deg", rot)
        self._data.view.rotation_step_deg = rot

    # Reset
    def reset_all_to_default(self) -> None:
        """ユーザー設定を全削除（ショートカットは別管理）"""
        self._settings.remove("general")
        self._settings.remove("view")
        self._data = self._load_effective()

    def reset_section(self, section: str) -> None:
        """特定のセクションのみを規定値へ"""
        if section not in ("general", "view"):
            raise ValueError(f"Invalid section: {section}")
        self._settings.remove(section)
        self._data = self._load_effective()

    def to_dict(self) -> dict[str, Any]:
        data = {
            "general": asdict(self._data.general),
            "view": asdict(self._data.view),
        }
        data["general"]["run_mode"] = self._data.general.run_mode.value
        return data

    def dump_effective_settings(self) -> str:
        """Return effective settings JSON (for diagnostics/support)."""
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("Failed to dump effective settings.")
            return "{}"

    # ---------- 内部実装 ---------------
    def _load_effective(self) -> AppSettingsData:
        """DEFAULTS (JSON preferred) + QSettings overrides, validate, and modelize."""
        self._warnings.clear()
        base = self._load_defaults_files()  # may fall back to DEFAULTS
        merged = self._apply_qsettings_overrides(base)
        return self._make_model_from(merged, base_defaults=base)

    def _is_strict(self) -> bool:
        """Strict mode for dev/CI: missing/broken defaults become fatal."""
        if _truthy_env("QV_STRICT_SETTINGS"):
            return True
        # If user already set run_mode in QSettings, use it to decide strictness.
        v = self._settings.value("general/run_mode", None)
        if v is None:
            return False
        try:
            mode = _validate_run_mode(v)
        except Exception:
            return False
        return mode in (RunMode.DEVELOPMENT, RunMode.VERBOSE)

    def _load_defaults_files(self) -> dict[str, Any]:
        """
        Load defaults from JSON files under settings_dir.
        
        Files (any can be missing):
        - app.json
        - viewer.json
        
        If settings_dir is None, use in-code DEFAULTS.
        """
        if self._settings_dir is None:
            return dict(base_defaults)

        strict = self._is_strict()
        quarantine = not strict  # production path only

        merged: dict[str, Any] = dict(base_defaults)

        app_json = _read_json_dict(
            self._settings_dir / "app.json",
            strict=strict,
            quarantine_broken=quarantine,
            warnings=self._warnings,
        )
        if app_json:
            merged = _deep_merge(merged, app_json)

        viewer_json = _read_json_dict(
            self._settings_dir / "viewer.json",
            strict=strict,
            quarantine_broken=quarantine,
            warnings=self._warnings,
        )
        if viewer_json:
            # allow either {"view": {...}} or flat
            if "view" in viewer_json and isinstance(viewer_json.get("view"), dict):
                merged = _deep_merge(merged, viewer_json)
            else:
                merged = _deep_merge(merged, {"view": viewer_json})
        return merged

    def _apply_qsettings_overrides(self, base: dict[str, Any]) -> dict[str, Any]:
        """
        Read the dict based settings and apply QSettings overrides.
        :param base:
        :return: apply QSettings overrides
        """
        # general
        g = dict(base.get("general", {}))
        v = self._settings.value("general/run_mode", None)
        if v is not None:
            g["run_mode"] = _validate_run_mode(v).value
        else:
            legacy = self._settings.value("general/dev_mode", None)
            if legacy is not None:
                g["run_mode"] = (
                    RunMode.DEVELOPMENT.value if _truthy(str(legacy)) else RunMode.PRODUCTION.value
                )
        v = self._settings.value("general/logging_level", None)
        if v is not None:
            g["logging_level"] = _validate_logging_level(v)

        # view
        vw = dict(base.get("view", {}))
        v = self._settings.value("view/rotation_step_deg", None)
        if v is not None:
            vw["rotation_step_deg"] = _validate_rotation_step(v)

        return {"general": g, "view": vw}

    def _make_model_from(self,
                         merged: dict[str, Any],
                         base_defaults: dict[str, Any]) -> AppSettingsData:
        """
        making model from merged dict and returning merged AppSettingsData
        :param merged:
        :return: merged AppSettingsData
        """
        g = merged.get("general", {})
        vw = merged.get("view", {})
        return AppSettingsData(
            general=GeneralConfig(
                run_mode=_validate_run_mode(g.get("run_mode",
                                                  base_defaults["general"]["run_mode"])),
                logging_level=_validate_logging_level(g.get("logging_level",
                                                            base_defaults["general"]["logging_level"])),
            ),
            view=ViewConfig(
                rotation_step_deg=_validate_rotation_step(vw.get("rotation_step_deg",
                                                                 base_defaults["view"]["rotation_step_deg"]))
            ),
        )
