# Awakened PoE Trade 原本保全

ぽえとれが参照したAwakened PoE Tradeの必要データ・実装仕様を、上流リポジトリが
取得不能になっても再確認できるよう、固定commitのソース一式を開発用に保存する。

- 固定commit: `1e2225af8cfe04ccc5676d00eede81d7ee071240`
- 原本: `vendor-sources/awakened-poe-trade-1e2225af.tar.gz`
- SHA-256 manifest: `vendor-sources/awakened-poe-trade-1e2225af.json`
- 内容: `stats.ndjson`、`items.ndjson`、`item-drop.json`、価格検索のfilter／preset／pseudo実装、MIT Licenseを含む当該commitの全ソース
- 用途: 開発時の復旧・比較監査のみ。PoENavi配布ZIPには同梱しない

検証:

```bash
python scripts/archive_awakened_source.py --verify
```

将来のAwakened更新はこの原本を上書きせず、別revision・別ファイル名で保存する。
⑤の有力fork切替対応は、この保存とは分離して必要時に実装する。
