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

日本語アイテム辞書を指定すると、数量専用OCRと保守的な候補照合を行い、画像名を含まない
一覧CSVも出力します。`trusted=no`の行は誤価格防止のため`item_name`を空欄にします。

```powershell
python scripts/expedition_ocr_probe.py path\to\screenshots `
  --dictionary path\to\items_ja.json `
  --csv expedition-items.csv
```

CSVはUTF-8 BOM付きで、Excelから直接開けます。Windows標準OCRとの比較時も、同じ列へ
結果を出すことでTesseract結果と行単位に比較できます。

## Windows標準OCRで実測する

Windows 10/11の日本語言語パックと.NET 8 SDKが必要です。PowerShellを開き、
Windows確認用ミラーのルートで次を実行します。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_expedition_windows_ocr.ps1
```

スクリプトは`Windows.Media.Ocr`を呼ぶヘルパーをビルドし、既存と同じ行分離画像を
日本語OCRへ渡します。今回のWindowsミラーでは入力画像と辞書を自動選択し、共有フォルダの
`expedition-items-windows.csv`へ結果を出力します。別の画像を使う場合は
`-InputDirectory`と`-Dictionary`を指定できます。
初回ビルド時は.NETが必要な参照ファイルを取得するため、ネット接続が必要な場合があります。

日本語OCRが利用できない場合は、Windowsの「設定」→「時刻と言語」→「言語と地域」で
日本語の言語機能を追加してから再実行します。実測CSVが生成されるまでは、Windows OCRの
精度を確認済みとは扱いません。

## 評価値

- `exact_rate`: 正規化後の完全一致率
- `mean_similarity`: 文字列類似度の平均
- `expected_rows` / `detected_rows`: 正解行数と検出行数

OCR結果がない場合に誤価格を表示しない設計を優先するため、実装判断では完全一致率に加え、
別アイテムへ誤一致した件数を個別に確認します。
