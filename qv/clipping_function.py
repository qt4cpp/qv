import logging

import vtk
from typing import TYPE_CHECKING, Sequence

from vtkmodules.vtkCommonDataModel import vtkImplicitSelectionLoop
from vtkmodules.vtkImagingStencil import vtkImplicitFunctionToImageStencil
from vtkmodules.vtkRenderingCore import vtkActor

import vtk_helpers
from log_util import log_io
from qv.region_selection import RegionSelectionController

if TYPE_CHECKING:
    # 型チェック時のみインポートする
    # 相互参照となってしまう。
    from main import VolumeViewer


logger = logging.getLogger(__name__)


class ClippingInteractorStyle(vtk.vtkInteractorStyleTrackballCamera):
    """Clipping interactor style for the volume viewer."""
    def __init__(self, viewer):
        super().__init__()
        self.viewer = viewer

        self.SetCurrentRenderer(viewer.renderer)
        self.picker = vtk.vtkCellPicker()
        self.picker.SetTolerance(0.005)

        self.AddObserver("LeftButtonPressEvent", self.OnLeftButtonDown)
        self.AddObserver("LeftButtonDoubleClickEvent", self.OnLeftButtonDoubleClick)

    def OnLeftButtonDown(self, caller, event):
        """マウスが左クリックされた点を3D座標で受け取り、viewer 経由でClipperに渡す"""
        x, y = self.GetInteractor().GetEventPosition()
        self.picker.Pick(x, y, 0, self.viewer.renderer)
        world_pt = self.picker.GetPickPosition()
        self.viewer.add_clip_point((float(x), float(y)), world_pt)

    def OnLeftButtonDoubleClick(self, caller, event):
        """ダブルクリックでクリッピングする領域を閉じる"""
        self.viewer.clipper.complete_selection()


class QVVolumeClipper:
    """
    Add function to clip the volume for QV.
    This class has a response to the clipping function.
    """
    def __init__(self, viewer: "VolumeViewer", overlay_renderer: vtk.vtkRenderer):
        self.viewer = viewer
        self.overlay_renderer = overlay_renderer

        self.clip_points_display: list[tuple[float, float]] = []
        self.clip_points_world: list[tuple[float, float, float]] = []

        self.backup_image = None

        self.mapper = vtk.vtkGPUVolumeRayCastMapper()
        self.clip_loop: vtkImplicitSelectionLoop | None = None
        self.stenciler: vtkImplicitFunctionToImageStencil | None = None
        self.preview_extrude_actor: vtkActor | None = None

        self.selection_active = False
        self.region_selection = RegionSelectionController(
            viewer.ui.vtk_widget.GetRenderWindow(),
            viewer.renderer,
            overlay_renderer,
        )
        self.region_selection.set_closed_callback(self._on_region_closed)

    def _get_current_image_from_viewer(self) -> vtk.vtkImageData | None:
        """viewer.volume から現在の vtkImageData を取得。取得できなければ None。"""
        if not getattr(self.viewer, "volume", None):
            return None
        mapper = self.viewer.volume.GetMapper()
        if not mapper:
            return None
        inp = mapper.GetInput()
        return inp

    def _build_binary_mask_from_clip(self) -> vtk.vtkImageData | None:
        """
        clip_loopで囲まれた領域を0, それ以外を255とするバイナリマスク(vtkImageData) を生成する。
        self.backup_image の幾何情報と一致させる。
        :return: Created Mask image(UnsignedChar, values: 0, 255). When failed, return None.
        """
        if self.backup_image is None or self.clip_loop is None:
            return None

        # clip_loopからステンシルを生成。必ずオリジナルと幾何を揃える。でないと位置がずれる。
        stenciler = vtk.vtkImplicitFunctionToImageStencil()
        stenciler.SetInput(self.clip_loop)
        stenciler.SetOutputSpacing(self.backup_image.GetSpacing())
        stenciler.SetOutputOrigin(self.backup_image.GetOrigin())
        stenciler.SetOutputWholeExtent(self.backup_image.GetExtent())
        stenciler.Update()

        # まず全体を255で満たす. 255: outside, 0: inside
        ones = vtk.vtkImageThreshold()
        ones.SetInputData(self.backup_image)
        ones.ReplaceInOn()
        ones.ReplaceOutOn()
        ones.ThresholdBetween(-1e38, 1e38)
        ones.SetInValue(255)
        ones.SetOutValue(255)
        ones.SetOutputScalarTypeToUnsignedChar()
        ones.Update()

        # Sets 0 in Stenciler, outside 1
        img_stencil = vtk.vtkImageStencil()
        img_stencil.SetInputData(ones.GetOutput())
        img_stencil.SetStencilConnection(stenciler.GetOutputPort())
        img_stencil.ReverseStencilOn()
        img_stencil.SetBackgroundValue(0)
        img_stencil.Update()

        mask_img = vtk.vtkImageData()
        mask_img.ShallowCopy(img_stencil.GetOutput())

        logging.debug("[Mask] type=%s range=%s extent=%s spacing=%s origin=%s",
                      mask_img.GetScalarTypeAsString(),
                      mask_img.GetScalarRange(),
                      mask_img.GetExtent(),
                      mask_img.GetSpacing(),
                      mask_img.GetOrigin())
        # 期待: type= UnsignedChar / range= (0.0, 255.0)

        return mask_img

    def start_region_selection(self) -> None:
        self.reset()
        self.selection_active = True
        self.region_selection.enable()

    def stop_region_selection(self) -> None:
        if self.region_selection.is_enabled():
            self.region_selection.disable()
        self.selection_active = False

    def add_selection_point(self, display_xy: tuple[float, float],
                            world_pt: tuple[float, float, float]) -> None:
        if not self.selection_active:
            return
        self.region_selection.add_display_point(display_xy[0], display_xy[1], world_pt)

    def complete_selection(self) -> None:
        if not self.selection_active:
            return
        self.region_selection.complete()

    def on_camera_updated(self) -> None:
        if self.selection_active:
            self.viewer.update_clipper_visualization()

    def get_preview_world_points(self) -> list[tuple[float, float, float]]:
        if self.selection_active:
            return self.region_selection.get_world_points()
        return list(self.clip_points_world)

    def is_selection_active(self) -> bool:
        return self.selection_active

    def _on_region_closed(
        self,
        display_points: Sequence[tuple[float, float]],
        world_points: Sequence[tuple[float, float, float]],
    ) -> None:
        if len(display_points) < 3 or len(world_points) < 3:
            self.stop_region_selection()
            self.reset()
            return

        self.clip_points_display = list(display_points)
        self.clip_points_world = list(world_points)
        self.stop_region_selection()
        self.viewer.update_clipper_visualization()

        previous_loop = self.clip_loop
        self.finalize_clip()

        if self.clip_loop is not None and self.clip_loop is not previous_loop:
            self.viewer.enter_clip_result_mode()

    @log_io(level=logging.INFO)
    def finalize_clip(self):
        # 入力画像の確保（バックアップ）
        current_image = self._get_current_image_from_viewer()
        if current_image is None:
            # 入力が無ければ以降の処理はできない
            logging.info("[Clip] No input volume available. Aborting finalize_clip().")
            self.backup_image = None
            self.clip_loop = None
            return

        # クリップ点は最低3点必要（ループ）
        if len(self.clip_points_display) < 3:
            logging.info(f"[Clip] Need at least 3 points to form a loop. Got {len(self.clip_points_display)}.")
            self.backup_image = None
            self.clip_loop = None
            return

        self.backup_image = vtk.vtkImageData()
        self.backup_image.DeepCopy(current_image)

        # -----------------------------
        # Get the information of camera
        cam = self.viewer.renderer.GetActiveCamera()
        fp = cam.GetFocalPoint()
        view_vec = vtk_helpers.direction_vector(cam.GetPosition(), fp)
        norm = vtk_helpers.calculate_norm(view_vec)
        # norm が 0 の場合を防ぐ
        if norm == 0:
            print("[Clip] Camera direction vector has zero length. Aborting finalize_clip().")
            self.backup_image = None
            self.clip_loop = None
            return
        view_vec = [v / norm for v in view_vec]

        world_points = list(self.clip_points_world)
        if len(world_points) < 3:
            logging.info("[Clip] Projected points are insufficeint to build a loop.")
            self.backup_image = None
            self.clip_loop = None
            return

        vtk_points = vtk.vtkPoints()
        for pt in world_points:
            vtk_points.InsertNextPoint(*pt)

        # ImplicitSelectionLoop を作成
        self.clip_loop = vtk.vtkImplicitSelectionLoop()
        self.clip_loop.SetLoop(vtk_points)
        self.clip_loop.SetNormal(*view_vec)  # 投影法線を明示的に設定して平行にする
        self.clip_loop.AutomaticNormalGenerationOff()  # 自動法線計算を無効化する。

        # -------------- 3D Preview -----------------
        # backup_image はここまでで必ず存在している前提
        bounds = self.backup_image.GetBounds()
        depth = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])

        poly = vtk.vtkPolyData()
        poly.SetPoints(vtk_points)
        lines = vtk.vtkCellArray()
        num_pts = vtk_points.GetNumberOfPoints()
        # ループ線分を形成
        lines.InsertNextCell(num_pts + 1)
        for i in range(num_pts):
            lines.InsertCellPoint(i)
        lines.InsertCellPoint(0)
        poly.SetLines(lines)

        # Extrude selection loop in both view directions for preview volume
        extrude_forward = vtk.vtkLinearExtrusionFilter()
        extrude_forward.SetInputData(poly)
        extrude_forward.SetExtrusionTypeToNormalExtrusion()
        extrude_forward.SetVector(*view_vec)
        extrude_forward.SetScaleFactor(depth * 2)
        extrude_forward.CappingOn()
        extrude_forward.Update()

        # 手前から奥に押し出す
        # reverse_view_vec = [-v for v in view_vec]
        # extrude_backward = vtk.vtkLinearExtrusionFilter()
        # extrude_backward.SetInputData(poly)
        # extrude_backward.SetExtrusionTypeToNormalExtrusion()
        # extrude_backward.SetVector(*reverse_view_vec)
        # extrude_backward.SetScaleFactor(depth)
        # extrude_backward.CappingOn()
        # extrude_backward.Update()

        # combined_preview = vtk.vtkAppendPolyData()
        # combined_preview.AddInputConnection(extrude_forward.GetOutputPort())
        # combined_preview.AddInputConnection(extrude_backward.GetOutputPort())
        # combined_preview.Update()

        # Make Preview
        mapper3D = vtk.vtkPolyDataMapper()
        mapper3D.SetInputConnection(extrude_forward.GetOutputPort())
        self.preview_extrude_actor = vtk.vtkActor()
        self.preview_extrude_actor.SetMapper(mapper3D)
        self.preview_extrude_actor.GetProperty().SetColor(0.5, 0.6, 0)
        self.preview_extrude_actor.GetProperty().SetOpacity(0.95)

        logging.info("[Finalize] clip_points=%s", len(world_points))
        logging.info("[Finalize] image_extent=%s", self.backup_image.GetExtent())
        logging.info("[Finalize] camera_fp=%s view_vec=%s", fp, view_vec)

        self.viewer.renderer.AddActor(self.preview_extrude_actor)
        self.viewer.preview_extrude_actor = self.preview_extrude_actor
        self.viewer.ui.vtk_widget.GetRenderWindow().Render()

    @log_io(level=logging.INFO)
    def cancel(self):
        """Cancel clipping and take back the original volume."""
        logging.debug("canceled clipping")
        if self.backup_image:
            mapper = vtk.vtkGPUVolumeRayCastMapper()
            mapper.SetInputData(self.backup_image)
            self.viewer.volume.SetMapper(mapper)
            self.viewer.ui.vtk_widget.GetRenderWindow().Render()
        self.reset()

    @log_io(level=logging.INFO)
    def apply(self):
        # 状態検証
        if self.backup_image is None:
            # 可能なら現在の viewer から遅延取得
            current_image = self._get_current_image_from_viewer()
            if current_image is not None:
                self.backup_image = vtk.vtkImageData()
                self.backup_image.DeepCopy(current_image)
                logging.info("[Clip] backup_image was None. Recovered from current volume.")
            else:
                logging.info("[Clip] No backup image and no current volume. Aborting apply().")
                self.reset()
                return

        if self.clip_loop is None:
            logging.info("[Clip] clip_loop is None. Did you finalize the clip with enough points?")
            self.reset()
            return

        # Completely invisible with Binary Mask on GPU mapper if enabled.
        mask_img = self._build_binary_mask_from_clip()
        if mask_img is not None:
            masker = vtk.vtkImageMask()
            masker.SetInputData(self.backup_image)
            masker.SetMaskInputData(mask_img)
            masker.SetMaskedOutputValue(0)
            masker.Update()

            # クリッピングしたデータを焼き込む
            baked_img = vtk.vtkImageData()
            baked_img.DeepCopy(masker.GetOutput())

            # 新しいマッパーで焼き込み済みデータを表示
            self.mapper = vtk.vtkGPUVolumeRayCastMapper()
            self.mapper.SetInputData(baked_img)

            if hasattr(self.mapper, "SetMaskInput"):
                try:
                    self.mapper.SetMaskInput(None)
                except Exception:
                    pass

            self.viewer.volume.SetMapper(self.mapper)
            self.viewer.ui.vtk_widget.GetRenderWindow().Render()

            # 焼き込んだデータを次のデータとして使用する
            if self.backup_image is None:
                self.backup_image = vtk.vtkImageData()
            self.backup_image.DeepCopy(baked_img)

        # もし、mask_img の作成に失敗したら Stencilで0で埋めて焼き込む。
        if mask_img is None:
            self.stenciler = vtk.vtkImplicitFunctionToImageStencil()
            self.stenciler.SetInput(self.clip_loop)
            self.stenciler.SetOutputSpacing(self.backup_image.GetSpacing())
            self.stenciler.SetOutputOrigin(self.backup_image.GetOrigin())
            self.stenciler.SetOutputWholeExtent(self.backup_image.GetExtent())
            self.stenciler.Update()

            image_stencil = vtk.vtkImageStencil()
            image_stencil.SetInputData(self.backup_image)
            image_stencil.SetStencilConnection(self.stenciler.GetOutputPort())
            image_stencil.ReverseStencilOn()
            image_stencil.SetBackgroundValue(0)
            image_stencil.Update()

            baked_img = vtk.vtkImageData()
            baked_img.DeepCopy(image_stencil.GetOutput())

            self.mapper = vtk.vtkGPUVolumeRayCastMapper()
            self.mapper.SetInputData(baked_img)
            self.viewer.volume.SetMapper(self.mapper)
            self.viewer.ui.vtk_widget.GetRenderWindow().Render()

            if self.backup_image is None:
                self.backup_image = vtk.vtkImageData()
            self.backup_image.DeepCopy(baked_img)
        self.reset()

    def reset(self):
        # 3Dプレビューを消す
        if getattr(self, "preview_extrude_actor", None):
            self.viewer.renderer.RemoveActor(self.preview_extrude_actor)
            self.preview_extrude_actor = None

        # 内部状態をクリア
        self.stop_region_selection()
        self.backup_image = None
        self.clip_loop = None
        self.clip_points_display.clear()
        self.clip_points_world.clear()
        self.selection_active = False

        # viewer 側の可視化もリセット
        if hasattr(self.viewer, "clipping_points"):
            self.viewer.clipping_points.clear()
        if hasattr(self.viewer, "update_clipper_visualization"):
            self.viewer.update_clipper_visualization()
