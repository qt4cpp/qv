import os
import sys
import json
import logging

from pathlib import Path
from typing import Callable
from PySide6.QtWidgets import QMainWindow, QMenuBar, QMenu
from PySide6.QtGui import QKeySequence, QAction
from PySide6.QtCore import QSettings

from qv.ui.error_notifier import ErrorNotifier


logger = logging.getLogger(__name__)


class ShortcutManager:
    """Manage keyboard shortcuts."""
    def __init__(self, parent: QMainWindow, config_path: Path):
        self.parent = parent
        self.config_path = config_path
        self.settings = QSettings("TedApp.org", "QV")
        self._actions: dict[str, QAction] = {}
        self._callbacks: dict[str, Callable] = {}
        self._default_shortcuts = self._load_default_config()
        self._load_user_overrides()
        self._register_actions()

        self.dev_mode = str(os.getenv("QV_DEV", "")).lower() in ("1", "true", "yes")
        logger.debug("ShortcutManager initialized Dev mode: %s", self.dev_mode)


    def _load_default_config(self) -> dict[str, str]:
        try:
            with open(self.config_path / "settings.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[ShortcutManager] Error loading default config file: {e}")
            return {}

    def _load_user_overrides(self):
        for cmd, default_seq in self._default_shortcuts.items():
            user_seq = self.settings.value(f"shortcuts/{cmd}", default_seq)
            if user_seq:
                self._default_shortcuts[cmd] = user_seq

    def _register_actions(self):
        for cmd, seq in self._default_shortcuts.items():
            action = QAction(cmd.replace("_", " ").title(), self.parent)
            action.setShortcut(QKeySequence(seq))
            action.triggered.connect(lambda checked=False, c=cmd: self._on_action_triggered(c))
            self.parent.addAction(action)
            self._actions[cmd] = action

    def _on_action_triggered(self, cmd: str):
        logger.debug("Action triggered: %s", cmd)
        cb = self._callbacks.get(cmd)
        if cb:
            func_name = getattr(cb, "__qualname__", repr(cb))
            func_module = getattr(cb, "__module__", "")
            logger.info("Shortcut triggered: %s -> %s.%s", cmd, func_module, func_name)
            try:
                cb()
            except Exception:
                ErrorNotifier.instance().notify(
                    title="Shortcut Error",
                    msg=f"Error in shortcut callback",
                    exc_info=sys.exc_info(),
                    severity="error",
                    dedup_seconds=1.0,
                )
                if getattr(self, "dev_mode", False):
                    raise
                return
        else:
            ErrorNotifier.instance().notify(
                title="Unregistered Shortcut",
                msg=f"Command '{cmd}' is not registered.",
                exc_info=sys.exc_info(),
                severity="error",
                dedup_seconds=1.0,
            )

    def add_callback(self, command_name: str, callback: Callable):
        if command_name not in self._actions:
            raise KeyError(f"Command '{command_name}' not found in registered actions.")
        self._callbacks[command_name] = callback

    def update_shortcut(self, cmd: str, new_seq: str) -> bool:
        if new_seq in [a.shortcut().toString() for a in self._actions.values()]:
            return False
        action = self._actions.get(cmd)
        if not action:
            return False
        action.setShortcuts(QKeySequence(new_seq))
        self.settings.setValue(f"shortcuts/{cmd}", new_seq)
        return True

    def reset_to_default(self):
        self.settings.clear()
        self._load_user_overrides()
        for cmd, action in self._actions.items():
            action.setShortcut(QKeySequence(self._default_shortcuts[cmd]))

    def actions(self):
        return self._actions.values()
