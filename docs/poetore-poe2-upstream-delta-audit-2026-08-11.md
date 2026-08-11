# ぽえとれPoE2 最新EE2／公式Trade2差分再監査

監査日: 2026-08-11

## 結論

- EE2の比較対象は既定ブランチ`master`ではなく、更新日時が新しい開発ブランチ`dev`とする。
- 最新`origin/dev`は、ぽえとれが既に固定している
  `d72afb83bc0888919a89d3c3744acee2c597e9c8`と完全一致した。EE2差分は0 commit／0 file。
- 公式Trade2の日英`stats`／`items`は配列内の順序だけ変化した。グループ、entry数、entry内容の
  multiset差分はすべて0件だった。
- 公式Trade2の日英`filters`／`static`および`leagues`はJSON構造まで完全一致した。
- よって、identity／Stat／filter／category／league／最終Trade2 JSONへ反映すべき新差分はない。
  ソース固定revision、配布metadata、PoE2実装は変更しない。

## 固定した取得結果

取得時刻: 2026-08-11T05:12:34Z

### Exiled Exchange 2

- `origin/dev`: `d72afb83bc0888919a89d3c3744acee2c597e9c8`
  - commit日時: 2026-07-27T19:29:47-05:00
  - 既存source lockとの差分: 0 commit／0 file
- `origin/master`: `acc7653f05629228f12e273ab1b8da3e46d6bcd1`
  - commit日時: 2026-06-20T08:57:42-05:00
  - `dev`より古いため、最新仕様の比較基準には採用しない

Gitの既定ブランチだけを機械的に比較すると、古い`master`を「新しいEE2」と誤認する。
今後もremote各branchのcommit日時と、固定revisionが最新開発branchの祖先またはHEADかを先に確認する。

### 公式Trade2

比較先は`vendor-sources/poe2-trade-api-2026-08-09/`、取得元は英語
`www.pathofexile.com/api/trade2/data/*`と日本語`jp.pathofexile.com/api/trade2/data/*`。

- `stats_en`: 8,248 entries、追加0／削除0／内容変更0
- `stats_ja`: 8,249 entries、追加0／削除0／内容変更0
- `items_en`: 3,880 entries、追加0／削除0／内容変更0
- `items_ja`: 3,873 entries、追加0／削除0／内容変更0
- `filters_en`／`filters_ja`: JSON構造差分0
- `static_en`／`static_ja`: JSON構造差分0
- `leagues`: JSON構造差分0

`stats`と`items`はraw SHA-256が変わっているが、同一group内のentry順序変更だけである。
各entryをgroup IDと正規化JSONでmultiset比較した結果、追加・削除とも0件だったため、
snapshotを内容更新として取り込まない。

## 影響分類

- identity: 差分なし
- Stat ID／日英Stat文面: 差分なし
- filter ID／option: 差分なし
- Trade category: 差分なし
- league: 差分なし
- Parser／検索条件のEE2挙動: 固定revisionが最新`dev` HEADのため差分なし
- 実装修正: 不要
- metadata再生成: 不要

Waystoneの`Monster Effectiveness` → `map_magic_monsters`、`Monster Rarity` →
`map_rare_monsters`を含む現行filter対応も、最新公式Trade2と一致している。

## 再監査手順

1. EE2の全remote branch HEAD、commit日時、固定revisionとの祖先関係を確認する。
2. 最新開発branchと固定revisionをcommit／file単位で比較する。
3. 公式Trade2を日英で取得し、raw hashだけでなくgroup ID＋entry正規化JSONのmultisetで比較する。
4. 差分がある場合だけidentity、Stat、filter、category、league、queryへの影響を分類する。
5. 並び順だけの変化をmetadata内容変更として取り込まない。
