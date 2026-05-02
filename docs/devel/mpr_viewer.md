2画面構成（VR + Axial MPR）設計
``` 
┌─────────────────────────────────────┐
│  MainWindow                         │
│  ┌─────────────┬───────────────┐   │
│  │ VolumeViewer│  MprViewer    │   │
│  │   (VR/3D)   │  (Axial)      │   │
│  └─────────────┴───────────────┘   │
│  ┌─────────────────────────────┐   │
│  │  HistogramWidget            │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

## MPR Viewer 設計ドキュメント

関連仕様:

- `Patient Orientation` 仕様: `docs/devel/patient_orientation.md`

## 概要

`MprViewer` は `BaseViewer` を継承した MPR（Multi-Planar Reconstruction）専用ビューワーである。  
同一の `vtkImageData` を `VolumeViewer` と共有し、Axial / Sagittal / Coronal の3断面をスライス表示する。  
断面の切り替えはメソッド呼び出しで行い、将来の UI（ボタン、タブ等）からも呼び出せる設計とする。

---

## ファイル配置
```

qv/ 
└── viewers/
 ├── base_viewer.py （既存・変更なし）
 ├── volume_viewer.py （既存・変更なし） 
 └── mpr_viewer.py 【新規】
``` 

---

## クラス設計

### `MprViewer(BaseViewer)`

**場所**: `qv/viewers/mpr_viewer.py`

#### 責務

| 責務 | 手段 |
|---|---|
| 断面スライス表示 | `vtkImageReslice` + `vtkImageActor` |
| 断面方向の管理 | `MprPlane` enum（Axial / Sagittal / Coronal）|
| スライス位置の管理 | スライスインデックス（整数）で管理 |
| Window/Level 反映 | `set_window_settings(WindowSettings)` を受け取り `vtkImageMapToColors` に反映 |
| データ受け取り | `set_image_data(vtkImageData)` で VolumeViewer から参照を渡す |

#### 主要属性
```
MprViewer
 ├── _image_data: vtkImageData | None # VolumeViewerから受け取った参照
 ├── _plane: MprPlane # 現在表示中の断面
 ├── _slice_index: int # 現在のスライス位置（整数）
 ├── _reslice: vtkImageReslice # 断面切り出しフィルタ 
 ├── _color_map: vtkImageMapToColors # グレースケール表示用 
 ├── _image_actor: vtkImageActor # 断面画像のアクター 
 └── _window_settings: WindowSettings # 現在のWindow/Level設定
``` 

---

## 断面定義

### `MprPlane` enum
```python
class MprPlane(enum.Enum): AXIAL = "axial" SAGITTAL = "sagittal" CORONAL = "coronal"
``` 

各断面の `vtkImageReslice` パラメータ（ResliceAxesDirectionCosines）:

| 断面 | x軸方向 | y軸方向 | 意味 |
|---|---|---|---|
| Axial | (1,0,0) | (0,1,0) | 水平断面（足→頭方向スライス）|
| Sagittal | (0,1,0) | (0,0,1) | 矢状断面（左→右方向スライス）|
| Coronal | (1,0,0) | (0,0,1) | 前額断面（前→後方向スライス）|

---

## パイプライン
```
vtkImageData (_image_data) │ ▼ vtkImageReslice (_reslice)
├── SetResliceAxesDirectionCosines() ← 断面方向
└── SetResliceAxesOrigin() ← スライス位置（中心点）
│ ▼ vtkImageMapToColors (_color_map) 
└── SetLookupTable(vtkWindowLevelLookupTable) ← Window/Level 
│ ▼ vtkImageActor (_image_actor) 
│ ▼ renderer（並行投影カメラ / ParallelProjection）
``` 

### カメラ設定

- `SetParallelProjection(True)` — 正射影（遠近感なし）
- 各断面に応じてカメラ位置・方向を初期化する  
  （例: Axial → カメラを Z+ 方向から見下ろす）

---

## 主要メソッド

### データ設定
```

python def set_image_data(self, image_data: vtkImageData) -> None: """VolumeViewerからvtkImageDataの参照を受け取り、パイプラインを初期化する。"""``` 

- `_reslice.SetInputData(image_data)` で参照を渡す（DeepCopyしない）
- 画像の extent / spacing / origin からスライス範囲を計算し、初期スライス位置を中央に設定
- パイプライン構築後に `_update_reslice()` を呼ぶ

### 断面切り替え
```

python def set_plane(self, plane: MprPlane) -> None: """表示断面を切り替える。スライス位置は新断面の中央にリセットする。"""``` 

- `_plane` を更新
- `_reslice` の方向コサイン・カメラ方向を再設定
- スライス位置を新断面の中央にリセット
- `_update_reslice()` → `update_view()` を呼ぶ

### スライス移動
```python
def set_slice_index(self, index: int) -> None:
    """スライスインデックスを設定し、表示を更新する。"""
def scroll_slice(self, delta: int) -> None:
    """スライスを delta 枚分スクロールする（+: 奥、-: 手前）。"""
``` 

- インデックスを有効範囲にクランプ
- `_update_reslice()` → `update_view()` を呼ぶ

### Window/Level
```python
def set_window_settings(self, settings: WindowSettings) -> None:
    """Window/Levelを更新し、表示を更新する。"""
``` 

- `vtkWindowLevelLookupTable` の Window/Level を更新
- `update_view()` を呼ぶ

### 内部更新
```python
def _update_reslice(self) -> None:
    """現在の断面方向とスライスインデックスからReslice原点を計算し、更新する。"""
``` 

---

## インタラクター設計

### `setup_interactor_style()`

MPR ビューワーでは 3D 回転は不要。  
`vtkInteractorStyleImage` を継承した `MprInteractorStyle` を使用し、MPR 専用の 2D 操作を定義する。

### 操作仕様

| 操作 | 挙動 | 備考 |
|---|---|---|
| マウスホイール | スライス移動 | ホイール用のスライス移動方向設定に従う |
| Shift + マウスホイール | 拡大 / 縮小 | 2D MPR のため `vtkCamera` の `ParallelScale` を変更する |
| 左ドラッグ上下 | スライス移動 | ドラッグ用のスライス移動方向設定に従う |
| 右ドラッグ | Window/Level 調整 | 横移動を Window、縦移動を Level に割り当てる |
| 左ダブルクリック | MPR 同期 | 指定位置を基準に他 MPR のスライスを同期する |
| Shift + 左ドラッグ | 連続 MPR 同期 | ドラッグ中のカーソル位置を基準に他 MPR を追従させる |

### スライス移動方向オプション

スライス移動方向は、左ドラッグとマウスホイールで個別に設定できるようにする。  
どちらの操作も、以下の 2 つの方向モードを選択できる。

| GUI 表示名 | 内部値 | 挙動 |
|---|---|---|
| 患者方向に合わせる | `patient_orientation` | Patient Orientation を基準にスライス移動方向を決定する |
| スライス番号順に移動する | `slice_index` | slice index の増減方向をそのままスライス移動方向にする |

設定項目は以下とする。

| 設定 | 対象操作 | 設定キー案 |
|---|---|---|
| スライスドラッグ方向 | 左ドラッグ上下 | `mpr/slice_drag_direction_mode` |
| ホイールスライス方向 | マウスホイール | `mpr/wheel_slice_direction_mode` |

デフォルト値はどちらも `patient_orientation` とする。  
設定はアプリ全体で共有し、すべての MPR viewer に適用する。

`patient_orientation` では、断面ごとの患者方向に従って移動する。  
`slice_index` では、患者方向を考慮せず、入力操作を slice index の増減に直接対応させる。

### スライスドラッグ

左ドラッグ単体ではパンではなくスライス移動を行う。  
ドラッグ中の上下移動量を累積し、一定ピクセル数を超えたタイミングで `scroll_slice()` を呼び出す。

- 細かいマウス移動で過剰にスライスが飛ばないよう、ピクセル閾値を設ける。
- 閾値未満の移動量は次の `MouseMoveEvent` に持ち越す。
- スライス移動方向は「スライスドラッグ方向」設定に従う。

「患者方向に合わせる」場合、ドラッグ方向とスライス移動方向は断面ごとに以下とする。

| Plane | 上ドラッグ | 下ドラッグ |
|---|---|---|
| Axial | Superior 方向へ移動 | Inferior 方向へ移動 |
| Coronal | Anterior 方向へ移動 | Posterior 方向へ移動 |
| Sagittal | Left 方向へ移動 | Right 方向へ移動 |

この方向定義は画面上の上下方向ではなく、各断面のスライス軸に対する患者座標上の移動方向を示す。  
実装では現在の断面・画像 orientation・slice index の増減方向を照合し、上記の患者方向に一致するよう `scroll_slice()` の符号を決定する。

「スライス番号順に移動する」場合は、上ドラッグで slice index を増やし、下ドラッグで slice index を減らす。

### ホイールスライス移動

Shift を押していないマウスホイールではスライス移動を行う。  
スライス移動方向は「ホイールスライス方向」設定に従う。

「患者方向に合わせる」場合、ホイール方向とスライス移動方向は断面ごとに以下とする。

| Plane | wheel forward | wheel backward |
|---|---|---|
| Axial | Superior 方向へ移動 | Inferior 方向へ移動 |
| Coronal | Anterior 方向へ移動 | Posterior 方向へ移動 |
| Sagittal | Left 方向へ移動 | Right 方向へ移動 |

「スライス番号順に移動する」場合は、wheel forward で slice index を増やし、wheel backward で slice index を減らす。

Shift + マウスホイールはズーム操作として扱うため、「ホイールスライス方向」設定の対象外とする。

### ズーム

Shift + マウスホイールでは MPR 画像の拡大 / 縮小を行う。  
MPR は平行投影の 2D ビューであるため、カメラ距離ではなく `vtkCamera.SetParallelScale()` で表示倍率を制御する。

- `Shift + wheel forward`: 拡大
- `Shift + wheel backward`: 縮小
- ズーム倍率は過剰な拡大 / 縮小を避けるため、最小値・最大値でクランプする。
- スライス変更時にズーム状態はリセットしない。
- plane 切り替えや画像読み込み時は、初期表示に合わせてズーム基準を再設定する。

ズームリセットは独立した機能として別途定義する。  
将来的には UI 操作、ショートカット、コンテキストメニューなどから現在の MPR viewer のズームだけを初期表示に戻せるようにする。

### ズームリセット

ズームリセットは `VolumeViewer` と同じ操作モデルで提供する。  
メニューや将来実装するボタンから呼び出せるよう、`MprViewer` 側にも `VolumeViewer` と揃えたズーム API を持たせる。

```python
def set_zoom_factor(self, factor: float) -> None:
    """初期表示を 1.0 とした倍率で MPR 表示をズームする。"""

def reset_zoom(self) -> None:
    """MPR 表示を初期フィット状態に戻す。"""
```

MPR は平行投影の 2D ビューであるため、`VolumeViewer` のようにカメラ距離を変更せず、初期フィット時の `ParallelScale` を基準値として保持する。

- 画像読み込み後、初期フィット時の `ParallelScale` をズーム基準値として保存する。
- `set_zoom_factor(1.0)` および `reset_zoom()` は、その基準値へ戻す。
- スライス変更時はズーム基準値を更新しない。
- スライス変更時は現在のズーム倍率を維持する。
- plane 切り替えや画像読み込み時は、表示対象が変わるためズーム基準値を再設定する。

UI からの呼び出しは後続実装とする。  
ただし今回のズーム実装では、メニューやボタンが viewer 種別を意識しすぎないよう、`MprViewer` に `reset_zoom()` API を用意しておく。

4画面構成でのリセット対象は UI 仕様として別途決める。

- アクティブな MPR viewer のみをリセットする。
- 全 MPR viewer をまとめてリセットする。
- VolumeViewer と MPR viewer を個別にリセットする。
- すべての viewer をまとめてリセットする。

---

## シグナル

| シグナル | 型 | タイミング |
|---|---|---|
| `sliceChanged` | `(MprPlane, int)` | スライスインデックスが変化したとき |
| `dataLoaded` | `()` | `set_image_data()` 完了時（BaseViewer 継承）|

---

## 断面切り替えの使い方（呼び出し側）
```python
Axial に切り替え
mpr_viewer.set_plane(MprPlane.AXIAL)
Sagittal に切り替え
mpr_viewer.set_plane(MprPlane.SAGITTAL)
Coronal に切り替え
mpr_viewer.set_plane(MprPlane.CORONAL)
``` 

---

## データフロー（VolumeViewer との連携）
```
VolumeViewer.load_volume()
│ 
├── _source_image ────────────── → MprViewer.set_image_data() 
│
└── windowSettingsChanged ──────→ MprViewer.set_window_settings()
``` 

- `_source_image` は **参照渡し**（`ShallowCopy` / `DeepCopy` なし）
- Window/Level は `VolumeViewer.windowSettingsChanged` シグナルで同期
- `MprViewer` 側での Window/Level 変更は Phase 2 以降（MPR 独立操作）

---

## 断面表示規約（暫定）

将来の `Patient Orientation` 対応および断面表示の一貫性確保のため、  
現時点で以下の表示規約を採用する。

### Axial

- 足側から頭側方向を見る
- 患者の右は画面の左に表示する
- 患者の左は画面の右に表示する

### Coronal

- 患者の前方から後方を見る
- 患者の右は画面の左に表示する
- 患者の左は画面の右に表示する

### Sagittal

- 患者の左側から右側方向を見る
- 画面の左を患者の前方とする
- 画面の右を患者の後方とする

## この規約の意図

- 3断面で左右・前後・上下の解釈を一貫させる
- 現段階の固定3断面実装において、viewer ごとの見え方を安定させる
- 将来 `Patient Orientation` に対応した際も、表示ポリシーを維持できるようにする

## 現段階での位置づけ

この規約は「最終的な DICOM orientation 対応」そのものではない。  
まず viewer が従う表示ポリシーを明確化し、その後に各データセットの患者座標系を  
この表示規約へ正規化する、という順序で実装する。

## 将来対応で決めること

以下は今後、`Patient Orientation` 対応時に明示的に仕様化する必要がある。

### 1. 患者座標系の正規化方針

- DICOM の `Image Orientation (Patient)` をどのように取り込むか
- `vtkImageData` の index space から patient space への変換をどこで保持するか
- viewer 内部の正本座標を何にするか
  - voxel index
  - world coordinate
  - patient coordinate

### 2. 表示規約へのマッピング方法

- patient 座標系から Axial / Coronal / Sagittal の各表示面へどう変換するか
- 各 plane ごとに必要な軸反転をどこで吸収するか
  - `PLANE_AXES`
  - camera の `view_up`
  - actor 側の transform
- radiological convention を維持するかどうか

### 3. Orientation marker 表示

- 画面端に表示する方位記号
  - `L / R`
  - `A / P`
  - `H / F`
- plane ごとにどの位置へ何を表示するか
- patient orientation 対応後に常に正しい marker を出す方法

### 4. Crosshair と同期座標の扱い

- crosshair の正本を patient/world 座標に統一するか
- `WorldPosition` を patient 座標として扱うか
- 他断面への投影時にどの変換行列を使うか

### 5. 将来拡張時の整合

- oblique MPR を導入した場合の表示規約
- thick slab 時の orientation 維持
- 同一 plane を複数 viewer で表示する場合の規約
- 画面レイアウト変更時にも表示規約を不変に保つ方法

## 実装上の指針

- 現段階では固定 plane ごとの表示向きを崩さない
- 一時的な見た目調整ではなく、上記規約に従って `PLANE_AXES` と camera を設計する
- `Patient Orientation` 対応時には、この表示規約を変更するのではなく、
  患者座標系をこの規約へマッピングする形で実装する
