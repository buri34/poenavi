# ぽえとれ pseudo Mod 残タスク

更新日: 2026-07-21  
比較基準: Awakened PoE Trade `fa31bfb`

## 目的

通常の武器・防具・アクセサリーについて、複数の実Modを価格検索向けのpseudo Modへ集約する挙動と、
表示候補の相互排他規則をAwakened PoE Tradeに合わせる。

## 現在対応済み

- 元素耐性、火・冷気・雷・混沌耐性
- Strength・Dexterity・Intelligence・全能力値
- 最大Life・Mana・Energy Shield
- Attack Speed・Cast Speed・Movement Speed
- 物理・元素・火・冷気・雷・Spell Damage
- Global Critical Strike Chance／Multiplier
- Life／Mana回復、物理AttackのLife／Mana Leech
- pseudoへ集約した元Modの二重表示除去
- 空きPrefix／Suffix

## P0: 未実装pseudoを追加

### Spell Critical Strike Chance

- [ ] Spell Critical Strike Chanceに寄与する実ModのrefをAwakenedから抽出する
- [ ] 複数Modを `pseudo.pseudo_global_spell_critical_strike_chance` へ合算する
- [ ] ローカル武器Critや一般Global Critを誤って含めない
- [ ] 日本語の単一Mod・複合Mod・crafted Mod fixtureを追加する

### Elemental Damage with Attack Skills

- [ ] 対応する実Modとhybrid Modのrefを抽出する
- [ ] Attack Skills限定の元素ダメージを専用pseudoへ合算する
- [ ] 一般Elemental DamageやSpell Damageとの二重計上を防ぐ
- [ ] 武器・指輪・アミュレットの日本語fixtureを追加する

### Burning Damage

- [ ] Burning Damageに寄与する実Modとhybrid Modのrefを抽出する
- [ ] Fire Damage／Damage over Timeとの関係をAwakened準拠で整理する
- [ ] 同じ値を複数pseudoへ表示する場合と置換する場合を区別する
- [ ] 日本語fixtureと検索JSONの回帰テストを追加する

## P0: group／replaces規則を再現

- [ ] Awakenedのpseudo定義から `group` と `replaces` を機械的に抽出する
- [ ] 同一group内では、より情報量の多いpseudoだけを初期表示する
- [ ] `replaces` 対象になった個別Mod／下位pseudoを非表示にする
- [ ] 複合耐性、能力値、Life、Mana、ES、Damage系で相互排他を検証する
- [ ] 表示順序と初期ON/OFFが入力順に依存しないことをテストする
- [ ] 未解決refがあっても、関係のないpseudoを消さないようにする

## P1: Awakened固有の表示・価値判断規則

- [ ] crafted Chaos Resistanceを、Awakenedと同条件で価値なし候補として隠す
- [ ] crafted Modと通常Modが同じpseudoへ寄与する場合の優先順位を合わせる
- [ ] アイテムカテゴリ別に不要なpseudoを隠す規則を棚卸しする
- [ ] 完成品検索とクラフトベース検索で表示候補を分ける
- [ ] 低い値・固定値・価格差に寄与しにくい値の初期選択規則を確認する

## データ設計

- [ ] pseudo定義をコードへの個別直書きから、レビュー可能な派生データへ移す
- [ ] 各定義にpseudo stat ID、寄与ref、group、replaces、対象カテゴリを保持する
- [ ] Awakenedの固定コミットと生成物のSHA-256を記録する
- [ ] 重複ref、循環replaces、存在しないstat IDを生成時に拒否する
- [ ] 更新時に追加・削除・変更件数をレポートする

## 完了条件

- [ ] 上記3種のpseudoが日本語詳細コピーから正しい値で生成される
- [ ] group／replaces適用後に、重複または矛盾する検索候補が残らない
- [ ] 元Mod値の合計、検索用10%緩和値、初期ON/OFFをfixtureで固定する
- [ ] 代表的な武器・防具・アクセサリーの検索JSONを公式Trade APIが受理する
- [ ] 全体pytest、compileall、Qt offscreen表示スモークが成功する
- [ ] `docs/poetore-awakened-gap-audit.md` のpseudo Mod項目を「実装済み」へ更新する

## 対象外

次の項目はpseudo Modとは別の残タスクとして扱う。

- Gem、Map、Heist、Bulk検索などのカテゴリ固有条件
- Flask／Tincture固有roll
- Captured Beast、Metamorph Sample、Voidstone
- Watcher's Eyeなど特定ユニーク固有の例外
