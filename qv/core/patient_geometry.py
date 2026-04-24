from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import vtk

PlaneName = Literal["axial", "coronal", "sagittal"]
ViewName = Literal["front", "back", "left", "right", "top", "bottom"]


@dataclass(frozen=True, slots=True)
class WorldPosition:
    """Patient/world-space point shared by MPR and VR."""
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class PatientFrame:
    """Canonical transforms derived from vtkImageData metadata."""
    ijk_to_patient: vtk.vtkMatrix4x4
    patient_to_ijk: vtk.vtkMatrix4x4
    src_to_patient: vtk.vtkMatrix4x4
    patient_to_src: vtk.vtkMatrix4x4
    convention: Literal["LPS", "RAS"] = "LPS"

    def patient_to_ijk(
            self,
            ijk: tuple[float, float, float]
    ) -> tuple[float, float, float]:
        return multiply_point(self.ijk_to_patient, ijk)

    def continuous_ijk_from_patient_point(
            self,
            point: tuple[float, float, float]
    ) -> tuple[float, float, float]:
        return multiply_point(self.patient_to_ijk, point)

    def source_axis_for_plane(self, plane: PlaneName) -> int:
        normal = PLANE_NORMALS_PATIENT[plane]
        source_axes = self._source_axes_in_patient()

        best_axis = 0
        best_score = -1.0
        for axis, source_axis in enumerate(source_axes):
            score = abs(dot_product(normal, source_axis))
            if score > best_score:
                best_axis = axis
                best_score = score
        return best_axis

    def _source_axis_in_patient(
            self,
    ) -> tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]:
        axes: list[tuple[float, float, float]] = []
        for column in range(3):
            vector = (
                self.ijk_to_patient.GetElement(0, column),
                self.ijk_to_patient.GetElement(1, column),
                self.ijk_to_patient.GetElement(2, column),
            )
            axes.append(normalize_vector(vector))
        return axes[0], axes[1], axes[2]


PLANE_DISPLAY_AXES_PATIENT: dict[
    PlaneName,
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ],
] = {
    "axial": (
        (1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
        (0.0, 0.0, -1.0),
    ),
    "coronal": (
        (-1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0),
    ),
    "sagittal": (
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 0.0),
    ),
}

PLANE_NORMALS_PATIENT: dict[PlaneName, tuple[float, float, float]] = {
    "axial": (0.0, 0.0, 1.0),
    "coronal": (0.0, 1.0, 0.0),
    "sagittal": (1.0, 0.0, 0.0),
}

CAMERA_DIRECTIONS_PATIENT: dict[ViewName, tuple[float, float, float]] = {
    "front": (0.0, 1.0, 0.0),
    "back": (0.0, -1.0, 0.0),
    "left": (-1.0, 0.0, 0.0),
    "right": (1.0, 0.0, 0.0),
    "top": (0.0, 0.0, -1.0),
    "bottom": (0.0, 0.0, 1.0),
}

CAMERA_VIEWUPS_PATIENT: dict[ViewName, tuple[float, float, float]] = {
    "front": (0.0, 0.0, -1.0),
    "back": (0.0, 0.0, -1.0),
    "left": (0.0, 0.0, -1.0),
    "right": (0.0, 0.0, -1.0),
    "top": (0.0, -1.0, 0.0),
    "bottom": (0.0, 1.0, 0.0),
}

CAMERA_ANGLES: dict[ViewName, tuple[float, float]] = {
    "front": (0.0, 0.0),
    "back": (180.0, 0.0),
    "left": (90.0, 0.0),
    "right": (270.0, 0.0),
    "top": (0.0, 90.0),
    "bottom": (0.0, 270.0),
}

PLANE_TO_PATIENT_COMPONENT: dict[PlaneName, int] = {
    "sagittal": 0,
    "coronal": 1,
    "axial": 2,
}


def build_patient_frame(image_data: vtk.vtkImageData) -> PatientFrame:
    spacing = image_data.GetSpacing()
    origin = image_data.GetOrigin()
    direction3 = get_direction_matrix(image_data)

    src_to_patient = vtk.vtkMatrix4x4()
    src_to_patient.Identity()

    ijk_to_patient = vtk.vtkMatrix4x4()
    ijk_to_patient.Identity()

    for row in range(3):
        for col in range(3):
            direction_value = direction3.GetElement(row, col)
            src_to_patient.SetElement(row, col, direction_value)
            ijk_to_patient.SetElement(row, col, direction_value * float(spacing[row]))
        ijk_to_patient.SetElement(row, 3, float(origin[row]))

    patient_to_ijk = vtk.vtkMatrix4x4()
    vtk.vtkMatrix4x4.Invert(ijk_to_patient, patient_to_ijk)

    patient_to_src = vtk.vtkMatrix4x4()
    vtk.vtkMatrix4x4.Invert(src_to_patient, patient_to_src)

    return PatientFrame(
        ijk_to_patient=ijk_to_patient,
        patient_to_ijk=patient_to_ijk,
        src_to_patient=src_to_patient,
        patient_to_src=patient_to_src,
    )


def get_direction_matrix(image_data: vtk.vtkImageData) -> vtk.vtkMatrix3x3:
    matrix = image_data.GetDirectionMatrix() if hasattr(image_data, "GetDirectionMatrix") else None
    if matrix is not None:
        return matrix

    identity = vtk.vtkMatrix3x3()
    identity.Identity()
    return identity


def get_plane_axes(
        plane: PlaneName,
) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]:
    return PLANE_DISPLAY_AXES_PATIENT[plane]


def get_plane_reslice_axes_direction_cosines(
        plane: PlaneName,
) -> tuple[float, float, float, float, float, float, float, float, float]:
    x_axis, y_axis, z_axis, = PLANE_DISPLAY_AXES_PATIENT[plane]
    return (
        x_axis[0], x_axis[1], x_axis[2],
        y_axis[0], y_axis[1], y_axis[2],
        z_axis[0], z_axis[1], z_axis[2],
    )


def image_center_continuous_ijk(image_data: vtk.vtkImageData) -> tuple[float, float, float]:
    extent = image_data.GetExtent()
    return (
        0.5 * (float(extent[0]) + float(extent[1])),
        0.5 * (float(extent[2]) + float(extent[3])),
        0.5 * (float(extent[4]) + float(extent[5])),
    )


def patient_axis_coordinate(plane: PlaneName, point: tuple[float, float, float]) -> float:
    return float(point[PLANE_TO_PATIENT_COMPONENT[plane]])


def multiply_point(matrix: vtk.vtkMatrix4x4,
                   point: tuple[float, float, float]) -> tuple[float, float, float]:
    vec = (float(point[0]), float(point[1]), float(point[2]), 1.0)
    result = []

    for row in range(4):
        result.append(sum(matrix.GetElement(row, col) * vec[col] for col in range(4)))

    w = result[3] if abs(result[3]) > 1e-9 else 1.0
    return result[0] / w, result[1] / w, result[2] / w


def normalize_vector(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    norm = (vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2) ** 0.5
    if norm < 1e-9:
        raise ValueError("Cannot normalize zero-length vector.")
    return vector[0] / norm, vector[1] / norm, vector[2] / norm


def dot_product(vector1: tuple[float, float, float], vector2: tuple[float, float, float]) -> float:
    return (vector1[0] * vector2[0]
            + vector1[1] * vector2[1]
            + vector1[2] * vector2[2]
            )