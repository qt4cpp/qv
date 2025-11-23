"""Interaction controller - manages user input and viewer interactions."""
from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Optional, TYPE_CHECKING

from PySide6.QtCore import QPoint

if TYPE_CHECKING:
    import vtk


logger = logging.getLogger(__name__)


class InteractionMode(Enum):
    """Enum for different interaction modes."""
    DEFAULT = auto()
    CAMERA_ROTATION = auto()
    WINDOWING = auto()  # Adjust window level and width
    CLIPPING = auto()
    ERASURE = auto()
    PAN = auto()
    ZOOM = auto()


class MouseButton(Enum):
    """Enum for different mouse buttons."""
    LEFT = auto()
    RIGHT = auto()
    MIDDLE = auto()
    NONE = auto()


class InteractionController:
    """
    Central coordinator for interaction mode management.

    This class bridges Qt UI and VTK interactor styles, managing:
    - Current interaction mode
    - Mode transitions with validation
    - Callbacks for mode changes
    - State persistence across mode switches

    Usage:
        controller = InteractionController()
        controller.add_mode_changed_callback(on_mode_changed)
        controller.set_mode(InteractionMode.CLIPPING)
    """

    def __init__(self):
        """Initialize the interaction controller."""
        self._current_mode: InteractionMode = InteractionMode.DEFAULT
        self._mode_stack: list[InteractionMode] = []

        # Callbacks for interaction events
        self._on_mode_changed_callbacks: list[Callable[[InteractionMode, InteractionMode], None]] = []
        self._on_mode_enter_callbacks: dict[InteractionMode, list[Callable[[], None]]] = {}
        self._on_mode_exit_callbacks: dict[InteractionMode, list[Callable[[], None]]] = {}

        # Optional reference to VTK interactor for coodination
        self._vtk_interactor: vtk.vtkRenderWindowInteractor | None = None

    @property
    def current_mode(self) -> InteractionMode:
        """Get current interaction mode."""
        return self._current_mode

    @property
    def previous_mode(self) -> InteractionMode | None:
        """Get previous interaction mode."""
        return self._mode_stack[-1] if self._mode_stack else None

    def get_previous_mode_or_default(self) -> InteractionMode:
        """Get previous interaction mode, or default mode if stack is empty."""
        return self.previous_mode or InteractionMode.DEFAULT

    @property
    def has_history(self) -> bool:
        """Check if there is mode history."""
        return bool(self._mode_stack)

    @property
    def mode_stack_depth(self) -> int:
        """Get depth of the mode stack."""
        return len(self._mode_stack)

    def set_vtk_interactor(self, interactor: vtk.vtkRenderWindowInteractor) -> None:
        """
        Set the VTK interactor for coordination.

        This allows the controller to coordinate with VTK's event system.
        :param interactor:
        """
        self._vtk_interactor = interactor

    def set_mode(self, mode: InteractionMode, record_history: bool = True) -> None:
        """
        Change the interaction mode.

        Triggers callbacks for mode exit, mode enter, and mode changed.

        :param mode: New interaction mode
        :param record_history: Whether to record current mode in stack (default: True)
        :return:
        """
        if mode == self._current_mode:
            return

        old_mode = self._current_mode

        self._triggered_mode_exit(old_mode)

        if record_history:
            self._mode_stack.append(old_mode)

        self._current_mode = mode

        logger.info(f"Interaction mode changed from {old_mode} -> {mode}")

        self._triggered_mode_enter(mode)
        self._notify_mode_changed(old_mode, mode)

    def push_mode(self, mode: InteractionMode) -> None:
        """
        Push current mode to stack and set new mode.
        :param mode: New interaction mode
        """
        self.set_mode(mode, record_history=True)
        logger.debug(f"Mode pushed: {mode.name} (stack depth: {self.mode_stack_depth})")

    def pop_mode(self) -> bool:
        """
        Pop mode from stack and restore it.

        :return: True if mode was restored, False otherwise
        """
        if not self._mode_stack:
            logger.warning("Cannot pop mode: mode stack is empty")
            return False

        previous_mode = self._mode_stack.pop()
        self.set_mode(previous_mode, record_history=False)
        logger.debug(f"Mode popped: {previous_mode.name} (stack depth: {self.mode_stack_depth})")
        return True

    def pop_or_default(self) -> InteractionMode:
        """
        Pop mode from stack, or set default mode if stack is empty.

        :return: The restored mode
        """
        if self.pop_mode():
            return self._current_mode
        else:
            self.set_mode(InteractionMode.DEFAULT, record_history=False)
            return InteractionMode.DEFAULT

    def clear_history(self) -> None:
        """Clear the interaction mode history."""
        self._mode_stack.clear()
        logger.debug("Interaction mode history cleared")

    def add_mode_changed_callback(
            self,
            callback: Callable[[InteractionMode, InteractionMode], None]
    ) -> None:
        """
        Add a callback for any interaction mode change.

        Callback signature: callback(old_mode: InteractionMode, new_mode: InteractionMode) -> None
        :param callback: Callback function
        """
        self._on_mode_changed_callbacks.append(callback)

    def add_mode_enter_callback(
            self, mode: InteractionMode,
            callback: Callable[[], None]
    ) -> None:
        """
        Add a callback for entering a specific interaction mode.
        :param mode:
        :param callback:
        """
        if mode not in self._on_mode_enter_callbacks:
            self._on_mode_enter_callbacks[mode] = []
        self._on_mode_enter_callbacks[mode].append(callback)

    def add_mode_exit_callback(
            self,
            mode: InteractionMode,
            callback: Callable[[], None]
    ) -> None:
        """
        Add a callback for exiting a specific interaction mode.
        :param mode: Mode to watch
        :param callback: Callback function
        """
        if mode not in self._on_mode_exit_callbacks:
            self._on_mode_exit_callbacks[mode] = []
        self._on_mode_exit_callbacks[mode].append(callback)

    def reset(self):
        """Reset the interaction controller to default mode."""
        self._mode_stack.clear()
        self.set_mode(InteractionMode.DEFAULT, record_history=False)
        logger.debug("Interaction controller reset")

    def _notify_mode_changed(self,
                             old_mode: InteractionMode,
                             new_mode: InteractionMode) -> None:
        """Notify callbacks of mode changes."""
        for callback in self._on_mode_changed_callbacks:
            try:
                callback(old_mode, new_mode)
            except Exception as e:
                logging.exception(f"Error in mode changed callback: {e}")

    def _trigger_mode_enter(self, mode: InteractionMode) -> None:
        """Trigger callbacks for entering a specific mode."""
        callbacks = self._on_mode_enter_callbacks.get(mode, [])
        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                logging.exception(f"Error in mode enter callback: {e}")

    def _trigger_mode_exit(self, mode: InteractionMode) -> None:
        """Trigger callbacks for exiting a specific mode."""
        callbacks = self._on_mode_exit_callbacks.get(mode, [])
        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                logging.exception(f"Error in mode exit callback: {e}")