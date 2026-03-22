from __future__ import annotations

import enum
import logging
from xml.sax.handler import property_interning_dict

import vtk
from PySide6 import QtCore

from qv.core.window_settings import WindowSettings
from qv.viewers.base_viewer import BaseViewer
from qv.viewers.interactor_styles.mpr_interactor_style import MprInteractorStyle

logger = logging.getLogger(__name__)


class MprPlane(enum.Enum):
    """MPR plane enumeration."""

    AXIAL = "axial"
    CORONAL = "coronal"
    SAGITTAL = "sagittal"


# Direction cosines for vtkImageReslice.SetResliceAxesDirectionCosines(...)
# (x_axis, y_axis, z_axis) as 3x3 row-major values.
PLANE_AXES: dict[MprPlane, tuple[float, float, float, float, float, float, float, float, float]] = {
    MprPlane.AXIAL: (
        1.0, 0.0, 0.0,
        0.0, -1.0, 0.0,
        0.0, 0.0, -1.0,
    ),
    MprPlane.CORONAL: (
        -1.0, 0.0, 0.0,
        0.0, 0.0, 1.0,
        0.0, 1.0, 0.0,
    ),
    MprPlane.SAGITTAL: (
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
        1.0, 0.0, 0.0,
    ),
}


PLANE_AXES_INDEX: dict[MprPlane, int] = {
    MprPlane.AXIAL: 2,
    MprPlane.CORONAL: 1,
    MprPlane.SAGITTAL: 0,
}

# Crosshair uses other viewers' current slice positions.
# Order is (vertical_line_source_lane, horizontal_line_source_plane).
CROSSHAIR_REFERENCE_PLANE: dict[MprPlane, tuple[MprPlane, MprPlane]] = {
    MprPlane.AXIAL: (MprPlane.SAGITTAL, MprPlane.CORONAL),
    MprPlane.CORONAL: (MprPlane.SAGITTAL, MprPlane.AXIAL),
    MprPlane.SAGITTAL: (MprPlane.CORONAL, MprPlane.AXIAL),
}


class MprViewer(BaseViewer):
    """2D MPR viewer."""

    sliceChanged = QtCore.Signal(object, int)

    def __init__(
            self,
            settings_manager=None,
            parent=None,
            *,
            plane: MprPlane = MprPlane.AXIAL,
    ) -> None:
        """
        Initialize an MPR viewer bound to a fixed anatomical plane by default.

        The viewer owns its own:
        - slice position
        - WW/WL state
        - camera state
        - crosshair overlay

        The crosshair itself is display-only. It reflects slice positions held by
        sibling viewers and does not modify any slice state.
        """
        self._image_data: vtk.vtkImageData | None = None
        self._plane: MprPlane = plane
        self._slice_index: int = 0
        self._slice_min: int = 0
        self._slice_max: int = 0

        self._reslice: vtk.vtkImageReslice | None = None
        self._wl_map: vtk.vtkImageMapToWindowLevelColors | None = None
        self._image_actor: vtk.vtkImageActor | None = None
        self._interactor_style: vtk.vtkInteractorStyleImage | None = None

        self._plane_overlay_actor: vtk.vtkTextActor | None = None
        self._crosshair_line_source: dict[str, vtk.vtkLineSource] = {}
        self._crosshair_actor: dict[str, vtk.vtkActor] = {}
        self._crosshair_slice_refs: dict[MprPlane, int | None] = {
            MprPlane.AXIAL: None,
            MprPlane.CORONAL: None,
            MprPlane.SAGITTAL: None,
        }
        self._crosshair_visible: bool = False

        self.delta_per_pixel: float = 1.0

        super().__init__(settings_manager, parent)

        self._init_plane_overlay()
        self._init_crosshair_overlay()
        self._setup_pipeline()
        self._sync_plane_overlay_text()

    @property
    def plane(self) -> MprPlane:
        """Return the currently assigned anatomical plane."""
        return  self._plane

    @property
    def plane_label(self) -> str:
        """Return the label for the current plane."""
        return self._plane.value.title()

    @property
    def slice_index(self) -> int:
        """Return the current slice index."""
        return self._slice_index

    def _init_plane_overlay(self) -> None:
        """Create a compact top-left overlay for the current plane."""
        actor = vtk.vtkTextActor()
        actor.SetInput("")

        text_prop = actor.GetTextProperty()
        text_prop.SetFontFamilyToCourier()
        text_prop.SetFontSize(14)
        text_prop.SetColor(0.95, 0.95, 0.30)
        text_prop.SetBold(True)
        text_prop.SetItalic(False)
        text_prop.SetShadow(True)
        text_prop.SetJustificationToLeft()
        text_prop.SetVerticalJustificationToTop()

        actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        actor.SetPosition(0.02, 0.98)

        self.overlay_renderer.AddActor(actor)
        self._plane_overlay_actor = actor

    def _init_crosshair_overlay(self) -> None:
        """
        Create world-space crosshair actors.

        The overlay renderer shares the main camera so the crosshair stays aligned
        with the resliced image while remaining visualy above it.
        """
        self.overlay_renderer.SetActiveCamera(self.renderer.GetActiveCamera())

        for name, color in (
            ("vertical", (1.0, 0.35, 0.35)),
            ("horizontal", (0.35, 1.0, 1.0)),
        ):
            line_source = vtk.vtkLineSource()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(line_source.GetOutputPort())

            actor = vtk.vtkActor()
            actor.SetMapper(mapper)

            prop = actor.GetProperty()
            prop.SetColor(*color)
            prop.SetLineWidth(1)
            prop.LightingOff()

            actor.VisibilityOff()
            self.overlay_renderer.AddActor(actor)

            self._crosshair_line_source[name] = line_source
            self._crosshair_actor[name] = actor

    def _format_plane_overlay_text(self) -> str:
        """
        Build a stable viewer label for pahsae 2.

        The plane name is always shown. Slice numbering is 1-based in the UI so
        users can visually compare panes without thinking about zero-based.
        """
        if self.get_slice_count() <= 0:
            return self.plane_label

        visible_slice = self._slice_index - self._slice_min + 1
        return f"{self.plane_label} Slice {visible_slice} / {self.get_slice_count()}"

    def _sync_plane_overlay_text(self) -> None:
        """Reresh the identification overlay after plane or slice changes."""
        if self._plane_overlay_actor is None:
            return
        self._plane_overlay_actor.SetInput(self._format_plane_overlay_text())

    def _setup_pipeline(self) -> None:
        """Build VTK image pipeline for MPR viewer."""
        self._reslice = vtk.vtkImageReslice()
        self._reslice.SetOutputDimensionality(2)
        self._reslice.SetInterpolationModeToLinear()
        self._reslice.SetAutoCropOutput(True)

        # Prevent warnings from unset input during startup.
        dummy = vtk.vtkImageData()
        dummy.SetDimensions(1, 1, 1)
        dummy.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
        self._reslice.SetInputData(dummy)

        self._wl_map = vtk.vtkImageMapToWindowLevelColors()
        self._wl_map.SetInputConnection(self._reslice.GetOutputPort())

        self._image_actor = vtk.vtkImageActor()
        self._image_actor.GetMapper().SetInputConnection(self._wl_map.GetOutputPort())

        self.renderer.AddActor(self._image_actor)
        self.renderer.ResetCamera()

    def setup_interactor_style(self) -> None:
        """Use image interactor style and bindd mouse-wheel slice navigation."""
        self._interactor_style = MprInteractorStyle(self)
        self.interactor.SetInteractorStyle(self._interactor_style)


    def load_data(self, image_data: vtk.vtkImageData) -> None:
        """BaseViewer abstract method implementation."""
        self.set_image_data(image_data)

    def _apply_window_settings(self, setting: WindowSettings) -> bool:
        if self._wl_map is None:
            return False

        self._wl_map.SetWindow(setting.width)
        self._wl_map.SetLevel(setting.level)
        self._wl_map.Modified()
        logger.debug("WL/WW map applied: %.1f, %.1f",
                     self._wl_map.GetLevel(), self._wl_map.GetWindow())
        return True

    @property
    def image_data(self) -> vtk.vtkImageData | None:
        """Expose loaded image  data for interactor-style checks."""
        return self._image_data

    def _get_scalar_range(self) -> tuple[float, float] | None:
        """Return the current scalar range when image data is loaded."""
        if self._image_data is None:
            return None
        return self._image_data.GetScalarRange()

    def _build_initial_window_settings(
            self,
            scalar_range: tuple[float, float],
    ) -> WindowSettings:
        """Create initial WW/WL using the same policy as VolumeViewer."""
        min_scalar, max_scalar = scalar_range
        scalar_width = max(1.0, max_scalar - min_scalar)
        level = round((min_scalar + max_scalar) / 2.0)
        width = round(max(1.0, min(scalar_width, 1024.0)))
        return WindowSettings(level=level, width=width)

    def set_window_settings(
            self,
            settings: WindowSettings,
            *,
            emit_signal: bool = True,
            render: bool = True,
    ) -> None:
        """Set WW/WL via BaseViewer contract after clamping to loaded image data."""
        scalar_range = self._get_scalar_range()
        if scalar_range is None:
            logger.warning("Cannot set window settings: image not loaded.")
            return

        clamped = settings.clamp(scalar_range)
        if clamped == self._window_settings:
            return

        super().set_window_settings(clamped, emit_signal=emit_signal, render=render)

    def set_image_data(self, image_data: vtk.vtkImageData) -> None:
        """
        Set the shared vtkImageData and initialize this viewer's own slice state.

        Each MPR viewer keeps its own slice position, camera, and WW/WL state
        even when multiple viewers point at the same vtkImageData instance.
        """
        if self._reslice is None or self._wl_map is None:
            return

        self._image_data = image_data
        self._reslice.SetInputData(image_data)
        logger.info("MPR image data loaded for %s", self._plane.value)

        self.set_window_settings(
            self._build_initial_window_settings(self._image_data.GetScalarRange()),
            emit_signal=False,
            render=False,
        )

        self._recompute_slice_range()
        self._slice_index = (self._slice_min + self._slice_max) // 2

        self._update_reslice()
        self._setup_camera(self._plane)
        self._sync_plane_overlay_text()
        self._refresh_crosshair_overlay(render=False)
        self.update_view()
        self.dataLoaded.emit()

    def _recompute_slice_range(self) -> None:
        """Recompute valid slice index range from current image and plane."""
        if self._image_data is None:
            self._slice_min = 0
            self._slice_max = 0
            return

        extent = self._image_data.GetExtent()
        axis = PLANE_AXES_INDEX[self._plane]
        self._slice_min = int(extent[2 * axis])
        self._slice_max = int(extent[2 * axis + 1])

    def set_plane(self, plane: MprPlane) -> None:
        """
        Switch current MPR plane and reset slice to the new center.

        This path is mainly kept ffor single-MPR mode. In the 4-up layout each
        viewer is expected to stay on its assigned plane.
        """
        if self._plane == plane:
            return
        self._plane = plane

        if self._image_data is None:
            self._sync_plane_overlay_text()
            return

        self._recompute_slice_range()
        self._slice_index = (self._slice_min + self._slice_max) // 2

        self._update_reslice()
        self._setup_camera(self._plane)
        self._sync_plane_overlay_text()
        self._refresh_crosshair_overlay(render=False)
        self.update_view()

        logger.info("MPR plane switched to %s", plane)
        self.sliceChanged.emit(self._plane, self._slice_index)

    def _update_reslice(self) -> None:
        """Update the reslice parameters."""
        if self._reslice is None or self._image_data is None:
            return

        self._reslice.SetResliceAxesDirectionCosines(*PLANE_AXES[self._plane])

        extent = self._image_data.GetExtent()
        spacing = self._image_data.GetSpacing()
        origin = self._image_data.GetOrigin()

        cx = origin[0] + (extent[0] + extent[1]) / 2.0 * spacing[0]
        cy = origin[1] + (extent[2] + extent[3]) / 2.0 * spacing[1]
        cz = origin[2] + (extent[4] + extent[5]) / 2.0 * spacing[2]

        world_origin = [cx, cy, cz]

        axis = PLANE_AXES_INDEX[self._plane]
        world_origin[axis] = origin[axis] + self._slice_index * spacing[axis]

        self._reslice.SetResliceAxesOrigin(
            world_origin[0],
            world_origin[1],
            world_origin[2],
        )
        self._reslice.Modified()
        self._reslice.Update()

        # Display Extent をリセットして全体を表示させる
        if self._image_actor is not None:
            out = self._reslice.GetOutput()
            if out is not None:
                we = out.GetExtent()
                self._image_actor.SetDisplayExtent(
                    we[0], we[1], we[2], we[3], we[4], we[5]
                )

    def _get_display_bounds(self) -> tuple[float, float, float, float, float, float] | None:
        """
        Return bounds of the currently displayed reslice output.

        Crosshair and camera setup must use the displayed slice space rather than
        the source volume bounds, otherwise the overlay and camera drift apart.
        """
        if self._image_actor is None:
            return None

        bounds = self._image_actor.GetBounds()
        if bounds is None:
            return None

        # Guard against uninitializecd / invalid actor bounds.
        if not all(abs(value) < 1e300 for value in bounds):
            return None

        return bounds

    def _setup_camera(self, plane: MprPlane) -> None:
        """
        Configure the camera for the currently displayed 2D reslice output.

        At this stage the camera setup is shared across all planes because each
        vtkImageReslice output is displayed as a 2D image actor in the viewer.
        The ``plane`` argument is kept to preserve the public/internal contract
        and to make future plane-specific tuning straightforward.
        """
        bounds = self._get_display_bounds()
        if bounds is None:
            logger.warning("Camera setup skipped: no display bounds.")
            return

        width = max(bounds[1] - bounds[0], 1.0)
        height = max(bounds[3] - bounds[2], 1.0)
        distance = max(width, height) * 2.0

        center = (
            0.5 * (bounds[0] + bounds[1]),
            0.5 * (bounds[2] + bounds[3]),
            0.5 * (bounds[4] + bounds[5]),
        )

        camera = self.renderer.GetActiveCamera()
        camera.SetParallelProjection(True)
        camera.SetFocalPoint(*center)
        camera.SetPosition(center[0], center[1], center[2] + distance)
        # Keep camera direction on +Z (stable), and flip vertical orientation only.
        camera.SetViewUp(0.0, -1.0, 0.0)
        camera.OrthogonalizeViewUp()

        self.renderer.ResetCamera()
        self.renderer.ResetCameraClippingRange()
        self.overlay_renderer.ResetCameraClippingRange()

        logger.debug(
            "[MprViewer:%s] Camera aligned for plane=%s with display bounds=%s",
            self._plane.value,
            plane.value,
            bounds,
        )

    def set_slice_index(self, index: int) -> None:
        """Set the current slice index for the active plane and refresh the view.

        The inpt index is clamped to the valid range: [_slice_min, _slice_max].
        """
        if self._image_data is None:
            logger.debug("set_slice_index ignored because imag is not loaded.")
            return

        clamped_index = max(self._slice_min, min(int(index), self._slice_max))
        if clamped_index == self._slice_index:
            return

        self._slice_index = clamped_index
        self._update_reslice()
        self._setup_camera(self._plane)
        self._sync_plane_overlay_text()
        self._refresh_crosshair_overlay(render=False)
        self.update_view()

        logger.debug("[MprViewer:%s] Slice index set to %s", self._plane.value, clamped_index)
        self.sliceChanged.emit(self._plane, self._slice_index)

    def scroll_slice(self, delta: int) -> None:
        """Move slice index by a relative amount (e.g. +1, -1). """
        if self._image_data is None:
            logger.debug("scroll_slice ignored because imag is not loaded.")
            return

        self.set_slice_index(self._slice_index + int(delta))

    def get_slice_count(self) -> int:
        """Return the number of slices in the current plane."""
        if self._image_data is None:
            return 0

        # extent は両端を含むため、枚数は(max - min + 1)
        return self._slice_max - self._slice_min + 1

    def adjust_window_settings(self, dx: int, dy: int) -> None:
        """Adjust window settings by drag delta (dx -> width, dy -> level)."""
        scalar_range = self._get_scalar_range()
        if scalar_range is None:
            return

        current = self.window_settings
        if current is None:
            return

        adjusted = self._window_settings.adjust(
            delta_width=dx * self.delta_per_pixel,
            delta_level=-dy * self.delta_per_pixel,
            scalar_range=scalar_range,
        )
        self.set_window_settings(adjusted)

    def set_crosshair_visible(self, visible: bool, *, render: bool = True) -> None:
        """
        Enable or disable crosshair display for this viewer.

        The overlay state is distinct from slice state; turning the overlay off
        never mutates the viewer's current slice.
        """
        if self._crosshair_visible == visible:
            return

        self._crosshair_visible = visible
        logger.debug("[MprViewer:%s] Crosshair visility -> %s", self._plane.value, visible)
        self._refresh_crosshair_overlay(render=render)

    def clear_crosshair_reference(self, *, render: bool = True) -> None:
        """Clear stored sibling-slice reference and hide crosshair lines."""
        for plane in self._crosshair_slice_refs:
            self._crosshair_slice_refs[plane] = None
        self._refresh_crosshair_overlay(render=render)

    def set_crosshair_slice_reference(
            self,
            plane: MprPlane,
            slice_index: int | None,
            *,
            render: bool = True,
    ) -> None:
        """
        Store another viewer's current slice for crosshair rendering.

        Theviewer intentionally ignores refrences for its own plane because a
        pane never draws a crosshair from its own slice.
        """
        if plane == self._plane:
            return

        normalized = None if slice_index is None else int(slice_index)
        if self._crosshair_slice_refs[plane] == normalized:
            return

        self._crosshair_slice_refs[plane] = normalized
        logger.debug(
            "[MprViewer:%s] Crosshair reference updated from %s -> %s",
            self._plane.value,
            plane.value,
            normalized,
        )
        self._refresh_crosshair_overlay(render=render)

    def _set_crosshair_actor_visibility(self, visible: bool) -> None:
        """Show or hide both crosshair line actors."""
        for actor in self._crosshair_actor.values():
            actor.SetVisibility(1 if visible else 0)

    def _slice_index_to_world(self, plane: MprPlane, slice_index: int) -> float:
        """Convert a slice index on the given plane to world corrdinate."""
        if self._image_data is None:
            raise RuntimeError("Image data not loaded.")

        extent = self._image_data.GetExtent()
        spacing = self._image_data.GetSpacing()
        origin = self._image_data.GetOrigin()

        axis = PLANE_AXES_INDEX[plane]
        min_index = int(extent[2 * axis])
        max_index = int(extent[2 * axis + 1])
        clamped = max(min_index, min(int(slice_index), max_index))
        return origin[axis] + clamped * spacing[axis]

    def _build_crosshair_world_position(self) -> tuple[float, float, float] | None:
        """
        Build the crosshair intersection point in source-world coordinates.

        World space is the canonical source of truth. Each viewer then converts
        that point into its own displayed slice space.
        """
        vertical_plane, horizontal_plane = CROSSHAIR_REFERENCE_PLANE[self._plane]
        vertical_index = self._crosshair_slice_refs[vertical_plane]
        horizontal_index = self._crosshair_slice_refs[horizontal_plane]

        if vertical_index is None or horizontal_index is None:
            logger.debug("[MprViewer:%s] Index is None, skipping crosshair rendering.",
                         self._plane.value)
            return None

        if self._plane == MprPlane.AXIAL:
            return (
                self._slice_index_to_world(MprPlane.SAGITTAL, vertical_index),  # x
                self._slice_index_to_world(MprPlane.CORONAL, horizontal_index), # y
                self._slice_index_to_world(MprPlane.AXIAL, self._slice_index),  # z
            )
        elif self._plane == MprPlane.CORONAL:
            return (
                self._slice_index_to_world(MprPlane.SAGITTAL, vertical_index),
                self._slice_index_to_world(MprPlane.CORONAL, self._slice_index),
                self._slice_index_to_world(MprPlane.AXIAL, horizontal_index),
            )
        else:
            return (
                self._slice_index_to_world(MprPlane.SAGITTAL, self._slice_index),
                self._slice_index_to_world(MprPlane.CORONAL, vertical_index),
                self._slice_index_to_world(MprPlane.AXIAL, horizontal_index),
            )

    def _build_crosshair_segments(
            self,
    ) -> dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] | None:
        """
        Build world-space line segments for the current crosshair state.

        Returns:
            dict | None ``{"vertical": (p1, p2), "horizontal": (p1, p2)}``
            when both required sibling slice references are present, otherwise ``None``.
        """
        if self._image_data is None:
            return None


        display_bounds = self._get_display_bounds()
        if display_bounds is None:
            logger.debug("[MprViewer:%s] Display bounds is None, skipping crosshair rendering.",
                         self._plane.value)
            return None

        crosshair_world = self._build_crosshair_world_position()
        if crosshair_world is None:
            logger.debug("[MprViewer:%s] Crosshair world position is None, skipping crosshair rendering.",
                         self._plane.value)
            return None

        corsshair_display = self._world_to_display_point(crosshair_world)
        if crosshair_world is None:
            logger.debug("[MprViewer:%s] Crosshair display position is None, skipping crosshair rendering.",
                         self._plane.value)
            return None

        display_x, display_y, display_z = corsshair_display
        plane_z = 0.5 * (display_bounds[4] + display_bounds[5])

        logger.debug(
            "[MprViewer:%s] Crosshair world=%s display=%s bounds=%s)",
            self._plane.value,
            crosshair_world,
            corsshair_display,
            display_bounds,
        )

        return {
            "vertical": (
                (display_x, display_bounds[2], plane_z),
                (display_x, display_bounds[3], plane_z),
            ),
            "horizontal": (
            (display_bounds[0], display_y, plane_z),
            (display_bounds[1], display_y, plane_z),
            ),
        }

    def _refresh_crosshair_overlay(self, *, render: bool = True) -> None:
        """
        Rebuild and apply the crosshair overlay.

        This method updates only the overlay actors. It never changes this
        viewer's slice or any sibling slice.
        """
        segments = self._build_crosshair_segments()

        if not self._crosshair_visible or segments is None:
            self._set_crosshair_actor_visibility(False)
            if render:
                self.update_view()
            return

        for name, (point1, point2) in segments.items():
            line_source = self._crosshair_line_source[name]
            line_source.SetPoint1(*point1)
            line_source.SetPoint2(*point2)
            line_source.Modified()

        self._set_crosshair_actor_visibility(True)
        self.overlay_renderer.ResetCameraClippingRange()

        if render:
            self.update_view()

    def _get_current_reslice_axes_components(
            self,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]] | None:
        """
        Return the active reslice basis vectors and origin.

        The basis vectors come  from PLANE_AXES and define how displayed slice
        coodinates map into source-world coordinates.
        """
        if self._reslice is None or self._image_data is None:
            return None

        axes = PLANE_AXES[self._plane]
        x_axis = (axes[0], axes[1], axes[2])
        y_axis = (axes[3], axes[4], axes[5])
        z_axis = (axes[6], axes[7], axes[8])

        origin = self._reslice.GetResliceAxesOrigin()

        if origin is None:
            return None

        return x_axis, y_axis, z_axis, (origin[0], origin[1], origin[2])

    def _world_to_display_point(
            self,
            world_point: tuple[float, float, float],
    ) -> tuple[float, float, float] | None:
        """
        Convert a source-world point into the displayed slice coordinate system.

        ResliceAxes defines the displyaed slice baiss in source-world space.
        Because the basis is orthhonormal for the fixed 3-plane setup, the
        inverse mapping is just dot(wordl - origin, axis).
        """
        axes_components = self._get_current_reslice_axes_components()
        if axes_components is None:
            return None

        x_axis, y_axis, z_axis, origin = axes_components
        dx = world_point[0] - origin[0]
        dy = world_point[1] - origin[1]
        dz = world_point[2] - origin[2]

        display_x = dx  * x_axis[0] + dy * x_axis[1] + dz * x_axis[2]
        display_y = dx  * y_axis[0] + dy * y_axis[1] + dz * y_axis[2]
        display_z = dx  * z_axis[0] + dy * z_axis[1] + dz * z_axis[2]

        return display_x, display_y, display_z