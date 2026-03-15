# MprViewer / MprInteractorStyle テストガイド

## 目的

このドキュメントは、`MprViewer` と `MprInteractorStyle` の開発・保守に必要なテスト運用をまとめた開発者向けガイドである。

新しく参加した開発者が次のことを迷わず行える状態を目指す。

- どのテストが何を保証しているかを把握する
- ローカルで必要なテストだけを素早く実行する
- 変更内容に応じて自動テストと手動確認を使い分ける
- 既存方針に沿って新しいテストを追加する

---

## 対象ファイル

実装:

- `qv/viewers/mpr_viewer.py`
- `qv/viewers/interactor_styles/mpr_interactor_style.py`
- `qv/ui/widgets/multi_viewer_panel.py`
- `qv/viewers/base_viewer.py`

自動テスト:

- `tests/viewers/conftest.py`
- `tests/viewers/test_mpr_viewer.py`
- `tests/viewers/test_mpr_interactor_style.py`
- `tests/ui/test_multi_viewer_panel.py`

関連ドキュメント:

- `docs/devel/mpr_viewer.md`
- `docs/devel/modify_mpr_viewer_interaction.md`
- `docs/tasks/arrange_mpr_viewer_interactor.md`

---

## テスト戦略の全体像

MPR 系のテストは、責務ごとに 3 層へ分けている。

### 1. `MprViewer` 単体テスト

目的:

- 画像ロード後の状態初期化を固定する
- スライス移動と面切り替えの仕様を固定する
- WW/WL の clamp と HUD 反映を固定する

特徴:

- 実際の DICOM は使わず、`sample_image_data` を使う
- Qt Widget は実体を作る
- headless 環境でも落ちないよう interactor 初期化は抑制する

### 2. `MprInteractorStyle` 単体テスト

目的:

- 右ドラッグ開始 / 継続 / 終了のイベント解釈を固定する
- ホイールから slice scroll への変換を固定する
- 未ロード状態で何もしないことを固定する

特徴:

- 実 `MprViewer` は使わない
- `ViewerSpy` と `FakeInteractor` で入力契約だけをテストする
- VTK のネイティブイベント配送まではテストしない

### 3. `MultiViewerPanel` 連携テスト

目的:

- VR 側ロード完了時に MPR へ `vtkImageData` が渡ることを固定する
- VR と MPR の WW/WL が独立であることを固定する

特徴:

- 連携の配線だけを見る
- 重い VTK 実体ではなく軽量 stub viewer を使う

---

## 自動テストでカバーする範囲

### `tests/viewers/test_mpr_viewer.py`

このファイルは `MprViewer` の状態遷移と表示設定の契約を担保する。

主なカバー内容:

- fixture から `MprViewer` を生成できる
- `sample_image_data` の shape / scalar range が期待どおり
- `set_image_data()` 後に `window_settings` が初期化される
- 初期 slice range と中央 slice が正しく計算される
- `set_window_settings()` が scalar range に clamp される
- `scroll_slice()` が範囲外へ出ない
- `set_slice_index()` が clamp 後の値で `sliceChanged` を emit する
- `set_plane()` が slice range を再計算し中央へ戻す
- 初回ロード後に WW/WL HUD が表示される

このテストが守っている仕様:

- MPR 初期 WW/WL の算出ルール
- slice index の clamp ルール
- 面切り替え時の「中央へ戻す」ルール
- `BaseViewer` の HUD と MPR 初期化の接続

### `tests/viewers/test_mpr_interactor_style.py`

このファイルは `MprInteractorStyle` の入力解釈だけを担保する。

主なカバー内容:

- 右ボタン押下で WW/WL drag が始まる
- drag 中の `MouseMoveEvent` だけ viewer へ `adjust_window_settings(dx, dy)` を渡す
- drag していないときは adjust しない
- ホイール前後で `scroll_slice(+1/-1)` を呼ぶ
- 未ロード状態では drag / wheel を無視する
- 右ボタン解放で drag 状態が終わる

このテストが守っている仕様:

- interactor style は raw な `dx` / `dy` を viewer へ渡す
- WW/WL の数学的変換は viewer 側の責務
- 入力ガードは style 側で行う

### `tests/ui/test_multi_viewer_panel.py`

このファイルは MPR と VR の連携方針を担保する。

主なカバー内容:

- `VolumeViewer.dataLoaded` 後に `source_image` が MPR 側へ渡る
- VR と MPR の WW/WL が相互に伝播しない

このテストが守っている仕様:

- 画像データの初期供給は行う
- WW/WL は独立動作とする

---

## 自動テストでカバーしない範囲

次は pytest だけでは十分に担保できないため、変更内容によっては手動確認が必要である。

- 実際の描画結果が視覚的に正しいか
- 実 DICOM で面方向が人間の期待どおりか
- 実マウス操作時の VTK 既定動作との競合有無
- ホイールや右ドラッグの体感速度
- リサイズ時の HUD 見え方
- GPU / ドライバ / OS 依存の VTK 挙動

`MprInteractorStyle` の単体テストは「イベントをどう解釈するか」を見ており、「実 UI 上で期待どおりに感じるか」は見ていない点に注意すること。

---

## テスト実行前の準備

### 必須環境

- Python 3.13 以上
- `PySide6`
- `VTK`
- `pytest`
- `pytest-qt`

### 依存インストール

`uv` を使う場合:

```bash
uv sync --group dev
```

`pip` を使う場合の一例:

```bash
pip install -r requirements.txt
pip install pytest-qt
```

### headless 実行

CI や SSH 環境では Qt の描画先がないため、`tests/conftest.py` で次を設定している。

```python
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
```

手元で単独実行するときに Qt plugin error が出る場合は、明示的に次を付けて実行する。

```bash
QT_QPA_PLATFORM=offscreen pytest ...
```

---

## よく使う実行コマンド

### `MprViewer` だけ回す

```bash
uv run pytest tests/viewers/test_mpr_viewer.py
```

### interactor style だけ回す

```bash
uv run pytest tests/viewers/test_mpr_interactor_style.py
```

### UI 連携回帰だけ回す

```bash
uv run pytest tests/ui/test_multi_viewer_panel.py
```

### MPR 関連をまとめて回す

```bash
uv run pytest \
  tests/viewers/test_mpr_viewer.py \
  tests/viewers/test_mpr_interactor_style.py \
  tests/ui/test_multi_viewer_panel.py
```

### `uv` を使わない場合

```bash
python -m pytest tests/viewers/test_mpr_viewer.py
python -m pytest tests/viewers/test_mpr_interactor_style.py
python -m pytest tests/ui/test_multi_viewer_panel.py
```

---

## fixture とテスト補助の使い方

### `tests/viewers/conftest.py`

ここで次の fixture を提供している。

#### `sample_image_data`

用途:

- 小さくて決定的な `vtkImageData` を作る
- scalar range を安定して比較する
- 実 DICOM に依存せず viewer ロジックだけをテストする

データ特性:

- dimensions: `(4, 5, 3)`
- scalar range: `(0.0, 59.0)`
- spacing / origin も固定済み

この fixture を使う理由:

- slice count と range を手計算しやすい
- 初期 WW/WL の期待値を固定しやすい

#### `mpr_viewer`

用途:

- headless 安全な `MprViewer` 実体を作る

ポイント:

- `BaseViewer._initialize_interactor` を monkeypatch している
- これにより、テスト中に VTK interactor の起動で不安定になりにくい
- `qtbot.addWidget(viewer)` まで含むため、signal 待ちにも使える

#### `isolated_qsettings`

用途:

- テスト中にローカル環境の `QSettings` を汚さない

ポイント:

- 設定系を触る viewer テストでは、実ユーザー設定と混ざる事故を防ぐ

---

## `MprViewer` テストの書き方

### 基本パターン

1. `mpr_viewer` と `sample_image_data` を使う
2. 状態変化を起こす
3. signal, internal state, HUD のいずれかを assert する

例:

```python
def test_set_slice_index_emits_slice_changed_with_clamped_value(
        mpr_viewer,
        qtbot,
        sample_image_data,
):
    mpr_viewer.set_image_data(sample_image_data)

    with qtbot.waitSignal(mpr_viewer.sliceChanged, timeout=1000) as blocker:
        mpr_viewer.set_slice_index(99)

    plane, index = blocker.args
    assert plane == MprPlane.AXIAL
    assert index == 2
```

### 何を assert するべきか

優先順位:

1. 公開 API の結果
2. signal の発火
3. viewer が保持する内部 state
4. HUD actor の表示文字列

避けたいこと:

- 描画結果のピクセル比較
- 実際の GUI マウス操作に依存した brittle なテスト
- VTK 実 renderer の詳細挙動への過剰な依存

### HUD をテストするときの考え方

HUD は `BaseViewer` 側の責務なので、MPR 側では次を見れば十分である。

- actor が存在する
- `GetVisibility() == 1`
- `GetInput()` が期待文字列

例:

```python
actor = mpr_viewer._window_overlay_actor
assert actor is not None
assert actor.GetVisibility() == 1
assert actor.GetInput() == "WL 30 WW 59"
```

---

## `MprInteractorStyle` テストの書き方

### 基本方針

このファイルでは、実 `MprViewer` や実マウスイベントを使わない。

代わりに次を使う。

- `ViewerSpy`: viewer との契約だけを模擬する
- `FakeInteractor`: `GetEventPosition()` だけを模擬する

この構成にしている理由:

- 失敗原因を VTK / Qt / viewer 本体から切り離せる
- interactor style の責務だけに集中できる
- raw `dx` / `dy` の扱いを安定して比較できる

### `ViewerSpy` に必要な最小契約

style 側から見て必要なのは次だけである。

- `image_data`
- `window_settings`
- `adjust_window_settings(dx, dy)`
- `scroll_slice(delta)`

実装変更で interactor style が viewer に新しい要求を持つようになった場合は、最初に `ViewerSpy` を更新すること。

### `FakeInteractor` の役割

`GetEventPosition()` の返り値を固定列で返し、drag 中の移動量を決定的にする。

例:

- 初回位置 `(100, 200)`
- 次回位置 `(112, 185)`
- 期待 `dx=12`, `dy=-15`

### `OnMouseMove` の monkeypatch

drag 外では `vtkInteractorStyleImage.OnMouseMove()` が呼ばれるため、テストではそこを no-op に差し替えている。

```python
monkeypatch.setattr(MprInteractorStyle, "OnMouseMove", lambda self: None)
```

これを忘れると、環境依存の副作用でテストが不安定になる。

---

## `MultiViewerPanel` 連携テストの書き方

### 目的

このテストは「実 viewer を動かす」ためではなく、「配線方針を固定する」ためにある。

確認したいのは次の 2 点だけである。

- `VolumeViewer.dataLoaded` から MPR へ画像が流れる
- WW/WL は viewer 間で共有しない

### stub viewer を使う理由

- 本物の `VolumeViewer` は VTK 負荷が高い
- このテストで見たいのはレンダリングではなく接続だけ
- 将来の仕様変更で配線が壊れたときに失敗理由が読みやすい

### テスト設計の原則

- signal と setter だけ持つ最小 stub を定義する
- widget として `MultiViewerPanel` に載せられるよう `QWidget` を継承する
- signal を emit して panel の slot が働くかを見る

---

## 変更時のチェックリスト

`MprViewer` や interactor に変更を入れたら、最低限ここまでは見る。

### `MprViewer` のみを触ったとき

- `tests/viewers/test_mpr_viewer.py`

### interactor style を触ったとき

- `tests/viewers/test_mpr_interactor_style.py`
- 右ドラッグとホイールの手動確認

### `MultiViewerPanel` や WW/WL 連携方針を触ったとき

- `tests/ui/test_multi_viewer_panel.py`
- `tests/viewers/test_mpr_viewer.py`
- 必要なら手動で VR / MPR 独立動作を確認

### 面方向や slice 計算を触ったとき

- `tests/viewers/test_mpr_viewer.py`
- 実 DICOM で Axial / Coronal / Sagittal を手動確認

---

## 手動テスト手順

自動テストが通っても、入力体感と実描画は別である。以下は MPR 関連変更時の手動確認手順である。

### 起動

```bash
python -m qv /path/to/dicom/series
```

または:

```bash
python -m qv
```

### 手順 1. 画像ロード直後

確認内容:

- VR が表示される
- MPR に画像が出る
- MPR 右下 HUD に WW/WL が表示される

期待結果:

- MPR が空白のままにならない
- HUD が非表示のまま残らない

### 手順 2. マウスホイール

確認内容:

- wheel forward で 1 slice 進む
- wheel backward で 1 slice 戻る
- 端でそれ以上進まない

期待結果:

- 1 step 単位で安定して動く
- 端で例外やジャンプが起きない

### 手順 3. 右ドラッグで WW/WL

確認内容:

- 右ボタン押下で drag を開始できる
- 横移動で width が変わる
- 縦移動で level が変わる
- HUD 表示がリアルタイム更新される

期待結果:

- `VolumeViewer` と同じ向きの感覚で動く
- ボタンを離した後は変化が止まる

### 手順 4. 断面切り替え

確認内容:

- Axial / Coronal / Sagittal が切り替わる
- 切り替え時に slice が中央へ戻る

期待結果:

- 面変更後に真っ黒や空表示にならない
- wheel 操作が継続して効く

### 手順 5. VR / MPR の独立動作

確認内容:

- VR 側で WW/WL を変えても MPR が変わらない
- MPR 側で WW/WL を変えても VR が変わらない

期待結果:

- 片側の操作が他方の HUD や表示へ波及しない

---

## 典型的なハマりどころ

### 1. Qt plugin error で pytest が起動しない

症状:

- `Could not load the Qt platform plugin ...`

対処:

- `QT_QPA_PLATFORM=offscreen` を付ける
- `tests/conftest.py` が読み込まれているか確認する

### 2. VTK interactor 初期化で不安定になる

症状:

- headless 環境で widget 生成時に落ちる

対処:

- `tests/viewers/conftest.py` と同様に `BaseViewer._initialize_interactor` を monkeypatch する

### 3. WW/WL 期待値がずれる

症状:

- 初期 `window_settings` や HUD 文字列の assert が落ちる

対処:

- `MprViewer._build_initial_window_settings()` の仕様変更有無を確認する
- `VolumeViewer` と揃える方針か独自方針かを先に決める
- 数値変更が仕様なら test とドキュメントを同時更新する

### 4. interactor style テストだけ急に壊れる

症状:

- `ViewerSpy` に存在しない属性参照で失敗する

対処:

- `MprInteractorStyle` が viewer に要求するプロトコルを確認する
- 必要なら `ViewerSpy` を最小限だけ拡張する

### 5. 連携テストが壊れたが viewer 単体テストは通る

症状:

- `MultiViewerPanel` のみ失敗する

対処:

- signal 接続の追加や削除を疑う
- `windowSettingsChanged` を viewer 間でつないでいないか確認する
- `dataLoaded` から `source_image` を MPR へ渡す経路を確認する

---

## 新しいテストを追加するときの判断基準

### `MprViewer` テストへ追加するケース

- 画像ロード後の内部 state が変わる
- slice 計算ルールが変わる
- 面切り替えの仕様が変わる
- WW/WL の clamp や HUD 反映が変わる

### `MprInteractorStyle` テストへ追加するケース

- ボタンやホイールの割り当てが変わる
- drag 開始条件が変わる
- input guard 条件が変わる
- viewer へ渡す引数契約が変わる

### `MultiViewerPanel` テストへ追加するケース

- viewer 間の signal 接続方針を変える
- 初期同期を追加する
- MPR パネル数を増やす

### 手動テストだけで済ませてはいけないケース

- clamp 条件の変更
- signal emit 条件の変更
- `dx` / `dy` の解釈変更
- 面切り替え時の初期 slice 位置変更

これらは再発しやすいため、必ず自動テストを追加すること。

---

## 保守ルール

- 仕様変更時は、実装より先に「どのテストが仕様を持つか」を決める
- `MprInteractorStyle` の数学は style に入れず、viewer 側へ寄せる
- 画像データを使う viewer テストは、まず `sample_image_data` で再現できるかを考える
- 実 DICOM が必要な確認は手動テストへ回す
- 新しい開発者が見ても意図が読めるよう、テスト名は挙動を文章で表現する

---

## 最低限のレビュー観点

MPR 関連の PR を見るときは、少なくとも次を確認する。

- 変更した責務に対応する pytest が更新されているか
- viewer と style の責務境界が崩れていないか
- 手動確認が必要な変更なのに、確認項目が共有されているか
- VR と MPR の独立動作が壊れていないか

このドキュメントにない新しい責務を導入した場合は、同じ PR で本ドキュメントも更新すること。
