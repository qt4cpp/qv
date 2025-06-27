import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout
import pyqtgraph as pg


def show_histgram_window(data: np.ndarray, bins: int = 100):
    window = QWidget()
    layout = QVBoxLayout(window)
    plot_widget = pg.PlotWidget()
    layout.addWidget(plot_widget)
    counts, edges = np.histogram(data.flatten(), bins=bins)
    print(f"x:{len(counts)}  y:{len(edges)}")

    x = np.repeat(edges, 2)[1:-1]
    y = np.repeat(counts, 2)
    centers = (edges[:-1] + edges[1:]) / 2
    plot_widget.plot(
        x=centers,
        y=counts,
        pen=pg.mkPen(color=(255, 255, 255), width=2),
        symbol=None,
    )
    # plot_widget.plot(counts, stepMode=True, fillLevel=0, brush=(100, 100, 255, 100))
    window.resize(600, 400)
    window.show()
    return window


def minimum_show_histgram_window():
    x = np.arange(1000)
    y = np.random.normal(size=(3,1000))
    plot_widget = pg.PlotWidget(title="Plot title")
    for i in range(3):
        plot_widget.plot(x, y[i], pen=pg.mkPen(color=(255, 255, i*18), width=2))
    plot_widget.show()
