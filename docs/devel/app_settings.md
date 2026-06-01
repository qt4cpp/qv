# アプリケーション設定 開発者マニュアル

本書は `AppSettingsManager` が管理するアプリケーション設定の仕様と、
設定項目を追加する際の実装手順をまとめた開発者向けドキュメントです。

対象:

- `qv/app/app_settings_manager.py`
- `qv/ui/dialogs/settings_dialog.py`
- `qv/ui/mainwindow.py`
- `settings/viewer.json`
- `settings/app.json`（必要に応じて配置）
- `tests/app/test_app_settings_manager.py`
- `tests/ui/test_settings_dialog.py`

---

## 1. 目的と設計方針

`AppSettingsManager` は、アプリケーション全体で共有する設定値を一箇所で管理します。

- 最終的な有効値（effective settings）を一箇所で決める
- 設定値の型と範囲を読み込み時に検証する
- 異常値があっても Production では安全な値へフォールバックする
- ユーザーが変更した値は `QSettings` に永続化する
- 呼び出し側は JSON、`QSettings`、内部 `dict` を直接参照しない
- 呼び出し側は `AppSettingsManager` の property と setter を使用する

`AppSettingsManager` はアプリケーション起動時に一度生成し、必要な viewer や dialog に
同じインスタンスを渡します。viewer ごとに独立した manager を生成すると、GUI で更新した
値が既存 viewer に反映されないため注意してください。

---

## 2. 基本的な使い方

### 2.1 共有 manager を生成する

`MainWindow` は共有 manager を保持し、`MultiViewerPanel` と `SettingsDialog` に渡します。

```py
class MainWindow(QMainWindow):
    def __init__(self, settings_mgr: AppSettingsManager | None = None):
        super().__init__()
        self.setting = settings_mgr or AppSettingsManager()

        self.multi_viewer_panel = MultiViewerPanel(
            settings_mgr=self.setting,
            parent=self,
        )

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(
            settings_manager=self.setting,
            parent=self,
        )
        dialog.exec()
```

`MultiViewerPanel` も同じ manager を各 viewer に渡します。

```py
self.volume_viewer = VolumeViewer(
    settings_manager=self.setting,
    parent=self,
)
self.mpr_axial_viewer = MprViewer(
    settings_manager=self.setting,
    parent=self,
    plane=MprPlane.AXIAL,
)
```

### 2.2 設定値を読み取る

呼び出し側は property を参照します。

```py
mode = self.setting.mpr_slice_drag_direction_mode
rotation_step = self.setting.rotation_step_deg
```

enum の設定値は raw string ではなく enum と比較します。

```py
if mode is SliceNavigationDirectionMode.SLICE_INDEX:
    self.scroll_slice(steps)
```

### 2.3 設定値を保存する

書き込みには setter を使用します。

```py
settings.set_mpr_slice_drag_direction_mode("slice_index")
settings.set_rotation_step_deg(7.0)
```

setter は以下を同時に更新します。

1. `QSettings` にユーザー設定を永続化する
2. in-memory の `AppSettingsData` を更新する

---

## 3. 設定値の構造と読み込み順

設定値には役割の異なる層があります。

| 層 | 役割 |
|---|---|
| `base_defaults` | コード内の最終フォールバック |
| `settings/app.json` | アプリケーション全体の配布時デフォルト |
| `settings/viewer.json` | Viewer 関連の配布時デフォルト |
| `QSettings` | ユーザーが変更した永続設定 |
| `AppSettingsData` | merge と検証が完了した有効設定 |

有効値は次の順番で決まります。後から読み込まれた値が優先されます。

```text
base_defaults
  -> settings/app.json
  -> settings/viewer.json
  -> QSettings
  -> validator
  -> AppSettingsData
```

優先順位として表すと、次の順です。

```text
QSettings
  > settings/viewer.json
  > settings/app.json
  > base_defaults
```

---

## 4. JSON デフォルトファイル仕様

JSON は配布時のデフォルト値を定義するファイルです。
GUI から変更したユーザー設定の保存先ではありません。

どちらのファイルもトップレベルは JSON object とします。
部分的な指定が可能で、省略された項目は下位層の値にフォールバックします。

### 4.1 `settings/app.json`

アプリケーション全体のデフォルト値を記述します。
現在の Production 構成では配置されていないため、欠損時は `base_defaults` に
フォールバックします。

```json
{
  "general": {
    "run_mode": "development",
    "logging_level": "INFO"
  }
}
```

### 4.2 `settings/viewer.json`

Viewer 関連のデフォルト値を記述します。
新規実装ではセクションを明示するネスト形式を使用してください。

```json
{
  "view": {
    "rotation_step_deg": 5.0
  },
  "mpr": {
    "slice_drag_direction_mode": "patient_orientation",
    "wheel_slice_direction_mode": "patient_orientation"
  }
}
```

後方互換のため、`view` セクションだけを記述するフラット形式も読み込めます。
フラット形式は内部的に `{"view": {...}}` として扱われます。

```json
{
  "rotation_step_deg": 5.0
}
```

### 4.3 欠損・破損時の挙動

| モード | 欠損・破損時の挙動 |
|---|---|
| Production（non-strict） | 警告を記録し、下位層の値へフォールバックして起動を継続する |
| Development / CI（strict） | `SettingsError` を送出して早期に問題を検出する |

Production で破損した JSON を検出した場合は、診断用に
`*.broken-YYYYmmdd-HHMMSS` へ rename します。

strict mode は次のいずれかで有効になります。

- 環境変数 `QV_STRICT_SETTINGS=1`
- `QSettings` の `general/run_mode` が `development` または `verbose`

strict mode では欠損ファイルもエラーになるため、strict mode を使う環境では
必要な JSON ファイルを配置してください。

---

## 5. データモデルと現在の設定

設定値は `qv/app/app_settings_manager.py` の dataclass で保持します。

```py
@dataclass
class AppSettingsData:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    view: ViewConfig = field(default_factory=ViewConfig)
    mpr: MPRConfig = field(default_factory=MPRConfig)
```

### 5.1 コード内デフォルト

`base_defaults` は JSON が利用できない場合にも使える最終フォールバックです。

```py
base_defaults: Dict[str, Any] = {
    "general": {
        "run_mode": RunMode.DEVELOPMENT.value,
        "logging_level": "INFO",
    },
    "view": {
        "rotation_step_deg": 5.0,
    },
    "mpr": {
        "slice_drag_direction_mode": (
            SliceNavigationDirectionMode.PATIENT_ORIENTATION.value
        ),
        "wheel_slice_direction_mode": (
            SliceNavigationDirectionMode.PATIENT_ORIENTATION.value
        ),
    },
}
```

### 5.2 QSettings キー

| QSettings キー | 型・許可値 | 既定値 |
|---|---|---|
| `general/run_mode` | `development`, `production`, `verbose` | `development` |
| `general/logging_level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `view/rotation_step_deg` | float: `0 < x <= 90` | `5.0` |
| `mpr/slice_drag_direction_mode` | `patient_orientation`, `slice_index` | `patient_orientation` |
| `mpr/wheel_slice_direction_mode` | `patient_orientation`, `slice_index` | `patient_orientation` |

### 5.3 レガシー互換キー

`general/dev_mode` は後方互換のため読み込みのみ対応します。
`general/run_mode` が存在しない場合に限り、次のように変換します。

| `general/dev_mode` | `general/run_mode` |
|---|---|
| truthy: `1`, `true`, `yes`, `on` | `development` |
| それ以外 | `production` |

新規コードでは `general/run_mode` を使用してください。

### 5.4 validator

読み込んだ値は dataclass に格納する前に検証します。
不正値の場合は `base_defaults` の安全な値へフォールバックします。

| 関数 | 対象 | 検証内容 |
|---|---|---|
| `_validate_run_mode(v)` | `general/run_mode` | `development`, `production`, `verbose` のいずれか |
| `_validate_logging_level(v)` | `general/logging_level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` のいずれか |
| `_validate_rotation_step(v)` | `view/rotation_step_deg` | float に変換可能、かつ `0 < x <= 90` |
| `_validate_slice_navigation_direction_mode(v, fallback_key=...)` | MPR の方向設定 | `patient_orientation`, `slice_index` のいずれか |

validator は、JSON 読み込み後のモデル生成と QSettings 上書きの両方で使用します。

---

## 6. 公開 API

### 6.1 読み取り property

| property | 型 | 用途 |
|---|---|---|
| `data` | `AppSettingsData` | 有効設定モデル |
| `run_mode` | `RunMode` | 実行モード |
| `dev_mode` | `bool` | レガシー互換ビュー |
| `logging_level` | `str` | ログレベル |
| `rotation_step_deg` | `float` | 3D Viewer の回転量 |
| `mpr_slice_drag_direction_mode` | `SliceNavigationDirectionMode` | MPR のドラッグ方向 |
| `mpr_wheel_slice_direction_mode` | `SliceNavigationDirectionMode` | MPR のホイール方向 |
| `warnings` | `tuple[str, ...]` | non-strict 読み込み時の警告 |
| `had_fallback` | `bool` | フォールバック発生有無 |

### 6.2 書き込み setter

| setter | 用途 |
|---|---|
| `set_run_mode(v)` | 実行モードを保存する |
| `set_dev_mode(v)` | レガシー互換 shim |
| `set_logging_level(v)` | ログレベルを保存する |
| `set_rotation_step_deg(v)` | 回転量を保存する |
| `set_mpr_slice_drag_direction_mode(v)` | MPR のドラッグ方向を保存する |
| `set_mpr_wheel_slice_direction_mode(v)` | MPR のホイール方向を保存する |

### 6.3 診断 API

問い合わせ対応やデバッグでは、検証済みの有効設定を出力できます。

```py
logger.info("Effective settings:\n%s", settings.dump_effective_settings())

if settings.had_fallback:
    logger.warning("Settings fallback: %s", settings.warnings)
```

`to_dict()` と `dump_effective_settings()` は診断用途です。
設定の変更には使用しません。

### 6.4 リセット API

```py
settings.reset_section("mpr")
settings.reset_all_to_default()
```

| API | 挙動 |
|---|---|
| `reset_section(section)` | 指定セクションの QSettings を削除して再ロードする |
| `reset_all_to_default()` | `general`, `view`, `mpr` の QSettings を削除して再ロードする |

ショートカット設定は別管理のため、`reset_all_to_default()` の対象外です。

---

## 7. SettingsDialog の設計

`SettingsDialog` は設定編集 UI の共通基盤です。
設定カテゴリごとに `QTabWidget` のタブを追加します。

現在は `MPR` タブに次の項目があります。

| UI 項目 | QSettings キー |
|---|---|
| `Slice drag direction` | `mpr/slice_drag_direction_mode` |
| `Wheel slice direction` | `mpr/wheel_slice_direction_mode` |

ボタンの挙動は次のとおりです。

| ボタン | 挙動 |
|---|---|
| `Apply` | 保存するが dialog は閉じない |
| `OK` | 保存して dialog を閉じる |
| `Cancel` | 未保存の編集内容を破棄して dialog を閉じる |

widget の変更時点では setter を呼びません。
`Apply` または `OK` のタイミングで setter を呼ぶことで、`Cancel` を実現します。

表示テキストと永続化する値は分離します。

```py
_DIRECTION_MODE_OPTIONS = (
    ("Match patient orientation", SliceNavigationDirectionMode.PATIENT_ORIENTATION),
    ("Follow slice number order", SliceNavigationDirectionMode.SLICE_INDEX),
)
```

将来翻訳を導入する場合も、変更するのは表示テキストだけです。
保存値の `patient_orientation` と `slice_index` は互換性維持のため変更しません。

---

## 8. MPR スライス移動方向

MPR のスライス移動方向は、左ドラッグとホイールで個別に設定できます。
どちらもアプリケーション全体の設定とし、すべての MPR viewer に適用します。
viewer ごと、plane ごとの個別設定は現時点では持ちません。

```py
class SliceNavigationDirectionMode(str, Enum):
    PATIENT_ORIENTATION = "patient_orientation"
    SLICE_INDEX = "slice_index"
```

### 8.1 `patient_orientation`

Patient Orientation を基準に移動方向を決定します。

| Plane | 上ドラッグ / wheel forward | 下ドラッグ / wheel backward |
|---|---|---|
| Axial | Superior | Inferior |
| Coronal | Anterior | Posterior |
| Sagittal | Left | Right |

### 8.2 `slice_index`

Patient Orientation を考慮せず、slice index の増減方向をそのまま使用します。

| 操作 | 挙動 |
|---|---|
| 上ドラッグ | slice index を増やす |
| 下ドラッグ | slice index を減らす |
| wheel forward | slice index を増やす |
| wheel backward | slice index を減らす |

### 8.3 実行中の設定反映

MPR の slice direction 設定は、操作イベント発生時に `MprViewer` が共有 manager から
値を読み取ります。

```py
mode = self.setting.mpr_slice_drag_direction_mode
```

そのため、設定変更後に viewer の再生成や signal 通知は不要です。
次の drag または wheel 操作から新しい値が使われます。

---

## 9. 新しい設定項目の追加手順

この節では、例として MPR の方向ラベル表示設定を追加します。

| 項目 | 値 |
|---|---|
| 設定名 | `show_orientation_labels` |
| セクション | `mpr` |
| 型 | `bool` |
| QSettings キー | `mpr/show_orientation_labels` |
| 既定値 | `true` |

設定値は必ず `AppSettingsManager` を経由して扱います。
Viewer や Dialog から `QSettings` を直接参照しないでください。

### 9.1 コード内デフォルト値を追加する

対象:

- `qv/app/app_settings_manager.py`
- `base_defaults`

JSON ファイルが欠損・破損している場合にも使用できる値を追加します。

```py
base_defaults: Dict[str, Any] = {
    # Existing sections are omitted here.
    "mpr": {
        "slice_drag_direction_mode": (
            SliceNavigationDirectionMode.PATIENT_ORIENTATION.value
        ),
        "wheel_slice_direction_mode": (
            SliceNavigationDirectionMode.PATIENT_ORIENTATION.value
        ),
        "show_orientation_labels": True,
    },
}
```

### 9.2 dataclass にフィールドを追加する

対象:

- `qv/app/app_settings_manager.py`
- `MPRConfig`

読み込み後の有効設定を保持するフィールドを追加します。

```py
@dataclass
class MPRConfig:
    slice_drag_direction_mode: SliceNavigationDirectionMode = (
        SliceNavigationDirectionMode.PATIENT_ORIENTATION
    )
    wheel_slice_direction_mode: SliceNavigationDirectionMode = (
        SliceNavigationDirectionMode.PATIENT_ORIENTATION
    )
    show_orientation_labels: bool = True
```

既存セクションに項目を追加する場合、通常は `AppSettingsData` の変更は不要です。

新しいセクションを追加する場合は dataclass を作成し、`AppSettingsData` にも
フィールドを追加します。

```py
@dataclass
class NewSectionConfig:
    enabled: bool = True

@dataclass
class AppSettingsData:
    # Existing sections are omitted here.
    new_section: NewSectionConfig = field(default_factory=NewSectionConfig)
```

### 9.3 validator を追加する

対象:

- `qv/app/app_settings_manager.py`
- Utility セクション

文字列 `"false"` に対して `bool("false")` を使うと `True` になります。
bool 値は明示的に変換してください。

```py
def _validate_bool(v: Any, *, fallback: bool) -> bool:
    """Normalize common bool representations or use the safe fallback."""
    if isinstance(v, bool):
        return v

    normalized = str(v).strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    return fallback
```

数値、enum、文字列なども、それぞれの型と範囲に応じた validator を用意します。
不正値の場合は例外を送出せず、`base_defaults` の安全な値へフォールバックします。

### 9.4 QSettings の上書き処理を追加する

対象:

- `qv/app/app_settings_manager.py`
- `AppSettingsManager._apply_qsettings_overrides()`

JSON のデフォルト値よりも優先されるユーザー設定を読み込みます。

```py
# mpr
mpr = dict(base.get("mpr", {}))

value = self._settings.value("mpr/show_orientation_labels", None)
if value is not None:
    mpr["show_orientation_labels"] = _validate_bool(
        value,
        fallback=bool(base_defaults["mpr"]["show_orientation_labels"]),
    )
```

既存の `return` に対象セクションが含まれていることも確認します。

```py
return {
    "general": g,
    "view": vw,
    "mpr": mpr,
}
```

### 9.5 dataclass の生成処理を更新する

対象:

- `qv/app/app_settings_manager.py`
- `AppSettingsManager._make_model_from()`

merge 済みの辞書から、検証済みのモデルを生成します。

```py
mpr=MPRConfig(
    # Existing fields are omitted here.
    show_orientation_labels=_validate_bool(
        mpr.get(
            "show_orientation_labels",
            base_defaults["mpr"]["show_orientation_labels"],
        ),
        fallback=bool(base_defaults["mpr"]["show_orientation_labels"]),
    ),
),
```

### 9.6 公開 property と setter を追加する

対象:

- `qv/app/app_settings_manager.py`
- `AppSettingsManager`

呼び出し側が使用する API を追加します。

```py
@property
def mpr_show_orientation_labels(self) -> bool:
    return self._data.mpr.show_orientation_labels

def set_mpr_show_orientation_labels(self, value: bool) -> None:
    enabled = _validate_bool(
        value,
        fallback=bool(base_defaults["mpr"]["show_orientation_labels"]),
    )
    self._settings.setValue("mpr/show_orientation_labels", enabled)
    self._data.mpr.show_orientation_labels = enabled
```

setter は必ず `QSettings` と in-memory の `AppSettingsData` を両方更新します。

### 9.7 JSON デフォルトファイルを更新する

対象:

- `settings/viewer.json`

配布時のデフォルト値を追加します。

```json
{
  "view": {
    "rotation_step_deg": 5.0
  },
  "mpr": {
    "slice_drag_direction_mode": "patient_orientation",
    "wheel_slice_direction_mode": "patient_orientation",
    "show_orientation_labels": true
  }
}
```

Viewer 関連設定は `settings/viewer.json` に配置します。
アプリケーション全体の設定は `settings/app.json` に配置します。

### 9.8 シリアライズと reset 対象を確認する

対象:

- `qv/app/app_settings_manager.py`
- `AppSettingsManager.to_dict()`
- `AppSettingsManager.reset_all_to_default()`
- `AppSettingsManager.reset_section()`
- `AppSettingsManager._load_defaults_files()`

bool、数値、文字列は `asdict()` で変換されるため、通常は `to_dict()` の追加処理は
不要です。enum を追加した場合は JSON 化できる文字列へ変換します。

```py
data["mpr"]["new_mode"] = self._data.mpr.new_mode.value
```

既存の `mpr` セクションに追加するだけなら reset 処理の変更は不要です。

新しいセクションを追加する場合は、次の3箇所にも追加します。

```py
def reset_all_to_default(self) -> None:
    # Existing sections are omitted here.
    self._settings.remove("new_section")

def reset_section(self, section: str) -> None:
    if section not in ("general", "view", "mpr", "new_section"):
        raise ValueError(f"Invalid section: {section}")

def _load_defaults_files(self) -> dict[str, Any]:
    known_sections = {"general", "view", "mpr", "new_section"}
```

新しいセクションでは、既存セクションと同様にデータ経路全体も更新します。

1. `base_defaults` にセクションを追加する
2. `AppSettingsData` に dataclass フィールドを追加する
3. `_apply_qsettings_overrides()` で QSettings を読み込み、返却 `dict` に追加する
4. `_make_model_from()` で dataclass を生成する
5. `to_dict()` の返却値に追加する
6. 読み取り property と setter を追加する

### 9.9 SettingsDialog に UI を追加する

対象:

- `qv/ui/dialogs/settings_dialog.py`
- `SettingsDialog._build_mpr_tab()`
- `SettingsDialog._load_effective_settings()`
- `SettingsDialog.apply_settings()`

bool 設定には `QCheckBox` を使います。

```py
def _build_mpr_tab(self) -> None:
    tab = QtWidgets.QWidget(self.tab_widget)
    form_layout = QtWidgets.QFormLayout(tab)

    # Existing controls are omitted here.
    self.mpr_show_orientation_labels_checkbox = QtWidgets.QCheckBox(tab)
    form_layout.addRow(
        "Show orientation labels:",
        self.mpr_show_orientation_labels_checkbox,
    )

    self.tab_widget.addTab(tab, "MPR")
```

初期表示時に有効設定を反映します。

```py
def _load_effective_settings(self) -> None:
    # Existing controls are omitted here.
    self.mpr_show_orientation_labels_checkbox.setChecked(
        self._settings_manager.mpr_show_orientation_labels
    )
```

`Apply` または `OK` のタイミングで保存します。

```py
def apply_settings(self) -> None:
    # Existing controls are omitted here.
    self._settings_manager.set_mpr_show_orientation_labels(
        self.mpr_show_orientation_labels_checkbox.isChecked()
    )
```

widget の変更イベントでは setter を呼びません。
これにより `Cancel` で未保存の変更を破棄できます。

### 9.10 Viewer で設定を使用する

対象例:

- `qv/viewers/mpr_viewer.py`

呼び出し側は manager の property を参照します。

```py
def _refresh_orientation_marker_visibility(self) -> None:
    visible = self.setting.mpr_show_orientation_labels
    for actor in self._orientation_marker_actor.values():
        actor.SetVisibility(visible)
```

反映タイミングは設定項目ごとに決めます。

| 設定の種類 | 推奨反映タイミング |
|---|---|
| 次回操作から有効になる設定 | 操作イベント内で property を読む |
| 表示・描画設定 | `Apply` 後に再描画または更新処理を呼ぶ |
| 起動時のみ有効な設定 | 次回起動後に反映する旨を UI に示す |

MPR slice direction は操作イベントごとに参照されるため、viewer の再生成は不要です。

### 9.11 manager のテストを追加する

対象:

- `tests/app/test_app_settings_manager.py`

最低限、デフォルト値、QSettings 上書き、setter 永続化、不正値フォールバックを
確認します。

```py
def test_mpr_orientation_labels_default_to_enabled(tmp_path: Path) -> None:
    manager = _manager(tmp_path / "settings", "OrientationLabelsDefault")

    assert manager.mpr_show_orientation_labels is True


def test_mpr_orientation_labels_setter_persists_to_qsettings(
        tmp_path: Path,
) -> None:
    app_name = "OrientationLabelsSetter"
    manager = _manager(tmp_path / "settings", app_name)

    manager.set_mpr_show_orientation_labels(False)

    assert manager.mpr_show_orientation_labels is False

    settings = QSettings(ORG, app_name)
    assert settings.value("mpr/show_orientation_labels", type=bool) is False
```

### 9.12 dialog のテストを追加する

対象:

- `tests/ui/test_settings_dialog.py`

Fake manager に property と setter を追加します。

```py
class FakeSettingsManager:
    def __init__(self) -> None:
        self.mpr_show_orientation_labels = True
        self.orientation_label_set_calls: list[bool] = []

    def set_mpr_show_orientation_labels(self, value: bool) -> None:
        self.orientation_label_set_calls.append(value)
        self.mpr_show_orientation_labels = value
```

`Apply` と `Cancel` の挙動を確認します。

```py
def test_apply_persists_orientation_label_visibility(qtbot) -> None:
    settings = FakeSettingsManager()
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)

    dialog.mpr_show_orientation_labels_checkbox.setChecked(False)
    dialog.apply_settings()

    assert settings.orientation_label_set_calls == [False]
```

### 9.13 ドキュメントを更新する

対象:

- `docs/devel/app_settings.md`

設定項目を追加した場合は、少なくとも次の箇所を更新します。

1. データモデルと `base_defaults`
2. QSettings キー一覧
3. validator の仕様
4. 公開 property と setter 一覧
5. GUI 項目一覧
6. 反映タイミング
7. テスト観点

---

## 10. テスト方針

### 10.1 AppSettingsManager

設定項目ごとに、次の経路を確認します。

- `base_defaults` が使われる
- JSON のデフォルト値が読み込まれる
- `QSettings` が JSON を上書きする
- 不正値は安全な値へフォールバックする
- setter が property と `QSettings` の両方を更新する
- section reset が他セクションを変更しない
- `to_dict()` が JSON 化可能な値を返す

`QSettings` はユーザー環境に保存されるため、テストでは保存先を `tmp_path` に
切り替えて隔離します。

```py
@pytest.fixture(autouse=True)
def isolate_qsettings(tmp_path: Path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    yield
```

### 10.2 SettingsDialog

- 有効設定が初期表示に反映される
- `Apply` で保存され、dialog は閉じない
- `OK` で保存され、dialog を閉じる
- `Cancel` で保存しない

### 10.3 Viewer 連携

- `MainWindow`、`MultiViewerPanel`、各 viewer が同じ manager を共有する
- 実行中の設定変更が想定したタイミングで反映される
- MPR slice direction の変更後も同じ viewer インスタンスを利用できる
- Shift + wheel の zoom など、既存操作が変更されない

### 10.4 実行コマンド

manager と dialog の変更では、最初に対象テストを実行します。

```bash
uv run pytest \
  tests/app/test_app_settings_manager.py \
  tests/ui/test_settings_dialog.py
```

Viewer の動作に影響する場合は、関連する UI テストも含めます。

```bash
uv run pytest tests/viewers tests/ui
```

---

## 11. 保守上の注意

- 保存済みの QSettings キーと enum の文字列値は、既存ユーザーとの互換性に影響する
- GUI の表示文言は変更・翻訳できるが、保存値は安易に変更しない
- UI 表示用ラベルと内部値を分離する
- 新しい設定は、反映タイミングを設計してから追加する
- 即時再描画が必要な設定では、`Apply` 後に更新処理または signal 通知を追加する
- Viewer や Dialog から `QSettings` を直接参照しない
- ショートカット設定は別管理のため、本書の reset 対象に含めない
