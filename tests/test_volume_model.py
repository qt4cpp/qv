import vtk

from qv.core.volume_model import VolumeExtent, VolumeModel


def _make_test_volume(
        dims=(10, 12, 14),
        spacing=(1.0, 2.0, 3.0),
        origin=(0.5, -1.0, 2.5),
) -> vtk.vtkImageData:
    volume = vtk.vtkImageData()
    volume.SetDimensions(*dims)
    volume.SetSpacing(*spacing)
    volume.SetOrigin(*origin)
    volume.AllocateScalars(vtk.VTK_SHORT, 1)
    volume.Modified()
    return volume


def test_volume_extent_from_vtk_extent():
    """Tests volume extent from VTK extent values"""
    extent = (0, 9, 2, 13, 5, 18)
    ve = VolumeExtent.from_vtk_extent(extent)

    assert ve.x_min == 0
    assert ve.x_max == 9
    assert ve.y_min == 2
    assert ve.y_max == 13
    assert ve.z_min == 5
    assert ve.z_max == 18
    assert ve.get_dimension(0) == 10
    assert ve.get_dimension(1) == 12
    assert ve.get_dimension(2) == 14


def test_set_volume_updates_metadata():
    """Tests volume setting updates model metadata"""
    volume = _make_test_volume(dims=(8, 9, 10), spacing=(0.7, 0.8, 1.5), origin=(1.0, 2.0, 3.0))
    model = VolumeModel()
    model.set_volume(volume)

    assert model.volume is volume
    assert model.extent.x_min == 0
    assert model.extent.x_max == 7
    assert model.extent.y_min == 0
    assert model.extent.y_max == 8
    assert model.extent.z_min == 0
    assert model.extent.z_max == 9

    assert model.spacing == (0.7, 0.8, 1.5)
    assert model.origin == (1.0, 2.0, 3.0)

    scalar_range = model.scalar_range
    assert isinstance(scalar_range, tuple)
    assert len(scalar_range) == 2


def test_get_slice_range_and_count():
    """Verifies slice range and count match volume dimensions"""
    volume = _make_test_volume(dims=(5, 6, 7))
    model = VolumeModel()
    model.set_volume(volume)

    assert model.get_slice_range(0) == (0, 4)
    assert model.get_slice_range(1) == (0, 5)
    assert model.get_slice_range(2) == (0, 6)

    assert model.get_slice_count(0) == 5
    assert model.get_slice_count(1) == 6
    assert model.get_slice_count(2) == 7


def test_create_demo_volume_basic_properties():
    """Verifies demo volume has expected properties"""
    volume = VolumeModel.create_demo_volume(size=16)

    assert isinstance(volume, vtk.vtkImageData)
    assert volume.GetDimensions() == (16, 16, 16)

    # デモボリュームはZ方向の異方性を持つ設計
    assert volume.GetSpacing() == (1.0, 1.0, 2.0)

    # Scalar range が有効な数値を返すことを確認
    scalar_range = volume.GetScalarRange()
    assert len(scalar_range) == 2
    assert scalar_range[0] <= scalar_range[1]


def test_from_volume_viewer_with_source_image():
    """Tests model creation from volume viewer with image"""
    class DummyVolumeViewer:
        def __init__(self, image: vtk.vtkImageData | None):
            self._source_image = image

    volume = _make_test_volume(dims=(4, 5, 6))
    viewer = DummyVolumeViewer(volume)

    model = VolumeModel.from_volume_viewer(viewer)

    assert model.volume is volume
    assert model.get_slice_count(0) == 4
    assert model.get_slice_count(1) == 5
    assert model.get_slice_count(2) == 6


def test_from_volume_viewer_without_source_image():
    """Tests model creation from volume viewer without image"""
    class DummyVolumeViewer:
        def __init__(self, image: vtk.vtkImageData | None):
            self._source_image = image

    viewer = DummyVolumeViewer(None)

    model = VolumeModel.from_volume_viewer(viewer)

    assert model.volume is None
    assert model.get_slice_count(0) == 0
    assert model.get_slice_count(1) == 0
    assert model.get_slice_count(2) == 0
