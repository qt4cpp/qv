import os
import numpy as np
import pytest
from PySide6.QtWidgets import QWidget
import pyqtgraph as pg

from ui.widgets.histgram_widget import show_histgram_window


@pytest.fixture(autouse=True)
def enable_xvfb(monkeypatch):
    """
    Ensure that Qt uses an offscreen buffer during testing.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

def test_show_histogram_window_returns_widget(qtbot):
    # Generate synthetic data
    data = np.random.randint(0, 10, size=(20, 30, 5))
    # Call function and verify it returns a QWidget
    window = show_histgram_window(data, bins=5)
    assert isinstance(window, QWidget)
    qtbot.addWidget(window)
    # Ensure the window is shown without errors
    assert window.isVisible()

def test_histogram_plot_data_matches_numpy(qtbot):
    # A simple known dataset for deterministic counts
    data = np.array([[[0, 1], [1, 2]], [[2, 3], [3, 4]]])
    # bins set to 4: edges [0,1,2,3,4]
    window = show_histgram_window(data, bins=4)
    qtbot.addWidget(window)
    # Locate the PlotWidget
    plot_widget = window.findChild(pg.PlotWidget)
    assert plot_widget is not None
    # Retrieve plotted data items
    data_items = plot_widget.plotItem.listDataItems()
    assert data_items, "No data items plotted"
    # Assuming the first data item is the histogram line
    x_plotted, y_plotted = data_items[0].getData()
    # Compute expected histogram
    counts, edges = np.histogram(data.flatten(), bins=4)
    centers = (edges[:-1] + edges[1:]) / 2
    # Compare plotted centers and counts
    assert pytest.approx(centers) == x_plotted
    assert pytest.approx(counts) == y_plotted
    # Close the window
    window.close()