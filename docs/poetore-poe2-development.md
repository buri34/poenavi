# ぽえとれ PoE2アーキテクチャ

この文書は、PoE2版ぽえとれの現行設計境界と検証方法を説明する。過去の実装日誌、
時点固定の監査結果、未確定の作業メモは含めない。

## 設計原則

- PoE1のParser／Trade処理をPoE2対応のために大規模改変しない。
- PoE2固有処理は`src/poetore/poe2/`へ分離する。
- コピー文面から公式Trade2 queryまでを縦方向に検証する。
- 解析できないModを黙って捨てず、未解決として表示する。
- 英語Trade2 APIと固定英語identityを内部検索の正本にする。
- 日本語公式Tradeへ遷移する時だけ、確認済み日英identityでname／typeを変換する。
- 推測した翻訳や未確認のカテゴリを正本データへ書き込まない。

## モジュール構成

- `parser.py`: PoE2コピー文面、property、Mod由来、状態フラグの解析
- `metadata.py`: 固定した公式Trade2 metadataと日英identityの参照
- `trade.py`: Trade2 query、search／fetch、キャッシュ、公式Trade URL
- `augment_pricing.py`: Rune／Soul Core等の補助価格処理
- `desecration_tiers.py`: 冒涜ModのTierデータと照合
- `desecration_ocr.py`: Windows OCRを使った画面読取
- `ndlocr_lite.py`: 数字欠落時だけ使う高精度OCR sidecar
- `ndlocr_pack.py`: 任意OCRパックの取得、検証、導入
- `audit.py`: 構造fixtureと実コピーfixtureのオフライン監査
- `local_global_audit.py`: Local／Global Stat選択の低頻度監査

UIは共通のぽえとれ画面を使用し、版選択時にParser、metadata、Trade adapterを切り替える。
PoE1／PoE2のリーグ選択値は別々に保存する。

## データと出典

公式Trade2のstats、items、filters、static、leaguesは、取得元URL、取得時刻、SHA-256、
件数をsource lockへ固定する。EE2を参照するデータはrevisionを固定し、公式データ、
EE2由来データ、PoENavi独自判断を区別する。

冒涜Tierデータの出典と更新手順は
[`poetore-poe2-desecration-tier-data.md`](poetore-poe2-desecration-tier-data.md)を参照する。
通常のTradeデータ更新は
[`poetore-league-data-update-plan.md`](poetore-league-data-update-plan.md)に従う。

## Parserと検索の境界

- Local／Global候補はアイテムカテゴリとMod由来から1つを選ぶ。
- 数値条件は画面上のチップを正本とし、非表示・OFFの条件を最終JSONへ送らない。
- 2値・4値Statは、固定fixtureと公式Stat IDで変換結果を検証する。
- Runeforged／Runemasteredは状態フラグへ丸めず、公式identityどおり別ベースとして扱う。
- Rune／Soul Core由来Modは通常explicitと混ぜない。
- 未確認の日英identityは推測変換せず、英語公式Trade URLへフォールバックする。

## 自動検証

自動テスト用の実コピーは`tests/fixtures/poe2/`に置く。Parserサンプル、日英identity、
最終Trade2 JSON、カテゴリ横断の構造監査をテストで固定する。

監査コマンド:

```bash
PYTHONPATH=. uv run --python 3.12 --with-requirements requirements.txt -- \
  python -m src.poetore.poe2.audit
```

監査出力は`build/poetore-poe2-audit/`へ生成され、Gitでは追跡しない。監査結果を根拠に
本番ルールを自動変更せず、レビュー後にコードと回帰テストへ反映する。

## Windows手動QA

公開する手動QA仕様は`tests/manual/poetore-poe2/`に置く。

- `windows-test-cases.csv`: 期待仕様の正本
- `WINDOWS_TEST_GUIDE.md`: 記録方法
- `README.md`: 実施入口と役割分担

記入用の実施票は次のコマンドで`build/manual/`へ生成する。

```bash
python scripts/generate_poe2_windows_test_sheet.py
```

実施結果、画像、URL、記入済み票は公開リポジトリへコミットしない。再現可能な不具合は、
匿名化したfixtureと回帰テストへ変換して公開treeへ戻す。

## 変更時の確認

PoE2 Parser／Tradeを変更した場合は、最低限次を確認する。

1. 対象fixtureのParser結果
2. 最終Trade2 JSON
3. PoE1側の回帰
4. 構造監査と実コピー監査
5. UI変更がある場合はQt offscreenとWindows実機
6. 外部データ更新時はsource lock、件数、SHA-256
