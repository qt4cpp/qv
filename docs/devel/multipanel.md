# 4画面構成 + Crosshair同期 設計ドキュメント（改訂版）

> 元文書をもとに、crosshair の意味、操作体系、責務分離を再整理した改訂版。

---

## 1. 概要

本設計は、同一の `vtkImageData` を共有して  
`VR / Axial / Coronal / Sagittal` の4画面を同時表示し、  
3つの MPR 画面間で crosshair 同期を行う構成を定義する。

現行実装では MPR は  
`vtkImageReslice + vtkImageMapToWindowLevelColors + vtkImageActor`  
を用いている。

本設計ではこの構成を維持し、まずは  
**固定3断面 + 安定した同期挙動の確立**  
を優先する。

---

## 2. 目的

- `VR / Axial / Coronal / Sagittal` の同時表示
- MPR 3画面間の crosshair 同期
- 断面ごとの独立操作と同期操作の両立
- ダブルクリックによる断面位置の整列
- 既存 `VolumeViewer` と `MprViewer` の再利用
- 初期段階での安定動作と十分な操作性能の確保

---

## 3. 非目的

- oblique MPR
- thick slab MPR
- DICOM patient orientation の完全対応
- VR 画面への crosshair / 3D marker の常時描画
- MPR と VR の WW/WL 連動

---

## 4. 前提

- `VolumeViewer` は既存構成を維持
- `MprViewer` は `vtkImageReslice` を使用
- `vtkImageData` は共有（DeepCopyしない）
- WW/WL は viewer ごとに独立
- **表示と操作を明確に分離する**

---

## 5. 画面構成

### 5.1 初期構成

```text
┌─────────────────────────────┬─────────────────────────────┐
│ VolumeViewer (VR)           │ MprViewer (Axial)           │
├─────────────────────────────┼─────────────────────────────┤
│ MprViewer (Coronal)         │ MprViewer (Sagittal)        │
└─────────────────────────────┴─────────────────────────────┘
```

### 5.2 将来構成
```text

┌─────────────────────────────┬─────────────────────────────┐
│                             │ MprViewer (Axial)           │
├                             ┼─────────────────────────────┤
│       VolumeViewer (VR)     │ MprViewer (Sagittal)        │
├                             ┼─────────────────────────────┤
│                             │ MprViewer (Coronal)         │
└─────────────────────────────┴─────────────────────────────┘

```

## 6. 全体構成（改訂）

### 6.1 主要クラス

- `VolumeViewer`
- `MprViewer`
- `MultiViewerPanel`
- `MprSyncController`（同期制御専用）

---

### 6.2 設計方針（重要）

本システムは以下の設計原則に基づく：

- 各 `MprViewer` は**独立した状態を保持する**
- Viewer 同士は**直接参照しない**
- 同期はすべて `MprSyncController` を介して行う
- 同期は常時ではなく、**操作イベントを契機に発生する**

---

### 6.3 状態の分類

状態は以下の2種類に分かれる：

#### ① Viewer 固有状態（永続状態）

各 `MprViewer` が保持する：

- 現在スライス位置（x / y / z のいずれか）
- WW/WL
- 表示設定（crosshair ON/OFF 等）
- カメラ状態

👉 **これらが各 viewer の正本状態**

---

#### ② 同期イベント状態（一時状態）

`MprSyncController` が扱う：

- 操作起点 viewer
- マウス位置から取得した `WorldPosition`
- 同期種別（crosshair / slice）
- 修飾キー状態（Shift 等）
- 再帰防止フラグ

👉 **これはイベント処理中のみ存在する**

---

## 7. Crosshair の意味（改訂）

### 7.1 定義

crosshair は以下を意味する：

> **他断面の現在スライス位置を可視化する補助表示**

---

### 7.2 表示の本質

- crosshair は**状態ではなく表示**
- 各 viewer が自身の overlay として描画する
- controller は描画を行わない

---

### 7.3 表示内容

各 viewer は他 viewer の状態を参照して crosshair を描画する：

#### Axial
- 縦線 → Sagittal の x
- 横線 → Coronal の y

#### Coronal
- 縦線 → Sagittal の x
- 横線 → Axial の z

#### Sagittal
- 縦線 → Coronal の y
- 横線 → Axial の z

---

### 7.4 更新タイミング

crosshair は以下のタイミングで更新される：

- 他 viewer の slice 変更時
- 同期イベント発生時

---

## 8. 同期モデル（新規・重要）

### 8.1 同期の定義

同期とは：

> **操作により得られた基準座標をもとに、他 viewer の表示または状態を更新する処理**

---

### 8.2 特徴

- 同期は**常時ではない**
- **イベント駆動**で発生する
- 同期対象および挙動は操作と設定に依存する

---

### 8.3 同期の入力

同期処理は以下の情報を入力として行われる：

- 操作を行った viewer（source viewer）
- マウス位置から取得した `WorldPosition`
- 操作種別（ホイール / ダブルクリック / ドラッグ）
- 修飾キー状態（Shift 等）

---

### 8.4 同期の出力

同期の結果として以下のいずれかが行われる：

- 他 viewer の crosshair 更新
- 他 viewer の slice 位置更新
- 両方

---

### 8.5 同期モード

同期の挙動は以下のように切り替え可能とする：

| モード | 挙動 |
|--------|------|
| crosshairのみ | 表示のみ更新 |
| slice同期 | スライス位置も更新 |
| 一時同期（Shift） | 操作中のみ同期 |
| 完全同期（ダブルクリック） | 全 viewer を揃える |

---

## 9. データ構造（改訂）

### 9.1 WorldPosition

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class WorldPosition:
    x: float
    y: float
    z: float
```

### 9.2 MprPlane

MPR の断面種別を表す enum。
`source_plane` には専用の別 enum を作らず、この `MprPlane` をそのまま使用する。

```python
import enum

class MprPlane(enum.Enum):
    AXIAL = "axial"
    CORONAL = "coronal"
    SAGITTAL = "sagittal"
```

#### 仕様

- 責務は「断面の幾何学的種別」のみとする
- `source_plane` は「操作起点となった viewer が現在表示している断面」を表す
- `viewer_id` の代用として意味を広げない
- 永続化・ログ・デバッグ出力では `.value` を使用する
- 現段階では固定3断面のみを扱い、`oblique` や `unknown` は追加しない

> **注意:** 現在の 4 画面構成では `Axial / Coronal / Sagittal` が
> 1 viewer ずつ固定で割り当たるため、
> 結果的に plane で viewer を一意に識別できる。
> ただしこれは UI 構成上の性質であり、
> `MprPlane` 自体の責務は viewer 識別ではない。
> 将来、同一断面を複数 viewer で表示する場合は
> `source_viewer_id` を別途導入する。

### 9.3 SyncRequest

同期イベントを表現する構造

```python
from dataclasses import dataclass

# 将来的に Ctrl など他の修飾キーへの拡張を想定し、
# modifier フラグは個別フィールドではなく必要に応じて追加する。
@dataclass(frozen=True, slots=True)
class SyncRequest:
    source_plane: MprPlane
    world_position: WorldPosition
    update_crosshair: bool
    update_slices: bool
    shift_pressed: bool = False
```

#### `source_plane` の意味

- 同期処理の起点となった断面
- `WorldPosition` を取得した viewer の現在断面
- target plane ではない
- slice 軸番号そのものでもない

> **補足:** `source_plane` を自由形式の `str` にすると
> typo や登録漏れで壊れやすいため、
> `MprPlane` enum に統一する。

## 10. 同期ルール（改訂）

### 10.1 初期化

- 各 viewer は独立した初期 slice を持つ
- crosshair は他 viewer の状態に基づき描画される

---

### 10.2 ホイール操作

#### 挙動
- 操作した viewer のみ slice を変更
- 他 viewer は変更しない

#### 結果
- 他 viewer の crosshair が更新される

> **補足:** crosshair は「他断面の現在スライス位置を可視化する線」であるため、
> 自身の slice が変われば他 viewer の crosshair 線の位置も変わる。
> 他 viewer の slice 自体は動かない。

---

### 10.3 ダブルクリック

#### 挙動
1. display → world 変換
2. `WorldPosition(x, y, z)` を取得
3. 各 viewer の slice を該当位置へ更新

#### 結果
- 全 viewer が同一位置に揃う
- crosshair も一致する

---

### 10.4 Shift操作（同期モード）

#### 挙動
1. Shift を押しながら左ドラッグする
2. ドラッグ中、カーソル位置を連続的に display → world 変換する
3. 取得した `WorldPosition` を `SyncRequest` として controller に送る
4. 他 viewer の slice 位置をリアルタイムで更新する

#### 結果
- ドラッグ中、全 viewer が同一位置を追従する
- ドラッグ終了後は各 viewer の最終位置がそのまま維持される

> **補足:** ドラッグ操作は高頻度でイベントが発生するため、
> throttle（~30Hz）を適用して過剰な再描画を防ぐ。

---

### 10.5 再帰防止

- controller 経由の更新ではイベントを再発火しない
- user 操作のみ同期トリガーとする

---

### 10.6 エラー処理

| ケース | 対応 |
|--------|------|
| volume外クリック | 無視 |
| image未設定 | early return |
| bounds超過 | clamp |
| ピッキング失敗 | 無視 |
