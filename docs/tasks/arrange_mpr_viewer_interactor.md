## 1. `test(mpr): add viewer test scaffold`
- 目的: MPR 系テストを書ける土台を先に作る
- 対象:
  - `tests/conftest.py`
  - `tests/viewers/test_mpr_viewer.py` 新規
  - `tests/viewers/test_mpr_interactor_style.py` 新規
- このコミットでやること:
  - `QApplication` fixture
  - `MprViewer` 生成用 fixture
  - 必要なら VTK event を直接叩かずに stub viewer を使う方針を固定
- 確認:
  - 空テストでもよいので pytest が安定して流れる
- 理由:
  - 以後のテスト追加で毎回 fixture まわりを触らずに済む

## 2. `test(mpr): cover slice navigation and window setting math`
- 目的: `MprViewer` 本体の挙動を先に固定する
- 対象:
  - `tests/viewers/test_mpr_viewer.py`
- 先に書くべきテスト:
  - `set_image_data()` 後に初期 `window_settings` が入る
  - `scroll_slice(+1/-1)` で範囲内に clamp される
  - `set_slice_index()` が `sliceChanged` を出す
  - `adjust_window_settings(dx, dy)` の `dx -> width`, `dy -> level` の期待値
  - `window_settings` 未設定時は何もしない
- 確認:
  - viewer 単体の失敗テストが揃う
- 理由:
  - interactor より先に viewer の期待仕様を固定できる

## 3. `test(mpr): cover dedicated interactor style behavior`
- 目的: `MprInteractorStyle` の仕様をテストで先に決める
- 対象:
  - `tests/viewers/test_mpr_interactor_style.py`
- 先に書くべきテスト:
  - 右ボタン押下で drag 開始
  - 右ドラッグ中の `MouseMoveEvent` だけ `adjust_window_settings()` を呼ぶ
  - ホイール前後で `scroll_slice(+1/-1)` を呼ぶ
  - 未ロード時は何もしない
  - 右ボタン解放で drag 終了
- 確認:
  - style 単体の red test が揃う
- 理由:
  - UI 配線前に入力仕様を固定できる

## 4. `feat(mpr): introduce MprInteractorStyle and remove observer state`
- 目的: `MprViewer` のイベント責務を style に移す
- 対象:
  - `qv/viewers/interactor_styles/mpr_interactor_style.py` 新規
  - `qv/viewers/mpr_viewer.py`
- このコミットでやること:
  - `setup_interactor_style()` を style ベースに変更
  - `_ww_wl_dragging`, `_ww_wl_last_pos` を削除
  - observer 群 `_on_right_button_press` などを削除
- 確認:
  - commit 2, 3 のテストが通る
  - 手動で wheel と右ドラッグだけ確認すればよい
- 理由:
  - 差分が `MprViewer` と新規 style に閉じる

## 5. `refactor(mpr): align window settings behavior with BaseViewer and VolumeViewer`
- 目的: WW/WL の責務と操作感を揃える
- 対象:
  - `qv/viewers/mpr_viewer.py`
  - 必要なら `tests/viewers/test_mpr_viewer.py`
- このコミットでやること:
  - `set_window_settings()` の入口を `BaseViewer` 前提で整理
  - `adjust_window_settings()` の `dy` 符号を `VolumeViewer` と揃える
  - `delta_per_pixel` 命名を統一
  - 初期 WW/WL 算出を helper 化
- 確認:
  - 右ドラッグの上下方向が VR と同じ感覚になる
  - HUD と表示更新がズレない
- 理由:
  - ここは仕様調整が入りやすいので、入力配線の後に分けた方が見やすい

## 6. `test(mpr): add integration regression for initial load and independence`
- 目的: 最後に連携面の回帰を押さえる
- 対象:
  - `tests/viewers/test_mpr_viewer.py`
  - 必要なら `tests/ui/test_multi_viewer_panel.py` 新規
  - 必要なら `qv/ui/widgets/multi_viewer_panel.py`
- 追加テスト候補:
  - `set_image_data()` 後に HUD 表示開始
  - MPR の WW/WL 変更が VR に波及しない
  - VR の `windowSettingsChanged` を今後つなぐなら、その方針どおりの初期同期
- 確認:
  - 独立動作の要件を自動テストで担保できる
- 理由:
  - 依存関係が一番広いので最後がよい

## **おすすめの実施順**
- まずは `1 -> 2` で `MprViewer` の期待挙動を固める
- 次に `3 -> 4` で interactor を導入する
- 最後に `5 -> 6` で仕様調整と回帰を締める

## **補足**
現状の争点はこの 2 つです。ここは commit 5 までに明示しておくとブレません。
- 初期 WW/WL を `MprViewer` 独自値で持つか、`VolumeViewer` 初期値に合わせるか
- `dy` の符号を VR と揃えるか