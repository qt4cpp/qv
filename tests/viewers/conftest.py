"""Shared fixtures for viewer-related tests."""

from __future__ import annotations

import sys

import numpy as np
import pytest
import vtk
from PySide6.QtCore import QSettings
from vtkmodules.util.numpy_support import numpy_to_vtk

from qv.app.app_settings_manager import AppSettingsManager
from qv.viewers.base_viewer import BaseViewer
from qv.viewers.mpr_viewer import MprViewer


@pytest.fixture
def isolated_qsettings(tmp_path):
    """
    Redirect QSettings to a temporary INI location.

    This prevents viewer tests from reading or mutating the user's real settings.
    """
    print(f"QSettings path: {tmp_path}")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))

    settings = QSettings("QVTests.org", "MprViewer")
    settings.clear()
    yield
    settings.clear()


@pytest.fixture
def settings_manager(isolated_qsettings):
    """Create an AppSettingsManager backend by isolated test settings."""
    return AppSettingsManager(
        org_domain="QVTests.org",
        app_name="MprViewer",
    )


@pytest.fixture
def sample_image_data():
    """
    Build a small deterministic vtkImageData for viewer tests.

    The scalar values are 0..59 so tests can assert the scalar range exactly.
    """
    dims = (4, 5, 3)
    values = np.arange(dims[0] * dims[1] * dims[2], dtype=np.int16)

    image = vtk.vtkImageData()
    image.SetDimensions(*dims)
    image.SetSpacing(0.7, 0.8, 1.5)
    image.SetOrigin(-10.0, -20.0, 5.0)

    # Attach contiguous scalar data so VTK can compute the range and extents.
    vtk_array = numpy_to_vtk(values, deep=True, array_type=vtk.VTK_SHORT)
    image.GetPointData().SetScalars(vtk_array)
    image.Modified()
    return image


@pytest.fixture
def mpr_viewer(qtbot, settings_manager, monkeypatch):
    """
    Create and register an MprViewer widget for tests.

    qtbot manages widget lifetime and keeps the fixture aligned with pytest-qt.
    """
    monkeypatch.setattr(BaseViewer, "_initialize_interactor", lambda self: None)

    viewer = MprViewer(settings_manager=settings_manager)
    qtbot.addWidget(viewer)
    return viewer
