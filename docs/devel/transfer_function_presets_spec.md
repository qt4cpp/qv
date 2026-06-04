# CT Transfer Function プリセット仕様

## 目的

本仕様は、`qv/viewers/volume_viewer.py` の volume rendering に対して、CT の部位・観察目的別に Transfer Function（以下 TF）を切り替えられるようにするための設計方針を定義する。

既存の `transfer_function_implementation_guide.md` は TF 調整時の画質・性能ガイドであり、本書は実装仕様とプリセット設計を扱う。

## 背景

現状の `VolumeViewer` は `WindowSettings` から以下の単純な TF を生成している。

- Color TF: window 下限を黒、window 上限を白にする線形グレースケール
- Opacity TF: window 下限を 0、window 上限を 1 にする線形不透明度
- `CLIPPED_SCALAR` は透明化対象として扱う

この方式は現状互換性が高い一方、CT の腹部、頭部、肺野、骨、血管などの観察目的に対して十分な表現力がない。特に volume rendering では、2D MPR の WW/WL と同じ値だけでは適切な見えにならないため、HU に基づいた color/opacity preset が必要になる。

## 基本方針

1. TF preset は `PerformanceProfile` から独立させる。
2. `default_linear` preset を用意し、既存表示との互換性を維持する。
3. CT preset は「部位」だけでなく「観察目的」単位で分ける。
4. UI 追加より先に、コード API と preset 値を安定させる。
5. DICOM tag による自動選択は初期実装では必須にしない。
6. `CLIPPED_SCALAR` は全 preset で必ず opacity 0 とする。
7. 標準 preset はソースコードに組み込み、ユーザー定義 preset は JSON などの外部ファイルに保存する。

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

新規モジュール `qv/viewers/transfer_functions.py` を追加し、TF preset を一元管理する。

想定 dataclass:

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
- ユーザー定義 preset: JSON などの外部ファイルに保存する
- 実行時: どちらも `TransferFunctionPreset` に変換し、同じ registry から参照する

### 標準 preset

標準 preset は `qv/viewers/transfer_functions.py` 内で定義する。

理由:

- `default_linear` の現状互換をテストで固定しやすい。
- CT 部位別 preset をアプリの品質保証対象として扱える。
- JSON ファイル欠落・破損・パス問題で標準表示が壊れない。
- 型チェック、単体テスト、コードレビューがしやすい。
- `CLIPPED_SCALAR` など実装上の特殊値と安全に統合できる。

標準 preset は immutable とし、UI から直接編集できない。ユーザーが標準 preset を調整したい場合は「複製してユーザー定義 preset として保存する」流れにする。

### ユーザー定義 preset

ユーザー定義 preset はアプリ設定ディレクトリ配下の JSON ファイルに保存する。

想定ファイル名:

- `transfer_function_presets.json`

JSON は schema version を持つ。

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

保存時・読み込み時には validation を行う。

検証項目:

- `schema_version` が対応範囲内である。
- `name` が空でない。
- `name` が preset registry 内で一意である。
- user preset が builtin preset と同じ `name` を使っていない。
- color point が `(hu, r, g, b)` 形式である。
- opacity point が `(hu, opacity)` 形式である。
- color 値が `0.0 <= r,g,b <= 1.0` を満たす。
- opacity 値が `0.0 <= opacity <= 1.0` を満たす。
- `scalar_opacity_unit_distance` が指定されている場合は `> 0.0` である。

JSON の読み込みに失敗した場合は、標準 preset のみで起動を継続する。ユーザー定義 preset の破損は volume 表示不能にしない。

### 名前衝突ルール

標準 preset は上書き不可とする。

ルール:

- builtin と同名の user preset は読み込まない。
- UI では builtin preset の直接編集を禁止する。
- builtin preset を編集したい場合は user preset として複製保存する。
- user preset 同士で同名がある場合は、後勝ちにせず validation error とする。

推奨命名:

- builtin: `ct_abdomen_soft_tissue`
- user: `user_abdomen_custom`

UI 表示では `display_name` を使うため、内部名は安定した識別子として扱う。

## 初期 preset

初期実装では以下を定義する。

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

追加予定 API:

```python
def set_transfer_function_preset(self, name: str) -> None:
    ...

@property
def current_transfer_function_preset_name(self) -> str:
    ...

def available_transfer_function_presets(self) -> tuple[str, ...]:
    ...
```

適用手順:

1. preset 名を registry から解決する。
2. `self._transfer_function_preset` を更新する。
3. preset に `default_window` がある場合は scalar range で clamp して `set_window_settings(..., render=False)` を呼ぶ。
4. 現在の `WindowSettings` と preset から color/opacity/gradient opacity を再構築する。
5. `SetScalarOpacityUnitDistance()` が指定されていれば `vtkVolumeProperty` に適用する。
6. `update_view()` は最後に 1 回だけ呼ぶ。

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

CT preset は HU 絶対値を基準に point を置く。ただし、読み込み画像の scalar range に含まれない point は VTK 側で外挿・補間されるため、preset 適用前に以下を確認する。

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

`vtkVolumeProperty.SetScalarOpacityUnitDistance(value)` を preset ごとに指定可能にする。

初期値の考え方:

- 未指定時は VTK 既定または現行挙動を維持する。
- 粒状感が強い preset は `1.2` から `2.0` の範囲で比較する。
- 値を大きくすると全体が薄くなりやすい。
- 値を小さくすると濃くなるが、ノイズや段差が目立ちやすい。

## Gradient Opacity

`gradient_opacity_points` は任意とする。

初期実装では必須にしない。導入する場合は、低勾配領域の寄与を弱める目的に限定する。

注意:

- 効きすぎると低コントラスト病変や軟部組織の連続性が消える。
- まず color/opacity/scalar opacity unit distance の調整を優先する。

## UI 方針

初期段階では UI 追加を必須にしない。

推奨順序:

1. `VolumeViewer` API で preset 切り替え可能にする。
2. 実データで preset 値を比較・調整する。
3. 値が安定してから UI に combo box または menu action を追加する。
4. 必要に応じてアプリ設定に最後に選択した preset を保存する。

UI 追加時の候補:

- toolbar combo box
- menu: `View > Transfer Function`
- settings dialog の viewer 設定

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

## 実装順序

1. `qv/viewers/transfer_functions.py` を追加する。
2. `TransferFunctionPreset` と preset registry を実装する。
3. `default_linear` を実装し、既存表示と同等にする。
4. `VolumeViewer` に `_transfer_function_preset_name` を追加する。
5. `VolumeViewer._apply_window_settings()` を preset 適用へ委譲する。
6. `set_transfer_function_preset()` を追加する。
7. `scalar_opacity_unit_distance` 適用を追加する。
8. 必要になった段階で `gradient_opacity_points` を適用する。
9. 単体テストを追加する。
10. 実データで preset 値を調整する。
11. user preset JSON の load/save と validation を追加する。
12. UI を追加する。
13. 設定永続化と DICOM tag による初期推定を検討する。

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
- ユーザー定義 preset の import/export
- ユーザー定義 preset の schema migration
- preset ごとの thumbnail preview
