# PoE2版ぽえとれ 実機テスト

このフォルダを、Windows実機テストの作業入口とする。

## 作業ファイル

- `windows-test-cases.csv`: Windows実機の受入作業票（60ケース）
- `search-matrix-audit.csv`: 装備27カテゴリのレアリティ／プリセット／検索範囲の構造監査結果
- `search-matrix-audit.json`: 上記監査の機械可読サマリーと全行
- `search-real-copy-audit.csv`: 日英実コピーfixtureの解析・最終Trade2 identity監査結果
- `../../tests/fixtures/poe2/real_copy_bilingual.csv`: 収集済み日英実コピーの自動テスト用fixture台帳
- `../poetore-pending-tasks.md`: ぽえとれ全体の残タスク正本
- `../poetore-poe2-development.md`: PoE2版の実装・検証履歴

実機で編集するのは`windows-test-cases.csv`だけとする。自動テスト用fixtureはMac正本で管理し、
実機作業票から確認済みコピーを取り込む時に更新する。

## 実施順

1. 優先度`必須`のうち、手元にあるアイテムから実施する
2. `判定`を`合格`／`不合格`／`保留`のいずれかへ更新する
3. 日英詳細コピー、実測したUI、Trade／Ninja URL、検索件数を可能な範囲で記録する
4. 不具合があれば、期待値との差と再現手順を`不具合・差分・メモ`へ記録する
5. 希少品は無理に入手せず、優先度`入手できた時`のまま残す

## 現在の件数

- 全60ケース
- 必須43件
- 推奨15件
- 入手できた時2件
- 2026-08-11時点では全件未実施

## P0自動監査（2026-08-11）

- 構造母集団351ケース
- 自動検証済み297ケース
- 仕様上対象外54ケース
- 検出不具合0件
- 日英実コピー台帳28組すべてを自動検証済み、実コピー待ちは0組

構造監査は合成fixtureで分岐と最終Trade2 JSONを総当たりする。翻訳・identity・ゲーム内コピー固有の
差異を合成fixtureだけで検証済みとは扱わない。UIは同じ27カテゴリをQt offscreenで自動監査し、
Windowsでの見た目・操作感は`windows-test-cases.csv`に残す。

再生成コマンド:

```bash
PYTHONPATH=. uv run --python 3.12 --with-requirements requirements.txt -- \
  python -m src.poetore.poe2.audit
```

## Windowsでの作業方法

作業票へ記録する`PoENaviコミット`と、起動した`poenavi-windows-<commit>`の末尾を一致させる。
`poenavi-windows-<commit>`は確認用スナップショットなので直接編集しない。Windows共有上に用意した
専用の作業コピーへ結果を記入し、確認後にMac正本へ取り込む。
