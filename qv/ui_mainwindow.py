import vtk
from PySide6 import QtCore
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QSplitter, QHBoxLayout, QLabel
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from histgram import HistogramWidget
from status import StatusField


class Ui_MainWindow:
    def setupUi(self, window: QMainWindow):
        window.setWindowTitle("QV - DICOM Viewer")
        central_widget = QWidget(window)
        self.vtk_widget = QVTKRenderWindowInteractor(central_widget)
        self.histgram_widget = HistogramWidget()
        self._status_label = {}
        # self.histgram_widget.setFixedHeight(200)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.vtk_widget)
        splitter.addWidget(self.histgram_widget)
        layout = QHBoxLayout(central_widget)
        layout.addWidget(splitter)
        window.setLayout(layout)

        window.setCentralWidget(central_widget)

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
