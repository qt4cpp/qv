# Transfer Function 実装ガイド（QV / VTK Volume Rendering）

## 目的
本書は、`qv/viewers/volume_viewer.py` の Transfer Function（以下 TF）を実装・調整するときに、
画質と性能を両立するための実践的な判断基準をまとめた開発者向けガイドです。

前提:
- `AutoAdjustSampleDistancesOff` で固定品質運用するケースを主対象とする
- 本プロジェクトでは `ImageSampleDistance < 1.0` は副作用（描画領域の欠け）が出る可能性があるため、通常は使わない
- `UseJitteringOn` はバンディング低減に有効だが、粒状感が増えることがある

---

## 1. 現状実装の要点

`qv/viewers/transfer_functions.py` が preset 定義、validation、JSON 読み書き、TF point 生成を担当する。
`VolumeViewer._apply_window_settings()` が `build_transfer_function_points(...)` の結果を VTK に反映する。
`update_transfer_functions()` は現在の WW/WL で再適用・再描画する互換 wrapper である。

- 初期 preset は `default_linear`。window 下限を黒・透明、上限を白・不透明にする。
- CT preset は `default_window` から active WW/WL へ color/opacity の scalar 座標を remap する。右ドラッグによる WW/WL 調整にも追従する。
- `default_window=None` の非 `default_linear` preset は固定 scalar point として扱う。
- `CLIPPED_SCALAR` の透明化は point 生成時に追加する。
- unit distance と gradient opacity は preset から反映し、WW/WL では変えない。未指定の preset に切り替えると unit distance は既定値に戻し、gradient opacity は無効化する。
- built-in は `View > Transfer Functions` から選択できる。選択状態の保存・復元は実装しない（タスク12は中止）。

TF 調整では以下を観察する:
- バンディング（等高線状の見え）
- jittering有効時の粒状ノイズの知覚
- ウィンドウ幅が狭いと階調遷移が急になり、見えが不安定

---

## 2. まず守る方針（このプロジェクト向け）

1. `ImageSampleDistance` は原則 `>= 1.0`
2. バンディング対策は `UseJitteringOn` を第一候補にする
3. jitteringで粒状感が出たら、TFと`ScalarOpacityUnitDistance`で抑える
4. いきなり多パラメータを同時変更しない（1つずつ比較）

---

## 3. パラメータ調整の順序

### Step 1: Opacity TFを「急峻すぎない形」にする
調整対象の CT / user preset の opacity を、3〜5点以上の緩やかなカーブにする。
`default_linear` の2点線形は互換性のため変更しない。

例（概念）:
- `min_val`: 0.00
- `min_val + 0.25*width`: 0.03
- `min_val + 0.50*width`: 0.12
- `min_val + 0.75*width`: 0.35
- `max_val`: 1.00

狙い:
- 低濃度帯をなだらかに立ち上げ、段差感と粒状感を抑える

### Step 2: `scalar_opacity_unit_distance` を調整
preset の `scalar_opacity_unit_distance` を指定し、レイ積分時の実効不透明度スケールを調整する。
viewer が `vtkVolumeProperty.SetScalarOpacityUnitDistance(value)` に反映する。

調整の考え方:
- 値を大きくする: ノイズ感を抑えやすいが、全体が薄くなりやすい
- 値を小さくする: コントラストが立つが、ノイズ/段差が目立ちやすい

初期値の目安:
- まず `1.0` を基準
- 粒状感が強い場合 `1.2 -> 1.5 -> 2.0` を比較

### Step 3: Gradient Opacity（必要時のみ）
preset の `gradient_opacity_points` に `(gradient, opacity)` を追加する。
viewer が `SetGradientOpacity(...)` に反映する。低勾配領域の寄与を抑えると、平坦ノイズを減らせることがある。

注意:
- 効きすぎると細部が消える
- まずは弱めのカーブから始める

---

## 4. jitteringの扱い

重要:
- `vtkGPUVolumeRayCastMapper` のjitteringは通常 `On/Off` 制御が中心で、
  強度を細かく指定できない構成が多い

実務上の解釈:
- 「jittering強度を下げる」の代わりに、
  TF（特にOpacity）と`ScalarOpacityUnitDistance`で見え方を整える

推奨組み合わせ:
- `UseJitteringOn`
- `ImageSampleDistance = 1.0`
- Opacityカーブを緩やかに
- `ScalarOpacityUnitDistance` をやや大きめ

---

## 5. 調整プロトコル（比較手順）

1. CT データを読み込み、scalar range と reader の rescale slope/intercept の反映を確認する。
2. camera pose、crop/clipping 状態、performance profile を固定する。
3. `View > Transfer Functions` で `Default Linear`、`CT Abdomen Soft Tissue`、`CT Head Brain`、`CT Bone` を順に選択する。preset 選択で初期 WW/WL が変わるため、表示中の実値を記録する。
4. 各 preset の初期状態を保存した後、右ドラッグで WW/WL を調整し、CT preset の見えも変化することを確認する。同じ preset を再選択しても WW/WL はリセットされない。初期値に戻す場合は一度別の preset に切り替えて戻す。
5. 同一 preset の変更前後を比較するときは active WW/WL も同じ値に揃え、opacity、unit distance、gradient opacity のうち1項目ずつ変える。
6. clipping 済み領域が透明のままか確認し、`Default Linear` に戻したときの互換表示も確認する。`default_linear` への切り替えは現在の WW/WL を維持するので、元の表示との比較では元の WW/WL に戻す。
7. performance profile を切り替えて TF preset 名が維持されることを確認する。性能比較では profile 以外の条件を固定する。
8. 再起動して `Default Linear` で始まることを確認する。最後の選択の復元は期待しない。

比較ごとに次を記録する（実測・目視未実施の項目は未評価と記す）:

| 項目 | 記録内容 |
|---|---|
| データ | dataset 名または匿名化 ID、scalar range |
| preset | 内部名、変更した point / パラメータ、コード revision または JSON |
| 表示条件 | camera pose、crop/clipping 状態、active WW/WL |
| 性能条件 | profile 名、静止時・操作時の jittering と sample distance |
| 不透明度 | 実効 `ScalarOpacityUnitDistance`、gradient opacity の有無 |
| 結果 | 静止画、banding、粒状感、組織境界の視認性、低コントラスト領域の消失、interaction 時 FPS |

推奨データセット:
- 通常CT（標準枚数）
- 高解像度/巨大スライスのCT
- 低コントラスト病変が含まれるケース

評価項目:
- バンディングの目立ち
- 粒状感
- 組織境界の視認性
- インタラクション時FPS

---

## 6. 症状別の対処表

### 症状A: 等高線状の線が見える
- `UseJitteringOn`
- Opacityカーブの立ち上がりを緩和
- Window幅が狭すぎる場合は適正化

### 症状B: つぶつぶ（粒状感）が気になる
- `ImageSampleDistance` を `1.0` に維持（`<1.0` は使わない）
- `ScalarOpacityUnitDistance` を上げる
- Opacityの中間点を増やして急峻な遷移を減らす

### 症状C: 描画領域が欠ける/切り取られる
- `ImageSampleDistance < 1.0` を避ける
- まず `1.0` 固定で原因切り分け

### 症状D: 画質は良いが重い
- インタラクション中だけ軽量設定に切替
- `interactive_image_sample_distance` を上げる
- `interactive_shade_enabled` を必要に応じてOFF

---

## 7. preset の追加と保存

TF は `TransferFunctionPreset`、描画性能は `PerformanceProfile` で管理する。
`PerformanceProfile` や `_apply_profile()` に TF 名・point・unit distance を追加しない。

### built-in preset を追加する

1. `qv/viewers/transfer_functions.py` の `_BUILTIN_PRESETS` に `TransferFunctionPreset(...)` を追加する。tuple の順序が UI の表示順になる。
2. 一意な `name` と `display_name` を付ける。`source` は `"builtin"`（既定値）にする。
3. 基準の `default_window=WindowSettings(level=..., width=...)` と、その window における color/opacity point を定義する。各 point は scalar 昇順、RGB/opacity は `0..1`。clipping 用 point は helper が付けるので preset 定義に含めない。
4. 必要なら `scalar_opacity_unit_distance > 0` と `gradient_opacity_points` を設定する。既存定義の `WindowSettings` を直接変更せず、新しい値を作る。
5. import 時の `_validate_builtin_presets()` で構造と名前の重複が検証される。追加した preset の初期 WW/WL、WW/WL 追従などの期待値を `tests/viewers/test_transfer_functions.py` に追加し、表示に関わる変更は viewer テストも確認する。
6. 下記テストと手動評価を実施し、仕様書の built-in 一覧へ名前・初期 WW/WL を追記する。メニューは `list_transfer_function_presets()` から構築されるため、個別 action の追加は不要。

ロード済み `VolumeViewer` を `viewer` とした API 操作例:

```python
from qv.core.window_settings import WindowSettings

viewer.set_transfer_function_preset("ct_head_brain")
assert viewer.current_transfer_function_preset_name == "ct_head_brain"
assert "ct_bone" in viewer.available_transfer_function_presets()
viewer.set_window_settings(WindowSettings(level=50.0, width=100.0))
viewer.set_transfer_function_preset("default_linear")
```

`set_transfer_function_preset(name, render=False)` で描画を抑制できる。不明な名前は `ValueError`。

### user preset を JSON に保存・再読み込みする

保存先は API に明示する。以下はプロジェクトルートでの実行例で、保存先は `settings/transfer_function_presets.json`。
既存ファイルは指定した一覧で置き換わるため、追加時は既存 preset も読み込んで渡す。
完全な JSON 例と必須・省略可能フィールドは[仕様書のユーザー定義 preset](transfer_function_presets_spec.md#ユーザー定義-preset)を参照する。

```python
from dataclasses import replace
from pathlib import Path

from qv.viewers.transfer_functions import (
    build_transfer_function_registry,
    get_transfer_function_preset,
    load_user_transfer_function_presets,
    save_user_transfer_function_presets,
)

path = Path("settings/transfer_function_presets.json")
existing = load_user_transfer_function_presets(path) if path.exists() else ()
custom = replace(
    get_transfer_function_preset("ct_abdomen_soft_tissue"),
    name="user_abdomen_custom",
    display_name="My Abdomen Custom",
    scalar_opacity_unit_distance=1.5,
    source="user",
)
# 同じ user preset を更新するときは、その定義だけ置き換える。
presets = tuple(
    preset for preset in existing
    if preset.name.strip().lower() != custom.name
) + (custom,)
save_user_transfer_function_presets(path, presets)
assert load_user_transfer_function_presets(path) == presets

registry = build_transfer_function_registry(path)
assert registry.get(custom.name) == custom
assert "default_linear" in registry.names()
assert registry.get("unknown_preset") is None
```

保存時は全入力の各 preset を検証し、`source="user"` の定義だけを入力順に出力する。
schema は `1`、`source` は JSON に出力しない。名前の衝突は読み込み時に拒否されるため、保存後の再読み込みまで確認する。
strict な load API は不正 JSON を例外にし、`build_transfer_function_registry(path)` はログを残して built-in のみへ fallback する。

現在の `VolumeViewer` とメニューが受け付けるのは built-in のみである。この JSON を置いても、上例で registry を構築しても、アプリの選択一覧には追加されない。
user preset の検証には load/save と `build_transfer_function_points(...)` を使える。GUI での評価は現在の built-in 追加経路を使い、user registry の viewer 接続は別途実装する。
user preset 定義の保存は継続するが、最後に選択した preset 名を `AppSettingsManager` に保存する機能は実装しない。

### 自動テスト

プロジェクトの Python 環境で、リポジトリルートから実行する。

```bash
python -m pytest tests/viewers/test_transfer_functions.py tests/viewers/test_volume_viewer.py tests/ui/test_mainwindow.py
```

GUI のない環境では必要に応じて `QT_QPA_PLATFORM=offscreen` を指定する。
自動テストは validation、JSON 往復・fallback、TF point、切り替えと UI 同期を確認する。実データの画質・FPS は第5節で別途記録する。

---

## 8. 最低限の受け入れ基準

1. `ImageSampleDistance >= 1.0` で、顕著な描画欠けが再現しない
2. jittering ON時に、従来よりバンディングが減る
3. 粒状感が診断上許容できるレベルまで低減できる
4. `balanced` プロファイルで操作感が実用範囲（FPS）を維持

---

## 9. 将来拡張

- user preset registry の viewer 接続と編集・import/export UI
- ヒストグラム連動の自動初期TF
- ROIベースの局所TF調整
- user preset JSON の schema migration


---

## 10. 関連仕様

CT の部位・観察目的別 Transfer Function preset の設計仕様は以下を参照する。

- [Transfer Function preset 仕様](transfer_function_presets_spec.md)
- [実装タスク（タスク12は中止、13は文書整備）](../tasks/transfer_function_presets_implementation_task.md)
