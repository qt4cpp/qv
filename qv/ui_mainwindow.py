from PySide6 import QtCore
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QSplitter, QHBoxLayout, QLabel
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from histgram import HistogramWidget


class Ui_MainWindow:
    def setupUi(self, window: QMainWindow):
        window.setWindowTitle("QV - DICOM Viewer")
        central_widget = QWidget(window)
        self.vtk_widget = QVTKRenderWindowInteractor(central_widget)
        self.histgram_widget = HistogramWidget()
        self._status_label = {}
        self.histgram_widget.setMinimumHeight(100)
        self.histgram_widget.sizePolicy().setVerticalStretch(0)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.vtk_widget)
        splitter.addWidget(self.histgram_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout = QHBoxLayout(central_widget)
        layout.addWidget(splitter)
        window.setLayout(layout)

        window.setCentralWidget(central_widget)

        self.create_menus(window)

    def create_menus(self, window: QMainWindow):
        file_menu = window.menuBar().addMenu("&File")
        view_menu = window.menuBar().addMenu("&View")

        file_menu.addAction("&Open", window.open_menu)
        file_menu.addAction("&Quit", window.close)

        view_menu.addAction("&Reset View", window.reset_camera)
        view_menu.addAction("Front view", window.front_view)
        view_menu.addAction("Reset Zoom", window.reset_zoom)
        view_menu.addAction("2x zoom", window.set_zoom_2x)
        view_menu.addAction("0.5x zoom", window.set_zoom_half)


    def setup_status(self, window: QMainWindow, **kwargs):
        status_bar = window.statusBar()
        for key, field in kwargs.items():
            if not field.visible:
                self._status_label[key] = None
                continue
            label = QLabel("", window)
            status_bar.addPermanentWidget(label)
            self._status_label[key] = label
        window.setStatusBar(status_bar)

    @QtCore.Slot(str, str)
    def _refresh_status_label(self, key: str, text: str) -> None:
        """Refresh the status label for the given key."""
        label = self._status_label[key]
        if label:
            label.setText(text)
