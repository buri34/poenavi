from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.poetore.expedition_ocr_probe import (
    OCR_ENGINES,
    analyze_directory,
    load_item_dictionary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="PoE2 Expedition報酬画面のOCR精度検証")
    parser.add_argument("input_dir", type=Path, help="PNG/JPEGを置いたフォルダ")
    parser.add_argument("--output", type=Path, default=Path("runs/expedition-ocr"))
    parser.add_argument("--language", default="jpn+eng", help="Tesseract言語（既定: jpn+eng）")
    parser.add_argument("--engine", choices=OCR_ENGINES, default="tesseract", help="OCRエンジン")
    parser.add_argument("--prepare-only", action="store_true", help="OCRせず行検出・前処理だけ実行")
    parser.add_argument("--dictionary", type=Path, help="Trade API形式の日本語items JSON")
    parser.add_argument("--csv", type=Path, help="一覧CSVの出力先（画像名は含めません）")
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        parser.error(f"入力フォルダがありません: {args.input_dir}")
    dictionary = load_item_dictionary(args.dictionary) if args.dictionary else []
    results = analyze_directory(
        args.input_dir,
        args.output,
        language=args.language,
        ocr_engine=args.engine,
        prepare_only=args.prepare_only,
        item_dictionary=dictionary,
        csv_path=args.csv,
    )
    print(f"{len(results)}画像を処理しました: {args.output / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
