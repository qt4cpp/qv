from PySide6 import QtCore
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QSplitter, QHBoxLayout, QLabel, QPushButton
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from histgram import HistogramWidget


class Ui_MainWindow:
    """
    Manage the UI for the main window.
    """
    def setupUi(self, window: QMainWindow):
        """
        Setup the UI for the main window.
        """
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
        self.create_clipping_buttons(window)

    def create_menus(self, window: QMainWindow):
        """Create the menus for the main window."""
        file_menu = window.menuBar().addMenu("&File")
        view_menu = window.menuBar().addMenu("&View")
        edit_menu = window.menuBar().addMenu("&Edit")

        file_menu.addAction("&Open", window.open_menu)
        file_menu.addAction("&Quit", window.close)

        view_menu.addAction("&Reset View", window.reset_camera)
        view_menu.addAction("Front view", window.front_view)
        view_menu.addAction("Reset Zoom", window.reset_zoom)
        view_menu.addAction("2x zoom", window.set_zoom_2x)
        view_menu.addAction("0.5x zoom", window.set_zoom_half)

        edit_menu.addAction("&Clip", window.enter_clip_mode)

    def create_clipping_buttons(self, window: QMainWindow):
        self.clip_button_widget = QWidget()
        layout = QHBoxLayout()
        self.apply_clip_button = QPushButton("Apply", window)
        self.cancel_clip_button = QPushButton("Cancel", window)
        layout.addWidget(self.apply_clip_button)
        layout.addWidget(self.cancel_clip_button)
        self.clip_button_widget.setLayout(layout)
        self.clip_button_widget.hide()

        window.statusBar().addPermanentWidget(self.clip_button_widget)

    def setup_status(self, window: QMainWindow, **kwargs):
        """Setup the status bar for the main window."""
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
