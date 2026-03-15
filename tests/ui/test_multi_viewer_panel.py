from __future__ import annotations

import pytest
from PySide6 import QtCore, QtWidgets

from qv.core.window_settings import WindowSettings
import qv.ui.widgets.multi_viewer_panel as multi_viewer_panel_module


class FakeVolumeViewer(QtWidgets.QWidget):
    dataLoaded = QtCore.Signal()
    windowSettingsChanged = QtCore.Signal(object)

    def __init__(self, settings_manager=None, parent=None) -> None:
        super().__init__(parent)
        self._settings_manager = settings_manager
        self._source_image = None
        self.window_settings = None

    @property
    def source_image(self):
        return self._source_image

    def set_source_image(self, image) -> None:
        self._source_image = image

    def set_window_settings(self, settings: WindowSettings) -> None:
        self.window_settings = settings
        self.windowSettingsChanged.emit(settings)


class FakeMprViewer(QtWidgets.QWidget):
    windowSettingsChanged = QtCore.Signal(object)

    def __init__(self, settings_manager=None, parent=None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.received_images = []
        self.window_settings = None

    def set_image_data(self, image) -> None:
        self.received_images.append(image)

    def set_window_settings(self, settings: WindowSettings) -> None:
        self.window_settings = settings
        self.windowSettingsChanged.emit(settings)


def test_multi_viewer_panel_loaded_volume_image_to_mpr(
        monkeypatch: pytest.MonkeyPatch,
        qtbot,
) -> None:
    """
    Volume load should still seed the MPR viewer with the shared image data.
    """
    monkeypatch.setattr(multi_viewer_panel_module, "VolumeViewer", FakeVolumeViewer)
    monkeypatch.setattr(multi_viewer_panel_module, "MprViewer", FakeMprViewer)

    panel = multi_viewer_panel_module.MultiViewerPanel(settings_mgr=object())
    qtbot.addWidget(panel)

    image = object()
    panel.volume_viewer.set_source_image(image)

    with qtbot.waitSignal(panel.volume_viewer.dataLoaded, timeout=1000):
        panel.volume_viewer.dataLoaded.emit()

    assert panel.mpr_viewer.received_images == [image]


def test_multi_viewer_panel_keeps_volume_and_mpr_window_settings_independent(
        monkeypatch: pytest.MonkeyPatch,
        qtbot,
) -> None:
    """
    VR and MPR WW/WL should remain independent.

    This guards against accidentally wiring windowSettingsChanged between the
    two viewers in either direction.
    """
    monkeypatch.setattr(multi_viewer_panel_module, "VolumeViewer", FakeVolumeViewer)
    monkeypatch.setattr(multi_viewer_panel_module, "MprViewer", FakeMprViewer)

    panel = multi_viewer_panel_module.MultiViewerPanel(settings_mgr=object())
    qtbot.addWidget(panel)

    volume_settings = WindowSettings(level=10.0, width=20.0)
    mpr_settings = WindowSettings(level=30.0, width=40.0)
    next_volume_settings = WindowSettings(level=50.0, width=60.0)
    next_mpr_settings = WindowSettings(level=70.0, width=80.0)

    panel.volume_viewer.set_window_settings(volume_settings)
    panel.mpr_viewer.set_window_settings(mpr_settings)

    panel.volume_viewer.set_window_settings(next_volume_settings)
    assert panel.mpr_viewer.window_settings == mpr_settings

    panel.mpr_viewer.set_window_settings(next_mpr_settings)
    assert panel.volume_viewer.window_settings == next_volume_settings
