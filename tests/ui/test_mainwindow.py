from __future__ import annotations

import pytest
from PySide6 import QtWidgets

import qv.ui.mainwindow as mainwindow_module


class FakeShortcutManager:
    def __init__(self, parent, config_path, settings_manager) -> None:
        pass


class FakeHistory:
    def can_undo(self) -> bool:
        return False

    def can_redo(self) -> bool:
        return False


class FakeVolumeViewer:
    current_profile_name = "balanced"

    def __init__(self) -> None:
        self.history = FakeHistory()

    def __getattr__(self, name):
        """Return no-op callbacks required while menu actions are constructed."""
        return lambda *args, **kwargs: None


class FakeMultiViewerPanel:
    layout_mode = mainwindow_module.ViewerLayoutMode.QUAD

    def set_layout_mode(self, mode) -> None:
        self.layout_mode = mode


class FakeSettingsDialog:
    instances: list["FakeSettingsDialog"] = []

    def __init__(self, settings_manager, parent=None) -> None:
        self.settings_manager = settings_manager
        self.parent = parent
        self.exec_calls = 0
        FakeSettingsDialog.instances.append(self)

    def exec(self) -> int:
        self.exec_calls += 1
        return QtWidgets.QDialog.DialogCode.Rejected


def _setup_fake_ui(window) -> None:
    window.volume_viewer = FakeVolumeViewer()
    window.mpr_viewer = object()
    window.multi_viewer_panel = FakeMultiViewerPanel()


def test_preference_action_opens_settings_dialog_with_shared_manager(
        monkeypatch: pytest.MonkeyPatch,
        qtbot,
) -> None:
    FakeSettingsDialog.instances.clear()

    monkeypatch.setattr(mainwindow_module, "ShortcutManager", FakeShortcutManager)
    monkeypatch.setattr(mainwindow_module, "SettingsDialog", FakeSettingsDialog)
    monkeypatch.setattr(mainwindow_module.MainWindow, "_setup_ui", _setup_fake_ui)
    monkeypatch.setattr(mainwindow_module.MainWindow,
                        "_setup_status_bar",
                        lambda self: None,
                        )
    monkeypatch.setattr(mainwindow_module.MainWindow,
                        "_register_shortcuts",
                        lambda self: None,
                        )

    settings_manager = object()
    window = mainwindow_module.MainWindow(settings_mgr=settings_manager)
    qtbot.addWidget(window)

    assert window.settings_action.text() == "&Preferences..."

    window.settings_action.trigger()

    assert len(FakeSettingsDialog.instances) == 1
    dialog = FakeSettingsDialog.instances[0]
    assert dialog.settings_manager is settings_manager
    assert dialog.parent is window
    assert dialog.exec_calls == 1
