import vtk
from typing import TYPE_CHECKING

from vtkmodules.vtkCommonDataModel import vtkImplicitSelectionLoop
from vtkmodules.vtkImagingStencil import vtkImplicitFunctionToImageStencil
from vtkmodules.vtkRenderingCore import vtkActor

import vtk_helpers

if TYPE_CHECKING:
    # 型チェック時のみインポートする
    # 相互参照となってしまう。
    from main import VolumeViewer


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
        pt = self.picker.GetPickPosition()
        self.viewer.add_clip_point(pt)

    def OnLeftButtonDoubleClick(self, caller, event):
        """ダブルクリックでクリッピングする領域を閉じる"""
        print("Double click")
        self.viewer.clipper.finalize_clip()
        self.viewer.enter_clip_result_mode()


class QVVolumeClipper:
    """
    Add function to clip the volume for QV.
    This class has a response to the clipping function.
    """
    def __init__(self, viewer: "VolumeViewer"):
        self.viewer = viewer
        self.clip_points = []  # ユーザーが打った点
        self.backup_image = None

        self.mapper = vtk.vtkGPUVolumeRayCastMapper()
        self.clip_loop: vtkImplicitSelectionLoop | None = None  # vtkImplicitSelectionLoop
        self.stenciler: vtkImplicitFunctionToImageStencil | None = None
        self.preview_extrude_actor: vtkActor | None = None

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

        print("[Mask] type=", mask_img.GetScalarTypeAsString(),
              "range=", mask_img.GetScalarRange(),
              "extent=", mask_img.GetExtent(),
              "spacing=", mask_img.GetSpacing(),
              "origin=", mask_img.GetOrigin())
        # 期待: type= UnsignedChar / range= (0.0, 255.0)

        return mask_img


    def add_point(self, pt):
        """Add a clipping point."""
        self.clip_points.append(pt)

    def finalize_clip(self):
        # 入力画像の確保（バックアップ）
        current_image = self._get_current_image_from_viewer()
        if current_image is None:
            # 入力が無ければ以降の処理はできない
            print("[Clip] No input volume available. Aborting finalize_clip().")
            self.backup_image = None
            self.clip_loop = None
            return

        # クリップ点は最低3点必要（ループ）
        if len(self.clip_points) < 3:
            print(f"[Clip] Need at least 3 points to form a loop. Got {len(self.clip_points)}.")
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

        # カメラの視線ベクトルに沿って、各店フォーカルポイントに垂直な平面へ正射影する
        vtk_points = vtk.vtkPoints()
        for pt in self.clip_points:
            vec_fp = vtk_helpers.direction_vector(pt, fp)
            d = sum(vec_fp[i] * view_vec[i] for i in range(3))
            proj_pt = [pt[i] - d * view_vec[i] for i in range(3)]
            vtk_points.InsertNextPoint(proj_pt)

        # ImplicitSelectionLoop を作成
        self.clip_loop = vtk.vtkImplicitSelectionLoop()
        self.clip_loop.SetLoop(vtk_points)

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

        extrude = vtk.vtkLinearExtrusionFilter()
        extrude.SetInputData(poly)
        extrude.SetExtrusionTypeToNormalExtrusion()
        extrude.SetVector(view_vec)
        extrude.SetScaleFactor(depth)
        extrude.CappingOn()
        extrude.Update()

        # Make Preview
        mapper3D = vtk.vtkPolyDataMapper()
        mapper3D.SetInputConnection(extrude.GetOutputPort())
        self.preview_extrude_actor = vtk.vtkActor()
        self.preview_extrude_actor.SetMapper(mapper3D)
        self.preview_extrude_actor.GetProperty().SetColor(0.5, 0.6, 0)
        self.preview_extrude_actor.GetProperty().SetOpacity(1.0)

        print("[Finalize] clip_points=", len(self.clip_points))
        print("[Finalize] image_extent=", self.backup_image.GetExtent())
        print("[Finalize] camera_fp=", fp, "view_vec=", view_vec)

        self.viewer.renderer.AddActor(self.preview_extrude_actor)
        self.viewer.preview_extrude_actor = self.preview_extrude_actor
        self.viewer.ui.vtk_widget.GetRenderWindow().Render()

    # A5A800
    def cancel(self):
        """Cancel clipping and take back the original volume."""
        print("[Clip] Cancelled.")
        if self.backup_image:
            mapper = vtk.vtkGPUVolumeRayCastMapper()
            mapper.SetInputData(self.backup_image)
            self.viewer.volume.SetMapper(mapper)
            self.viewer.ui.vtk_widget.GetRenderWindow().Render()
        self.reset()

    def apply(self):
        # 状態検証
        if self.backup_image is None:
            # 可能なら現在の viewer から遅延取得
            current_image = self._get_current_image_from_viewer()
            if current_image is not None:
                self.backup_image = vtk.vtkImageData()
                self.backup_image.DeepCopy(current_image)
                print("[Clip] backup_image was None. Recovered from current volume.")
            else:
                print("[Clip] No backup image and no current volume. Aborting apply().")
                self.reset()
                return

        if self.clip_loop is None:
            print("[Clip] clip_loop is None. Did you finalize the clip with enough points?")
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
        self.backup_image = None
        self.clip_loop = None
        self.clip_points.clear()

        # viewer 側の可視化もリセット
        if hasattr(self.viewer, "clipping_points"):
            self.viewer.clipping_points.clear()
        if hasattr(self.viewer, "update_clipper_visualization"):
            self.viewer.update_clipper_visualization()