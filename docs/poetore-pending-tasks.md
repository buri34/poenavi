# ぽえとれ 残タスク正本

更新日: 2026-08-05

基準バージョン: `v3.1.1`（`2dae3fc`）

Awakened比較基準: `31b3e0e8ba0a6bac2266603c2e170925c8f02b81`（v3.29.103）

## この文書の扱い

この文書を、ぽえとれの残タスクと製品方針の正本とする。
過去の監査文書、`docs/poetore-resume.md`、workspaceや旧SMB作業コピーの
`tasks/todo.md`に残る未チェック項目より、本書を優先する。

項目は次の4区分で管理する。

- **完了**: v3.1.1までに実装・検証・公開済み
- **継続**: 実装または検証を進める残タスク
- **保留**: 外部環境、実物、採用判断が整うまで着手しない
- **対象外**: 現在の製品方針として実装しない

## 再開時の推奨順

1. Valdo Mapの報酬条件検索
2. ぽえとれの実機性能比較と残るボトルネックの改善
3. 公式Trade・Awakenedデータ更新作業の自動化
4. 通信切断・復旧の実機確認
5. 価格結果UIと特殊カテゴリの任意改善

## 継続

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

### 継続運用: 次回リリース

以下はv3.1.1では完了済み。次回バージョンごとに再実施する。

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

## 完了

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

- 2026-08-05: v2.8.2基準の旧文書をv3.1.1のコード、テスト、Git履歴、
  リリース成果物監査と照合。未チェックのまま残っていた完了項目を「完了」へ移し、
  実作業が残る項目を「継続」、環境・採用判断待ちを「保留」、意図的非対応を
  「対象外」へ分離した。
