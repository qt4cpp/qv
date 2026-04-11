"""Placeholder tests for the future MprInteractorStyle task."""

from __future__ import annotations

import pytest

from qv.core.window_settings import WindowSettings
from qv.viewers.interactor_styles.mpr_interactor_style import MprInteractorStyle
from qv.viewers.coordinates import VtkDisplayPoint


class ViewerSpy:
    """Minimal spy object reserved for future interactor-style tests."""

    def __init__(
            self,
            *,
            image_data_loaded: bool = True,
            has_window_settings: bool = True,
    ) -> None:
        # The interactor style only needs truthy/non-truthy state here.
        self.image_data = object() if image_data_loaded else None
        self.window_settings = (
            WindowSettings(level=40.0, width=80.0)
            if has_window_settings
            else None
        )
        self.adjust_calls: list[tuple[int, int]] = []
        self.scroll_calls: list[int] = []
        self.sync_calls: list[tuple[int, int, bool]] = []

    def adjust_window_settings(self, dx: int, dy: int) -> None:
        """Record WW/WL adjustments requests."""
        self.adjust_calls.append((dx, dy))

    def scroll_slice(self, delta: int) -> None:
        """Record slice scrolling requests."""
        self.scroll_calls.append(delta)

    def request_sync_at_vtk_position(
            self,
            point: VtkDisplayPoint,
            *,
            shift_pressed: bool = False,
    ) -> bool:
        """Record Shift-drag sync requests."""
        self.sync_calls.append((point.x, point.y, shift_pressed))
        return True


class FakeInteractor:
    """Simple interactor stub that returns a scripted sequence of positions."""

    def __init__(self,
                 positions: list[tuple[int, int]],
                 *,
                 shift_key: bool = False
     ) -> None:
        self._positions = positions
        self._index = 0
        self._shift_key = shift_key

    def GetEventPosition(self) -> tuple[int, int]:
        """Return the next scripted cursor position."""
        if not self._positions:
            raise AssertionError("FakeInteractor requires at least one position.")

        pos = self._positions[min(self._index, len(self._positions) - 1)]
        self._index += 1
        return pos

    def GetShiftKey(self) -> int:
        """Return 1 when Shift is pressed, matching the VTK API shape."""
        return 1 if self._shift_key else 0


@pytest.fixture
def loaded_viewer() -> ViewerSpy:
    """Provide a viewer spy that behaves like a loaded MPR viewer."""
    return ViewerSpy(image_data_loaded=True, has_window_settings=True)


@pytest.fixture
def unloaded_viewer() -> ViewerSpy:
    """Provide a viewer spy that behaves like an unloaded MPR viewer."""
    return ViewerSpy(image_data_loaded=False, has_window_settings=False)


def test_right_button_press_starts_ww_wl_drag(
        loaded_viewer: ViewerSpy,
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Right-button press should enter WW/WL drag mode.

    The style should capture the cursor position ao the next mouse-move event
    can compute a delta.
    """
    style = MprInteractorStyle(loaded_viewer)
    fake_interactor = FakeInteractor([(10, 20)])

    monkeypatch.setattr(MprInteractorStyle, "GetInteractor", lambda self: fake_interactor)

    style.on_right_button_down(None, None)

    assert style._mode == "ww/wl"
    assert style._last_pos == (10, 20)


def test_mouse_move_adjusts_window_settings_only_during_active_drag(
        loaded_viewer: ViewerSpy,
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Mouse move should update WW/WL only while drag mode is active.

    The style is expected to pass raw dx/dy through to the viewer and let the
    viewer decide how those deltas map to width/level.
    """
    style = MprInteractorStyle(loaded_viewer)
    fake_interactor = FakeInteractor([(100, 200), (112, 185)])

    monkeypatch.setattr(MprInteractorStyle, "GetInteractor", lambda self: fake_interactor)
    monkeypatch.setattr(MprInteractorStyle, "OnMouseMove", lambda self: None)

    # No drag yet, so mouse move should be ignored.
    style.on_mouse_move(None, None)
    assert loaded_viewer.adjust_calls == []

    style.on_right_button_down(None, None)
    style.on_mouse_move(None, None)

    assert loaded_viewer.adjust_calls == [(12, -15)]
    assert style._last_pos == (112, 185)


def test_mouse_wheel_scrolls_slice_forward_and_backward(
        loaded_viewer: ViewerSpy,
) -> None:
    """Wheel events should be converted into relative slice movement."""
    style = MprInteractorStyle(loaded_viewer)

    style.on_mouse_wheel_forward(None, None)
    style.on_mouse_wheel_backward(None, None)

    assert loaded_viewer.scroll_calls == [+1, -1]


def test_unloaded_viewers_ignores_drag_and_wheel_events(
        unloaded_viewer: ViewerSpy,
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Unloaded viewers should ignore all drag and wheel events.

    This prevents the style from trying to perform WW/WL or slice navigation
    when the viewer has no valid image state yet.
    """
    style = MprInteractorStyle(unloaded_viewer)
    fake_interactor = FakeInteractor([(5, 6), (8, 9)])

    monkeypatch.setattr(MprInteractorStyle, "GetInteractor", lambda self: fake_interactor)
    monkeypatch.setattr(MprInteractorStyle, "OnMouseMove", lambda self: None)

    style.on_right_button_down(None, None)
    style.on_mouse_move(None, None)
    style.on_mouse_wheel_forward(None, None)
    style.on_mouse_wheel_backward(None, None)

    assert unloaded_viewer.adjust_calls == []
    assert unloaded_viewer.scroll_calls == []


def test_right_button_release_finishes_drag_and_stops_followup_adjustments(
        loaded_viewer: ViewerSpy,
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Right-button release should end WW/WL drag mode.

    After release, addtional mouse-move events must not keep adjusting the
    window settings.
    """
    style = MprInteractorStyle(loaded_viewer)
    fake_interactor = FakeInteractor([(20, 30), (25, 40), (40, 60)])

    monkeypatch.setattr(MprInteractorStyle, "GetInteractor", lambda self: fake_interactor)
    monkeypatch.setattr(MprInteractorStyle, "OnMouseMove", lambda self: None)

    style.on_right_button_down(None, None)
    style.on_mouse_move(None, None)
    style.on_right_button_up(None, None)
    style.on_mouse_move(None, None)

    assert loaded_viewer.adjust_calls == [(5, 10)]
    assert style._mode is None
    assert style._last_pos is None


def test_shift_left_button_press_starts_sync_drag_and_emits_initial_sync(
        loaded_viewer: ViewerSpy,
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Shift + left press should enter sync-drag mode and emit one initial request.

    Emitting immediately makes the first drag position deterministic instead of
    waiting for the next mouse-move event.
    """
    style = MprInteractorStyle(loaded_viewer)
    fake_interactor = FakeInteractor([(50, 60)], shift_key=True)

    monkeypatch.setattr(MprInteractorStyle, "GetInteractor", lambda self: fake_interactor)
    monkeypatch.setattr(MprInteractorStyle, "OnLeftButtonDown", lambda self: None)

    style.on_left_button_down(None, None)

    assert style._mode == "sync-drag"
    assert style._last_pos == (50, 60)
    assert loaded_viewer.sync_calls == [(50, 60, True)]

def test_shift_drag_mouse_move_continuously_requests_sync(
        loaded_viewer: ViewerSpy,
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    style = MprInteractorStyle(loaded_viewer)
    fake_interactor = FakeInteractor(
        [(50, 60), (50, 60), (54, 63), (70, 90)],
        shift_key=True,
    )

    monkeypatch.setattr(MprInteractorStyle, "GetInteractor", lambda self: fake_interactor)
    monkeypatch.setattr(MprInteractorStyle, "OnLeftButtonDown", lambda self: None)
    monkeypatch.setattr(MprInteractorStyle, "OnMouseMove", lambda self: None)

    style.on_left_button_down(None, None)
    style.on_mouse_move(None, None)
    style.on_mouse_move(None, None)
    style.on_mouse_move(None, None)

    assert loaded_viewer.sync_calls == [
        (50, 60, True),
        (54, 63, True),
        (70, 90, True),
    ]
    assert style._last_pos == (70, 90)