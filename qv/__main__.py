import os
import sys
from PySide6 import QtWidgets
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk


def load_dicom_series(directory: str) -> vtk.vtkImageData:
    reader = vtk.vtkDICOMImageReader()
    reader.SetDirectoryName(directory)
    reader.Update()
    return reader.GetOutput()


class VolumeViewer(QtWidgets.QMainWindow):
    def __init__(self, dicom_dir: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("qv - DICOM Volume Viewer")

        self.frame = QtWidgets.QFrame()
        self.vl = QtWidgets.QVBoxLayout()
        self.vtk_widget = QVTKRenderWindowInteractor(self.frame)
        self.vl.addWidget(self.vtk_widget)
        self.frame.setLayout(self.vl)
        self.setCentralWidget(self.frame)

        self.renderer = vtk.vtkRenderer()
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()

        if dicom_dir:
            self.load_volume(dicom_dir)

        self.show()
        self.interactor.Initialize()

    def load_volume(self, dicom_dir: str) -> None:
        image = load_dicom_series(dicom_dir)
        mapper = vtk.vtkGPUVolumeRayCastMapper()
        mapper.SetInputData(image)

        color_func = vtk.vtkColorTransferFunction()
        color_func.AddRGBPoint(0, 0.0, 0.0, 0.0)
        color_func.AddRGBPoint(500, 1.0, 0.5, 0.3)
        color_func.AddRGBPoint(1000, 1.0, 0.5, 0.3)
        color_func.AddRGBPoint(1150, 1.0, 1.0, 0.9)

        opacity_func = vtk.vtkPiecewiseFunction()
        opacity_func.AddPoint(0, 0.00)
        opacity_func.AddPoint(500, 0.15)
        opacity_func.AddPoint(1000, 0.15)
        opacity_func.AddPoint(1150, 0.85)

        volume_property = vtk.vtkVolumeProperty()
        volume_property.SetColor(color_func)
        volume_property.SetScalarOpacity(opacity_func)
        volume_property.ShadeOn()
        volume_property.SetInterpolationTypeToLinear()

        volume = vtk.vtkVolume()
        volume.SetMapper(mapper)
        volume.SetProperty(volume_property)

        self.renderer.AddVolume(volume)
        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()


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
