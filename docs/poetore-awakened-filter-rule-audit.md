# Awakened検索判断規則の準拠監査

監査日: 2026-07-31

比較対象: Awakened PoE Trade `18a401efce4683a274978e3f41ce08ac8948732b`

一覧CSV: `docs/poetore-awakened-filter-rule-audit.csv`

## 目的

機能の有無ではなく、カテゴリ・プリセット・値の境界によって変わる
「表示／非表示」「初期ON／OFF」「検索値・範囲」を規則単位で比較する。

CSVの`鰤さん判断欄`が`要判断`または`要確認`の行は、Awakenedへ機械的に揃える前に
ぽえとれ独自仕様を維持するか判断する対象である。

## 再監査の方法

初回監査の「機能・規則単位」だけでは、I21のように1行の中へ
完成品／Exact／クラフトベースの分岐が隠れる問題があった。
再監査では、Awakenedの対象11ファイルを改めて読み直し、次を別ケースとして照合した。

- 対象カテゴリとrarity
- 選択中プリセット
- 条件を表示するか
- 初期ON／OFF
- 境界値・丸め・完全一致
- 最終Trade APIへ送信するか

特に複合規則だったプリセット、ilvl、Area Level、Cluster Jewelを細分化し、
CSVを85規則から122規則へ拡張した。

## 集計

- 全122規則
- 準拠: 101
- 部分準拠: 8
- 差分・判断必要: 2
- ぽえとれ独自仕様: 5
- 対象外: 3
- 未対応: 3

## 判定の意味

- `準拠`: 実装と回帰テスト、または同等の最終Trade API条件を確認した。
- `部分準拠`: 中核は対応しているが、分岐・初期値・UIの一部に差がある。
- `差分・判断必要`: 両方動作するが初期判断が異なり、製品判断が必要。
- `独自仕様`: ぽえとれが意図的または結果的にAwakened以上の操作を提供する。
- `未対応`: Awakenedの専用判断が存在し、ぽえとれに対応処理がない。
- `対象外`: 旧Bulkや現行ゲームで重要性の低いカテゴリとして製品スコープ外。

## 今回見つかった重要差分

1. **メモリーの糸はプリセット別に挙動が違う（準拠済み）**
   - Awakenedの完成品プリセット: 非表示・OFF。
   - Awakenedのベース／Exactプリセット: 60以上ON、59以下OFF。
   - ぽえとれも同じプリセット別挙動へ変更した。

2. **通常Mapのrolled Mod（準拠済み）**
   - AwakenedのExact Mapは通常Modを初期ON。
   - ぽえとれもBlighted以外のExact Mapで通常Modをすべて初期ONへ変更した。

3. **ハイブリッド防具とBlock**
   - Awakenedはハイブリッド防御値とBlockを初期OFF。
   - ぽえとれはBlockを初期OFFへ変更。ハイブリッド防御値は初期ONを維持。

4. **Mapの収益系property（準拠済み）**
   - AwakenedはCorrupted Map、More Drops付き、Nightmare Map等に絞り、
     Quantity・Pack Size・More Dropsを初期ONにする。
   - ぽえとれも同じ対象・初期値へ変更した。

5. **8 Mod Map（準拠済み）**
   - Awakenedは条件を満たすMapへ`# Modifiers = 8`を追加する。
   - ぽえとれも`Mod数 = 8`条件を追加した。

6. **Exactの数値許容幅**
   - AwakenedはMap以外のExact Modを最大2%に制限する。
   - ぽえとれは共通許容幅と一部固定10%緩和を使うため、条件によって差が出る。

7. **Chronicle of Atzoatl（準拠済み）**
   - Awakenedの全86 Room規則を機械比較し、削除・非表示・初期ON/OFF・
     閉鎖部屋と爆薬部屋の組み合わせを同じ挙動へ変更した。

8. **大型Cluster Jewelの9パッシブ（ぽえとれ独自仕様）**
   - Awakenedは9パッシブを`最大9`として8パッシブも検索対象に含める。
   - ぽえとれはユーザー判断により`最小9`とし、価値の異なる8パッシブを除外する。

9. **ExactのMagic rarity（今回の再監査で発見）**
   - AwakenedはAdorned対象外のMagic品について、Magic条件を初期OFF候補として持ち、
     初期APIにはrarityを送らない。
   - ぽえとれは`nonunique`を初期APIへ送る。

10. **Veiled非Uniqueのilvl（今回の再監査で発見）**
    - Awakenedは完成品プリセットでもilvlを強制的に初期ONにする。
    - ぽえとれは通常完成品と同じ初期OFFのため未対応。

11. **最大ライフ／マナ疑似Modのrequired条件（今回の再監査で発見）**
    - Awakenedは明示最大ライフModがある時だけ最大ライフ合計を生成し、
      明示最大マナModがある時だけ最大マナ合計を生成する。
    - ぽえとれは筋力だけ、または知性だけでも疑似Modを生成する。
    - 武器の最大ライフ合計を初期OFFにした直前修正だけでは完全準拠になっていない。

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
