import logging

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout
from pyqtgraph import ViewBox

from log_util import log_io

logger = logging.getLogger(__name__)


class HistogramWidget(pg.PlotWidget):
    """
    Display a histogram of the given data.
    -------------
    - set_data(): Set the data for the histogram.
     Arguments: data: ndarray, bins: int
    """
    def __init__(self, parent=None, data: np.ndarray = None):
        super().__init__(parent)
        self.xmin: int = -2048
        self.xmax: int = 8192
        self.ymin: int = 0
        self.ymax: int = 100000000
        self.getViewBox().setLimits(xMin=self.xmin, xMax=self.xmax, yMin=self.ymin, yMax=self.ymax)
        # self.setYRange(min=self.ymin, max=self.ymax, padding=0)

        self.plot_item = self.getPlotItem()
        self.plot_item.showAxis("right")
        self.vb2 = ViewBox()
        self.vb2.setLimits(yMin=0, yMax=1.2)
        self.plot_item.scene().addItem(self.vb2)
        self.plot_item.getAxis("right").linkToView(self.vb2)
        self.plot_item.getAxis("right").setLabel("Opacity (0-1)")
        self.vb2.setXLink(self.plot_item)

        self.plot_item.getViewBox().sigResized.connect(self.update_view)
        self.update_view()

        if data is not None:
            self.set_data(data)

    @log_io(level=logging.DEBUG)
    def set_data(self, data: np.ndarray, bins: int = 200):
        """
        Set the data for the histogram.
        :param data: numpy array
        :param bins: datastore for the histogram
        :return: None
        """
        flat = data.flatten()
        counts, edges = np.histogram(flat, bins=bins)
        _, y_hi = np.percentile(counts, [0, 98])
        self.setYRange(min=0, max=y_hi)
        centers = edges[:-1] + edges[1:] / 2
        self.plot(
            x=centers,
            y=counts,
            pen=pg.mkPen(color=(255, 255, 255), width=1),
            symbol=None,
        )

    def update_opacity_curve(self, pwf):
        """
        Update the viewing graph based on the Piecewise function.
        :param pwf: Opacity function.
        :return:
        """
        self.vb2.clear()
        xs, ys = sample_opacity(pwf)
        opacity_curve = pg.PlotDataItem(x=xs, y=ys, pen=pg.mkPen(color=(255, 255, 60), width=1))
        self.vb2.addItem(opacity_curve)

    def update_view(self):
        """Update the view when the window is resized."""
        self.vb2.setGeometry(self.plot_item.getViewBox().sceneBoundingRect())
        self.vb2.linkedViewChanged(self.plot_item.getViewBox(), self.vb2.XAxis)


def sample_opacity(pwf, n_samples=256, scalar_range=(-2048, 8192)):
    """Sample the opacity function at a regular grid of points."""
    x = np.linspace(scalar_range[0], scalar_range[1], n_samples)
    y = np.array([pwf.GetValue(x) for x in x])
    return x, y


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
    """
    Display a histogram of the given data.
    This function is used for testing.
    """
    x = np.arange(1000)
    y = np.random.normal(size=(3,1000))
    plot_widget = pg.PlotWidget(title="Plot title")
    for i in range(3):
        plot_widget.plot(x, y[i], pen=pg.mkPen(color=(255, 255, i*18), width=2))
    plot_widget.show()

