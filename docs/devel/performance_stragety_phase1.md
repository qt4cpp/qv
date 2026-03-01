# Phase 1 設計提案（QV Performance）

## 目的
Phase 1 では、既存機能を大きく壊さずに「性能改善の土台」を作ることを目的とする。  
対象は以下の4点。

1. `PerformanceProfile` の導入
2. インタラクション中の動的品質切替
3. ヒストグラム更新の軽量化（サンプリング）
4. KPIログの追加（計測可能性の確保）

---

## 解決したい課題（Phase 1範囲）

- DICOM読み込み後の初期描画までの待ち時間が長い
- カメラ操作中に描画が重く、操作性が悪い
- データ量が大きいとヒストグラム生成がUI応答を悪化させる
- 改善効果を定量的に評価しづらい

---

## 設計方針

## 1. PerformanceProfile を中核にする
描画品質設定を分散させず、1つの設定オブジェクトで管理する。

- プロファイル: `speed` / `balanced` / `quality`
- 主な制御項目:
  - `shade_enabled`
  - `image_sample_distance`
  - `auto_adjust_sample_distances`
  - `interactive_image_sample_distance`
  - `interactive_shade_enabled`

> 初期値は `balanced` を採用する。

---

## 2. VolumeViewer に適用APIを追加する
`VolumeViewer` 側に `set_profile(profile)` を追加し、Mapper/Propertyに反映する。

- `vtkVolumeProperty`: `ShadeOn/Off`
- `vtkGPUVolumeRayCastMapper` or `vtkSmartVolumeMapper`:
  - `SetImageSampleDistance(...)`
  - `AutoAdjustSampleDistancesOn/Off`

---

## 3. インタラクション中の動的品質切替
カメラ操作中は品質を下げ、操作終了後に通常品質へ戻す。

- `StartInteractionEvent`:
  - `apply_interactive_quality(True)`
- `EndInteractionEvent`:
  - `apply_interactive_quality(False)`

> 体感操作性を優先しつつ、停止後に画質を回復する。

---

## 4. ヒストグラム更新の軽量化
全ボクセル処理を避け、データサイズに応じてサンプリング率を決定する。

- 入力点数 `n_points`
- 目標サンプル上限（例: 2,000,000）
- `sampling = ceil(n_points / target_samples)`（最低1）

`MainWindow` 側で sampling を決めてから `HistogramWidget` に渡す。

---

## 5. KPIロギング
改善効果を比較できるよう、以下のKPIを必ず出力する。

- `load_ms`
- `first_frame_ms`
- `fps_interaction`
- `mask_apply_ms`

ログ形式は key=value の機械可読形式を推奨する。

---

## コンポーネント案

- `qv/viewers/performance_profile.py`（新規）
  - `PerformanceProfile` dataclass
  - `get_profile(name)` / presets
- `qv/viewers/volume_viewer.py`
  - `set_profile(...)`
  - `apply_interactive_quality(...)`
  - `load_ms`, `first_frame_ms`, `mask_apply_ms` 計測
- `qv/viewers/interactor_styles/volume_interactor_style.py`
  - interaction開始/終了フック
  - `fps_interaction` 計測
- `qv/ui/mainwindow.py`
  - ヒストグラムsampling算出と適用
- `qv/app/perf_metrics.py`（新規）
  - `PerfTimer`
  - `log_metric(...)`

---

## イベントフロー（Phase 1）

1. DICOMロード開始時刻を記録
2. 読込完了で `load_ms` を記録
3. `set_profile(balanced)` を適用
4. 初回描画後 `first_frame_ms` を記録
5. 操作開始で interactive 設定適用
6. 操作終了で通常設定復帰 + `fps_interaction` 記録
7. クリッピング確定時に `mask_apply_ms` 記録

---

## 実装順（推奨）

1. `PerformanceProfile` 実装
2. `VolumeViewer.set_profile()` 実装
3. 動的品質切替実装
4. KPIロギング基盤実装
5. `load_ms` / `first_frame_ms` / `fps_interaction` / `mask_apply_ms` 計測追加
6. ヒストグラムsampling方針の共通化

---

## 受け入れ基準（Phase 1）

- デフォルト `balanced` で既存の見た目を大きく損なわない
- 操作中の体感応答が改善する
- ヒストグラム更新でUI停止が発生しない
- `qv.log` に4つのKPIが出力される

---

## 非対象（Phase 2以降）
- DICOM読み込みの全面非同期化
- クリッピング二段階処理（preview/commit完全分離）
- データサイズ別の高度な自動最適化