"""
Clipping operation for volume data based on user-defined region.
"""
import logging
from typing import TYPE_CHECKING, Sequence, Callable

import vtk
from matplotlib.backends import backend_registry
from vtkmodules.vtkCommonDataModel import vtkImplicitSelectionLoop
from vtkmodules.vtkRenderingCore import vtkActor

from core import geometry_utils
from core.region_selection import RegionSelectionController
from log_util import log_io
from operations.base_operation import BaseOperation

CLIPPED_SCALAR = -32768  # value guaranteed to sit outside clinical HUs


if TYPE_CHECKING:
    # 型チェック時のみインポートする
    # 相互参照となってしまう。
    from viewers.volume_viewer import VolumeViewer


logger = logging.getLogger(__name__)


class ClippingOperation(BaseOperation):
    """
    Operation to clip volume data based on user-defined region.

    This operation allows users to define a 3D region by selecting points,
    then clips (removes) volume data within that region. The operation is
    independent of viewer implementation nad only depends on:
    - Image data (vtk.vtkImageData)
    - Camera information (vtk.vtkCamera)
    - Renderer for visualization (vtk.vtkRenderer)

    Attributes:
        viewer: Reference to VolumeViewer (needed for UI integration)
        ovarlay_renderer: Renderer for visualization elemnts
        region_slection: Controller for region selection
        clip_loop: The implicit selection loop defining the clip region.
        preview_extrude_actor: Actor for 3D preview of the clip region.
    """

    def __init__(
            self,
            viewer: "VolumeViewer",
            overlay_renderer: vtk.vtkRenderer,
            image_provider: Callable[[], vtk.vtkImageData | None] | None = None,
            camera_provider: Callable[[], vtk.vtkCamera | None] | None = None,
            renderer_provider: Callable[[], vtk.vtkRenderer | None] | None = None,
            image_updater: Callable[[vtk.vtkImageData], None] | None = None,
    ):
        """
        Initialize the clipping operation.

        :param viewer: The volume viewer instance.
        :param overlay_renderer: Renderer for selection visualization.
        :param image_provider: Optional callable to get curernt image data.
                               Defaults to getting from viewer.volume.
        :param camera_provider: Optional callable to get current camera.
                                Defaults to getting from viewer.renderer.
        :param renderer_provider: Optional callbale to get renderer.
                                  Defaults to getting from viewer.renderer.
        :param image_updater: Optional callbale to update viewer with new image.
                              Defaults to updating viewer.volume.
        """
        super().__init__()
        self.viewer = viewer
        self.overlay_renderer = overlay_renderer

        # Data providers and updaters  (for flexiblility and testability)
        self._image_provider = image_provider or self._default_image_provider
        self._camera_provider = camera_provider or self._default_camera_provider
        self._renderer_provider = renderer_provider or self._default_renderer_provider
        self._image_updater = image_updater or self._default_image_updater

        # Selection state
        self.clip_points_display: list[tuple[float, float]] = []
        self.clip_points_world: list[tuple[float, float, float]] = []
        self.clip_points_center: list[tuple[float, float, float]] = []

        # VTK objects
        self.clip_loop: vtkImplicitSelectionLoop | None = None
        self.preview_extrude_actor: vtkActor | None = None

        # Region selection controller
        self.region_selection = RegionSelectionController(
            viewer.vtk_widget.GetRenderWindow(),
            viewer.renderer,
            overlay_renderer,
        )
        self.region_selection.set_closed_callback(self._on_region_closed)

        logger.debug("[ClippingOperation] Initialized.")

    # =====================================================
    # Lifecycle methods (BaseOperation interface)
    # =====================================================

    def start(self) -> None:
        """
        Start the clipping operation.

        Resets state, creates binary mask, applies it to the images.
        and updates the viewer.
        """
        logger.info("[ClippingOperation] Starting operation.")
        self.reset()
        self.is_active = True
        self.region_selection.enable()

    def apply(self) -> None:
        """
        Apply the clipping operation to the volume.

        Validates state, creates binary mask, applies it to the images,
        and updates the viewer.
        """
        logger.info("[ClippingOperation] Applying operation.")

        if not self._has_backup():
            current_image = self._image_provider()
            if current_image is not None:
                self._backup_image_data(current_image)
                logger.info("[ClippingOperation] Backed up current image.")
            else:
                logger.warning("[ClippingOperation] No backup and current image. Aborting.")
                self.reset()
                return

        if self.clip_loop is None:
            logger.warning("[ClippingOperation] No clip loop defined. Aborting.")
            self.reset()
            return

        clipping_img = self._apply_clipping()
        if clipping_img is not None:
            self._image_updater(clipping_img)
            self._backup_image_data(clipping_img)

        self.reset()

    def cancel(self) -> None:
        """
        Cancel the clipping operation.

        Restores the backup image if available.
        """
        logger.info("[ClippingOperation] Canceling operation.")
        if self._has_backup():
            self._image_updater(self.backup_image)
        self.reset()

    def reset(self) -> None:
        """
        Reset the clipping operation to initial state.

        Clears all internal state, removes preview, and disables region selection.
        """
        logger.debug("[ClippingOperation] Resetting operation.")

        if self.preview_extrude_actor is not None:
            renderer = self._renderer_provider()
            if renderer is not None and self.preview_extrude_actor is not None:
                renderer.RemoveActor(self.preview_extrude_actor)
            self.preview_extrude_actor = None

        # Stop region selection
        self._stop_region_selection()

        self.backup_image = None
        self.clip_loop = None
        self.clip_points_display.clear()
        self.clip_points_world.clear()
        self.clip_points_center.clear()
        self.is_active = False

        # Clear viewer visualization
        if hasattr(self.viewer, "clipping_points"):
            self.viewer.clipping_points.clear()
        if hasattr(self.viewer, "update_clipper_visualization"):
            self.viewer.update_clipper_visualization()

    # =====================================================
    # Clipping-specific public interface
    # =====================================================

    def add_selection_point(self, display_xy: tuple[float, float],
                            world_pt: tuple[float, float, float]) -> None:
        """
        Add a point to the selection region.

        :param display_xy: Display coordinates (x, y) in pixels.
        :param world_pt: World coordinates (x, y, z).
        """
        if not self.is_active:
            return
        self.region_selection.add_display_point(display_xy[0], display_xy[1], world_pt)

    def complete_selection(self) -> None:
        """
        Complete the region selection.

        Signals the region selection controller to finish selecting points.
        """
        if not self.is_active:
            return
        self.region_selection.complete()

    def finalize_clip(self) -> None:
        """
        Finalize the clip region and create preview visualization.

        Screen-space based implementation:

        - Uses the user-drawn display (screen) coordinates as the source of truth
          for the clipping loop.
        - Projects those display points onto a plane passing through the volume
          center (or camera focal point) with normal equal to the view direction.
        - Builds a vtkImplicitSelectionLoop from the projected points and creates
          a 3D preview by extruding that polygon along the view direction.
        """
        logger.info("[ClippingOperation] Finalizing clip region.")

        # Backup current image
        current_image = self._image_provider()
        if current_image is None:
            logger.warning("[ClippingOperation] No current image.")
            self.clip_loop = None
            return

        self._backup_image_data(current_image)

        if len(self.clip_points_display) < 3:
            logger.warning("[ClippingOperation] Need at least 3 points. Got %d",
                           len(self.clip_points_display))
            self.backup_image = None
            self.clip_loop = None
            return

        camera = self._camera_provider()
        renderer = self._renderer_provider()
        if camera is None or renderer is None:
            logger.warning("[ClippingOperation] No camera or renderer available.")
            self.backup_image = None
            self.clip_loop = None
            return

        # View direction (normal of clip plane)
        fp = camera.GetFocalPoint()
        view_vec = geometry_utils.direction_vector(camera.GetPosition(), fp)
        norm = geometry_utils.calculate_norm(view_vec)

        if norm == 0:
            logger.warning("[ClippingOperation] Camera direction is invalid.")
            self.backup_image = None
            self.clip_loop = None
            return

        view_vec = [v / norm for v in view_vec]

        #  --- Screen-space clipping core ---
        # project display points (x, y) onto a singe plane (through volume center)
        # so the resulting world-space polygon matches wat the user sees.
        world_points_center = self._project_display_to_center_plane(
            self.clip_points_display,
            camera,
            renderer,
        )
        if len(world_points_center) < 3:
            logger.warning("[ClippingOperation] Not enough world points.")
            self.backup_image = None
            self.clip_loop = None
            return

        self.clip_points_center = list(world_points_center)

        bounds = self.backup_image.GetBounds()
        back_depth = max(
            bounds[1] - bounds[0],
            bounds[3] - bounds[2],
            bounds[5] - bounds[4]
        )
        front_depth = max(0.0, back_depth - 1e-6)

        vtk_points = vtk.vtkPoints()
        for pt in self.clip_points_center:
            vtk_points.InsertNextPoint(*pt)

        self.clip_loop = vtkImplicitSelectionLoop()
        self.clip_loop.SetLoop(vtk_points)
        self.clip_loop.SetNormal(*view_vec)
        self.clip_loop.AutomaticNormalGenerationOff()

        self._create_preview(vtk_points, view_vec, front_depth)

        logger.info("[ClippingOperation] Finalized with %d points.",
                    len(self.clip_points_center))

    def on_camera_updated(self) -> None:
        """
        Handle camera update events.

        Updates visualization when camera changes during selection.
        """
        if self.is_active:
            if hasattr(self.viewer, "update_clipper_visualization"):
                self.viewer.update_clipper_visualization()

    def get_preview_world_points(self) -> list[tuple[float, float, float]]:
        """
        Get world points for preview visualization.

        :return: List of world points.
        """
        if self.clip_points_center:
            return list(self.clip_points_center)

        if self.clip_points_world:
            return list(self.clip_points_world)

        if self.is_active:
            return self.region_selection.get_world_points()
        return []

    # =====================================================
    # Internal helpers
    # =====================================================

    def _stop_region_selection(self) -> None:
        """Stop region selection mode."""
        if self.region_selection.is_enabled():
            self.region_selection.disable()

    def _on_region_closed(
            self,
            display_points: Sequence[tuple[float, float]],
            world_points: Sequence[tuple[float, float, float]],
    ) -> None:
        """
        Callback when region selection is closed.

        :param display_points: Display coordinates of selection.
        :param world_points:  World coordinates of selection.
        """
        if len(display_points) < 3 or len(world_points) < 3:
            self._stop_region_selection()
            self.reset()
            return

        # Screen-space clipping: display points are the primary source for
        # building the clip loop. World points are kept only for debugging
        # or potential future use.
        self.clip_points_display = list(display_points)
        self.clip_points_world = list(world_points)
        self._stop_region_selection()

        if hasattr(self.viewer, "update_clipper_visualization"):
            self.viewer.update_clipper_visualization()

        previous_loop = self.clip_loop
        self.finalize_clip()

        # Notify viewer that clip result is ready
        if self.clip_loop is not None and self.clip_loop is not previous_loop:
            if hasattr(self.viewer, "update_clipper_visualization"):
                self.viewer.update_clipper_visualization()
            self.viewer.enter_clip_result_mode()

    def _project_display_to_center_plane(
            self,
            display_points: Sequence[tuple[float, float]],
            camera: vtk.vtkCamera,
            renderer: vtk.vtkRenderer,
    ) -> list[tuple[float, float, float]]:
        """
        Project screen-space points onto a plane passing through the volume center
         (or camera focal point) with normal equal to the view direction.

         This is the core of the screen-space clipping approach:
         - The user draws the ROI in display coordinates.
         - We take thos (x, y) pixels and assign them a common depth value.
           corresponding to the volume center on screen.
         - We then convert (x, y, depth) back to world coordinates.

         As a result, the polygon used for clipping lies on a single plane
         orthogonal to the view direction and viaually matches the ROI seen by the user.
        """

        if not display_points:
            return []

        # Determine the reference point for depth: volume center or focal point.
        center = self._get_clip_plane_center(camera)

        renderer.SetWorldPoint(center[0], center[1], center[2], 1.0)
        renderer.WorldToDisplay()
        _, _, depth = renderer.GetDisplayPoint()

        projected: list[tuple[float, float, float]] = []
        for x, y in display_points:
            renderer.SetDisplayPoint(x, y, depth)
            renderer.DisplayToWorld()
            wx, wy, wz, w = renderer.GetWorldPoint()
            if w != 0.0:
                wx /= w
                wy /= w
                wz /= w
            projected.append((wx, wy, wz))

        return projected

    def _apply_clipping(self) -> vtk.vtkImageData | None:
        """
        Apply clipping to the backup image.

        :return: Clipped image data, or None if failed.
        """
        if not self._has_backup() or self.clip_loop is None:
            return None

        # Try mask-based approach first
        mask_img = self._build_binary_mask()
        if mask_img is not None:
            return self._apply_mask(mask_img)

        # Fallback to stencil-based approach
        return self._apply_stencil()

    def _build_binary_mask(self) -> vtk.vtkImageData | None:
        """
        Build binary mask from clip loop.

        Creates a mask where 0 represents inside the clip region
        and 255 represents outside.

        :return: Binary mask image, or None if failed.
        """
        if not self._has_backup() or self.clip_loop is None:
            return None

        stenciler = vtk.vtkImplicitFunctionToImageStencil()
        stenciler.SetInput(self.clip_loop)
        stenciler.SetOutputSpacing(self.backup_image.GetSpacing())
        stenciler.SetOutputOrigin(self.backup_image.GetOrigin())
        stenciler.SetOutputWholeExtent(self.backup_image.GetExtent())
        stenciler.Update()

        ones = vtk.vtkImageThreshold()
        ones.SetInputData(self.backup_image)
        ones.ReplaceInOn()
        ones.ReplaceOutOn()
        ones.ThresholdBetween(-1e38, 1e38)
        ones.SetInValue(255)
        ones.SetOutValue(255)
        ones.SetOutputScalarTypeToUnsignedChar()
        ones.Update()

        img_stencil = vtk.vtkImageStencil()
        img_stencil.SetInputData(ones.GetOutput())
        img_stencil.SetStencilConnection(stenciler.GetOutputPort())
        img_stencil.ReverseStencilOn()
        img_stencil.SetBackgroundValue(0)
        img_stencil.Update()

        mask_img = vtk.vtkImageData()
        mask_img.ShallowCopy(img_stencil.GetOutput())

        logger.debug("[ClippingOperation] Mask cerated: type=%s, range=%s",
                     mask_img.GetScalarTypeAsString(),
                     mask_img.GetScalarRange())

        return mask_img

    def _apply_mask(self, mask_img: vtk.vtkImageData) -> vtk.vtkImageData | None:
        """
        Apply mask to back up image.

        :param mask_img: Binary mask image.
        :return: Clipped image data.
        """
        if not self._has_backup():
            return None

        masker = vtk.vtkImageMask()
        masker.SetInputData(self.backup_image)
        masker.SetMaskInputData(mask_img)
        masker.SetMaskedOutputValue(CLIPPED_SCALAR)
        masker.Update()

        clipped_img = vtk.vtkImageData()
        clipped_img.DeepCopy(masker.GetOutput())

        return clipped_img

    def _apply_stencil(self) -> vtk.vtkImageData | None:
        """
        Apply stencil directly (fallback method).

        :return: Clipped image data.
        """
        if not self._has_backup() or self.clip_loop is None:
            return None

        stenciler = vtk.vtkImplicitFunctionToImageStencil()
        stenciler.SetInput(self.clip_loop)
        stenciler.SetOutputSpacing(self.backup_image.GetSpacing())
        stenciler.SetOutputOrigin(self.backup_image.GetOrigin())
        stenciler.SetOutputWholeExtent(self.backup_image.GetExtent())
        stenciler.Update()

        image_stencil = vtk.vtkImageStencil()
        image_stencil.SetInputData(self.backup_image)
        image_stencil.SetStencilConnection(stenciler.GetOutputPort())
        image_stencil.ReverseStencilOn()
        image_stencil.SetBackgroundValue(CLIPPED_SCALAR)
        image_stencil.Update()

        clipped_img = vtk.vtkImageData()
        clipped_img.DeepCopy(image_stencil.GetOutput())

        return clipped_img

    def _create_preview(
            self,
            vtk_points: vtk.vtkPoints,
            view_vec: Sequence[float],
            front_depth: float
    ) -> None:
        """
        Create 3D preview of the clipping region.

        :param vtk_points: Points defining the selection loop.
        :param view_vec: Normalized view direction vector.
        """
        if not self._has_backup():
            return

        bounds = self.backup_image.GetBounds()
        back_depth = max(
            bounds[1] - bounds[0],
            bounds[3] - bounds[2],
            bounds[5] - bounds[4]
        )

        v_norm = geometry_utils.calculate_norm(view_vec)
        if v_norm < 1e-6:
            return

        vx = view_vec[0] / v_norm
        vy = view_vec[1] / v_norm
        vz = view_vec[2] / v_norm

        poly = vtk.vtkPolyData()
        poly.SetPoints(vtk_points)

        lines = vtk.vtkCellArray()
        num_pts = vtk_points.GetNumberOfPoints()
        lines.InsertNextCell(num_pts + 1)
        for i in range(num_pts):
            lines.InsertCellPoint(i)
        lines.InsertCellPoint(0)
        poly.SetLines(lines)

        extrude_back = vtk.vtkLinearExtrusionFilter()
        extrude_back.SetInputData(poly)
        extrude_back.SetVector(vx, vy, vz)
        extrude_back.SetExtrusionTypeToNormalExtrusion()
        extrude_back.SetScaleFactor(back_depth)
        extrude_back.SetCapping(True)

        extrude_front = vtk.vtkLinearExtrusionFilter()
        extrude_front.SetInputData(poly)
        extrude_front.SetVector(-vx, -vy, -vz)
        extrude_front.SetExtrusionTypeToNormalExtrusion()
        extrude_front.SetScaleFactor(max(front_depth, 0.0))
        extrude_front.SetCapping(True)

        appned = vtk.vtkAppendPolyData()
        appned.AddInputConnection(extrude_back.GetOutputPort())
        appned.AddInputConnection(extrude_front.GetOutputPort())
        appned.Update()

        mapper3D = vtk.vtkPolyDataMapper()
        mapper3D.SetInputConnection(appned.GetOutputPort())
        self.preview_extrude_actor = vtk.vtkActor()
        self.preview_extrude_actor.SetMapper(mapper3D)
        self.preview_extrude_actor.GetProperty().SetColor(0.5, 0.5, 0)
        self.preview_extrude_actor.GetProperty().SetOpacity(1.0)

        renderer = self._renderer_provider()
        if renderer is not None:
            renderer.AddActor(self.preview_extrude_actor)

        self.viewer.preview_extrude_actor = self.preview_extrude_actor
        self._render()

    def _render(self) -> None:
        """Trigger render on viewer"""
        if hasattr(self.viewer, "vtk_widget"):
            self.viewer.vtk_widget.GetRenderWindow().Render()

    # =====================================================
    # Default provider/updater implementations
    # =====================================================

    def _default_image_provider(self) -> vtk.vtkImageData | None:
        """Get current image from viewer"""
        if not hasattr(self.viewer, "volume") or self.viewer.volume is None:
            return None
        return self.viewer.volume.GetMapper().GetInput()

    def _default_camera_provider(self) -> vtk.vtkCamera | None:
        """Get current camera from viewer"""
        if not hasattr(self.viewer, "renderer"):
            return None
        return self.viewer.renderer.GetActiveCamera()

    def _default_renderer_provider(self) -> vtk.vtkRenderer | None:
        """Get current renderer from viewer"""
        return getattr(self.viewer, "renderer", None)

    def _default_image_updater(self, image_data: vtk.vtkImageData) -> None:
        """Update volume mapper with new image data"""
        if not hasattr(self.viewer, "volume") or self.viewer.volume is None:
            return
        mapper = self.viewer.volume.GetMapper()
        mapper.SetInputData(image_data)
        self.viewer.volume.SetMapper(mapper)
        self._render()

    def _get_clip_plane_center(self, camera: vtk.vtkCamera) -> tuple[float, float, float]:
        """
        Get center of the clipping plane from camera

        Prefer the volume center if available, otherwise use the camera focal point.
        """
        if hasattr(self.viewer, "get_volume_center"):
            try:
                return self.viewer.get_volume_center()
            except Exception:
                pass
        return camera.GetFocalPoint()

    def _project_points_to_center_plane(
            self,
            world_points: Sequence[tuple[float, float, float]],
            camera: vtk.vtkCamera,
            view_vec: Sequence[float],
    ) -> Sequence[tuple[float, float, float]]:
        """
        Project user-selected world points onto a plane passing through
        the volume center with normal equal to the view direction.

        This makes the clipping loop lie around the center of the volume
        instead of near the front surface.

        :param world_points: User-selected world points.
        :param camera: camera object.
        :param view_vec: view direction vector.
        """
        cam_pos = camera.GetPosition()
        center = self._get_clip_plane_center(camera)

        cx, cy, cz = center
        ex, ey, ez = cam_pos
        nx, ny, nz = view_vec

        projected: list[tuple[float, float, float]] = []
        for px, py, pz in world_points:
            dx = px - ex
            dy = py - ey
            dz = pz - ez

            denom = nx * dx + ny * dy + nz * dz
            if abs(denom) < 1e-6:
                projected.append((px, py, pz))
                continue
            num = nx * (cx - ex) + ny * (cy - ey) + nz * (cz - ez)
            t = num / denom

            qx = ex + t * dx
            qy = ey + t * dy
            qz = ez + t * dz
            projected.append((qx, qy, qz))
        return projected