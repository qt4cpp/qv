"""Scaffold tests for MprViewer."""

from __future__ import annotations

from PySide6 import QtWidgets

from qv.core.window_settings import WindowSettings
from qv.viewers.mpr_viewer import MprPlane


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
    with qtbot.waitSignal(mpr_viewer.image_data_loaded, timeout=1000):
        mpr_viewer.set_image_data(sample_image_data)

    assert mpr_viewer._image_data is sample_image_data
    assert mpr_viewer.window_settings == WindowSettings(level=29.5, width=59.0)

    # For dimensions (4, 5, 3), the axial axis extent is 0..2.
    assert mpr_viewer._slice_min == 0
    assert mpr_viewer._slice_max == 2
    assert mpr_viewer._slice_index == 1
    assert mpr_viewer.get_slice_count() == 3

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

    with qtbot.waitSignal(mpr_viewer.slice_changed, timeout=1000) as blocker:
        mpr_viewer.set_image_index(99)

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

    with qtbot.waitSignal(mpr_viewer.slice_changed, timeout=1000) as blocker:
        mpr_viewer.set_plane(MprPlane.CORONAL)

        plane, index = blocker.args
        assert plane == MprPlane.CORONAL
        assert index == 2

        # For dimensions (4, 5, 3), the coronal axis extent is 0..4.
        assert mpr_viewer._slice_min == 0
        assert mpr_viewer._slice_max == 4
        assert mpr_viewer._slice_index == 2
        assert mpr_viewer.get_slice_count() == 5
