from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class Command(Generic[T]):
    before: T
    after: T


class HistoryManager(Generic[T]):
    """
    Generic Undo/Redo history manager (Qt-independent).

    Design notes:
    - This class is intentionally UI-framework-agnostic.
      UI state (enabling/disabling actions) is updated bythe caller.
    - `apply_state` is injected so this module does not depend on VTK/Qt/viewer code.
    - If apply_state raises an exception, we do not mutate stacks (history remains consistent).
    """

    def __init__(self, max_undo: int = 10) -> None:
        self._max_undo = max_undo
        self._undo_stack: list[Command[T]] = []
        self._redo_stack: list[Command[T]] = []

    def clear(self) -> None:
        """Clear undo/redo stacks."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        logger.debug("history cleared")

    def can_undo(self) -> bool:
        """Return True if undo is possible."""
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        """Return True if redo is possible."""
        return bool(self._redo_stack)

    def do(self, cmd: Command[T], apply_state: Callable[[T], None]) -> None:
        """
        Execute a new command and push it to the undo stack.

        Rules:
        - Always clears redo stack on a new command.
        - Trims undo stack to max size.
        """
        apply_state(cmd.after)
        self._undo_stack.append(cmd)
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self, apply_state: Callable[[T], None]) -> None:
        logger.debug(f"undo stack size: {len(self._undo_stack)}")
        if not self._undo_stack:
            return
        cmd = self._undo_stack[-1]
        apply_state(cmd.before)
        self._undo_stack.pop()
        self._redo_stack.append(cmd)
        logger.debug(f"undo: {cmd.before} -> {cmd.after}")

    def redo(self, apply_state: Callable[[T], None]) -> None:
        logger.debug(f"redo stack size: {len(self._redo_stack)}")
        if not self._redo_stack:
            return
        cmd = self._redo_stack[-1]
        apply_state(cmd.after)
        self._redo_stack.pop()
        self._undo_stack.append(cmd)
        logger.debug(f"redo: {cmd.before} -> {cmd.after}")