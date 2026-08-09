# ぽえとれ PoE2モード開発

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

- [ ] 実PoE2クライアントからCurrency、Rare武器／防具、Unique、Gem、Waystoneの日英全文を収集
- [x] identity indexをEE2固定revisionの日英全identityへ拡張
- [x] 基本property、公式Stat ID、数値、未解決Mod保持を実装
- [x] Currency、Unique、Rare武器／防具の基本カテゴリを追加
- [x] 既存10件単位fetch、先行表示、cache、価格結果へPoE2 adapterを接続
- [x] PoE2モードの起動カード、ホットキー、遅延生成、共通UIを解禁
- [x] PoE1／PoE2切替時に旧版のぽえとれ画面を破棄するlifecycleを実装
- [x] 共通リーグ選択UIへPoE2リーグだけを表示し、版別に選択値を保存
- [ ] 実機fixtureでadvanced Mod header、tier、roll範囲、Mod種別の精度を追加検証
- [ ] Gem、Waystoneを実機試用対象へ追加
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

- [ ] 実コピーfixtureを武器、防具、アクセサリー、Unique、Rune等で蓄積する
- [ ] 各fixtureについて「選択IDのみ」「代替IDのみ」「Local／Global OR」の3クエリを生成する
- [ ] 同一リーグ・status・数値条件で件数を比較し、選択IDが0件かつ代替IDが有件、または
      OR件数と選択ID件数の差が大きい組合せを要監査として出力する
- [ ] 件数差だけで正解と断定せず、代表出品をfetchしてベースタイプと実Modを照合する
- [ ] レート制限を避けるため、固定fixtureを使う手動／低頻度の監査コマンドとして実装し、
      通常検索中には追加API呼び出しを行わない
- [ ] 監査済みのカテゴリ・Mod規則をデータ化し、未監査範囲と最終確認日をレポートする

### 日本語公式Trade2への遷移

内部の価格取得は完全性の高い英語Trade2 APIと英語identityを正本にする。「公式トレード」
ボタンでは、実検索に使った最終JSONを複製し、`name`と`type`だけを固定日英identity indexで
日本語化して、`jp.pathofexile.com/trade2/search/poe2/<league>?q=<JSON>`を開く。
Stat ID、`stat_id|option`、filter option ID、数値条件は日英で共通のため変更しない。

英語3,880件に対して日本語itemsは3,873件で、防具groupに7件の差がある。日本語identityを
確認できない場合は日本語サイトへ英語名を推測送信せず、英語APIが発行したquery IDの
`www.pathofexile.com/trade2/...` URLへフォールバックする。

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
