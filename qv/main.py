import copy
import sys
import math
from pathlib import Path

import vtk
from PySide6 import QtWidgets, QtCore
from vtkmodules.util.numpy_support import vtk_to_numpy

import qv.utils.vtk_helpers as vtk_helpers
from qv.status import STATUS_FIELDS, StatusField
from shortcut_manager import ShortcutManager
from ui_mainwindow import Ui_MainWindow
from vtk_helpers import return_dicom_dir


class VolumeViewer(QtWidgets.QMainWindow):
    statusChanged = QtCore.Signal(str, str)

    def __init__(self, dicom_dir: str | None = None, rotation_factor: float = 0.5) -> None:
        super().__init__()
        config_path = Path(__file__).parent.parent / "settings"
        self.shortcut_mgr = ShortcutManager(parent=self, config_path=config_path)
        self.register_command()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        w = self.ui.vtk_widget
        w.installEventFilter(self)
        self.renderer = vtk.vtkRenderer()
        w.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = w.GetRenderWindow().GetInteractor()

        self._right_dragging = False
        self._left_dragging = False
        self._last_pos = QtCore.QPoint()
        self.rotation_factor = rotation_factor

        # インスタンス毎にステータスを保持できるようにディープコピーをする。
        self.status_fields: dict[str, StatusField] = {
            k: copy.deepcopy(v) for k, v in STATUS_FIELDS.items()
        }
        self.ui.setup_status(self, **self.status_fields)
        self.statusChanged.connect(self.ui._refresh_status_label)

        self.delta_per_pixel = 1

        self.volume: vtk.vtkVolume | None = None
        self.volume_property: vtk.vtkVolumeProperty | None = None
        self.scalar_range: tuple[float, float] | None = None
        self.color_func: vtk.vtkColorTransferFunction | None = None
        self.opacity_func: vtk.vtkPiecewiseFunction | None = None

        if dicom_dir:
            self.load_volume(dicom_dir)

        self.show()
        self.interactor.Initialize()

    def register_command(self):
        self.shortcut_mgr.add_callback("front_view", self.front_view)

    def update_status(self, **kwargs):
        """Update the status fields with the given keyword arguments and
         refresh the labels."""
        for key, value in kwargs.items():
            field = self.status_fields.get(key)
            if field is not None:
                self.status_fields[key].value = value

    def open_menu(self):
        dicom_dir = vtk_helpers.select_dicom_directory()
        if dicom_dir is None:
            return
        self.load_volume(dicom_dir)

    def load_volume(self, dicom_dir: str) -> None:
        image = vtk_helpers.load_dicom_series(dicom_dir)
        self.scalar_range = image.GetScalarRange()
        self.window_level = round(min(4096.0, sum(self.scalar_range) / 2.0))
        self.window_width = round(min(self.window_level / 2.0, 1024.0))
        self.azimuth, self.elevation = vtk_helpers.get_camera_angles(self.renderer.GetActiveCamera())
        volume_array = vtk_to_numpy(image.GetPointData().GetScalars())
        # self.ui.histgram_widget = show_histgram_window(volume_array)
        self.ui.histgram_widget.set_data(volume_array)

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
        camera = vtk.vtkCamera()
        camera.SetClippingRange(0.001, 100)
        camera.SetFocalPoint(0, 0, 0)
        self.apply_camera_angle()
        self.renderer.SetActiveCamera(camera)

        self.renderer.ResetCamera()
        self.update_transfer_functions()
        # self.test_AddRGBPoint()
        self.ui.vtk_widget.GetRenderWindow().Render()

        # self.ui.histgram_widget.set_viewing_range(self.window_level-self.window_width / 2,
        #                                    self.window_level+self.window_width / 2)
        self.ui.histgram_widget.update_viewing_graph(self.volume_property.GetScalarOpacity())

    def test_AddRGBPoint(self) -> None:
        self.color_func.AddRGBPoint(0, 0.0, 0.0, 0.0)
        self.color_func.AddRGBPoint(500, 1.0, 0.5, 0.3)
        self.color_func.AddRGBPoint(1200, 1.0, 0.5, 0.3)
        self.color_func.AddRGBPoint(1350, 1.0, 1.0, 0.9)

        self.ui.vtk_widget.GetRenderWindow().Render()

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

        self.ui.vtk_widget.GetRenderWindow().Render()

    def update_histgram_window(self) -> None:
        if self.ui.histgram_widget is None:
            return

        pwf = self.volume_property.GetScalarOpacity()
        self.ui.histgram_widget.update_viewing_graph(pwf)

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
        self.ui.vtk_widget.GetRenderWindow().Render()
        self.azimuth, self.elevation = vtk_helpers.get_camera_angles(camera)

    def apply_camera_angle(self):
        azimuth, elevation = 0, 90
        camera = self.renderer.GetActiveCamera()
        camera.Azimuth(azimuth)
        camera.Elevation(elevation)
        # camera.SetPosition(0, 0, 1)

        camera.OrthogonalizeViewUp()
        self.renderer.SetActiveCamera(camera)
        self.renderer.ResetCameraClippingRange()
        self.ui.vtk_widget.GetRenderWindow().Render()
        self.azimuth, self.elevation = vtk_helpers.get_camera_angles(
            self.renderer.GetActiveCamera()
        )

    def set_camera_view(self, view: str) -> None:
        """
        Set the camera to a preset view angle.
        Valid view values: 'front', 'back', 'left', 'right', 'top', 'bottom'.
        """


        # Preset directions for each view (unit sphere)
        directions = {
            'front':  (0.0, 1.0, 0.0),
            'back':   (0.0, -1.0, 0.0),
            'left':   (-1.0, 0.0, 0.0),
            'right':  (1.0, 0.0, 0.0),
            'top':    (0.0, 0.0, 1.0),
            'bottom': (0.0, 0.0, -1.0),
        }
        # Up vectors to keep orientation
        viewups = {
            'front':  (0.0, 0.0, 1.0),
            'back':   (0.0, 0.0, 1.0),
            'left':   (0.0, 0.0, 1.0),
            'right':  (0.0, 0.0, 1.0),
            'top':    (0.0, 1.0, 0.0),
            'bottom': (0.0, 1.0, 0.0),
        }
        key = view.lower()
        if key not in directions:
            return

        camera = self.renderer.GetActiveCamera()
        fp = camera.GetFocalPoint()
        pos = camera.GetPosition()
        distance = vtk_helpers.calculate_norm(vtk_helpers.direction_vector(fp, pos))
        unit_new = directions[key]

        new_pos = [fp[i] + unit_new[i] * distance for i in range(3)]
        camera.SetPosition(*new_pos)
        camera.SetViewUp(*viewups[key])
        # Apply position and orientation
        self.renderer.ResetCameraClippingRange()
        # Update internal azimuth/elevation status
        self.ui.vtk_widget.GetRenderWindow().Render()
        self.azimuth, self.elevation = vtk_helpers.get_camera_angles(camera)

    def front_view(self):
        self.set_camera_view('front')

    def back_view(self):
        self.set_camera_view('back')

    def left_view(self):
        self.set_camera_view('left')

    def right_view(self):
        self.set_camera_view('right')

    def top_view(self):
        self.set_camera_view('top')

    def bottom_view(self):
        self.set_camera_view('bottom')

    def get_volume_center(self) -> tuple[float, float, float]:
        bounds = self.volume.GetBounds()  # (xmin,xmax, ymin,ymax, zmin,zmax)
        center = (
            0.5 * (bounds[0] + bounds[1]),
            0.5 * (bounds[2] + bounds[3]),
            0.5 * (bounds[4] + bounds[5]),
        )
        return center

    def get_default_distance(self) -> float:
        """
        Compute the default distance from the camera to the volume center.
        :return: distance
        """
        if self.volume is None:
            raise RuntimeError("Volume not loaded")
        bounds = self.volume.GetBounds()
        max_dim = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])
        return 2.0 * max_dim

    def reset_center(self):
        """Reset the camera to the volume center."""
        center = self.get_volume_center()
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(*center)

    def reset_zoom(self):
        """Reset the camera distance to the default value."""
        self.set_zoom_factor(1.0)

    def set_zoom_factor(self, factor: float):
        camera = self.renderer.GetActiveCamera()
        fp = camera.GetFocalPoint()
        pos = camera.GetPosition()

        dir_vec = vtk_helpers.direction_vector(fp, pos)
        norm = vtk_helpers.calculate_norm(dir_vec)
        if norm == 0:
            return
        unit_dir = [d / norm for d in dir_vec]
        new_dist = self.get_default_distance() / factor

        new_pos = [fp[i] + unit_dir[i] * new_dist for i in range(3)]
        camera.SetPosition(*new_pos)
        self.renderer.ResetCameraClippingRange()
        self.ui.vtk_widget.GetRenderWindow().Render()
        self.azimuth, self.elevation = vtk_helpers.get_camera_angles(camera)

    def set_zoom_2x(self):
        self.set_zoom_factor(2.0)

    def set_zoom_half(self):
        self.set_zoom_factor(0.5)

    def reset_camera(self):
        """Reset the camera to the default position."""
        self.renderer.ResetCamera()
        self.apply_camera_angle()
        self.ui.vtk_widget.GetRenderWindow().Render()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.ui.vtk_widget:
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
        text = self.status_fields["azimuth"].formatter(value)
        self.statusChanged.emit("azimuth", text)

    @property
    def elevation(self) -> float:
        return self.status_fields["elevation"].value

    @elevation.setter
    def elevation(self, value: float):
        self.status_fields["elevation"].value = value
        text = self.status_fields["elevation"].formatter(value)
        self.statusChanged.emit("elevation", text)

    @property
    def window_width(self) -> float:
        return self.status_fields["window_width"].value

    @window_width.setter
    def window_width(self, value: float):
        self.status_fields["window_width"].value = value
        text = self.status_fields["window_width"].formatter(value)
        self.statusChanged.emit("window_width", text)

    @property
    def window_level(self) -> float:
        return self.status_fields["window_level"].value

    @window_level.setter
    def window_level(self, value: float):
        self.status_fields["window_level"].value = value
        text = self.status_fields["window_level"].formatter(value)
        self.statusChanged.emit("window_level", text)

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
    # dicom_dir = sys.argv[1] if len(sys.argv) > 1 else None
    # if not dicom_dir:
    #     dicom_dir = vtk_helpers.select_dicom_directory()
    #     if dicom_dir is None:
    #         return

    # ビューアーを起動
    # viewer = VolumeViewer(dicom_dir)
    viewer = VolumeViewer(return_dicom_dir())

    # アプリケーションを実行（正常終了でプロセス終了）
    sys.exit(app.exec())


if __name__ == "__main__":
    main()