import csv
from pathlib import Path


AUDIT_CSV = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "poetore-awakened-filter-rule-audit.csv"
)


def test_awakened_filter_rule_audit_has_valid_reviewable_rows():
    with AUDIT_CSV.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    expected_columns = {
        "rule_id",
        "大分類",
        "対象",
        "Awakened仕様",
        "ぽえとれ現状",
        "判定",
        "推奨",
        "鰤さん判断欄",
        "Awakened根拠",
        "ぽえとれ根拠",
    }
    assert rows
    assert set(rows[0]) == expected_columns
    assert len(rows) >= 80
    assert len({row["rule_id"] for row in rows}) == len(rows)

    allowed_statuses = {
        "準拠",
        "部分準拠",
        "差分・判断必要",
        "独自仕様",
        "未対応",
        "対象外",
    }
    for row in rows:
        assert not row.get(None)
        assert row["判定"] in allowed_statuses
        assert all(
            row[column].strip()
            for column in expected_columns - {"鰤さん判断欄"}
        )


def test_awakened_filter_rule_audit_keeps_decision_rows_visible():
    with AUDIT_CSV.open(encoding="utf-8", newline="") as stream:
        rows = {row["rule_id"]: row for row in csv.DictReader(stream)}

    expected_review_rows = {
        "S07",  # Map explicit Mod defaults
        "R02",  # Hybrid armour properties
    }
    assert expected_review_rows <= rows.keys()
    assert all(rows[rule_id]["鰤さん判断欄"] == "要判断"
               for rule_id in expected_review_rows)
