"""Dedicated interactor style for MPR viewer."""

from __future__ import annotations

from typing import Protocol

from vtkmodules.vtkInteractionStyle import vtkInteractorStyleImage


class MprInteractorStyle(vtkInteractorStyleImage):
    """
    Interactor style for 2D MPR viewing.

    Responsibilities:
    - right drag -> WW/WL adjustment
    - mouse wheel -> slice navigation
    - keep other image-style mouse behavior delegated to vtkInteractorStyleImage
    """

    def __init__(self, viewer: Protocol) -> None:
        super().__init__()
        self._viewer = viewer
        self._mode: str | None = None
        self._last_pos: tuple[int, int] | None = None

        self.AddObserver("RightButtonPressEvent", self.on_right_button_down)
        self.AddObserver("RightButtonReleaseEvent", self.on_right_button_up)
        self.AddObserver("MouseMoveEvent", self.on_mouse_move)
        self.AddObserver("MouseWheelForwardEvent", self.on_mouse_wheel_forward)
        self.AddObserver("MouseWheelBackwardEvent", self.on_mouse_wheel_backward)

    def _has_loaded_image(self) -> bool:
        """Return True when the viewer has image data ready for interaction."""
        return getattr(self._viewer, "image_data", None) is not None

    def _has_window_settings(self) -> bool:
        """Return True when the viewer has window/level settings."""
        return getattr(self._viewer, "window_settings", None) is not None

    def on_right_button_down(self, obj, event) -> None:
        """
        Start WW/WL drag.

        The cursor position is captured here so subsequent mouse moves can
        forward relative dx/dy to the viewer.
        """
        if not self._has_loaded_image() or not self._has_window_settings():
            return

        iren = self.GetInteractor()
        self._last_pos = iren.GetEventPosition()
        self._mode = 'ww/wl'

    def on_right_button_up(self, obj, event) -> None:
        """Finish WW/WL drag and clear the stored cursor position."""
        self._mode = None
        self._last_pos = None

    def on_mouse_move(self, obj, event) -> None:
        """
        Forward raw dx/dy to the viewer only while WW/WL drag is active.

        Outside drag mode, fall back to the default image-style behavior.
        """
        if self._mode != 'ww/wl' or self._last_pos is None:
            self.OnMouseMove()
            return

        iren = self.GetInteractor()
        x, y = iren.GetEventPosition()
        lx, ly = self._last_pos
        dx, dy = x -lx, y - ly

        if dx == 0 and dy == 0:
            return

        self._viewer.adjust_window_settings(dx, dy)
        self._last_pos = (x, y)

    def on_mouse_wheel_forward(self, obj, event) -> None:
        """Move one slice forward when image data is loaded."""
        if not self._has_loaded_image():
            return
        self._viewer.scroll_slice(+1)

    def  on_mouse_wheel_backward(self, obj, event) -> None:
        """Move one slice backward when image data is loaded."""
        if not self._has_loaded_image():
            return
        self._viewer.scroll_slice(-1)
