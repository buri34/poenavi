# ぽえとれPoE2モード EE2／PoE1差分監査

監査日: 2026-08-10

実装状況: 本レポートの高優先度6件、Gem Socket／Charm Qualityチップ、
PoE2武器DPSヘッダー要約は2026-08-10の共通UI修正で対応済み。閾値はEE2準拠でGem Level 19、
Gem Quality 16、Gem Socket 3、Charm Quality 10以上を初期ONとする。

## 1. 監査対象

- ぽえとれPoE2: `feature/poe2-foundation` / `1ceab69bb8bddaa720947f927483cb84a3072d79`
- 比較するPoE1: v3.2.2 / `52518a9ee9bbb46a8cb43b1aa5ee996240f107b1`
- Exiled Exchange 2（EE2）: `d72afb83bc0888919a89d3c3744acee2c597e9c8`
- 公式Trade2 metadata: `vendor-sources/poe2-trade-api-2026-08-09/`
- 実コピーfixture: `tests/fixtures/poe2/real_copy_bilingual.csv`ほか

EE2は仕様資料として読み、正否は固定した公式Trade2 metadataと実コピーfixtureで照合した。
PoE1比較では、Influence、Link、Cluster Jewel、Heist等、PoE1にしか存在しない仕様の差は
不具合として数えない。

## 2. 結論

PoE2 Parser、日英identity、Stat解決、Local／Global選択、PoE2固有Property、Rune／Soul Core、
特殊カテゴリの基礎は十分に実用段階へ達している。一方で、PoE1共通UIが
`weapon`、`armour`、`accessory`、`gem`というPoE1側の大分類だけを判定しており、PoE2側の
`spear`、`body_armour`、`active_gem`等を同じグループとして扱えていない箇所がある。

その結果、Parserで値を正しく読めていても、画面に条件が出ない、画面の設定がTrade2へ渡らない、
逆に画面へ出ない条件が裏で強制される、という差分が残っている。優先して直すべきなのは以下の6件。

1. PoE2で「Mod数値の検索範囲」設定が効かない
2. PoE2で「価格通貨」と「出品期間」が表示だけで検索へ渡らない
3. PoE2 GemのLevel、Quality、Gem Socket条件と結果列が欠ける
4. PoE2 RareのItem Levelが画面に出ず、コピー値以上を裏で強制する
5. PoE2非Unique検索に`nonunique` Rarity条件がない
6. PoE2装備でベース範囲切替と完成品／ベースプリセットが利用できない

これらはPoE1／PoE2のゲーム仕様差ではなく、共通UIとPoE2 adapterの接続差である。

## 3. EE2との差分

### 3.1 高優先度: Mod数値の検索範囲がPoE2へ適用されない

ぽえとれ画面には「Mod数値: -5%／-10%／-20%まで許容」等の共通設定が表示される。
PoE1では`apply_search_range()`を通すが、PoE2では`poe2_trade_filters()`をそのまま返すため、
選択値を変えても通常Modのmin／maxが変わらない。

現在のPoE2では、例えば読取値105のModは、画面で-10%を選んでも105以上のまま送られる。
一部のDPSや防御Propertyだけは内部で固定10%緩和されるため、条件によって緩和方法も不統一である。

EE2は`searchStatRange`をStat filter生成へ渡している。PoE1ぽえとれも同じ共通設定を適用する。
これは検索0件や極端に少ない結果へ直結するため最優先で直す。

根拠:

- `src/poetore/ui.py:2381`
- `src/poetore/trade.py:437`
- EE2 `renderer/src/web/price-check/filters/create-stat-filters.ts:41`
- EE2 `renderer/src/web/price-check/settings-price-check.vue:75`

### 3.2 高優先度: 価格通貨と出品期間がPoE2検索へ渡らない

共通UIには「すべての通貨／Chaos／Divine」と「出品期間」が表示され、検索中表示にも選択値が出る。
しかしPoE2の`search_prices()`呼出しには`trade_currency`と`listed_within`を渡していない。
PoE2 query builderにも`trade_filters.price`と`trade_filters.indexed`がない。

公式Trade2 metadataには両方が存在し、EE2も両方を送信する。現在の画面表示は、実際には効いていない
条件を効いているように見せるため、検索精度だけでなくUI上の誤表示でもある。

根拠:

- `src/poetore/ui.py:3315`
- `src/poetore/ui.py:3418`
- `src/poetore/poe2/trade.py:618`
- `vendor-sources/poe2-trade-api-2026-08-09/filters_en.json`
- EE2 `renderer/src/web/price-check/trade/pathofexile-trade.ts:585`

### 3.3 高優先度: Gem Level／Quality／Socketの既定条件が欠ける

PoE2 ParserはGemのLevel、Quality、Socketを読めている。実コピーのFreezing Markでは、
Level 19、Quality 20、Socket 4を保持している。しかし共通UIは`category == "gem"`だけをGem扱いし、
PoE2の`active_gem`、`support_gem`、`meta_gem`を認識しない。

このため次が起きる。

- Gem Levelチップが表示されず、Trade2の`misc_filters.gem_level`を送れない
- Gem Qualityチップが表示されず、`type_filters.quality`を送れない
- 結果一覧でGem Lv／Quality列が表示されない
- Gem SocketはMod一覧には出るが常に初期OFF。EE2は3個以上を初期ONにする

EE2は通常GemでLevel 19以上、Quality 16以上、Gem Socket 3個以上を有意な初期条件として扱う。
閾値はそのまま採用するか別途製品判断できるが、値を編集・送信できない現状は差分である。

根拠:

- `src/poetore/ui.py:3675`
- `src/poetore/ui.py:3716`
- `src/poetore/ui.py:4593`
- `src/poetore/poe2/trade.py:502`
- EE2 `renderer/src/web/price-check/filters/create-item-filters.ts:489`
- EE2 `renderer/src/web/price-check/trade/pathofexile-trade.ts:726`

### 3.4 高優先度: Rare Item Levelが非表示なのに強制される

共通Item LevelチップはPoE1の`weapon`／`armour`／`accessory`だけを対象にするため、PoE2 Rare装備では
非表示になる。一方、PoE2 query builderはRareであれば必ずコピー元Item Levelをminとして送る。

例:

- Soaring Spear ilvl 81をコピーすると、UIにはilvl条件が出ない
- Trade2 JSONには`type_filters.ilvl.min = 81`が必ず入る
- ユーザーはOFFにも緩和にもできない

EE2の完成品プリセットではItem Levelは通常初期OFFであり、Exact／ベース検索時に有効化する。
PoE1ぽえとれもチップを正本としてON／OFF・編集できる。PoE2側も同じ設計に揃える必要がある。

根拠:

- `src/poetore/ui.py:3601`
- `src/poetore/poe2/trade.py:639`
- EE2 `renderer/src/web/price-check/filters/create-item-filters.ts:390`

### 3.5 高優先度: 非Unique Rarity条件がない

PoE2 query builderは、名前のない未鑑定Uniqueだけ`rarity=unique`を送る。Normal／Magic／Rareの
通常検索では`nonunique`を送らない。

Mod条件を減らした検索やProperty中心の検索では、同じベースのUniqueが候補へ混ざる可能性がある。
EE2はNormal／Magic／Rareの完成品検索で`nonunique`を送り、Exact時だけNormal／Magicを区別する。
PoE1ぽえとれも`nonunique`を送る。

根拠:

- `src/poetore/poe2/trade.py:643`
- `src/poetore/trade.py:3478`
- EE2 `renderer/src/web/price-check/filters/create-item-filters.ts:325`

### 3.6 中～高優先度: 完成品／ベースプリセットと検索範囲切替がPoE2で働かない

共通`available_trade_presets()`はPoE1の大分類だけを見るため、PoE2装備では常に完成品1種類になる。
また、ヘッダーの「ベース名／同一クラスすべて」もPoE2装備で非表示になり、PoE2 query builderは常に
exact base typeを送る。

EE2のPseudo presetは通常、同じカテゴリ全体を性能中心に検索し、クラフト価値がある場合は
Exact baseのBase Item presetも追加する。PoE1ぽえとれも完成品／ベースと、ベース名／同一クラスを
ユーザーが切り替えられる。

PoE2で「同じ性能の別ベース」を探せないことはゲーム仕様差ではない。ただし、現在のExact base既定を
維持するか、EE2同様にカテゴリ検索を既定にするかは製品判断が必要である。

根拠:

- `src/poetore/trade.py:779`
- `src/poetore/ui.py:2072`
- `src/poetore/poe2/trade.py:630`
- EE2 `renderer/src/web/price-check/filters/create-presets.ts:78`
- EE2 `renderer/src/web/price-check/filters/create-item-filters.ts:195`

### 3.7 中優先度: 一部Propertyの既定ON／OFFがEE2と異なる

- Charm QualityはPoE2共通UIで表示されない。EE2はQuality 10以上を初期ONにする
- Gem Socketはぽえとれで常に初期OFF。EE2は3個以上を初期ONにする
- Requirement LevelはぽえとれPoE2で条件化しない。EE2は低レベルRare完成品で候補を用意する
- Crafted／Fractured／Desecrated状態はぽえとれで初期ONになるが、EE2は主に対応Statそのものを使い、
  完成品検索で同じ状態を必須にしない場合がある

最後の状態条件は、現在のぽえとれがEE2より「同じ作り方・同じ状態」を強く求める方向である。
価格比較として完成性能を優先するなら、Mod条件と状態条件を別々に初期ONにするか再検討する。

### 3.8 中優先度: 未対応カテゴリが残る

現在の実コピーfixtureで対象にしたCrossbow、Focus、Buckler、Charm、Tablet、Relic、Barya、
Ultimatum、Waystone、Rune／Soul Core、Gem、Jewel等は対応している。

一方、EE2と固定identityには存在するが、PoE2 ParserのItem Class／Category mappingがないものがある。
固定Trade2／identity（2026-08-09）で確認できる内訳は次の通り。

- Life／Mana Flask: Lesser、Medium、Greater、Grand、Giant、Colossal、Gargantuan、
  Transcendent、Ultimateの各Life／Mana、計18ベース。Charmは対応済み
- Map Fragment: An Audience with the King、Breachlord Sac、Cowardly／Deadly／Victorious Fate、
  Expedition Logbook、Head of the King、Idol of Estazunti、Kulemak's Invitation、
  Raven's Reflection、Simulacrum、The Triskelion Reforgedの12種
- Pinnacle Key: Ancient／Faded／Weathered Crisis Fragment、Primary／Secondary／Tertiary
  Calamity Fragment、Call of the Shadows、Origin Core／Cradle／Sparkの10種
- Vault Key: Azmeri、Olroth、Ritualistic、Tangmazu、Arbiter、Trialmaster、Twilight、Xesht、
  Zarokh 2種のReliquary Key、計10種
- Wombgift: Ornate、Banded、Revelatory、Lavish、Signetの5種。identity上のカテゴリ名は
  `BrequelFruit`で、Trade2 itemsの独立groupは`wombgift`
- その他のEndgame Item: BreachstoneとExpedition LogbookはTrade2で独立カテゴリを持つ。
  Waystone、Barya、Ultimatum、Tabletは対応済み

これらは実コピーfixtureがなく、現状はParserでカテゴリ未解決になる可能性が高い。
まず現行リーグで実在・Trade対象かを確認し、対象なら日英実コピーを収集して追加する。

### 3.9 低～中優先度: EE2の補助機能で未実装のもの

価格検索コアとは別に、EE2には次の機能がある。

- Price trend表示
- Related Items
- poeprices.info予測
- ゲーム内風Tooltip
- Seller account、Gold fee、Sale type、API側Collapse等の詳細条件
- より豊富な結果表示

これらはPoE2仕様への必須追従ではなく、製品機能差である。現状の検索正確性を直した後に、
必要性があるものだけ個別判断すればよい。

## 4. PoE1 v3.2.2との差分

### 4.1 PoE1／PoE2仕様差として問題にしないもの

次はゲーム仕様または公式API仕様が異なるため、同じ機能に揃える必要はない。

- PoE1 Socket色／Link／White Socketと、PoE2 Gem Socket／Augment Socket
- Influence、Eldritch、Synthesised、Cluster Jewel、Heist、Logbook等のPoE1固有条件
- MapとWaystone／Tablet／Trial品のProperty差
- Rune／Soul Core、Runic Ward、Reload Time、Spirit等のPoE2固有条件
- 通常Currency／Uncut GemをTrade出品検索せず、Currency Exchange由来poe.ninja価格へ分ける方針
- Local／Global候補を匿名Query上限に合わせて単一IDへ選び、33件の監査結果を適用した方針

### 4.2 仕様差では説明できないPoE1 parity不足

PoE1で動いており、PoE2公式Trade2にも同等フィルターがあるのに、PoE2で効いていないものは以下。

- Mod数値の検索範囲
- 価格通貨
- 出品期間
- Item Levelの表示・ON／OFF・編集
- Gem Level／Qualityの表示・ON／OFF・編集
- Gem Lv／Quality結果列
- 非Unique Rarity
- Exact base／同一Item Classの切替
- 完成品／ベースプリセット
- 武器DPSのヘッダー要約

これらは、PoE2用ParserやTrade APIの不足ではなく、共通UI側のカテゴリ判定とPoE2 search adapterの
引数不足である。同じ修正基盤でまとめて直せる。

## 5. EE2と異なるが意図的・妥当なもの

### 5.1 Local／Global Stat

EE2のOR方式は匿名ユーザーのQuery複雑度上限へ達しやすい。ぽえとれは装備カテゴリから単一IDを選び、
33ケースの低頻度監査結果を反映済みである。これは現在の方針を維持してよい。

### 5.2 Currency／Uncut Gem

通常Trade2出品ではなく、poe.ninja Currency Exchange価格を表示する方針は鰤さんの判断に基づく。
EE2のBulk Trade経路との差は意図的である。

### 5.3 ログイン／POESESSID

EE2は内蔵ブラウザの公式ログインCookieを利用できる。ぽえとれはアカウント情報・Cookieを扱わない。
匿名Query上限はあるが、セキュリティと実装負荷を考えると現在は妥当な差である。

### 5.4 仮Rune／Soul Core

EE2は画像付き選択、ぽえとれは効果文付きプルダウンだが、ユーザーが空き枠へ仮挿入し、完成後のStatで
検索する意味は同じ。公式APIで空きソケット数そのものを指定できない制約も同じである。

### 5.5 Base Defence Percentile

PoE2では対応不要。公式Trade2にフィルターがなく、EE2側の生成・送信も無効化され、固定PoE2ベースに
可変基礎防御幅も存在しない。これは未実装差分へ数えない。

## 6. 現在の強い部分

再監査でEE2／公式仕様と大きく整合していた範囲は以下。

- 日英コピーのidentity、advanced Mod header、Tier、Roll範囲
- explicit／implicit／rune／crafted／fractured／desecrated／sanctifiedのStat ID解決
- 2値・4値Statの算術平均
- Local／Globalのカテゴリ別選択と監査結果
- Unique名＋Base、未鑑定UniqueのBase＋Unique検索
- AR／EV／ES／Runic Ward、DPS、APS、Crit、Reload、Spirit、Block
- Pseudo resistance、attribute、life、mana
- Waystone、Tablet、Charm、Relic、Barya、Ultimatum、Time-Lost Jewel
- Rune／Soul Core、Runeforged／Runemastered、仮Augment
- 日英Trade URL、League分離、Search／Fetch／Cache／先行表示
- poe.ninja Unique／Currency／Uncut Gem参考価格

対象回帰テスト427件は成功した。既存テストが通ることと、上記のUI・Query差が存在することは両立する。
現状のテストは、PoE2の共通UIコントロールが最終Trade2 JSONへ反映されるかを十分に固定していない。

## 7. 推奨修正順

### Step 1: PoE2カテゴリ群を共通判定へ集約

`is_equipment`、`is_weapon`、`is_armour`、`is_gem`等の判定を、PoE1大分類とPoE2細分類の両方へ
使える小さなhelperへまとめる。先に大規模リファクタリングはせず、今回判明したUI境界だけ置き換える。

対象:

- Item header／Base scope
- Weapon DPS summary
- Item Level
- Gem Level／Quality
- 結果列
- Preset判定

### Step 2: 共通検索オプションをPoE2 query builderへ接続

- search range
- trade currency
- listed within
- item level min／max
- gem level min
- rarity
- exact base／category scope

UIの表示値と最終JSONを1対1で固定する統合テストを追加する。

### Step 3: EE2既定値を必要な範囲だけ反映

- Gem Level／Quality／Socketの初期ON閾値
- Charm Quality
- Item Levelの完成品／ベース別初期状態
- Crafted／Fractured／Desecrated等の状態条件

ここは検索思想に関わるため、EE2を機械的にコピーせず、現在のぽえとれの「完成性能中心」と整合させる。

### Step 4: 未対応カテゴリを実コピーで確認

Flask、Map Fragment／Pinnacle Key／Vault Key、Wombgiftを現行リーグの実在・取引方法から確認する。
Trade対象なら日英fixtureを追加し、Parserから最終JSONまで固定する。

### Step 5: 補助機能を個別判断

Related Items、Price trend、結果Tooltip等は検索正確性を直した後に優先度を決める。

## 8. 判定

現状は「通常Unique／Rareの実機試用版」としては成立しているが、PoE2モード全体をPoE1版と同等の
完成度と呼ぶには、共通UI→Trade2 JSON境界の修正が必要である。

特に検索範囲、価格通貨、出品期間、Gem条件、Item Level、Rarityは、表示上の差ではなく検索結果を
変えるため、次の実装単位としてまとめて直すことを推奨する。
