# PoE2ぽえとれ 最新EE2カテゴリ網羅監査

監査日: 2026-09-01

## 比較基準

- EE2 repository: `Kvan7/Exiled-Exchange-2`
- 最新開発ブランチ: `dev`
- 最新revision: `10fe4fcd0b0ce089f82ad985a3c41a633c210a46`
- commit日時: 2026-08-31 20:49:17 -0500
- PoENavi固定revision: `d72afb83bc0888919a89d3c3744acee2c597e9c8`

GitHubの全remote branchをcommit日時順に確認し、`dev`を最新の実装基準とした。既定の`master`は
2026-06-20が最終更新で、PoE2価格検索の比較基準には使用しない。

## 差分結論

固定revisionから最新`dev`までは28 commitあるが、PoE2の英日identity集合とRune／Soul Core集合に
増減はなかった。PoENaviのindex生成処理で再構築して比較した結果は次のとおり。

- identity index: 3,832一意キー、追加0、削除0
- augment index: 259 entries、追加0、削除0
- 最新EE2英日items: 4,015 raw rowsずつ
- 名前付きcraftable category: 49種類

最新差分は主にOverlay、CI、item editor保存UI、診断ログであり、検索可能アイテムの母集団変更ではない。

## 既存実機テストの不足

既存ケースは特殊状態や代表カテゴリの深掘りには強いが、EE2が持つカテゴリ集合に対して次が不足していた。

- PoE2で通常品が実装済みの武器9系統を同一基準で横断する実機検索
- 防具7系統の全部位横断
- Quiver、Amulet、Belt、Talismanを含む装身具横断
- Gemの各familyを複数identityで確認する試験
- Currency、Omen、Rune、Soul Coreを複数品で横断する試験
- Map、TowerAugment、MapFragment、Breachstoneの経路横断
- Key、Logbook、MiscMapItem、BrequelFruit、Relicの特殊カテゴリ横断
- 同一カテゴリ内の通常／Advanced／Expert相当baseの取り違え
- Unique identityの装備カテゴリ横断サンプル

## 追加ケース

上記を`P2-WIN-075`〜`P2-WIN-083`として追加した。1カテゴリ1ケースへ機械的に増やすのではなく、
同一セッションで複数カテゴリを順番に検索するスイープ形式にして、認識不能だけでなく前アイテムの
identity・filter残留とカテゴリ誤分類も同時に検出する。

この監査はEE2のidentityデータと実装を一次資料とした。公式Trade2で実際に検索可能か、現在リーグに
出品があるかはWindows実機で生成URLと応答を保存して確定する。

補足: EE2には将来用と思われるOne/Two Hand Sword、One/Two Hand Axe、DaggerカテゴリとUnique Flailが
存在するが、実機の通常品網羅テストからは除外した。QuiverはEE2の独立カテゴリとして`P2-WIN-077`で確認する。
