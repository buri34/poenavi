# ぽえとれ 開発再開メモ

最終更新: 2026-07-20

## 目標

Awakened PoE Tradeの判断精度を、日本語PoE向けに最大限再現する。
Awakened / RePoE / 日本語公式Trade APIを参考情報源とし、ぽえとれ独自の
スキーマと実装を維持する。

## 再開地点

- worktree: `/Volumes/Android共有用/poenavi-dev-poetore`
- branch: `feature/poetore-spike`
- GitHub: 未push。手順11・12のコミット後は `origin/main` より34コミット先行、
  READMEのリモート更新1コミット分は内容反映済みだが履歴上behind 1
- 手順1〜6完了コミット: `a9e19aa`
- Corrupted / Split条件改善コミット: `55ae6ae`
- 手順7「pseudo Modを拡充」: 完了
- 手順8「ユニークとExact検索を強化」: 完了
- 手順9「UIへ段階的に統合」: 完了
- 手順10「実アイテムで横断検証」: 完了
- 手順11「データ更新の仕組み」: 完了
- 手順12「配布・権利・セキュリティ監査」: 自動監査完了、Windows最終確認待ち
- 手順7完了コミット: `56e688c`
- 手順8完了コミット: `2e4d598`
- 再開する作業: **手順11・12のWindows実機／配布成果物最終確認**

## 完了済み: 手順1〜6

1. 現在版と代表検索JSONを回帰基準として固定
2. Mod共通マスター、Tier、日本語matcher、解析結果の独自スキーマを実装
3. Awakened、RePoE、日本語公式Trade APIの生成パイプラインを実装
4. RePoEを必要最小限の派生インデックスへ縮小
5. 日本語Mod解析を共通ref / stat ID / 一致確度付き基盤へ切り替え
6. better / inverted / exact / 可変幅によるAwakened準拠の数値判定を実装

詳細は `docs/poetore-metadata.md`、生成物は
`data/poetore/mod_metadata.json`、生成器は
`scripts/build_poetore_metadata.py` を参照する。

## 完了済み: 手順7 pseudo Modを拡充

利用頻度の高いものから実装する。

- 個別・合計元素耐性
- 能力値・全能力
- ライフ・マナ・ES
- 攻撃速度・キャストスピード
- スペルダメージ
- 属性別ダメージ
- クリティカル率・倍率
- 移動速度
- 自動回復・リーチ

同時に、個別Modとの二重表示と、意味が近いpseudo同士の重複を整理する。
主要pseudoのメタデータ駆動化と重複排除を実装済み。

### 手順7の検証結果

- 日本語Modから対象pseudoを生成し、複数Modを正しい値で集約
- 集約済み個別Modの二重表示を除去
- 253 tests + 22 subtests、compileall、Qt offscreen smoke成功
- Mirage公式Trade APIでpseudo 3条件、100候補・10価格取得成功

## 完了済み: 手順8 ユニークとExact検索を強化

- 完璧ロールは検索値を緩和しない
- 小さいほど良いModは最大値条件、`better=0`は完全一致条件にする
- 未鑑定ユニークは公式itemsデータから候補を選択する
- 同名・同ベースの通常版／Legacy等はVariant選択UIを出し、Trade APIへ
  `discriminator`を送る
- Foilは`rarity=uniquefoil`、非Foulbornは`foulborn_item=false`を送る
- Enchant、特殊Implicit、Synthesised Implicitはstat ID経路を維持する
- 詳細コピーのCrafted Prefix/Suffixを空き枠計算へ含める

検証は258 tests + 22 subtests、compileall、Qt offscreen smoke成功。
Mirage公式Trade APIでAuxium Legacy discriminator検索が受理され、検索IDを取得した。

## 残りの手順9〜12

### 手順9: UIへ段階的に統合（完了）

目的は、内部で行っているAwakened準拠の判断を、日本語ユーザーが確認・修正できる形で
表示すること。既存のチェックボックス、最小値／最大値編集、完成品／クラフトベース切替は
維持する。

実装対象:

- 検索条件ごとに次の情報を表示する
  - 日本語の検索条件名と種別（property / pseudo / explicit等）
  - 読み取った実数値
  - Trade APIへ送る最小値／最大値
  - Tier、可変範囲、Prefix／Suffix
  - 生成元（通常、Crafted、Fractured、Influence、Enchant、Implicit等）
  - 自動選択された理由（主要DPS、防御値、pseudo、T1/T2、ユニーク可変Mod等）
  - metadata一致確度
- 一致確度が低いModと未解決Modを警告表示する
- Exact、低いほど良い、符号反転、完璧ロールをUI上で判別できるようにする
- pseudoへ吸収された元Modを必要に応じて展開確認できる形を検討する
- Variant、Corrupted、Split、価格通貨などの状態条件を同じ検索条件領域へ整理する
- 画面が横に広がりすぎないよう、詳細列またはツールチップ／展開行を使う

進め方:

1. `TradeStatFilter`へ表示用メタ情報と自動選択理由を追加
2. `resolve_trade_stat_filters()`で理由と生成元を設定
3. `PoetoreWindow._populate_stat_filters()`へ列・ツールチップを追加
4. 未解決Modを別枠または警告行で表示
5. 既存の編集・再検索動作が変わらないことを回帰確認

完了条件:

- 自動判断の根拠、Tier、範囲、生成元、一致確度を日本語UIで確認できる
- 低確度／未解決Modを見落とさない
- ユーザー編集値が再検索JSONへ正しく反映される
- 代表アイテムのQt UIテスト、全体テスト、offscreen smokeが成功する

実装結果:

- `TradeStatFilter`へ読取値、Tier、範囲、Affix、生成元、自動選択理由、Exact、betterを追加
- 検索条件UIへ「判断・詳細」列と同内容のツールチップを追加
- Property / pseudo / T1/T2 / ユニーク可変Modなどの自動選択理由を日本語表示
- Prefix / Suffix、Influence、Fractured、Crafted等の生成元を表示
- 完全一致、低いほど良い、API符号反転、一致確度を表示
- pseudoが単一Mod由来なら元ModのTier・範囲を引き継ぎ、複数なら「複数Mod集約」と表示
- 未解決Modを警告し、検索時に公式API照合を試すことを明示
- ユーザーが最小／最大／チェックを編集しても表示メタ情報を保持
- 261 tests + 22 subtests、compileall、Qt offscreen実アイテム表示スモーク成功

### 手順10: 実アイテムで横断検証（完了）

目的は、公式Tradeサイトとぽえとれで同じ条件・候補範囲になるかを実データで比較し、
アルゴリズム上の不足と日本語matcher不足を切り分けること。

検証マトリクス:

- 武器: 物理、属性、物理＋属性、DPS非重視スペル武器
- 防具: Armour / Evasion / ES / Ward、単一・ハイブリッド
- 装飾品: 指輪、アミュレット、ベルト、元素／混沌耐性、能力値、ライフ
- ユニーク: 固定値、可変値3個以下／4個以上、完璧ロール、低いほど良い
- 特殊状態: Fractured、Influence、二重Influence、Synthesised、Enchant
- 状態条件: Corrupted、Mirrored、Split、Foil、Foulborn、未鑑定、Legacy Variant
- Mod構造: 複数行、複数数値、Crafted、空きPrefix／Suffix

各ケースで記録するもの:

- 日本語通常コピーと詳細コピー
- 解析結果と自動選択理由
- ぽえとれが生成した検索JSON
- 公式Tradeサイトで手入力した検索JSONまたは検索URL
- 候補件数と、差分が出た場合の原因

完了条件:

- 各カテゴリの代表ケースを回帰fixtureとして保存する
- 意図しない検索条件差分を解消する
- 意図的なAwakened差分は文書化する
- 未対応ケースは推測値で埋めず、明示的な警告か未対応一覧へ残す
- 全ケースで公式APIが検索JSONを受理する

実装・検証結果:

- `tests/fixtures/poetore/step10_cases.json`へ12カテゴリの日本語詳細コピーと期待条件を保存
- `tests/test_poetore_cross_validation.py`で原文→解析→自動選択→検索JSONを一体検証
- 既存回帰テストと合わせ、ユニーク4可変Mod、完璧ロール、低いほど良い、Legacy、
  Foulborn、未鑑定、複数行、Synthesised等を横断確認
- 本体と同じ公式Trade API経路で12/12件の検索JSONが受理され、検索ID発行に成功
- 検証範囲、Awakenedとの差分、未対応範囲を`docs/poetore-step10-validation.md`へ記録

### 手順11: データ更新の仕組みを作る

目的は、PoEリーグ更新やTrade stat変更へ安全に追従し、データ更新だけで解析が突然壊れる
ことを防ぐこと。

実装対象:

- `scripts/build_poetore_metadata.py`の入力バージョン／commit／SHA-256を固定・表示
- 現行インデックスと新生成物の差分レポートを出す
  - 新規／削除／変更されたref・stat ID・日本語matcher
  - better / inverted / exact / localの変更
  - Tier範囲、必要ilvl、生成種別の変更
- 曖昧matcherと未解決日本語Modの一覧を生成する
- 件数、ファイルサイズ、重複stat ID、空matcher等の整合性検査を追加する
- 一時ファイルへ生成し、テスト成功後だけ正本を置き換える
- 更新前後の検索fixture差分を自動検査する

完了条件:

- 同じ入力から再現可能な派生インデックスを生成できる
- 意図しない大量削除・対応崩れを検知して更新を中止できる
- 差分レビューと全テストを通さない限り正本を更新しない
- RePoE元JSONを配布物へ混入させない
- 更新手順を`docs/poetore-metadata.md`へ記載する

実装結果:

- Awakened commit、各入力version／SHA-256をsource lockで固定
- 新規／削除／変更、Tier／ルール／matcher差分、曖昧・未解決一覧をJSONレポート化
- 重複、空matcher、件数、サイズ、大量削除を検査
- 候補インデックスを使った全テスト成功後だけ、正本とlockを原子的に置換
- 更新後の日本語公式statで対象9,270件の追加・削除・変更が0件と確認
- 詳細な更新手順を`docs/poetore-metadata.md`へ記載

### 手順12: 配布・権利・セキュリティの最終監査

目的は、試作機能を一般配布可能な状態へ整え、ライセンス・GGG方針・データ容量・秘密情報・
既存PoENaviへの影響を確認すること。この手順を終えるまではGitHubへpush／PRしない。

監査項目:

- RePoEの元JSONや不要な全データが成果物へ入っていないこと
- `data/poetore/mod_metadata.json`が必要最小限の派生データであること
- RePoE MIT、Awakened PoE Trade MIT、GGGの権利・出典表記
- 無料・非公式ツールであり、GGGの提携・承認製品ではない旨の表示
- API利用頻度、User-Agent、rate limit、エラー時バックオフを確認する
- ログへ認証情報、個人情報、不要なクリップボード全文を残さない
- PoENavi通常起動、更新機能、既存ガイド／みになびへ影響しないこと
- 配布ZIP／EXEへ不要な開発データ、キャッシュ、テストfixtureを含めないこと
- `THIRD_PARTY_NOTICES.md`、README、アプリ内表記を一致させる

最終検証:

- 全自動テスト、compileall、Qt UI、Windows実機
- 公式Trade APIで代表検索
- 配布成果物の内容・サイズ・機密情報スキャン
- `references/github-security-checks.md`に従うpush前チェック

完了条件:

- 権利表記・データ境界・API運用・配布物監査に未解決事項がない
- Windows実機でAlt+Dから検索・条件編集・再検索まで成功する
- 鰤さんが公開範囲とpush／PRを明示承認する
- 承認後にのみGitHub push／PRへ進む

自動監査・実装結果:

- 配布対象、権利表記、API運用、ログ、秘密情報、通常機能の回帰を監査
- 配布ZIPへLICENSE／README／THIRD_PARTY_NOTICESを同梱
- ZIPへ開発データ・元JSON・候補ファイルが混入した場合にビルドを停止
- API 429時にRetry-Afterへ従う1回再試行を追加
- ぽえとれ画面へ無料・非公式・GGG非提携／非承認を表示
- 詳細は`docs/poetore-release-audit.md`。WindowsでのZIP生成とAlt+D実機確認のみ残る

## 直近の仕様判断

- 未コラプト品の初期値は「未コラプトのみ」: `corrupted=false`
- コラプト品は「コラプト品含む」: `corrupted` 条件を省略
- 非スプリット品の初期値は「非スプリットのみ」: `split=false`
- スプリット済み品は「スプリット品含む」: `split` 条件を省略
- 同じアイテムの再検索ではユーザー選択を保持する
- 完成品とクラフトベース、ハイブリッド防具の全防御値選択など既存仕様を維持する

## 検証済み状態

2026-07-20 手順11・12自動監査完了時点:

- `284 passed, 22 subtests passed`
- 12/12の代表検索JSONを公式Trade APIが受理
- `python -m compileall` 成功
- Qt offscreen smoke 成功
- worktreeはclean

再開時は最初に次を確認する。

```bash
git status --short --branch
git log --oneline -5
PYTHONPATH=. QT_QPA_PLATFORM=offscreen uv run --python 3.12 \
  --with pytest --with-requirements requirements.txt -- pytest -q
```

## 運用上の境界

- SMB worktreeを正本として更新する
- ローカルcommitは実行してよい
- GitHubへのpush、PR、mergeは鰤さんの明示確認後に行う
- RePoEの元データ全体をアプリへ同梱しない
- 未確認値を正本データへ推測で書かない
