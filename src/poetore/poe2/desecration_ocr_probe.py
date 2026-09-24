"""Offline-image probe for the production Desecration Windows OCR pipeline."""

from __future__ import annotations

import html
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PySide6.QtGui import QImage

from src.poetore.expedition_ocr_probe import WindowsOcrServer
from src.poetore.poe2.desecration_ocr import (
    image_bytes,
    prepare_desecration_frame,
    resolve_ocr_variants,
)
from src.poetore.poe2.desecration_overlay import selectable_categories

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".webp"})


class OcrServer(Protocol):
    def start(self) -> None: ...

    def recognize(self, images: list[bytes]) -> list[str]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ProbeCase:
    image: Path
    category: str | None = None
    expected_texts: tuple[str, ...] = ()
    expected_tiers: tuple[int | tuple[int, ...] | None, ...] = ()


def _tier_from_json(value) -> int | tuple[int, ...] | None:
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, list) and all(isinstance(item, int) for item in value):
        return tuple(value)
    raise ValueError(f"Invalid expected tier: {value!r}")


def load_probe_cases(input_dir: Path, manifest: Path | None = None) -> tuple[ProbeCase, ...]:
    input_dir = input_dir.resolve()
    if manifest is None:
        return tuple(
            ProbeCase(image=path)
            for path in sorted(input_dir.iterdir())
            if path.is_file() and path.suffix.casefold() in IMAGE_SUFFIXES
        )
    loaded = json.loads(manifest.read_text(encoding="utf-8"))
    rows = loaded.get("cases") if isinstance(loaded, dict) else None
    if not isinstance(rows, list):
        raise TypeError("Probe manifest must contain a cases list.")
    cases = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("file"), str):
            raise TypeError("Every probe case must contain a file name.")
        image = (input_dir / row["file"]).resolve()
        if input_dir not in image.parents or not image.is_file():
            raise ValueError(f"Probe image was not found inside the input directory: {image}")
        expected_texts = tuple(str(value) for value in row.get("expected_texts", ()))
        expected_tiers = tuple(_tier_from_json(value) for value in row.get("expected_tiers", ()))
        if expected_texts and len(expected_texts) != 3:
            raise ValueError(f"Expected exactly three texts for {image.name}.")
        if expected_tiers and len(expected_tiers) != 3:
            raise ValueError(f"Expected exactly three tiers for {image.name}.")
        category = row.get("category")
        cases.append(ProbeCase(
            image=image,
            category=str(category) if category else None,
            expected_texts=expected_texts,
            expected_tiers=expected_tiers,
        ))
    return tuple(cases)


def _json_tier(value):
    return list(value) if isinstance(value, tuple) else value


def _selected_rows(resolution, category: str | None):
    if category and category in resolution.categories:
        return (
            resolution.tiers_by_category[category],
            resolution.texts_by_category[category],
            resolution.ranges_by_category[category],
            resolution.statuses_by_category[category],
        )
    return (
        resolution.fallback_tiers,
        resolution.fallback_texts,
        resolution.fallback_ranges,
        resolution.fallback_statuses,
    )


def _write_html(report: dict, output_dir: Path) -> None:
    cards = []
    for case in report["cases"]:
        choice_rows = []
        for choice in case["choices"]:
            variants = "".join(
                "<li><strong>候補{}</strong><pre>{}</pre>"
                "<img src=\"{}\" alt=\"OCR候補画像\"></li>".format(
                    index + 1,
                    html.escape(text or "（空）"),
                    html.escape(choice["prepared_images"][index]),
                )
                for index, text in enumerate(choice["raw_texts"])
            )
            expected = choice.get("expected_tier", "未指定")
            actual = choice.get("tier")
            choice_rows.append(
                "<section class=\"choice\"><h3>選択肢 {}</h3>"
                "<p>判定: <strong>{}</strong> / 状態: {} / 期待値: {}</p>"
                "<p>採用文字列: {}</p><ul>{}</ul></section>".format(
                    choice["index"], html.escape(str(actual)),
                    html.escape(choice["status"]), html.escape(str(expected)),
                    html.escape(choice["selected_text"] or "（空）"), variants,
                )
            )
        state = "PASS" if case.get("passed") is True else (
            "FAIL" if case.get("passed") is False else "NO EXPECTATION"
        )
        cards.append(
            "<article><h2>{} — {}</h2><p>部位: {} / パネル検出: {}</p>"
            "<img class=\"source\" src=\"{}\" alt=\"入力画像\">{}</article>".format(
                html.escape(case["file"]), state,
                html.escape(case.get("category") or "未指定"),
                "成功" if case["valid_panel"] else "失敗",
                html.escape(case["source_image"]), "".join(choice_rows),
            )
        )
    document = """<!doctype html><html lang="ja"><meta charset="utf-8">
<title>アビス冒涜 Windows OCR検証</title><style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#17191d;color:#eee}}
article{{border:1px solid #555;border-radius:10px;padding:18px;margin:0 0 24px}}
.source{{max-width:620px;width:100%}}.choice{{border-top:1px solid #444;margin-top:16px}}
ul{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:0}}
li{{list-style:none;background:#222;padding:10px}}li img{{max-width:100%;background:white}}
pre{{white-space:pre-wrap;color:#bde6a3}}@media(max-width:800px){{ul{{grid-template-columns:1fr}}}}
</style><h1>アビス冒涜 Windows OCR検証</h1>
<p>成功 {passed}/{total}（期待値未指定は集計外）</p>{cards}</html>""".format(
        passed=report["passed_cases"], total=report["expected_cases"],
        cards="".join(cards),
    )
    (output_dir / "report.html").write_text(document, encoding="utf-8")


def run_probe(
    cases: tuple[ProbeCase, ...],
    output_dir: Path,
    *,
    ocr_server: OcrServer | None = None,
    prepare_only: bool = False,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = output_dir / "source"
    prepared_dir = output_dir / "prepared"
    source_dir.mkdir(exist_ok=True)
    prepared_dir.mkdir(exist_ok=True)
    server = ocr_server
    owns_server = server is None and not prepare_only
    if owns_server:
        server = WindowsOcrServer()
    if server is not None and not prepare_only:
        server.start()
    results = []
    try:
        for case in cases:
            source_name = case.image.name
            copied_source = source_dir / source_name
            shutil.copy2(case.image, copied_source)
            frame = prepare_desecration_frame(QImage(str(case.image)))
            raw_grouped: tuple[tuple[str, ...], ...] = ()
            prepared_paths: list[tuple[str, ...]] = []
            if frame.valid_panel:
                flat_images = []
                for choice_index, variants in enumerate(frame.variants, 1):
                    choice_paths = []
                    for variant_index, image in enumerate(variants, 1):
                        name = f"{case.image.stem}-choice-{choice_index}-variant-{variant_index}.png"
                        destination = prepared_dir / name
                        if not image.save(str(destination), "PNG"):
                            raise RuntimeError(f"Failed to save prepared image: {destination}")
                        choice_paths.append(destination.relative_to(output_dir).as_posix())
                        flat_images.append(image_bytes(image))
                    prepared_paths.append(tuple(choice_paths))
                if not prepare_only and server is not None:
                    raw = server.recognize(flat_images)
                    width = len(frame.variants[0])
                    raw_grouped = tuple(
                        tuple(raw[index * width:(index + 1) * width])
                        for index in range(3)
                    )
            resolution = None
            if raw_grouped:
                resolution = resolve_ocr_variants(raw_grouped, selectable_categories())
                tiers, texts, ranges, statuses = _selected_rows(resolution, case.category)
            else:
                tiers, texts, ranges, statuses = (
                    (None,) * 3, ("",) * 3, ((),) * 3,
                    (("not_run",) * 3 if prepare_only else ("read_failed",) * 3),
                )
            choices = []
            for index in range(3):
                expected = case.expected_tiers[index] if case.expected_tiers else None
                choices.append({
                    "index": index + 1,
                    "raw_texts": list(raw_grouped[index]) if raw_grouped else [],
                    "selected_text": texts[index],
                    "tier": _json_tier(tiers[index]),
                    "status": statuses[index],
                    "ranges": list(ranges[index]),
                    "expected_text": case.expected_texts[index] if case.expected_texts else None,
                    "expected_tier": _json_tier(expected),
                    "prepared_images": list(prepared_paths[index]) if prepared_paths else [],
                })
            passed = None
            if case.expected_tiers and not prepare_only:
                passed = all(
                    choices[index]["tier"] == _json_tier(case.expected_tiers[index])
                    for index in range(3)
                )
            results.append({
                "file": source_name,
                "category": case.category,
                "valid_panel": frame.valid_panel,
                "source_image": copied_source.relative_to(output_dir).as_posix(),
                "resolved_categories": list(resolution.categories) if resolution else [],
                "passed": passed,
                "choices": choices,
            })
    finally:
        if server is not None:
            server.close()
    expected_results = [row for row in results if row["passed"] is not None]
    report = {
        "schema_version": 1,
        "engine": "Windows.Media.Ocr" if not prepare_only else "prepare-only",
        "case_count": len(results),
        "expected_cases": len(expected_results),
        "passed_cases": sum(row["passed"] is True for row in expected_results),
        "all_expected_passed": bool(expected_results) and all(
            row["passed"] is True for row in expected_results
        ),
        "cases": results,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    _write_html(report, output_dir)
    return report
