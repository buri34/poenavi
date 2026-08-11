from __future__ import annotations

import csv
import json

from pathlib import Path

from src.poetore.poe2.audit import audit_real_copy_pairs, build_audit_rows, write_reports


REAL_COPY_FIXTURES = Path(__file__).parent / "fixtures" / "poe2" / "real_copy_bilingual.csv"


def test_poe2_search_matrix_has_complete_structural_population():
    rows = build_audit_rows()
    categories = {row.category for row in rows}
    assert len(categories) == 27
    assert len(rows) == 351
    assert sum(row.status == "自動検証済み" for row in rows) == 297
    assert sum(row.status == "仕様上対象外" for row in rows) == 54
    assert not any(row.status == "不具合" for row in rows)


def test_poe2_search_matrix_validates_final_trade2_identity_and_stats():
    rows = {row.case_id: row for row in build_audit_rows()}
    exact = rows["bow:rare:finished:exact"]
    assert (exact.observed_trade_category, exact.observed_type) == (
        "weapon.bow", "Rider Bow",
    )
    assert (exact.observed_rarity, exact.observed_stat_count) == ("nonunique", 1)
    broad = rows["bow:rare:base:class"]
    assert (broad.observed_type, broad.observed_stat_count) == ("", 0)
    unique = rows["focus:unique:finished:exact"]
    assert (unique.observed_name, unique.observed_rarity) == ("Synthetic Unique", "")


def test_poe2_search_matrix_reports_are_machine_readable(tmp_path):
    csv_path, json_path, rows = write_reports(tmp_path)
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(csv_rows) == len(rows)
    assert payload["counts"] == {
        "自動検証済み": 297,
        "仕様上対象外": 54,
        "不具合": 0,
    }
    assert len(payload["rows"]) == len(rows)
    assert payload["real_copy_counts"] == {
        "自動検証済み": 23,
        "実コピー待ち": 5,
        "不具合": 0,
    }


def test_poe2_real_copy_pairs_are_audited_without_overclaiming_missing_samples():
    rows = audit_real_copy_pairs(REAL_COPY_FIXTURES)
    assert len(rows) == 28
    assert sum(row["audit_status"] == "自動検証済み" for row in rows) == 23
    assert sum(row["audit_status"] == "実コピー待ち" for row in rows) == 5
    assert not any(row["audit_status"] == "不具合" for row in rows)
    flail = next(row for row in rows if row["fixture_id"] == "FX002")
    assert flail["audit_status"] == "自動検証済み"
    assert (flail["ja_base_type"], flail["en_base_type"]) == (
        "Chain Flail", "Chain Flail",
    )
