import math
from pathlib import Path

import vtk
import numpy as np
from PySide6 import QtWidgets
from matplotlib import pyplot as plt
from vtkmodules.vtkDICOM import vtkDICOMReader, vtkDICOMTag


def load_dicom_series(directory: str) -> vtk.vtkImageData:
    """Load a DICOM series from a directory."""
    reader = vtk.vtkDICOMImageReader()
    reader.SetDirectoryName(directory)
    reader.Update()
    return reader.GetOutput()


def select_dicom_directory() -> str | None:
    """Select a directory containing DICOM series."""
    dialog = QtWidgets.QFileDialog()
    dialog.setFileMode(QtWidgets.QFileDialog.Directory)
    if dialog.exec():
        return dialog.selectedFiles()[0]
    return None


def plot_hist_clip(volume, bins=100, lower_pct=25, upper_pct=99):
    data = volume.flatten()
    vmin, vmax = np.percentile(data, [lower_pct, upper_pct])
    vmin = -1024
    vmax = 4096
    fig, ax = plt.subplots()
    ax.hist(data, bins=bins, range=(vmin, vmax), edgecolor="black")
    ax.set_xlim(vmin, vmax)
    ax.set_xlabel("Signal Intensity ({}–{} pct)".format(lower_pct, upper_pct))
    ax.set_yscale("log")
    ax.set_ylabel("Count")
    ax.set_title("Clipped Histogram")
    plt.tight_layout()
    plt.show()


def get_camera_angles(camera: vtk.vtkCamera) -> tuple[float, float]:
    """
    Calculate the camera angles (azimuth and elevation)
    by the direction vector from the focal point to the camera position.
    :param camera:
    :return: azimuth, elevation
    """
    # 1) 方向ベクトルを取得
    pos = np.array(camera.GetPosition())
    fp = np.array(camera.GetFocalPoint())
    v = pos - fp  # カメラから注視点へのベクトル

    # 2) ベクトル長
    r = np.linalg.norm(v)
    if r == 0:
        return 0.0, 0.0

    # 3) 仰角 (elevation): z 成分から
    elevation = math.degrees(math.asin(v[2] / r))

    # 4) 方位角 (azimuth): x–y 平面での角度
    azimuth = math.degrees(math.atan2(v[1], v[0]))

    return azimuth, elevation


def return_dicom_dir():
    dicom_dir = "../dicom/HF_head/"
    return dicom_dir


def transform_vector(v, mat):
    """Transform a vector by a 3x3 matrix."""
    result = [0.0, 0.0, 0.0]
    for i in range(3):
        result[i] = sum(v[j] * mat.GetElement(i, j) for j in range(3))
    return result


def direction_vector(start_point: tuple[float, float, float],
                     end_point: tuple[float, float, float]) -> tuple[float, float, float]:
    """Calculate the direction vector between two points."""
    return end_point[0] - start_point[0], end_point[1] - start_point[1], end_point[2] - start_point[2]


def calculate_distance(start_point: tuple[float, float, float],
                       end_point: tuple[float, float, float]) -> float:
    """Calculate the distance between two points."""
    dx = end_point[0] - start_point[0]
    dy = end_point[1] - start_point[1]
    dz = end_point[2] - start_point[2]

    return math.sqrt(dx*dx + dy*dy + dz*dz)

def calculate_norm(vector: tuple[float, float, float]) -> float:
    """Calculate the norm of a vector."""
    return np.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2)


def get_camera_and_view_direction(
        source: vtk.vtkRenderer | vtk.vtkCamera
) -> tuple[vtk.vtkCamera, list[float, float, float], float] | None:
    """
    Return the camera, normalized view vector, and its norm.

    Accepts either a renderer (uses its active camera) or a camera directly;
    returns ``None`` when no camera is available or the view vector has zero
    length.
    """
    if isinstance(source, vtk.vtkRenderer):
        camera = source.GetActiveCamera()
    else:
        camera = source

    if camera is None:
        return None

    focal_point = camera.GetFocalPoint()
    view_vec = direction_vector(camera.GetPosition(), focal_point)
    norm = calculate_norm(view_vec)
    if norm == 0:
        return None

    view_dir = [component / norm for component in view_vec]
    return camera, view_dir, norm
