from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Mapping, Optional


class SettingsError(RuntimeError):
    """Raised when strict settings loading fails (dev/CI)."""

def truthy_env(name: str) -> bool:
    """Return True if environment variable is truthy (non-empty, non-zero, etc.)."""
    v = os.environ.get(name, "")
    return v.strip().lower() in ("1", "true", "yes", "on")


def deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-merge dictionaries (override wins)."""
    out: dict[str, Any] = dict(base)
    for k, v in override.items():
        if isinstance(v, Mapping) and isinstance(out.get(k), Mapping):
            out[k] = deep_merge(dict(out[k]), v)
        else:
            out[k] = v
    return out


def read_json_dict(
        path: Path,
        *,
        strict: bool,
        quarantine_broken: bool,
        warnings: list[str],
        logger: Any = None,
) -> Optional[dict[str, Any]]:
    """
    Read JSON file and return dict.

    Behavior:
    - strict=True: missing/broken/non-dict -> raise SettingsError
    - strict=False: return None and record warnings (and log if logger given)
    - quarantine_broken=True: rename broken file to .broken-YYYYmmdd-HHMMSS

    Notes:
    - `warnings` is always appended with human-readable messages on non-fatal path.
    - `logger` can be stdlib logger; if omitted, function is silent except exceptions
     in strict mode.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        msg = f"Defaults JSON missing: {path}"
        if strict:
            raise SettingsError(msg)
        warnings.append(msg)
        if logger is not None:
            logger.warning(msg)
        return None
    except Exception as e:
        msg = f"Failed to read JSON from {path}: ({e})"
        if strict:
            raise SettingsError(msg)
        warnings.append(msg)
        if logger is not None:
            logger.exception(msg)
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        msg = f"Failed to parse JSON from {path}: ({e})"
        if quarantine_broken:
            try:
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                broken = path.with_suffix(f".broken-{ts}")
                path.rename(broken)
                msg += f" -> quarantined to {broken}"
            except Exception:
                if logger is not None:
                    logger.exception(msg)
                return None
        if strict:
            raise SettingsError(msg) from e
        warnings.append(msg)
        if logger is not None:
            logger.warning(msg)
        return None

    if not isinstance(data, dict):
        msg = f"Defaults JSON must be an object at top-level: {path}"
        if strict:
            raise SettingsError(msg)
        warnings.append(msg)
        if logger is not None:
            logger.error(msg)
        return None

    return data