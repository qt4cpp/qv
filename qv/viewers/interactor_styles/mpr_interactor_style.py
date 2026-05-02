"""Dedicated interactor style for MPR viewer."""

from __future__ import annotations

from typing import Protocol
import logging

from vtkmodules.vtkInteractionStyle import vtkInteractorStyleImage

from qv.viewers.coordinates import VtkDisplayPoint

logger = logging.getLogger(__name__)


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
        self._slice_drag_accumulated_y: float = 0.0
        self._slice_drag_pixels_per_slice: int = 8

        self.AddObserver("LeftButtonPressEvent", self.on_left_button_down)
        self.AddObserver("LeftButtonReleaseEvent", self.on_left_button_up)
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

    def _is_shift_pressed(self) -> bool:
        """Return True when Shift is pressed."""
        iren = self.GetInteractor()
        return bool(iren is not None and iren.GetShiftKey())

    def on_left_button_down(self, obj, event) -> None:
        """
        Start a Shift-drag synchronization when possible.

        Normal left-button behavior is preserved unless Shift is pressed while
        valid image data is loaded.
        """
        if not self._has_loaded_image():
            return

        iren = self.GetInteractor()
        self._last_pos = iren.GetEventPosition()

        if iren.GetShiftKey():
            self._mode = 'sync-drag'
            x, y = self._last_pos
            logger.debug("[MprInteractorStyle] Shift-drag start at (%d, %d)", x, y)
            self._viewer.request_sync_at_vtk_position(
                VtkDisplayPoint(x=x, y=y),
                shift_pressed=True,
            )
            return

        self._mode = "slice-drag"
        self._slice_drag_accumulated_y = 0.0
        logger.debug("[MprInteractorStyle] Start slice-drag at %s", self._last_pos)

    def on_left_button_up(self, obj, event) -> None:
        """Finish Shift-drag synchronization if it is active."""
        if self._mode in {'sync-drag', 'slice-drag'}:
            logger.debug("[MprInteractorStyle] End slice-drag at %s", self._last_pos)
            self._mode = None
            self._last_pos = None
            self._slice_drag_accumulated_y = 0.0
            return

        self.OnLeftButtonUp()

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
        if self._mode == 'sync-drag':
            iren = self.GetInteractor()
            x, y = iren.GetEventPosition()

            if self._last_pos == (x, y):
                return

            self._viewer.request_sync_at_vtk_position(
                VtkDisplayPoint(x=x, y=y),
                shift_pressed=True,
            )
            self._last_pos = (x, y)
            return

        if self._mode == "slice-drag":
            iren = self.GetInteractor()
            x, y = iren.GetEventPosition()

            if self._last_pos is None:
                self._last_pos = (x, y)
                return

            lx, ly = self._last_pos
            dy = y - ly

            # VTK display Y grows upward. Positive dy makes upward drag positive.
            self._slice_drag_accumulated_y += dy

            visual_steps = int(self._slice_drag_accumulated_y / self._slice_drag_pixels_per_slice)
            if visual_steps != 0:
                self._viewer.scroll_slice_by_patient_drag(visual_steps)
                self._slice_drag_accumulated_y -= (visual_steps * self._slice_drag_pixels_per_slice)
                logger.debug(
                    "[MprInteractorStyle] Slice drag scroll visual_steps=%d",
                    visual_steps
                )
            # steps = int(self._slice_drag_accumulated_y / self._slice_drag_pixels_per_slice)
            # if steps != 0:
            #     self._viewer.scroll_slice(steps)
            #     self._slice_drag_accumulated_y -= steps * self._slice_drag_pixels_per_slice
            #     logger.debug("[MprInteractorStyle] Slice drag scroll steps=%d", steps)

            self._last_pos = (x, y)
            return

        if self._mode != 'ww/wl' or self._last_pos is None:
            self.OnMouseMove()
            return

        iren = self.GetInteractor()
        x, y = iren.GetEventPosition()
        lx, ly = self._last_pos
        dx, dy = x - lx, y - ly

        if dx == 0 and dy == 0:
            return

        self._viewer.adjust_window_settings(dx, dy)
        self._last_pos = (x, y)

    def on_mouse_wheel_forward(self, obj, event) -> None:
        """Move one slice forward when image data is loaded."""
        if not self._has_loaded_image():
            return

        if self._is_shift_pressed():
            logger.debug("[MprInteractorStyle] Shift-wheel forward: zoom in.")
            self._viewer.adjust_zoom_by_steps(+1)
            return

        self._viewer.scroll_slice(+1)

    def  on_mouse_wheel_backward(self, obj, event) -> None:
        """Move one slice backward when image data is loaded."""
        if not self._has_loaded_image():
            return

        if self._is_shift_pressed():
            logger.debug("[MprInteractorStyle] Shift-wheel backward: zoom out.")
            self._viewer.adjust_zoom_by_steps(-1)
            return

        self._viewer.scroll_slice(-1)
