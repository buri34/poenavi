from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.poetore.poe2.desecration_ocr_probe import load_probe_cases, run_probe


def main() -> int:
    default_input = ROOT / "tests" / "fixtures" / "poetore" / "poe2" / "desecration"
    parser = argparse.ArgumentParser(
        description="保存済みの冒涜3択画像を本番同等のWindows OCR経路で検証します。",
    )
    parser.add_argument("--input-dir", type=Path, default=default_input)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    manifest = args.manifest
    default_manifest = args.input_dir / "reported-cases.json"
    if manifest is None and default_manifest.is_file():
        manifest = default_manifest
    cases = load_probe_cases(args.input_dir, manifest)
    if not cases:
        parser.error(f"入力画像がありません: {args.input_dir}")
    report = run_probe(cases, args.output, prepare_only=args.prepare_only)
    print(f"{report['case_count']}画像を処理しました: {args.output / 'report.html'}")
    if args.prepare_only or not report["expected_cases"]:
        return 0
    return 0 if report["all_expected_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
