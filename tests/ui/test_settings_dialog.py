from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from qv.app.app_settings_manager import SliceNavigationDirectionMode
from qv.ui.dialogs.settings_dialog import SettingsDialog


class FakeSettingsManager:
    """Minimal settings backend for testing dialog behavior in isolation."""

    def __init__(
            self,
            *,
            drag_mode: SliceNavigationDirectionMode = (
                SliceNavigationDirectionMode.PATIENT_ORIENTATION
            ),
            wheel_mode: SliceNavigationDirectionMode = (
                SliceNavigationDirectionMode.PATIENT_ORIENTATION
            ),
    ) -> None:
        self.mpr_slice_drag_direction_mode = drag_mode
        self.mpr_wheel_slice_direction_mode = wheel_mode
        self.drag_set_calls: list[str] = []
        self.wheel_set_calls: list[str] = []

    def set_mpr_slice_drag_direction_mode(self, value: str) -> None:
        self.drag_set_calls.append(value)
        self.mpr_slice_drag_direction_mode = SliceNavigationDirectionMode(value)

    def set_mpr_wheel_slice_direction_mode(self, value: str) -> None:
        self.wheel_set_calls.append(value)
        self.mpr_wheel_slice_direction_mode = SliceNavigationDirectionMode(value)


def _button(
        dialog: SettingsDialog,
        standard_button: QtWidgets.QDialogButtonBox.StandardButton,
) -> QtWidgets.QPushButton:
    button = dialog.button_box.button(standard_button)
    assert button is not None
    return button


def test_dialog_initializes_controls_from_effective_settings(qtbot) -> None:
    settings = FakeSettingsManager(
        drag_mode=SliceNavigationDirectionMode.SLICE_INDEX,
        wheel_mode=SliceNavigationDirectionMode.PATIENT_ORIENTATION,
    )
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)

    assert dialog.tab_widget.count() == 1
    assert dialog.tab_widget.tabText(0) == "MPR"
    assert dialog.mpr_slice_drag_direction_combo.currentData() == "slice_index"
    assert (
        dialog.mpr_wheel_slice_direction_combo.currentData() == "patient_orientation"
    )


def test_apply_persists_settings_without_closing_dialog(qtbot) -> None:
    settings = FakeSettingsManager()
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.mpr_slice_drag_direction_combo.setCurrentIndex(
        dialog.mpr_slice_drag_direction_combo.findData("slice_index")
    )
    dialog.mpr_wheel_slice_direction_combo.setCurrentIndex(
        dialog.mpr_wheel_slice_direction_combo.findData("slice_index")
    )

    qtbot.mouseClick(
        _button(dialog, QtWidgets.QDialogButtonBox.StandardButton.Apply),
        QtCore.Qt.MouseButton.LeftButton,
    )

    assert settings.drag_set_calls == ["slice_index"]
    assert settings.wheel_set_calls == ["slice_index"]
    assert dialog.isVisible()


def test_cancel_discards_pending_changes(qtbot) -> None:
    settings = FakeSettingsManager()
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.mpr_slice_drag_direction_combo.setCurrentIndex(
        dialog.mpr_slice_drag_direction_combo.findData("slice_index")
    )
    dialog.mpr_wheel_slice_direction_combo.setCurrentIndex(
        dialog.mpr_wheel_slice_direction_combo.findData("slice_index")
    )

    qtbot.mouseClick(
        _button(dialog, QtWidgets.QDialogButtonBox.StandardButton.Cancel),
        QtCore.Qt.MouseButton.LeftButton,
    )

    assert settings.drag_set_calls == []
    assert settings.wheel_set_calls == []
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Rejected


def test_ok_persists_settings_and_accepts_dialog(qtbot) -> None:
    settings = FakeSettingsManager()
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.mpr_slice_drag_direction_combo.setCurrentIndex(
        dialog.mpr_slice_drag_direction_combo.findData("slice_index")
    )

    with qtbot.waitSignal(dialog.accepted, timeout=1000):
        qtbot.mouseClick(
            _button(dialog, QtWidgets.QDialogButtonBox.StandardButton.Ok),
            QtCore.Qt.MouseButton.LeftButton,
        )

    assert settings.drag_set_calls == ["slice_index"]
    assert settings.wheel_set_calls == ["patient_orientation"]
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted