# Awakenedカテゴリ別UI・poe.ninja価格UI監査

調査日: 2026-07-22  
基準: Awakened PoE Trade `fa31bfbbe99e04e386b4af2d71d633e2b6823c0f`

## 結論

- Awakenedはカテゴリ別の別画面ではなく、共通の並びに必要なチップとMod行だけを差し込む構造。
- poe.ninja価格・7日グラフは公式Trade検索結果とは独立した参考相場。リーグ単位の価格一覧を約30分キャッシュし、ローカル照合する。
- ぽえとれでも実装可能。PySide6の`QPainter`で小型スパークラインを描けば追加依存は不要。
- 初版はAwakenedと同じく対応する代表アイテムだけに限定し、レア完成品の推定価格としては表示しない。

## 1. Awakened画面の共通構造

上から、アイテム名／検索範囲、poe.ninja参考価格、検索条件チップ、プリセット切替、Mod条件、検索操作、検索結果の順。

チップの固定表示順:

1. リンク数
2. Map Tier
3. Valdo Completion Reward
4. Area Level
5. Heist公開Wing数
6. Sentinel Charge
7. Blighted状態
8. discriminator／Variant
9. item level
10. stock
11. ~~白ソケット数~~（Awakened準拠で検索条件から削除）
12. Gem Level
13. Quality
14. Influence
15. Magic rarity
16. 未鑑定
17. Veiled
18. Foil Unique
19. Mirrored
20. Split
21. 選択Mod数／全Mod数

CorruptedはAwakenedではこの列ではなく、名前・カテゴリ選択側の状態フィルター。ぽえとれは現在の3段階ボタンを維持してよい。

## 2. 検索プリセット

### 完成品（pseudo）

- Life、耐性、総ダメージ等のpseudo Modを中心に検索。
- Influenceやilvlなどクラフトベース向け条件は原則初期OFF。
- ユニーク、Crafted Modあり、品質20の完成品、Corrupted、Mirrored等は通常こちらだけ。

### クラフトベース（base item／exact）

- ベース、ilvl、Influence、Fractured／Synthesised等を中心に検索。
- 武器・防具の品質は20以上の場合だけ表示し、20は初期OFF、21以上は初期ON。
- Influenceは1～2個なら初期ON。

### 専用Exactのみ

- 未鑑定品、Normal品
- 非ユニークFlask／Tincture／Sanctum Relic／Idol
- Charm
- Map／Memory／Invitation
- Heist Contract／Blueprint
- 非クラフト可能な非ユニーク品

## 3. カテゴリ別UI監査

### 武器

- 共通: ilvl、Corrupted、Mirrored、Split、Influence、Magic完全一致、未鑑定、Veiled、Foil（Unique）。
- 6リンク時: Link 6を初期ON。
- クラフトベース: 品質20以上、Influence、ilvlを重視。
- 完成品: pDPS/eDPS、攻撃速度、Crit、主要pseudo Modを中心にする。

### 防具・盾

- 実在する基礎防御値だけ表示: Armour、Evasion、Energy Shield、Ward。
- ShieldはBlockも表示。ハイブリッドは実在する値を複数表示。
- Body Armourの6リンク時だけLink 6。
- クラフトベースでbase percentile、ilvl、品質、Influenceを重視。

### アクセサリー・矢筒

- Ring／Amulet／Belt／Quiverをカテゴリ検索またはベース完全一致で切替。
- 完成品はLife、耐性、能力値、Anointment、主要pseudo Modを中心にする。
- Catalyst品質はAwakenedの武器・防具向け共通品質チップの対象外。

### Jewel／Abyss Jewel

- 非ユニークはカテゴリ検索を重視。
- Magic品はMagic完全一致を初期ON。通常Jewelはilvlを検索条件にしない。
- Corrupted条件を表示し、Influence、品質、リンクは表示しない。

### Cluster Jewel

- Large／Medium／Smallを完全一致。
- ilvl帯: 1–49、50–67、68–74、75–83、84+。
- Passive数・enchant・notable等をMod欄へ。

### Gem

- Gem Level、Quality、Corrupted、Variant/discriminator。
- Gem Levelは取得値を下限にする。
- Qualityは品質ありだけ表示。通常最大Lv20は16以上、Transfiguredは20以上、最大Lv1は品質ありで初期ON。
- item level、Split、Mirrored、Influenceは通常不要。

### Flask／Tincture

- 非ユニークは専用Exact。
- 品質20以上だけ表示。20は初期OFF、21以上は初期ON。
- ilvlは表示候補だが初期OFF。Enchant、Charge Recovery、専用Modを整理。

### Map／Invitation

- Mapは専用Exact。Tierは取得値の完全一致。
- Blighted／Blight-ravaged、Valdo Completion Rewardは読み取り専用で常に反映。
- Unique Mapは固有名＋ベース＋Variant。Mapでは未知Mod表示を抑制。

### Heist Contract／Blueprint

- 専用Exact。Area Levelは取得値を下限にする。
- Blueprintは公開Wing数を取得値の下限にする。Target／Job Level等は専用Mod条件。

### Expedition Logbook

- Area Levelを`1 / 68 / 73 / 78 / 81 / 83`の帯下限へ丸める。
- AreaごとにI～Vのプリセットを作り、選択AreaのFaction・Area Modをexact条件にする。

### Chronicle／Forbidden Tome／Mirrored Tablet等

- Chronicle: Area Levelを`1 / 68 / 73 / 75 / 78 / 80`へ丸める。
- Forbidden Tome: 82以下は完全一致、83以上は83+。
- Mirrored Tablet: 取得Area Levelを下限にする。
- Memory／Sanctum Relic／Charm／Idol等は専用Exactを基本とする。

### Currency／Divination Card／Stack品

- 名前完全一致の簡潔なUI。
- Awakenedはstockを持つが、ぽえとれはBulk Exchange対象外方針のため実装しない。

## 4. poe.ninja参考価格UI

### 表示内容

- 現在の代表価格（chaosまたはdivine換算）。
- `Last 7 days`の小型エリアチャート。
- 上昇／下落／横ばいアイコンと変動の大きさ。
- クリックでpoe.ninja詳細ページを開く。

重要: dense APIの`graph`は7日分の絶対価格ではなく、現在値を基準にした変動系列。UI文言は「7日推移」または「7日変動」とし、絶対価格履歴と誤解させない。

### データ取得

Awakenedのエンドポイント:

`https://poe.ninja/poe1/api/economy/current/dense/overviews?league=<league>&language=en`

2026-07-22実測:

- HTTP 200、Standardで約2.64 MB
- `Cache-Control: public, max-age=1800, stale-while-revalidate=300, stale-if-error=86400`
- 複数カテゴリをまとめたJSON

Awakenedの取得制御:

- 人気のあるPCリーグだけ。
- UIが直近20分以内に価格を必要とした時だけ取得。
- 正常更新間隔31分。4分ごとに再試行可否を確認。
- リーグ変更時はキャッシュ破棄・即時更新。
- Divine Orb価格をchaos↔divine換算に利用。

### 対応カテゴリ

- Currency、Fragment、Scarab、Fossil、Resonator、Oil、Essence等
- Base Type
- Map、Blighted Map、Blight-ravaged Map、Invitation
- Divination Card、Captured Beast
- Unique Jewel／Flask／Weapon／Armour／Accessory／Map／Relic／Tincture
- Skill Gem

非対応・不向き:

- 一般的なレア完成品の個別Mod構成
- 二重Influenceの非ユニークベース
- poe.ninja側に集計行がないVariant
- Private Leagueや非人気リーグ

### アイテム照合キー

- Unique: 固有名＋ベース＋6L＋一部固有Variant。
- Gem: 名前＋Gem Level＋Quality＋Corrupted。
- Map: 名前＋Tier＋Blighted種別＋Atlas世代。
- 非ユニークBase: ベース名＋ilvl（86+まとめ）＋単一Influence。
- Currency等: 名前。

同名VariantのUniqueには、Vessel of Vinktar、Atziri's Splendour、Voices等の個別判定がある。

### ぽえとれへの推奨実装

1. 価格データサービスをUIから分離。
2. dense overviewをリーグ単位で30～31分キャッシュ。
3. 起動時ではなく、ぽえとれ初回表示時に遅延取得。
4. `ETag`／`If-None-Match`とgzipを使い、304なら既存キャッシュを再利用。
5. 失敗時はTrade検索を妨げず、参考価格欄だけ非表示または取得失敗表示。
6. PySide6 `QPainter`で48×32px程度のスパークラインを描画。
7. 価格欄クリックでpoe.ninja詳細ページを開く。
8. `poe.ninja参考価格`と明記し、Trade検索結果の中央値と混同させない。

初版対象:

- Unique、Gem、Map／Blighted Map
- Currency／Fragment／Divination Card等の名前一致品

ぽえとれでの対象外:

- 非ユニーク武器・防具・装飾品のBaseType価格は参考価値が低いため表示しない
- Cluster Jewelは集計自体に価値があるが、日本語コピーから`Enchant効果＋パッシブ数＋ilvl帯`への高信頼度照合が未完成のため初版では表示しない

後回し:

- 全Unique Variantの個別判定
- Legacy／Foil／Foulborn等の価格区分監査
- Private League代替
- レア完成品の価格推定

### 利用上の注意

- エンドポイントは現在利用できるが、公開された安定版API仕様書は確認できなかった。形式変更時は安全に無効化する。
- poe.ninjaのキャッシュ指示は30分なので、それより短い取得をしない。
- 出典リンクを表示し、リリース前に利用方針・クレジット要件を再確認する。

## 5. 実装順

1. 本監査を基準に共通UIの表示順・状態初期化を確定。
2. 防具・盾の専用数値欄。
3. アクセサリー、Jewel、Gem、Flask、Map、Heistの実物監査。
4. 未鑑定Unique画像カード。
5. poe.ninja価格サービス＋価格行＋7日スパークライン。
6. Windows高DPI・通信失敗・キャッシュ・リーグ変更テスト。

## 6. 根拠

- Filter生成: <https://github.com/SnosMe/awakened-poe-trade/blob/fa31bfbbe99e04e386b4af2d71d633e2b6823c0f/renderer/src/web/price-check/filters/create-item-filters.ts>
- プリセット: <https://github.com/SnosMe/awakened-poe-trade/blob/fa31bfbbe99e04e386b4af2d71d633e2b6823c0f/renderer/src/web/price-check/filters/create-presets.ts>
- チップ順: <https://github.com/SnosMe/awakened-poe-trade/blob/fa31bfbbe99e04e386b4af2d71d633e2b6823c0f/renderer/src/web/price-check/filters/FiltersBlock.vue>
- 価格UI: <https://github.com/SnosMe/awakened-poe-trade/blob/fa31bfbbe99e04e386b4af2d71d633e2b6823c0f/renderer/src/web/price-check/trends/PriceTrend.vue>
- 照合キー: <https://github.com/SnosMe/awakened-poe-trade/blob/fa31bfbbe99e04e386b4af2d71d633e2b6823c0f/renderer/src/web/price-check/trends/getDetailsId.ts>
- 取得・キャッシュ: <https://github.com/SnosMe/awakened-poe-trade/blob/fa31bfbbe99e04e386b4af2d71d633e2b6823c0f/renderer/src/web/background/Prices.ts>
