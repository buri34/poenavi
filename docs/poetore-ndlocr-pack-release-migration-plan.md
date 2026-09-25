# ぽえとれ 高精度OCRパック専用Release移行計画

- 作成日: 2026-09-26
- 状態: **設計合意済み／実装未着手**
- 対象: PoE2「アビス冒涜Modティアチェック」の高精度OCRパック配布
- 現行候補版: PoENavi v4.4.1 Pre-release

## 1. 背景

v4.4.1候補では、既存Updaterの展開後512MiB上限を守るため、PoENavi本体と高精度OCRパックを
別ZIPに分離した。ただし現行実装は、PoENaviのアプリ版数をURLへ埋め込み、各本体Releaseへ
同じ約223MiBの高精度OCRパックを毎回添付する。

この方式には次の問題がある。

- 高精度OCRの内容が変わらなくても、本体更新のたびに同一ファイルを再アップロードする。
- Releaseページに本体ZIPとOCRパックZIPが並び、初めてPoENaviを使う人がOCRパックだけを
  本体と誤認してダウンロードする可能性がある。
- 添付忘れにより、新規利用者だけ高精度OCRを準備できない状態が発生し得る。
- アプリ版数とOCRパック版数のライフサイクルが不要に結合している。

## 2. 目的

1. 高精度OCRパックを、PoENavi本体とは独立した不変の専用Releaseから取得する。
2. PoENavi本体Releaseには本体ZIPとSHA-256だけを置き、利用者が選ぶファイルを明確にする。
3. 高精度OCRパックが変わらない限り、v4.4.2以降でも同じパックを再利用する。
4. 既存の自動更新、`/releases/latest`、導入済みパックの再利用を壊さない。
5. パック更新時も、古いPoENaviが参照する旧パックを削除・上書きしない。

## 3. 用語とバージョン境界

### PoENavi本体版

`v4.4.1`、`v4.4.2`のようなアプリの版数。PoENavi本体Releaseと自動更新判定に使用する。

### 高精度OCRパック版

NDLOCR-Lite本体、PoENavi用ヘルパー、4モデル、ライセンスを一組として識別する版数。
初回は既存パックとの対応を保つため`1.3.1-r1`とし、専用タグを`ndlocr-pack-v1.3.1-r1`とする。

`1.3.1`はNDLOCR-Liteの基礎版、`r1`はPoENavi向けパッケージ改訂を表す。モデル、ヘルパー、
ランタイム、構成、ライセンスのいずれかが変われば`r2`以降へ進める。既存タグのassetは上書きしない。

ローカル保存先は互換性維持のため当面`ndlocr-1.3.1`のままとする。導入マーカーには基礎版に加えて
専用Releaseタグを記録し、将来の`r2`を同じ基礎版と誤認しないようにする。v4.4.1候補が既に導入した
旧形式マーカーは、記録済みarchive SHA-256が`r1`の確定SHAと一致する場合だけ`r1`として移行する。

## 4. 確定する配布構成

### 4.1 PoENavi本体Release

通常の本体Releaseには次の2ファイルだけを添付する。

- `PoENavi.zip`
- `PoENavi.zip.sha256`

高精度OCRパックは添付しない。これにより、初めての利用者がReleaseページから選ぶ配布ZIPを
`PoENavi.zip`へ一本化する。

### 4.2 高精度OCRパック専用Release

同じ`buri34/poenavi`リポジトリに、次の独立Releaseを一度だけ作成する。

- タグ: `ndlocr-pack-v1.3.1-r1`
- Releaseタイトル: `［内部コンポーネント］PoENavi 高精度OCRパック 1.3.1-r1`
- 公開状態: **公開済みPre-release**（Draftにはしない）
- 添付:
  - `PoENavi-HighAccuracyOCR.zip`
  - `PoENavi-HighAccuracyOCR.zip.sha256`

Pre-releaseとすることで、assetは固定URLから公開取得できる一方、PoENavi本体の
`/releases/latest`には採用されない。

Release本文の先頭には、次の趣旨を明記する。

> これはPoENavi本体ではありません。通常はPoENaviが自動取得するため、手動ダウンロードは不要です。

## 5. PoENaviの取得仕様

PoENaviは`APP_VERSION`ではなく、高精度OCRパックのタグ定数からURLを組み立てる。

```text
https://github.com/buri34/poenavi/releases/download/ndlocr-pack-v1.3.1-r1/PoENavi-HighAccuracyOCR.zip
https://github.com/buri34/poenavi/releases/download/ndlocr-pack-v1.3.1-r1/PoENavi-HighAccuracyOCR.zip.sha256
```

管理画面を開いた時の既存動作は維持する。

1. ローカルの導入済みマーカー、ヘルパー、4モデルを確認する。
2. 対応するパックが正常なら通信せず、そのまま再利用する。
3. 未導入、破損、旧版の場合だけ専用ReleaseからSHAとZIPを取得する。
4. SHA-256と既存のZIP安全条件を検証し、ユーザーデータ領域へ原子的に導入する。
5. 失敗時もWindows OCRを継続利用できる。

v4.4.1、v4.4.2、v4.5.0が同じパック版を指定する限り、すべて同じURLを利用する。

## 6. ビルド・Release工程の分離

### 本体Release工程

- 本体ZIPへNDLOCR実行環境・モデルが混入していないことを監査する。
- 本体ZIPの展開後容量が512MiB未満であることを監査する。
- GitHub Release作成時は本体ZIPとSHAだけをアップロードする。
- 高精度OCRパックの生成・アップロードを毎回行わない。
- 既存Pre-releaseがあるタグでは、Releaseを作り直さず本体2assetだけを`--clobber`更新し、
  Pre-release状態を維持する。

### OCRパック更新工程

- OCRパックの内容を更新する時だけ、専用の明示実行工程で生成する。
- 自己完結EXE、4モデル、ライセンス、ZIP安全条件、実画像スモークを検証する。
- 実ZIP、添付SHA、GitHub asset digestを照合する。
- 新しい不変タグへ公開し、既存のOCRパックReleaseは残す。
- 新パック対応PoENaviのコードで参照タグと期待パック版を同時に更新する。

## 7. v4.4.1 Pre-releaseからの移行手順

現在のv4.4.1は固定URLが本体タグを参照しているため、次の順序で移行する。

1. 検証済みの現行OCRパック2ファイルを、`ndlocr-pack-v1.3.1-r1`の専用Pre-releaseへ公開する。
2. 公開URL、SHAファイル、GitHub asset digest、ZIP構成を照合する。
3. PoENaviの取得URLを専用タグへ変更し、アプリ版数への依存を除く。
4. 導入済みの現行パックを再利用できるよう、既存マーカーとの互換性を維持する。
5. 本体Release workflowからOCRパック生成・添付を外し、専用更新工程へ分離する。
6. v4.4.1の新しい本体ZIPをWindowsで生成し、本体サイズ・SHA・内容を監査する。
7. `v4.4.1`タグを新コミットへ更新し、既存Pre-releaseへ新本体ZIPとSHAを上書きする。
   タグ更新で起動するworkflowは、既存Releaseを再作成せずasset更新へ分岐させる。
8. クリーンなOCRパック保存先で、管理画面から専用Releaseを自動取得できることを実機確認する。
9. 導入済み保存先では、再ダウンロードせず「利用できます」になることを確認する。
10. v4.4.1 ReleaseからOCRパック2ファイルを削除し、本体2ファイルだけにする。
11. 最終確認後、v4.4.1のPre-release指定を外して正式版へ昇格する。

専用Releaseの公開と新本体の検証が完了するまで、現在のv4.4.1 Pre-release上のOCRパックは削除しない。

## 8. 誤ダウンロード防止

- 本体Releaseには`PoENavi.zip`以外の大容量ZIPを置かない。
- 専用Releaseタイトルの先頭へ`［内部コンポーネント］`を付ける。
- 専用Release本文の先頭で「PoENavi本体ではない」「手動取得不要」と明記する。
- 専用ReleaseはPre-releaseのまま維持し、本体のLatestへ昇格させない。
- READMEや通常の利用案内では専用Releaseをインストール先として案内しない。
- エラー調査などで手動取得が必要な場合だけ、用途と展開先を個別に案内する。

## 9. テスト計画

実装時の回帰は変更境界に限定する。

- URLが`APP_VERSION`ではなく`ndlocr-pack-v1.3.1-r1`へ固定される。
- v4.4.1と仮のv4.4.2で同じOCRパックURLになる。
- 導入済みパックが正常なら、ダウンローダーを呼ばない。
- 未導入時はSHA取得、ZIP取得、検証、導入の順に進む。
- 本体Release workflowがOCRパックassetを添付しない。
- 専用OCRパック工程だけがOCRパックassetを生成する。
- 本体ZIPへNDLOCR EXE・モデルが混入しない。
- `releases/latest`がOCRパック専用Pre-releaseを返さない。
- 公開後、専用asset URLが認証なしでHTTP 200になる。

## 10. 完了条件

- v4.4.1 Releaseには本体ZIPとSHAだけがある。
- `ndlocr-pack-v1.3.1-r1` Pre-releaseにはOCRパックZIPとSHAだけがある。
- クリーン環境のv4.4.1が専用Releaseから自動導入できる。
- 導入済み環境は同じパックを再利用し、再ダウンロードしない。
- 仮のv4.4.2でも同じ専用URLを組み立てる回帰テストが通る。
- 本体の`/releases/latest`と自動更新が専用Releaseの影響を受けない。
- 旧Updaterの展開後512MiB上限を本体ZIPが継続して満たす。

## 11. ロールバック

専用Release取得に問題があれば、v4.4.1 Pre-release上のOCRパックを残した状態で取得URLだけを
従来の本体タグへ戻す。専用Releaseは削除せず、原因調査中はPre-releaseのまま保持する。

正式版昇格後は既存タグやassetを上書きせず、修正版のPoENaviまたは新しいOCRパックタグで対応する。
