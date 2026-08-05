import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.build_poetore_metadata import _run_regression_tests
from scripts.update_poetore_trade_data import (
    atomic_apply_manifest,
    audit_bilingual_items,
    audit_bilingual_stats,
    build_pseudo_relations_candidate,
    diff_pseudo_relations,
    sha256_file,
    verify_manifest,
    verify_representative_trade_api,
)


def test_bilingual_items_ignore_entry_order_but_detect_structure_difference():
    english = {"result": [{"id": "gem", "entries": [
        {"type": "Fireball"},
        {"type": "Vaal Fireball", "disc": "vaal"},
    ]}]}
    japanese = {"result": [{"id": "gem", "entries": [
        {"type": "ヴァールファイヤーボール", "disc": "vaal"},
        {"type": "ファイヤーボール"},
    ]}]}
    assert audit_bilingual_items(english, japanese)["structure_mismatches"] == []

    japanese["result"][0]["entries"].pop()
    assert audit_bilingual_items(english, japanese)["structure_mismatches"][0]["group"] == "gem"


def test_bilingual_stats_compare_ids_types_and_option_ids_not_translation():
    english = {"result": [{"id": "explicit", "entries": [
        {"id": "explicit.one", "text": "One", "type": "explicit",
         "option": {"options": [{"id": 1, "text": "A"}]}},
        {"id": "explicit.english_only", "text": "Only", "type": "explicit"},
    ]}]}
    japanese = {"result": [{"id": "explicit", "entries": [
        {"id": "explicit.one", "text": "一", "type": "implicit",
         "option": {"options": [{"id": 2, "text": "乙"}]}},
    ]}]}
    result = audit_bilingual_stats(english, japanese)
    assert result["english_only"] == ["explicit.english_only"]
    assert result["option_mismatches"][0]["id"] == "explicit.one"
    assert result["type_mismatches"][0]["id"] == "explicit.one"


def _manifest(root: Path, targets: dict[str, tuple[Path, Path]]) -> Path:
    rows = {}
    for name, (target, candidate) in targets.items():
        rows[name] = {
            "target": str(target.relative_to(root)),
            "candidate": str(candidate.relative_to(root)),
            "base_sha256": sha256_file(target),
            "candidate_sha256": sha256_file(candidate),
        }
    path = root / "manifest.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "mode": "refresh",
        "root": str(root),
        "files": rows,
    }), encoding="utf-8")
    return path


def test_manifest_rejects_candidate_tampering_and_authoritative_changes(tmp_path):
    target = tmp_path / "target.json"
    candidate = tmp_path / "candidate.json"
    target.write_text("old", encoding="utf-8")
    candidate.write_text("new", encoding="utf-8")
    manifest = _manifest(tmp_path, {"data": (target, candidate)})
    verify_manifest(manifest, tmp_path)

    candidate.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="candidate file hash mismatch"):
        verify_manifest(manifest, tmp_path)
    candidate.write_text("new", encoding="utf-8")
    target.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="authoritative file changed"):
        verify_manifest(manifest, tmp_path)


def test_atomic_apply_rolls_back_all_files_when_replace_fails(tmp_path):
    targets = {}
    for index in range(2):
        target = tmp_path / f"target-{index}.json"
        candidate = tmp_path / f"candidate-{index}.json"
        target.write_text(f"old-{index}", encoding="utf-8")
        candidate.write_text(f"new-{index}", encoding="utf-8")
        targets[str(index)] = (target, candidate)
    manifest = _manifest(tmp_path, targets)
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated replace failure")
        Path(source).replace(target)

    with pytest.raises(OSError, match="simulated"):
        atomic_apply_manifest(manifest, tmp_path, replace=fail_second)
    assert (tmp_path / "target-0.json").read_text() == "old-0"
    assert (tmp_path / "target-1.json").read_text() == "old-1"


def test_atomic_apply_replaces_every_reviewed_file(tmp_path):
    targets = {}
    for index in range(2):
        target = tmp_path / f"target-{index}.json"
        candidate = tmp_path / f"candidate-{index}.json"
        target.write_text(f"old-{index}", encoding="utf-8")
        candidate.write_text(f"new-{index}", encoding="utf-8")
        targets[str(index)] = (target, candidate)
    manifest = _manifest(tmp_path, targets)
    applied = atomic_apply_manifest(manifest, tmp_path)
    assert len(applied) == 2
    assert (tmp_path / "target-0.json").read_text() == "new-0"
    assert (tmp_path / "target-1.json").read_text() == "new-1"


def test_external_candidate_does_not_claim_distribution_data_file(tmp_path):
    candidate = tmp_path / "mod_metadata.json"
    candidate.write_text("{}", encoding="utf-8")
    captured = {}

    def run(_command, **kwargs):
        captured.update(kwargs["env"])

    with patch("scripts.build_poetore_metadata.subprocess.run", side_effect=run):
        _run_regression_tests(candidate)
    assert captured["POETORE_METADATA_PATH"] == str(candidate.resolve())
    assert "POETORE_CANDIDATE_BUILD" not in captured


def test_representative_api_verifier_reports_success_and_failure():
    cases = [
        {
            "id": "ok", "trade_base": "Fireball",
            "text": "Item Class: Skill Gems\nRarity: Gem\nFireball\n--------\nLevel: 1",
        },
        {
            "id": "bad", "trade_base": "Fireball",
            "text": "Item Class: Skill Gems\nRarity: Gem\nFireball\n--------\nLevel: 1",
        },
    ]
    responses = iter(({"id": "query-1", "result": ["a"]}, {"error": "rejected"}))
    result = verify_representative_trade_api(
        cases=cases, sender=lambda _url, _payload: next(responses), pause=lambda _value: None,
    )
    assert result["passed"] == [{"id": "ok", "query_id": "query-1", "candidates": 1}]
    assert result["failures"] == [{"id": "bad", "error": "rejected"}]


def test_fixed_awakened_archive_reproduces_pseudo_relations():
    root = Path(__file__).parents[1]
    generated = build_pseudo_relations_candidate(
        root / "vendor-sources/awakened-poe-trade-31b3e0e8.tar.gz",
        "31b3e0e8ba0a6bac2266603c2e170925c8f02b81",
    )
    current = json.loads(
        (root / "data/poetore/pseudo_relations.json").read_text(encoding="utf-8")
    )
    assert generated["relations"] == current["relations"]


def test_pseudo_diff_reports_added_removed_and_changed_rows():
    old = {"relations": [
        {"pseudo_ref": "same", "stat_id": "1"},
        {"pseudo_ref": "changed", "stat_id": "2"},
        {"pseudo_ref": "removed", "stat_id": "3"},
    ]}
    new = {"relations": [
        {"pseudo_ref": "same", "stat_id": "1"},
        {"pseudo_ref": "changed", "stat_id": "4"},
        {"pseudo_ref": "added", "stat_id": "5"},
    ]}
    result = diff_pseudo_relations(old, new)
    assert [row["pseudo_ref"] for row in result["added"]] == ["added"]
    assert [row["pseudo_ref"] for row in result["removed"]] == ["removed"]
    assert [row["pseudo_ref"] for row in result["changed"]] == ["changed"]
