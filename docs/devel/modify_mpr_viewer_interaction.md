# MprViewer インタラクション改善メモ

## 目的

`MprViewer` のインタラクションと `WindowSettings` の挙動を、`VolumeViewer` と整合する形に整理する。  
この修正は別ブランチで行う前提とし、Task 6 では着手しない。

テスト運用と手動確認手順は `docs/devel/mpr_viewer_testing.md` を参照する。

---

## 背景

現在の `MprViewer` は `BaseViewer` の `window_settings` 共通IFへ寄せつつあるが、`VolumeViewer` と比べて次の差分が残っている。

- `MprViewer` の右ドラッグ操作が VTK の既定 `vtkInteractorStyleImage` の挙動に影響される
- `MprViewer` と `VolumeViewer` で `WindowSettings` 更新時の責務分担が揃っていない
- `BaseViewer` が `window_settings` の所有者である設計に対して、`MprViewer` 側に実装の揺れが残っている
- `VolumeViewer` は独自 interactor style を持つが、`MprViewer` は observer ベースで実装されており、構造が不統一

---

## 現状の課題

### 1. MprViewer の右ドラッグ挙動が不安定
`vtkInteractorStyleImage` に `AddObserver()` しているだけだと、既定の右ボタン操作が残る。  
そのため、独自の WW/WL 操作と VTK 標準挙動が競合する可能性がある。

### 2. WindowSettings の適用経路が VolumeViewer と完全には揃っていない
理想は以下。

- 状態保持: `BaseViewer`
- VTK パイプラインへの反映: 各サブクラスの `_apply_window_settings()`
- 右ドラッグや UI 操作: 各サブクラスの `adjust_window_settings()` / `set_window_settings()`

この分担に完全には揃っていない。

### 3. インタラクション実装の責務分離が弱い
`MprViewer` 本体がイベント監視、ドラッグ状態、WW/WL 計算をまとめて持っている。  
`VolumeViewer` のように interactor style 側へ寄せたほうが見通しがよい。

---

## 改善目標

### 目標1
`MprViewer` の WW/WL 操作を、VTK 既定の `vtkInteractorStyleImage` の挙動から独立させる。

### 目標2
`WindowSettings` の責務を `VolumeViewer` と揃える。

### 目標3
`BaseViewer` の共通IFを唯一の入口にする。

---

## 目指す構造

### BaseViewer
責務:

- `window_settings` の保持
- HUD 表示更新
- `windowSettingsChanged` シグナル発火
- `set_window_settings()` の共通入口
- `_apply_window_settings()` フック呼び出し

### VolumeViewer
責務:

- `_apply_window_settings()` で transfer function 更新
- 独自 interactor style から `adjust_window_settings()` を呼ぶ

### MprViewer
責務:

- `_apply_window_settings()` で `vtkImageMapToWindowLevelColors` 更新
- 独自 interactor style から `adjust_window_settings()` を呼ぶ
- `BaseViewer` の `window_settings` を直接再管理しない

### MprInteractorStyle
新規導入候補。責務:

- 右ドラッグ開始/終了
- マウス移動中の WW/WL 調整
- ホイールによるスライス移動
- VTK 標準の競合操作を抑止

---

## 修正方針

## 1. MprInteractorStyle を新設する

候補ファイル:

- `qv/viewers/interactor_styles/mpr_interactor_style.py`

想定責務:

- `RightButtonPressEvent`
- `RightButtonReleaseEvent`
- `MouseMoveEvent`
- `MouseWheelForwardEvent`
- `MouseWheelBackwardEvent`

`MprViewer` 本体ではなく、interactor style 側でイベント解釈を行う。

### 方針
- 右ドラッグ中のみ `adjust_window_settings(dx, dy)` を呼ぶ
- ホイールは `scroll_slice(+1/-1)` を呼ぶ
- 既定処理へ流すかどうかを明示的に制御する

---

## 2. MprViewer のイベント状態管理を最小化する

現在 `MprViewer` が持っている以下の状態は、必要に応じて interactor style へ移す。

候補:

- `_ww_wl_dragging`
- `_ww_wl_last_pos`

`MprViewer` 自体は viewer としての責務だけ残す。

---

## 3. WindowSettings の入口を BaseViewer に統一する

`MprViewer` では以下を徹底する。

- `self._window_settings` を直接持たない
- `BaseViewer.window_settings` を利用する
- 状態更新は `super().set_window_settings(...)`
- 実描画反映は `_apply_window_settings(...)`

### 理想形
```python
def _apply_window_settings(self, settings: WindowSettings) -> bool:
    if self._wl_map is None:
        return False

    self._wl_map.SetWindow(settings.width)
    self._wl_map.SetLevel(settings.level)
    self._wl_map.Modified()
    return True
```

## 4. VolumeViewer と MprViewer の WW/WL 操作感を揃える

比較対象:

- `delta_per_pixel` / `_ww_wl_delta_per_pixel`
- `dx` を width に使うか
- `dy` を level に使うか
- `dy` の符号
- clamp のタイミング

### 方針

可能なら以下を揃える。

- 横移動: width 変更
- 縦移動: level 変更
- clamp は `set_window_settings()` 側で行う
- ドラッグの感度を viewer ごとに分ける場合も、命名は統一する

## 5. MprViewer の初期 WW/WL を画像ロード後に確定する

この方針は現時点で採用予定。

- 起動直後は HUD 非表示
- `set_image_data()` 後に `WindowSettings` を計算して適用
- その時点で HUD 表示開始

この方針により、ダミーの `WindowSettings` を初期値として持たずに済む。

## 修正対象候補ファイル

- `qv/viewers/mpr_viewer.py`
- `qv/viewers/interactor_styles/mpr_interactor_style.py` 新規
- `qv/viewers/base_viewer.py`
- 必要なら `qv/ui/widgets/multi_viewer_panel.py`

## 具体的な作業案

1. `MprInteractorStyle` を追加する
2. `MprViewer.setup_interactor_style()` を observer ベースから style ベースへ変更する
3. `MprViewer` の右ドラッグ用フラグを整理する
4. `MprViewer.set_window_settings()` を `BaseViewer` 共通IF前提で見直す
5. `MprViewer.adjust_window_settings()` を `VolumeViewer` と同じ考え方へ揃える
6. `VolumeViewer` と `MprViewer` の WW/WL 感度・符号を揃える
7. 回帰確認を行う

## 確認項目

### MPR

- 右ドラッグで WW/WL が変化する
- HUD がリアルタイムに追従する
- 画像表示にもリアルタイム反映される
- ホイールでスライス移動できる
- 右ドラッグ時に VTK 既定の不要な挙動が出ない

### VR

- 既存の WW/WL 操作が壊れていない
- HUD が従来どおり追従する

### 独立動作

- VR 側の WW/WL を変えても MPR は変わらない
- MPR 側の WW/WL を変えても VR は変わらない

## 非対象

この別ブランチでは、少なくとも以下は必須ではない。

- VR と MPR の WW/WL 連動
- MPR 専用クロスライン表示
- MPR のパン・ズームの全面再設計
- 複数 MPR パネルへの横展開

## 補足

この修正の中心は「MprViewer を VolumeViewer と同じ設計思想へ寄せること」であり、  
単に右ドラッグを動かすことではない。

特に重要なのは次の2点。

- `BaseViewer` を `WindowSettings` の唯一の所有者にする
- インタラクション解釈を viewer 本体から切り離す

この2点が揃うと、今後の MPR 拡張でも破綻しにくくなる。
