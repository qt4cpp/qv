# Undo/Redo（クリッピング）開発者向けドキュメント

このドキュメントは、QV の **クリッピング操作における Undo/Redo の設計・責務分担・データフロー・実装上の注意点**を、後から参画する開発者が理解できるようにまとめたものです。

---

## 目的 / 要件

### 目的
- クリッピング（Clip inside / Clip outside）を複数回適用できる
- Undo/Redo で直前のクリッピング状態を復元できる
- 元のボリューム（`vtkImageData`）は**破壊せず**、表示上だけ「消える」ようにする
- 大規模ボリューム（スライス1000枚など）でも、可能な限りメモリ消費を抑える

### 現在の基本方針
- **元画像**は `VolumeViewer._source_image` として保持し、変更しない
- クリッピング結果は「画像を複製して保存」ではなく、**マスク（uint8）を累積**して実現する
- Undo/Redo は「マスク状態」を復元することで見た目を戻す

---

## 用語

- **Source image**: 読み込んだ元の `vtkImageData`。変更しない。
- **Mask image**: `uint8` のマスク。値によって表示/非表示を制御。
- **Keep-mask方式**: `255=keep(表示) / 0=hide(非表示)` として扱う方式。
- **CLIPPED_SCALAR**: 非表示にしたいボクセルの値（例：`-16383`）。transfer function 側で透明にする。

---

## モジュール責務

### `qv/core/history/history_manager.py`
VTK/Qt 非依存の汎用 Undo/Redo スタック。

- `Command(before, after)` を積む
- `do()` は `after` を適用してから undo stack に積む
- `undo()` は `before` を適用して undo stack から取り出し redo stack に移す
- `redo()` は `after` を適用して redo stack から取り出し undo stack に戻す

注意:
- `HistoryManager` 自体は「状態の意味」を知らない。
- 「状態をどう適用するか」は `apply_state`（コールバック）に委譲される。

### `qv/core/states/clipping_state.py`
Undo/Redo で保存・復元する「状態オブジェクト」。

- 現在は **累積マスクを圧縮した bytes** を保存する想定（例：`mask_zlib: bytes | None`）
- `ClippingState.default()` は「クリップなし」状態（例：`mask_zlib=None`）

### `qv/viewers/volume_viewer.py`
実際の VTK パイプラインと UI 状態遷移を持つ。

- `apply_clipping()`：
  - ROI から「リージョン keep-mask」を生成
  - 現在の累積マスクに積算（AND / min）
  - 圧縮して `ClippingState` を生成し、`HistoryManager.do()` で履歴に追加
- `set_clipping_state(state)`：
  - state を復元し、`vtkImageMask` に与えるマスクを更新
  - mapper（volume）入力は常に `_masker.GetOutputPort()` を使う（パイプラインを作り直さない）

---

## データ構造と意味

### 元画像（不変）
- `VolumeViewer._source_image: vtk.vtkImageData`
- 読み込んだボリュームを保持し、**絶対に書き換えない**

### マスク画像（可変、累積）
- `VolumeViewer._clip_mask_image: vtk.vtkImageData`
- scalar type: `unsigned char`
- 値の意味（keep-mask方式）:

| 値 | 意味 |
|---:|---|
| 255 | keep（表示する） |
| 0 | hide（マスクされ、CLIPPED_SCALAR に置換される） |

### クリッピング状態（履歴）
- `ClippingState(mask_zlib: bytes | None)`
  - `None` は「クリップなし」
  - bytes は `_clip_mask_image` のスカラーを `zlib` 圧縮したもの

---

## VTK パイプライン（概念）
```
_source_image (vtkImageData, 不変)
│ 
├── _clip_mask_image (vtkImageData, uint8, 255/0)
│
└── vtkImageMask (_masker)
- InputData = _source_image
- MaskInputData = _clip_mask_image
- MaskedOutputValue = CLIPPED_SCALAR
↓ mapper.SetInputConnection(_masker.GetOutputPort())
↓ vtkVolume
```

重要ポイント:
- Undo/Redo で **パイプラインを再構築しない**
- 変更するのは `_clip_mask_image` の中身だけ
- `mapper.SetInputConnection(...)` は基本的に初期化時のみで、以後は `Modified()` + `Render` が中心

---

## inside / outside の扱い（keep-mask方式）

ROI ポリゴンから `vtkImplicitSelectionLoop` + `vtkImplicitFunctionToImageStencil` を使ってマスクを作る。

### 期待する結果（keep-mask）
- `REMOVE_INSIDE`（内側を消す）
  - keep-mask: **outside=255 / inside=0**
- `REMOVE_OUTSIDE`（外側を消す）
  - keep-mask: **inside=255 / outside=0**

### 注意（ReverseStencil の罠）
`vtkImageStencil` の `ReverseStencilOn/Off` は直感と逆に感じやすい。

- 入力を全255、背景を0にした場合、
  - 「inside を 255 にしたい」か
  - 「outside を 255 にしたい」か
で ReverseStencil の ON/OFF が変わる。

実装を変更した場合は、**必ず Clip inside/outside を1回ずつ**手動で確認し、挙動を固定すること。

---

## 状態遷移（ユーザー操作）

1. `start_clip_inside()` / `start_clip_outside()`
   - `clipping_operation.set_mode(...)`
   - インタラクタスタイルをクリップ用に切り替え
2. ユーザーが ROI を描く → preview 表示
3. `apply_clipping()`
   - ROI → `region_keep_mask` を生成
   - `_clip_mask_image` に積算
   - 圧縮して `ClippingState` を作成し、履歴に push
4. `undo()` / `redo()`
   - `HistoryManager.undo/redo(self.set_clipping_state)` が呼ばれる
   - `set_clipping_state()` 内で mask を復元し表示更新

---

## `HistoryManager` の使い方（実装ルール）

### do（新しい状態を適用して積む）
`HistoryManager.do(cmd, apply_state)` は以下を保証する:
- `apply_state(cmd.after)` を実行
- undo stack に積む
- redo stack はクリアされる

### undo / redo
- `undo()` は `cmd.before` を適用する
- `redo()` は `cmd.after` を適用する

### UI 連携
`HistoryManager` は UI に依存しないため、Qt のアクション（Undo/Redoボタン有効/無効）は呼び出し側（MainWindow）が `can_undo()/can_redo()` を見て更新する。

---

## 実装上の落とし穴・注意点

### 1) `vtkImageMask` のマスク解釈
環境差があり、当初の「0=表示」と仮定すると全消しになることがあった。  
そのため現在は **keep-mask（255=表示, 0=非表示）** を採用。

### 2) inside/outside の反転
`vtkImageStencil` の `ReverseStencilOn/Off` が直感と逆に見えるケースがある。  
「どちらを残したいか（inside or outside）」でテストし、ロジックを固定すること。

### 3) `stenciler.Update()` の呼び忘れ
`vtkImplicitFunctionToImageStencil` は `Update()` を呼ばないと出力が不定になる場合がある。  
マスク生成時は `Update()` を必ず呼ぶ。

### 4) メモリと速度
- 画像そのものを履歴に積むと、1000スライス級で数GBに達する可能性がある
- マスク方式でも undo 回数を増やすと圧縮バイト列が増える（ただし画像複製よりは軽いことが多い）
- 速度ボトルネックは「ROI→ステンシル→マスク生成」なので、必要に応じてスレッド化/先読み等を検討

---

## デバッグの指針（ログ）

以下をログすると原因切り分けが容易です。

- ロード直後:
  - `_clip_mask_image.GetScalarRange()` が `(255,255)` か
  - `_masker.GetOutput().GetScalarRange()` が元画像に近いか
- apply後:
  - マスクのレンジが `(0,255)` になっているか（0が混ざる）
- undo/redo後:
  - 復元後のレンジが期待と一致するか

---

## 今後の拡張ポイント

- マスク生成の高速化（スレッド化/差分化）
- Undo履歴の保存方式（圧縮率改善、差分圧縮、最大保持数の見直し）
- 複数種操作（クリップ以外）を同じ `HistoryManager` で扱う際の State 設計