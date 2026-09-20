# CT Transfer Function プリセット仕様

## 目的

本仕様は、`qv/viewers/volume_viewer.py` の volume rendering に対して、CT の部位・観察目的別に Transfer Function（以下 TF）を切り替えられるようにするための設計方針を定義する。

[実装ガイド](transfer_function_implementation_guide.md) は preset の追加・保存・評価手順を扱い、本書は実装済み API とデータ仕様を扱う。

## 背景

`VolumeViewer` の初期 preset `default_linear` は、`WindowSettings` から以下の TF を生成する。

- Color TF: window 下限を黒、window 上限を白にする線形グレースケール
- Opacity TF: window 下限を 0、window 上限を 1 にする線形不透明度
- `CLIPPED_SCALAR` は透明化対象として扱う

この方式は現状互換性が高い一方、CT の腹部、頭部、肺野、骨、血管などの観察目的に対して十分な表現力がない。特に volume rendering では、2D MPR の WW/WL と同じ値だけでは適切な見えにならないため、HU に基づいた color/opacity preset が必要になる。

## 基本方針

1. TF preset は `PerformanceProfile` から独立させる。
2. `default_linear` preset を用意し、既存表示との互換性を維持する。
3. CT preset は「部位」だけでなく「観察目的」単位で分ける。
4. built-in preset はコード API と `View > Transfer Functions` メニューから選択する。
5. DICOM tag による自動選択は初期実装では必須にしない。
6. `CLIPPED_SCALAR` は全 preset で必ず opacity 0 とする。
7. 標準 preset はソースコードに組み込み、ユーザー定義 preset は JSON に保存する。
8. 最後に選択した TF preset の保存・復元は実装しない（タスク12は中止）。次回起動時に同じ TF を再選択する意義が薄いため、新しい viewer は `default_linear` で開始する。

## 責務分離

### PerformanceProfile

`qv/viewers/performance_profile.py` は描画性能・品質のみを扱う。

対象:

- `shade_enabled`
- `image_sample_distance`
- `auto_adjust_sample_distances`
- `interactive_image_sample_distance`
- `interactive_shade_enabled`
- `use_jittering`
- `interactive_use_jittering`

TF preset 名は `PerformanceProfile` に持たせない。

理由:

- `quality + ct_abdomen_soft_tissue`
- `speed + ct_abdomen_soft_tissue`
- `quality + ct_head_brain`

のように、性能設定と TF 設定を直交させるため。

### TransferFunctionPreset

`qv/viewers/transfer_functions.py` で TF preset を管理する。

実装済み dataclass:

```python
from dataclasses import dataclass

from qv.core.window_settings import WindowSettings


@dataclass(frozen=True)
class TransferFunctionPreset:
    name: str
    display_name: str
    default_window: WindowSettings | None
    color_points: tuple[tuple[float, float, float, float], ...]
    opacity_points: tuple[tuple[float, float], ...]
    gradient_opacity_points: tuple[tuple[float, float], ...] = ()
    scalar_opacity_unit_distance: float | None = None
    source: str = "builtin"
```

各 point の意味:

- `color_points`: `(hu, r, g, b)`
- `opacity_points`: `(hu, opacity)`
- `gradient_opacity_points`: `(gradient, opacity)`

`default_window` は preset 選択時に初期 WW/WL として適用する。ただし、`default_linear` は現状互換のため、既存の読み込み時 window を維持できるよう `None` を許容する。

`source` は preset の由来を表す。

- `builtin`: アプリに組み込まれた標準 preset
- `user`: ユーザーが作成・保存した preset

## プリセット保存方式

TF preset はハイブリッド方式で管理する。

- 標準 preset: ソースコードに組み込む
- ユーザー定義 preset: JSON に保存する
- `build_transfer_function_registry(path)` は両者を統合した `TransferFunctionRegistry` を返す

現在の `VolumeViewer` とメニューは built-in 専用 API を参照する。統合 registry を viewer に渡す API、自動読み込み、user preset の編集・選択 UI は未実装である。

### 標準 preset

標準 preset は `qv/viewers/transfer_functions.py` 内で定義する。

理由:

- `default_linear` の現状互換をテストで固定しやすい。
- CT 部位別 preset をアプリの品質保証対象として扱える。
- JSON ファイル欠落・破損・パス問題で標準表示が壊れない。
- 型チェック、単体テスト、コードレビューがしやすい。
- `CLIPPED_SCALAR` など実装上の特殊値と安全に統合できる。

標準 preset の dataclass は frozen で、UI に編集機能はない。定義を複製して user preset として保存する場合は、実装ガイドの Python API 例を使う。

### ユーザー定義 preset

保存先は load/save API の `path` 引数で明示する。固定の保存場所や `AppSettingsManager` によるパス解決は未実装である。
開発時の配置例はプロジェクトルートからの `settings/transfer_function_presets.json` とする。この場所に置くだけではアプリに読み込まれない。

JSON は UTF-8、対応する `schema_version` は `1`。

```json
{
  "schema_version": 1,
  "presets": [
    {
      "name": "user_abdomen_custom",
      "display_name": "My Abdomen Custom",
      "default_window": {
        "level": 40,
        "width": 350
      },
      "color_points": [
        [-1000, 0.0, 0.0, 0.0],
        [40, 0.8, 0.6, 0.45],
        [300, 1.0, 0.9, 0.75]
      ],
      "opacity_points": [
        [-1000, 0.0],
        [-100, 0.0],
        [40, 0.08],
        [300, 0.35],
        [1000, 0.85]
      ],
      "gradient_opacity_points": [],
      "scalar_opacity_unit_distance": 1.2
    }
  ]
}
```

各 preset の必須キーは `name`、`display_name`、`color_points`、`opacity_points`。
`default_window` は省略または `null` で固定 scalar point になり、指定する場合は `level` と `width` が必要（`width >= 1.0`）。
`gradient_opacity_points` の省略値は `[]`、`scalar_opacity_unit_distance` は省略または `null` を許容する。
`source` は保存せず、読み込み時に `"user"` に正規化する。

保存時・読み込み時には各 preset の validation を行う。

検証項目:

- `schema_version` が `1` である（読み込み時）。
- `name` が空でない。
- `display_name` が空でない。
- `name` が preset registry 内で一意である（読み込み・registry 構築時）。
- user preset が builtin preset と同じ `name` を使っていない（読み込み時）。
- color point が `(hu, r, g, b)` 形式である。
- opacity point が `(hu, opacity)` 形式である。
- color/opacity point は空でなく、scalar 順に並ぶ（同じ scalar 値は許容）。gradient point も勾配値順に並ぶ。
- color 値が `0.0 <= r,g,b <= 1.0` を満たす。
- opacity 値が `0.0 <= opacity <= 1.0` を満たす。
- `scalar_opacity_unit_distance` が指定されている場合は `> 0.0` である。

`load_user_transfer_function_presets(path)` は破損・不正データやファイル欠損を例外として返す。
`build_transfer_function_registry(path)` は読み込み例外をログに記録し、ファイル内の user preset 全体を除外して built-in のみを返す。
現在のアプリ起動はこの JSON を読み込まないため、JSON の破損の影響を受けない。

`save_user_transfer_function_presets(path, presets)` は入力の各 preset を検証し、`source == "user"` のみを入力順に保存する。親ディレクトリは自動作成し、既存ファイルは置き換える。名前の衝突は保存時には検証しないため、保存後に strict な load API で再読み込みして確認する。

### 名前衝突ルール

標準 preset は上書き不可とする。

ルール:

- 名前の比較・検索は前後の空白を除去し、小文字化して行う。
- builtin と同名の user preset がある JSON は読み込みを拒否する。
- builtin preset を調整して保存したい場合は、別名の user preset として複製する（編集 UI は未実装）。
- user preset 同士で同名がある場合は、後勝ちにせず validation error とする。

推奨命名:

- builtin: `ct_abdomen_soft_tissue`
- user: `user_abdomen_custom`

UI 表示では `display_name` を使うため、内部名は安定した識別子として扱う。

## built-in preset

以下の8種類を定義している。

| preset | 表示名 | 目的 | 初期 WW/WL |
|---|---|---|---:|
| `default_linear` | Default Linear | 現状互換の白黒線形 TF | 現行 window を維持 |
| `ct_abdomen_soft_tissue` | CT Abdomen Soft Tissue | 腹部軟部組織 | WW 350 / WL 40 |
| `ct_liver` | CT Liver | 肝実質・腹部造影評価の開始点 | WW 150 / WL 70 |
| `ct_head_brain` | CT Head Brain | 脳実質 | WW 80 / WL 40 |
| `ct_head_bone` | CT Head Bone | 頭蓋骨 | WW 1800 / WL 350 |
| `ct_bone` | CT Bone | 骨全般 | WW 2000 / WL 300 |
| `ct_lung` | CT Lung | 肺野 | WW 1500 / WL -600 |
| `ct_vessel` | CT Vessel | 造影血管強調 | WW 700 / WL 200 |

注意:

- 上記 WW/WL は初期値であり、volume rendering 用 opacity は実データで別途調整する。
- 血管と骨は HU が重なるため、TF だけで完全分離できない。
- `ct_vessel` は CTA/MRA 相当の強調表示ではなく、造影 CT の高 HU 域を目立たせる preset と位置づける。

## TF 適用ルール

`VolumeViewer` は現在の TF preset 名を状態として持つ。

実装済み API:

```python
def set_transfer_function_preset(self, name: str, *, render: bool = True) -> None:
    ...

@property
def current_transfer_function_preset_name(self) -> str:
    ...

def available_transfer_function_presets(self) -> tuple[str, ...]:
    ...
```

適用手順:

1. preset 名を registry から解決する。
2. 同じ preset なら何もしない。異なる場合は `self._transfer_function_preset_name` を更新する。未ロードなら名前を保持して終了する。
3. ロード済みで preset に `default_window` がある場合は `set_window_settings(..., render=False)` を呼ぶ。このメソッド内で scalar range に clamp する。
4. 現在の `WindowSettings` と preset から color/opacity/gradient opacity を再構築する。
5. `scalar_opacity_unit_distance` と gradient opacity を `vtkVolumeProperty` に反映する。
6. TF が更新され、`render=True` なら `update_view()` を最後に1回呼ぶ。`render=False` では描画しない。

`available_transfer_function_presets()` は built-in の内部名の tuple を返す。不明な名前の選択は `ValueError` となり、選択状態を変更しない。
`update_transfer_functions()` は現在の WW/WL で TF を再適用して描画する互換 wrapper として残している。

### モジュール API

| API | 戻り値・役割 |
|---|---|
| `list_transfer_function_presets()` | built-in の `tuple[TransferFunctionPreset, ...]`（UI 表示順） |
| `get_transfer_function_preset(name)` | built-in を取得。不明名は `ValueError` |
| `validate_transfer_function_preset(preset)` | 単一 preset を検証。不正なら `ValueError` |
| `load_user_transfer_function_presets(path)` | JSON を検証して user preset の tuple を返す |
| `save_user_transfer_function_presets(path, presets)` | user preset 定義を JSON に保存する |
| `build_transfer_function_registry(user_preset_path=None)` | built-in と user を統合した `TransferFunctionRegistry`。パス省略時は built-in のみ |
| `registry.presets` / `registry.names()` | 定義の tuple / 内部名の tuple（built-in の後に JSON 順の user preset） |
| `registry.get(name)` | built-in / user preset を取得。不明名は `None` |
| `build_transfer_function_points(*, preset, window_settings, clipped_scalar)` | VTK に投入する `TransferFunctionPoints` を生成 |

`TransferFunctionPoints` は `color_points`、`opacity_points`、`gradient_opacity_points` を持つ frozen dataclass である。unit distance は point に含めず、viewer が preset から直接反映する。

## default_linear の互換性

`default_linear` は既存実装と同じ結果を生成する。

Color TF:

- `CLIPPED_SCALAR -> black`
- `window_min -> black`
- `window_max -> white`

Opacity TF:

- `CLIPPED_SCALAR -> 0.0`
- `window_min -> 0.0`
- `window_max -> 1.0`

この preset を初期値にすることで、既存ユーザーの見え方を変更しない。

## CT preset の適用方針

CT preset は `default_window` における HU を基準に point を定義する。
`default_window` を持つ非 `default_linear` preset（user preset を含む）は、active WW/WL に合わせて color/opacity の scalar 座標を線形 remap する。

```python
default_min, default_max = preset.default_window.get_range()
active_min, active_max = window_settings.get_range()
mapped_scalar = active_min + (preset_scalar - default_min) * (
    (active_max - active_min) / (default_max - default_min)
)
```

window 外の point も同じ式で外挿し、RGB と opacity の値は変えない。
`default_window is None` の非 `default_linear` preset は固定 scalar point として扱う。
gradient opacity は勾配値、unit distance は距離なので remap しない。
`CLIPPED_SCALAR` の black / opacity 0 の point は remap 後に追加する。

これにより CT preset 選択後も右ドラッグの WW/WL 調整が表示に反映される。適用前に以下を確認する。

- scalar range が CT HU として妥当か
- 最小値が空気付近、最大値が骨・造影域まで含むか
- intercept/slope が reader 側で反映済みか

HU として妥当でない場合は、CT preset を適用しても正しく見えない。この場合は DICOM 読み込み処理側で rescale slope/intercept の扱いを確認する。

## Opacity 設計

初期 opacity は急峻にしすぎない。

理由:

- banding が目立ちやすくなる
- jittering 有効時に粒状感が増える
- window 操作時に見えが急変しやすい

推奨:

- 軟部組織 preset は 3-5 点以上の緩い立ち上がりにする。
- 骨 preset は低 HU 域を透明寄り、高 HU 域を強調する。
- 肺 preset は空気域を完全透明にせず、肺実質・血管・胸壁の関係が見えるよう段階的に上げる。
- 血管 preset は高 HU 域を強調するが、骨との分離限界を仕様上明記する。

## ScalarOpacityUnitDistance

`scalar_opacity_unit_distance` を `vtkVolumeProperty.SetScalarOpacityUnitDistance(value)` に反映する。

初期値の考え方:

- 未指定時は volume property 作成時に記録した既定値へ戻し、前の preset の値を残さない。
- 粒状感が強い preset は `1.2` から `2.0` の範囲で比較する。
- 値を大きくすると全体が薄くなりやすい。
- 値を小さくすると濃くなるが、ノイズや段差が目立ちやすい。

## Gradient Opacity

`gradient_opacity_points` は任意とする。

空でなければ `vtkPiecewiseFunction` を作成して `SetGradientOpacity(...)` に渡し、gradient opacity を有効にする。空なら無効化し、前の preset の効果を残さない（無効化 API がない VTK では空の function に置き換える）。現在の built-in preset はすべて未指定である。

注意:

- 効きすぎると低コントラスト病変や軟部組織の連続性が消える。
- まず color/opacity/scalar opacity unit distance の調整を優先する。

## UI 方針

`MainWindow` の `View > Transfer Functions` に built-in の `display_name` を排他的なチェック付き action として表示する。
選択時に `VolumeViewer.set_transfer_function_preset(name)` を呼び、メニュー初期化時とメニュー選択後に viewer の状態へチェックを同期する。
未ロードでも選択できる。user preset の編集・import/export UI は未実装である。

選択状態は viewer 内だけで保持する。最後の選択をアプリ設定へ保存・復元する機能は実装しない。

## 自動選択方針

初期実装では手動選択を標準とする。

将来拡張として、DICOM tag から初期 preset を推定してよい。

候補 tag:

- `BodyPartExamined`
- `SeriesDescription`
- `ProtocolName`
- `Modality`

ただし、施設差・表記揺れ・日本語/英語混在が大きいため、自動選択は best effort とし、ユーザーが手動で上書きできる必要がある。

## テスト方針

単体テスト:

1. `default_linear` が既存の color/opacity point と同等になる。
2. すべての preset が一意の `name` を持つ。
3. すべての preset の opacity が `0.0 <= opacity <= 1.0` を満たす。
4. すべての preset の color が `0.0 <= r,g,b <= 1.0` を満たす。
5. `CLIPPED_SCALAR` が最終 TF で opacity 0 になる。
6. 存在しない preset 名を指定すると明確な `ValueError` になる。
7. builtin preset は user preset で上書きできない。
8. user preset JSON が破損していても builtin preset の registry は利用できる。
9. user preset JSON の schema version が未対応の場合は明確に拒否される。
10. CT preset の color/opacity 座標が active WW/WL に追従し、gradient opacity は変化しない。
11. user preset 定義が JSON 保存・再読み込みで同等になる。

統合テスト:

1. volume 読み込み後に preset を切り替えて例外が出ない。
2. preset 切り替え時に `window_settings` が期待値へ更新される。
3. preset 切り替え後も clipping 済み領域が透明のまま維持される。
4. `PerformanceProfile` 切り替えと TF preset 切り替えが互いに状態を壊さない。

目視評価:

- 同一 CT dataset
- 同一 camera pose
- 同一 crop/clipping 状態
- 同一 performance profile
- 各 preset の静止画を保存して比較

評価項目:

- 組織境界の視認性
- banding
- jittering 由来の粒状感
- 低コントラスト領域の消失
- interaction 時 FPS

## 開発・調整手順

built-in 追加、user JSON の保存・再読み込み、テストコマンド、手動評価の記録項目は[実装ガイド](transfer_function_implementation_guide.md)を参照する。
タスクの履歴とタスク12の中止方針は[実装タスク](../tasks/transfer_function_presets_implementation_task.md)に記載する。

## 受け入れ基準

初期実装の受け入れ条件:

1. `default_linear` 選択時に既存表示と実質的に同じ見えになる。
2. CT preset を切り替えても例外が発生しない。
3. `CLIPPED_SCALAR` による clipping 透明化が維持される。
4. `PerformanceProfile` と TF preset を独立して切り替えられる。
5. `ImageSampleDistance < 1.0` を使わずに、主要 preset で顕著な描画欠けが出ない。
6. 少なくとも `ct_abdomen_soft_tissue` と `ct_head_brain` は実データで目視確認済みとする。
7. ユーザー定義 preset の読み込み失敗時も builtin preset だけで表示を継続できる。

## 将来拡張

- histogram 連動の自動 opacity 初期化
- ROI ベースの局所 TF
- DICOM tag による initial preset 推定
- 統合 registry の viewer 接続と user preset の編集・import/export UI
- ユーザー定義 preset の schema migration
- preset ごとの thumbnail preview
