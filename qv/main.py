import copy
import logging
import sys
from pathlib import Path

import vtk
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QEvent
from vtkmodules.util.numpy_support import vtk_to_numpy

import qv.utils.vtk_helpers as vtk_helpers
from qv.utils.log_util import log_io
from clipping_function import QVVolumeClipper, ClippingInteractorStyle
from qv.status import STATUS_FIELDS, StatusField
from shortcut_manager import ShortcutManager
from ui.ui_mainwindow import Ui_MainWindow
from volumeviewer_interactor_style import VolumeViewerInteractorStyle
from vtk_helpers import return_dicom_dir
from logging_setup import LogSystem


logger = logging.getLogger(__name__)


class VolumeViewer(QtWidgets.QMainWindow):
    """Main window for the volume viewer."""
    statusChanged = QtCore.Signal(str, str)

    def __init__(self, dicom_dir: str | None = None, rotation_factor: float = 0.5) -> None:
        super().__init__()
        config_path = Path(__file__).parent.parent / "settings"
        self.shortcut_mgr = ShortcutManager(parent=self, config_path=config_path)
        self.register_command()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        logging.debug("UI created.")

        w = self.ui.vtk_widget
        w.installEventFilter(self)
        self.renderer = vtk.vtkRenderer()
        w.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = w.GetRenderWindow().GetInteractor()
        self._default_interactor_style = VolumeViewerInteractorStyle(self)
        self.interactor.SetInteractorStyle(self._default_interactor_style)
        self._clipping_interactor_style = ClippingInteractorStyle(self)

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

        self.clipper = QVVolumeClipper(self)
        # Actor for visualize the clipping region.
        self.clipper_actor = vtk.vtkActor()
        self.clipper_polydata = vtk.vtkPolyData()
        self.clipper_mapper = vtk.vtkPolyDataMapper()
        self.clipper_mapper.SetInputData(self.clipper_polydata)
        self.clipper_actor.SetMapper(self.clipper_mapper)
        self.clipper_actor.GetProperty().SetColor(1, 1, 0)
        self.clipper_actor.GetProperty().SetLineWidth(5)
        self.clipper_actor.GetProperty().SetOpacity(0.5)
        self.renderer.AddActor(self.clipper_actor)
        self.clipping_points = []

        self.ui.apply_clip_button.clicked.connect(self.apply_clipping)
        self.ui.cancel_clip_button.clicked.connect(self.cancel_clipping)

    def register_command(self):
        """
        Register the commands for the volume viewer.
        Commands are written in the settings file.
        """
        self.shortcut_mgr.add_callback("front_view", self.front_view)
        self.shortcut_mgr.add_callback("back_view", self.back_view)
        self.shortcut_mgr.add_callback("left_view", self.left_view)
        self.shortcut_mgr.add_callback("right_view", self.right_view)
        self.shortcut_mgr.add_callback("top_view", self.top_view)
        self.shortcut_mgr.add_callback("bottom_view", self.bottom_view)

    def eventFilter(self, obj, event):
        if obj == self.ui.vtk_widget:
            if event.type() == QEvent.MouseButtonDblClick:
                logger.debug("Mouse double click event detected ->  LeftButtonDoubleClickEvent")
                self.interactor.InvokeEvent("LeftButtonDoubleClickEvent")
                return True
        return super().eventFilter(obj, event)

    def update_status(self, **kwargs):
        """
        Update the status fields with the given keyword arguments and
        refresh the labels.
         """
        for key, value in kwargs.items():
            field = self.status_fields.get(key)
            if field is not None:
                self.status_fields[key].value = value

    def open_menu(self):
        dicom_dir = vtk_helpers.select_dicom_directory()
        if dicom_dir is None:
            return
        self.load_volume(dicom_dir)

    @log_io(level=logging.INFO)
    def load_volume(self, dicom_dir: str) -> None:
        """Load a volume from a DICOM directory."""
        logger.info(f"Loading volume from {dicom_dir}                                                                                                                                                                                                                              ")
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

        self.renderer.SetActiveCamera(camera)

        self.renderer.ResetCamera()
        self.update_transfer_functions()
        # self.test_AddRGBPoint()
        self.ui.vtk_widget.GetRenderWindow().Render()
        self.set_camera_view('front')

        # self.ui.histgram_widget.set_viewing_range(self.window_level-self.window_width / 2,
        #                                    self.window_level+self.window_width / 2)
        self.ui.histgram_widget.update_viewing_graph(self.volume_property.GetScalarOpacity())
        logging.info("Volume loaded: extent=%s spacing=%s origin=%s",
                     image.GetExtent(), image.GetSpacing(), image.GetOrigin())

    def test_AddRGBPoint(self) -> None:
        self.color_func.AddRGBPoint(0, 0.0, 0.0, 0.0)
        self.color_func.AddRGBPoint(500, 1.0, 0.5, 0.3)
        self.color_func.AddRGBPoint(1200, 1.0, 0.5, 0.3)
        self.color_func.AddRGBPoint(1350, 1.0, 1.0, 0.9)

        self.ui.vtk_widget.GetRenderWindow().Render()

    def update_transfer_functions(self) -> None:
        """
        Update the transfer functions for the volume.
        This function handles the window/level and color/opacity transfer functions.
        :return: None
        """
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
        """
        Update the viewing range of the histogram window.
        :return: None
        """
        if self.ui.histgram_widget is None:
            return

        pwf = self.volume_property.GetScalarOpacity()
        self.ui.histgram_widget.update_viewing_graph(pwf)

    def adjust_window_level(self, dx: int, dy: int) -> None:
        """
        Change the window/level of the volume according to the mouse movement.
        :param dx:
        :param dy:
        :return: None
        """
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
        """
        Rotate the camera according to the mouse movement.
        :param dx:
        :param dy:
        :return: None
        """
        da = -dx * self.rotation_factor
        de = -dy * self.rotation_factor
        camera = self.renderer.GetActiveCamera()
        camera.Azimuth(da)
        camera.Elevation(de)
        camera.OrthogonalizeViewUp()
        self.renderer.ResetCameraClippingRange()
        self.ui.vtk_widget.GetRenderWindow().Render()
        self.azimuth = (self.azimuth + da) % 360
        self.elevation = (self.elevation + de) % 360

    def apply_camera_angle(self):
        """
        Apply a pre-defined position to the current camera angle.
        :return:
        """
        azimuth, elevation = 0, 90
        camera = self.renderer.GetActiveCamera()
        camera.Azimuth(azimuth)
        camera.Elevation(elevation)
        # camera.SetPosition(0, 0, 1)

        camera.OrthogonalizeViewUp()
        self.renderer.SetActiveCamera(camera)
        self.renderer.ResetCameraClippingRange()
        self.ui.vtk_widget.GetRenderWindow().Render()
        self.azimuth, self.elevation = azimuth, elevation
        # self.azimuth, self.elevation = vtk_helpers.get_camera_angles(
        #     self.renderer.GetActiveCamera()
        # )

    def set_camera_view(self, view: str) -> None:
        """
        Set the camera to a preset view angle.
        Valid view values: 'front', 'back', 'left', 'right', 'top', 'bottom'.
        """


        # Preset directions for each view (unit sphere)
        directions = {
            'front':  (0.0, 1.0, 0.0),
            'back':   (0.0, -1.0, 0.0),
            'left':   (1.0, 0.0, 0.0),
            'right':  (-1.0, 0.0, 0.0),
            'top':    (0.0, 0.0, -1.0),
            'bottom': (0.0, 0.0, 1.0),
        }
        # Up vectors to keep orientation
        viewups = {
            'front':  (0.0, 0.0, -1.0),
            'back':   (0.0, 0.0, -1.0),
            'left':   (0.0, 0.0, -1.0),
            'right':  (0.0, 0.0, -1.0),
            'top':    (0.0, -1.0, 0.0),
            'bottom': (0.0, 1.0, 0.0),
        }
        angles = {
            'front':  (0.0, 0.0),
            'back':   (180, 0.0),
            'left':   (90, 0.0),
            'right':   (270, 0.0),
            'top':    (0.0, 90.0),
            'bottom': (0.0, 270.0),
        }
        key = view.lower()
        if key not in directions:
            return

        patient_matrix = None
        if self.volume:
            mapper = self.volume.GetMapper()
            image = mapper.GetInput()
            if hasattr(image, "GetDirectionMatrix"):
                patient_matrix = image.GetDirectionMatrix()

        camera = self.renderer.GetActiveCamera()
        fp = camera.GetFocalPoint()
        pos = camera.GetPosition()
        distance = vtk_helpers.calculate_norm(vtk_helpers.direction_vector(fp, pos))
        dir_vec = directions[key]
        up_vec = viewups[key]

        if patient_matrix:
            dir_vec = vtk_helpers.transform_vector(dir_vec, patient_matrix)
            up_vec = vtk_helpers.transform_vector(up_vec, patient_matrix)

        new_pos = [fp[i] + dir_vec[i] * distance for i in range(3)]
        camera.SetPosition(*new_pos)
        camera.SetViewUp(*up_vec)
        # Apply position and orientation
        self.renderer.ResetCameraClippingRange()
        # Update internal azimuth/elevation status
        self.ui.vtk_widget.GetRenderWindow().Render()
        self.azimuth, self.elevation = angles[key]

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
        """Return the iso-center of the whole volume."""
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
        """Set the camera zoom factor."""
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

    def apply_clipping(self):
        self.clipper.apply()
        self.exit_clip_mode()

    def cancel_clipping(self):
        self.clipper.cancel()
        self.exit_clip_mode()

    def enter_clip_mode(self):
        """Enter clip mode."""
        logging.debug("enter_clip_mode")
        self.interactor.SetInteractorStyle(self._clipping_interactor_style)
        self.ui.vtk_widget.GetRenderWindow().Render()
        self.ui.clip_button_widget.show()

    def enter_clip_result_mode(self):
        """Enter clip result mode to check the result of clipping before applying."""
        self.interactor.SetInteractorStyle(self._default_interactor_style)

    def exit_clip_mode(self):
        logging.debug("exit_clip_mode")
        self.interactor.SetInteractorStyle(self._default_interactor_style)
        self.ui.clip_button_widget.hide()

    def add_clip_point(self, pt: tuple[float, float, float]):
        self.clipper.add_point(pt)
        self.clipping_points.append(pt)
        self.update_clipper_visualization()

    def update_clipper_visualization(self):
        points = vtk.vtkPoints()
        lines = vtk.vtkCellArray()
        n = len(self.clipping_points)
        for i, pt in enumerate(self.clipping_points):
            points.InsertNextPoint(pt)
            if i > 0:
                lines.InsertNextCell(2)
                lines.InsertCellPoint(i - 1)
                lines.InsertCellPoint(i)
        if n >= 3:
            lines.InsertNextCell(2)
            lines.InsertCellPoint(n - 1)
            lines.InsertCellPoint(0)
        self.clipper_polydata.SetPoints(points)
        self.clipper_polydata.SetLines(lines)
        self.ui.vtk_widget.GetRenderWindow().Render()


def main():
    logs = LogSystem("qv")

    # 未処理例外はログを残す
    def excepthook(exctype, value, tb):
        logging.getLogger("qv").exception("Uncaught exception", exc_info=(exctype, value, tb))
    sys.excepthook = excepthook

    # 既存の QApplication インスタンスを取得。なければ新規作成。
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    # ビューアーを起動
    # viewer = VolumeViewer(dicom_dir)
    # 暫定的に自動的にDICOM画像を読み込むようにする。
    logger.info("App start")
    viewer = VolumeViewer(return_dicom_dir())

    # Qt 終了次にログを確実に止める
    app.aboutToQuit.connect(logs.stop)
    try:
        rc = app.exec()
        logger.info("App exit (rc=%s)", rc)
        sys.exit(rc)
    finally:
        logs.stop()  # 念のため


if __name__ == "__main__":
    main()