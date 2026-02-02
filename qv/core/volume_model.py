"""
VolumeModel - Sharing Volume data model.

設計原則:
- 元ボリュームは1つの vtkImageData (canonical volume) として管理
- ビュー毎に vtkImageData を複製しない
- 等方化はオプション

等方化ボリュームを追加する場合の差し込み口:
- resampled_volume プロパティを追加
- get_volume(resampled=True/False) メソッドで切り替える
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import vtk

logger = logging.getLogger(__name__)


@dataclass
class VolumeExtent:
    """ボリュームの範囲情報"""
    x_min: int
    x_max: int
    y_min: int
    y_max: int
    z_min: int
    z_max: int

    @classmethod
    def from_vtk_extent(cls, extent: tuple[int, ...]) -> "VolumeExtent":
        return cls(
            x_min=extent[0], x_max=extent[1],
            y_min=extent[2], y_max=extent[3],
            z_min=extent[4], z_max=extent[5]
        )

    def get_dimension(self, axis: int) -> int:
        """指定軸のスライス数を返す (0=x, 1=y, 2=z)"""
        if axis == 0:
            return self.x_max - self.x_min + 1
        elif axis == 1:
            return self.y_max - self.y_min + 1
        else:
            return self.z_max - self.z_min + 1
        raise ValueError(f"Invalid axis: {axis}")


class VolumeModel:
    """
    共有ボリュームデータモデル

    単一の vtkImageData を保持し、全ビューアで共有する。
    データの複製は行わない。

    使用方法:
    1. 直接 vtkImageData を設定: set_volume(vtk_image_data)
    2. 既存 VolumeViewer から取得: from_volume_viewer(volume_viewer)

    将来拡張:
    - 等方化: _resampled_volume を追加
      -> get_volume(resampled=True_ で等方かボリュームを取得
    """

    def __init__(self) -> None:
        self._volume: vtk.vtkImageData | None = None
        self._extent: VolumeExtent | None = None
        self._spacing: tuple[float, float, float] = (1.0, 1.0, 1.0)
        self._origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._scalar_range: tuple[float, float] = (0.0, 1.0)

        # 将来拡張: 等方化ボリューム
        # self._resampled_volume: vtk.vtkImageData | None = None

    @property
    def volume(self) -> vtk.vtkImageData | None:
        """元ボリューム (canonical volume) を返す"""
        return self._volume

    @property
    def extent(self) -> VolumeExtent | None:
        return self._extent

    @property
    def spacing(self) -> tuple[float, float, float]:
        return self._spacing

    @property
    def origin(self) -> tuple[float, float, float]:
        return self._origin

    @property
    def scalar_range(self) -> tuple[float, float]:
        return self._scalar_range

    def set_volume(self, volume: vtk.vtkImageData) -> None:
        """
        ボリュームデータを設定する

        :param volume: vtkImageData （複製せずに山椒を保持する）
        :return:
        """
        self._volume = volume
        extent = volume.GetExtent()
        self._extent = VolumeExtent.from_vtk_extent(extent)
        self._spacing = volume.GetSpacing()
        self._origin = volume.GetOrigin()
        self._scalar_range = volume.GetScalarRange()

        logger.info(
            "VolumeModel: extent=%s, spacing=%s, origin=%s, scalar_range=%s",
            extent, self._spacing, self._origin, self._scalar_range
        )

    @classmethod
    def from_volume_viewer(cls, volume_viewer: "VolumeViewer") -> "VolumeModel":
        """
        既存の VolumeViewer からボリュームモデルを作成する

        VolumeViewer._source_image を参照(複製しない)

        :param cls:
        :param volume_viewer: 既存の VolumeViewer インスタンス
        :return:  VolumeModel インスタンス
        """
        model = cls()
        if volume_viewer._source_image is not None:
            model.set_volume(volume_viewer._source_image)
        return model

    def get_slice_count(self, axis: int) -> int:
        """
        指定した軸方向のスライス数を返す

        :param axis: 軸方向 0=Sagittal(X), 1=Coronal(Y), 2=Axial(Z)
        :return: スライス数
        """
        if self._extent is None:
            return 0
        return self._extent.get_dimension(axis)

    def get_slice_range(self, axis: int) -> tuple[int, int]:
        """
        指定軸のスライス範囲を返す

        :param axis:  0=Sagittal(X), 1=Coronal(Y), 2=Axial(Z)
        :return: (min_index, max_index)
        """
        if self._extent is None:
            return 0, 0
        if axis == 0:
            return self._extent.x_min, self._extent.x_max
        elif axis == 1:
            return self._extent.y_min, self._extent.y_max
        elif axis == 2:
            return self._extent.z_min, self._extent.z_max
        raise ValueError(f"Invalid axis: {axis}")

    @staticmethod
    def create_demo_volume(size: int = 128) -> vtk.vtkImageData:
        """
        デモ用のランダムボリュームを生成する

        実運用では以下のいずれかに差し替える:
        - vtk_helpers.load_dicom_series(directory)
        - VolumeViewer.load_volume(directory) のちに from_volume_viewer() で取得する

        :param size: ボリュームサイズ(各軸）
        :return:  vtkImageData
        """
        from vtkmodules.util.numpy_support import numpy_to_vtk

        logger.info(f"Creating demo volume {size}x{size}x{size}")

        volume = vtk.vtkImageData()
        volume.SetDimensions(size, size, size)
        volume.SetSpacing(1.0, 1.0, 2.0)  # z方向は異方性を持たせる
        volume.SetOrigin(0.0, 0.0, 0.0)
        volume.AllocateScalars(vtk.VTK_SHORT, 1)

        # NumPy配列として編集
        arr = np.random.randint(-200, 200, (size, size, size), dtype=np.int16)

        # 中心に級を配置（CT値を模倣)
        center = size // 2
        z, y, x = np.ogrid[:size, :size, :size]
        dist = np.sqrt((x - center) ** 2 + (y - center) ** 2 + (z - center) ** 2)
        arr[dist < size // 4] = 1000  # 軟部組織相当
        arr[dist < size // 8] = 2000  # 骨相当

        # VTK配列に変換
        vtk_arr = numpy_to_vtk(arr.ravel(order="F"), deep=True, array_type=vtk.VTK_SHORT)
        volume.GetPointData().SetScalars(vtk_arr)
        volume.Modified()

        return volume