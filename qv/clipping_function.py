import vtk
from typing import TYPE_CHECKING

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
        x, y = self.GetInteractor().GetEventPosition()
        self.picker.Pick(x, y, 0, self.viewer.renderer)
        pt = self.picker.GetPickPosition()
        self.viewer.add_clip_point(pt)

    def OnLeftButtonDoubleClick(self, caller, event):
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
        self.clip_points = []
        self.backup_image = None

        self.mapper = vtk.vtkGPUVolumeRayCastMapper()
        self.clip_loop = None
        self.stenciler = None
        self.preview_extrude_actor = None


    def add_point(self, pt):
        """Add a clipping point."""
        self.clip_points.append(pt)

    def finalize_clip(self):
        if self.viewer.volume:
            self.backup_image = vtk.vtkImageData()
            self.backup_image.DeepCopy(self.viewer.volume.GetMapper().GetInput())

        # -----------------------------
        # Get the information of camera
        cam = self.viewer.renderer.GetActiveCamera()
        fp = cam.GetFocalPoint()
        view_vec = vtk_helpers.direction_vector(cam.GetPosition(), fp)
        norm = vtk_helpers.calculate_norm(view_vec)
        view_vec = [v / norm for v in view_vec]

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
        poly = vtk.vtkPolyData()
        poly.SetPoints(vtk_points)
        lines = vtk.vtkCellArray()
        num_pts = vtk_points.GetNumberOfPoints()
        lines.InsertNextCell(num_pts)
        for i in range(num_pts):
            lines.InsertCellPoint(i)
        lines.InsertCellPoint(0)
        poly.SetLines(lines)
        extrude = vtk.vtkLinearExtrusionFilter()
        extrude.SetInputData(poly)
        extrude.SetExtrusionTypeToNormalExtrusion()
        extrude.SetVector(view_vec)
        bounds = self.backup_image.GetBounds()
        depth = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4])
        extrude.SetScaleFactor(depth)
        extrude.CappingOn()
        extrude.Update()

        # Make Translucent Preview
        mapper3D = vtk.vtkPolyDataMapper()
        mapper3D.SetInputConnection(extrude.GetOutputPort())
        self.preview_extrude_actor = vtk.vtkActor()
        self.preview_extrude_actor.SetMapper(mapper3D)
        self.preview_extrude_actor.GetProperty().SetColor(0.5, 0.6, 0)
        self.preview_extrude_actor.GetProperty().SetOpacity(0.4)
        self.viewer.renderer.AddActor(self.preview_extrude_actor)
        self.viewer.preview_extrude_actor = self.preview_extrude_actor
        self.viewer.ui.vtk_widget.GetRenderWindow().Render()

    # A5A800
    def cancel(self):
        if self.backup_image:
            mapper = vtk.vtkGPUVolumeRayCastMapper()
            mapper.SetInputData(self.backup_image)
            self.viewer.volume.SetMapper(mapper)
            self.viewer.ui.vtk_widget.GetRenderWindow().Render()
            self.reset()


    def apply(self):
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
        image_stencil.SetBackgroundValue(0)
        image_stencil.Update()

        self.mapper.SetInputData(image_stencil.GetOutput())
        self.viewer.volume.SetMapper(self.mapper)
        self.viewer.ui.vtk_widget.GetRenderWindow().Render()
        self.reset()

    def reset(self):
        if hasattr(self, 'preview_extrude_actor'):
            self.viewer.renderer.RemoveActor(self.preview_extrude_actor)

        self.backup_image = None
        self.clip_points.clear()
        self.viewer.clipping_points.clear()
        self.viewer.update_clipper_visualization()