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

少なくとも以下の座標系を区別して扱う。

- voxel index space
- patient/world space
- viewer display space

slice 同期や crosshair、camera preset の基準は、固定 IJK ではなく patient/world 系を正本とする。

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

- `ijk -> patient/world`
- `patient/world -> ijk`

実装形は 4x4 matrix、direction matrix、または同等の変換表現とする。

### MPR の基準

MPR の `WorldPosition` は、最終的には patient/world 系の基準点として扱う。

これにより以下を統一できる。

- 他断面への slice 投影
- crosshair 表示
- point sync
- 将来の oblique 拡張

### VR の基準

VR では volume 自体に patient orientation を反映したうえで、camera preset を患者基準で定義する。

つまり以下の意味はデータに依らず一定であるべきとする。

- `front_view`
- `back_view`
- `left_view`
- `right_view`
- `top_view`
- `bottom_view`

---

## MPR 仕様

### plane の意味

各 plane は患者基準で以下を意味する。

- Axial: 頭尾方向に法線を持つ断面
- Coronal: 前後方向に法線を持つ断面
- Sagittal: 左右方向に法線を持つ断面

### plane 表示規約

既存の `docs/devel/mpr_viewer.md` の表示規約を維持する。

- Axial: 足側から頭側を見る
- Coronal: 前方から後方を見る
- Sagittal: 左側から右側を見る

これにより、患者の左右・前後・上下の見え方は plane ごとに安定する。

### slice index

slice index は viewer の都合で持つ離散値であり、正本座標ではない。  
患者基準の位置から現在 plane の法線方向成分を求めた結果として導出されるものとする。

つまり次を守る。

- patient/world 位置から slice index を計算できる
- slice index から reslice origin を再構成できる
- 軸番号の決め打ちだけで slice 位置を決めない

### crosshair

crosshair は他 viewer の現在断面位置を表示する補助情報である。  
crosshair の基準点は patient/world 系で統一する。

### slice 操作

wheel や drag による slice 移動は、画面座標ではなくその plane の法線方向移動として定義する。  
画面上の上/下、前/後のどちらを slice 増減に対応させるかは、patient orientation を canonical 表示へ写した後に決定する。

---

## VR 仕様

### camera preset

VR の preset view は患者基準で定義する。

- front: 患者前方から後方を見る
- back: 患者後方から前方を見る
- left: 患者左側から右側を見る
- right: 患者右側から左側を見る
- top: 頭側から足側を見る
- bottom: 足側から頭側を見る

### camera orientation

camera position だけでなく、`view_up` も patient orientation を反映して決定する。  
これにより同じ `front_view` でもデータ orientation によって上下が反転する事態を防ぐ。

### orientation marker

VR でも MPR と同様に患者基準の orientation marker を表示可能にする前提で設計する。  
少なくとも以下が正しく導出できる必要がある。

- L / R
- A / P
- H / F

### MPR との整合

VR は slice を持たないが、患者基準の右左前後上下は MPR と一致していなければならない。  
MPR の plane 規約と VR の preset view 規約は同じ patient/world 基準から導出される。

---

## 実装上の指針

### MPR

- `PLANE_AXES` は canonical 表示規約を表す層として扱う
- `PLANE_AXES_INDEX` による固定軸前提は最終仕様では置き換える
- `world_to_slice_index()` は patient/world 基準で計算する
- `_update_reslice()` は patient/world から reslice origin を決める

### VR

- `VolumeViewer` の camera preset は patient matrix を反映できる形を維持する
- volume から取得できる direction / patient matrix を camera controller に渡す
- preset view と orientation marker は同じ patient basis を共有する

### 共通

- 一時的な符号合わせで plane ごとに個別補正しない
- MPR と VR で別々の患者基準を持たない
- 変換行列の所在を明確にし、viewer ごとに独自解釈しない

---

## 導入順

### Phase 1: patient/world 変換の保持

- DICOM 由来の orientation 情報を読み取る
- `ijk <-> patient/world` を保持する
- VR と MPR の両方から参照できる形にする

### Phase 2: VR camera への反映

- `VolumeViewer` の patient matrix を確実に設定する
- preset view の方向と `view_up` を患者基準で検証する
- 必要なら orientation marker の基礎情報をここで揃える

### Phase 3: MPR reslice への反映

- fixed axis 前提の slice 計算を patient/world 基準へ置き換える
- crosshair と point sync を patient/world 基準で統一する
- plane 表示規約を維持したまま orientation を吸収する

### Phase 4: 操作仕様の確定

- wheel / drag / double click の意味を patient/world 基準で再定義する
- MPR と VR の orientation marker を必要に応じて追加する

---

## 受け入れ条件

- 同一データで MPR と VR の左右前後上下の解釈が一致する
- VR の preset view が患者基準で安定する
- MPR の slice / crosshair / sync が patient/world 基準で整合する
- fixed plane の表示規約を維持したまま orientation を吸収できる
- orientation marker を導入する場合に、MPR と VR の両方で同じ基準から導出できる
