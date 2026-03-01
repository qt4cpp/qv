# Transfer Function 実装ガイド（QV / VTK Volume Rendering）

## 目的
本書は、`qv/viewers/volume_viewer.py` の Transfer Function（以下 TF）を実装・調整するときに、
画質と性能を両立するための実践的な判断基準をまとめた開発者向けガイドです。

前提:
- `AutoAdjustSampleDistancesOff` で固定品質運用するケースを主対象とする
- 本プロジェクトでは `ImageSampleDistance < 1.0` は副作用（描画領域の欠け）が出る可能性があるため、通常は使わない
- `UseJitteringOn` はバンディング低減に有効だが、粒状感が増えることがある

---

## 1. 現状実装の要点

現状のTF更新ロジック:
- `update_transfer_functions()` で
  - Color TF: `min_val -> black`, `max_val -> white` の線形
  - Opacity TF: `min_val -> 0`, `max_val -> 1` の線形
- 参照: `qv/viewers/volume_viewer.py`

この構成はシンプルで保守しやすい一方、以下が起きやすい:
- バンディング（等高線状の見え）
- jittering有効時の粒状ノイズの知覚
- ウィンドウ幅が狭いと階調遷移が急になり、見えが不安定

---

## 2. まず守る方針（このプロジェクト向け）

1. `ImageSampleDistance` は原則 `>= 1.0`
2. バンディング対策は `UseJitteringOn` を第一候補にする
3. jitteringで粒状感が出たら、TFと`ScalarOpacityUnitDistance`で抑える
4. いきなり多パラメータを同時変更しない（1つずつ比較）

---

## 3. 実装優先順位（推奨）

### Step 1: Opacity TFを「急峻すぎない形」にする
現状の2点線形を、3〜5点の緩やかなカーブにする。

例（概念）:
- `min_val`: 0.00
- `min_val + 0.25*width`: 0.03
- `min_val + 0.50*width`: 0.12
- `min_val + 0.75*width`: 0.35
- `max_val`: 1.00

狙い:
- 低濃度帯をなだらかに立ち上げ、段差感と粒状感を抑える

### Step 2: `ScalarOpacityUnitDistance` を導入
`vtkVolumeProperty.SetScalarOpacityUnitDistance(value)` を使って、
レイ積分時の実効不透明度スケールを調整する。

調整の考え方:
- 値を大きくする: ノイズ感を抑えやすいが、全体が薄くなりやすい
- 値を小さくする: コントラストが立つが、ノイズ/段差が目立ちやすい

初期値の目安:
- まず `1.0` を基準
- 粒状感が強い場合 `1.2 -> 1.5 -> 2.0` を比較

### Step 3: Gradient Opacity（必要時のみ）
`SetGradientOpacity(...)` で低勾配領域の寄与を抑えると、
平坦ノイズを減らせることがある。

注意:
- 効きすぎると細部が消える
- まずは弱めのカーブから始める

---

## 4. jitteringの扱い

重要:
- `vtkGPUVolumeRayCastMapper` のjitteringは通常 `On/Off` 制御が中心で、
  強度を細かく指定できない構成が多い

実務上の解釈:
- 「jittering強度を下げる」の代わりに、
  TF（特にOpacity）と`ScalarOpacityUnitDistance`で見え方を整える

推奨組み合わせ:
- `UseJitteringOn`
- `ImageSampleDistance = 1.0`
- Opacityカーブを緩やかに
- `ScalarOpacityUnitDistance` をやや大きめ

---

## 5. 調整プロトコル（比較手順）

比較を再現可能にするため、以下を固定して評価する:

1. 同一データセット（2〜3種類）
2. 同一カメラ姿勢（正面/斜め）
3. 同一Window設定
4. 各設定で静止画を保存
5. FPSと主観評価をセットで記録

推奨データセット:
- 通常CT（標準枚数）
- 高解像度/巨大スライスのCT
- 低コントラスト病変が含まれるケース

評価項目:
- バンディングの目立ち
- 粒状感
- 組織境界の視認性
- インタラクション時FPS

---

## 6. 症状別の対処表

### 症状A: 等高線状の線が見える
- `UseJitteringOn`
- Opacityカーブの立ち上がりを緩和
- Window幅が狭すぎる場合は適正化

### 症状B: つぶつぶ（粒状感）が気になる
- `ImageSampleDistance` を `1.0` に維持（`<1.0` は使わない）
- `ScalarOpacityUnitDistance` を上げる
- Opacityの中間点を増やして急峻な遷移を減らす

### 症状C: 描画領域が欠ける/切り取られる
- `ImageSampleDistance < 1.0` を避ける
- まず `1.0` 固定で原因切り分け

### 症状D: 画質は良いが重い
- インタラクション中だけ軽量設定に切替
- `interactive_image_sample_distance` を上げる
- `interactive_shade_enabled` を必要に応じてOFF

---

## 7. 実装ポイント（コード反映時）

反映候補:
- `PerformanceProfile` にTF関連パラメータを追加
  - 例: `opacity_preset`, `scalar_opacity_unit_distance`
- `update_transfer_functions()` を preset対応にする
- `_apply_profile()` で `SetScalarOpacityUnitDistance(...)` を適用

設計原則:
- 既定値は現状互換を維持
- 新規パラメータはプロファイルで一元管理
- UI追加前にコード側で安定値を固める

---

## 8. 最低限の受け入れ基準

1. `ImageSampleDistance >= 1.0` で、顕著な描画欠けが再現しない
2. jittering ON時に、従来よりバンディングが減る
3. 粒状感が診断上許容できるレベルまで低減できる
4. `balanced` プロファイルで操作感が実用範囲（FPS）を維持

---

## 9. 将来拡張

- 目的別TFプリセット（bone / soft tissue / vessel など）
- ヒストグラム連動の自動初期TF
- ROIベースの局所TF調整
- 設定の永続化（`AppSettingsManager` 連携）

