# Expedition OCR精度検証

PoE2の報酬画面キャプチャから報酬行を分離し、OCR結果をJSONへ保存する開発用ツールです。
ゲームやPoENavi本体には接続せず、指定フォルダ内のPNG/JPEGだけを処理します。
全画面画像では左端の報酬パネルだけを自動走査し、パネルだけを切り抜いた画像も処理できます。

## 入力

画像を任意のフォルダへ置きます。正解率も測る場合は、画像と同名の
`<画像名>.truth.json`を次の形式で隣へ置きます。

```json
{
  "rows": [
    "3x 高貴なオーブ",
    "1x 混沌のオーブ"
  ]
}
```

行は画面の上から順に記述します。

## 実行

Tesseractと日本語言語データが利用できる環境では次を実行します。

```powershell
python scripts/expedition_ocr_probe.py path\to\screenshots
```

OCR環境を用意する前に行検出と前処理だけ確認する場合:

```powershell
python scripts/expedition_ocr_probe.py path\to\screenshots --prepare-only
```

結果は既定で`runs/expedition-ocr/`へ出力されます。画像ごとのフォルダには
分離・3倍拡大した各報酬行、`result.json`が入り、全画像の結果は`summary.json`へまとまります。
`runs/`はGit管理対象外です。

## 評価値

- `exact_rate`: 正規化後の完全一致率
- `mean_similarity`: 文字列類似度の平均
- `expected_rows` / `detected_rows`: 正解行数と検出行数

OCR結果がない場合に誤価格を表示しない設計を優先するため、実装判断では完全一致率に加え、
別アイテムへ誤一致した件数を個別に確認します。
