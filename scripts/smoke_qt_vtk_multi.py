from __future__ import annotations

"""
Smoke test for multiple QVTK widgets (VolumeViewer + SliceViewerWidget).

Goal
  Reproduce or isolate OpenGL/VTK crashes by controlling:
  - which pipelines are initialized
  - which viewer renders
  - when rendering happens

Quick start
  Baseline (no init, immediate render):
    python scripts/smoke_qt_vtk_multi.py

Options and what they isolate
  --init volume|slice|both
    Initialize pipelines without loading data.
    Use when you suspect setup code (clipping/reslice) triggers instability.

  --render volume|slice|none|both
    Control which viewer calls Render().
    Use when you suspect a specific viewer is crashing in Render().

  --render-timing delayed --render-delay-ms <ms>
    Delay Render() via QTimer.
    Use when you suspect OpenGL context readiness or timing is the trigger.

Recommended combos
  Init + render only one viewer:
    --init volume --render volume
    --init slice --render slice

  Init both, render one:
    --init both --render volume
    --init both --render slice

  Timing sensitivity check:
    --render both --render-timing delayed --render-delay-ms 1000
"""

import argparse
import sys
from pathlib import Path

from PySide6 import QtCore, QtWidgets

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from qv.viewers.mpr import SliceAxis, SliceViewerWidget
from qv.viewers.volume_viewer import VolumeViewer


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Qt + VTK multi-viewer smoke test")
    parser.add_argument(
        "--render",
        choices=("both", "volume", "slice", "none"),
        default="both",
        help="Control initial Render() calls via BaseViewer flags.",
    )
    parser.add_argument(
        "--render-timing",
        choices=("immediate", "delayed"),
        default="immediate",
        help="Render immediately via BaseViewer or schedule delayed renders.",
    )
    parser.add_argument(
        "--render-delay-ms",
        type=int,
        default=300,
        help="Delay in milliseconds for scheduled renders when using --render-timing delayed.",
    )
    parser.add_argument(
        "--init",
        choices=("none", "volume", "slice", "both"),
        default="none",
        help="Initialize viewer pipelines without loading data.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    app = QtWidgets.QApplication(sys.argv)

    window = QtWidgets.QMainWindow()
    window.setWindowTitle("Qt + VTK Multi Smoke")
    window.resize(1200, 800)

    central = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(central)

    volume_viewer = VolumeViewer(parent=central)
    slice_viewer = SliceViewerWidget(axis=SliceAxis.AXIAL, parent=central)

    if args.init in ("volume", "both"):
        volume_viewer._setup_clipping()
    if args.init in ("slice", "both"):
        slice_viewer._setup_mpr_pipeline()

    if args.render_timing == "delayed":
        volume_viewer._skip_render_once = True
        slice_viewer._skip_render_once = True
    elif args.render != "both":
        volume_viewer._skip_render_once = args.render != "volume"
        slice_viewer._skip_render_once = args.render != "slice"

    layout.addWidget(volume_viewer, stretch=3)
    layout.addWidget(slice_viewer, stretch=2)

    window.setCentralWidget(central)
    window.show()

    if args.render_timing == "delayed":
        def _do_render() -> None:
            if args.render in ("both", "volume"):
                volume_viewer.vtk_widget.GetRenderWindow().Render()
            if args.render in ("both", "slice"):
                slice_viewer.vtk_widget.GetRenderWindow().Render()

        QtCore.QTimer.singleShot(args.render_delay_ms, _do_render)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
