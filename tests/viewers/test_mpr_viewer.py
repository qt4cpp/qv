"""Scaffold tests for MprViewer."""

from __future__ import annotations

import pytest
from PySide6 import QtWidgets

from qv.core.window_settings import WindowSettings
from qv.core.patient_geometry import PatientFrame, build_patient_frame
from qv.viewers.coordinates import QtDisplayPoint
from qv.viewers.mpr_viewer import MprPlane, MprViewer, SyncRequest, WorldPosition


def test_mpr_viewer_fixture_creates_widget(mpr_viewer):
    """"The shared fixture should construct a live QWidget without WW/WL state."""
    assert isinstance(mpr_viewer, QtWidgets.QWidget)
    assert mpr_viewer.window_settings is None


def test_sample_image_data_fixture_has_expected_metadata(sample_image_data):
    """"The shared fixture should provide a vtkImageData with expected metadata."""
    assert sample_image_data.GetDimensions() == (4, 5, 3)
    assert sample_image_data.GetScalarRange() == (0.0, 59.0)


def test_set_image_data_initializes_window_settings_and_slice_state(
        mpr_viewer,
        qtbot,
        sample_image_data,
):
    """
    Loading image data should initialize the core MPR state.

    This test fixes the basic contract before interaction work starts:
    - the source image is kept
    - initial WW/WL is computed
    - the axial slice range is derived from the image extent
    - the initial slice is centered
    """
    with qtbot.waitSignal(mpr_viewer.dataLoaded, timeout=1000):
        mpr_viewer.set_image_data(sample_image_data)

    assert mpr_viewer._image_data is sample_image_data
    assert mpr_viewer.window_settings == WindowSettings(level=30.0, width=59.0)

    # For dimensions (4, 5, 3), the axial axis extent is 0..2.
    assert mpr_viewer._slice_min == 0
    assert mpr_viewer._slice_max == 2
    assert mpr_viewer._slice_index == 1
    assert mpr_viewer.get_slice_count() == 3


def test_constructor_plane_is_used_when_image_is_loaded(
        qtbot,
        settings_manager,
        monkeypatch,
        sample_image_data,
):
    """
    The constructor plane should define the initial slice axis in 4-up mode.
    """
    from qv.viewers.base_viewer import BaseViewer

    monkeypatch.setattr(BaseViewer, "_initialize_interactor", lambda self: None)

    coronal_viewer = MprViewer(
        settings_manager=settings_manager,
        plane=MprPlane.CORONAL
    )
    qtbot.addWidget(coronal_viewer)

    with qtbot.waitSignal(coronal_viewer.dataLoaded, timeout=1000):
        coronal_viewer.set_image_data(sample_image_data)

    assert coronal_viewer.plane == MprPlane.CORONAL
    assert coronal_viewer._slice_min == 0
    assert coronal_viewer._slice_max == 4
    assert coronal_viewer._slice_index == 2
    assert coronal_viewer.get_slice_count() == 5


def test_plane_overlay_shows_plane_name_ater_construction(mpr_viewer):
    """
    The pane label should identiy the viewer even beffore image load.
    """
    actor = mpr_viewer._plane_overlay_actor
    assert actor is not None
    assert actor.GetInput() == "Axial"


def test_plane_overlay_updates_after_image_load(mpr_viewer, sample_image_data):
    """
    The overlay should include plane name and a user-facing slice number.
    """
    mpr_viewer.set_image_data(sample_image_data)

    actor = mpr_viewer._plane_overlay_actor
    assert actor is not None
    assert actor.GetInput() == "Axial Slice 2 / 3"


def test_set_window_settings_clamps_to_scalar_range(mpr_viewer, sample_image_data):
    """
    Explicit WW/WL updates should be clamped to the scalar range.

    This keeps the test aligned with BaseViewer's shared window-settings contract
    while still validating the MPR-specific clamping path.
    """
    mpr_viewer.set_image_data(sample_image_data)

    # The scalar range is 0..59, so both values should be clamped.
    mpr_viewer.set_window_settings(WindowSettings(level=999, width=999))

    assert mpr_viewer.window_settings == WindowSettings(level=59.0, width=59.0)


def test_scroll_slice_clamps_to_valid_range(mpr_viewer, sample_image_data):
    """
    Relative slice scrolling should stay within the computed slice range.

    This test focuses on the viewer contract and avoids any interactor-specific
    assumptions.
    """
    mpr_viewer.set_image_data(sample_image_data)

    mpr_viewer.scroll_slice(+10)
    assert mpr_viewer._slice_index == 2

    mpr_viewer.scroll_slice(-10)
    assert mpr_viewer._slice_index == 0


def test_set_slice_index_updates_plane_overlay(
        mpr_viewer,
        sample_image_data,
):
    """
    Slice overlay text should track the active slice of that viewer only.
    """
    mpr_viewer.set_image_data(sample_image_data)
    mpr_viewer.set_slice_index(2)

    actor = mpr_viewer._plane_overlay_actor
    assert actor is not None
    assert actor.GetInput() == "Axial Slice 3 / 3"


def test_set_slice_index_emits_slice_changed_with_clamped_value(
        mpr_viewer,
        qtbot,
        sample_image_data,
):
    """
    Absolute slice updates should emit the final clamped index.

    Using on out-of-range input makes the clamp behavior part of the test.
    """
    mpr_viewer.set_image_data(sample_image_data)

    with qtbot.waitSignal(mpr_viewer.sliceChanged, timeout=1000) as blocker:
        mpr_viewer.set_slice_index(99)

    plane, index = blocker.args
    assert plane == MprPlane.AXIAL
    assert index == 2
    assert mpr_viewer._slice_index == 2


def test_set_plane_recomputes_slice_range_and_resets_to_center(
        mpr_viewer,
        qtbot,
        sample_image_data,
):
    """
    Changing plane  should recompute the valid slice range for that axis.

    The viewer currently resets the slice to the center of the new plane, so
    the test locks in that behavior before later interaction refactors.
    """
    mpr_viewer.set_image_data(sample_image_data)

    with qtbot.waitSignal(mpr_viewer.sliceChanged, timeout=1000) as blocker:
        mpr_viewer.set_plane(MprPlane.CORONAL)

    plane, index = blocker.args
    assert plane == MprPlane.CORONAL
    assert index == 2

    # For dimensions (4, 5, 3), the coronal axis extent is 0..4.
    assert mpr_viewer._slice_min == 0
    assert mpr_viewer._slice_max == 4
    assert mpr_viewer._slice_index == 2
    assert mpr_viewer.get_slice_count() == 5

    actor = mpr_viewer._plane_overlay_actor
    assert actor is not None
    assert actor.GetInput() == "Coronal Slice 3 / 5"


def test_set_image_data_shows_window_overlay_after_initial_load(
        mpr_viewer,
        sample_image_data,
):
    """
    Initial load should the integration enable the shared WW/WL HUD

    This protects the integration between BaseViewer's overlay state and the
    MPR-specific initial window-setting setup.
    """
    mpr_viewer.set_image_data(sample_image_data)

    actor = mpr_viewer._window_overlay_actor
    assert actor is not None
    assert actor.GetVisibility() == 1
    assert actor.GetInput() == 'WL 30 WW 59'


def test_build_crosshair_segments_for_axial_viewer(mpr_viewer, sample_image_data):
    """
    Axial crosshair  should use:
    - vertical line from sagittal  x
    - horizontal line from coronal y
    """
    mpr_viewer.set_image_data(sample_image_data)
    mpr_viewer.set_crosshair_visible(True, render=False)
    mpr_viewer.set_crosshair_slice_reference(MprPlane.SAGITTAL, 2, render=False)
    mpr_viewer.set_crosshair_slice_reference(MprPlane.CORONAL, 3, render=False)

    segments = mpr_viewer._build_crosshair_segments()
    assert segments is not None

    display_bounds = mpr_viewer._image_actor.GetBounds()
    assert display_bounds is not None

    origin = mpr_viewer._reslice.GetResliceAxesOrigin()
    assert origin is not None

    crosshair_world = (-8.6, -17.6, 6.5)

    display_x = crosshair_world[0] - origin[0]
    display_y = -(crosshair_world[1] - origin[1])
    plane_z = 0.5 * (display_bounds[4] + display_bounds[5])

    assert segments['vertical'][0] == pytest.approx(
        (display_x, display_bounds[2], plane_z)
    )
    assert segments['vertical'][1] == pytest.approx(
        (display_x, display_bounds[3], plane_z)
    )
    assert segments['horizontal'][0] == pytest.approx(
        (display_bounds[0], display_y, plane_z)
    )
    assert segments['horizontal'][1] == pytest.approx(
        (display_bounds[1], display_y, plane_z)
    )


def test_crosshair_segments_are_absent_until_both_references_exist(
        mpr_viewer, sample_image_data
):
    mpr_viewer.set_image_data(sample_image_data)
    mpr_viewer.set_crosshair_visible(True, render=False)
    mpr_viewer.set_crosshair_slice_reference(MprPlane.SAGITTAL, 1, render=False)

    assert mpr_viewer._build_crosshair_segments() is None


def test_crosshair_slice_reference_ignores_own_plane(
        mpr_viewer, sample_image_data
):
    mpr_viewer.set_image_data(sample_image_data)
    mpr_viewer.set_crosshair_visible(True, render=False)
    mpr_viewer.set_crosshair_slice_reference(MprPlane.AXIAL, 99, render=False)

    assert mpr_viewer._crosshair_slice_refs[MprPlane.AXIAL] is None


def test_world_to_slice_index_uses_viewer_plane_axis(mpr_viewer, sample_image_data):
    """
    The viewer should convert a canonical world point inti a local slice index
    using its own plane axis.
    """
    mpr_viewer.set_image_data(sample_image_data)

    assert mpr_viewer.world_to_slice_index(WorldPosition(x=-9.3, y=-18.4, z=0.0)) == 2


def test_request_sync_at_qt_position_emits_sync_request(
        mpr_viewer,
        qtbot,
        monkeypatch,
) -> None:
    """
    Double-click sync should emit a full slice-sync request when picking succeeds.
    """
    picked_world = WorldPosition(x=1.5, y=2.5, z=3.5)
    monkeypatch.setattr(
        mpr_viewer,
        "pick_world_position_from_display",
        lambda point: picked_world,
    )

    with qtbot.waitSignal(mpr_viewer.syncRequested, timeout=1000) as blocker:
        handled = mpr_viewer.request_sync_at_qt_position(
            QtDisplayPoint(120, 80)
        )

    assert handled is True
    request = blocker.args[0]
    assert isinstance(request, SyncRequest)
    assert request.source_plane == MprPlane.AXIAL
    assert request.world_position == picked_world
    assert request.update_crosshair is True
    assert request.update_slices is True
    assert request.shift_pressed is False


def test_request_sync_at_qt_position_emits_shift_drag_sync_request(
        mpr_viewer,
        qtbot,
        monkeypatch,
) -> None:
    """
    Shift-drag sync should emit a continuous SyncRequest with the modifier flag.
    """
    picked_world = WorldPosition(x=4.0, y=5.0, z=6.0)
    monkeypatch.setattr(
        mpr_viewer,
        "pick_world_position_from_qt_display",
        lambda point: picked_world,
    )

    with qtbot.waitSignal(mpr_viewer.syncRequested, timeout=1000) as blocker:
        handled = mpr_viewer.request_sync_at_qt_position(
            QtDisplayPoint(x=25, y=35),
            shift_pressed=True,
        )

        assert handled is True
        request = blocker.args[0]
        assert isinstance(request, SyncRequest)
        assert request.source_plane == MprPlane.AXIAL
        assert request.world_position == picked_world
        assert request.update_crosshair is True
        assert request.update_slices is True
        assert request.shift_pressed is True


def test_oriented_image_remaps_axial_slice_axis_to_patient_superior(
        mpr_viewer,
        oriented_sample_image_data,
):

    mpr_viewer.set_image_data(oriented_sample_image_data)

    assert mpr_viewer._slice_min == 0
    assert mpr_viewer._slice_max == 4
    assert mpr_viewer._slice_index == 2


def test_world_to_slice_index_uses_patient_frame_for_oriented_image(
        mpr_viewer,
        oriented_sample_image_data,
):
    frame = build_patient_frame(oriented_sample_image_data)
    patient_point = frame.patient_point_from_continuous_ijk((1.0, 3.0, 2.0))

    mpr_viewer.set_image_data(
        oriented_sample_image_data,
        patient_frame=frame,
    )

    assert mpr_viewer.world_to_slice_index(
        WorldPosition(
            x=patient_point[0],
            y=patient_point[1],
            z=patient_point[2],
        )
    ) == 3