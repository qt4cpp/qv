import os
import sys
from PySide6 import QtWidgets, QtCore
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk


def load_dicom_series(directory: str) -> vtk.vtkImageData:
    reader = vtk.vtkDICOMImageReader()
    reader.SetDirectoryName(directory)
    reader.Update()
    return reader.GetOutput()


class VolumeViewer(QtWidgets.QMainWindow):
    def __init__(self, dicom_dir: str | None = None, rotation_factor: float = 0.5) -> None:
        super().__init__()
        self.setWindowTitle("qv - DICOM Volume Viewer")

        self.frame = QtWidgets.QFrame()
        self.vl = QtWidgets.QVBoxLayout()
        self.vtk_widget = QVTKRenderWindowInteractor(self.frame)
        self.vl.addWidget(self.vtk_widget)
        self.frame.setLayout(self.vl)
        self.setCentralWidget(self.frame)

        self.status_label = QtWidgets.QLabel()
        self.statusBar().addPermanentWidget(self.status_label)

        self.renderer = vtk.vtkRenderer()
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()

        self.vtk_widget.installEventFilter(self)
        self._right_dragging = False
        self._left_dragging = False
        self._last_pos = QtCore.QPoint()
        self.rotation_factor = rotation_factor

        self.scalar_range: tuple[float, float] | None = None
        self.window_width: float | None = None
        self.window_level: float | None = None
        self.color_func: vtk.vtkColorTransferFunction | None = None
        self.opacity_func: vtk.vtkPiecewiseFunction | None = None

        if dicom_dir:
            self.load_volume(dicom_dir)

        self.show()
        self.interactor.Initialize()

    def update_status_label(self) -> None:
        if self.window_level is not None and self.window_width is not None:
            self.status_label.setText(
                f"Center: {self.window_level:.2f}  Range: {self.window_width:.2f}"
            )
        else:
            self.status_label.setText("")

    def load_volume(self, dicom_dir: str) -> None:
        image = load_dicom_series(dicom_dir)
        self.scalar_range = image.GetScalarRange()
        self.window_width = self.scalar_range[1] - self.scalar_range[0]
        self.window_level = sum(self.scalar_range) / 2

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
        self.vtk_widget.GetRenderWindow().Render()
        self.update_status_label()

    def update_transfer_functions(self) -> None:
        if self.color_func is None or self.opacity_func is None:
            return

        min_val = self.window_level - self.window_width / 2
        max_val = self.window_level + self.window_width / 2

        self.color_func.RemoveAllPoints()
        self.color_func.AddRGBPoint(min_val, 0.0, 0.0, 0.0)
        self.color_func.AddRGBPoint(max_val, 1.0, 1.0, 1.0)

        self.opacity_func.RemoveAllPoints()
        self.opacity_func.AddPoint(min_val, 0.0)
        self.opacity_func.AddPoint(max_val, 1.0)

        self.vtk_widget.GetRenderWindow().Render()

    def adjust_window_level(self, dx: int, dy: int) -> None:
        if self.window_width is None or self.window_level is None:
            return

        self.window_width += dx * self.window_width * 0.01
        if self.scalar_range is not None:
            max_width = self.scalar_range[1] - self.scalar_range[0]
            self.window_width = max(1.0, min(max_width, self.window_width))

        self.window_level += -dy * self.window_width * 0.01
        if self.scalar_range is not None:
            self.window_level = max(self.scalar_range[0], min(self.scalar_range[1], self.window_level))

        self.update_transfer_functions()
        self.update_status_label()

    def rotate_camera(self, dx: int, dy: int) -> None:
        camera = self.renderer.GetActiveCamera()
        camera.Azimuth((-dx * self.rotation_factor) % 360)
        camera.Elevation((dy * self.rotation_factor))
        camera.OrthogonalizeViewUp()
        self.renderer.ResetCameraClippingRange()
        self.vtk_widget.GetRenderWindow().Render()

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


def select_dicom_directory() -> str | None:
    dialog = QtWidgets.QFileDialog()
    dialog.setFileMode(QtWidgets.QFileDialog.Directory)
    if dialog.exec():
        return dialog.selectedFiles()[0]
    return None


def main():
    app = QtWidgets.QApplication(sys.argv)
    dicom_dir = sys.argv[1] if len(sys.argv) > 1 else None
    if not dicom_dir:
        dicom_dir = select_dicom_directory()
        if dicom_dir is None:
            return
    viewer = VolumeViewer(dicom_dir)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
