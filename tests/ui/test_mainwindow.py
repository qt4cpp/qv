from __future__ import annotations
from types import SimpleNamespace

import pytest
from PySide6 import QtWidgets


import qv.ui.mainwindow as mainwindow_module


class FakeShortcutManager:
    def __init__(self, parent, config_path, settings_manager) -> None:
        self.callbacks: dict[str, object] = {}

    def add_callback(self, name: str, callback: object) -> None:
        self.callbacks[name] = callback


class FakeHistory:
    def can_undo(self) -> bool:
        return False

    def can_redo(self) -> bool:
        return False


class FakeVolumeViewer:
    current_profile_name = "balanced"
    current_transfer_function_preset_name = "default_linear"

    def __init__(self) -> None:
        self.history = FakeHistory()
        self.selected_transfer_function_presets: list[str] = []

    def set_transfer_function_preset(self, name: str) -> None:
        self.selected_transfer_function_presets.append(name)
        self.current_transfer_function_preset_name = name

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


def _fake_transfer_function_presets():
    """Return minimal preset-like objects for MainWindow menu tests."""
    return (
        SimpleNamespace(
            name="default_linear",
            display_name="Default Linear",
        ),
        SimpleNamespace(
            name="ct_head_brain",
            display_name="CT Head Brain",
        ),
        SimpleNamespace(
            name="ct_abdomen_soft_tissue",
            display_name="CT Abdomen Soft Tissue",
        ),
    )


def _create_menu_only_mainwindow(
        monkeypatch: pytest.MonkeyPatch,
        qtbot,
        settings_manager=object(),
):
    """Create MainWindow with real menus and fake viewer widgets."""
    monkeypatch.setattr(mainwindow_module, "ShortcutManager", FakeShortcutManager)
    monkeypatch.setattr(mainwindow_module, "SettingsDialog", FakeSettingsDialog)
    monkeypatch.setattr(mainwindow_module.MainWindow, "_setup_ui", _setup_fake_ui)
    monkeypatch.setattr(
        mainwindow_module.MainWindow,
        "_setup_status_bar",
        lambda self: None,
    )
    monkeypatch.setattr(
        mainwindow_module,
        "list_transfer_function_presets",
        _fake_transfer_function_presets,
    )

    window = mainwindow_module.MainWindow(settings_mgr=settings_manager)
    qtbot.addWidget(window)
    return window


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


def test_transfer_function_menu_exposes_preset_display_names(
        monkeypatch: pytest.MonkeyPatch,
        qtbot,
) -> None:
    """Transfer function menu should show preset display names."""
    window = _create_menu_only_mainwindow(monkeypatch, qtbot)

    actions = window._transfer_function_preset_actions

    assert actions["default_linear"].text() == "Default Linear"
    assert actions["ct_head_brain"].text() == "CT Head Brain"
    assert actions["ct_abdomen_soft_tissue"].text() == "CT Abdomen Soft Tissue"
    assert actions["default_linear"].isChecked()


def test_transfer_function_menu_applies_selected_preset(
        monkeypatch: pytest.MonkeyPatch,
        qtbot,
) -> None:
    """Selecting a transfer function action should update the volume viewer."""
    window = _create_menu_only_mainwindow(monkeypatch, qtbot)

    window._transfer_function_preset_actions["ct_head_brain"].trigger()

    assert window.volume_viewer.selected_transfer_function_presets == [
        "ct_head_brain",
    ]
    assert window.volume_viewer.current_transfer_function_preset_name == "ct_head_brain"
    assert window._transfer_function_preset_actions["ct_head_brain"].isChecked()
