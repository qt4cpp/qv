"""Geometry utility functions for vector and matrix operations."""
from __future__ import annotations

import math
from typing import Tuple

import vtk


def direction_vector(
        start_point: Tuple[float, float, float],
        end_point: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    """Calculate the direction vector between two points."""
    return (
        end_point[0] - start_point[0],
        end_point[1] - start_point[1],
        end_point[2] - start_point[2],
    )


def calculate_distance(
        start_point: Tuple[float, float, float],
        end_point: Tuple[float, float, float]
) -> float:
    """
    Calculate the distance between two points.

    :param start_point: Starting point (x, y, z)
    :param end_point: Ending point (x, y, z)
    :return: Distance between the two points
    """
    dx = end_point[0] - start_point[0]
    dy = end_point[1] - start_point[1]
    dz = end_point[2] - start_point[2]
    return math.sqrt(dx*dx + dy*dy + dz*dz)


def calculate_norm(vector: Tuple[float, float, float]) -> float:
    """
    Calulate the norm of a vector.

    :param vector: Vector (x, y, z)
    :return: Magnitude of the vector
    """
    return math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2)


def transform_vector(
        vector: Tuple[float, float, float],
        matrix: vtk.vtkMatrix4x4,
) -> Tuple[float, float, float]:
    """
    Transform a 3D vector by a 4x4 matrix.
    Used for patient coordinate transformation in DICOm images.

    :param vector: Vector (x, y, z)
    :param matrix: VTK transformation matrix
    :return: Transformed vector (x, y, z)
    """
    result = [0.0, 0.0, 0.0]
    for i in range(3):
        result[i] = sum(vector[j] * matrix.GetElement(i, j) for j in range(3))
    return tuple(result)


def normalize_vector(vector: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """
    Normalize a 3D vector.

    :param vector: Vector (x, y, z)
    :return: Normalized vector (x, y, z)
    """
    norm = calculate_norm(vector)
    return tuple(v / norm for v in vector)


def dot_product(
        vector1: Tuple[float, float, float],
        vector2: Tuple[float, float, float]
) -> float:
    """
    Calculate the dot product of two 3D vectors.

    :param vector1: Vector (x, y, z)
    :param vector2: Vector (x, y, z)
    :return: Dot product of the two vectors
    """
    return sum(v1 * v2 for v1, v2 in zip(vector1, vector2))


def cross_product(
        vector1: Tuple[float, float, float],
        vector2: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    """
    Calculate the cross product of two 3D vectors.

    :param vector1: First vector (x, y, z)
    :param vector2: Second vector (x, y, z)
    :return: Cross product vector (x, y, z)
    """
    return (
        vector1[1] * vector2[2] - vector1[2] * vector2[1],
        vector1[2] * vector2[0] - vector1[0] * vector2[2],
        vector1[0] * vector2[1] - vector1[1] * vector2[0],
    )