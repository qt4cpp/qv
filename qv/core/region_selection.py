from __future__ import annotations

from typing import Callable, Sequence

import vtk

import logging
import qv.utils.vtk_helpers as vtk_helpers
from core import geometry_utils

logger = logging.getLogger(__name__)


RegionClosedCallback = Callable[[Sequence[tuple[float, float]],
                                 Sequence[tuple[float, float, float]]], None]


class RegionSelectionController:
    """
    Manage polygon selection on top of a VTK render window.

    - collects clicks in display coordinates
    - renders the polygon as a 2D overlay
    - projects the polygon onto a camera-aligned plane when needed
    - emits a callback with (display_points, world_points) once the user finalises
    """

    def __init__(
        self,
        render_window: vtk.vtkRenderWindow,
        world_renderer: vtk.vtkRenderer,
        overlay_renderer: vtk.vtkRenderer,
    ) -> None:
        logger.debug("initialising region selection controller")

        self.render_window = render_window
        self.world_renderer = world_renderer
        self.overlay_renderer = overlay_renderer

        self.display_points: list[tuple[float, float]] = []
        self.world_points: list[tuple[float, float, float]] = []
        self.reference_depth: float | None = None
        self.closed_callback: RegionClosedCallback | None = None
        self._enabled = False

        # 2D polyline overlay
        self._overlay_points = vtk.vtkPoints()
        self._overlay_lines = vtk.vtkCellArray()
        self._overlay_verts = vtk.vtkCellArray()
        self._overlay_polydata = vtk.vtkPolyData()
        self._overlay_polydata.SetPoints(self._overlay_points)
        self._overlay_polydata.SetLines(self._overlay_lines)
        self._overlay_polydata.SetVerts(self._overlay_verts)

        self._overlay_mapper = vtk.vtkPolyDataMapper2D()
        self._overlay_mapper.SetInputData(self._overlay_polydata)

        coord = vtk.vtkCoordinate()
        coord.SetCoordinateSystemToDisplay()
        self._overlay_mapper.SetTransformCoordinate(coord)

        self._overlay_actor = vtk.vtkActor2D()
        self._overlay_actor.SetMapper(self._overlay_mapper)

        prop = self._overlay_actor.GetProperty()
        prop.SetOpacity(1.0)
        self.set_overlay_property(
            line_color=(1.0, 0.95, 0.1),
            line_width=2.0,
            point_size=6.0,
        )

        self.overlay_renderer.AddActor2D(self._overlay_actor)

        # observer: when camera interaction ends, recompute projection
        self._interactor_observer_id: int | None = None

        logger.debug("initialisation complete")

    # ----------------------------------------------------
    # public API
    def set_overlay_property(
        self,
        line_color: tuple[float, float, float] = (1.0, 0.95, 0.1),
        line_width: float = 2.0,
        point_size: float = 6.0,
    ) -> None:
        prop = self._overlay_actor.GetProperty()
        prop.SetColor(line_color)
        prop.SetLineWidth(line_width)
        prop.SetPointSize(point_size)

    def set_closed_callback(self, callback: RegionClosedCallback | None) -> None:
        self.closed_callback = callback

    def enable(self) -> None:
        if self._enabled:
            return
        self._enabled = True
        self.reset()
        interactor = self.render_window.GetInteractor()
        if self._interactor_observer_id is None:
            self._interactor_observer_id = interactor.AddObserver(
                "EndInteractionEvent", self._on_camera_interaction
            )
        logger.info("region selection enabled")

    def disable(self) -> None:
        if not self._enabled:
            return
        self.reset(clear_overlay=True)
        interactor = self.render_window.GetInteractor()
        if self._interactor_observer_id is not None:
            interactor.RemoveObserver(self._interactor_observer_id)
            self._interactor_observer_id = None
        logger.info("region selection disabled")

    def add_display_point(
        self,
        x: float,
        y: float,
        picked_world: tuple[float, float, float] | None = None,
    ) -> None:
        """Register a new vertex (usually on LeftButtonPress)."""
        if not self._enabled:
            return
        self._ensure_reference_depth(picked_world)
        self.display_points.append((x, y))
        self._invalidate_projection()
        self._update_overlay()
        self.render_window.Render()

    def is_enabled(self) -> bool:
        return self._enabled

    def get_display_points(self) -> list[tuple[float, float]]:
        return list(self.display_points)

    def get_world_points(self) -> list[tuple[float, float, float]]:
        if self.display_points and not self.world_points:
            self._project_display_points()
        return list(self.world_points)

    def complete(self) -> None:
        if not self._enabled or len(self.display_points) < 3:
            logger.debug("region selection complete: not enabled or <3 points")
            return
        
        world_points = self._project_display_points()
        if self.closed_callback and len(world_points) == len(self.display_points):
            self.closed_callback(
                tuple(self.display_points),
                tuple(world_points),
            )

        self.reset(clear_overlay=True)
        self.render_window.Render()
        logger.info("region selection complete")

    # -------------------------------------------------
    # Internal helpers
    def reset(self, clear_overlay: bool = False) -> None:
        self.display_points.clear()
        self._invalidate_projection()
        self.reference_depth = None
        if clear_overlay:
            self._overlay_actor.SetVisibility(0)
            self._clear_overlay()
        else:
            self._update_overlay()
        logger.debug("region selection reset")

    def _invalidate_projection(self) -> None:
        self.world_points.clear()

    def _clear_overlay(self) -> None:
        self._overlay_points.Reset()
        self._overlay_lines.Reset()
        self._overlay_verts.Reset()
        self._overlay_polydata.Modified()

    def _update_overlay(self) -> None:
        self._clear_overlay()

        for x, y in self.display_points:
            self._overlay_points.InsertNextPoint(x, y, 0.0)

        count = len(self.display_points)
        if count == 1:
            self._overlay_verts.InsertNextCell(1)
            self._overlay_verts.InsertCellPoint(0)
        elif count >= 2:
            self._overlay_lines.InsertNextCell(count)
            for idx in range(count):
                self._overlay_lines.InsertCellPoint(idx)

        self._overlay_actor.SetVisibility(1 if count else 0)
        self._overlay_points.Modified()
        self._overlay_lines.Modified()
        self._overlay_verts.Modified()
        self._overlay_polydata.Modified()

    def _ensure_reference_depth(
        self,
        picked_world: tuple[float, float, float] | None,
    ) -> None:
        if self.reference_depth is not None:
            return

        camera_info = vtk_helpers.get_camera_and_view_direction(self.world_renderer)
        if camera_info is None:
            return

        camera, view_dir, norm = camera_info
        cam_pos = camera.GetPosition()

        # 常に手前（カメラに近い位置）に設定
        # picked_worldの有無に関わらず、一定の手前位置を使用
        self.reference_depth = norm * 0.8  # normの0.5%の位置

    def _update_reference_depth_from_world(self) -> None:
        if not self.world_points:
            return

        camera_info = vtk_helpers.get_camera_and_view_direction(self.world_renderer)
        if camera_info is None:
            return

        camera, view_dir, _ = camera_info
        cam_pos = camera.GetPosition()

        depths = []
        for point in self.world_points:
            cam_to_point = geometry_utils.direction_vector(cam_pos, point)
            depth = sum(cam_to_point[i] * view_dir[i] for i in range(3))
            depths.append(depth)

        if depths:
            self.reference_depth = sum(depths) / len(depths)

    def _project_display_points(self) -> list[tuple[float, float, float]]:
        if not self.display_points:
            self.world_points.clear()
            return []

        camera_info = vtk_helpers.get_camera_and_view_direction(self.world_renderer)
        if camera_info is None:
            self.world_points.clear()
            return []

        camera, view_dir, norm = camera_info
        cam_pos = camera.GetPosition()

        depth = self.reference_depth
        if depth is None:
            depth = norm
            self.reference_depth = depth

        plane_point = [cam_pos[i] + view_dir[i] * depth for i in range(3)]
        renderer = self.world_renderer

        projected: list[tuple[float, float, float]] = []
        for x, y in self.display_points:
            renderer.SetDisplayPoint(x, y, 0.0)
            renderer.DisplayToWorld()
            near4 = renderer.GetWorldPoint()
            if near4[3] == 0:
                projected.append(tuple(cam_pos))
                continue
            near = [near4[i] / near4[3] for i in range(3)]

            renderer.SetDisplayPoint(x, y, 1.0)
            renderer.DisplayToWorld()
            far4 = renderer.GetWorldPoint()
            if far4[3] == 0:
                projected.append(tuple(near))
                continue
            far = [far4[i] / far4[3] for i in range(3)]

            ray_dir = [far[i] - near[i] for i in range(3)]
            denom = sum(ray_dir[i] * view_dir[i] for i in range(3))
            if abs(denom) < 1e-6:
                projected.append(tuple(near))
                continue

            t = sum((plane_point[i] - near[i]) * view_dir[i] for i in range(3)) / denom
            pt3d = [near[i] + t * ray_dir[i] for i in range(3)]
            projected.append(tuple(pt3d))

        self.world_points = projected
        return projected

    def _on_camera_interaction(self, *_args) -> None:
        if not self._enabled or not self.display_points:
            return

        if not self.world_points:
            self._project_display_points()
        else:
            self._update_reference_depth_from_world()
            self._project_display_points()

        self.render_window.Render()
