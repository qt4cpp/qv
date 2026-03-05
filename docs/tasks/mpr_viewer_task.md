
## タスクリスト：MPR Viewer → Multi Viewer 実装

---

### Phase 1: MprViewer 本体

---

#### Task 1 — `MprPlane` enum 定義

**コミットメッセージ**: `feat(mpr): add MprPlane enum`

**ファイル**: `qv/viewers/mpr_viewer.py`（新規作成・骨格のみ）

**内容**:
- `MprPlane(enum.Enum)` を定義（`AXIAL` / `SAGITTAL` / `CORONAL`）
- 各断面の方向コサイン定数（`PLANE_AXES` dict）を定義
- ファイルの骨格（import / logger / class stub）のみ

**完了条件**: `from qv.viewers.mpr_viewer import MprPlane` が通ること

---

#### Task 2 — `MprViewer` クラス骨格と VTK パイプライン初期化

**コミットメッセージ**: `feat(mpr): scaffold MprViewer with VTK pipeline`

**ファイル**: `qv/viewers/mpr_viewer.py`

**内容**:
- `MprViewer(BaseViewer)` クラス定義
- `__init__` で属性初期化（`_image_data`, `_plane`, `_slice_index`, `_reslice`, `_color_map`, `_image_actor`, `_window_settings`）
- `_setup_pipeline()` — `vtkImageReslice` + `vtkWindowLevelLookupTable` + `vtkImageMapToColors` + `vtkImageActor` の生成と接続
- `setup_interactor_style()` — `vtkInteractorStyleImage` の設定（Observer なし）
- `load_data()` — `BaseViewer` 抽象メソッドの stub 実装（`set_image_data` に委譲）

**完了条件**: `MprViewer` がインスタンス化でき、空のウィンドウが表示される

---

#### Task 3 — `set_image_data()` と `_update_reslice()` の実装

**コミットメッセージ**: `feat(mpr): implement set_image_data and reslice update`

**ファイル**: `qv/viewers/mpr_viewer.py`

**内容**:
- `set_image_data(image_data: vtkImageData)` の実装
  - `_reslice.SetInputData()` で参照を渡す
  - extent / spacing / origin からスライス範囲（`_slice_min`, `_slice_max`）を計算
  - 初期スライス位置を中央に設定
  - `_setup_camera()` → `_update_reslice()` → `update_view()` を呼ぶ
  - `dataLoaded.emit()` を発火
- `_update_reslice()` の実装
  - 現在の `_plane` に対応する方向コサインを `_reslice.SetResliceAxesDirectionCosines()` に設定
  - スライスインデックスから world 座標（origin）を計算し `SetResliceAxesOrigin()` に設定
- `_setup_camera(plane: MprPlane)` の実装
  - `SetParallelProjection(True)`
  - 各断面に対応したカメラ位置・上方向ベクトルを設定
  - `renderer.ResetCamera()` 呼び出し

**完了条件**: `set_image_data()` 後に Axial 断面が表示される

---

#### Task 4 — `set_plane()` による断面切り替え

**コミットメッセージ**: `feat(mpr): implement plane switching (axial/sagittal/coronal)`

**ファイル**: `qv/viewers/mpr_viewer.py`

**内容**:
- `set_plane(plane: MprPlane)` の実装
  - `_plane` を更新
  - スライス範囲を新断面に基づいて再計算
  - スライス位置を中央にリセット
  - `_setup_camera()` → `_update_reslice()` → `update_view()` を呼ぶ
- `sliceChanged = Signal(object, int)` シグナル定義

**完了条件**: `set_plane(MprPlane.SAGITTAL)` で Sagittal、`set_plane(MprPlane.CORONAL)` で Coronal が正しく表示される

---

#### Task 5 — スライス移動（`set_slice_index` / `scroll_slice`）

**コミットメッセージ**: `feat(mpr): implement slice navigation`

**ファイル**: `qv/viewers/mpr_viewer.py`

**内容**:
- `set_slice_index(index: int)` の実装
  - `_slice_min` / `_slice_max` にクランプ
  - `_update_reslice()` → `update_view()`
  - `sliceChanged.emit()` を発火
- `scroll_slice(delta: int)` の実装（`set_slice_index` に委譲）
- `get_slice_count() -> int` プロパティ（現断面のスライス枚数を返す）

**完了条件**: `scroll_slice(+1)` / `scroll_slice(-1)` で断面が1枚ずつ移動する

---

#### Task 6 — マウスホイールによるスライス操作

**コミットメッセージ**: `feat(mpr): connect mouse wheel to slice scrolling`

**ファイル**: `qv/viewers/mpr_viewer.py`

**内容**:
- `setup_interactor_style()` を更新し、`vtkInteractorStyleImage` に Observer を追加
  - `MouseWheelForwardEvent` → `scroll_slice(+1)`
  - `MouseWheelBackwardEvent` → `scroll_slice(-1)`

**完了条件**: マウスホイールで断面がスクロールする

---

#### Task 7 — Window/Level 反映（`set_window_settings`）

**コミットメッセージ**: `feat(mpr): implement window/level sync`

**ファイル**: `qv/viewers/mpr_viewer.py`

**内容**:
- `set_window_settings(settings: WindowSettings)` の実装
  - `vtkWindowLevelLookupTable` の `SetWindow()` / `SetLevel()` を更新
  - `_color_map.Modified()` → `update_view()`

**完了条件**: `VolumeViewer.windowSettingsChanged` を接続すると MPR 側も同じ輝度で表示される

---

### Phase 2: MultiViewerPanel

---

#### Task 8 — `MultiViewerPanel` の骨格と2画面レイアウト

**コミットメッセージ**: `feat(ui): add MultiViewerPanel with VR + Axial layout`

**ファイル**: `qv/ui/widgets/multi_viewer_panel.py`（新規）

**内容**:
- `MultiViewerPanel(QWidget)` クラス定義
- `QSplitter(Horizontal)` で左右に `VolumeViewer` / `MprViewer` を配置
- `add_viewer(viewer, name)` メソッドで将来の4画面拡張に備えたインターフェース

**完了条件**: VR と Axial MPR が左右に並んで表示される

---

#### Task 9 — データロード後のビューワー間同期

**コミットメッセージ**: `feat(ui): wire VolumeViewer signals to MprViewer`

**ファイル**: `qv/ui/widgets/multi_viewer_panel.py`

**内容**:
- `VolumeViewer.dataLoaded` → `MprViewer.set_image_data(_source_image)`
- `VolumeViewer.windowSettingsChanged` → `MprViewer.set_window_settings()`
- `_source_image` を公開するプロパティまたはメソッドを `VolumeViewer` に追加

**完了条件**: DICOM ロード後、VR と Axial MPR が同時に表示される

---

#### Task 10 — `MainWindow` への `MultiViewerPanel` 組み込み

**コミットメッセージ**: `feat(ui): integrate MultiViewerPanel into MainWindow`

**ファイル**: `qv/ui/mainwindow.py`

**内容**:
- `VolumeViewer` 単独配置を `MultiViewerPanel` に置き換え
- Histogram ウィジェットとの接続を `MultiViewerPanel` 経由に調整
- 既存のショートカット・メニューが `VolumeViewer` に引き続き届くことを確認

**完了条件**: アプリ起動時に2画面構成で表示され、既存機能（クリッピング等）が動作する

---

### タスク依存関係

```
Task 1
  └── Task 2
        ├── Task 3
        │     ├── Task 4
        │     │     └── Task 5
        │     │           └── Task 6
        │     └── Task 7
        │
        └── Task 8 (Task 3完了後)
              └── Task 9
                    └── Task 10
```

