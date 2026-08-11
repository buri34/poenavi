# ぽえとれ PoE2モード開発

2026-08-10時点のEE2／PoE1 v3.2.2との再比較結果と、検索精度へ影響する差分の優先順位は
`docs/poetore-poe2-gap-analysis-2026-08-10.md`を正本とする。

## 守る設計境界

既存のPoE1 ParserとTrade処理は、PoE2対応のために先行移動・大規模改変しない。
PoE2側を`src/poetore/poe2/`の新規モジュールとして追加し、コピー文面から公式Trade2の
実出品まで縦方向に成立させた後、本当に共通化できるtransport、cache、price resultだけを
小さく抽出する。

これはPoE2完成後に忘れず再評価する残タスクであり、「共通化しない」という決定ではない。

## 2026-08-09 最小縦切り

- [x] 公式Trade2の英日stats、items、filters、static、leaguesをsnapshot化
- [x] URL、取得時刻、SHA-256、bytes、group／entry件数をsource lockへ固定
- [x] EE2参照revisionを`d72afb83bc0888919a89d3c3744acee2c597e9c8`へ固定
- [x] Currency、Rare装備、Uniqueの日英fixtureを出典・期待値付きで固定
- [x] 既存PoE1 Parserを移動せず、PoE2 Parserの最小骨格を追加
- [x] name、type、categoryだけのPoE2最小query builderを追加
- [x] コピー文面→Parser→query→モックsearch/fetchのテストを追加
- [x] 公式Trade2 search/fetchでUnique Focusの実出品を確認

fixtureの日本語側は、固定EE2英語fixtureと固定EE2日本語identityデータから作った対訳fixture。
PoE2クライアントから直接採取した文面とは称さない。実機試用前に、鰤さんの日本語クライアント
から採取した全文へ置き換えまたは追加する。

## 次の残タスク

- [ ] Fractured由来Statの状態行（「特殊／フラクチャー」）を通常の検索チップ風UIで表示し、初期OFFとする
- [ ] 未鑑定、Veiled、Foil Unique、Split、Mirroredの状態切替UIを、循環選択機能を維持したまま
      通常検索チップに近い外観へ統一する（詳細仕様は`docs/poetore-pending-tasks.md`を正本とする）
- [ ] 実PoE2クライアントからCurrency、Rare武器／防具、Unique、Gem、Waystoneの日英全文を収集
- [x] identity indexをEE2固定revisionの日英全identityへ拡張
- [x] 基本property、公式Stat ID、数値、未解決Mod保持を実装
- [x] Currency、Unique、Rare武器／防具の基本カテゴリを追加
- [x] 既存10件単位fetch、先行表示、cache、価格結果へPoE2 adapterを接続
- [x] PoE2モードの起動カード、ホットキー、遅延生成、共通UIを解禁
- [x] PoE1／PoE2切替時に旧版のぽえとれ画面を破棄するlifecycleを実装
- [x] 共通リーグ選択UIへPoE2リーグだけを表示し、版別に選択値を保存
- [ ] 実機fixtureでadvanced Mod header、tier、roll範囲、Mod種別の精度を追加検証
- [x] Gem、WaystoneをParser／Trade2検索対象へ追加（実コピー全文の追加検証は継続）
- [ ] Crossbow、Spear、Flail、Focus、Bucklerの実コピー全文を追加検証
- [ ] 縦切り完成後、重複した共通処理だけを小さく抽出する

## Phase 1〜3 実機試用版（2026-08-09）

PoE1と同じぽえとれ画面をPoE2でも開放し、PoE2 Parser／Trade2 adapterを実行時に
切り替える。リーグ欄は共通UIだが、PoE2ではTrade2 `/data/leagues`の結果だけを表示し、
`league_poe2`へPoE1とは別保存する。「自動」はStandard／Hardcore以外の最初のSCを選ぶ。

実機試用対象はCurrency、Unique、基本Rare武器／防具。特殊カテゴリ、Rune／Soul Core、
Charm／Tablet／Relic、Sanctified／Desecrated／Runeforged、Pseudo Stat、DPS自動計算、
品質20%換算、PoE2固有Unique例外は今回の対象外として残す。解析できない数値Modは
黙って捨てず、画面の未解決警告へ残す。

### 初回実機報告の修正

日本語Mageblood詳細コピーを固定fixtureへ追加。全角コロンの装備条件、`{ 暗黙モッド }`／
`{ ユニークモッド }`見出し、`2(1-3)`のroll範囲、4種類のMage's Legacy option、
`43(25-50)%`の可変値を解析し、検索可能な7 Modを全件解決する。

PoE2リーグは画面生成時点でRunes of Aldur／HC Runes of Aldur／Standard／Hardcoreを
表示し、ライブ更新に失敗しても同じ候補を維持する。Trade2のoption StatはPoE1と異なり、
`stat_id|option`をIDとして送る。公式Runes of Aldurの`any`検索でMagebloodの全7条件が
12件となることを確認した。

### 2回目の実機報告の修正

日本語Rare手袋の実コピー全文をfixtureへ追加。公式Trade2の日本語Statテンプレートが
`混沌耐性 #%`である一方、ゲーム内コピーは正の値へ`+15(12-15)%`のように`+`を挿入する。
テンプレート自体に符号指定がない`#`では、このコピー由来の正符号を許容するようにした。
混沌耐性は`explicit.stat_2923486259`、min 15として検索クエリへ送る。

同じ全文に含まれる`{ 冒涜 プレフィックスモッド ... }`はdesecrated、行末`(rune)`は
augmentとして優先解決する。Runes of AldurでGrand Bracers＋混沌耐性15以上を実検索し、
HTTP 200、2件、fetchした出品のbaseTypeがGrand Bracersであることを確認した。

### 3回目の実機報告の修正

日本語Rareスピアの実コピー全文をfixtureへ追加。EE2固定revision
`d72afb83bc0888919a89d3c3744acee2c597e9c8`の`getRollOrMinmaxAvg()`と同様、
2値および4値Statは算術平均へ正規化してTrade2のminへ送る。
`25から39の物理ダメージを追加する`は`(25 + 39) / 2 = 32`として表示・送信する。

PoE2装備の品質は20でも共通品質チップへ表示する。通常品質20は価値を決める条件では
ないため初期OFFとし、ユーザーがONにした時だけ`misc_filters.quality.min`へ送る。
従来はチップが非表示でもParser値から品質20を送っていたため、UIと最終JSONの正本を
品質チップへ一本化した。Runes of AldurでSoaring Spear＋物理フラット平均32以上を
実検索し、HTTP 200、3,177件を確認した。

### poe.ninja PoE2 Unique参考価格

PoE2 EconomyのUniqueカテゴリ画面は、公開画面用の内部API
`/poe2/api/economy/stash/current/item/overview`を使用する。カテゴリ型はPoE1の
`UniqueAccessory`ではなく`UniqueAccessories`、同様に`UniqueWeapons`、
`UniqueArmours`の複数形。これは公式に安定性が保証されたAPIではないため、31分キャッシュし、
取得失敗時は参考価格欄だけを非表示にしてTrade2検索を継続する。

2026-08-09 JST、Runes of Aldurの実APIでMageblood 350 Divine、The Taming
3.91 Divineを確認した。Unique名とbaseTypeの両方を完全一致させ、corrupted集計は通常品と
混ぜない。ぽえとれ設定画面にも、ぽえなびと同じ`poe_version`と
`poe_version_mode`（毎回確認／PoE1固定／PoE2固定）を追加する。

### Local／Global Statの単一選択と監査

通常検索はPoE1ぽえとれと同様、アイテムカテゴリとMod種別から適切なLocal／Globalの
Trade2 Stat IDを1つ選んで送る。EE2式のOR検索はPoE2の仕様変化へ柔軟だが、未ログイン時の
公式Trade2クエリ複雑度上限へ達しやすく、再送による検索遅延も避けたい。このため通常経路では
速度と未ログイン互換性を優先して単一IDを使い、正しさは別の監査で継続検証する。

- [x] 実コピーfixtureを武器、防具、アクセサリー、Unique、Rune等で蓄積する
- [x] 各fixtureについて「選択IDのみ」「代替IDのみ」「Local／Global OR」の3クエリを生成する
- [x] 同一リーグ・status・数値条件で件数を比較し、選択IDが0件かつ代替IDが有件、または
      OR件数と選択ID件数の差が大きい組合せを要監査として出力する
- [x] 件数差だけで正解と断定せず、代表出品をfetchしてベースタイプと実Modを照合する
- [x] レート制限を避けるため、固定fixtureを使う手動／低頻度の監査コマンドとして実装し、
      通常検索中には追加API呼び出しを行わない
- [x] 監査済みのカテゴリ・Mod規則をコードと回帰テストへ固定し、最終確認日を記録する

#### 30秒間隔の低頻度監査計画

監査は通常の価格検索プロセスから完全に分離し、OpenClawの隔離Cronを
`schedule.kind=every`、`everyMs=30000`で起動する。1回のCron実行でTrade2 APIを最大1回だけ
呼び出し、監査状態ファイルに次の処理位置を保存する。

```text
fixture / Stat候補
  → 選択ID search
  → 代替ID search
  → Local／Global OR search
  → 必要なケースだけ代表出品fetch
  → 判定・次候補
```

このため1候補につき最低90秒、fetchを行う候補は最低120秒かけ、短時間に複数リクエストを
まとめて送らない。各応答の`X-Rate-Limit-Ip-State`、`X-Rate-Limit-Account-State`、
`Retry-After`を保存し、残量が安全閾値以下なら次回実行をスキップする。HTTP 429は再試行せず、
指定された待機時間＋安全余裕まで監査を自動停止する。ヘッダーがない場合も30秒未満では送らない。

監査状態はcandidate ID、段階、query ID、件数、代表出品ID、最終呼出時刻、再開可能時刻を
原子的に保存する。CronやMacが停止しても次回は保存位置から再開し、同じ段階を重複送信しない。
監査対象を使い切ったらCronを自動無効化し、件数差・実Mod照合・未判定理由をCSV／JSONへ出力する。
監査CLIは`scripts/audit_poetore_poe2_local_global.py`として実装した。固定Stat metadataと
日英実コピーfixtureからLocal／Global候補を抽出し、状態・途中結果を
`~/.openclaw/data/poenavi-audits/poe2-local-global/`へ原子的に保存する。2026-08-09 JSTに
OpenClaw Cron `28f3db2b-dd66-4ef2-8a17-21ab6535b15b`を30秒間隔で起動した。
CronはCLIを1ステップだけ呼び、完了時に自身を削除する。監査結果から本番のStat選択規則を
自動変更せず、`report.json`／`report.csv`を人間が確認してから反映する。

2026-08-10 JSTに全33候補・API 109回の監査が完了した。22候補は現行選択が正しく、10候補は
代替IDだけが有件だったため、代表出品の実Mod hashをfetchして代替IDを正解と確定した。残る
Crossbow命中力1候補はLocal／Globalの両方に出品があったが、Local 1,512件・Global 19件で、
通常武器Affixとして現行Localを維持した。反映した規則は次のとおり。

- 防具のArmour／Evasion／Energy Shield／Runic WardはUniqueを含めLocalを選ぶ
- 防具上のAttack SpeedとAccuracyはGlobalを選ぶ
- 武器の通常Attack SpeedとAccuracyはLocalを選ぶ
- 監査した武器のcrafted Accuracy複合ModはGlobalを選ぶ

旧実装で誤選択していたRare手袋Attack Speed、Rare Spear crafted Accuracy、Helmet Accuracy、
Runemastered Unique防具のEvasion計10件を修正し、日英実コピーfixtureで最終Stat IDを固定した。

### 日本語公式Trade2への遷移

内部の価格取得は完全性の高い英語Trade2 APIと英語identityを正本にする。「公式トレード」
ボタンでは、実検索に使った最終JSONを複製し、`name`と`type`だけを固定日英identity indexで
日本語化して、`jp.pathofexile.com/trade2/search/poe2/<league>?q=<JSON>`を開く。
Stat ID、`stat_id|option`、filter option ID、数値条件は日英で共通のため変更しない。

英語3,880件に対して日本語itemsは3,873件で、防具groupに7件の差がある。日本語identityを
確認できない場合は日本語サイトへ英語名を推測送信せず、英語APIが発行したquery IDの
`www.pathofexile.com/trade2/...` URLへフォールバックする。

## Phase 4〜5 PoE2固有プロパティ・状態区分（2026-08-09）

公式Trade2 snapshotとEE2固定revisionを照合し、次の専用条件を共通検索UIの編集可能行へ
追加した。条件をOFFにした場合は最終JSONへ送信しない。

- 装備: Spirit、Runic Ward、Reload Time、Augment Socket数
- Gem: Gem Socket数（Active／Support／Meta Gemを別カテゴリで保持）
- Waystone: Tier、Revive、Pack Size、Magic Monster、Rare Monster、Area Level、
  Unidentified Tier
- 状態: Sanctified、Desecrated、Fractured、Crafted、Corrupted、Mirrored
- 単体アイテム: RuneとSoul Coreを`currency.rune`／`currency.soulcore`へ分離

Deflectionには公式Trade2の集約property filterがないため、コピー文面の個別Stat IDとして
検索する。Runeforged／Runemasteredにも状態filterはなく、公式items上の別ベースidentityを
そのままtypeへ送る。通常ベースへ丸めない。

Rune／Soul Core由来の数値Modは通常explicitへ混ぜず、`rune.*`等の由来Statとして保持する。
Sanctified／Desecrated／Fractured／Craftedも見出しから由来を判別し、対応する状態filterと
個別Statを独立してON／OFFできる。

### Phase 4〜5後も残す境界

- Empty Socket数そのものには公式専用filterがない。今回は総Augment Socket数を実装し、
  Empty Socketへの仮想Rune追加は高度検索支援のPhaseへ残す。
- Runeforged／Runemasteredは状態チェックではなく別ベース選択を維持する。
- 固定EE2由来の日英fixtureは実クライアント採取と混同しない。実コピー全文を継続追加する。
- MagicのAffix付き表示名はEE2同様、全ITEM identityの連続部分一致から最長かつ
  アイテムクラスとカテゴリが一致するベースを選ぶ。Waystone等のカテゴリ固有文字列除去へ
  戻さない。公式日本語identityには同一訳を持つ英語ベースが8組あるため、将来は防御値等の
  propertyを使うvariant判定を追加し、曖昧な日本語ベースの単一選択を監査する。
- Deflection等の個別StatとLocal／Global単一選択は、低頻度監査で件数と実出品を照合する。

### Magic Waystone実コピー追補

日本語Magic Waystoneは`破壊する 感電する ウェイストーン (ティア15)`のように、Affix名を
Tier付きベース名の前へ連結する。末尾の`ウェイストーン (ティアN)`を公式base identityへ
正規化し、Affix名をtypeへ混ぜない。実コピー表記の`パックサイズ`と
`ウェイストーンドロップ確率`は、それぞれ`map_packsize`と`map_bonus`へ変換する。

提供全文のクリティカル率、クリティカルダメージ、感電領域の3 Modを公式Stat IDへ解決し、
説明文は未解決Mod警告へ入れない。Runes of AldurへTier／復活／Pack Size／Drop Chanceと
3 Modを送信し、HTTP 200、30件を確認した。

## Phase 6 特殊カテゴリ（2026-08-09）

公式Trade2 snapshotとEE2固定revisionを照合し、次のPoE2カテゴリを専用Tradeカテゴリへ
分離した。通常・Magic・Rareはベースidentityだけをtypeへ送り、Uniqueはnameとtypeを送る。

- Charm: `flask.charm`
- Tablet: `map.tablet`
- Relic: `sanctum.relic`
- Jewel／Time-Lost Jewel: `jewel`
- Djinn Barya等: `map.barya`
- Inscribed Ultimatum／Fate: `map.ultimatum`

Barya／UltimatumではArea Levelを解析して初期ONにする。Trial Countはコピー文面から保持するが、
現在の公式Trade2には対応する直接filterがないため検索条件へは送らない。Ultimatum Hintは
`Victorious`／`Cowardly`／`Deadly`へ正規化し、EE2と同様に編集可能な初期OFF条件として表示する。

Time-Lost JewelのRadiusも解析して保持するが、現在の公式Trade2にはRadius専用filterがない。
Tabletの残り使用回数はpseudo Statであり、高度検索支援のPhaseへ残す。Filled Coffinと
Mirrored TabletはEE2のPoE1実装には存在する一方、固定したPoE2 Trade2 itemsとidentityには
存在しないため、PoE2用の推測カテゴリやidentityは作らない。

固定fixtureはEE2の日英identityと公式snapshotから作った合成コピー文面であり、実クライアント
採取とは区別する。Charm、Tablet、Relic、Barya、Ultimatum、Time-Lost Jewelの実コピー全文を
入手した際はfixtureを置き換えるか追補し、表示文面の変更を監査する。

2026-08-09 JST、Runes of AldurでMagic Charm、通常Tablet、Djinn Barya、Inscribed Ultimatumを
検索し、HTTP 200と取得出品のbaseType一致を確認した。Relic検索もHTTP 200で受理されたが、
確認時点の出品は0件だった。その後Rate Limitへ到達したため、Time-Lost Jewelの追加ライブ
検索は行わず、固定metadataと最終JSONで検証した。

## Phase 7 高度な検索支援（2026-08-09）

EE2固定revisionの計算規則と公式Trade2 filterを照合し、PoE2専用カテゴリのまま共通検索UIへ
次の高度条件を追加した。

- 武器: 物理DPS（最低品質20%換算）、元素DPS、合計DPS、APS、Critical Hit Chance
- 防具: Armour、Evasion、Energy Shield、Runic Ward（最低品質20%換算）、Block
- Pseudo: 元素耐性合計、火／冷気／雷／混沌耐性、筋力／器用さ／知性、最大Life、最大Mana
- Tablet: `pseudo.pseudo_number_of_uses_remaining`
- Unique可変値: コピー文面の現在値とroll下限／上限を保持し、安全に高いほど良いと判断できる
  Statだけ共通UIの可変値操作へ接続

初期ONのPseudoが集約する元Modは同時送信せず、同じ性能を直接StatとPseudoで二重拘束しない。
最大LifeはEE2と同様、明示Lifeが存在する時だけStrength由来分を加える。最大Manaも明示Manaが
存在する時だけIntelligence由来分を加える。元素耐性合計は各元素への寄与数を反映するため、
全元素耐性10%は合計30として扱う。

### Empty Augment Socketの仮想Rune検索

EE2固定の日英itemsから259アイテム・475カテゴリ別効果を`augment_index.json`へ生成した。
非Unique／非Mirrored装備に空きAugment Socketがある時だけ、検索画面へ
「空きソケットN個 仮Rune」選択を表示する。選択したRune／Soul Coreの効果を空き数ぶん合算し、
`rune.*` Statとして最終Trade2 JSONへ加える。ゲーム内アイテム自体は変更しない。

PoE2ではCorrupted品にもRune／Soul Coreを挿入できるため、Corruptedは表示除外条件にしない。
EE2の`create-item-filters.ts`も空きソケットUIの条件を`rarity !== Unique`としており、
Corrupted状態では除外していない。UniqueはEE2準拠で仮挿入UIを出さず、Mirroredは変更不能品として
引き続き対象外にする。

同じ効果に複数のTrade ID候補がある場合は、選択した仮想Runeの1条件だけを
`count(min=1)`のORへする。通常ModのLocal／Global単一選択方針は変更せず、未ログイン時の
クエリ複雑度を常時増やさない。Socket-bound効果も固定データの対象カテゴリだけへ表示する。

仮挿入候補は元データ順ではなく、効果系統、Rune系列、強度の順で表示する。火・冷気・雷耐性など
同種の元素効果を隣接させ、同一系列は数値の強い順に`Perfect → Greater → 通常 → Lesser`とする。
Soul Core等の段階名を持たない候補も同じ効果系統へまとめ、同条件では表示名で安定ソートする。

### 公式仕様上の境界

Exact／Count／Notの一般編集UIは、今回必要な仮想Runeの限定OR以外は導入しない。
PoE2 Trade2側へ正式filterが追加された時点でmetadata差分監査から再評価する。

### Base Defence PercentileはPoE2で対応不要（2026-08-09調査）

Base Defence Percentileは「公式仕様待ち」ではなく、PoE2の一般仕様ではないと判断し、実装対象・
残タスクから除外する。判断根拠は次のとおり。

- PoE2公式`/api/trade2/data/filters`のEquipment FiltersにはAR、EV、ES、Runic Ward等の実数値は
  あるが、`base_defence_percentile`は存在しない。
- EE2固定revisionの通常フィルター生成では`filterBasePercentile(ctx)`がコメントアウトされ、
  Trade2 JSONへ`equipment_filters.filters.base_defence_percentile`を送る処理もコメントアウトされている。
- EE2 ParserにはPoE1由来と見られる計算コードが残るが、`no ward since base percent isn't used anymore`
  と明記されている。汎用検索で有効な機能ではない。
- PoENaviが固定したEE2由来PoE2 identity全件を監査した結果、AR／EV／ES／Wardの基礎値範囲で
  `min != max`となるベースは0件だった。Percentileを計算するランダムな基礎防御値幅がない。

参照先：

- <https://www.pathofexile.com/api/trade2/data/filters>
- <https://github.com/Kvan7/Exiled-Exchange-2/blob/d72afb83bc0888919a89d3c3744acee2c597e9c8/renderer/src/web/price-check/filters/create-stat-filters.ts#L109-L114>
- <https://github.com/Kvan7/Exiled-Exchange-2/blob/d72afb83bc0888919a89d3c3744acee2c597e9c8/renderer/src/web/price-check/trade/pathofexile-trade.ts#L943-L956>
- <https://github.com/Kvan7/Exiled-Exchange-2/blob/d72afb83bc0888919a89d3c3744acee2c597e9c8/renderer/src/parser/Parser.ts#L1906-L1940>

`augment_index.json`はEE2のMIT対象データを由来として固定revisionを明記する。更新時は
`build_poetore_poe2_indexes.py --ee2-root <固定checkout> --augment-only`でcandidateを生成し、
カテゴリ数・効果数・Trade ID差分を確認してから適用する。

## 実コピーによる曖昧ベース判定（2026-08-09）

同じ日本語名を持つPoE2装備を、鰤さんが同一現物の日本語／英語設定で詳細コピーした14組を
`ambiguous_bases_bilingual.json`へ固定した。現行リーグで出品が存在しないOminous Glovesと
Wanderer Armourは対象外として記録し、存在を推測したfixtureは作らない。

EE2固定revisionの`items.ndjson`からidentityを生成する際、従来捨てていた`tags`と
`armour`（基礎AR／EV／ES／Ward範囲）をVariantごとに保持する。同じ日本語名の候補が複数ある
Rare／Magic装備は、コピーされた最終防御値から品質・ローカルflat・ローカルincreasedの影響を
除き、EE2の基礎値候補へ照合して英語`ref_name`を一意に決定する。

Uniqueは名前が持つ`base_ref`を先に使う。基礎値による候補差が一意にならない場合は先頭候補を
推測採用せず、`base identity曖昧`として検索を停止する。日英14組についてParserの`base_type`、
英語Trade2の`type`、日本語公式Trade2 URLのローカライズ済み`type`まで回帰テストする。

## 公式API検証記録

2026-08-09 JST、リーグ`Runes of Aldur`へ以下を送信した。

- name: `The Eternal Spark`
- type: `Crystal Focus`
- category: `armour.focus`
- status: `online`

searchはHTTP 200、total 101。先頭IDをfetchし、返却itemのnameが`The Eternal Spark`、
baseTypeが`Crystal Focus`であることを確認した。query IDや出品IDは一時値のため正本へ固定しない。

## 固定入力

- Source lock: `scripts/poetore-poe2-sources.lock.json`
- Snapshot: `vendor-sources/poe2-trade-api-2026-08-09/`
- Fixture: `tests/fixtures/poe2/minimal_items.json`
- Identity: `data/poetore/poe2/identity_index.json`

snapshot検証:

```bash
python3 scripts/snapshot_poetore_poe2_sources.py --verify
```

## 実コピーfixture拡充の残タスク（2026-08-09）

鰤さんが日英同一現物を収集した28ケースのCSVを
`tests/fixtures/poe2/real_copy_bilingual.csv`へ固定した。実コピー28組のうち、Uncut Gemを
除く27組をParserの日英identity回帰へ利用する。Sanctified、Mirrored、複雑Unique 3件も収集済みで、
実コピー待ちは0件となった。

Uncut Gemは通常Trade2出品検索ではなくCurrency Exchangeで売買する運用のため、
`Uncut Skill Gems`／`スキルジェムの原石`を専用`uncut_gem`カテゴリとして解析し、通常Currencyと
同じくTrade2出品検索を行わない。poe.ninjaが実際に使用する
`/poe2/api/economy/exchange/current/overview`の`Currency`／`UncutGems`をリーグ別に31分キャッシュし、
英語identity（UncutはLevel込み）で照合する。表示価格は`maxVolumeCurrency`／`maxVolumeRate`から、
最も取引量の多いDivine／Exalted／Chaos建ての1個あたり価格を算出する。取得不能時は参考価格欄だけを
非表示とし、別のTrade2検索へフォールバックしない。

確認ソース:

- <https://poe.ninja/poe2/economy/runesofaldur/currency>
- <https://poe.ninja/poe2/economy/runesofaldur/uncut-gems>
- <https://poe.ninja/poe2/api/economy/exchange/current/overview?league=Runes%20of%20Aldur&type=Currency>
- <https://poe.ninja/poe2/api/economy/exchange/current/overview?league=Runes%20of%20Aldur&type=UncutGems>

EE2の現行実装も、Item Classを欠くMeta Gemを特例としてGEMデータベースへ照合する。PoENaviは
さらに誤判定防止として、コピータグの`Meta`／`メタ`と、固定GEM metadataの`MetaSkillGem`が
両方一致した時だけMeta Gemとして扱う。Active／Support／Meta Gemの説明・効果区画は、EE2同様
アイテムMod解析へ渡さず、identity・Level・Quality・SocketだけをTrade条件に使う。

未鑑定UniqueはEE2同様、固有名を要求せず、正規化したベース、Unique rarity、Identified=falseを
Trade2へ送る。RunemasteredはEE2上でもRuneforgedから文字列を除く対象ではなく別ベースであり、
PoENavi内部でも`runemastered`と`runeforged`を別フラグとして保持する。

## 実コピーfixtureの未解決警告整理（2026-08-09）

EE2はCharmのProperty区画に`Currently has # Charges`がある場合、持続時間、消費／最大／現在
チャージ、付与効果を含む区画全体をFlask系Propertyとして消費し、Mod解析へ渡さない。PoENaviも
同じ検索責務に揃えつつ、表示に使える値は`properties`へ保持する。Trade2へ送るのは暗黙の発動条件と
明示Affix（例：Charges per use減少）だけとする。

EE2のStat matcherが持つ`negate`規則もcompact indexの照合時に再現する。`reduced`／`減少する`を
canonicalな`increased`／`増加する`Statへ照合し、値を負数へ変換する。低い値が良い条件はTrade2の
maxへ送る。これにより要求能力値減少、Charges per use減少、毒・出血持続時間減少を日英同一IDへ
解決する。Tabletのコロンなし`10 uses remaining`／`残り使用回数 10回`もPropertyとして保持する。

収集済み実コピー23組（Uncut Gem除外）を再集計し、数値を含む未解決行が0件であることを固定する。
