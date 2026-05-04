# アプリケーション設定仕様（AppSettingsManager）

本書は `AppSettingsManager` が管理するアプリケーション設定の仕様・読み込み順・キー規約・拡張手順をまとめた開発者向けドキュメントです。

対象:
- `qv/app/app_settings_manager.py`

---

## 1. 目的と設計方針

- **設定の最終的な有効値（effective settings）**を一箇所で決め、呼び出し側の実装を単純化する
- 設定値の型・範囲を **読み込み時に検証**し、異常値でアプリが落ちないようにする
- ユーザー上書きは **QSettings** に永続化し、次回起動でも保持する
- 呼び出し側は `dict` を直接扱わず、`AppSettingsManager` の **プロパティ / setter** 経由で利用する

---

## 2. 設定の読み込み順（有効設定の決定）

現状実装の読み込み順は以下です。

1. **コード内 `base_defaults`** を最終フォールバックにする
2. **`settings/app.json`** が存在すれば読み込んで merge する
3. **`settings/viewer.json`** が存在すれば読み込んで merge する
4. **QSettings の値で上書き**する
5. 上書き値は **バリデーション関数**で検証し、異常ならフォールバックする

## 2.1 JSON デフォルトファイル仕様

本プロジェクトでは、コード内 `DEFAULTS` を最終フォールバックとしつつ、
**JSON ファイルによるデフォルト定義** を優先的に読み込む。

### settings/app.json

- トップレベルオブジェクト(dict)
- 想定するキーは `general` / `view` / `mpr`
- 部分的に指定可能（指定されていないキーは `base_defaults` にフォールバック）

example:
```json
{
  "general": {
    "run_mode": "development",
    "logging_level": "INFO"
  },
  "view": {
    "rotation_step_deg": 5.0
  },
  "mpr": {
    "slice_drag_direction_mode": "patient_orientation",
    "wheel_slice_direction_mode": "patient_orientation"
  }
}
```

### settings/viewer.json

`viewer.json` は Viewer / View 系のデフォルトを用途別に分割して持つためのファイルです。
本プロジェクトでは、 **2つの形式を許可**しています。

#### フラット

```json
{
  "rotation_step_deg": 2.0
}
```

#### ネスト

```json
{
  "view": {
    "rotation_step_deg": 2.0
  },
  "mpr": {
    "slice_drag_direction_mode": "patient_orientation",
    "wheel_slice_direction_mode": "patient_orientation"
  }
}
```

フラット形式は内部的に `{"view": {...}}` に正規化され、 `base_defaults` と deep-merge されます。  
ネスト形式では `view` / `mpr` などのセクションをそのまま deep-merge します。

### 欠損･破損時の挙動

- Production(strict ではない)
  - 欠損･破損していても起動を継続し、ログに継続を出します（フォールバック） 
- Development(strict)
  - 欠損･破損は例外 (`SettingsError`) として扱い、早期に問題を顕在化させます。

strict 判定条件:
- 環境変数 `QV_STRICT_SETTINGS=1` が指定されている場合
- それ以外では `QSettings` の `general/run_mode` が `development` / `verbose`の場合

---

## 3. データモデル

設定は dataclass として保持されます。

- `AppSettingsData`
  - `GeneralConfig`
    - `run_mode: RunMode`（既定: `RunMode.PRODUCTION`）
    - `logging_level: str`（既定: `"INFO"`）
  - `ViewConfig`
    - `rotation_step_deg: float`（既定: `5.0`）
  - `MprConfig`
    - `slice_drag_direction_mode: SliceNavigationDirectionMode`
    - `wheel_slice_direction_mode: SliceNavigationDirectionMode`

内部的には `DEFAULTS` が初期値の「ソース」となり、`_load_effective()` で `AppSettingsData` に変換されます。

### 3.1 MPR スライス移動方向

MPR のスライス移動方向は、左ドラッグとマウスホイールで個別に設定できる。

```py
class SliceNavigationDirectionMode(str, Enum):
    PATIENT_ORIENTATION = "patient_orientation"
    SLICE_INDEX = "slice_index"
```

| 値 | GUI 表示名 | 意味 |
|---|---|---|
| `patient_orientation` | 患者方向に合わせる | Patient Orientation を基準にスライス移動方向を決める |
| `slice_index` | スライス番号順に移動する | slice index の増減方向をそのまま使う |

既定値はどちらも `patient_orientation` とする。

---

## 4. DEFAULTS（コード内デフォルト）

`DEFAULTS` は辞書で定義されています。

- `general.run_mode`
- `general.logging_level`
- `view.rotation_step_deg`
- `mpr.slice_drag_direction_mode`
- `mpr.wheel_slice_direction_mode`

例（現状）:
```py
DEFAULTS = {
  "general": {"run_mode": "development", "logging_level": "INFO"},
  "view": {"rotation_step_deg": 5.0},
  "mpr": {
    "slice_drag_direction_mode": "patient_orientation",
    "wheel_slice_direction_mode": "patient_orientation",
  },
}
```

## 5. QSettings キー仕様

`AppSettingsManager` が参照・保存するキーは以下です。

### 5.1 正規キー

- `general/run_mode` : `"development" | "production" | "verbose"`
- `general/logging_level` : `"DEBUG" | "INFO" | "WARNING" | "ERROR"`
- `view/rotation_step_deg` : float（`0 < x <= 90`）
- `mpr/slice_drag_direction_mode` : `"patient_orientation" | "slice_index"`
- `mpr/wheel_slice_direction_mode` : `"patient_orientation" | "slice_index"`

### 5.2 互換キー（レガシー）

- `general/dev_mode` : truthy な文字列（`"1" "true" "yes" "on"` など）を真として扱う

レガシーキーが存在し、`general/run_mode` が存在しない場合に限り、

- `dev_mode == true` → `run_mode = development`
- `dev_mode == false` → `run_mode = production`

として変換されます。

---

## 6. バリデーション仕様（落とさない設計）

### 6.1 run_mode

- `RunMode` または文字列を受け取り、`development/production/verbose` に正規化
- 不正値の場合は `DEFAULTS` の `general.run_mode` にフォールバック

関数: `_validate_run_mode(v)`

### 6.2 logging_level

- 文字列を大文字化して `DEBUG/INFO/WARNING/ERROR` のみ許可
- 不正値は `base_defaults["general"]["logging_level"]` にフォールバック

関数: `_validate_logging_level(v)`

### 6.3 rotation_step_deg

- `float` 変換できない場合は`base_defaults["view"]["rotation_step_deg"]` にフォールバック
- 範囲外（`<= 0` または `> 90`）の場合も同様

関数: `_validate_rotation_step(v)`

### 6.4 MPR スライス移動方向

- 文字列または `SliceNavigationDirectionMode` を受け取る
- 許可値は `patient_orientation` / `slice_index`
- 不正値の場合は `base_defaults["mpr"]` の該当値にフォールバック

関数案:

```py
def _validate_slice_navigation_direction_mode(v: Any) -> SliceNavigationDirectionMode:
    ...
```

---

## 7. 公開 API（呼び出し側が使うもの）

### 7.1 読み取り（プロパティ）

- `run_mode: RunMode`
- `dev_mode: bool`（`run_mode is DEVELOPMENT` の互換ビュー）
- `logging_level: str`
- `rotation_step_deg: float`
- `mpr_slice_drag_direction_mode: SliceNavigationDirectionMode`
- `mpr_wheel_slice_direction_mode: SliceNavigationDirectionMode`
- `data: AppSettingsData`
- `to_dict() -> dict`（デバッグ用途）

### 7.2 書き込み（setter）

- `set_run_mode(v: str | RunMode)`
- `set_dev_mode(v: bool)`（互換 shim）
- `set_logging_level(v: str)`
- `set_rotation_step_deg(v: float)`
- `set_mpr_slice_drag_direction_mode(v: str | SliceNavigationDirectionMode)`
- `set_mpr_wheel_slice_direction_mode(v: str | SliceNavigationDirectionMode)`

setter は `QSettings` に即保存し、同時に in-memory の dataclass も更新します。

---

## 8. リセット API

- `reset_all_to_default()`
  - `general` / `view` / `mpr` を `QSettings` から remove し、再ロードする
  - docstring では「ショートカットは別管理」と明記
- `reset_section(section: str)`
  - `general` / `view` / `mpr` のいずれかを remove し、再ロードする
  - 不正な `section` は `ValueError`

---

## 9. MPR オプション仕様

### 9.1 対象設定

今回追加する MPR オプションは以下の 2 つです。

| 設定 | QSettings キー | 既定値 |
|---|---|---|
| スライスドラッグ方向 | `mpr/slice_drag_direction_mode` | `patient_orientation` |
| ホイールスライス方向 | `mpr/wheel_slice_direction_mode` | `patient_orientation` |

どちらもアプリ全体設定とし、すべての MPR viewer に適用する。  
viewer ごと、plane ごとの個別設定は現時点では持たない。

### 9.2 モードの意味

#### `patient_orientation`

Patient Orientation を基準にスライス移動方向を決定する。

ドラッグ:

| Plane | 上ドラッグ | 下ドラッグ |
|---|---|---|
| Axial | Superior | Inferior |
| Coronal | Anterior | Posterior |
| Sagittal | Left | Right |

ホイール:

| Plane | wheel forward | wheel backward |
|---|---|---|
| Axial | Superior | Inferior |
| Coronal | Anterior | Posterior |
| Sagittal | Left | Right |

#### `slice_index`

Patient Orientation を考慮せず、slice index の増減方向をそのまま使う。

| 操作 | 挙動 |
|---|---|
| 上ドラッグ | slice index を増やす |
| 下ドラッグ | slice index を減らす |
| wheel forward | slice index を増やす |
| wheel backward | slice index を減らす |

### 9.3 UI 方針

UI 表示名は以下とする。

| 内部値 | GUI 表示名 |
|---|---|
| `patient_orientation` | 患者方向に合わせる |
| `slice_index` | スライス番号順に移動する |

初期 UI は MPR 設定として提供する。  
将来的に Preferences ダイアログを整備する場合は、MPR セクションに以下を配置する。

- スライスドラッグ方向
- ホイールスライス方向

設定変更後は、`AppSettingsManager` に保存し、`MainWindow` または `MultiViewerPanel` から既存 MPR viewer へ反映する。

---

## 10. 拡張手順（新しい設定を追加する場合）

1. `DEFAULTS` に追加（最後の砦）
2. dataclass（`GeneralConfig` / `ViewConfig` / `MprConfig`）にフィールド追加
3. バリデーション関数を追加（型/範囲）
4. `_apply_qsettings_overrides()` に読み込み・上書き処理を追加
5. `_make_model_from()` に反映
6. `AppSettingsManager` にプロパティ / setter を追加
7. docs 更新（本ファイル）
8. テスト追加（推奨）

---

## 11. テスト観点（推奨）

- `QSettings` に値がない場合：`DEFAULTS` がそのまま反映される
- 互換キー（`general/dev_mode`）がある場合：`run_mode` に反映される
- 不正値（`run_mode` / `logging_level` / `rotation_step_deg` / MPR direction mode）：
  - 例外で落ちず、フォールバックする
- `reset_all_to_default` / `reset_section` が期待通りキーを remove する
- MPR direction mode の setter が QSettings と in-memory model の両方を更新する

> NOTE: pytest の `tmp_path` で `QSettings` を隔離するには工夫が必要なため、最小はバリデーション関数の単体テストから推奨します。
