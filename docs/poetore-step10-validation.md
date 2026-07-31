# ぽえとれ 手順10 横断検証

検証日: 2026-07-20

## 回帰fixture

`tests/fixtures/poetore/step10_cases.json` に、日本語の詳細コピー原文、英語Tradeベース、
期待する自動選択条件、状態条件を一体で保存する。

収録した代表ケース:

- 武器: 物理、属性、物理＋属性、DPSを主要条件にしないスペルワンド
- 防具: Armour＋ES、Armour＋Evasion、Ward
- 装飾品: ライフ、元素／混沌耐性、能力値のpseudo集約
- ユニーク: 固定Modを除外し、可変Modが3個以下なら自動選択
- 特殊Mod: Fractured、Crafted、Enchant、空きPrefix／Suffix
- 特殊状態: 二重Influence、Synthesised、Corrupted、Split、Mirrored、Foil

`tests/test_poetore_cross_validation.py` は、各原文を実際のparserと条件選択器へ通し、
有効な条件値、表示候補、検索JSONの状態条件を検証する。

既存の `tests/test_poetore_trade.py` では、次の補完ケースを回帰確認する。

- ユニークの可変Modが4個以上、完璧ロール、低いほど良い、exact、符号反転
- 未鑑定ユニーク、Legacy discriminator、Foulborn
- 6ソケット／リンク、品質、Fractured／Synthesisedのクラフトベース検索
- 単一Influence、複数行Mod、同一stat合算、ローカルModの二重条件除去

## 公式Trade API検証

本体と同じ `www.pathofexile.com/api/trade/search/<league>` を使い、現在の日本語公式
stat一覧でModを再解決した検索JSONを送信する。レート制限を避けるため検索間隔を空け、
出品詳細のfetchは行わない。

初回は12件中11件が受理された。1件の拒否理由はfixtureに使った架空のユニーク名
`The Example` であり、API応答は `Unknown item name` だった。実在する `The Ignomon`
へ修正後に再検証し、**12件すべてで検索IDの発行に成功**した。

Mirageリーグでの受理時候補件数（時点値）:

- physical_weapon 9、elemental_weapon 0、mixed_weapon 7、spell_weapon 0
- armour_es_hybrid 3、evasion_armour_hybrid 0、ward_armour 6
- accessory_pseudos 1、variable_unique 56、fractured_crafted 67
- synth_enchant_corrupted 0、mirrored_foil_unique 0

0件のケースも検索JSON自体は受理され、検索IDが発行されている。候補件数は相場状況で変わるため、
回帰テストの固定値にはしない。fixtureの`expected_enabled`と状態条件を、公式サイトで同じ項目を
手入力した場合の基準JSONとして比較し、生成JSONとの差分がないことを検証する。

## Awakenedとの差分と意図

- 自動選択の閾値は現状10%緩和を基本とする。判断理由はぽえとれ独自の診断表示。
- 未コラプト品は `corrupted=false`、コラプト品は指定なし（両方）を初期値とする。
- 非Split品は `split=false`、Split済み品は指定なし（両方）を初期値とする。
- Finished検索ではSynthesisedやInfluenceを暗黙固定しない。クラフトベース検索では
  ベース価値に関わるため、Synthesised、Fractured、Influenceを条件化する。
- Foilは公式rarity `uniquefoil` を使用する。Foulborn品は状態指定なし、通常品は
  `foulborn_item=false` とする。

## 未対応・実機確認が必要な範囲

- fixtureの原文は回帰用の代表例であり、公式サイトの候補件数そのものはリーグと時刻で変動する。
- Legacy Variantは公式itemsデータのdiscriminator選択まで自動テスト済み。実在品を使った
  Windows UI操作は引き続き手動スモーク対象とする。
- 日本語matcherで解決できない新規Modは推測でstat IDを付けず、UI警告へ残す。
