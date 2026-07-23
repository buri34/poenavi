# ぽえとれ 残タスク一覧

更新日: 2026-07-24
開発ブランチ: `feature/poetore-spike`  
比較基準: Awakened PoE Trade `fa31bfb`

## この文書の扱い

この文書を、2026-07-22時点のぽえとれ残タスクの正本とする。
過去の監査文書や`tasks/todo.md`に残る古い未チェック項目より、本書を優先する。

## 再開時の推奨順

1. **高優先度: ユニーク可変Modのドラッグ式レンジ調整**
2. **高優先度: 未鑑定ユニークの画像付き候補カード**
3. Windows実機確認（初版公開前確認は完了）
4. Valdo Mapの報酬検索を実物で再調査・修正
5. Filled Coffin・公式Tradeデータ更新手順の確認
6. README・配布ビルド・公開準備

共通UI、検索チップ、Trade結果表、poe.ninja参考価格欄は初版が完成しているため、
次回は共通部分を作り直さずカテゴリ専用UIへ進む。

## P0: カテゴリ別UIの再設計

価格検索ロジックは主要カテゴリで実装済みだが、Awakenedを参考にしたカテゴリ別レイアウトは
武器パターンの初版だけが完了している。色はぽえなびの黒＋黄緑を共通テーマとする。

カテゴリ別の表示順・初期状態・プリセット差は、
`docs/poetore-awakened-ui-and-poeninja-audit.md`の監査結果を基準とする。

- [x] 武器
- [x] 防具・盾
  - 完成品は`Block → Armour → Evasion → ES → Ward`の順で実在値だけ表示し、初期ONにする
  - ハイブリッド防具では実在する防御値をすべて表示する
  - ベースアイテムは実防御値を初期OFF、ilvl・base percentileを初期ONにする
  - base percentileは上段の編集・ON/OFF可能な`ベース防御値`チップへ集約する
  - 品質20は初期OFF、21以上は初期ON、Influenceはベースアイテムで初期ONにする
- [x] アクセサリー・通常装備
  - Life、耐性、能力値、Anointment、Veiled等を整理する
- [x] Jewel／Abyss Jewel／Cluster Jewel
  - Magic完全一致、Corrupted、Passive数、item level帯を専用配置する
- [x] Gem
  - Gem Level、Quality、Corrupted、通常／Vaal／Awakened／Transfiguredを専用配置する
- [x] Flask／Tincture
  - Quality、Enchant、Charge Recovery、専用Modを整理する
- [x] Map／Invitation
  - Tier、Blighted、Quantity系、危険Mod、Completion Rewardを専用配置する
- [x] Heist Contract／Blueprint
  - Area Level、Job Level、公開Wing数、Targetを専用配置する
- [x] Expedition Logbook
  - Area Level帯、Faction、エリア別条件を専用配置する
- [x] Captured Beast・名前完全一致品
  - 不要なMod領域を出さず、同一種類検索であることを明示する
- [x] その他の専用検索品
  - Memory Line、Sanctum Relic、Charm、Idol、Chronicle of Atzoatl、Mirrored Tablet、Forbidden Tome
- [x] Currency／Divination Card／Stack品
  - 通常Web Trade検索だけを使う簡潔なUIにする
  - 旧Bulk Exchangeは実装しない

### 共通UIで残る作業

- [ ] **高優先度: ユニーク可変Modの検索値をドラッグで調整できるUI**
  - Awakenedの`StatRollSlider`を仕様参考にし、コードはコピーせずQtで独自実装する
  - 可変幅を持つユニークMod行に、ロール下限・上限を両端へ表示した横長バーを追加する
  - 元アイテムの実ロール位置をバー上の目盛りで示し、現在検索対象となる範囲を塗りつぶして見せる
  - 初期状態が最小値検索なら、バー上のクリック／左右ドラッグで検索最小値を変更する
  - 最大値検索のModでは同じ操作で検索最大値を変更する。最小・最大の両方が入る範囲検索は数値欄を基本操作とし、誤操作を避ける
  - ドラッグ中は変更後の値をポップアップ表示し、マウスを離した時点で確定する
  - ドラッグ操作で無効だったModを自動的にONにし、既存の最小・最大入力欄とも双方向同期する
  - 値の丸めはAwakenedのstat別`dp`ルールに従い、通常整数Modは整数、小数対応Modだけ必要な小数桁を維持する
  - 可変幅のない固定Mod、比較不能Mod、選択肢型Modにはバーを表示しない
  - マウス操作、数値入力、ON/OFF、公式Tradeへ送る値の一致をWindows実機と自動テストで確認する
- [ ] **高優先度: 未鑑定ユニークの候補選択を画像付きカードUIへ変更する**
  - 初版では非対応。未鑑定ユニークを読み取った場合は鑑定後の検索を案内し、検索ボタンを無効化する
  - 現在の名前だけのプルダウンでは、未鑑定状態のユーザーが各候補の性能・見た目を判断しにくい
  - Awakened準拠で、同一ベースの候補をアイコン画像＋ユニーク名のカード一覧として表示する
  - 候補が1種類なら自動選択し、複数の場合だけカード選択画面を表示する
  - Legacy等の同名Variantを候補内でどう扱うかも実装時に確認する
- [x] 武器初版を基準に、全カテゴリ共通となるヘッダー・取引条件・検索ボタン・結果欄を確定する
  - 検索チップを固定順の共通登録へ集約し、表示中チップを横幅に応じて自動折り返しする
  - 情報階層を`アイテム名／検索範囲 → poe.ninja参考価格欄 → 検索チップ → プリセット → Mod条件`へ統一する
  - poe.ninja参考価格、7日推移、外部リンクを対応カテゴリだけ表示する
  - Influenceチップはアイコン付き。チェックを持たない状態チップも、現在の検索方針として常に有効色で表示する
  - Mod一覧からAND／NOT／COUNTの手動選択列を削除する。通常ModはAND、Valdo除外等のNOT／COUNTは内部設定を維持する
  - Mod一覧へ表示専用の`ティア`列を追加し、取得できた武器・防具・装飾品等のMod Tierを表示する
  - `mod条件をたたむ／ひらく`ボタンでMod一覧を折りたたみ、入力値と選択状態は保持する
  - Trade結果表は基本列を`価格｜出品日時`とし、条件に応じて在庫／ilvl／ジェムLv／品質を追加する
  - リーグ選択をタイトルバーへ移し、明示的な`▼`ボタンを表示する。Alt+D直後には入力フォーカスを当てない
- [x] カテゴリを切り替えても、不要な条件や前アイテムの選択状態が残らないことを確認する
- [x] 「完成品／クラフトベース／専用検索」の表示規則を全カテゴリの実アイテムで確認する
- Windows表示倍率・小解像度テストは、利用優先度が低いため2026-07-23に製品確認対象外とした

## P0: Windows実機・配布状態での最終確認

自動テストとmacOS Qt offscreenでは確認済みだが、最新変更をまとめたWindows実機確認は未完了。

- [x] `run_dev.bat`から最新ブランチを起動し、Alt+Dの連続検索を確認する
- [x] スタッシュ側／インベントリ側の左右配置、PoE上端基準、マルチモニターを確認する
- [x] Esc、Alt+W、右上×、画面外クリックで閉じることを確認する
- [x] 全プルダウン操作で誤って閉じないことを確認する
- [x] ぽえなび本体・みになび・店売り検索を誤リサイズしないことを確認する
- [x] 日本語公式Tradeボタンが現在の検索条件を正しく引き継ぐことを確認する
  - Windows受け入れCSVのWIN-041〜045で、装備、Jewel/Gem、Map/Heist、Flask/Tincture、名前一致/特殊の5群を簡易確認する
- [x] 取引方式、出品期間、通貨条件、キャッシュ表示を確認する
  - 公開リーグ切替とPrivate Leagueは利用可能な環境が整った時点で再確認する
- [x] 代表アイテムを横断確認する
  - Rare/Magic/Normal装備、Unique、Jewel、Gem、Map、Heist、Flask、Captured Beast
- [x] 直近修正の実物確認を行う
  - Affix付きMagic品の英語ベース抽出
  - 通常コピー側レアリティの保持
  - Gem本体レベルの使用
  - 用語説明・Jewelソケット説明の除外
  - 専用Exactの「専用検索」表示
  - Map Tier／Blighted状態／Veiled種別検索
  - Foulborn Unique Modの解析と「ファウルボーン」種別表示
  - poe.ninja価格・7日変動率・リンク
  - 状態チップの有効色と、Mod論理列削除後の検索結果
- [x] Windows配布ZIPを生成し、同梱データ・起動・Alt+Dを最終確認する

## P1: データ保守性・監査の仕上げ

- [x] 区画構造優先パーサーと回帰fixtureを整備する
  - 通常コピー／詳細コピー54件をfixture化し、説明文・使用方法・フレーバーテキストをModへ混ぜないことを自動検証済み
  - Mirrored／Split／Synthesised／Corrupted等の状態判定は既存fixtureを含めて対応済み
  - 新しいアイテム種別で末尾説明がModに混入した場合は、通常／詳細コピー対をfixtureへ追加して区画判定を拡張する
- [x] Valdo Map固有ModのTrade stat対応を追加する
  - 区画構造パーサーによる抽出は完了している
  - 今回の実サンプルでは固有Mod 8件が未解決だったが、この8件だけを個別対応するタスクではない
  - 公式Tradeデータに存在するValdo固有Mod全体について、日英表記からstat IDへ汎用的に解決できる派生データと回帰テストを整備する
  - 未知のValdo Modは誤ったstatへ寄せず未解決として扱い、公式データ更新時に差分を検出できるようにする
  - Awakened準拠ではCompletion Reward完全一致、Foil、実Modを検索し、元アイテムにVoid死亡Modがない場合は同ModをNOT条件で除外する
- [ ] **Valdo Mapの報酬検索を実物で再調査・修正する**
  - 初版では報酬条件を検索へ送らず、「報酬条件検索は非対応・報酬を除いて検索」と画面に明示する
  - 現状、報酬名・Foil条件・日英Trade名の変換処理はあるが、Windows実機では報酬条件を使った検索がまだ正常に成立しない
  - 対応が複雑なため、ほかの検索テストを優先して一旦保留する
  - 再開時は実際のValdo Map詳細コピー、ぽえとれ内部クエリ、日本語公式Tradeへ渡すクエリを比較し、報酬option ID・type・discriminator・Foil条件を再確認する
  - 自動テストのAPI受理だけで完了とせず、Windows実機で報酬条件がTrade画面へ正しく復元されるところまで確認する
- [x] Inscribed UltimatumはAwakened準拠の名前完全一致検索に留める
  - 供物・報酬・クリア条件・試練Mod・Area Levelは検索条件へ変換しない
  - UIへチャレンジタイプ・報酬種類・必要なアイテム・報酬などの条件検索が非対応であることを明示する
- [x] pseudo定義本体を`trade.py`内の個別定義からレビュー可能な派生データへ移す
  - `group/replaces`の19関係とSHA-256固定は実装済み
  - `_SIMPLE_PSEUDOS`等の寄与ref・対象カテゴリを同じ生成物へ統合する
- [x] pseudo派生データ生成時に、重複ref・循環`replaces`・存在しないstat IDを拒否する
- [x] pseudo更新時に追加・削除・変更件数をレポートする
- [x] `docs/poetore-pseudo-mod-tasks.md`を実装済み状況へ整理し、古い未チェック項目を解消する
- [ ] Filled Coffin固有のNecropolis Modが現行製品スコープに必要か確認し、必要ならfixtureと専用検索を追加する
- [ ] 新規リーグや公式Tradeデータ更新時の、名称・Mod・option差分更新手順を最終確認する

## P2: 任意の使い勝手向上

次は不足機能ではあるが、鰤さんともじゃこで採用をまだ決めていない。

- [x] **poe.ninja参考価格＋7日推移チャート**
  - 実装可能性・対応カテゴリ・取得間隔・照合キーを監査済み
  - Trade検索結果とは別の参考相場として、価格・7点スパークライン・poe.ninjaリンクを表示する
  - dense overviewをリーグ単位で遅延取得し、30～31分キャッシュする
  - 初版はUnique、Gem、Map、名前一致交換品を対象とする
  - 非ユニークBaseTypeは参考価値が低いため対象外
  - Cluster Jewelは`Enchant効果＋パッシブ数＋ilvl帯`で集計されるが、日本語コピーから英語集計キーへの照合をまだ高信頼度で保証できないため対象外。誤価格を避け、照合精度改善後に再検討する
  - 31分メモリキャッシュ、Private League除外、通信失敗時の非表示、7日スパークライン、poe.ninjaリンクを実装済み
  - 詳細は`docs/poetore-awakened-ui-and-poeninja-audit.md`を参照

- [ ] オンライン状態フィルターの細分化
- [ ] 販売者情報の詳細表示
- [ ] 重複出品の集約方法をアプリ側／API側で切り替える機能
- [ ] 価格結果UIの追加改善
  - 出品行の情報量、中央値の見せ方、エラー・rate-limit・キャッシュ表示の整理
  - 同一出品者・同一価格の重複出品を`×3`等で集約する
  - スタック品では同一出品者の在庫数を合算する
  - 値段未設定／スタッシュ由来の価格を専用アイコンで区別する
  - 自分の出品を`You`等で識別する
  - 初回20件を取得し、不足時だけ最大100件まで段階的に追加取得する
  - 検索一致件数・オンライン条件・公式Tradeリンクは既に実装済みのため維持する
- [ ] **Cluster Jewelのpoe.ninja参考価格照合（優先度高め）**
  - poe.ninjaは`Enchant効果＋パッシブ数＋ilvl帯`でCluster Jewelを集計している
  - 現状は日本語Enchantから英語集計キーへの照合精度を保証できず、誤価格防止のため価格欄を表示しない
  - 日英Enchantを公式ID等で高信頼度に対応付け、パッシブ数・ilvl帯も一致できた場合だけ対象へ追加する
- [ ] 白ソケット数の検索チップ
  - 白ソケットを読み取ったアイテムだけ表示する
  - 読み取った個数を最小値として初期ONにし、編集・ON/OFFを可能にする
  - Awakened準拠候補だが、現時点では実装を見送る
- [ ] ジェムVariantの読み取り専用チップ
  - Transfigured／Vaal／Awakened等のVariant判定結果を上段へ表示する
  - Trade API用discriminator・通常版との対応付けは実装済み
  - 検索条件のON/OFFではなく、現在適用中のVariantを明示する用途とする
  - 現時点では専用チップUIの実装を見送る
- [ ] 選択Mod数・折りたたみチップ
  - `選択中Mod数 / 全Mod数`を上段へ表示する
  - チップ操作でMod条件一覧を展開／折りたたみする
  - 検索条件そのものではなく、選択状況の確認とMod欄操作を兼ねる
  - 現時点では実装を見送る

## 統合・公開前に必要な作業

- [x] `feature/poetore-spike`とv2.5.4の`main`を確認し、安全に同期する
- [x] README、利用方法、非公式ツール表記を初版UIへ合わせる
- [x] 全pytest、compileall、Windows配布ビルド、成果物検証を実行する
- [x] 公開バージョンをv2.6.0とし、ぽえとれ初版を正式リリース対象にする
- [ ] ユーザーの明示確認後にのみGitHubへpush／PR／Releaseする

## 意図的に実装しないもの

以下は未着手タスクではなく、製品判断による対象外。

- 公式Web Tradeの旧Bulk Exchangeと独自交換UI
- Bulk用stack size／stock filter
- Sentinel Chargeの検索チップ
  - Sentinel専用の条件だが、ぽえとれではSentinelカテゴリ自体を製品対象外としているため実装しない
- Stock／スタック数の検索チップ
  - Currencyやスタック品向けの条件だが、ぽえとれでは旧Bulk Exchangeを対象外としている
  - 通常Web Trade検索を使う現在の方針では利用価値が低いため実装しない
- Metamorph Sample
- Sentinel
- Voidstone
- Charged Compass

## 現在の到達点

- Awakenedギャップ監査で確認した主要な検索ロジックは、上記対象外を除いて実装済み
- 専用Exact条件は実装済みで、UI上も「専用検索」と表示
- 共通検索チップ、状態制御、Trade結果表、poe.ninja参考価格UIの初版は実装済み
- 区画構造優先パーサーは通常／詳細コピー54件を回帰fixture化済み
- 直近の自動検証: `531 passed + 22 subtests`、compileall成功
- SMB共有 `/Volumes/Android共有用/poenavi/` へ同期済み
- GitHubには未push
