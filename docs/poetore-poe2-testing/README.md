# PoE2版ぽえとれ 実機テスト

このフォルダを、Windows実機テストの作業入口とする。

## 作業ファイル

- `windows-test-run.csv`: Windows実機で記入する83ケースの実施票。期待仕様の隣に結果を記入する
- `windows-test-cases.csv`: 83ケースの詳細仕様・追跡用正本。原則として実機では編集しない
- `WINDOWS_TEST_GUIDE.md`: 記入欄、0件、詳細コピー、P2-WIN-001の具体例
- `search-matrix-audit.csv`: 装備27カテゴリのレアリティ／プリセット／検索範囲の構造監査結果
- `search-matrix-audit.json`: 上記監査の機械可読サマリーと全行
- `search-real-copy-audit.csv`: 日英実コピーfixtureの解析・最終Trade2 identity監査結果
- `../../tests/fixtures/poe2/real_copy_bilingual.csv`: 収集済み日英実コピーの自動テスト用fixture台帳
- `../poetore-pending-tasks.md`: ぽえとれ全体の残タスク正本
- `../poetore-poe2-development.md`: PoE2版の実装・検証履歴

実機で編集するのは`windows-test-run.csv`と詳細コピー用`.txt`だけとする。詳細仕様、自動テスト用fixture、
原因分析はMac正本で管理する。

## 実施方法

1. `WINDOWS_TEST_GUIDE.md`を最初に読む。
2. `windows-test-run.csv`を実施順に進める。必要ケースは削減していない。
3. 各ケースで識別、チップ、検索条件を個別に照合し、検索応答と一次証拠を記録する。
4. 0件でも原因推測は不要。件数、URL、詳細コピーを残せば、Mac側で切り分ける。
5. まとまった件数ごとにMac側へ返し、発見した差分を修正・再試験する。

### 実機で確認する範囲

実機では、Windows固有の表示・操作・クリップボード・通信・実API応答を確認する。Parser、identity、
Stat、最終Trade2 JSONの網羅性はP0自動監査が担保するため、カテゴリ総当たりを人手で再検証しない。
P2-WIN-065以降は、単品の網羅では見つけにくい連続操作・復旧・条件往復・表示とqueryの対応を確認する。
P2-WIN-075以降は、最新版EE2のidentityカテゴリを母集団に、武器・防具・装身具・Gem・交換品・地図・
特殊エントリー品・base variant・Uniqueをカテゴリ横断で確認する。

## 現在の件数

- 詳細仕様・追跡台帳: 全83ケース
- Windows実施票: 全83ケース
- P2-WIN-001〜064: 従来のカテゴリ・状態・導線テスト
- P2-WIN-065〜074: 2026-09-01追加の相互作用・復旧・検索意味テスト
- P2-WIN-075〜083: 2026-09-01最新版EE2基準の検索可能アイテム網羅テスト

## P0自動監査（2026-08-11）

- 構造母集団351ケース
- 自動検証済み297ケース
- 仕様上対象外54ケース
- 検出不具合0件
- 日英実コピー台帳28組すべてを自動検証済み、実コピー待ちは0組

構造監査は合成fixtureで分岐と最終Trade2 JSONを総当たりする。翻訳・identity・ゲーム内コピー固有の
差異を合成fixtureだけで検証済みとは扱わない。UIは同じ27カテゴリをQt offscreenで自動監査し、
Windowsでの見た目・操作感は`windows-test-run.csv`に残す。

再生成コマンド:

```bash
PYTHONPATH=. uv run --python 3.12 --with-requirements requirements.txt -- \
  python -m src.poetore.poe2.audit
```

## Windowsでの作業方法

作業票へ記録する`PoENaviコミット`と、起動した`poenavi-windows-<commit>`の末尾を一致させる。
`poenavi-windows-<commit>`は確認用スナップショットなので直接編集しない。Windows共有上に用意した
専用の作業コピーへ結果を記入し、確認後にMac正本へ取り込む。
