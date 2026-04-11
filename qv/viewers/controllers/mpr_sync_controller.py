from __future__ import annotations

import logging

from qv.viewers.mpr_viewer import MprPlane, MprViewer, SyncRequest

logger = logging.getLogger(__name__)


class MprSyncController:
    """
    Controller responsible for applying synchronization requests across MPR viewers.

    Phase 5 scope:
    - accept one-shot sync requests from double click
    - accept continuous sync requests from Shift-drag
    - convert the requested world position into each viewer's slice index
    - update all viewers once per request
    - avoid recursive re-entry while a sync is already running.
    """

    def __init__(self) -> None:
        self._viewers: dict[MprPlane, MprViewer] = {}
        self._is_syncing = False

    def register_viewer(self, viewer: MprViewer) -> None:
        """Register one fixed-plane viewer."""
        self._viewers[viewer.plane] = viewer
        logger.debug("[MprSyncController] Registered viewer: %s", viewer.plane.value)

    def handle_sync_request(self, request: SyncRequest) -> None:
        """Handle a SyncRequest from a single viewer."""
        if self._is_syncing:
            logger.debug("[MprSyncController] Ignoring nested sync request from %s.",
                         request.source_plane)
            return

        if not request.update_slices:
            logger.debug("[MprSyncController] Request without slice updates received; nothing to do.")
            return

        self._is_syncing = True
        try:
            request_kind = "shift-drag" if request.shift_pressed else "double-click"
            logger.info(
                "[MprSyncController] Sync from %s at world=(%.3f, %.3f, %.3f).",
                request_kind,
                request.source_plane.value,
                request.world_position.x,
                request.world_position.y,
                request.world_position.z,
            )

            for plane, viewer in self._viewers.items():
                if viewer.image_data is None:
                    logger.debug("[MprSyncController] Skipping sync to %s: no image data.", plane.value)
                    continue

                target_index = viewer.world_to_slice_index(request.world_position)
                logger.debug(
                    "[MprSyncController] plane=%s, target_slice=%d, request_kind=%s",
                    plane.value,
                    target_index,
                    request_kind,
                )
                viewer.set_slice_index(target_index)
        finally:
            self._is_syncing = False
            logger.debug("[MprSyncController] Sync completed.")
