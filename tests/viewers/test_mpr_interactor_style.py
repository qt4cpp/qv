"""Placeholder tests for the future MprInteractorStyle task."""

from __future__ import annotations

import pytest

# Real tests will be added when the dedicated interactor style is introduced.
pytestmark = pytest.mark.skip(
    reason="MprInteractorStyle is introduced in a later task."
)


class ViewerSpy:
    """Minimal spy object reserved for future interactor-style tests."""

    def __init__(self) -> None:
        self.adjust_calls: list[tuple[int, int]] = []
        self.scroll_calls: list[int] = []

    def adjust_window_settings(self, dx: int, dy: int) -> None:
        """Record WW/WL adjustments requests."""
        self.adjust_calls.append((dx, dy))

    def scroll_slice(self, delta: int) -> None:
        """Record slice scrolling requests."""
        self.scroll_calls.append(delta)


@pytest.fixture
def viewer_spy() -> ViewerSpy:
    """Provide a fresh spy instance per test."""
    return ViewerSpy()


def test_mpr_interactor_style_placeholder(viewer_spy: ViewerSpy) -> None:
    """Keep the placeholder file green until the real task starts."""
    assert viewer_spy.adjust_calls == []
    assert viewer_spy.scroll_calls == []