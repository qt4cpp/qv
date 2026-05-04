# MPR slice direction settings 実装プラン

対象仕様:
- `docs/devel/app_settings.md`
- `docs/devel/mpr_viewer.md`

目的:
- MPR の slice drag / wheel slice direction option を `AppSettingsManager` と MPR 操作に反映する。
- 今後ほかのアプリ設定も GUI で編集できるよう、設定ダイアログの土台を作る。

---

## 1. `feat(settings): add MPR slice direction settings`

- 目的: MPR スライス移動方向設定を `AppSettingsManager` の正式な設定モデルに入れる
- 対象:
  - `qv/app/app_settings_manager.py`
  - `settings/viewer.json`
  - 必要なら `settings/app.json` 新規
  - `tests/app/test_app_settings_manager.py` 新規、または既存 settings 系テスト
- このコミットでやること:
  - `SliceNavigationDirectionMode` enum を追加する
    - `patient_orientation`
    - `slice_index`
  - `base_defaults["mpr"]` を追加する
    - `slice_drag_direction_mode`
    - `wheel_slice_direction_mode`
  - `MprConfig` と `AppSettingsData.mpr` を追加する
  - `_validate_slice_navigation_direction_mode()` を追加する
  - 公開 property を追加する
    - `mpr_slice_drag_direction_mode`
    - `mpr_wheel_slice_direction_mode`
  - setter を追加する
    - `set_mpr_slice_drag_direction_mode()`
    - `set_mpr_wheel_slice_direction_mode()`
  - `QSettings` override を `mpr/slice_drag_direction_mode` と `mpr/wheel_slice_direction_mode` に対応させる
  - `to_dict()`, `dump_effective_settings()`, `reset_all_to_default()`, `reset_section()` を `mpr` 対応にする
  - `viewer.json` の nested 判定を `view` だけでなく `general` / `view` / `mpr` セクション形式に対応させる
- テスト:
  - default は両方 `patient_orientation`
  - JSON default で `mpr` が読める
  - `QSettings` が JSON default を上書きする
  - 不正値は default に fallback する
  - setter 後に property と QSettings が更新される
  - `reset_section("mpr")` で MPR 設定だけ戻る
- 確認:
  - `pytest tests/app/test_app_settings_manager.py`
  - 既存 settings 利用箇所の import が壊れない
- 理由:
  - 操作/UI から dict や raw string を直接扱わない土台を先に固める

---

## 2. `feat(mpr): route slice navigation through direction settings`

- 目的: 左ドラッグとホイールのスライス移動方向を設定値で切り替える
- 対象:
  - `qv/viewers/mpr_viewer.py`
  - `qv/viewers/interactor_styles/mpr_interactor_style.py`
  - `tests/viewers/test_mpr_viewer.py`
  - `tests/viewers/test_mpr_interactor_style.py`
- このコミットでやること:
  - `MprViewer` に設定対応のスライス移動 API を追加する
    - `scroll_slice_by_drag_steps(visual_steps: int)`
    - `scroll_slice_by_wheel_steps(wheel_steps: int)`
  - 左ドラッグ:
    - `patient_orientation`: 既存の患者方向ロジックを使う
    - `slice_index`: 上ドラッグで `slice_index +`, 下ドラッグで `slice_index -`
  - ホイール:
    - `patient_orientation`: forward を Axial=Superior / Coronal=Anterior / Sagittal=Left に合わせる
    - `slice_index`: forward で `slice_index +`, backward で `slice_index -`
  - 既存 `_slice_index_direction_for_upward_patient_drag()` を、ドラッグ/ホイール共通に使いやすい名前へ整理する
  - `MprInteractorStyle` の呼び出し先を差し替える
    - 左ドラッグ: `scroll_slice_by_drag_steps()`
    - 通常 wheel: `scroll_slice_by_wheel_steps()`
    - Shift+wheel は現状通り zoom のままにする
- テスト:
  - interactor は左ドラッグで `scroll_slice_by_drag_steps()` を呼ぶ
  - interactor は通常 wheel で `scroll_slice_by_wheel_steps(+1/-1)` を呼ぶ
  - Shift+wheel は zoom のみで slice navigation を呼ばない
  - `slice_index` mode では入力方向がそのまま `scroll_slice()` に渡る
  - `patient_orientation` mode では既存の患者方向ロジックが使われる
- 確認:
  - `pytest tests/viewers/test_mpr_viewer.py tests/viewers/test_mpr_interactor_style.py`
- 理由:
  - UI 追加前に、実際の操作が `AppSettingsManager` の有効値を参照する状態にする

---

## 3. `feat(ui): add application settings dialog scaffold`

- 目的: 今後の設定項目追加に耐える GUI の土台を作る
- 対象:
  - `qv/ui/dialogs/settings_dialog.py` 新規
  - `qv/ui/mainwindow.py`
  - `tests/ui/test_settings_dialog.py` 新規
- このコミットでやること:
  - `SettingsDialog(QDialog)` を追加する
  - `QTabWidget` を使い、セクションごとにタブを増やせる構成にする
  - 初期実装では `MPR` タブを作る
  - MPR タブに `QFormLayout` と `QComboBox` を配置する
    - スライスドラッグ方向
    - ホイールスライス方向
  - combo の表示名と内部値を仕様に合わせる
    - `患者方向に合わせる` -> `patient_orientation`
    - `スライス番号順に移動する` -> `slice_index`
  - `OK` / `Apply` / `Cancel` を持つ `QDialogButtonBox` を置く
  - `Apply` / `OK` で `AppSettingsManager` の setter を呼ぶ
  - `Cancel` では保存しない
- テスト:
  - 初期表示が `AppSettingsManager` の値と一致する
  - combo 変更後に `Apply` で setter が呼ばれる、または manager の値が更新される
  - `Cancel` では manager の値が変わらない
- 確認:
  - `pytest tests/ui/test_settings_dialog.py`
- 理由:
  - 今回は MPR の2項目だけを載せるが、将来 `general` / `view` / shortcuts 以外の設定も同じ枠に足せるようにする

---

## 4. `feat(ui): expose settings dialog from MainWindow menu`

- 目的: ユーザーがアプリ内から設定 GUI を開けるようにする
- 対象:
  - `qv/ui/mainwindow.py`
  - 必要なら `tests/ui/test_mainwindow.py` 新規または既存 UI テスト
- このコミットでやること:
  - メニューに `Preferences...` または `Settings...` action を追加する
  - `_open_settings_dialog()` を追加し、共有 `self.setting` を `SettingsDialog` に渡す
  - 設定変更後、既存 MPR viewer が次の入力イベントから新設定を読むことを確認する
  - 今回は viewer への即時通知 signal は作らない
    - MPR の方向設定はイベント処理時に `AppSettingsManager` を読むため、既存 viewer 再生成は不要
- テスト:
  - MainWindow に settings action が作成される
  - action trigger で dialog が生成される
  - 可能なら monkeypatch した dialog で `exec()` 呼び出しを確認する
- 確認:
  - `pytest tests/ui`
  - 手動でメニューから dialog を開き、設定を変更して MPR drag / wheel の向きが変わる
- 理由:
  - GUI は `MainWindow` から開くのが既存メニュー構造に合っている

---

## 5. `test(mpr): add integration coverage for settings-driven navigation`

- 目的: 設定 manager、MPR viewer、interactor の連携回帰を押さえる
- 対象:
  - `tests/viewers/test_mpr_viewer.py`
  - `tests/viewers/test_mpr_interactor_style.py`
  - 必要なら `tests/ui/test_multi_viewer_panel.py`
- このコミットでやること:
  - `AppSettingsManager` を差し替えた MPR viewer で、設定変更が次の操作に反映されることを確認する
  - 3つの MPR viewer が同じ manager を共有することを確認する
  - `MultiViewerPanel` で全 MPR viewer に同じ `settings_mgr` が渡る既存構造を回帰テストとして明示する
- テスト:
  - drag 設定を `slice_index` に変更後、同じ viewer インスタンスで左ドラッグ方向が変わる
  - wheel 設定を `slice_index` に変更後、同じ viewer インスタンスで wheel 方向が変わる
  - Shift+wheel は設定変更後も zoom のまま
- 確認:
  - `pytest tests/viewers tests/ui`
- 理由:
  - GUI と操作が分かれた実装になるため、連携部分の回帰を最後にまとめて固定する

---

## 推奨実施順

1. `feat(settings): add MPR slice direction settings`
2. `feat(mpr): route slice navigation through direction settings`
3. `feat(ui): add application settings dialog scaffold`
4. `feat(ui): expose settings dialog from MainWindow menu`
5. `test(mpr): add integration coverage for settings-driven navigation`

この順なら、設定データモデル、操作反映、GUI、統合回帰の責務がコミットごとに分かれる。

---

## 実装時の注意

- `MprInteractorStyle` は設定値を直接知らず、viewer のメソッドを呼ぶだけにする。
- `MprViewer` は `self.setting` から property を読む。`QSettings` を直接読まない。
- `SliceNavigationDirectionMode` の比較は raw string ではなく enum property を使う。
- `SettingsDialog` は今回 MPR タブだけでよいが、タブ追加しやすい private builder method に分ける。
- `Cancel` で保存されないよう、combo の変更時点では setter を呼ばない。
- `reset_section()` は `mpr` を許可する。将来の GUI reset ボタン追加に備える。
