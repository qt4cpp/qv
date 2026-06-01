from __future__ import annotations

import logging

from PySide6 import QtWidgets

from qv.app.app_settings_manager import (
    AppSettingsManager,
    SliceNavigationDirectionMode,
)


logger = logging.getLogger(__name__)


_DRECTION_MODE_OPTIONS = (
("Match patinet orientation", SliceNavigationDirectionMode.PATIENT_ORIENTATION),
("Follow slice number order", SliceNavigationDirectionMode.SLICE_INDEX),
)


class SettingsDialog(QtWidgets.QDialog):
    """
    Application settings dialog.

    Settings are written only when Apply or OK is pressed. Editing a widget
    does not mutate AppSettingsManager, so Cancel can discard pending changes.
    """

    def __init__(
            self,
            settings_manager: AppSettingsManager,
            parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings_manager = settings_manager

        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(520, 240)

        self._setup_ui()
        self._load_effective_settings()

    def _setup_ui(self) -> None:
        root_layout = QtWidgets.QVBoxLayout(self)

        self.tab_widget = QtWidgets.QTabWidget(self)
        root_layout.addWidget(self.tab_widget)

        self._build_mpr_tab()

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok
            | QtWidgets.QDialogButtonBox.Apply
            | QtWidgets.QDialogButtonBox.Cancel,
            parent=self,
        )
        root_layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

        apply_button = self.button_box.button(
            QtWidgets.QDialogButtonBox.StandardButton.Apply
        )
        apply_button.clicked.connect(self.apply_settings)

    def _build_mpr_tab(self) -> None:
        """Create controls for MPR slice-navigation behavior."""
        tab = QtWidgets.QWidget(self.tab_widget)
        form_layout = QtWidgets.QFormLayout(tab)

        self.mpr_slice_drag_direction_combo = self._create_direction_combo(tab)
        self.mpr_wheel_slice_direction_combo = self._create_direction_combo(tab)

        form_layout.addRow("Slice drag direction:", self.mpr_slice_drag_direction_combo)
        form_layout.addRow("Wheel slice direction:", self.mpr_wheel_slice_direction_combo)

        self.tab_widget.addTab(tab, "MPR")

    def _create_direction_combo(self, parent: QtWidgets.QWidget) -> QtWidgets.QComboBox:
        """Create a combo box for selecting direction options."""
        combo = QtWidgets.QComboBox(parent)
        for label, mode in _DRECTION_MODE_OPTIONS:
            combo.addItem(label, mode.value)
        return combo

    def _load_effective_settings(self) -> None:
        """Populate controls from the current effective settings."""
        self._select_combo_value(
            self.mpr_slice_drag_direction_combo,
            self._settings_manager.mpr_slice_drag_direction_mode.value,
        )
        self._select_combo_value(
            self.mpr_wheel_slice_direction_combo,
            self._settings_manager.mpr_wheel_slice_direction_mode.value,
        )

    def _select_combo_value(
            self,
            combo: QtWidgets.QComboBox,
            value: str,
    ) -> None:
        """Select an item by its stable internal value."""
        index = combo.findData(value)
        if index < 0:
            logger.warning("Unsupported settings value ignored: %s", value)
            return
        combo.setCurrentIndex(index)

    def apply_settings(self) -> None:
        """Persist the values currently selected in the dialog."""
        drag_mode = self.mpr_slice_drag_direction_combo.currentData()
        wheel_mode = self.mpr_wheel_slice_direction_combo.currentData()

        self._settings_manager.set_mpr_slice_drag_direction_mode(drag_mode)
        self._settings_manager.set_mpr_wheel_slice_direction_mode(wheel_mode)

        logger.info(
            "MPR settings applied: slice_drag_direction_mode=%s, "
            "wheel_slice_direction_mode=%s",
            drag_mode,
            wheel_mode,
        )

    def _on_accept(self) -> None:
        """Apply pending changes and close the dialog."""
        self.apply_settings()
        self.accept()
