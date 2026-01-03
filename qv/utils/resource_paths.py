from __future__ import annotations

import sys
from pathlib import Path


def app_base_dir() -> Path:
    """
    Retrurn base directory for bundled resources

    - In PyInstaller onefile/onedir: use sys._MEIPASS (temporary extraction dir).
    - In development: use project root (where `settings/` exists).
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # qv/utils/resource_paths.py -> parents[2] is assumed to be the project root.
    return Path(__file__).resolve().parents[2]


def settings_dir() -> Path:
    """Return the directory for settings files (e.g., shortcuts.json)."""
    return app_base_dir() / "settings"


def shortcuts_json_path() -> Path:
    return settings_dir() / "shortcuts.json"
