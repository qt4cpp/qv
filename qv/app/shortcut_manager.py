import sys
import json
import logging

from pathlib import Path
from typing import Callable, Optional, Protocol
from PySide6.QtWidgets import QMainWindow
from PySide6.QtGui import QKeySequence, QAction
from PySide6.QtCore import QSettings

from ui.dialogs.error_notifier import ErrorNotifier
from app.app_settings_manager import AppSettingsManager, RunMode


logger = logging.getLogger(__name__)


class SettingsProtocol(Protocol):
    @property
    def run_mode(self) -> RunMode: ...


class ShortcutManager:
    """
    Manage keyboard shortcuts with split configuration files.
    -------------------------
    This manager now reads two kinds of settings.
    1) `shortcuts.json` (package default) + user overrides in QSettings under `shortcuts/*`.
    2) `settings.json` (package default) for general app settings (e.g., run_mode)
       User overrides for general
    add_callback: Add a callback function for a shortcut.
    update_shortcut: Update the shortcut for a command.
    reset_to_default: Reset all shortcuts to default.
    actions: Return a list of all actions.
    --------------------------
    - You need to call add_callback to register a callback function for the given command.
    - You can use the registered command name. So write the command and the shortcut in the settings file.
    - ShortcutManager will read the default settings from the file and override them
    with user-defined shortcuts.
    """
    def __init__(self, parent: QMainWindow, config_path: Path,
                 settings_manager: Optional[AppSettingsManager] = None):
        self.parent = parent
        self.config_path = config_path
        self._shortcut_settings = QSettings("TedApp.org", "QV")
        self._settings_manager: AppSettingsManager = settings_manager or AppSettingsManager()

        self._actions: dict[str, QAction] = {}
        self._callbacks: dict[str, Callable] = {}
        self._default_shortcuts = self._load_default_shortcut()
        self._load_user_overrides()
        self._register_actions()

        logger.debug(
            "ShortcutManager initialized run mode: %s",
            self._settings_manager.run_mode.value,
        )


    def _load_default_shortcut(self) -> dict[str, str]:
        """
        Load the default config from `shortcuts.json`.
        Settings are stored in JSON format.
        File format example:
        {
            "open_menu": "Ctrl+O",
            "quit": "Ctrl+Q"
        }
        :return: dict[str, str]
        """
        logger.debug(f"Loading default shortcuts: {self.config_path}")
        try:
            with open(self.config_path / "shortcuts.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.debug(f"Loaded default shortcuts: {data}")
                return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[ShortcutManager] Error loading shortcuts.json: {e}")
            return {}

    def _load_user_overrides(self):
        """
        Override default shortcuts with user-defined shortcuts.
        """
        for cmd, default_seq in self._default_shortcuts.items():
            user_seq = self._shortcut_settings.value(f"shortcuts/{cmd}", default_seq)
            if user_seq:
                self._default_shortcuts[cmd] = user_seq

    def _register_actions(self):
        """
        Register default actions for each command.
        :return:
        """
        for cmd, seq in self._default_shortcuts.items():
            action = QAction(cmd.replace("_", " ").title(), self.parent)
            action.setShortcut(QKeySequence(seq))
            action.triggered.connect(lambda checked=False, c=cmd: self._on_action_triggered(c))
            self.parent.addAction(action)
            self._actions[cmd] = action

    def _on_action_triggered(self, cmd: str):
        """
        Trigger the callback function for the given command.
        :param cmd: Command name.(e.g., "open_menu")
        :return:
        """
        logger.debug("Action triggered: %s", cmd)
        cb = self._callbacks.get(cmd)
        if cb:
            func_name = getattr(cb, "__qualname__", repr(cb))
            func_module = getattr(cb, "__module__", "")
            logger.info("Shortcut triggered: %s -> %s.%s",
                        cmd, func_module, func_name)
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
                if self._settings_manager.dev_mode:
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
        """
        Add a callback function for a shortcut.
        :param command_name: Command name( e.g., "open_menu).
        :param callback: Callback function. (e.g., self.open_menu)
        :return:
        """
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
        self._shortcut_settings.setValue(f"shortcuts/{cmd}", new_seq)
        return True

    def reset_to_default(self):
        self._shortcut_settings.clear()
        self._load_user_overrides()
        for cmd, action in self._actions.items():
            action.setShortcut(QKeySequence(self._default_shortcuts[cmd]))

    def actions(self):
        return self._actions.values()
