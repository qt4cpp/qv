from __future__ import annotations

from dataclasses import dataclass

from qv.viewers.controllers.mpr_sync_controller import MprSyncController
from qv.viewers.mpr_viewer import MprPlane, SyncRequest, WorldPosition


@dataclass
class ViewerSpy:
    plane: MprPlane
    image_data: object = object()
    target_index: int = 0

    def __post_init__(self) -> None:
        self.received_indices: list[int] = []

    def world_to_slice_index(self, world_position: WorldPosition) -> int:
        # Each spy retruns a plane-specific canned slice index so the test only
        # validatates controller fan-out and not the viewer math.
        return self.target_index

    def set_slice_index(self, index: int) -> None:
        self.received_indices.append(index)


def test_sync_controller_updates_all_registered_viewers() -> None:
    controller = MprSyncController()

    axial = ViewerSpy(MprPlane.AXIAL, target_index=11)
    coronal = ViewerSpy(MprPlane.CORONAL, target_index=22)
    sagittal = ViewerSpy(MprPlane.SAGITTAL, target_index=33)

    controller.register_viewer(axial)
    controller.register_viewer(coronal)
    controller.register_viewer(sagittal)

    request = SyncRequest(
        source_plane=MprPlane.AXIAL,
        world_position=WorldPosition(x=1.0, y=2.0, z=3.0),
        update_crosshair=True,
        update_slices=True,
    )

    controller.handle_sync_request(request)

    assert axial.received_indices == [11]
    assert coronal.received_indices == [22]
    assert sagittal.received_indices == [33]


def test_sync_controller_skips_unloaded_viewers() -> None:
    controller = MprSyncController()

    loaded = ViewerSpy(MprPlane.AXIAL, image_data=object(), target_index=7)
    unloaded = ViewerSpy(MprPlane.CORONAL, image_data=None, target_index=9)

    controller.register_viewer(loaded)
    controller.register_viewer(unloaded)

    request = SyncRequest(
        source_plane=MprPlane.AXIAL,
        world_position=WorldPosition(x=1.0, y=2.0, z=3.0),
        update_crosshair=True,
        update_slices=True,
    )

    controller.handle_sync_request(request)

    assert loaded.received_indices == [7]
    assert unloaded.received_indices == []