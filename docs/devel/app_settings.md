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

1. **コード内 `DEFAULTS`** をベースにする  
2. **QSettings の値で上書き**する  
3. 上書き値は **バリデーション関数**で検証し、異常ならフォールバックする

※ 現状、JSON ファイルのデフォルト読み込みは未実装です（今後拡張予定なら別途 docs 追記）。

---

## 3. データモデル

設定は dataclass として保持されます。

- `AppSettingsData`
  - `GeneralConfig`
    - `run_mode: RunMode`（既定: `RunMode.PRODUCTION`）
    - `logging_level: str`（既定: `"INFO"`）
  - `ViewConfig`
    - `rotation_step_deg: float`（既定: `5.0`）

内部的には `DEFAULTS` が初期値の「ソース」となり、`_load_effective()` で `AppSettingsData` に変換されます。

---

## 4. DEFAULTS（コード内デフォルト）

`DEFAULTS` は辞書で定義されています。

- `general.run_mode`
- `general.logging_level`
- `view.rotation_step_deg`

例（現状）:
```py
DEFAULTS = {
  "general": {"run_mode": "development", "logging_level": "INFO"},
  "view": {"rotation_step_deg": 1.0},
}
```

## 5. QSettings キー仕様

`AppSettingsManager` が参照・保存するキーは以下です。

### 5.1 正規キー

- `general/run_mode` : `"development" | "production" | "verbose"`
- `general/logging_level` : `"DEBUG" | "INFO" | "WARNING" | "ERROR"`
- `view/rotation_step_deg` : float（`0 < x <= 90`）

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
- 不正値は `"INFO"` にフォールバック（現状実装）

関数: `_validate_logging_level(v)`

### 6.3 rotation_step_deg

- `float` 変換できない → `5.0` にフォールバック（現状実装）
- 範囲外（`<= 0` または `> 90`） → `5.0` にフォールバック（現状実装）

関数: `_validate_rotation_step(v)`

> NOTE: `DEFAULTS["view"]["rotation_step_deg"]` が `1.0` なのに対し、検証失敗時は `5.0` に固定フォールバックしています。  
> 「常に DEFAULTS に戻す」方針にしたい場合は、ここを `DEFAULTS` 参照へ統一するのが望ましいです。

---

## 7. 公開 API（呼び出し側が使うもの）

### 7.1 読み取り（プロパティ）

- `run_mode: RunMode`
- `dev_mode: bool`（`run_mode is DEVELOPMENT` の互換ビュー）
- `logging_level: str`
- `rotation_step_deg: float`
- `data: AppSettingsData`
- `to_dict() -> dict`（デバッグ用途）

### 7.2 書き込み（setter）

- `set_run_mode(v: str | RunMode)`
- `set_dev_mode(v: bool)`（互換 shim）
- `set_logging_level(v: str)`
- `set_rotation_step_deg(v: float)`

setter は `QSettings` に即保存し、同時に in-memory の dataclass も更新します。

---

## 8. リセット API

- `reset_all_to_default()`
  - `general` と `view` を `QSettings` から remove し、再ロードする
  - docstring では「ショートカットは別管理」と明記
- `reset_section(section: str)`
  - `general` または `view` のみ remove し、再ロードする
  - 不正な `section` は `ValueError`

---

## 9. 拡張手順（新しい設定を追加する場合）

1. `DEFAULTS` に追加（最後の砦）
2. dataclass（`GeneralConfig` or `ViewConfig`）にフィールド追加
3. バリデーション関数を追加（型/範囲）
4. `_apply_qsettings_overrides()` に読み込み・上書き処理を追加
5. `_make_model_from()` に反映
6. `AppSettingsManager` にプロパティ / setter を追加
7. docs 更新（本ファイル）
8. テスト追加（推奨）

---

## 10. テスト観点（推奨）

- `QSettings` に値がない場合：`DEFAULTS` がそのまま反映される
- 互換キー（`general/dev_mode`）がある場合：`run_mode` に反映される
- 不正値（`run_mode` / `logging_level` / `rotation_step_deg`）：
  - 例外で落ちず、フォールバックする
- `reset_all_to_default` / `reset_section` が期待通りキーを remove する

> NOTE: pytest の `tmp_path` で `QSettings` を隔離するには工夫が必要なため、最小はバリデーション関数の単体テストから推奨します。

