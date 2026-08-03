# 公式Trade反射Mod日本語文面更新（2026-08-03）

公式日本語Trade APIで改善された次の6 Statを採用した。ID・英語ref・発生源を固定し、
`tests/test_poetore_metadata.py`で採用文面を回帰検証する。

- `explicit.stat_1574578643`: `Watcher's Eye` — Purity of Elements中に受ける反射元素ダメージを50〜75%防ぐ
- `explicit.stat_2255585376`: `Watcher's Eye` — Determination中に受ける反射物理ダメージを50〜75%防ぐ
- `explicit.stat_3829555156`: `Sibyl's Lament` — 右リング時、プレイヤーとミニオンの反射物理ダメージを100%防ぐ
- `explicit.stat_3991837781`: `Sibyl's Lament` — 左リング時、プレイヤーとミニオンの反射元素ダメージを100%防ぐ
- `implicit.stat_1973340656`: Eater of Worlds Body Armour implicit — Pinnacle Atlas Boss付近でミニオンの反射ダメージを75〜100%防ぐ
- `implicit.stat_2467518140`: Eater of Worlds Body Armour implicit — ミニオンの反射ダメージを45〜70%防ぐ

同時期に公式APIのVeiled 20 Statが英語へ戻る応答を確認したため、
`scripts/poetore-japanese-overrides.json`へ監査済み日本語を保持する。API応答が日本語へ
戻った場合も同じ文面を適用し、英語応答へ再変動してもゲーム内日本語コピーとの照合を壊さない。
