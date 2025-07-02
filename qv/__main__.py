import copy
import math
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSplitter
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.util.numpy_support import vtk_to_numpy
import vtk

from qv.histgram import show_histgram_window, HistogramPlotWidget
from qv.status import STATUS_FIELDS, StatusField
import qv.utils.vtk_helpers as vtk_helpers


class VolumeViewer(QtWidgets.QMainWindow):
    def __init__(self, dicom_dir: str | None = None, rotation_factor: float = 0.5) -> None:
        super().__init__()
        self.setWindowTitle("qv - DICOM Volume Viewer")

        self.frame = QtWidgets.QFrame()
        self.splitter = QSplitter(Qt.Vertical)
        self.vtk_widget = QVTKRenderWindowInteractor(self.frame)
        self.splitter.addWidget(self.vtk_widget)
        self.hist_window = HistogramPlotWidget()
        self.splitter.addWidget(self.hist_window)
        self.vl = QtWidgets.QVBoxLayout()
        self.vl.addWidget(self.splitter)
        self.frame.setLayout(self.vl)
        self.setCentralWidget(self.frame)

        self.renderer = vtk.vtkRenderer()
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()

        self.vtk_widget.installEventFilter(self)
        self._right_dragging = False
        self._left_dragging = False
        self._last_pos = QtCore.QPoint()
        self.rotation_factor = rotation_factor

        # インスタンス毎にステータスを保持できるようにディープコピーをする。
        self.status_fields: dict[str, StatusField] = {
            k: copy.deepcopy(v) for k, v in STATUS_FIELDS.items()
        }
        # ステータス毎にラベルを設定する
        self._status_label = {}
        for key, field in self.status_fields.items():
            if not field.visible:
                self._status_label[key] = None
                continue
            label = QLabel("", self)
            self.statusBar().addPermanentWidget(label)
            self._status_label[key] = label

        self.delta_per_pixel = 1

        self.scalar_range: tuple[float, float] | None = None
        self.color_func: vtk.vtkColorTransferFunction | None = None
        self.opacity_func: vtk.vtkPiecewiseFunction | None = None

        if dicom_dir:
            self.load_volume(dicom_dir)

        self.show()
        self.interactor.Initialize()

    def update_status(self, **kwargs):
        """Update the status fields with the given keyword arguments and
         refresh the labels."""
        for key, value in kwargs.items():
            field = self.status_fields.get(key)
            if field is not None:
                self.status_fields[key].value = value

    def _refresh_status_label(self, key: str) -> None:
        """Refresh the status label for the given key."""
        if self._status_label[key] is None:
            return
        value = self.status_fields[key].value
        self._status_label[key].setText(self.status_fields[key].formatter(value))

    def load_volume(self, dicom_dir: str) -> None:
        image = vtk_helpers.load_dicom_series(dicom_dir)
        self.scalar_range = image.GetScalarRange()
        self.window_level = round(min(4096.0, sum(self.scalar_range) / 2.0))
        self.window_width = round(min(self.window_level / 2.0, 1024.0))
        self.azimuth, self.elevation = vtk_helpers.get_camera_angles(self.renderer.GetActiveCamera())
        volume_array = vtk_to_numpy(image.GetPointData().GetScalars())
        # self.hist_window = show_histgram_window(volume_array)
        self.hist_window.set_data(volume_array)

        mapper = vtk.vtkGPUVolumeRayCastMapper()
        mapper.SetInputData(image)

        self.color_func = vtk.vtkColorTransferFunction()
        self.opacity_func = vtk.vtkPiecewiseFunction()

        self.volume_property = vtk.vtkVolumeProperty()
        self.volume_property.SetColor(self.color_func)
        self.volume_property.SetScalarOpacity(self.opacity_func)
        self.volume_property.ShadeOn()
        self.volume_property.SetInterpolationTypeToLinear()

        self.volume = vtk.vtkVolume()
        self.volume.SetMapper(mapper)
        self.volume.SetProperty(self.volume_property)

        self.renderer.AddVolume(self.volume)
        self.renderer.ResetCamera()
        self.update_transfer_functions()
        # self.test_AddRGBPoint()
        self.vtk_widget.GetRenderWindow().Render()

        # self.hist_window.set_viewing_range(self.window_level-self.window_width / 2,
        #                                    self.window_level+self.window_width / 2)
        self.hist_window.update_viewing_graph(self.volume_property.GetScalarOpacity())

    def test_AddRGBPoint(self) -> None:
        self.color_func.AddRGBPoint(0, 0.0, 0.0, 0.0)
        self.color_func.AddRGBPoint(500, 1.0, 0.5, 0.3)
        self.color_func.AddRGBPoint(1200, 1.0, 0.5, 0.3)
        self.color_func.AddRGBPoint(1350, 1.0, 1.0, 0.9)

        self.vtk_widget.GetRenderWindow().Render()

    def update_transfer_functions(self) -> None:
        if self.color_func is None or self.opacity_func is None:
            return

        min_val = self.window_level - self.window_width / 2
        max_val = self.window_level + self.window_width / 2

        self.color_func.RemoveAllPoints()
        self.color_func.AddRGBPoint(min_val, 0.0, 0.0, 0.0)
        # self.color_func.AddRGBPoint(self.window_level, 1.0, 1.0, 1.0)
        self.color_func.AddRGBPoint(max_val, 1.0, 1.0, 1.0)

        self.opacity_func.RemoveAllPoints()
        self.opacity_func.AddPoint(min_val, 0.0)
        self.opacity_func.AddPoint(max_val, 1.0)

        self.vtk_widget.GetRenderWindow().Render()

    def update_histgram_window(self) -> None:
        if self.hist_window is None:
            return

        pwf = self.volume_property.GetScalarOpacity()
        self.hist_window.update_viewing_graph(pwf)

    def adjust_window_level(self, dx: int, dy: int) -> None:
        if self.window_width is None or self.window_level is None:
            return

        self.window_width += dx * self.delta_per_pixel
        if self.scalar_range is not None:
            max_width = self.scalar_range[1] - self.scalar_range[0]
            self.window_width = max(1.0, min(max_width, self.window_width))

        self.window_level += -dy * self.delta_per_pixel
        if self.scalar_range is not None:
            self.window_level = max(self.scalar_range[0], min(self.scalar_range[1], self.window_level))

        self.update_transfer_functions()
        self.update_histgram_window()

    def rotate_camera(self, dx: int, dy: int) -> None:
        camera = self.renderer.GetActiveCamera()
        camera.Azimuth((-dx * self.rotation_factor) % 360)
        camera.Elevation((dy * self.rotation_factor))
        camera.OrthogonalizeViewUp()
        self.renderer.ResetCameraClippingRange()
        self.vtk_widget.GetRenderWindow().Render()
        self.azimuth, self.elevation = vtk_helpers.get_camera_angles(camera)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.vtk_widget:
            if event.type() == QtCore.QEvent.MouseButtonPress:
                if event.button() == QtCore.Qt.RightButton:
                    self._right_dragging = True
                    self._last_pos = event.pos()
                    return True
                if event.button() == QtCore.Qt.LeftButton:
                    self._left_dragging = True
                    self._last_pos = event.pos()
                    return True
            if event.type() == QtCore.QEvent.MouseMove:
                if self._right_dragging:
                    pos = event.pos()
                    dx = pos.x() - self._last_pos.x()
                    dy = pos.y() - self._last_pos.y()
                    self._last_pos = pos
                    self.adjust_window_level(dx, dy)
                    return True
                if self._left_dragging:
                    pos = event.pos()
                    dx = pos.x() - self._last_pos.x()
                    dy = pos.y() - self._last_pos.y()
                    self._last_pos = pos
                    self.rotate_camera(dx, dy)
                    return True
            if event.type() == QtCore.QEvent.MouseButtonRelease:
                if event.button() == QtCore.Qt.RightButton:
                    self._right_dragging = False
                    return True
                if event.button() == QtCore.Qt.LeftButton:
                    self._left_dragging = False
                    return True
        return super().eventFilter(obj, event)

    @property
    def azimuth(self) -> float:
        return self.status_fields["azimuth"].value

    @azimuth.setter
    def azimuth(self, value: float):
        self.status_fields["azimuth"].value = value
        self._refresh_status_label("azimuth")

    @property
    def elevation(self) -> float:
        return self.status_fields["elevation"].value

    @elevation.setter
    def elevation(self, value: float):
        self.status_fields["elevation"].value = value
        self._refresh_status_label("elevation")

    @property
    def window_width(self) -> float:
        return self.status_fields["window_width"].value

    @window_width.setter
    def window_width(self, value: float):
        self.status_fields["window_width"].value = value
        self._refresh_status_label("window_width")

    @property
    def window_level(self) -> float:
        return self.status_fields["window_level"].value

    @window_level.setter
    def window_level(self, value: float):
        self.status_fields["window_level"].value = value
        self._refresh_status_label("window_level")

    @property
    def delta_per_pixel(self) -> int:
        return self.status_fields["delta_per_pixel"].value

    @delta_per_pixel.setter
    def delta_per_pixel(self, value: int):
        self.status_fields["delta_per_pixel"].value = value


def main():
    # 既存の QApplication インスタンスを取得。なければ新規作成。
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    # DICOM ディレクトリの取得
    dicom_dir = sys.argv[1] if len(sys.argv) > 1 else None
    if not dicom_dir:
        dicom_dir = vtk_helpers.select_dicom_directory()
        if dicom_dir is None:
            return

    # ビューアーを起動
    viewer = VolumeViewer(dicom_dir)

    # アプリケーションを実行（正常終了でプロセス終了）
    sys.exit(app.exec())


if __name__ == "__main__":
    main()