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
- [ ] identity indexを3組の最小fixture用から公式metadata全体のcandidate生成へ拡張
- [ ] section、property、advanced Mod header、tier、roll、未解決Mod保持を実装
- [ ] Crossbow、Spear、Flail、Focus、Buckler、Gem、Waystoneのカテゴリを追加
- [ ] 既存Trade transport、10件単位fetch、先行表示、cache、価格結果へPoE2 adapterを接続
- [ ] PoE2モードの起動カード、ホットキー、遅延生成、共通UIを解禁
- [ ] PoE1／PoE2を実行時に切り替え、表示中ウィンドウとservice lifecycleを検証
- [ ] 縦切り完成後、重複した共通処理だけを小さく抽出する

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
