# Logging System（QV）開発者向けドキュメント

このドキュメントは、QV の **ロギング基盤（起動ログ / 実行ログ / PyInstaller対応 / Qtメッセージ / クラッシュログ）** の設計思想・責務分担・データフロー・実装上の注意点を、後から参画する開発者が理解できるようにまとめたものです。

---

## 目的 / 要件

### 目的
- **起動直後（Qt/VTK import 前後）** に落ちる問題でも、原因調査に必要な情報を残す
- 開発時は詳細ログ（DEBUG）で原因を追いやすくし、本番時は過剰なログを抑える
- PyInstaller（onedir/onefile）環境でも **ログ出力先が壊れない**
- Qtプラグイン・Qt内部メッセージをログに残し、GUI起動失敗の切り分けを容易にする
- VTK/OpenGL などで **例外を介さずプロセスが落ちる**ケースでも、可能な範囲でクラッシュ情報を残す

### 非目的（スコープ外）
- すべてのクラッシュを必ず捕捉すること（OS/ドライバ起因の強制終了は限界がある）
- ネットワーク送信（集中ログ基盤）・監視サービス連携（将来拡張の余地はあり）

---

## 用語

- **Startup logging**: `QApplication` 作成前に行う最小限のロギング初期化。PyInstaller切り分けに重要。
- **Runtime logging**: アプリ実行中（UI操作、DICOM読込、VTK描画等）のログ。Queue方式でI/O負荷を平準化。
- **Crash log**: `faulthandler` によるクラッシュ時のバックトレース出力（可能な範囲）。
- **Qt message**: Qt内部（プラグイン探索、レンダラー、警告等）から出るログ。通常のPython例外とは別系統。

---

## モジュール責務

### `qv/app/logging_setup.py`
ロギングの中核。**起動ログ**と**実行ログ**を同一モジュールで提供する。

- `setup_startup_logging(app_name)`  
  - 起動直後に必ず呼ぶ（`QApplication` 作成前）
  - ローテーション付きファイルログを確立
  - `sys.excepthook` をセット（未捕捉例外の記録）
  - `faulthandler` を有効化（クラッシュログの保険）
  - 起動診断情報（frozen/cwd/sys.path等）を出力
  - ログ出力先は **書き込み可能な場所を自動選択**（フォールバックあり）

- `LogSystem(app_name)`  
  - アプリ実行中のログ基盤（QueueHandler + QueueListener）
  - `logging.config.dictConfig` により、root logger を QueueHandler 経由にする
  - ファイル書き込みは Listener 側の `RotatingFileHandler` が担当
  - `apply_levels()` で起動後にログレベルを変更可能

- `apply_logging_policy(logs, settings)`  
  - 実行モード（DEV/PROD/VERBOSE）に応じた出力レベル切替ポリシー

- `install_qt_message_handler()`  
  - Qt内部メッセージを Python logging に流す
  - Qtプラグインエラー等の切り分けで有効

> 注: `setup_startup_logging()` と `LogSystem()` はどちらも root logger を触るため、**起動順と整合**が重要（後述）。

---

## 起動シーケンス（重要）

### `qv/main.py` の推奨順序
1. setup_startup_logging(app_name=“qv”) 
2. install_qt_message_handler() 
3. PySide6 / VTK import 
4. main() 内で LogSystem(“qv”) を起動（実行ログへ移行） 
5. AppSettingsManager 読み込み → apply_logging_policy() 
6. QApplication 作成 → MainWindow 構築 → app.exec()


#### なぜ `main()` の外で行うのか
- Qtプラグイン問題は **QApplication 作成時に発生**することが多い
- `main()` 内で初期化すると、プラグイン失敗時に **コードが実行されずログが残らない**

---

## ログ出力先（パス戦略）

### パス決定ルール
`_find_writable_log_dir(app_name)` により、次の順で書き込み可能性を検証して決定する。

1. `app_base_dir/logs`
2. `~/.{app_name}/logs`
3. `cwd/logs`（最後の手段）

#### `app_base_dir` の決定
- frozen（PyInstaller）: `Path(sys.executable).parent`
- 開発時: プロジェクトルート推定（`Path(__file__).parents[2]`）

> 目的: **権限・配置先の違い（dist配下 / アプリバンドル / カレント違い）に耐える**こと。

---

## ログファイル設計

### 起動ログ
- `logs/{app_name}.log`
  - `RotatingFileHandler`
  - サイズ上限 `max_bytes` と `backup_count` で肥大化を抑制
- `logs/{app_name}.crash.log`
  - `faulthandler` 用
  - OS/ドライバ起因で完全に残らないケースはあり得るが、残るときの情報価値が高い

### 実行ログ（Queue方式）
- root logger → `QueueHandler` へ投入
- `QueueListener` が `RotatingFileHandler` へ書き込み
- メリット:
  - UIスレッドのI/O待ちが減り、体感の引っ掛かりが減る
  - 大量ログ時でもフリーズしにくい

---

## 例外・クラッシュの扱い

### 未捕捉例外（Python例外）
- `sys.excepthook` を `setup_startup_logging()` が設定
- 目的:
  - 起動直後の失敗（Qt import前後）でも確実に残す
- 注意:
  - Qtのシグナル/スロット内例外は `sys.excepthook` に必ず流れるとは限らない  
    → 必要なら個別に try/except + logger.exception を設ける（運用で増やす）

### クラッシュ（VTK/OpenGL 等）
- `faulthandler.enable(file=...)` を使用
- 目的:
  - `Segmentation fault` 等で落ちる場合に、Pythonレベルで残せる情報を最大化
- 限界:
  - すべての強制終了でログが残る保証はない
  - ただし残った場合の価値が非常に高いので有効化を推奨

---

## Qtメッセージログ

### `install_qt_message_handler()`
- Qt内部ログ（プラグイン探索、警告、レンダラー、フォント等）を `logging.getLogger("Qt")` に流す
- Qtプラグイン問題の切り分けで特に重要

#### 運用上の注意
- Qtログはノイズが多いことがある
- 本番ではレベル調整（INFO/WARN中心）やフィルタ導入を検討

---

## ログレベルポリシー（RunMode）

### `apply_logging_policy(logs, settings)`
- `RunMode.DEVELOPMENT` / `RunMode.VERBOSE`:
  - root/console/file を基本 DEBUG に寄せる
- `RunMode.PRODUCTION`:
  - console は INFO
  - file は DEBUG（調査用に残す）

> 目的: 本番利用で画面をログで埋めつつ、調査に必要な情報はファイルへ残す。

---

## 実装上の落とし穴・注意点

### 1) `setup_startup_logging()` と `LogSystem()` の二重初期化
- 両者とも root logger のハンドラ構成に影響する
- 推奨:
  - **起動ログ（RotatingFileHandler + console） → 実行ログ（Queue方式）へ移行**する意図を明確にする
  - 起動後に Queue方式へ切り替える際、ハンドラの再構成が起きることを理解する

### 2) `sys.excepthook` の上書き
- excepthook は1つだけ
- 推奨:
  - **excepthook は logging_setup 側に集約**し、main.py で再設定しない
  - 必要なら `logging_setup` 内で「チェーン」する（将来拡張）

### 3) ログ出力先の権限問題
- PyInstaller 配布先（例: Program Files、アプリバンドル内）では書けないことがある
- `_find_writable_log_dir()` のフォールバックが重要
- 調査時はログの出力先を必ず確認する（起動時にログへ出る）

### 4) ログ肥大化
- 3D描画・DICOM処理はログが増えやすい
- `RotatingFileHandler` のパラメータは運用に合わせて調整する
  - 例: maxBytes=5MB, backupCount=10 など

---

## デバッグの指針（何を見るか）

### 起動しない（GUIが出ない）
- `logs/{app_name}.log` の先頭（起動診断）
- Qt plugin エラーが出ていないか（Qt logger）
- frozen=True の場合:
  - `sys.executable` と `app_base_dir` が想定通りか
  - `PySide6/plugins/platforms` が同梱されているか

### 起動後に落ちる / 突然死する
- `logs/{app_name}.crash.log` が生成されているか
- VTK/OpenGL 関連のログが直前に出ていないか

---

## 今後の拡張ポイント

- 起動時に `QT_DEBUG_PLUGINS=1` を **診断モード時のみ**有効化する仕組み（CLIフラグ等）
- OS別の推奨ログディレクトリ（Windows: `%LOCALAPPDATA%`、macOS: `~/Library/Logs`）を統一ポリシー化
- UIから「ログを開く」「ログ場所をコピー」する機能（ErrorNotifier 連携）
- 構造化ログ（JSON）対応（将来の解析・集約に有利）

---

## まとめ（設計の要点）
- **起動フェーズ**と**実行フェーズ**のログを分け、起動直後の失敗でも情報を残す
- PyInstaller環境で **ログ出力先が壊れない**ようにフォールバックを持つ
- Queue方式で実行ログのI/O負荷を平準化し、UIの引っ掛かりを減らす
- Qtメッセージ・クラッシュログを取り込み、3D/GUI特有の「無言死」に備える