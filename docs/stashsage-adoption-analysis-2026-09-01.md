# StashSage比較・採用可能性分析

調査日: 2026-09-01

## 調査対象

- Repository: `https://github.com/rheinze08/StashSage`
- Branch: `main`
- Revision: `e9a72c008ca95274ffe6e1d0f76fc272ad3a86ef`
- 公開版表記: v0.5.14
- 最終commit日時: 2026-07-29 19:36:43 -0500

リポジトリは`sync: public export (v0.5.14)`として公開されている。デスクトップUI、Parser、
supervised inference、KNN、価格換算、Discord bot、設計資料の一部は読めるが、学習・scrape・updater等で
参照される複数module、tests、model本体、学習元parquetは公開ツリーに含まれない。

## 結論

StashSageのコードやmodelをそのままPoENaviへ取り込むのは現時点では推奨しない。一方、次の2つは
ぽえとれの現行データと公式Trade2経路だけで独自実装でき、利用者価値が高い。

1. 検索結果から「条件が近い比較対象」を数件提示する説明可能な類似出品表示
2. 過去の検索条件・件数・中央値・代表出品を保存する価格検索履歴

機械学習価格予測とCraft Potentialは、独立機能として検証する価値はあるが、製品へ組み込む段階ではない。

## ライセンスと公開範囲

公開repositoryには`LICENSE`、`COPYING`、source code利用許諾を定める文書がない。WebサイトのTermsは
無保証・利用者責任等を定めるが、複製・改変・再配布の許諾ではない。

そのため現時点の扱いは次とする。

- コード、model、画像、model metadataのコピー: 行わない
- 一般的な設計思想やUI上の着想: 独自設計・独自実装なら参考可能
- 将来コードを利用する場合: repository所有者から明示ライセンスまたは個別許諾を取得する

## StashSageの価格判断方式

### XGBoost価格予測

現在出品中のRare itemと提示価格を学習データにし、Mod、base defence、DPS等から価格を回帰予測する。
armourはAR/EV/ES構成ごとにsegmentを分け、武器はDPS派生量を特徴に含める。

公開`feature_importances_index.json`の62モデルを監査した結果:

- R²最小: -0.1268
- R²中央値: 0.2355
- R²平均: 0.2350
- R²最大: 0.6518
- R²が負: 12モデル
- R² 0.2未満: 26モデル
- R² 0.5以上: 10モデル

強いカテゴリはQuarterstaff、Spear、Bow、Crossbow、一部ES防具等。Amulet、複数Jewel、Waystone、
Tablet、一部Helmetは弱い。repository自身も「完全な正確性ではなく素早い開始価格」「未販売の現行出品を
学習するためnoisy」と説明している。

### KNN類似品

XGBoostのfeature importanceを重みにして近いitemを探し、その価格の平均・中央値と個別比較品を表示する。
予測根拠を実例で確認できる点はXGBoost単独より説明しやすい。ただし学習済みKNN bundleは大きく、
公開build size reportでは個別modelが20〜79MB、Windows ZIP全体は約505MBである。

### Craft Potential

Rare itemへ候補Modを1個追加したfeature rowを作り、予測価格の増分を順位付けする。着想は面白いが、
StashSage自身の資料でも次を考慮しないと明記している。

- affixの合法性
- prefix/suffix空き
- item level
- tag、weight、affix group競合
- 理論上の最大roll（観測dataset最大を使用）

「クラフト提案」として表示すると誤解を招きやすく、現状のぽえとれへは採用しない。

## ぽえとれへ参考にする候補

### 優先度A: 説明可能な類似出品

現行ぽえとれが取得した公式Trade2結果の中から、次の差が小さいものを上位3〜5件表示する。

- 選択中Statの一致数
- 数値差の正規化距離
- base、rarity、corrupted等の必須状態一致
- DPS、防御値、Life、耐性等の主要性能差

「AI予測価格」ではなく「今回取得した出品の中で条件が近い例」と明記する。公式検索結果、URL、実価格を
根拠にでき、別model配布や巨大assetを必要としない。類似度の内訳も表示できる。

### 優先度A: 価格検索履歴

検索時点の次をローカル保存し、同一identityの過去推移を確認できるようにする。

- 日時、league、item identity
- 有効検索条件と数値
- 件数、中央値、安値例
- 代表出品と公式Trade URL
- 0件、通信error、cache利用の区別

StashSageのPrediction Historyより、ぽえとれでは「予測履歴」ではなく一次情報である公式検索結果の履歴にする。

### 優先度B: 相場の確からしさ表示

単一価格を強く見せず、次の材料から「参考度」を表示する。

- 有効seller数
- 価格分布の幅
- 同一価格への集中度
- 近似出品数
- 0件または少数件
- 検索条件を1個外した場合の変化

これはmodel confidenceではなく、取得できたmarket evidenceの厚さを示す。

### 優先度C: ML価格予測spike

実施する場合はStashSage modelを使わず、PoENavi独自dataset・独自modelで限定spikeとする。候補カテゴリは
公開R²が比較的高く、ぽえとれ側でもDPSを安定解析できるSpear、Crossbow、Bow、Quarterstaff等から始める。

採用条件:

- 時系列holdoutで検証する（random splitだけにしない）
- league更新後の劣化を測る
- MAE、中央値誤差倍率、価格帯別誤差を表示する
- 公式Trade結果より悪い場合は採用しない
- 「推定」であり出品保証ではないことをUIで明示する

## 参考にしない／後回し

- Stash scrape: ぽえとれの即時価格検索という中心目的から外れ、rate limitと運用負担が大きい
- Discord bot: PoENavi desktop内で完結する現行UXより優先度が低い
- poe2scout通貨換算: ぽえとれにはpoe.ninjaと公式Trade経路があり、source追加の利益が小さい
- 学習済みpickle配布: 巨大化、更新、Python互換性、供給網検証の負担が大きい
- Craft Potential: legalityを扱わない状態ではユーザーを誤誘導しやすい

## 推奨する次の作業

最初は実装ではなく、既存の保存済みTrade2応答を使った「類似出品スコア」のoffline spikeを行う。
代表Rare装備20〜30件で、人が近いと判断する比較品と順位が合うか確認する。良ければ価格結果UIへ
任意展開の「近い出品」欄として設計する。その後、同じ保存形式を価格検索履歴へ再利用する。
