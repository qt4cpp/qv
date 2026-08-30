# Transfer Function Preset 実装タスク

参照仕様: `docs/devel/transfer_function_presets_spec.md`

## 目的

CT の部位・観察目的別 Transfer Function preset を、既存表示互換を保ちながら `VolumeViewer` に導入する。

実装は以下の順序で進める。

1. built-in preset の型・registry・validation を作る。
2. `default_linear` を preset 経由にして既存挙動を維持する。
3. CT preset の切り替え API を `VolumeViewer` に追加する。
4. user preset JSON の読み書きを追加する。
5. 値が安定してから UI と設定永続化を追加する。

## 非対象

初期実装では以下を対象外にする。

- DICOM tag による自動 preset 推定
- histogram 連動の自動 opacity 最適化
- ROI ベースの局所 TF
- preset thumbnail preview
- user preset の schema migration

---

## 1. `test(tf): add transfer function preset validation tests`

目的: TF preset のデータ仕様を先にテストで固定する。

対象:

- `tests/viewers/test_transfer_functions.py` 新規

このコミットでやること:

- `TransferFunctionPreset` の基本 validation 仕様をテストする。
- preset 名の一意性をテストする。
- color 値が `0.0 <= r,g,b <= 1.0` に収まることをテストする。
- opacity 値が `0.0 <= opacity <= 1.0` に収まることをテストする。
- `scalar_opacity_unit_distance` が指定された場合は `> 0.0` であることをテストする。
- unknown preset 名で明確な `ValueError` になることをテストする。

確認:

- この時点では red test でもよい。
- テスト名で仕様が読める状態にする。

理由:

- preset 値は後で調整されるため、構造と検証ルールを先に固定する。

---

## 2. `feat(tf): introduce builtin transfer function registry`

目的: built-in preset をソースコード管理で追加する。

対象:

- `qv/viewers/transfer_functions.py` 新規
- `tests/viewers/test_transfer_functions.py`

このコミットでやること:

- `TransferFunctionPreset` dataclass を追加する。
- `get_transfer_function_preset(name)` を追加する。
- `list_transfer_function_presets()` を追加する。
- `validate_transfer_function_preset()` を追加する。
- built-in registry を追加する。
- `default_linear` preset を追加する。
- CT 初期 preset を追加する。

初期 built-in preset:

- `default_linear`
- `ct_abdomen_soft_tissue`
- `ct_liver`
- `ct_head_brain`
- `ct_head_bone`
- `ct_bone`
- `ct_lung`
- `ct_vessel`

確認:

- `pytest tests/viewers/test_transfer_functions.py`
- 全 built-in preset が validation を通る。
- `default_linear` が存在する。

理由:

- `VolumeViewer` に触る前に、TF preset の独立モジュールを安定させる。

---

## 3. `test(volume): cover default linear transfer function compatibility`

目的: `default_linear` が現状の白黒線形 TF と同等であることを固定する。

対象:

- `tests/viewers/test_volume_viewer.py` 新規、または既存 viewer テストへ追加
- 必要なら `tests/viewers/conftest.py`

このコミットでやること:

- sample `WindowSettings` を使い、`default_linear` 適用後の color/opacity point を検証する。
- `CLIPPED_SCALAR` が opacity 0 になることを検証する。
- window 下限が black / opacity 0 になることを検証する。
- window 上限が white / opacity 1 になることを検証する。

確認:

- この時点では red test でもよい。
- VTK の point 検証が不安定なら、VTK function へ投入する直前の normalized point 生成 helper をテスト対象にする。

理由:

- 最初の refactor で見た目を変えないことが、この機能の安全条件になる。

---

## 4. `refactor(volume): route default transfer function through preset registry`

目的: 既存表示を変えずに、`VolumeViewer` の TF 更新経路を preset 対応へ置き換える。

対象:

- `qv/viewers/volume_viewer.py`
- `qv/viewers/transfer_functions.py`
- `tests/viewers/test_volume_viewer.py`

このコミットでやること:

- `VolumeViewer` に `_transfer_function_preset_name = "default_linear"` を追加する。
- `_apply_window_settings()` の既存ロジックを helper へ委譲する。
- `default_linear` 選択時は現状と同じ color/opacity を生成する。
- `CLIPPED_SCALAR` の透明化を維持する。
- `update_transfer_functions()` の互換 wrapper は維持する。

確認:

- `pytest tests/viewers/test_volume_viewer.py tests/viewers/test_transfer_functions.py`
- 手動確認では既存表示と大きく変わらないことを確認する。

理由:

- ここは挙動変更なしの refactor として分ける。CT preset の導入と混ぜない。

---

## 5. `feat(volume): add transfer function preset switching API`

目的: `VolumeViewer` から CT preset を切り替えられるようにする。

対象:

- `qv/viewers/volume_viewer.py`
- `qv/viewers/transfer_functions.py`
- `tests/viewers/test_volume_viewer.py`

このコミットでやること:

- `set_transfer_function_preset(name: str)` を追加する。
- `current_transfer_function_preset_name` property を追加する。
- `available_transfer_function_presets()` を追加する。
- preset の `default_window` がある場合は `WindowSettings` を更新する。
- preset 切り替え時の render は最後に 1 回だけ行う。
- unknown preset 名は `ValueError` とする。

確認:

- `pytest tests/viewers/test_volume_viewer.py tests/viewers/test_transfer_functions.py`
- `ct_abdomen_soft_tissue` 選択時に WW/WL が `WL 40 / WW 350` へ更新される。
- `ct_head_brain` 選択時に WW/WL が `WL 40 / WW 80` へ更新される。
- `default_linear` に戻せる。

理由:

- UI なしでも API 経由で実データ比較できる状態にする。

---

## 6. `feat(volume): support opacity unit distance and gradient opacity presets`

目的: preset ごとの volume rendering 調整パラメータを VTK property に反映する。

対象:

- `qv/viewers/volume_viewer.py`
- `qv/viewers/transfer_functions.py`
- `tests/viewers/test_volume_viewer.py`
- `tests/viewers/test_transfer_functions.py`

このコミットでやること:

- `scalar_opacity_unit_distance` を `vtkVolumeProperty.SetScalarOpacityUnitDistance(...)` に反映する。
- `gradient_opacity_points` が空でない場合のみ `vtkPiecewiseFunction` を作成して `SetGradientOpacity(...)` する。
- `gradient_opacity_points` が空の場合の既存挙動を壊さない。
- preset 切り替え時に前回 gradient opacity が残留しないようにする。

確認:

- `pytest tests/viewers/test_volume_viewer.py tests/viewers/test_transfer_functions.py`
- gradient opacity 未指定の built-in preset で例外が出ない。
- `scalar_opacity_unit_distance` 指定 preset で property に値が反映される。

理由:

- color/opacity と volume property の調整は関心が近いが、基本 preset 切替とは別コミットにして差分を小さくする。

---

## 7. `test(tf): cover user preset json validation and fallback`

目的: user preset JSON の読み込み仕様をテストで固定する。

対象:

- `tests/viewers/test_transfer_functions.py`
- 必要なら `tests/app/test_app_settings_manager.py`

このコミットでやること:

- valid JSON から user preset を読み込めることをテストする。
- `schema_version` 未対応時に明確に拒否されることをテストする。
- builtin と同名の user preset が拒否されることをテストする。
- user preset 同士の同名重複が拒否されることをテストする。
- JSON 破損時も builtin registry は利用できることをテストする。

確認:

- この時点では red test でもよい。

理由:

- user preset はファイル破損や手編集を前提に、防御的な仕様を先に固める必要がある。

---

## 8. `feat(tf): load user transfer function presets from json`

目的: user preset JSON を読み込み、built-in registry と統合する。

対象:

- `qv/viewers/transfer_functions.py`
- 必要なら `qv/app/app_settings_manager.py`
- `tests/viewers/test_transfer_functions.py`

このコミットでやること:

- `load_user_transfer_function_presets(path)` を追加する。
- `build_transfer_function_registry(user_preset_path=None)` を追加する。
- user preset 読み込み時に validation を行う。
- 読み込み失敗時はログを出し、built-in preset のみで継続する。
- user preset の `source` は `"user"` に正規化する。

確認:

- `pytest tests/viewers/test_transfer_functions.py`
- 破損 JSON でも `default_linear` は取得できる。
- builtin preset を user preset が上書きできない。

理由:

- まず読み込み専用で実装し、保存・UI編集とは分ける。

---

## 9. `feat(tf): save user transfer function presets to json`

目的: UI からの将来編集に備え、user preset の保存 API を追加する。

対象:

- `qv/viewers/transfer_functions.py`
- `tests/viewers/test_transfer_functions.py`

このコミットでやること:

- `save_user_transfer_function_presets(path, presets)` を追加する。
- JSON に `schema_version` を出力する。
- builtin preset は保存対象に含めない。
- 保存前に validation を行う。
- 出力順を安定させる。

確認:

- `pytest tests/viewers/test_transfer_functions.py`
- 保存した JSON を再読み込みして同等の preset になる。
- builtin preset が JSON に混入しない。

理由:

- 保存 API は UI 編集機能の土台だが、UI とは独立してテストできる。

---

## 10. `feat(ui): expose transfer function preset selection`

目的: ユーザーが画面上で TF preset を切り替えられるようにする。

対象:

- `qv/ui/mainwindow.py`
- `qv/ui/widgets/multi_viewer_panel.py` 必要時
- `qv/viewers/volume_viewer.py`
- `tests/ui/test_mainwindow.py` 必要時

このコミットでやること:

- menu または toolbar に TF preset 選択 UI を追加する。
- 表示には `display_name` を使う。
- 選択変更で `VolumeViewer.set_transfer_function_preset(name)` を呼ぶ。
- viewer 未ロード時の選択変更で例外が出ないようにする。
- 初期 UI 表示は `current_transfer_function_preset_name` と同期する。

確認:

- `pytest tests/ui/test_mainwindow.py tests/viewers/test_volume_viewer.py tests/viewers/test_transfer_functions.py`
- 手動で `default_linear`、`ct_abdomen_soft_tissue`、`ct_head_brain` を切り替えられる。

理由:

- 値と API が安定してから UI を追加することで、手戻りを減らす。

---

## 11. `fix(tf): make CT transfer function presets follow WW/WL`

目的: `default_linear` 以外の CT preset でも、右ドラッグによる WW/WL 調整が見た目に反映されるようにする。

背景:

- `default_linear` は active `WindowSettings` から TF point を生成するため、WW/WL 調整で見た目が変わる。
- CT preset は HU 絶対値の `color_points` / `opacity_points` をそのまま使っているため、WW/WL の値が変わっても TF point が変わらない。
- UI で preset 選択可能になった後の基本操作性に関わるため、selected preset 永続化より先に仕様を固定する。

対象:

- `qv/viewers/transfer_functions.py`
- `tests/viewers/test_transfer_functions.py`
- 必要なら `docs/devel/transfer_function_presets_spec.md`

このコミットでやること:

- `default_linear` は現状互換のまま維持する。
- `default_window` を持つ非 `default_linear` preset では、preset point の scalar 値を active `WindowSettings` に線形 remap する。
- remap は `color_points` と `opacity_points` に適用する。
- `gradient_opacity_points` は勾配値なので WW/WL remap しない。
- `scalar_opacity_unit_distance` は距離スケールなので WW/WL remap しない。
- `default_window is None` の非 `default_linear` preset は remap せず固定 scalar point として扱う。

remap 仕様:

```python
default_min, default_max = preset.default_window.get_range()
active_min, active_max = window_settings.get_range()

mapped_scalar = active_min + (
    (preset_scalar - default_min)
    * ((active_max - active_min) / (default_max - default_min))
)
```

確認:

- `pytest tests/viewers/test_transfer_functions.py tests/viewers/test_volume_viewer.py`
- `ct_head_brain` などの CT preset 選択後、右ドラッグで見た目が変化する。
- `default_linear` の既存互換が維持される。
- gradient opacity point は active window によって変化しない。

理由:

- TF preset 選択後の基本操作性を安定させる。
- Step 12 の selected preset 永続化に進む前に、保存される preset の実操作上の意味を固定する。

---

## 12. `feat(settings): persist selected transfer function preset`

目的: 最後に選択した TF preset を次回起動時にも復元する。

対象:

- `qv/app/app_settings_manager.py`
- `qv/ui/mainwindow.py`
- `docs/devel/app_settings.md` 必要時
- `tests/app/test_app_settings_manager.py`
- `tests/ui/test_mainwindow.py` 必要時

このコミットでやること:

- app settings に selected TF preset 名を追加する。
- 不明な preset 名が保存されている場合は `default_linear` に fallback する。
- preset 選択時に設定を保存する。
- volume 初期化時に保存値を反映する。

確認:

- `pytest tests/app/test_app_settings_manager.py tests/ui/test_mainwindow.py tests/viewers/test_transfer_functions.py`
- 不正な保存値でも起動が壊れない。

理由:

- UI 選択が入った後に永続化を追加する方が責務が明確になる。

---

## 13. `docs(tf): document transfer function preset workflow`

目的: 実装後の開発・調整手順をドキュメントに反映する。

対象:

- `docs/devel/transfer_function_presets_spec.md`
- `docs/devel/transfer_function_implementation_guide.md`
- 必要なら `README.md`

このコミットでやること:

- 実装済み API 名に仕様書を合わせる。
- built-in preset 追加手順を記載する。
- user preset JSON の場所と schema を記載する。
- 手動評価手順を更新する。

確認:

- ドキュメント上の API 名と実装名が一致している。
- 新規開発者が preset 追加・調整を再現できる。

理由:

- 仕様書先行で進めるため、最後に実装との差分を必ず戻す。

---

## 推奨実施順

最小実用単位:

1. commit 1
2. commit 2
3. commit 3
4. commit 4
5. commit 5

この時点で、UI なしで built-in CT preset を実データ評価できる。

user preset 対応:

1. commit 7
2. commit 8
3. commit 9

UI と運用:

1. commit 10
2. commit 11
3. commit 12
4. commit 13

## 実データ評価チェック

built-in CT preset が API 経由で切り替え可能になった時点で、以下を記録する。

- dataset 名または匿名化 ID
- preset 名
- performance profile 名
- camera pose
- WW/WL
- `ScalarOpacityUnitDistance`
- banding の有無
- jittering 由来の粒状感
- 組織境界の視認性
- interaction 時 FPS

最低限、以下は目視確認する。

- `default_linear`
- `ct_abdomen_soft_tissue`
- `ct_head_brain`
- `ct_bone`

## 完了条件

- `default_linear` が既存表示互換を維持する。
- CT preset を UI または API から切り替えられる。
- CT preset 選択中も WW/WL 調整で見た目が変化する。
- `CLIPPED_SCALAR` の透明化が全 preset で維持される。
- `PerformanceProfile` と TF preset を独立して切り替えられる。
- user preset JSON が壊れていても built-in preset だけで起動継続できる。
- selected preset をアプリ設定から復元できる。
