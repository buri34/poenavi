# ぽえとれPoE2 補助機能再棚卸し

監査日: 2026-08-11

比較対象:

- PoENavi `feature/poe2-foundation` / `ebb851f`
- Exiled Exchange 2 `dev` / `d72afb83bc0888919a89d3c3744acee2c597e9c8`
- 公式Trade2 metadata `vendor-sources/poe2-trade-api-2026-08-09/`

この監査はコード、UI入口、テスト、最新EE2を照合した棚卸しである。実装修正は行わない。

## 結論

以前の差分監査で未実装としてまとめていた補助機能のうち、Price trendと結果一覧の主要情報は
既にPoE2へ実装済みだった。poeprices.info予測は最新EE2でも無効化されており、PoE2 parityの
残タスクにはしない。

実際にPoE2で残る主要な機能差は次の3点である。

1. Related Items
2. 検索結果のゲーム内風Tooltip
3. 検索結果のSeller表示・状態表示などの追加情報

API Collapse、スタック総額、Wiki／PoE2DB導線は低優先度の個別判断とする。

## 実装済み

### poe.ninja参考価格とPrice trend

PoE2でも実装済み。参考価格、7日変動率、スパークライン、poe.ninja詳細ページへのリンクを
共通UIに表示する。

対応範囲:

- Unique Accessories／Weapons／Armours
- Currency
- Uncut Gems
- poe.ninja `Fragments`に収録された一部Fragment／Key

Rare装備はpoe.ninjaに個体価格がないため対象外。poe.ninja側に行がない特殊品も欄を非表示にする。
これは機能未実装ではなく、価格データの収録範囲による制約である。

### Trade検索結果の基本表示

PoE1／PoE2共通で実装済み。

- 検索候補件数、取得件数、中央値、安値例
- 最大100件までの段階取得と先行表示
- 同一出品者・同一価格のローカル集約と`×件数`表示
- Stack在庫、Item Level、Gem Level、Quality
- 出品日時の相対表示
- 対面／インスタント／値段なしの区別
- 値段なし出品の中央値・安値例からの除外
- 公式Tradeを開くリンク
- 検索・fetchキャッシュ

### 検索状態・通貨・掲載期間

PoE2でも実装済みで、最終Trade2 JSONへ反映される。

- インスタントのみ／インスタント＋対面／対面のみ／オフラインを含む
- Exalted／Divine／ExaltedまたはDivine／指定なし
- 24時間、3日、1週間、2週間、1か月、2か月、指定なし

## 一部実装

### より豊富な結果表示

PoENaviは価格判断に必要な主要列を実装済みだが、EE2より簡潔である。

PoENaviにあるもの:

- 価格、在庫、ilvl、Gem Level、Quality、出品日時、取引方式
- 同一Seller連投の集約
- 中央値、安値例

EE2にだけあるもの:

- SellerのAccount名またはIGN
- Online／AFK／Offline、Instant Buyoutの状態表示
- 自分の出品、In demand、Goneの表示
- 別通貨へ正規化した参考価格
- 各出品の完全なItem情報

主要な価格比較は可能なため「未実装」ではなく一部実装とする。

### Listing Collapse

PoENaviは同一Seller・同一価格を取得後にローカル集約する。EE2は設定により公式Trade2の
`trade_filters.collapse=true`を送るAPI Collapseも選べる。

目的は重複出品による相場の偏りを減らすことで共通だが、検索候補IDの段階から畳むか、fetch後に
畳むかが異なる。現状のPoENavi方式は中央値と安値例の偏りを抑えられているため、API Collapseは
必須差分ではない。

## 未実装

### Related Items

PoE1ではAwakened由来の関連品123グループを表示するが、PoE2処理は`related = ()`として明示的に
無効化されている。

最新EE2にはPoE2用`item-drop.json`が115グループあり、Boss Fragment一式、Key、Gem、Unique報酬などを
関連表示する。PoE2で実装する場合は、PoE1台帳の流用ではなく、このPoE2 identityとpoe.ninja PoE2
カテゴリへ対応した専用台帳が必要である。

価値:

- Fragment一式とBoss報酬の価格を同時に見られる
- Key／Invitation／Reliquary品の費用対効果を判断しやすい

優先度は中。検索精度には影響しないが、PoE2固有コンテンツとの相性がよい。

### 検索結果のゲーム内風Tooltip

PoENaviのPoE2 fetch処理は、一覧表示に必要な値へ変換した後、元のItem詳細を保持しない。
そのため各出品へマウスを重ねても、名称、Property、Socket、Implicit、Explicit、Tierなどの
ゲーム内風Tooltipは表示されない。

最新EE2はfetchしたItemを再解析し、Item画像、Socket、Property、Enchant、Rune、Implicit、
Fractured／Explicit／Desecrated／Mutated／Veiled ModをHoverまたはShift+Hoverで表示する。

価値は高いが、表示UIだけでなくfetchモデルと日英表示処理の拡張が必要。優先度は中～高。
2026-08-11、鰤さん判断により正式な残タスクへ追加した。

### Seller表示と出品状態

PoENavi内部の`PriceListing`はAccount名を保持し、インスタント判定にも`listing.fee`を使うが、
結果一覧へSeller名は表示しない。Online／AFK／Offline、IGN、自分の出品、In demand、Goneも
モデルへ保持していない。

Tooltipより実装範囲は小さいが、Seller名を常時表示すると横幅が増える。列、Tooltip、展開行の
どれに置くかはUI判断が必要。優先度は中。

## 現時点では残タスクにしないもの

### poeprices.info予測

PoENaviには未実装。ただし最新EE2でも`PricePrediction`の描画はコメントアウトされ、ソースには
PoE2対応時に再確認する旨のFIXMEがある。外部サービスもPoE2対応を前提にできないため、
EE2 parityの残タスクから除外する。

### Seller Account／Gold Fee／Sale Typeの検索条件

公式Trade2 metadataには`account`、`fee`、`sale_type`があるが、最新EE2の通常検索requestも
これらを送っていない。

- EE2のAccount設定はSeller表示と自分の出品判定用
- `listing.fee`はInstant Buyout表示用
- Online／Instant等の`status`と`trade_filters.sale_type`は別機能

したがって「EE2にあるがPoENaviにない検索条件」という以前の分類は誤り。利用要望が出た時の
独立した製品機能候補とする。

### スタック総額

EE2には1個単価×コピーしたStack数を表示する`StackValue`がある。PoENaviは出品在庫列を表示するが、
手元のStack総額は表示しない。Currency Exchange対象品では参考価格との乗算で実装可能だが、
検索精度とは無関係なため低優先度とする。

### Wiki／PoE2DB導線

最新EE2にはWikiとPoE2DBを開く導線がある。PoENaviは公式Tradeとpoe.ninjaへの導線を持つが、
PoE2 Wiki／PoE2DBボタンはない。価格検索の補助としては低優先度で、必要性を個別判断する。

## 推奨する判断順

実装する場合のおすすめ順。今回の監査では実装しない。

1. ゲーム内風Tooltip
2. Related Items
3. Seller／出品状態の追加表示
4. API Collapse
5. スタック総額
6. Wiki／PoE2DB導線

Tooltipは「安い出品が本当に同等品か」をぽえとれ内で確認できるため、最も実用効果が大きい。
Related ItemsはPoE2 Boss Fragment／Keyの価格判断に強い。Seller表示は有用だが、横幅と情報密度の
設計を先に決める必要がある。

## 根拠となる現行コード

- PoE2 poe.ninja分岐: `src/poetore/ui.py::_queue_poe_ninja_price`
- 7日変動表示: `src/poetore/ui.py::_show_poe_ninja_price`
- PoE2 Related無効化: `src/poetore/ui.py::_queue_poe_ninja_price`
- 結果モデル: `src/poetore/trade.py::PriceListing`
- PoE2 fetch変換: `src/poetore/poe2/trade.py::search_prices`
- 結果一覧: `src/poetore/ui.py::_show_price_result`
- EE2 Price trend: `renderer/src/web/price-check/trends/PriceTrend.vue`
- EE2 Related Items: `renderer/src/web/price-check/related-items/RelatedItems.vue`
- EE2 Tooltip: `renderer/src/web/price-check/trade/TradeItem.vue`、`TooltipItem.vue`
- EE2 prediction無効化: `renderer/src/web/price-check/CheckedItem.vue`
