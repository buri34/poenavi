# ぽえとれ 新リーグ向けTradeデータ更新計画

更新日: 2026-07-24
状態: 実装前設計
対象: PoE 1の新リーグ開始時および公式Tradeデータ更新時

## 目的

新リーグで追加・変更されるアイテム、Mod、Trade optionへ、短時間かつ安全に追従できる
更新フローを用意する。

運用者が行う判断を、原則として次の3段階へ絞る。

1. 更新候補を生成する
2. 要約された差分と警告を確認する
3. 問題がなければ正本へ反映する

取得データを無条件に上書きせず、不明点や大きな差分があれば正本を変更せず停止する。

## 今回の境界

この文書は実装前の設計を確定するものであり、更新コマンドやアプリ本体は変更しない。

既存の`scripts/build_poetore_metadata.py`は廃止せず、Modメタデータ更新の中核として再利用する。
新しい総合フローは、その前後に日英データ同期監査、pseudo監査、代表API確認を追加する。

## 更新対象

### 1. Modメタデータ

- `data/poetore/mod_metadata.json`
- 日本語Mod matcher
- 公式Trade stat ID
- Tier、Prefix／Suffix、local判定
- 数値方向、符号反転、完全一致、option
- Gemおよび防具ベースの派生情報

主な入力:

- Awakened PoE Tradeの固定commit
- RePoEのstats／mods
- 日本語公式Trade API `/api/trade/data/stats`

既存の生成・監査機能をそのまま利用する。

### 2. 日英公式Tradeのアイテム一覧

- 英語公式Trade API `/api/trade/data/items`
- 日本語公式Trade API `/api/trade/data/items`
- Unique名、ベース名、Gem名、カテゴリ、option ID

日英配列の位置や件数が一致するとは仮定せず、可能な限りIDとカテゴリをキーに比較する。
名称だけで自動対応できない項目は「未対応候補」として報告し、推測で正本へ書かない。

### 3. 日英公式TradeのStat一覧

- 英語公式Trade API `/api/trade/data/stats`
- 日本語公式Trade API `/api/trade/data/stats`
- stat ID、種別、text、option ID／text

同じstat IDを軸に日英を比較し、片側欠落、text変更、option追加・削除・名称変更を報告する。

### 4. pseudo派生データ

- `data/poetore/pseudo_definitions.json`
- `data/poetore/pseudo_relations.json`

Awakened参照commitを更新した場合に、追加・削除・変更を別枠で表示する。
関係の変化が検索条件の置換・集約へ影響するため、自動反映前に人間のレビューを必須とする。

### 5. source lock

- `scripts/poetore-sources.lock.json`

各入力のURL、Awakened revision、取得日、SHA-256を保持する。
通常実行ではhash不一致をエラーとし、更新モードでのみ新hashを候補化する。

## 生成するレポート

機械可読JSONと、人間が短時間で読めるMarkdownを同時に生成する。

想定ファイル:

- `build/poetore-update-report.json`
- `build/poetore-update-report.md`

Markdownの先頭には次の要約を置く。

- 判定: `PASS`／`REVIEW REQUIRED`／`BLOCKED`
- 入力元とrevision／取得hash
- アイテム: 追加／削除／変更／日英片側欠落の件数
- Stat: 追加／削除／変更／option差分／日英片側欠落の件数
- Modメタデータ: 追加／削除／変更／曖昧／未解決の件数
- pseudo: 追加／削除／変更の件数
- テストと公式Trade API疎通の結果
- 正本へ反映可能か

詳細には、件数だけでなく確認対象のID、旧値、新値、英語名、日本語名、影響カテゴリを載せる。

## 自動停止条件

次のいずれかに該当した場合、正本やsource lockを変更せず`BLOCKED`で終了する。

- 入力元を取得できない、JSONとして読めない
- 通常モードでsource hashがlockと一致しない
- 同一IDに矛盾する複数定義がある
- 必須ID、英語名、日本語名などが空
- 日英の対応を一意に決められない
- 公式stat IDが消え、ぽえとれの現行定義から参照されている
- Mod削除が既存基準の10%超または100件超
- pseudo relationの参照先が存在しない
- 候補データを使ったテストが失敗する
- 代表Trade APIクエリがHTTP成功しても、送信条件を正しく復元できない

`--allow-large-removal`のような例外指定は、上流で意図した削除だと確認して記録を残した場合だけ使う。

## 警告に留める条件

次は自動反映せずレビュー対象にするが、データ全体の生成は継続してよい。

- 新規アイテムまたは新規Stat
- 日本語だけ未公開、または英語だけ未公開
- 表示名だけの変更
- optionの追加・表示順変更
- Awakenedにはあるが公式Tradeにない項目
- 公式TradeにはあるがRePoE／Awakenedにない項目
- matcherが複数候補へ一致する

未確認値は正本へ推測で埋めず、レポート内の候補として分離する。

## 想定コマンド

最終的には、総合入口を1つ用意する。

```bash
# lock済み入力で再現性を確認
PYTHONPATH=. python scripts/update_poetore_trade_data.py

# 上流の最新データを取得し、候補と差分だけ生成
PYTHONPATH=. python scripts/update_poetore_trade_data.py --refresh

# レビュー後、同じ候補を正本とlockへ原子的に反映
PYTHONPATH=. python scripts/update_poetore_trade_data.py --apply
```

`--refresh`と`--apply`を同時実行する設計にはしない。確認した候補と反映対象が同一であることを
候補manifestのSHA-256で保証し、レビュー中に上流が変化しても別内容を反映しない。

## 更新時の標準手順

### 事前準備

1. 作業ブランチがcleanであることを確認する
2. 現行のsource lockと配布データのhashを記録する
3. 上流障害と区別するため、日英公式Trade APIへ疎通確認する

### Dry-run

1. `--refresh`で候補を取得・生成する
2. Markdownレポートの先頭要約を確認する
3. 新アイテム、新Stat、削除、日英欠落、pseudo差分を確認する
4. `BLOCKED`の場合は正本を変更せず原因を調査する

### レビュー

1. 新規・変更項目がリーグ告知と整合するか確認する
2. 削除項目が本当に廃止されたか確認する
3. 日英名称とoption IDの対応を確認する
4. 未解決項目はfixture候補へ回し、推測で確定しない
5. 候補データを使った全テスト結果を確認する

### Apply

1. レビューした候補manifestを指定して`--apply`する
2. 配布データとsource lockを原子的に更新する
3. 変更対象外ファイルに差分がないことを確認する
4. 更新レポートをレビュー記録として残す

### 公開前

1. 代表カテゴリを英語・日本語Trade APIへ実送信する
2. 日本語公式Trade画面で条件が復元されることを確認する
3. Windows実機で新アイテムをAlt+D検索する
4. 配布ZIPに派生データだけが入り、raw入力やlockが含まれないことを確認する

## 代表API確認

毎回すべてのアイテムを検索するのではなく、変更の影響を受けやすい代表fixtureを使う。

- 通常Rare装備: explicit、pseudo、Tier、Prefix／Suffix
- Unique: 名前、ベース、可変Mod、固定Mod
- Gem: 通常、Vaal、Transfigured、Awakened
- Map: 通常Unique、Blighted、Valdo
- 特殊カテゴリ: Cluster Jewel、Logbook、Blueprint／Contract

新規カテゴリやoption変更を検出した場合は、そのカテゴリを今回限りの追加確認対象へ自動で出す。

## 実装を小分けにする順序

### Phase 1: 読み取り専用の総合監査

- 日英`items`／`stats`を取得してID単位で比較する
- 既存Modメタデータdry-runを呼び出す
- JSON／Markdownレポートを生成する
- 正本は一切変更しない

完了条件:

- 現在のlock済みデータで再実行すると同じ要約になる
- 日英の順序差だけでは変更扱いにならない
- 片側欠落とoption差分を具体的なID付きで確認できる

### Phase 2: pseudo監査と停止条件

- pseudo definitions／relationsの差分を統合する
- 参照切れ、大量削除、曖昧対応を`BLOCKED`にする
- 候補データを使って全テストを実行する

完了条件:

- 意図的に壊したfixtureで正本を変更せず停止する
- 追加・削除・変更がMarkdownへ読みやすく出る

### Phase 3: レビュー済み候補の原子的反映

- candidate manifestとSHA-256を保存する
- `--apply`はレビュー済みmanifestだけを受け付ける
- 複数の正本とsource lockを失敗時に巻き戻す

完了条件:

- 適用途中の疑似エラーでも正本が半端な状態にならない
- dry-run後に上流が変わっても未レビュー内容を反映しない

### Phase 4: 代表Trade API確認

- 代表fixtureから日英クエリを生成する
- HTTP受理だけでなく、送信したfilter ID／optionを検査する
- ネットワーク失敗とデータ不整合を別の結果として表示する

完了条件:

- 新リーグ開始時に、更新・差分確認・反映・代表確認を一つの手順で完了できる

## 非目標

- 新アイテム固有UIを自動生成する
- 未知の日本語名やMod対応をAIや類似文字列だけで確定する
- 公式Trade、Awakened、RePoEのrawデータを配布ZIPへ同梱する
- 上流の変更をレビューなしで自動公開する
- 新リーグ開始時刻に自動でGitHubへpush／Releaseする

## 実装開始前に再確認すること

- 公式Trade APIの利用条件やendpointに変更がないか
- Awakenedの参照commitとライセンス表記
- RePoEの配布条件とendpoint
- 現在の公式Trade response schema
- 新リーグ固有カテゴリが追加されていないか
- GitHub公開やReleaseは別途、鰤さんの明示確認後に行う
