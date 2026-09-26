# PoE2版ぽえとれ Windows手動QA

このディレクトリには、公開可能な手動QAの仕様と記入方法だけを置く。記入済み実施票、
スクリーンショット、公式Trade URL、実施者固有の作業記録はコミットしない。

## 公開する正本

- `windows-test-cases.csv`: 83ケースの期待仕様
- `WINDOWS_TEST_GUIDE.md`: 記入方法と0件時の扱い
- `../../fixtures/poe2/`: 自動テスト用の固定fixture

## 記入用実施票の生成

リポジトリルートで次を実行する。

```bash
python scripts/generate_poe2_windows_test_sheet.py
```

記入用CSVは`build/manual/poetore-poe2-windows-test-run.csv`へ生成される。`build/`はGitで
追跡しないため、結果を公開ソースへ混ぜずに実機確認できる。

## 役割分担

- 自動テスト: Parser、identity、Stat、最終Trade2 JSON、カテゴリ構造
- Windows手動QA: 表示、操作、クリップボード、実通信、フォーカス、連続操作

0件や通信失敗をその場で推測判定せず、画面上で確認できた事実を実施票へ記録する。
再現可能な不具合は、個人情報や一時URLを除いたfixtureと回帰テストへ変換する。

## 監査出力

PoE2構造監査は次で実行する。

```bash
PYTHONPATH=. uv run --python 3.12 --with-requirements requirements.txt -- \
  python -m src.poetore.poe2.audit
```

結果は`build/poetore-poe2-audit/`へ生成され、Gitでは追跡しない。
