# ぽえとれ 残タスク正本

更新日: 2026-08-11

公開版基準: `APP_VERSION 3.2.1`

開発版基準: `feature/poe2-foundation`（`7e41a4e`）

Awakened比較基準: `1e2225af8cfe04ccc5676d00eede81d7ee071240`（2026-08-10時点master）

EE2比較基準: `d72afb83bc0888919a89d3c3744acee2c597e9c8`

## この文書の扱い

この文書を、ぽえとれの残タスクと製品方針の正本とする。
過去の監査文書、`docs/poetore-resume.md`、workspaceや旧SMB作業コピーの
`tasks/todo.md`に残る未チェック項目より、本書を優先する。

項目は次の5区分で管理する。

- **検証済み**: 開発ブランチで実装・自動テスト済みだが未公開
- **完了**: 公開版までに実装・検証・公開済み
- **継続**: 実装または検証を進める残タスク
- **保留**: 外部環境、実物、採用判断が整うまで着手しない
- **対象外**: 現在の製品方針として実装しない

## 再開時の推奨順

1. PoE2実コピーfixtureと状態条件の検索精度監査
2. Valdo Mapの報酬条件検索
3. ぽえとれの実機性能比較と残るボトルネックの改善
4. 通信切断・復旧の実機確認
5. 価格結果UIと特殊カテゴリの任意改善

## 継続

### P0: PoE2実コピーと状態条件の検索精度監査

自動テストは固定EE2 identityと公式Trade2 metadataを中心に整備済みだが、特殊カテゴリには
合成コピーfixtureも残る。日本語PoE2クライアントの実コピーと最終Trade2 JSONを正本として、
検索候補を狭めすぎないことまで確認する。

Windows実機の作業票は`docs/poetore-poe2-testing/windows-test-cases.csv`を使用する。
Requirement Levelは別途製品判断するため、この作業票の試験対象には含めない。

- [ ] Life／Mana Flask、Wombgift、Map Fragment、Pinnacle Key、Vault Key、Expedition Logbookの
      日英通常コピー／詳細コピーを収集し、Item Class、Magic名、Property区切りを固定する
- [ ] Crossbow、Spear、Flail、Focus、Buckler、Gem、Waystoneの実コピーfixtureを追加し、
      advanced Mod header、Tier、roll範囲、Mod種別を確認する
- [x] Crafted／Fractured／Desecrated条件を固定EE2と比較し、完成品では状態チップを初期OFF、
      通常Explicit版があるModは性能条件へ正規化し、特殊版しかないMod・ベース検索・変更不可品は
      元のStat種別を維持する
- [x] 実コピー待ちだったSanctified、Mirrored、Mageblood、Against the Darkness、
      Ventor's Gambleの日英5組を追加し、全28組の日英identityと最終Trade2 identityを自動検証した
- [x] Normal／Magic／Rare／Unique × 完成品／ベース × exact base／同一classについて、
      装備27カテゴリの構造母集団351ケースを作成し、有効297ケースのUI分岐と最終Trade2 JSONを
      自動監査した（仕様上対象外54、検出不具合0）
- [ ] 上記297ケースのWindows実機表示・操作を`windows-test-cases.csv`で確認する
- [x] `P2-WIN-002`で判明した個別属性PropertyのeDPS欠落を修正した。PoE2専用計算で
      `火／Fire`、`冷気／Cold`、`雷／Lightning Damage`を合算し、日本語・英語、
      単属性・複合属性、合計DPSとTrade2条件を回帰テストした

### P1: PoE2 Requirement Levelと比較監査の継続

- [ ] EE2が低レベルRareへ提示するRequirement Level条件について、実需要とTrade2件数を確認し、
      検索チップとして採用するか製品判断する
- [x] 固定EE2、最新EE2、公式Trade2 metadata、実装済みコードを再照合した。最新EE2 `dev`は
      固定revisionと同一、公式Trade2はentry順序以外の意味差分0件だった。詳細は
      `docs/poetore-poe2-upstream-delta-audit-2026-08-11.md`を参照する
- [x] Price trend、Related Items、結果Tooltip等の補助機能を再棚卸しした。Price trendは実装済み、
      結果Tooltipは未実装、結果一覧は一部実装、poeprices.infoは最新EE2でも無効のため
      parity対象外と整理した。詳細は`docs/poetore-poe2-auxiliary-features-audit-2026-08-11.md`を参照する
- [x] 固定EE2のPoE2用Related Items 115グループを専用台帳として取り込み、日英identity、
      poe.ninja PoE2カテゴリ別価格、取得不能時の安全な「—」表示を実装した
- [ ] PoE2検索結果の各出品へ、実ItemのProperty、Socket、Implicit、Explicit、Tier、状態を確認できる
      ゲーム内風Tooltipを追加する。表示はHover／Shift+Hoverを候補とし、横幅を増やさず詳細確認できる形にする
- [ ] PoE1／PoE2の検索queryへ公式TradeのAPI Collapseを追加し、検索ID取得時点から同一Sellerの
      大量出品を畳む。現行のfetch後ローカル集約は表示・安全網として維持し、取得Seller数と中央値を比較検証する
- [ ] PoE2の完成品Mod表示へ、PoE1と同じ「最終性能 → Prefix系統 → Suffix系統 → その他」の
      並び順を適用する。PoE2専用の`poe2_trade_filters()`経路で、各行へ元Modのaffix、
      pseudoの寄与元affix、元アイテム内の記載位置を引き継ぎ、各系統内は原文順を維持する。
      最大ライフ合計・最大マナ合計はPrefix系統、通常affixと暗黙等が混在するpseudoは
      Prefix、次にSuffixを優先するPoE1既存規則へ揃える

### P0: Valdo Mapの報酬条件検索

現状はValdo固有Modの解析とTrade stat解決まで対応しているが、
Completion Rewardを検索条件へ含めず、非対応であることを画面に表示している。

- [ ] 実物の詳細コピー、内部クエリ、日本語公式Tradeへ渡すクエリを並べて再調査する
- [ ] 報酬option ID、type、discriminator、Foil条件、日英名称変換を確認する
- [ ] Completion Reward完全一致、Foil、実Mod、Void死亡Mod除外をAwakened準拠で組み立てる
- [ ] API受理だけでなく、日本語公式Trade画面へ報酬条件が復元されることをWindows実機で確認する

### P1: 性能比較と軽量化

v3.0.1までに検索区間別のJSONL性能トレース、クリップボード取得短縮、
重複API呼び出しを増やさない検索高速化を実装済み。残りは比較計測と、
計測結果に基づく追加改善である。

- [ ] Awakened PoE Trade、PoE Overlay、ぽえとれで、起動・Alt+D解析・初回検索・キャッシュ検索・画面表示を同条件比較する
- [ ] Windows実機で経過時間、CPU、メモリ、ネットワーク待ちを記録する
- [ ] トレースからUIスレッド待ち、不要な再描画、重複処理、過剰なJSON走査を特定して改善する
- [ ] 改善前後を比較し、通常のPoENavi起動、タイマー、ガイド、みになびに性能劣化がないことを確認する

### P1: 通信障害からの復旧

- [ ] ネットワーク切断中のエラー表示と、復旧後にアプリ再起動なしで再検索できることをWindows実機で確認する

### P2: 価格結果UI

- [ ] 自分の出品を`You`等で識別する
- [ ] 販売者名／最終キャラクター名とオンライン・AFK状態を表示する
- [ ] エラー、rate-limit、キャッシュ、中央値の表示を整理する
- [ ] オンライン状態フィルターを細分化する

### P2: poe.ninja・検索チップ

- [ ] Cluster Jewelを日英Enchant、パッシブ数、ilvl帯まで高信頼度で対応付け、poe.ninja参考価格を表示する
- [ ] Gem Variant（Transfigured／Vaal／Awakened等）を読み取り専用チップで明示する
- [ ] PoE2ゲーム内Currency Exchange対象だがpoe.ninja `Fragments`に未収録の
      Primary／Secondary／Tertiary Calamity Fragment、Zarokh's Reliquary Key: Temporalis、
      An Audience with the King、Head of the King、Idol of Estazunti、Breachstoneについて、
      取得可能な価格APIまたは安全な代替表示を再調査する

### 継続運用: 次回リリース

以下は過去リリースで完了済み。次回バージョンごとに再実施する。

- [ ] 最新コミットからWindows配布ZIPを生成し、ZIP監査と展開後の起動を確認する
- [ ] README・更新履歴へ公開分の変更点を追加する
- [ ] `APP_VERSION`を公開バージョンへ更新する
- [ ] 全テスト、構文、JSON、機密情報、配布内容、SHA-256を検証する

## 保留

外部環境または製品判断が必要なため、条件が整うまで着手しない。

- [ ] 次期公開リーグ開始後、Standard以外への切替と実際の検索先リーグを確認する
- [ ] Private League参加環境で、対象リーグ検索とpoe.ninja欄の扱いを確認する
- [ ] Filled Coffin固有のNecropolis Modを製品対象にするか、実物需要と公式Trade仕様を見て判断する
- [ ] poeprices.infoのレア装備価格予測を製品対象にするか、精度・説明責任・障害時分離を評価して判断する

## 検証済み・未公開

`feature/poe2-foundation`で自動テストとWindows確認用ミラー同期まで完了しているが、
GitHub push／公開リリースは未実施。

- [x] PoE1／PoE2カテゴリの共通UI判定、Mod検索範囲、価格通貨、出品期間をTrade2へ接続
- [x] Gem Level／Quality／Socket、Charm Quality、Rare Item Level、nonunique条件をEE2準拠で実装
- [x] PoE2のベース名／同一class、完成品／ベース、武器DPSヘッダー要約を実装
- [x] Map Fragment 8種、Pinnacle Key 7種、Vault Key 9種をpoe.ninja `Fragments`価格へ接続
- [x] Expedition Logbook、Life／Mana Flask 18ベース、Wombgift 5種をTrade2検索へ接続

## 完了

### v3.2.0

- [x] `Ctrl+D`既定のAUTO-HIDE価格検索を追加し、Ctrl／Alt保持キーと通常キーを設定可能にする
- [x] 保持キー中の操作モード移行、解放後の距離判定、画面外移動時のPoE復帰を実装する
- [x] PoE復帰時、最小化時だけ復元し、最大化状態を維持する
- [x] 3.29追加「傭兵の召喚状」をビルド名、メインスキル、サポートスキル、Tierで検索可能にする
- [x] 傭兵のメインスキルを初期表示し、サポートスキルは専用ボタンで展開するUIへ整理する
- [x] v3.2.0のREADME、更新履歴、Windows CI、配布ZIP、SHA-256を検証して公開する

### v3.1.1までの残タスク解消

- [x] 検索結果へ「取引方式」列を追加し、対面／インスタント／値段なしを区別
- [x] 値段なし出品を中央値と安値例から除外
- [x] 同一出品者・同一価格を`×3`等で集約し、スタック在庫を合算
- [x] 初回20件を取得し、不足時だけ最大100件まで段階取得
- [x] JSONL性能トレースで、コピー、解析、metadata、Trade API、poe.ninja、画面表示を区間計測
- [x] クリップボード取得待ちを短縮し、追加API呼び出しなしで検索経路を高速化
- [x] 新規リーグ／公式Tradeデータ更新の設計を文書化
- [x] Tradeデータ総合監査・候補生成・レビュー済み候補の原子的反映を一つのコマンドへ統合
- [x] 日英Items／Stats、Modメタデータ、pseudo、Map Mod、代表Trade API確認を統合
- [x] Awakened取得不能時に公式Trade＋RePoE＋独自台帳だけで更新する経路を総合入口へ統合
- [x] Essence／Infamous由来Modを検索条件の種別へ表示
- [x] 関連アイテム価格一覧を日本語名・分類・poe.ninja参考価格付きで表示
- [x] 白ソケット数と通常ソケット数を検索条件から除外
- [x] リンク数を編集可能な検索チップへ統合し、5／6リンクだけ初期ON
- [x] 選択中Mod数／全Mod数とMod欄の展開・折りたたみを実装
- [x] pseudo Mod、group／replaces、候補優先順位をメタデータ駆動化
- [x] Awakened v3.29.103相当のStat、Gem、Unique固定Mod、関連ドロップ、Map Modへ更新
- [x] v3.1.1のREADME、更新履歴、APP_VERSION、Windowsビルド、公開ZIP、SHA-256を検証して公開

詳細な完了内容は次を参照する。

- `docs/release-notes-v3.1.0.md`
- `docs/release-notes-v3.1.1.md`
- `docs/poetore-pseudo-mod-tasks.md`
- `docs/poetore-awakened-gap-audit.md`
- `docs/poetore-release-audit.md`

## 対象外

次は未着手ではなく、現在の製品方針による対象外。

- 公式Web Tradeの旧Bulk Exchangeと独自交換UI
- Bulk用stack size／stock filter
- Sentinel Chargeの検索チップ
- Stock／スタック数の検索チップ
- Metamorph Sample
- Sentinel
- Voidstone
- Charged Compass
- Brutality Supportを含む通常Gemの初期通貨条件変更
  - 非ユニークGemを`カオスまたは神のオーブ`で検索するのはAwakened準拠の意図的仕様

## 棚卸し記録

- 2026-08-10: 公開版と`feature/poe2-foundation`の基準を分離。PoE2共通UI parity、
  特殊カテゴリのNinja／Trade2振り分けを「検証済み・未公開」へ追加した。実コピーfixture、
  状態条件、Requirement Level、カテゴリ×レアリティ総当たり、比較監査文書更新を継続へ追加。
  完了済みデータ更新作業を推奨順から除外した。

- 2026-08-08: 基準をv3.2.0へ更新。AUTO-HIDE、最大化維持、傭兵の召喚状検索と
  専用UIを完了へ追加した。継続・保留・対象外の既存項目は引き続き有効。

- 2026-08-05: v2.8.2基準の旧文書をv3.1.1のコード、テスト、Git履歴、
  リリース成果物監査と照合。未チェックのまま残っていた完了項目を「完了」へ移し、
  実作業が残る項目を「継続」、環境・採用判断待ちを「保留」、意図的非対応を
  「対象外」へ分離した。
