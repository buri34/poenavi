# Awakened検索判断規則の準拠監査

監査日: 2026-07-31

比較対象: Awakened PoE Trade `18a401efce4683a274978e3f41ce08ac8948732b`

一覧CSV: `docs/poetore-awakened-filter-rule-audit.csv`

## 目的

機能の有無ではなく、カテゴリ・プリセット・値の境界によって変わる
「表示／非表示」「初期ON／OFF」「検索値・範囲」を規則単位で比較する。

CSVの`鰤さん判断欄`が`要判断`または`要確認`の行は、Awakenedへ機械的に揃える前に
ぽえとれ独自仕様を維持するか判断する対象である。

## 集計

- 全85規則
- 準拠: 63
- 部分準拠: 9
- 差分・判断必要: 5
- ぽえとれ独自仕様: 4
- 対象外: 3
- 未対応: 1

## 判定の意味

- `準拠`: 実装と回帰テスト、または同等の最終Trade API条件を確認した。
- `部分準拠`: 中核は対応しているが、分岐・初期値・UIの一部に差がある。
- `差分・判断必要`: 両方動作するが初期判断が異なり、製品判断が必要。
- `独自仕様`: ぽえとれが意図的または結果的にAwakened以上の操作を提供する。
- `未対応`: Awakenedの専用判断が存在し、ぽえとれに対応処理がない。
- `対象外`: 旧Bulkや現行ゲームで重要性の低いカテゴリとして製品スコープ外。

## 今回見つかった重要差分

1. **メモリーの糸はプリセット別に挙動が違う**
   - Awakenedの完成品プリセット: 非表示・OFF。
   - Awakenedのベース／Exactプリセット: 60以上ON、59以下OFF。
   - ぽえとれ: 両プリセットで60以上ON。
   - 直前の60境界修正はベース側には準拠したが、完成品側は判断が必要。

2. **通常Mapのrolled Mod**
   - AwakenedのExact Mapは通常Modを初期ON。
   - ぽえとれは通常Map Modを初期OFF、ValdoだけON。
   - 危険Modを誤って含めにくいぽえとれ仕様にも合理性があるため、自動変更しない。

3. **ハイブリッド防具とBlock**
   - Awakenedはハイブリッド防御値とBlockを初期OFF。
   - ぽえとれは実在する防御値とBlockを完成品検索で初期ON。
   - 検索精度と件数のどちらを優先するかで判断が分かれる。

4. **Mapの収益系property**
   - AwakenedはCorrupted Map、More Drops付き、Nightmare Map等に絞り、
     Quantity・Pack Size・More Dropsを初期ONにする。
   - ぽえとれは全Mapで表示する一方、Tier以外を初期OFFにする。

5. **8 Mod Map**
   - Awakenedは条件を満たすMapへ`# Modifiers = 8`を追加する。
   - ぽえとれには専用条件がない。

6. **Exactの数値許容幅**
   - AwakenedはMap以外のExact Modを最大2%に制限する。
   - ぽえとれは共通許容幅と一部固定10%緩和を使うため、条件によって差が出る。

## 監査範囲

- `create-presets.ts`
- `create-item-filters.ts`
- `create-stat-filters.ts`
- `pseudo/item-property.ts`
- `pseudo/maps.ts`
- `pseudo/flasks.ts`
- `pseudo/heist.ts`
- `pseudo/anointments.ts`
- `pseudo/atzoatl-rules.ts`
- `pseudo/reflection-rules.ts`
- `pseudo/index.ts`

結果表示、通信キャッシュ、内蔵ブラウザ、旧Bulk ExchangeはこのCSVの主対象外。
pseudoのgroup/replaces定義そのものは既存の
`docs/poetore-pseudo-mod-tasks.md`と生成済みメタデータを正本とする。

## 次の進め方

1. CSVの`要判断`行について、Awakened準拠／ぽえとれ独自仕様のどちらにするか決める。
2. `要確認`行は追加fixtureまたはAPI比較で確定する。
3. 決定済みの差分から小さなコミットへ分けて修正する。
4. 将来のAwakened更新時は、このCSVのrule IDを維持したまま差分を追記する。
