import os

# VTK(QVTKRenderWindowInteractor) がWaylandネイティブに非対応のため、
# 強制的にX11(XWayland)プラットフォームにする。
# 明示的に QT_QP_PLATFORM を設定している場合はそちらを優先する。
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from qv.main import main

if __name__ == "__main__":
    raise SystemExit(main())
