from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qv.viewers.controllers.mpr_sync_controller import MprSyncController

__all__ = ["MprSyncController"]


def __getattr__(name: str):
    if name == "MprSyncController":
        from qv.viewers.controllers.mpr_sync_controller import MprSyncController
        return MprSyncController
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
