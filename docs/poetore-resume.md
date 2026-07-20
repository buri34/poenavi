# ぽえとれ 開発再開メモ

最終更新: 2026-07-20

## 目標

Awakened PoE Tradeの判断精度を、日本語PoE向けに最大限再現する。
Awakened / RePoE / 日本語公式Trade APIを参考情報源とし、ぽえとれ独自の
スキーマと実装を維持する。

## 再開地点

- worktree: `/Volumes/Android共有用/poenavi-dev-poetore`
- branch: `feature/poetore-spike`
- GitHub: 未push。この再開メモのコミット後は `origin/main` より27コミット先行
- 手順1〜6完了コミット: `a9e19aa`
- Corrupted / Split条件改善コミット: `55ae6ae`
- 再開する作業: **手順7「pseudo Modを拡充」**

## 完了済み: 手順1〜6

1. 現在版と代表検索JSONを回帰基準として固定
2. Mod共通マスター、Tier、日本語matcher、解析結果の独自スキーマを実装
3. Awakened、RePoE、日本語公式Trade APIの生成パイプラインを実装
4. RePoEを必要最小限の派生インデックスへ縮小
5. 日本語Mod解析を共通ref / stat ID / 一致確度付き基盤へ切り替え
6. better / inverted / exact / 可変幅によるAwakened準拠の数値判定を実装

詳細は `docs/poetore-metadata.md`、生成物は
`data/poetore/mod_metadata.json`、生成器は
`scripts/build_poetore_metadata.py` を参照する。

## 手順7: pseudo Modを拡充

利用頻度の高いものから実装する。

- 個別・合計元素耐性
- 能力値・全能力
- ライフ・マナ・ES
- 攻撃速度・キャストスピード
- スペルダメージ
- 属性別ダメージ
- クリティカル率・倍率
- 移動速度
- 自動回復・リーチ

同時に、個別Modとの二重表示と、意味が近いpseudo同士の重複を整理する。
最初の実装単位は、既存の装飾品pseudoを土台にした
**個別元素耐性・合計元素耐性のメタデータ駆動化と重複排除**とする。

### 手順7の完了条件

- 日本語Modから対象pseudoを安定して生成できる
- 複数Modを正しい値で集約できる
- 集約済みの個別Modを二重に初期選択しない
- ユーザーがpseudoと個別Modを確認・選択できる
- 代表的な武器・防具・装飾品の検索JSONを回帰テストで固定する
- 全体テスト、compileall、Qt offscreen smoke、公式Trade APIの受理を確認する

## 残りのロードマップ

8. ユニークとExact検索を強化
   - 完璧ロール、小さいほど良いMod、Variant、Foil / Foulborn、特殊Implicit
   - 未鑑定ユニーク例外、Enchant、Synthesised Implicit
   - Crafted Mod込みの正確な空きPrefix / Suffix
9. UIへ段階的に統合
   - Tier、範囲、生成元、自動選択理由、一致確度、未解決警告を表示
10. 実アイテムで検証
   - 武器、防具、装飾品、ユニーク、特殊状態、Legacyを公式Tradeサイトと比較
11. データ更新の仕組みを作る
   - バージョン固定、差分レポート、新規・削除・変更Mod、未解決一覧、自動テスト
12. 配布と権利表記を最終監査
   - 最小派生データ、MIT / GGG表記、無料・非公式表記、必要ならGGGへ確認

## 直近の仕様判断

- 未コラプト品の初期値は「未コラプトのみ」: `corrupted=false`
- コラプト品は「コラプト品含む」: `corrupted` 条件を省略
- 非スプリット品の初期値は「非スプリットのみ」: `split=false`
- スプリット済み品は「スプリット品含む」: `split` 条件を省略
- 同じアイテムの再検索ではユーザー選択を保持する
- 完成品とクラフトベース、ハイブリッド防具の全防御値選択など既存仕様を維持する

## 検証済み状態

2026-07-20時点:

- `252 passed, 22 subtests passed`
- `python -m compileall` 成功
- Qt offscreen smoke 成功
- worktreeはclean

再開時は最初に次を確認する。

```bash
git status --short --branch
git log --oneline -5
PYTHONPATH=. QT_QPA_PLATFORM=offscreen uv run --python 3.12 \
  --with pytest --with-requirements requirements.txt -- pytest -q
```

## 運用上の境界

- SMB worktreeを正本として更新する
- ローカルcommitは実行してよい
- GitHubへのpush、PR、mergeは鰤さんの明示確認後に行う
- RePoEの元データ全体をアプリへ同梱しない
- 未確認値を正本データへ推測で書かない
