from __future__ import annotations

import pytest
from PySide6 import QtCore, QtWidgets

from qv.core.window_settings import WindowSettings
from qv.viewers.mpr_viewer import MprPlane
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

    def __init__(
            self,
            settings_manager=None,
            parent=None,
            *,
            plane: MprPlane = MprPlane.AXIAL,
    ) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.plane = plane
        self.received_images = []
        self.window_settings = None

    def set_image_data(self, image) -> None:
        self.received_images.append(image)

    def set_window_settings(self, settings: WindowSettings) -> None:
        self.window_settings = settings
        self.windowSettingsChanged.emit(settings)


def test_multi_viewer_panel_builds_fixed_four_view_layout(
        monkeypatch: pytest.MonkeyPatch,
        qtbot,
) -> None:
    """
    Phase 1 should build one VR pane plus three fixed-plane MPR panes.
    """
    monkeypatch.setattr(multi_viewer_panel_module, "VolumeViewer", FakeVolumeViewer)
    monkeypatch.setattr(multi_viewer_panel_module, "MprViewer", FakeMprViewer)

    panel = multi_viewer_panel_module.MultiViewerPanel(settings_mgr=object())
    qtbot.addWidget(panel)

    assert panel.layout_mode == multi_viewer_panel_module.ViewerLayoutMode.QUAD

    assert panel.top_splitter.count() == 2
    assert panel.bottom_splitter.count() == 2

    assert panel.top_splitter.widget(0) is panel.volume_viewer
    assert panel.top_splitter.widget(1) is panel.mpr_axial_viewer
    assert panel.bottom_splitter.widget(0) is panel.mpr_coronal_viewer
    assert panel.bottom_splitter.widget(1) is panel.mpr_sagittal_viewer

    assert panel.mpr_axial_viewer.plane == MprPlane.AXIAL
    assert panel.mpr_coronal_viewer.plane == MprPlane.CORONAL
    assert panel.mpr_sagittal_viewer.plane == MprPlane.SAGITTAL

    assert panel.mpr_viewer is panel.mpr_axial_viewer
    assert set(panel.mpr_viewers) == {
        MprPlane.AXIAL,
        MprPlane.CORONAL,
        MprPlane.SAGITTAL,
    }


def test_multi_viewer_panel_loaded_volume_image_to_all_mpr_viewers(
        monkeypatch: pytest.MonkeyPatch,
        qtbot,
) -> None:
    """
    Volume load should seed all three MPR viewers with the shared image data.
    """
    monkeypatch.setattr(multi_viewer_panel_module, "VolumeViewer", FakeVolumeViewer)
    monkeypatch.setattr(multi_viewer_panel_module, "MprViewer", FakeMprViewer)

    panel = multi_viewer_panel_module.MultiViewerPanel(settings_mgr=object())
    qtbot.addWidget(panel)

    image = object()
    panel.volume_viewer.set_source_image(image)

    with qtbot.waitSignal(panel.volume_viewer.dataLoaded, timeout=1000):
        panel.volume_viewer.dataLoaded.emit()

    assert panel.mpr_axial_viewer.received_images == [image]
    assert panel.mpr_coronal_viewer.received_images == [image]
    assert panel.mpr_sagittal_viewer.received_images == [image]


def test_multi_viewer_panel_keeps_all_window_settings_independent(
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
    axial_settings = WindowSettings(level=30.0, width=40.0)
    coronal_settings = WindowSettings(level=50.0, width=60.0)
    sagittal_settings = WindowSettings(level=70.0, width=80.0)

    panel.volume_viewer.set_window_settings(volume_settings)
    panel.mpr_axial_viewer.set_window_settings(axial_settings)
    panel.mpr_coronal_viewer.set_window_settings(coronal_settings)
    panel.mpr_sagittal_viewer.set_window_settings(sagittal_settings)

    next_volume_settings = WindowSettings(level=99.0, width=100.0)
    panel.volume_viewer.set_window_settings(next_volume_settings)

    assert panel.mpr_axial_viewer.window_settings == axial_settings
    assert panel.mpr_coronal_viewer.window_settings == coronal_settings
    assert panel.mpr_sagittal_viewer.window_settings == sagittal_settings

    next_coronal_settings = WindowSettings(level=110.0, width=120.0)
    panel.mpr_coronal_viewer.set_window_settings(next_coronal_settings)

    assert panel.volume_viewer.window_settings == next_volume_settings
    assert panel.mpr_axial_viewer.window_settings == axial_settings
    assert panel.mpr_sagittal_viewer.window_settings == sagittal_settings
