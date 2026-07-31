# Awakened価格チェック機能 最終ギャップ監査

監査日: 2026-07-31
比較対象: Awakened PoE Trade `3c8e0320ab3ea22d6dccc6cad48b5efaf94d1fe2`

## 結論

ぽえとれは、通常装備、ユニーク、Gem、Map、Heist、Expedition等の主要な価格チェックを
Awakened相当まで実装済み。意図的に対象外とした旧Bulk Exchange、残タスク化したpseudo、
低頻度の特殊アイテムと検索画面の補助機能を除き、監査で確認した主要差分は解消している。

専用Exactプリセットのカテゴリ別・初期ON/OFF監査は
`docs/poetore-exact-preset-audit.md`を正本とする。
値の境界、プリセット別の初期ON/OFF、ぽえとれ独自仕様まで含む規則単位の比較は
`docs/poetore-awakened-filter-rule-audit.csv`を正本とし、解説は
`docs/poetore-awakened-filter-rule-audit.md`を参照する。
今後のUI再設計、実機検証、保守性改善を含む残タスクは
`docs/poetore-pending-tasks.md`を正本とする。

判定基準:

- 実装済み: parser、検索条件生成、UI編集、回帰テストが揃う
- 部分対応: 基本検索または一部条件は動くが、Awakened固有ルールや専用UIが欠ける
- 未対応: 種別認識、専用条件、検索経路のいずれかがない

## カテゴリ別一覧

### 1. 起動・検索・結果表示 — 実装済み

- Alt+Dで通常コピーと詳細コピーを取得し、日本語名と詳細情報を合成
- 現行PCリーグの自動選択、公式Trade API検索、価格順の出品取得
- インスタントのみ／インスタント＋対面／対面のみ／オフラインを含む
- 出品期間、日本語公式Trade検索URL、検索／出品取得キャッシュ
- 通貨条件（任意、Chaos、Divine、Chaos＋Divine）
- 件数、先頭出品、通貨別中央値、rate-limit表示
- 429 `Retry-After`バックオフ
- 関連素材・同系統／報酬・派生品のpoe.ninja参考価格一覧

Awakenedとの差: リーグ内オンラインの細分化、販売者情報の詳細、
アプリ側/API側の重複出品集約切替は未対応。

### 2. 通常装備の基本条件 — 実装済み

- 日本語ベースタイプ、レアリティ、ユニーク名
- 完成品／クラフトベースのプリセット
- item level、品質、ソケット、リンク
- 武器のtotal DPS／pDPS／eDPS／APS／crit（品質20%換算を含む）
- 防具のArmour／Evasion／ES／Ward（ハイブリッドを含む）
- 空きPrefix／Suffix

base percentile、block、Memory Strands、クラスタージュエルのitem level帯正規化、
Magic JewelのAdorned向けrarity／corrupted厳密条件まで対応済み。

### 3. Mod解析・数値判断 — 実装済み

- explicit／implicit／crafted／fractured／enchantとInfluence生成元
- 共通ref、公式stat ID、日本語matcher、一致確度、Tier、可変範囲
- min／max、低いほど良い、符号反転、完全一致、完璧ロール
- 複数行・複数値・同一stat合算、ローカルModの二重条件除去
- 条件のON/OFFと数値編集、判断理由・未解決警告
- option型Mod 14 stat／937候補を、公式日本語名と共通option IDで照合
- Anointment 470候補のOil構成とAwakened準拠の初期表示・選択規則
- AND／NOT／COUNT検索グループのUI編集とTrade query生成
- Veiled 20候補、Searing Exarch／Eater of Worlds状態、Eldritch等の生成元表示
- Essence由来は「エッセンス」、Infamous由来は「悪名高い」と種別欄へ表示

装備価格チェック範囲の差分は解消済み。Filled Coffin固有のNecropolis ModとImbued Gemは、
後続の特殊アイテム／Gem対応側に残る。

### 4. 主要pseudo Mod — 実装済み

実装済み:

- 元素／各属性／混沌耐性、能力値、ライフ、マナ、ES
- Attack/Cast/Movement Speed、物理／元素／属性別／Spell Damage
- Global Crit、ライフ・マナ回復、物理Attackリーチ
- 個別Modとの二重表示除去
- Spell Crit、Attack Skills限定Elemental Damage、Burning Damage
- 固定Awakened定義から抽出したgroup/replaces相互排他
- crafted Chaos Resistance単独候補の非表示、crafted/通常Modの合算
- 完成品とクラフトベースの候補分離、固定rollと初期選択規則

詳細な実装タスクは `docs/poetore-pseudo-mod-tasks.md` を参照。

### 5. ユニーク・Variant・特殊状態 — 実装済み

- 未鑑定ユニーク候補解決、Legacy discriminator選択
- 固定Mod除外、可変Mod数による初期選択、完璧／低いほど良いroll
- Corrupted、Mirrored、Split、Fractured、Synthesised
- 1～2 Influence、Foil、Foulborn
- Enchant、特殊Implicit、Synthesised Implicitのstat ID経路
- 未鑑定Watcher's Eyeのitem level固定
- Agnerod系のitem levelを75／78／80／82へ正規化

### 6. Gem — 実装済み

- 日本語名と詳細コピーの英語名を分離し、公式検索用の英語typeを保持
- 固定済みAwakened itemsから812 Gemの最大レベル・通常形・discriminatorを派生
- Gem Level、Quality、Corruptedの初期選択をAwakened準拠で判断
- Awakened／Vaal／Transfiguredを通常形とdiscriminatorで厳密検索
- Empower／Enlighten／Enhanceと覚醒版を含む最大レベル1／3／4／5／6の例外
- コラプト済み高レベルGemにImbued候補を表示

### 7. Map・Invitation・特殊マップ — 実装済み

- Map Tier、Blighted／Blight-ravaged、completion reward、map quantity／rarity／pack size
- More Maps／Scarabs／Currency／Divination Cards pseudo
- Valdo系の「死亡時にVoid」危険ModをNOT条件で除外
- Nightmare Map、foil reward、Invitationのexact検索

### 8. Heist・Expedition・特殊コンテンツ — 主要ルール実装済み

- Blueprintのarea level／revealed wingsとEnchantなし条件
- Contractのarea level／9 job level／Priceless target
- Heist Gear、Brooch、Tool、Cloak、Trinketのカテゴリ認識とMod検索
- Expedition Logbookのarea levelを1／68／73／78／81／83帯へ正規化
- Chronicle of Atzoatlのarea帯と主要Tier 3部屋
- Mirrored Tabletの低難易度Reflection除外と高価値Reflection初期選択
- Memory Strands、SanctumのResolve／Inspiration／Aureus
- Charm、Idol、Graft、Sentinelのカテゴリ認識

### 9. Currency・Card・Stack品 — 通常検索を維持

- 名前／ベースタイプによる通常Trade検索と通貨条件は可能
- Awakenedには公式Web Tradeの旧Bulk Exchange API連携がある
- ゲーム内Currency Exchangeを優先する製品判断により、旧Bulk endpointと独自交換UIは対象外
- stack size／stock filterは追加せず、個別出品の確認用途に限定する

### 10. その他のアイテム種別 — 製品スコープ整理済み

- Captured Beastは専用help文判定、英語ビースト名の完全一致検索に対応済み
- Metamorph Sample、Sentinel、Voidstone、Charged Compassは意図的に対象外

Flask／Tinctureは品質、通常Mod、Enkindling判定、Charge Recovery hybridのNOT除外に対応済み。
Cluster Jewelはitem level帯、最適Passive数、Jewel Socket Mod非表示に対応済み。

## 優先度付き残課題

専用Exactは、意図的な対象外5項目を除いてAwakened `3c8e032` のカテゴリ分岐、
条件構成、初期ON/OFFへ準拠済み。

## `fa31bfb`から`3c8e032`までの再監査

価格チェックに関係する変更をコミット単位で確認した。

- Essence／Infamous由来表示: 今回ぽえとれへ反映
- Expedition Logbook解析修正、翻訳名を含むコピー解析、Trade option仕様変更、
  3.29ゲームデータ更新: 2026-07-28のメタデータ更新・日本語詳細コピー対応で反映済み
- 白ソケット専用フィルター削除: 今回ぽえとれへ反映
- 詳細Modボタン操作不要化: ぽえとれは単一詳細コピーを直接取得するため対応済み
- Captcha後のリーグ一覧取得: Awakened内蔵WebView固有。外部ブラウザ方式の
  ぽえとれには適用しない
- Trade結果キャッシュ時間修正: ぽえとれは独自の5分キャッシュであり、
  Awakened旧6時間キャッシュ問題の影響を受けない
- アイコンのclipping修正、サイトversion、既定設定: ぽえとれ機能への移植対象外

この範囲で、Essence／Infamous表示以外に未反映だった新しい価格検索機能はない。
関連アイテム価格一覧は`3c8e032`より前から存在する既存差分で、今回あわせて実装した。

## 総合判定

- 通常装備・ユニーク・Gem・主要特殊コンテンツ: **実装済み**
- Awakenedの価格チェック全機能: **主要機能対応（意図的な対象外と残タスクあり）**
- 公開時の正確な表現: 「日本語PoE向け価格チェック。Awakened相当の主要な
  Mod判断、pseudo、ユニーク、Gem、Map、Heist等に対応」

この監査はソース比較であり、Windows実機の配布ZIP／Alt+D最終確認は別の未完了項目として残す。
