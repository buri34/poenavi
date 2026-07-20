# Awakened価格チェック機能 最終ギャップ監査

監査日: 2026-07-21  
比較対象: Awakened PoE Trade `fa31bfbbe99e04e386b4af2d71d633e2b6823c0f`

## 結論

ぽえとれは、通常の武器・防具・装飾品とユニークを価格チェックする中核経路は
Awakened相当まで実装済み。一方、Awakenedが個別ルールを持つ特殊アイテム群は
広く未対応であり、「全アイテム種別まで含めてAwakened同等」とはいえない。

判定基準:

- 実装済み: parser、検索条件生成、UI編集、回帰テストが揃う
- 部分対応: 基本検索または一部条件は動くが、Awakened固有ルールや専用UIが欠ける
- 未対応: 種別認識、専用条件、検索経路のいずれかがない

## カテゴリ別一覧

### 1. 起動・検索・結果表示 — 実装済み

- Alt+Dで通常コピーと詳細コピーを取得し、日本語名と詳細情報を合成
- 現行PCリーグの自動選択、公式Trade API検索、価格順の出品取得
- インスタントのみ／インスタント＋対面／対面のみ
- 通貨条件（任意、Chaos、Divine、Chaos＋Divine）
- 件数、先頭出品、通貨別中央値、rate-limit表示
- 429 `Retry-After`バックオフ

Awakenedとの差: オフライン・リーグ内オンライン・出品期間・販売者情報・検索URL、
アプリ側/API側の重複出品集約切替、結果キャッシュは未対応。

### 2. 通常装備の基本条件 — 実装済み

- 日本語ベースタイプ、レアリティ、ユニーク名
- 完成品／クラフトベースのプリセット
- item level、品質、ソケット、リンク、白ソケット
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

装備価格チェック範囲の差分は解消済み。Filled Coffin固有のNecropolis ModとImbued Gemは、
後続の特殊アイテム／Gem対応側に残る。

### 4. 主要pseudo Mod — 部分対応

実装済み:

- 元素／各属性／混沌耐性、能力値、ライフ、マナ、ES
- Attack/Cast/Movement Speed、物理／元素／属性別／Spell Damage
- Global Crit、ライフ・マナ回復、物理Attackリーチ
- 個別Modとの二重表示除去

不足:

- Spell Crit pseudo
- Elemental Damage with Attack Skills
- Burning Damage
- Awakenedのgroup/replaces規則を完全再現した相互排他
- crafted chaos resistanceを価値なしとして隠す等の個別表示規則

詳細な実装タスクは `docs/poetore-pseudo-mod-tasks.md` を参照。

### 5. ユニーク・Variant・特殊状態 — 実装済み

- 未鑑定ユニーク候補解決、Legacy discriminator選択
- 固定Mod除外、可変Mod数による初期選択、完璧／低いほど良いroll
- Corrupted、Mirrored、Split、Fractured、Synthesised
- 1～2 Influence、Foil、Foulborn
- Enchant、特殊Implicit、Synthesised Implicitのstat ID経路

差分: Watcher's Eye未鑑定品のitem level固定、Agnerodのitem level帯など、
Awakenedの固有例外は未対応。

### 6. Gem — 部分対応

- 日本語名／ベース名による基本検索は可能
- Gem Level、Quality、Corrupted、Awakened／Vaal／Transfiguredの識別と専用条件、
  Empower／Enlighten／Enhanceの特別扱いは未対応

### 7. Map・Invitation・特殊マップ — 未対応

- Map Tier、Blighted／Blight-ravaged、completion reward、map quantity／rarity／pack size
- Valdo's Puzzle Box系の危険Mod除外、Nightmare Map、foil reward
- Invitation固有検索

現在はカテゴリ名と一般Modによる基本検索に留まり、Awakenedのmap専用ルールはない。

### 8. Heist・Expedition・特殊コンテンツ — 未対応

- Blueprintのarea level／revealed wings、Contractのjob level
- Heist Gear、Brooch、Tool、Cloak、Trinketの種別別条件
- Expedition Logbookのエリア別プリセット
- Chronicle of Atzoatlの部屋Tier整理
- Mirrored TabletのReflection難易度整理
- Memory Line、Sanctum Relic、Charm、Idol、Graft、Sentinel

一部名称はカテゴリ認識するが、専用property／pseudo／初期選択規則がない。

### 9. Currency・Card・Stack品・Bulk — 部分対応

- 名前／ベースタイプによる通常Trade検索と通貨条件は可能
- stack size／stock filter、Currency Exchange/Bulk endpoint、merchant-only判定、
  stack value表示は未対応

### 10. その他のアイテム種別 — 未対応

- Captured Beast
- Metamorph Sample
- Flask／Tinctureの固有roll・hybrid Mod規則
- Voidstone

## 優先度付き残課題

### P0: 「装備価格チェック同等」を完成させる

1. pseudo不足3種とgroup/replaces規則を追加
2. Gemの高頻度条件を実装
3. 上記を日本語実アイテムfixtureと公式Trade APIで横断検証

### P1: 高頻度の非装備を広げる

1. Map／Invitation
2. Gemのlevel／quality／corrupted／variant
3. Currency／Card／stack sizeとBulk検索
4. Flask／Tincture

### P2: 特殊コンテンツを追従する

- Heist、Expedition Logbook、Atzoatl、Mirrored Tablet、Memory Line、Sanctum、
  Sentinel、Captured Beast、Metamorph Sample等

## 総合判定

- 通常装備・ユニーク価格チェック: **実装済み（細かな例外は残る）**
- Awakenedの価格チェック全機能: **部分対応**
- 公開時の正確な表現: 「日本語PoE向けの装備価格チェック。Awakened相当の主要な
  Mod判断・pseudo・ユニーク検索に対応。特殊アイテムは段階対応」

この監査はソース比較であり、Windows実機の配布ZIP／Alt+D最終確認は別の未完了項目として残す。
