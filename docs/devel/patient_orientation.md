# Patient Orientation 仕様

## 目的

本書は、DICOM の `Patient Orientation` および関連する患者座標情報を qv 内でどのように扱うかを定義する。  
対象は MPR に限定せず、`MprViewer` と `VolumeViewer` の両方を含む。

本書の目的は以下である。

- MPR と VR で座標解釈を揃える
- fixed plane 表示と患者座標系の関係を明確にする
- 将来の orientation marker、camera preset、crosshair、slice 操作の基準を統一する
- 一時的な見た目調整ではなく、データ由来の orientation を正しく扱う

本書は既存の以下の文書を補完する。

- `docs/devel/mpr_viewer.md`
- `docs/devel/multipanel.md`
- `docs/devel/modify_mpr_viewer_interaction.md`

---

## 背景

現状の `MprViewer` は固定 plane 前提で `PLANE_AXES` と `PLANE_AXES_INDEX` を用いており、  
slice index、reslice origin、crosshair 投影の一部が軸固定の実装になっている。

一方 `VolumeViewer` では slice index は持たないが、患者基準の front/back/left/right/top/bottom view を正しく扱うには、  
volume の orientation を camera 側へ反映する必要がある。

したがって `Patient Orientation` は MPR だけの課題ではなく、VR を含む表示系全体の基礎仕様である。

加えて、現状の DICOM ローダ (`vtkDICOMImageReader`) は `Image Orientation (Patient)` を完全には反映しない。  
そのため `vtkImageData.GetDirectionMatrix()` が単位行列のまま下流に流れているケースがあり、  
camera 側だけで patient matrix を補正しても整合が取り切れない。本書ではローダ層も含めて再設計する。

---

## 対象範囲

### MPR に影響する項目

- Axial / Coronal / Sagittal の plane 解釈
- slice index と患者座標の対応
- `vtkImageReslice` の reslice axes と origin
- crosshair の world/patient 座標
- viewer 上の orientation marker
- マウスホイールや drag による slice 移動方向の意味

### VR に影響する項目

- front / back / left / right / top / bottom の camera preset
- `ViewUp` を含む camera orientation
- orientation marker
- MPR と VR の「右/左/前/後/頭/足」の一貫性
- 将来 3D 上に断面位置や marker を出す場合の座標整合

### 本書の非対象

- oblique MPR の最終仕様
- thick slab の最終仕様
- DICOM 以外の任意 orientation フォーマット対応
- VR と MPR の WW/WL 連動
- UI デザインの細部

---

## 基本方針

### 1. 表示規約を先に固定する

viewer が従う表示ポリシーは既存の fixed plane 規約を維持する。

- Axial / Coronal / Sagittal の canonical な見え方は維持する
- radiological convention を採るかどうかは plane 表示仕様側で管理する
- `Patient Orientation` 対応によって viewer の見え方ポリシーを都度変えない

### 2. データセットを表示規約へ正規化する

`Patient Orientation` 対応は、データごとに表示ポリシーを変えるためではない。  
各データセットの patient 座標系を、viewer が採用する canonical な表示規約へマッピングするために使う。

### 3. viewer 内部の正本は patient/world 系に寄せる

少なくとも以下の座標系を区別して扱う（詳細は §座標モデル）。

- voxel index space
- source space (VTK のローカル世界座標)
- patient space (DICOM 由来)
- viewer display space

slice 同期や crosshair、camera preset の基準は、固定 IJK ではなく patient 系を正本とする。

### 4. 患者座標規約は LPS を内部正本とする

DICOM 準拠で内部表現は **LPS (Left, Posterior, Superior)** を採用する。  
RAS との相互変換は I/O 境界（読み込み・marker 表示・外部連携）でのみ行う。  
これにより orientation marker (L/R, A/P, H/F) の符号が一意に決まる。

---

## 座標モデル

### 入力として使う DICOM 情報

- `Image Orientation (Patient)`
- `Image Position (Patient)`
- pixel spacing / slice spacing

必要に応じて以下も参照対象とする。

- `Patient Position`
- 画像 series 全体から導出される slice normal

### 保持すべき変換

少なくとも以下を論理的に保持する。

- `IJK -> PAT`
- `PAT -> IJK`
- `SRC -> PAT`（= `vtkImageData.GetDirectionMatrix()`）
- `PAT -> SRC`

実装形は 4x4 matrix、direction matrix、または同等の変換表現とする。

### PatientFrame 値オブジェクト

変換行列の所在を明確にするため、以下の値オブジェクトを単一の正本として導入する。

```python
@dataclass(frozen=True, slots=True)
class PatientFrame:
    ijk_to_patient: vtk.vtkMatrix4x4
    patient_to_ijk: vtk.vtkMatrix4x4
    src_to_patient: vtk.vtkMatrix4x4   # = vtkImageData.GetDirectionMatrix() を 4x4 化したもの
    convention: Literal["LPS", "RAS"] = "LPS"
```

- 配置場所: `qv/core/patient_geometry.py`（新規）を推奨
- VR / MPR / picker / crosshair / marker は **すべて** これを参照する
- viewer ごとの独自解釈・独自行列保持は禁止する

### plane normal と patient 軸の対応
各 plane の法線は `PatientFrame` から以下の規約で導出する（LPS 基準）。

| plane | 法線方向（PAT） | 視線方向（カメラ位置→注視点） | 意味 |
| --- | --- | --- | --- |
| Axial | +S (Superior) | -S（足側→頭側） | 頭尾方向に法線 |
| Coronal | +P (Posterior) | +P（前方→後方） | 前後方向に法線 |
| Sagittal | +L (Left) | +L（左→右） | 左右方向に法線 |
### view_up の規約
VR camera preset の も同じ `PatientFrame` から導出する。 `view_up`

| preset | camera 視線方向（PAT） | view_up（PAT） |
| --- | --- | --- |
| front | +P | -S |
| back | -P | -S |
| left | -L | -S |
| right | +L | -S |
| top | -S | -P |
| bottom | +S | +P |
これらは / の生成根拠となる。 `CameraPreset.DIRECTIONS``CameraPreset.VIEWUPS`
### MPR の基準
MPR の は、最終的には PAT 系の基準点として扱う。 `WorldPosition`
これにより以下を統一できる。
- 他断面への slice 投影
- crosshair 表示
- point sync
- 将来の oblique 拡張

の型定義は MPR 専用ではなくなるため、 または
`qv/core/patient_geometry.py` の中立モジュールへ移設する。 `WorldPosition``qv/viewers/coordinates.py`
### VR の基準
VR では volume 自体に patient orientation を反映したうえで、camera preset を患者基準で定義する。
つまり以下の意味はデータに依らず一定であるべきとする。
- `front_view`
- `back_view`
- `left_view`
- `right_view`
- `top_view`
- `bottom_view`

### direction matrix の責務分担
`vtkImageData.GetDirectionMatrix()` は VTK のレンダリングパイプラインに自動適用される。
camera 側で再度 patient matrix を掛けると二重補正となるため、以下を厳守する。
- volume 表示への反映: VTK 内蔵処理に任せる（`SetDirectionMatrix` を正しく設定する）
- camera preset の方向計算: `PatientFrame` から `PAT` 軸で算出し、SRC 系へ最終投影する
- どちらが何を担うかをコード上に明示し、二重補正を生まないこと

## MPR 仕様
### plane の意味
各 plane は患者基準で以下を意味する（再掲: §plane normal と患者軸の対応）。
- Axial: 頭尾方向に法線を持つ断面
- Coronal: 前後方向に法線を持つ断面
- Sagittal: 左右方向に法線を持つ断面

### plane 表示規約
既存の の表示規約を維持する。 `docs/devel/mpr_viewer.md`
- Axial: 足側から頭側を見る
- Coronal: 前方から後方を見る
- Sagittal: 左側から右側を見る

これにより、患者の左右・前後・上下の見え方は plane ごとに安定する。
### slice index
slice index は viewer の都合で持つ離散値であり、正本座標ではない。
PAT 位置から現在 plane の法線方向成分を求めた結果として導出されるものとする。
つまり次を守る。
- PAT 位置から slice index を計算できる
- slice index から reslice origin を再構成できる
- 軸番号の決め打ちだけで slice 位置を決めない

### crosshair
crosshair は他 viewer の現在断面位置を表示する補助情報である。
crosshair の基準点は PAT 系で統一する。
の対応も `PatientFrame` から導出可能な形へ置き換える。
固定の plane 名→軸番号マップは最終仕様では持たない。 `CROSSHAIR_REFERENCE_PLANE`
### slice 操作
wheel や drag による slice 移動は、画面座標ではなくその plane の法線方向移動として定義する。
画面上の上/下、前/後のどちらを slice 増減に対応させるかは、patient orientation を canonical 表示へ写した後に決定する。
## VR 仕様
### camera preset
VR の preset view は患者基準で定義する。
- front: 患者前方から後方を見る
- back: 患者後方から前方を見る
- left: 患者左側から右側を見る
- right: 患者右側から左側を見る
- top: 頭側から足側を見る
- bottom: 足側から頭側を見る

具体ベクトルは §view_up の規約 の表に従う。
### camera orientation
camera position だけでなく、 も patient orientation を反映して決定する。
これにより同じ でもデータ orientation によって上下が反転する事態を防ぐ。 `view_up``front_view`
### orientation marker
VR でも MPR と同様に患者基準の orientation marker を表示可能にする前提で設計する。
少なくとも以下が正しく導出できる必要がある。
- L / R
- A / P
- H / F

### MPR との整合
VR は slice を持たないが、患者基準の右左前後上下は MPR と一致していなければならない。
MPR の plane 規約と VR の preset view 規約は同じ `PatientFrame` から導出される。
## 実装上の指針
### MPR
- は canonical 表示規約を表す層として扱う `PLANE_AXES`
- による固定軸前提は最終仕様では置き換える `PLANE_AXES_INDEX`
- は PAT 基準で計算する `world_to_slice_index()`
- は PAT から reslice origin を決める `_update_reslice()`
- crosshair 系メソッド ( / / / / ) も `PatientFrame` 経由に書き換える `_slice_index_to_world``_build_crosshair_world_position``_build_crosshair_segments``_world_to_display_point``_display_to_world_point`

### VR
- の patient matrix は `PatientFrame.src_to_patient` を経由して設定する `VolumeViewer`
- `vtkImageData.SetDirectionMatrix()` を通じて VTK 内蔵経路で反映させる
- camera preset と orientation marker は同じ `PatientFrame` を共有する
- camera 側の追加補正と direction matrix 反映の二重適用を避ける

### 共通
- 一時的な符号合わせで plane ごとに個別補正しない
- MPR と VR で別々の患者基準を持たない
- 変換行列の所在は `PatientFrame` に集約し、viewer ごとに独自解釈しない
- を MPR 専用モジュールから中立モジュールへ移設する `WorldPosition`

## 導入順
順序見直し: MPR の reslice / slice index 計算は数値整合の検証が容易で、後段の crosshair / clipping との整合確認の基準にもなる。VR camera より先に MPR 側を固める。### Phase 1: ローダと PatientFrame の確立
- DICOM 由来の orientation 情報を読み取れるローダに刷新
    - 現状の は を取り切れない `vtkDICOMImageReader``Image Orientation (Patient)`
    - 候補: `vtk-dicom` (`vtkDICOMReader`)、または pydicom + 自前 構築 `vtkImageData`

- `PatientFrame` を返すローダ API を定義
- `vtkImageData.GetDirectionMatrix()` が DICOM の と一致すること `Image Orientation (Patient)`
- VR と MPR の両方から `PatientFrame` を参照できる経路を用意
- 完了条件:
    - 既知の HFS / FFS / HFP / FFP データでローダ単体テストが通る
    - `PatientFrame` が単位行列となるダミーデータでは現状表示と pixel 単位で一致（後方互換）

### Phase 2: MPR reslice への反映
- fixed axis 前提の slice 計算を PAT 基準へ置き換える
- / / `_slice_index_to_world()` を `PatientFrame` 経由に `_update_reslice()``world_to_slice_index()`
- crosshair と point sync を PAT 基準で統一する
- を patient basis から導出する形に変更 `CROSSHAIR_REFERENCE_PLANE`
- plane 表示規約を維持したまま orientation を吸収する

### Phase 3: VR camera への反映
- の patient matrix を `PatientFrame.src_to_patient` から確実に設定する `VolumeViewer`
- preset view の方向と を §view_up の規約 の表に従い実装 `view_up`
- direction matrix の責務分担（VTK 内蔵 vs camera 補正）を明文化し、二重補正を排除
- 必要なら orientation marker の基礎情報をここで揃える

### Phase 4: 操作仕様と marker の確定
- wheel / drag / double click の意味を PAT 基準で再定義する
- MPR と VR の orientation marker を必要に応じて追加する
- camera_state の azimuth/elevation のレポート単位（world / patient）を選定し統一する
- interactor styles の slice 増減方向を patient basis に整合させる
- 必要なら / `app.json` に表示ポリシー（marker on/off, radiological convention）を追加 `viewer.json`

## 受け入れ条件
### 機能要件
- 同一データで MPR と VR の左右前後上下の解釈が一致する
- VR の preset view が患者基準で安定する
- MPR の slice / crosshair / sync が PAT 基準で整合する
- fixed plane の表示規約を維持したまま orientation を吸収できる
- orientation marker を導入する場合に、MPR と VR の両方で同じ基準から導出できる

### テスト要件（自動化推奨）
- HFS / FFS / HFP / FFP の 4 パターンで MPR の `L/R/A/P/H/F` が反転しない
- 同一データで 後の VR と axial MPR の `L/R` が一致する `front_view`
- `PatientFrame` が単位行列の場合、Phase 1 導入前の表示と pixel 単位で一致する（後方互換）
- crosshair の交点座標が `IJK -> PAT -> IJK` のラウンドトリップで誤差 1 voxel 以内に収まる
- direction matrix を二重適用していないこと（patient matrix 適用前後の volume bounds が PAT 系で一致）


主な変更点まとめ:

1. §背景 にローダ起因の前提崩れを明記
2. §対象範囲 を MPR / VR / 共通基盤の 3 区分に再編し、crosshair の各メソッド名・ローダ・WorldPosition 移設まで列挙
3. §非対象 に clipping マスク・既存 Undo/Redo state・DICOM 実装エラーを明示
4. §基本方針 に LPS 採用を追加
5. §座標モデル を 4 系（IJK/SRC/PAT/DSP）の表で再定義し、`PatientFrame` 値オブジェクト・plane normal 表・view_up 規約表・direction matrix 責務分担 を新設
6. §MPR 仕様 / §VR 仕様 / §実装上の指針 を `PatientFrame` 経由前提で書き直し、対象メソッドを具体名で記載
7. §導入順 を Phase 1: ローダ + PatientFrame → Phase 2: MPR → Phase 3: VR → Phase 4: 操作 / marker に変更し、各 Phase の完了条件を追加
8. §受け入れ条件 に自動テスト要件 5 項目を追加
