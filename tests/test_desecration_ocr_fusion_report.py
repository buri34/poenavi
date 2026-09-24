from __future__ import annotations

import json
from pathlib import Path

from scripts.desecration_ocr_fusion_report import (
    build_report,
    inserted_number,
    prepare_ndl_inputs,
    resolve_ndl_numeric_rescue,
    stable_missing_number_body,
)

FIXTURES = Path(__file__).parent / "fixtures" / "poetore" / "poe2" / "desecration"


def _choice(*, text: str, tier=None, status="read_failed", raw_texts=None):
    return {
        "index": 1,
        "selected_text": text,
        "tier": tier,
        "status": status,
        "ranges": [],
        "raw_texts": raw_texts or [text] * 4,
    }


def test_stable_missing_number_body_accepts_katakana_dash_variants():
    choice = _choice(
        text="物 理 ダ メ ー ジ が % 増 加 す る",
        raw_texts=[
            "物 理 ダ メ ー ジ が % 増 加 す る",
            "物 理 ダ メ ー ジ が % 増 加 す る",
            "物 理 ダ メ - ジ が % 増 加 す る",
            "物 理 ダ メ - ジ が % 増 加 す る",
        ],
    )

    assert stable_missing_number_body(choice) == "物理ダメージが%増加する"


def test_stable_missing_number_body_rejects_success_and_unstable_variants():
    assert stable_missing_number_body(
        _choice(text="物理ダメージが51%増加する", tier=1, status="matched"),
    ) is None
    assert stable_missing_number_body(
        _choice(
            text="物理ダメージが%増加する",
            raw_texts=[
                "物理ダメージが%増加する",
                "物理ダメージが64%増加する",
                "物理ダメージが%増加する",
                "物理ダメージが%増加する",
            ],
        ),
    ) is None


def test_inserted_number_requires_exactly_one_numeric_insertion():
    assert inserted_number(
        "物理ダメージが%増加する",
        "物理ダメージが64%増加する",
    ) == "64"
    assert inserted_number(
        "ダメージが51%増加する",
        "ダメージが5196増加する",
    ) is None
    assert inserted_number(
        "物理ダメージが%増加する",
        "物理ダメージが64%増加する75",
    ) is None


def test_ndl_rescue_requires_valid_tier_after_exact_insertion():
    choice = _choice(text="物理ダメージが%増加する")

    rescued = resolve_ndl_numeric_rescue(
        choice, "物理ダメージが64%増加する", "spear",
    )

    assert rescued is not None
    assert rescued["tier"] == 7
    assert rescued["inserted_number"] == "64"
    assert resolve_ndl_numeric_rescue(
        choice, "物理ダメージが999%増加する", "spear",
    ) is None


def test_prepare_ndl_inputs_only_crops_unresolved_stable_choice(tmp_path):
    summary = {
        "cases": [{
            "file": "reported-spear-physical-read-failed.png",
            "choices": [
                _choice(text="物理ダメージが%増加する"),
                _choice(text="1から4の雷ダメージを追加する", tier=10, status="matched"),
                _choice(
                    text="物理ダメージが24%増加する\n命中力 +41",
                    tier=7,
                    status="matched",
                ),
            ],
        }],
    }
    summary_path = tmp_path / "windows.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")

    plan = prepare_ndl_inputs(
        summary_path, FIXTURES, tmp_path / "ndl-input", tmp_path / "plan.json",
    )

    assert plan["candidate_count"] == 1
    assert plan["candidates"][0]["choice_index"] == 1
    assert (tmp_path / "ndl-input" / plan["candidates"][0]["crop"]).is_file()


def test_build_report_keeps_windows_success_and_uses_ndl_only_for_gap(tmp_path):
    windows = {
        "cases": [
            {
                "file": "physical.png",
                "choices": [_choice(text="物理ダメージが%増加する")],
            },
            {
                "file": "companion.png",
                "choices": [_choice(
                    text="コンパニオンの存在下にいる時にダメージが51%増加する",
                    tier=1,
                    status="matched",
                )],
            },
        ],
    }
    manifest = {
        "cases": [
            {
                "file": "physical.png",
                "category": "spear",
                "expected_texts": ["物理ダメージが64%増加する"],
                "expected_tiers": [7],
            },
            {
                "file": "companion.png",
                "category": "spear",
                "expected_texts": [
                    "コンパニオンの存在下にいる時にダメージが51%増加する",
                ],
                "expected_tiers": [1],
            },
        ],
    }
    plan = {
        "candidate_count": 2,
        "candidates": [
            {
                "file": "physical.png",
                "choice_index": 1,
                "crop": "physical-choice-1.png",
                "windows_body": "物理ダメージが%増加する",
            },
            {
                "file": "companion.png",
                "choice_index": 1,
                "crop": "companion-choice-1.png",
                "windows_body": "コンパニオンの存在下にいる時にダメージが51%増加する",
            },
        ],
    }
    windows_path = tmp_path / "windows.json"
    manifest_path = tmp_path / "manifest.json"
    plan_path = tmp_path / "plan.json"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    windows_path.write_text(json.dumps(windows, ensure_ascii=False), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    (raw_dir / "physical-choice-1.json").write_text(json.dumps({
        "contents": [[{
            "boundingBox": [[0, 0], [0, 10], [100, 0], [100, 10]],
            "text": "物理ダメージが64%増加する",
            "confidence": 0.878,
        }]],
    }, ensure_ascii=False), encoding="utf-8")
    (raw_dir / "companion-choice-1.json").write_text(json.dumps({
        "contents": [[{
            "boundingBox": [[0, 0], [0, 10], [100, 0], [100, 10]],
            "text": "コンパニオンの存在下にいる時にダメージが5196増加する",
            "confidence": 0.494,
        }]],
    }, ensure_ascii=False), encoding="utf-8")

    report = build_report(windows_path, raw_dir, plan_path, manifest_path)

    assert report["all_expected_passed"] is True
    assert report["passed_choices"] == 2
    assert report["ndl_candidate_count"] == 2
    assert report["ndl_rescue_count"] == 1
    assert report["cases"][0]["choices"][0]["source"] == "ndl_numeric_rescue"
    assert report["cases"][1]["choices"][0]["source"] == "windows"
    assert report["cases"][1]["choices"][0]["ndl_text"].endswith("5196増加する")
    assert report["cases"][1]["choices"][0]["final_text"].endswith("51%増加する")


def test_reported_manifest_uses_actual_one_to_four_and_tier_ten():
    manifest = json.loads(
        (FIXTURES / "reported-cases.json").read_text(encoding="utf-8"),
    )
    spear = next(
        row for row in manifest["cases"]
        if row["file"] == "reported-spear-physical-read-failed.png"
    )

    assert spear["expected_texts"][1] == "1から4の雷ダメージを追加する"
    assert spear["expected_tiers"][1] == 10
