from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.poetore.poe2.desecration_ocr import choice_bands
from src.poetore.poe2.desecration_tiers import resolve_desecration_choices_fuzzy

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
KATAKANA_DASH_RE = re.compile(r"(?<=[ァ-ヶ])[-‐‑–—](?=[ァ-ヶ])")
UNRESOLVED_STATUSES = frozenset({"read_failed", "unsupported", "category_unselected"})


def compact(text: str) -> str:
    text = re.sub(r"\s+", "", str(text or ""))
    return KATAKANA_DASH_RE.sub("ー", text)


def stable_missing_number_body(choice: dict) -> str | None:
    """Return a stable Windows OCR body eligible for an NDL numeric pass."""
    if choice.get("tier") is not None:
        return None
    if choice.get("status") not in UNRESOLVED_STATUSES:
        return None
    raw_texts = choice.get("raw_texts")
    if not isinstance(raw_texts, list) or len(raw_texts) != 4:
        return None
    normalized = tuple(compact(text) for text in raw_texts)
    if not normalized[0] or len(set(normalized)) != 1:
        return None
    body = normalized[0]
    if not re.search(r"[ぁ-んァ-ヶ一-龯]", body):
        return None
    return body


def prepare_ndl_inputs(
    windows_summary: Path,
    input_dir: Path,
    output_dir: Path,
    plan_path: Path,
) -> dict:
    report = json.loads(windows_summary.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = []
    for case in report.get("cases", []):
        source = input_dir / str(case.get("file", ""))
        image = QImage(str(source))
        bands = choice_bands(image)
        if image.isNull() or len(bands) != 3:
            continue
        for choice in case.get("choices", []):
            body = stable_missing_number_body(choice)
            index = int(choice.get("index", 0))
            if body is None or index not in (1, 2, 3):
                continue
            band = bands[index - 1]
            crop_name = f"{source.stem}-choice-{index}.png"
            crop_path = output_dir / crop_name
            crop = image.copy(
                0, band.top, image.width(), max(1, band.bottom - band.top),
            )
            if not crop.save(str(crop_path), "PNG"):
                raise RuntimeError(f"Failed to save NDL OCR crop: {crop_path}")
            candidates.append({
                "file": source.name,
                "choice_index": index,
                "crop": crop_name,
                "windows_body": body,
            })
    plan = {"candidate_count": len(candidates), "candidates": candidates}
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return plan


def _ndl_text(payload: dict) -> tuple[str, float | None]:
    lines = []
    confidences = []
    for page in payload.get("contents", []):
        for line in page:
            box = line.get("boundingBox") or []
            ys = [float(point[1]) for point in box if len(point) >= 2]
            center = sum(ys) / len(ys) if ys else float(len(lines))
            text = str(line.get("text") or "")
            if text:
                lines.append((center, text))
            confidence = line.get("confidence")
            if isinstance(confidence, (int, float)):
                confidences.append(float(confidence))
    combined = "\n".join(text for _center, text in sorted(lines))
    confidence = min(confidences) if confidences else None
    return combined, confidence


def load_ndl_results(raw_dir: Path, plan: dict) -> dict[tuple[str, int], dict]:
    results = {}
    for candidate in plan.get("candidates", []):
        raw_path = raw_dir / (Path(candidate["crop"]).stem + ".json")
        if not raw_path.is_file():
            continue
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        text, confidence = _ndl_text(payload)
        results[(candidate["file"], int(candidate["choice_index"]))] = {
            "text": text,
            "confidence": confidence,
            "raw_json": raw_path.name,
        }
    return results


def inserted_number(windows_text: str, ndl_text: str) -> str | None:
    """Return the sole number whose removal makes the NDL text identical."""
    windows_body = compact(windows_text)
    ndl_body = compact(ndl_text)
    matches = []
    for token in NUMBER_RE.finditer(ndl_body):
        without = ndl_body[:token.start()] + ndl_body[token.end():]
        if without == windows_body:
            matches.append(token.group())
    return matches[0] if len(matches) == 1 else None


def _tier_value(result):
    if result.tier is not None:
        return result.tier
    return list(result.tier_candidates) if result.tier_candidates else None


def resolve_ndl_numeric_rescue(
    choice: dict,
    ndl_text: str,
    category: str,
) -> dict | None:
    windows_body = stable_missing_number_body(choice)
    if windows_body is None:
        return None
    number = inserted_number(windows_body, ndl_text)
    if number is None:
        return None
    result = resolve_desecration_choices_fuzzy(ndl_text, (category,))[category]
    tier = _tier_value(result)
    if tier is None:
        return None
    return {
        "text": ndl_text,
        "tier": tier,
        "ranges": list(result.range_labels),
        "inserted_number": number,
    }


def _manifest_cases(manifest: Path) -> dict[str, dict]:
    loaded = json.loads(manifest.read_text(encoding="utf-8"))
    return {str(row["file"]): row for row in loaded["cases"]}


def build_report(
    windows_summary: Path,
    ndl_raw: Path,
    plan_path: Path,
    manifest: Path,
) -> dict:
    windows = json.loads(windows_summary.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    ndl_results = load_ndl_results(ndl_raw, plan)
    expected_cases = _manifest_cases(manifest)
    cases = []
    for case in windows.get("cases", []):
        file_name = str(case["file"])
        expected = expected_cases[file_name]
        category = str(expected["category"])
        choices = []
        for offset, windows_choice in enumerate(case.get("choices", [])):
            index = offset + 1
            expected_text = str(expected["expected_texts"][offset])
            expected_tier = expected["expected_tiers"][offset]
            ndl = ndl_results.get((file_name, index))
            windows_tier = windows_choice.get("tier")
            if windows_tier is not None:
                final_text = str(windows_choice.get("selected_text") or "")
                final_tier = windows_tier
                final_ranges = list(windows_choice.get("ranges") or [])
                source = "windows"
                reason = "Windows OCRでTier確定済みのためNDLOCRを使用しない"
            else:
                rescue = resolve_ndl_numeric_rescue(
                    windows_choice,
                    str(ndl["text"]) if ndl else "",
                    category,
                ) if ndl else None
                if rescue is not None:
                    final_text = rescue["text"]
                    final_tier = rescue["tier"]
                    final_ranges = rescue["ranges"]
                    source = "ndl_numeric_rescue"
                    reason = (
                        "Windows OCRの安定本文にNDLOCRが数字"
                        f"{rescue['inserted_number']}だけを補完"
                    )
                else:
                    final_text = str(windows_choice.get("selected_text") or "")
                    final_tier = None
                    final_ranges = []
                    source = "unresolved"
                    reason = (
                        "NDLOCR結果がない"
                        if ndl is None else
                        "数字1個だけの厳格な補完条件を満たさない"
                    )
            text_matches_expected = compact(final_text) == compact(expected_text)
            # The production resolver intentionally tolerates narrowly-scoped
            # Japanese OCR substitutions (for example 回避力 -> 回避カ) when the
            # modifier and numeric range are still unambiguous.  Keep the probe's
            # pass criterion aligned with the existing Windows OCR report: Tier is
            # authoritative, while exact text equality remains visible evidence.
            passed = final_tier == expected_tier
            choices.append({
                "index": index,
                "windows_text": windows_choice.get("selected_text"),
                "windows_tier": windows_tier,
                "windows_status": windows_choice.get("status"),
                "windows_raw_texts": windows_choice.get("raw_texts", []),
                "ndl_text": ndl.get("text") if ndl else None,
                "ndl_confidence": ndl.get("confidence") if ndl else None,
                "source": source,
                "reason": reason,
                "final_text": final_text,
                "final_tier": final_tier,
                "ranges": final_ranges,
                "expected_text": expected_text,
                "expected_tier": expected_tier,
                "text_matches_expected": text_matches_expected,
                "passed": passed,
            })
        cases.append({
            "file": file_name,
            "category": category,
            "passed": all(choice["passed"] for choice in choices),
            "choices": choices,
        })
    all_choices = [choice for case in cases for choice in case["choices"]]
    return {
        "schema_version": 1,
        "engines": ["Windows.Media.Ocr", "NDLOCR-Lite 1.3.1"],
        "policy": "windows_authoritative_ndl_numeric_rescue_only",
        "case_count": len(cases),
        "passed_cases": sum(case["passed"] for case in cases),
        "choice_count": len(all_choices),
        "passed_choices": sum(choice["passed"] for choice in all_choices),
        "ndl_candidate_count": int(plan.get("candidate_count", 0)),
        "ndl_rescue_count": sum(
            choice["source"] == "ndl_numeric_rescue" for choice in all_choices
        ),
        "all_expected_passed": bool(cases) and all(case["passed"] for case in cases),
        "cases": cases,
    }


def render_html(report: dict) -> str:
    cards = []
    for case in report["cases"]:
        rows = []
        for choice in case["choices"]:
            state = "PASS" if choice["passed"] else "FAIL"
            ndl_text = choice["ndl_text"] or "（未実行）"
            confidence = choice["ndl_confidence"]
            confidence_text = "—" if confidence is None else f"{confidence:.3f}"
            rows.append(
                f"<section class='choice'><h3>選択肢 {choice['index']} — {state}</h3>"
                f"<p><b>採用元:</b> {html.escape(choice['source'])}</p>"
                f"<p><b>理由:</b> {html.escape(choice['reason'])}</p>"
                f"<p><b>Windows:</b><br><code>{html.escape(str(choice['windows_text'] or '（空）'))}</code>"
                f" / Tier {html.escape(str(choice['windows_tier']))}</p>"
                f"<p><b>NDLOCR:</b> confidence {confidence_text}<br>"
                f"<code>{html.escape(str(ndl_text))}</code></p>"
                f"<p><b>最終:</b><br><code>{html.escape(str(choice['final_text'] or '（空）'))}</code>"
                f" / Tier {html.escape(str(choice['final_tier']))}</p>"
                f"<p><b>期待:</b><br><code>{html.escape(choice['expected_text'])}</code>"
                f" / Tier {html.escape(str(choice['expected_tier']))}</p></section>"
            )
        state = "PASS" if case["passed"] else "FAIL"
        cards.append(
            f"<article><h2>{html.escape(case['file'])} — {state}</h2>"
            f"{''.join(rows)}</article>"
        )
    return f"""<!doctype html><html lang="ja"><meta charset="utf-8">
<title>Windows OCR + NDLOCR 合成検証</title><style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#17191d;color:#eee}}
article{{border:1px solid #555;border-radius:10px;padding:18px;margin:0 0 24px}}
.choice{{border-top:1px solid #444;margin-top:16px}}code{{white-space:pre-wrap;color:#bde6a3}}
</style><h1>Windows OCR + NDLOCR 合成検証</h1>
<p>{report['passed_cases']}/{report['case_count']}画像、
{report['passed_choices']}/{report['choice_count']}Mod成功。</p>
<p>NDLOCR実行候補 {report['ndl_candidate_count']}件、採用 {report['ndl_rescue_count']}件。</p>
<p>Windows OCRでTier確定した結果は上書きせず、安定本文から数字だけ欠けた行に限ってNDLOCRを使います。</p>
{''.join(cards)}
<footer><p>NDLOCR-Lite 1.3.1 (CC BY 4.0):
<a href="https://github.com/ndl-lab/ndlocr-lite">ndl-lab/ndlocr-lite</a></p></footer></html>"""


def write_report(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (output_dir / "report.html").write_text(
        render_html(report), encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Windows OCRを主系統にしたNDLOCR数字補完を独立検証します。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--windows-summary", type=Path, required=True)
    prepare.add_argument("--input-dir", type=Path, required=True)
    prepare.add_argument("--ndl-input", type=Path, required=True)
    prepare.add_argument("--plan", type=Path, required=True)
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--windows-summary", type=Path, required=True)
    report_parser.add_argument("--ndl-raw", type=Path, required=True)
    report_parser.add_argument("--plan", type=Path, required=True)
    report_parser.add_argument("--manifest", type=Path, required=True)
    report_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        plan = prepare_ndl_inputs(
            args.windows_summary, args.input_dir, args.ndl_input, args.plan,
        )
        print(json.dumps(plan, ensure_ascii=False))
        return 0
    report = build_report(
        args.windows_summary, args.ndl_raw, args.plan, args.manifest,
    )
    write_report(report, args.output)
    print(json.dumps({
        key: report[key] for key in (
            "case_count", "passed_cases", "choice_count", "passed_choices",
            "ndl_candidate_count", "ndl_rescue_count",
        )
    }, ensure_ascii=False))
    return 0 if report["all_expected_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
