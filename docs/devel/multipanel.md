# 4画面構成 + Crosshair同期 設計ドキュメント

## 1. 概要

本設計は、同一の `vtkImageData` を共有して `VR / Axial / Coronal / Sagittal` の4画面を同時表示し、3つの MPR 画面間で crosshair 同期を行うための構成を定義する。

現行実装では MPR は `vtkImageReslice + vtkImageMapToWindowLevelColors + vtkImageActor` を用いている。本設計ではこの構成を維持し、まずは固定3断面の同期表示を成立させることを優先する。

---

## 2. 目的

- 同一データから `VR / Axial / Coronal / Sagittal` を同時表示する
- Axial / Coronal / Sagittal 間で crosshair を同期する
- 1つの MPR 画面でのダブルクリック、ホイール操作を他断面へ反映する
- 既存の `VolumeViewer` と `MprViewer` を最大限再利用する
- 初期段階で十分な操作性能を維持する

---

## 3. 非目的

- oblique MPR
- thick slab MPR
- DICOM patient orientation の完全対応
- VR 画面への crosshair / 3D marker の常時描画
- MPR と VR の WW/WL 連動

---

## 4. 前提

- `VolumeViewer` は既存の `vtkGPUVolumeRayCastMapper` ベース構成を維持する
- `MprViewer` は既存の `vtkImageReslice` ベース構成を維持する
- MPR 3画面は同一の `vtkImageData` を参照共有し、コピーしない
- WW/WL は当面 `VolumeViewer` と各 `MprViewer` で独立とする

---

## 5. 画面構成

まずは次の構成にする。
```text 
┌─────────────────────────────┬─────────────────────────────┐
│ VolumeViewer (VR)           │ MprViewer (Axial)           │
├─────────────────────────────┼─────────────────────────────┤
│ MprViewer (Coronal)         │ MprViewer (Sagittal)        │
└─────────────────────────────┴─────────────────────────────┘
``` 

その後、次の構成を追加する。
```text
┌─────────────────────────────┬─────────────────────────────┐
│                             │ MprViewer (Axial)           │
├                             ┼─────────────────────────────┤
│       VolumeViewer (VR)     │ MprViewer (Sagittal)        │
├                             ┼─────────────────────────────┤
|                             | MprViewer (Coronal)         |
└─────────────────────────────┴─────────────────────────────┘
```
 `` 

---

## 6. 全体構成

### 6.1 主要クラス

- `VolumeViewer`
- `MprViewer`
- `MultiViewerPanel`
- `MprSyncController`（新規追加・`QObject` 継承）

### 6.2 推奨ファイル配置
```text
qv/
 ├── viewers/ 
 │   ├── volume_viewer.py 
 │   ├── mpr_viewer.py 
 │   └── controllers/ 
 │        └── mpr_sync_controller.py 
 └── ui/ 
      └── widgets/ 
          └── multi_viewer_panel.py
 
tests/ 
├── ui/ 
│   └── test_multi_viewer_panel.py 
└── viewers/ 
     └── test_mpr_sync_controller.py
``` 

---

## 7. 設計方針

### 7.1 MPR は既存 vtkImageReslice を継続利用する
初期目標は固定3断面の4画面表示と crosshair 同期であり、現時点では `vtkImageReslice` のままで十分実装可能である。
将来、連続ドラッグ時の負荷や oblique MPR が問題化した場合に `vtkImageResliceMapper` への移行を再検討する。

### 7.2 同期は Viewer 間の直接接続ではなく Controller 経由にする
各 `MprViewer` が他 viewer を直接知らないようにし、同期責務を `MprSyncController` に集中させる。
これにより、再帰更新、同期停止、将来の VR マーカー連携を管理しやすくする。

### 7.3 共有状態は world 座標を正本とする
crosshair の共有位置は `WorldPosition(x, y, z)` で保持する。
各 viewer はこの world 座標を自断面の slice index と crosshair 表示位置へ変換する。

### 7.4 crosshair 同期のトリガーはダブルクリックとする
MPR 画面上での crosshair 位置の変更はダブルクリックで行う。
シングルクリックやドラッグでは crosshair は更新しない。
これにより、通常の WW/WL 操作やパン操作との誤操作を防ぐ。

### 7.5 レイアウト切替は Strategy パターンで分離する
2つのレイアウト（2×2 / 1+3）の切替を `LayoutStrategy` プロトコルで抽象化する。
viewer のライフサイクルは `MultiViewerPanel` が管理し、レイアウト変更時は `setParent(None)` → 再配置の流れとする。

---

## 8. 共有データ型

### 8.1 WorldPosition

crosshair の共有座標を型安全に扱うため、NamedTuple を用いる。
```python 
from typing import NamedTuple
class WorldPosition(NamedTuple): x: float y: float z: float
``` 

シグナルの引数型として `tuple` の代わりに `WorldPosition` を使う。
`pos.x` のようにアクセスでき、可読性と型安全性が向上する。

---

## 9. クラス設計

### 9.1 MultiViewerPanel

**責務**
* 4画面の生成と配置
* `VolumeViewer` の `source_image` を3つの `MprViewer` へ配布
* `MprSyncController` の生成と接続
* レイアウト切替の管理
* viewer の生存期間管理

**主要属性**
```python 
class MultiViewerPanel(QWidget): 
  volume_viewer: VolumeViewer axial_viewer: 
  MprViewer coronal_viewer: 
  MprViewer sagittal_viewer: 
  MprViewer mpr_sync_controller:
  MprSyncController _layout_strategy: 
  LayoutStrategy
``` 

### 9.1.1 初期化方針
1. `VolumeViewer` を1つ生成する
2. `MprViewer` を3つ生成する
3. 各 `MprViewer` に plane を固定設定する（`set_plane_fixed()`）
4. `VolumeViewer.dataLoaded` で3 viewer へ同じ `vtkImageData` を渡す
5. その後 `MprSyncController.initialize_crosshair_to_center()` を呼ぶ

### 9.1.2 レイアウト切替
```python 
from typing import Protocol
class LayoutStrategy(Protocol): def apply(self, panel: MultiViewerPanel) -> None: ...
class TwoByTwoLayout: """2×2 グリッドレイアウト""" def apply(self, panel: MultiViewerPanel) -> None: ...
class OnePlusThreeLayout: """左 VR 大 + 右 MPR×3 レイアウト""" def apply(self, panel: MultiViewerPanel) -> None: ...
``` 

- `MultiViewerPanel.set_layout(strategy: LayoutStrategy)` でランタイム切替する
- 切替時は各 viewer を `setParent(None)` で一旦外し、新しい splitter 構成に再配置する
- viewer インスタンス自体は破棄せず再利用する（VTK パイプラインの再構築を避ける）
- 切替後も `MprSyncController` の接続は維持される

---

### 9.2 MprViewer

**既存責務**
* 指定断面のスライス表示
* slice index 管理
* WW/WL 反映
* マウスホイールによるスライス移動

**追加責務**
* crosshair の表示
* ダブルクリック位置を world 座標へ変換して通知
* controller から受け取った共有位置に基づき crosshair を更新

**追加シグナル**
```python
ダブルクリックによる crosshair 位置通知
crosshairPicked = QtCore.Signal(object, object) # (MprPlane, WorldPosition)
ホイールによるスライス変更通知（world 座標で emit）
sliceWorldChanged = QtCore.Signal(object, float) # (MprPlane, world_value)
``` 

**追加メソッド**
```python 
def set_plane_fixed(self, plane: MprPlane) -> None: """初期化時に plane を固定する。通常運用では切り替えない。""" ...
def set_crosshair_world(self, world_pos: WorldPosition) -> None: """controller から共有位置を受け取り、crosshair を描画更新する。""" ...
def get_current_world_pos(self) -> WorldPosition: """現在の slice index に対応する world 座標を返す。""" ...
def display_to_world(self, x: int, y: int) -> WorldPosition | None: """display 座標を world 座標に変換する。volume 外なら None を返す。""" ...
def set_slice_index_silent(self, index: int) -> None: """slice index を更新するが sliceChanged / sliceWorldChanged シグナルを emit しない。 controller からの同期更新で再帰ループを防ぐために使用する。""" ...
``` 

### 実装メモ
- 現在の `_plane` は viewer ごとに固定利用する
- `set_plane_fixed()` は初期化時のみ使い、通常運用では切り替え UI を持たない
- crosshair 表示は `overlay_renderer` 上の actor で描画する
- MPR 内ダブルクリックは picker で world 座標へ変換する
- ホイール操作は現在と同様に `scroll_slice()` を使う
- `sliceWorldChanged` は `sliceChanged` の代わりに world 座標値で emit する
  - 変換責務を viewer 側に持たせることで controller を薄く保つ
- `display_to_world()` は volume 外のクリック時に `None` を返す

---

### 9.3 MprSyncController

#### 責務
- 3つの MPR viewer の登録
- 共有 world 座標（`WorldPosition`）の保持
- slice 同期と crosshair 同期
- 再帰更新の抑止（context manager 方式）
- 初期位置の決定
- ダブルクリック同期の throttle

#### QObject 継承
`MprSyncController` は `QObject` を継承する。
`QTimer` による throttle 制御やシグナル/スロット接続に必要なため。

#### 主要属性

```python 
class MprSyncController(QObject): image_data: vtkImageData | None viewers: dict[MprPlane, MprViewer] current_world: WorldPosition | None _sync_depth: int # 再帰ガードカウンタ _throttle_timer: QTimer _pending_world: WorldPosition | None
``` 

#### 再帰ガード（Context Manager 方式）
```python 
from contextlib import contextmanager
@contextmanager def _guard(self): """同期更新中の再帰呼び出しを安全に抑止する。 例外発生時でもカウンタが確実に戻る。""" self._sync_depth += 1 try: yield finally: self._sync_depth -= 1
@property def _is_syncing(self) -> bool: return self._sync_depth > 0
``` 

#### Throttle 制御

```python 
def init(self): self._throttle_timer = QTimer() self._throttle_timer.setInterval(33) # ~30Hz self._throttle_timer.setSingleShot(True) self._throttle_timer.timeout.connect(self._flush_pending) self._pending_world: WorldPosition | None = None
def _flush_pending(self) -> None: """タイマー発火時に最新の pending world を apply する。""" if self._pending_world is not None: self.current_world = self._pending_world self._pending_world = None self.apply_world_to_all()
``` 

Throttle の配置方針:
- `MprViewer` は毎回シグナルを emit する（viewer 側を単純に保つ）
- `MprSyncController` が最新の world 座標のみ保持し、タイマー発火時にまとめて反映する
- ホイール操作やダブルクリック連打時の過剰更新を防ぐ

#### 主要メソッド
```python
def register_viewer(self, plane: MprPlane, viewer: MprViewer) -> None """viewer を登録し、シグナルを接続する。"""
def set_image_data(self, image_data: vtkImageData) -> None """image_data を設定する。crosshair は center にリセットされる。"""
def initialize_crosshair_to_center(self) -> None """volume center を初期 crosshair 位置に設定し、全 viewer に反映する。"""
def on_slice_world_changed(self, plane: MprPlane, world_value: float) -> None """ホイール操作で world 座標値が変更されたとき呼ばれる。 current_world の該当軸を更新し、他 viewer の crosshair を更新する。"""
def on_crosshair_picked(self, plane: MprPlane, world: WorldPosition) -> None """ダブルクリックで world 座標が取得されたとき呼ばれる。 throttle 経由で apply する。"""
def apply_world_to_all(self) -> None """current_world を全 viewer の crosshair と slice に反映する。 MPR viewer のみを対象とし、VR viewer は含まない。"""
``` 

---

## 10. 同期ルール

### 10.1 初期表示時

- `VolumeViewer` が読込完了後、3つの `MprViewer` に同一 `vtkImageData` を渡す
- 各 viewer は自 plane の中央 slice を表示する
- `MprSyncController` は volume center を初期 crosshair 位置に設定する
- controller は各 viewer に crosshair を反映する

### 10.2 ホイール操作時

Axial でホイール前進した場合の流れ：

1. Axial の `slice_index` が変わる
2. `sliceWorldChanged(AXIAL, new_world_z)` が発火する（viewer が world 座標に変換）
3. controller は `current_world.z` を更新する（`_replace(z=new_world_z)`）
4. controller は Coronal / Sagittal の crosshair を更新する
5. 必要なら他 viewer の slice も同期更新する（`set_slice_index_silent()`）

### 10.3 ダブルクリック時

Axial 画面でダブルクリックした場合の流れ：

1. Axial viewer はダブルクリック位置を `display_to_world()` で world 座標に変換する
2. volume 外の場合は `None` → 無視する
3. `crosshairPicked(AXIAL, WorldPosition(x, y, z))` が発火する
4. controller は `current_world` を更新する（x, y は新値、z は Axial の現在 slice 値を維持）
5. controller は Coronal / Sagittal の slice index を `set_slice_index_silent()` で更新する
6. 3 viewer すべてで crosshair 表示を更新する

### 10.4 シングルクリック / ドラッグ時

- シングルクリック: crosshair は更新しない（従来の操作を維持）
- ドラッグ: crosshair は更新しない（WW/WL 操作やパンとして機能する）

---

## 11. Crosshair の意味

各 viewer には「他の2断面との交点」を表す十字線を描画する。

- Axial: x / y の交点線を表示する
- Coronal: x / z の交点線を表示する
- Sagittal: y / z の交点線を表示する

---

## 12. データフロー

`VolumeViewer.load_data()`

1. `->` source_image 更新
2. `->` dataLoaded emit
3. `->` `MultiViewerPanel._on_volume_data_loaded()`
4. `->` axial/coronal/sagittal に同一 image_data を渡す
5. `->` `MprSyncController.set_image_data(image_data)`
6. `->` center world を初期化
7. `->` 各 viewer へ slice / crosshair 反映

---

## 13. エラーケースと対応

| ケース | 対応 |
|---|---|
| ダブルクリック位置が volume 外 | `display_to_world()` が `None` を返す → viewer はシグナルを emit しない → controller は何もしない |
| `image_data` が `None` のまま同期呼出 | controller の各メソッドで early return する |
| viewer の register 漏れ（2つしか登録されていない） | `apply_world_to_all()` は登録済み viewer のみ処理する。warn ログを出力する |
| VR データ読み込み失敗後の MPR 状態 | MPR を空白/無効状態に戻す。crosshair を非表示にする |
| 新データ読み込み（image_data 差し替え） | `set_image_data()` で crosshair を center にリセットする |
| crosshair 位置が volume の端を超える | world 座標を volume bounds に clamp する |

---

## 14. 性能方針

- `vtkImageReslice` は各 MPR viewer ごとに1つ持つ
- `vtkImageData` は共有し、DeepCopy しない
- 同期更新は controller がまとめて行う（`apply_world_to_all()`）
- viewer 間の再帰 signal loop は context manager ベースの `_sync_depth` で抑止する
- 連続操作時の過剰 render は controller の `QTimer` throttle（~30Hz）で回避する
- 初期段階では VR 側の crosshair 追従を必須にしない
- `apply_world_to_all()` の対象は MPR viewer のみ（VR viewer は含まない）

---

## 15. 想定される実装順

### Phase 1

- `MultiViewerPanel` を4画面へ拡張
- `MprViewer` を3インスタンス化
- 各 viewer の plane 固定化（`set_plane_fixed()`）
- 同一 `image_data` の配布

### Phase 2

- `MprSyncController` を追加（`QObject` 継承、context manager ガード）
- `sliceWorldChanged` ベースの同期を追加
- volume center 初期化を追加

### Phase 3

- MPR ダブルクリックによる world 座標取得を追加
- crosshair 表示を追加
- ダブルクリック同期を追加

### Phase 4

- `QTimer` throttle 実装
- `LayoutStrategy` によるレイアウト切替
- 必要なら VR マーカー連携
- 実測で問題があれば MPR mapper 変更を再検討

---

## 16. テスト方針

### 16.1 UI テスト

- `VolumeViewer.dataLoaded` 後に3つの `MprViewer` へ同一 image が渡る
- 4 viewer が想定位置に配置される
- viewer 追加 API が4画面でも破綻しない
- レイアウト切替後に viewer が正しい親に属し、同期が維持される

### 16.2 単体テスト

- Axial の slice 変更で shared world の z が更新される
- Coronal の slice 変更で shared world の y が更新される
- Sagittal の slice 変更で shared world の x が更新される
- controller が再帰更新しない（`_sync_depth` が正しく動作する）
- center 初期化時に全 viewer が一致した位置を指す
- `display_to_world()` が volume 外で `None` を返す
- 新データ読込後に crosshair が center にリセットされる

### 16.3 Throttle テスト

- 高速連続ダブルクリックで `apply_world_to_all()` の呼出回数が制限される
- throttle タイマー発火後に最新の world 座標が正しく反映される

### 16.4 境界値テスト

- volume の端（index=0, index=max）で crosshair が clamp される
- volume bounds 外のダブルクリックが無視される

### 16.5 手動確認

- 4画面が同時表示される
- Axial のホイールで Coronal / Sagittal の crosshair が追従する
- Coronal のダブルクリックで Axial / Sagittal が同一点を指す
- シングルクリック / ドラッグでは crosshair が動かない
- WW/WL は viewer ごとに独立して動く
- 通常 CT で操作遅延が目立たない
- レイアウト切替後も同期が維持される

---

## 17. 将来拡張

- oblique MPR
- thick slab
- VR 上の 3D crosshair marker
- patient orientation 対応
- `vtkImageResliceMapper` への移行検討

---

## 18. 結論

初期実装では、現行の `MprViewer` を3つ並べ、`MprSyncController`（`QObject` 継承）を追加して crosshair 同期を実現する。crosshair の位置変更はダブルクリックをトリガーとし、シングルクリック/ドラッグとの操作競合を防ぐ。再帰ガードは context manager で例外安全に保ち、throttle は controller 側の `QTimer` で一元管理する。

この方針は変更範囲が小さく、4画面構成を早く成立させやすい。性能問題が実測で顕在化した段階で、MPR の mapper 変更を検討する。

