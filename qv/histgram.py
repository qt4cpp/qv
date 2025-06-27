import numpy as np
import vtk
from PySide6.QtWidgets import QWidget, QVBoxLayout
import pyqtgraph as pg


def show_histgram_window(data: np.ndarray, bins: int = 1024):
    """Display a histogram of the given data."""
    window = QWidget()
    layout = QVBoxLayout(window)
    plot_widget = pg.PlotWidget()
    layout.addWidget(plot_widget)
    plot_widget.setXRange(max=4096, min=-2048, padding=0)
    plot_widget.setYRange(max=1000000, min=0, padding=0)
    counts, edges = np.histogram(data.flatten(), bins=bins)

    x = np.repeat(edges, 2)[1:-1]
    y = np.repeat(counts, 2)
    centers = (edges[:-1] + edges[1:]) / 2
    plot_widget.plot(
        x=centers,
        y=counts,
        pen=pg.mkPen(color=(255, 255, 255), width=1),
        symbol=None,
    )
    window.resize(500, 300)
    window.show()
    return window


def minimum_show_histgram_window():
    x = np.arange(1000)
    y = np.random.normal(size=(3,1000))
    plot_widget = pg.PlotWidget(title="Plot title")
    for i in range(3):
        plot_widget.plot(x, y[i], pen=pg.mkPen(color=(255, 255, i*18), width=2))
    plot_widget.show()

