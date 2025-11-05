import copy
import logging
import math
from pathlib import Path

import vtk
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QEvent
from vtkmodules.util.numpy_support import vtk_to_numpy

import qv.utils.vtk_helpers as vtk_helpers
from app_settings_manager import AppSettingsManager
from core import geometry_utils
from qv.utils.log_util import log_io
from clipping_function import QVVolumeClipper, ClippingInteractorStyle
from qv.status import STATUS_FIELDS, StatusField
from shortcut_manager import ShortcutManager
from ui.ui_mainwindow import Ui_MainWindow
from viewer.camera_controller import CameraController
from core.camera_state import CameraAngle
from volumeviewer_interactor_style import VolumeViewerInteractorStyle

logger = logging.getLogger(__name__)


class VolumeViewer(QtWidgets.QMainWindow):
    """Main window for the volume viewer."""
    statusChanged = QtCore.Signal(str, str)

    def __init__(self, dicom_dir: str | None = None,
                 settings_manager: AppSettingsManager | None = None) -> None:
        super().__init__()
        config_path = Path(__file__).parent.parent.parent / "settings"
        print(config_path)
        self.setting = settings_manager or AppSettingsManager()
        self.shortcut_mgr = ShortcutManager(parent=self, config_path=config_path,
                                            settings_manager=self.setting)
        self.register_command()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        logging.debug("UI created.")

        w = self.ui.vtk_widget
        w.installEventFilter(self)
        render_window = w.GetRenderWindow()

        self.renderer = vtk.vtkRenderer()
        self.renderer.SetLayer(0)
        render_window.AddRenderer(self.renderer)
        render_window.SetNumberOfLayers(2)

        self.camera_controller = CameraController(self.renderer.GetActiveCamera(), self.renderer)
        self.camera_controller.add_angle_changed_callback(self._on_camera_angle_changed)

        self.overlay_renderer = vtk.vtkRenderer()
        self.overlay_renderer.SetLayer(1)
        self.overlay_renderer.SetInteractive(False)
        if hasattr(self.overlay_renderer, "SetBackgroundAlpha"):
            self.overlay_renderer.SetBackgroundAlpha(0.0)
        if hasattr(self.overlay_renderer, "SetUseDepth"):
            self.overlay_renderer.SetUseDepth(0)
        render_window.AddRenderer(self.overlay_renderer)

        self.interactor = render_window.GetInteractor()
        self._default_interactor_style = VolumeViewerInteractorStyle(self)
        self.interactor.SetInteractorStyle(self._default_interactor_style)
        self._clipping_interactor_style = ClippingInteractorStyle(self)

        self._right_dragging = False
        self._left_dragging = False
        self._last_pos = QtCore.QPoint()
        self.rotation_factor = self.setting.rotation_step_deg

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

        self.clipper = QVVolumeClipper(self, self.overlay_renderer)
        # Actor for visualize the clipping region.
        self.clipper_actor = vtk.vtkActor()
        self.clipper_polydata = vtk.vtkPolyData()
        self.clipper_mapper = vtk.vtkPolyDataMapper()
        self.clipper_mapper.SetInputData(self.clipper_polydata)
        self.clipper_actor.SetMapper(self.clipper_mapper)
        prop = self.clipper_actor.GetProperty()
        prop.SetColor(1, 1, 0)
        prop.SetLineWidth(3)
        prop.SetOpacity(1.0)
        prop.SetRenderLinesAsTubes(True)
        prop.RenderPointsAsSpheresOn()
        prop.SetPointSize(6)
        self.renderer.AddActor(self.clipper_actor)
        self._clipper_overlay_observer = self.interactor.AddObserver(
            "EndInteractionEvent", self._on_camera_interaction
        )

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
        self.shortcut_mgr.add_callback("load_image", self.open_menu)

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
        # camera = vtk.vtkCamera()
        # camera.SetClippingRange(0.001, 100)
        # camera.SetFocalPoint(0, 0, 0)
        self.camera_controller.extract_patient_matrix_from_volume(self.volume)

        # self.renderer.SetActiveCamera(camera)
        self.camera_controller.reset_to_bounds(self.volume.GetBounds(), view='front')

        # self.renderer.ResetCamera()
        self.azimuth = self.camera_controller.azimuth
        self.elevation = self.camera_controller.elevation

        self.update_transfer_functions()
        # self.test_AddRGBPoint()
        self.ui.vtk_widget.GetRenderWindow().Render()
        # self.set_camera_view('front')

        # self.ui.histgram_widget.set_viewing_range(self.window_level-self.window_width / 2,
        #                                    self.window_level+self.window_width / 2)
        self.ui.histgram_widget.update_opacity_curve(self.volume_property.GetScalarOpacity())
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
        self.ui.histgram_widget.update_opacity_curve(pwf)

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

    def _on_camera_angle_changed(self, angle: CameraAngle) -> None:
        """Callback for when the camera angle changes."""
        self.azimuth = angle.azimuth
        self.elevation = angle.elevation

    def rotate_camera(self, dx: int, dy: int) -> None:
        """
        Rotate the camera according to the mouse movement.
        :param dx:
        :param dy:
        :return: None
        """
        da = -dx * self.rotation_factor
        de = -dy * self.rotation_factor

        self.camera_controller.rotate(da, de)
        self.ui.vtk_widget.GetRenderWindow().Render()

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
        self.camera_controller.set_preset_view(view)
        self.ui.vtk_widget.GetRenderWindow().Render()

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
        if self.volume is None:
            return

        bounds = self.volume.GetBounds()
        max_dim = max(
            bounds[1] - bounds[0],
            bounds[3] - bounds[2],
            bounds[5] - bounds[4],
        )
        default_distance = 2.0 * max_dim

        self.camera_controller.set_zoom(factor, default_distance=default_distance)
        self.ui.vtk_widget.GetRenderWindow().Render()

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
        self.clipper.start_region_selection()
        self.ui.vtk_widget.GetRenderWindow().Render()
        self.ui.clip_button_widget.show()

    def enter_clip_result_mode(self):
        """Enter clip result mode to check the result of clipping before applying."""
        self.interactor.SetInteractorStyle(self._default_interactor_style)
        self.clipper.stop_region_selection()

    def exit_clip_mode(self):
        logging.debug("exit_clip_mode")
        self.interactor.SetInteractorStyle(self._default_interactor_style)
        self.clipper.stop_region_selection()
        self.ui.clip_button_widget.hide()

    def add_clip_point(self, display_xy: tuple[float, float], world_pt: tuple[float, float, float]) -> None:
        self.clipper.add_selection_point(display_xy, world_pt)
        self.update_clipper_visualization()

    def _on_camera_interaction(self, *_):
        self.clipper.on_camera_updated()

    def update_clipper_visualization(self):
        world_points = self.clipper.get_preview_world_points()
        if not world_points:
            self.clipper_polydata.Initialize()
            self.ui.vtk_widget.GetRenderWindow().Render()
            return

        cam = self.renderer.GetActiveCamera()
        cam_pos = cam.GetPosition()
        bounds = self.renderer.ComputeVisiblePropBounds()
        diag = math.sqrt(sum((bounds[2 * i + 1] - bounds[2 * i])**2 for i in range(3))) or 1.0
        offset = 0.002 * diag

        points = vtk.vtkPoints()
        verts = vtk.vtkCellArray()
        lines = vtk.vtkCellArray()

        n = len(world_points)
        for i, pt in enumerate(world_points):
            to_cam = [cam_pos[j] - pt[j] for j in range(3)]
            length = geometry_utils.calculate_norm(to_cam)
            if length:
                disp_pt = [pt[j] + to_cam[j] / length * offset for j in range(3)]
            else:
                disp_pt = pt
            points.InsertNextPoint(*disp_pt)

            verts.InsertNextCell(1)
            verts.InsertCellPoint(i)

            if i > 0:
                lines.InsertNextCell(2)
                lines.InsertCellPoint(i - 1)
                lines.InsertCellPoint(i)

        if n == 1:
            lines.InsertNextCell(2)
            lines.InsertCellPoint(0)
            lines.InsertCellPoint(0)
        elif n == 2:
            pass
        elif n >= 3:
            lines.InsertNextCell(2)
            lines.InsertCellPoint(n - 1)
            lines.InsertCellPoint(0)

        self.clipper_polydata.SetPoints(points)
        self.clipper_polydata.SetVerts(verts)
        self.clipper_polydata.SetLines(lines)
        self.ui.vtk_widget.GetRenderWindow().Render()
