from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any, Dict
from PySide6.QtCore import QSettings
import logging

logger = logging.getLogger(__name__)

# ----------------------
# デフォルト設定
# ----------------------
DEFAULTS: Dict[str, Any] = {
    "general": {
        "dev_mode": "INFO",  # "DEBUG", "INFO", "WARNING", "ERROR"
    },
    "view": {
        "rotation_step_deg": 5.0,
    },
}

# ---------------------
# Data model
# ---------------------
@dataclass
class GeneralConfig:
    dev_mode: bool = False
    logging_level: str = "INFO"

@dataclass
class ViewConfig:
    rotation_step_deg: float = 5.0

@dataclass
class AppSettingsData:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    view: ViewConfig = field(default_factory=ViewConfig())

# ----------------------
# Utility
# ----------------------
def _truthy(s: str) -> bool:
    return s.strip().lower() in ("1", "true", "yes", "on")

def _validate_logging_level(v: str) -> str:
    v = str(v).upper()
    return v if v in ("DEBUG", "INFO", "WARNING", "ERROR") else "INFO"

def _validate_rotation_step(v: Any) -> float:
    try:
        f = float(v)
    except Exception:
        return 5.0
    return f if (0 < f <= 90) else 5.0


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
    def __init__(self, org_domain: str = "TedApp.org", app_name: str = "QV"):
        self._settings = QSettings(org_domain, app_name)
        self._data = self._load_effective()

    # 読み取り
    @property
    def data(self) -> AppSettingsData:
        return self._data

    @property
    def dev_mode(self) -> bool:
        return self._data.general.dev_mode

    @property
    def logging_level(self) -> str:
        return self._data.general.logging_level

    @property
    def rotation_step_deg(self) -> float:
        return self._data.view.rotation_step_deg

    # 書き込み
    def set_dev_mode(self, v: bool) -> None:
        val = bool(v)
        self._settings.setValue("general/dev_mode", "true" if val else "false")
        self._data.general.dev_mode = val

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
        return {
            "general": asdict(self._data.general),
            "view": asdict(self._data.view),
        }

    # ---------- 内部実装 ---------------
    def _load_effective(self) -> AppSettingsData:
        """DEFAULTS をベースに QSettings の上書きを反映、検証、モデル化"""
        merged = self._read_from_qsettings(DEFAULTS)
        return self._make_model_from(merged)

    def _read_from_qsettings(self, base: dict[str, Any]) -> dict[str, Any]:
        # general
        g = dict(base.get("general", {}))
        v = self._settings.value("general/dev_mode", None)
        if v is not None:
            g["dev_mode"] = _truthy(str(v))
        v = self._settings.value("general/logging_level", None)
        if v is not None:
            g["logging_level"] = _validate_logging_level(v)

        # view
        vw = dict(base.get("view", {}))
        v = self._settings.value("view/rotation_step_deg", None)
        if v is not None:
            vw["rotation_step_deg"] = _validate_rotation_step(v)

        return {"general": g, "view": vw}

    def _make_model_from(self, merged: dict[str, Any]) -> AppSettingsData:
        g = merged.get("general", {})
        vw = merged.get("view", {})
        return AppSettingsData(
            general=GeneralConfig(
                dev_mode=bool(g.get("dev_mode", DEFAULTS["general"]["dev_mode"])),
                logging_level=_validate_logging_level(g.get("logging_level", DEFAULTS["general"]["dev_mode"])),
            ),
            view=ViewConfig(
                rotation_step_deg=_validate_rotation_step(vw.get("rotation_step_deg", DEFAULTS["view"]["rotation_step_deg"]))
            ),
        )