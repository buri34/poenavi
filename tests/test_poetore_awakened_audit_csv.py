import csv
from pathlib import Path


AUDIT_CSV = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "poetore-awakened-filter-rule-audit.csv"
)


def _rows():
    with AUDIT_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_awakened_audit_has_unique_granular_rule_ids():
    rows = _rows()
    rule_ids = [row["rule_id"] for row in rows]

    assert len(rows) >= 120
    assert len(rule_ids) == len(set(rule_ids))
    assert {
        "I14a",
        "I21a",
        "I21b",
        "I21c",
        "I21d",
        "I28",
        "R11",
        "R12",
        "C01a",
        "C01h",
    } <= set(rule_ids)


def test_awakened_audit_tracks_resolved_and_remaining_differences():
    rows = {row["rule_id"]: row for row in _rows()}

    for rule_id in ("I14a", "S18", "S19", "S20", "R11", "R12"):
        assert rows[rule_id]["判定"] == "準拠"
        assert rows[rule_id]["鰤さん判断欄"] == ""
    assert rows["I28"]["判定"] == "未対応"
    assert rows["I28"]["鰤さん判断欄"] == "要対応"
