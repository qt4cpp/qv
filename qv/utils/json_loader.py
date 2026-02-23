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


def _fail(
        msg: str,
        *,
        strict: bool,
        warnings: list[str],
        logger: Any = None,
        exc: Exception | None = None,
        level: str = "warning",
) -> Optional[dict[str, Any]]:
    """Centralized failure handler: records a human-readable warning message, logs it
    at the requested level (optional with exception context), and raises
    SettingsError when strict=True. Returns None in non-strict mode to indicate fallback.
     """
    if strict:
        raise SettingsError(msg) from exc
    warnings.append(msg)
    if logger is not None:
        log = getattr(logger, level, logger.warning)
        if exc is not None and level == "exception":
            logger.exception(msg)
        else:
            log(msg)
    return None


def _read_text(path: Path) -> str:
    """Read the entire file as UTF-8 text. Any I/O errors are propagated to the caller."""
    return path.read_text(encoding="utf-8")


def _parse_json(text: str, path: Path) -> dict[str, Any]:
    """Parse JSON text and ensure the top-level value is a dictionary. Raises ValueError
    if the JSON is valid but not an object.
    """
    data = json.loads(text)
    if not isinstance(data, dict):
        raise SettingsError(f"Defaults JSON must be an object at top-level: {path}")
    return data


def _quarantine(path: Path, *, logger: Any = None) -> str:
    """Rename a broken JSON file to a timestamped .broken-YYYYmmdd-HHMMSS suffix
    for diagnostics and return the new path as a string.
    """
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    broken = path.with_suffix(f".broken-{ts}")
    path.rename(broken)
    if logger is not None:
        logger.warning(f"Broken JSON quarantined to {broken}")
    return str(broken)


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
    """
    try:
        text = _read_text(path)
    except FileNotFoundError as e:
        return _fail(f"Defaults JSON missing: {path}",
                     strict=strict, warnings=warnings, logger=logger, exc=e)
    except Exception as e:
        return _fail(f"Failed to read JSON from {path}: ({e})",
                     strict=strict, warnings=warnings, logger=logger, exc=e,
                     level="exception")

    try:
        return _parse_json(text, path)
    except json.JSONDecodeError as e:
        msg = f"Failed to parse JSON from {path}: ({e})"
        if quarantine_broken:
            try:
                quarantined = _quarantine(path, logger=logger)
                msg += f" -> quarantined to {quarantined}"
            except Exception as qe:
                return _fail(msg, strict=strict, warnings=warnings, logger=logger, exc=qe,
                             level="exception")
        return _fail(msg, strict=strict, warnings=warnings, logger=logger, exc=e)
    except Exception as e:
        return _fail(str(e), strict=strict, warnings=warnings, logger=logger, exc=e, level="error")
