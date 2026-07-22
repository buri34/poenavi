# ぽえとれ 残タスク一覧

更新日: 2026-07-21  
開発ブランチ: `feature/poetore-spike`  
比較基準: Awakened PoE Trade `fa31bfb`

## この文書の扱い

この文書を、2026-07-21時点のぽえとれ残タスクの正本とする。
過去の監査文書や`tasks/todo.md`に残る古い未チェック項目より、本書を優先する。

## P0: カテゴリ別UIの再設計

価格検索ロジックは主要カテゴリで実装済みだが、Awakenedを参考にしたカテゴリ別レイアウトは
武器パターンの初版だけが完了している。色はぽえなびの黒＋黄緑を共通テーマとする。

- [x] 武器
- [ ] 防具・盾
  - Armour、Evasion、ES、Ward、Block、base percentileを必要なものだけ表示する
  - ハイブリッド防具では実在する防御値をすべて表示する
- [ ] アクセサリー・通常装備
  - Life、耐性、能力値、Anointment、Veiled等を整理する
- [ ] Jewel／Abyss Jewel／Cluster Jewel
  - Magic完全一致、Corrupted、Passive数、item level帯を専用配置する
- [ ] Gem
  - Gem Level、Quality、Corrupted、通常／Vaal／Awakened／Transfiguredを専用配置する
- [ ] Flask／Tincture
  - Quality、Enchant、Charge Recovery、専用Modを整理する
- [ ] Map／Invitation
  - Tier、Blighted、Quantity系、危険Mod、Completion Rewardを専用配置する
- [ ] Heist Contract／Blueprint
  - Area Level、Job Level、公開Wing数、Targetを専用配置する
- [ ] Expedition Logbook
  - Area Level帯、Faction、エリア別条件を専用配置する
- [ ] Captured Beast・名前完全一致品
  - 不要なMod領域を出さず、同一種類検索であることを明示する
- [ ] その他の専用検索品
  - Memory Line、Sanctum Relic、Charm、Idol、Chronicle of Atzoatl、Mirrored Tablet、Forbidden Tome
- [ ] Currency／Divination Card／Stack品
  - 通常Web Trade検索だけを使う簡潔なUIにする
  - 旧Bulk Exchangeは実装しない

### 共通UIで残る作業

- [ ] 武器初版を基準に、全カテゴリ共通となるヘッダー・取引条件・検索ボタン・結果欄を確定する
- [ ] カテゴリを切り替えても、不要な条件や前アイテムの選択状態が残らないことを確認する
- [ ] 「完成品／クラフトベース／専用検索」の表示規則を全カテゴリの実アイテムで確認する
- [ ] 小さい解像度・Windows表示倍率125%／150%で、縦方向の収まりとスクロールを確認する

## P0: Windows実機・配布状態での最終確認

自動テストとmacOS Qt offscreenでは確認済みだが、最新変更をまとめたWindows実機確認は未完了。

- [ ] `run_dev.bat`から最新ブランチを起動し、Alt+Dの連続検索を確認する
- [ ] スタッシュ側／インベントリ側の左右配置、PoE上端基準、マルチモニター、高DPIを確認する
- [ ] Esc、Alt+W、右上×、フォーカス喪失で閉じることを確認する
- [ ] 全プルダウン操作で誤って閉じないことを確認する
- [ ] ぽえなび本体・みになび・店売り検索を誤リサイズしないことを確認する
- [ ] 日本語公式Tradeボタンが現在の検索条件を正しく引き継ぐことを確認する
- [ ] リーグ選択、Private League、取引方式、出品期間、通貨条件、キャッシュ表示を確認する
- [ ] 代表アイテムを横断確認する
  - Rare/Magic/Normal装備、Unique、Jewel、Gem、Map、Heist、Flask、Captured Beast
- [ ] 直近修正の実物確認を行う
  - Affix付きMagic品の英語ベース抽出
  - 通常コピー側レアリティの保持
  - Gem本体レベルの使用
  - 用語説明・Jewelソケット説明の除外
  - 専用Exactの「専用検索」表示
- [ ] Windows配布ZIPを生成し、同梱データ・起動・Alt+Dを最終確認する

## P1: データ保守性・監査の仕上げ

- [ ] pseudo定義本体を`trade.py`内の個別定義からレビュー可能な派生データへ移す
  - `group/replaces`の19関係とSHA-256固定は実装済み
  - `_SIMPLE_PSEUDOS`等の寄与ref・対象カテゴリを同じ生成物へ統合する
- [ ] pseudo派生データ生成時に、重複ref・循環`replaces`・存在しないstat IDを拒否する
- [ ] pseudo更新時に追加・削除・変更件数をレポートする
- [ ] `docs/poetore-pseudo-mod-tasks.md`を実装済み状況へ整理し、古い未チェック項目を解消する
- [ ] Filled Coffin固有のNecropolis Modが現行製品スコープに必要か確認し、必要ならfixtureと専用検索を追加する
- [ ] 新規リーグや公式Tradeデータ更新時の、名称・Mod・option差分更新手順を最終確認する

## P2: 任意の使い勝手向上（未決定）

次は不足機能ではあるが、鰤さんともじゃこで採用をまだ決めていない。

- [ ] オンライン状態フィルターの細分化
- [ ] 販売者情報の詳細表示
- [ ] 重複出品の集約方法をアプリ側／API側で切り替える機能
- [ ] 価格結果UIの追加改善
  - 出品行の情報量、中央値の見せ方、エラー・rate-limit・キャッシュ表示の整理
- [ ] 白ソケット数の検索チップ
  - 白ソケットを読み取ったアイテムだけ表示する
  - 読み取った個数を最小値として初期ONにし、編集・ON/OFFを可能にする
  - Awakened準拠候補だが、現時点では実装を見送る

## 統合・公開前に必要な作業

- [ ] `feature/poetore-spike`と最新`main`の差分を確認し、安全に同期する
- [ ] README、スクリーンショット、利用方法、非公式ツール表記を最新UIへ合わせる
- [ ] 全pytest、compileall、Windows配布ビルド、成果物検証を実行する
- [ ] 公開するバージョンとリリース範囲を決める
- [ ] ユーザーの明示確認後にのみGitHubへpush／PR／Releaseする

## 意図的に実装しないもの

以下は未着手タスクではなく、製品判断による対象外。

- 公式Web Tradeの旧Bulk Exchangeと独自交換UI
- Bulk用stack size／stock filter
- Metamorph Sample
- Sentinel
- Voidstone
- Charged Compass

## 現在の到達点

- Awakenedギャップ監査で確認した主要な検索ロジックは、上記対象外を除いて実装済み
- 専用Exact条件は実装済みで、UI上も「専用検索」と表示
- 直近の自動検証: `370 passed + 22 subtests`、compileall、Qt offscreen成功
- 最新ローカルコミット: `9132ba1`
- GitHubには未push
