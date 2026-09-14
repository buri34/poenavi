import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).parents[1]
    / "scripts"
    / "audit_poetore_poe2_desecration_update.py"
)
SPEC = importlib.util.spec_from_file_location("audit_desecration_update", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def payload(revision="old", profile_id="p000", entries=None, unparsed=None):
    return {
        "schema_version": 1,
        "source": {"pob2_revision": revision},
        "profiles": [{"id": profile_id, "category": "ring", "tags": ["ring"]}],
        "entries": entries or [],
        "diagnostics": {
            "fully_matchable_rows": len(entries or []),
            "rows_with_unparsed_parts": unparsed or [],
            "numeric_skeleton_collisions": [],
        },
    }


def entry(mod_id="Life1", profile_id="p000", tier=1, value=10):
    return {
        "mod_id": mod_id,
        "pool": "normal",
        "type": "Prefix",
        "group": "Life",
        "required_level": 1,
        "profile_tiers": {profile_id: tier},
        "parts": [{
            "stat_hash": "1",
            "stat_id": "desecrated.stat_1",
            "text": {"en": "+# to Life", "ja": "最大ライフ +#"},
            "ranges": [[value, value]],
            "source_text": f"+{value} to Life",
        }],
    }


def test_profile_ids_are_not_treated_as_semantic_changes():
    before = payload(entries=[entry()])
    after = payload(
        revision="new", profile_id="p999",
        entries=[entry(profile_id="p999")],
    )
    report = MODULE.compare_payloads(before, after)
    assert report["summary"] == {
        "profiles_added": 0,
        "profiles_removed": 0,
        "mods_added": 0,
        "mods_removed": 0,
        "mods_changed": 0,
        "new_unparsed_rows": 0,
        "resolved_unparsed_rows": 0,
        "numeric_skeleton_collisions": 0,
    }
    assert not report["requires_review"]


def test_report_separates_added_removed_changed_and_unparsed_rows():
    before = payload(
        entries=[entry("Changed"), entry("Removed")],
        unparsed=["Resolved"],
    )
    after = payload(
        revision="new",
        entries=[entry("Changed", tier=2), entry("Added")],
        unparsed=["NewBroken"],
    )
    report = MODULE.compare_payloads(before, after)
    assert report["summary"]["mods_added"] == 1
    assert report["summary"]["mods_removed"] == 1
    assert report["summary"]["mods_changed"] == 1
    assert report["summary"]["new_unparsed_rows"] == 1
    assert report["summary"]["resolved_unparsed_rows"] == 1
    assert report["changes"]["mods_added"] == ["Added"]
    assert report["changes"]["mods_removed"] == ["Removed"]
    assert report["changes"]["mods_changed"][0]["fields"] == ["profile_tiers"]
    assert report["requires_review"]


def test_validation_rejects_missing_profile_references():
    broken = payload(entries=[entry(profile_id="missing")])
    with pytest.raises(ValueError, match="missing profiles"):
        MODULE.compare_payloads(payload(), broken)


def test_audit_refuses_to_overwrite_production_baseline(tmp_path):
    baseline = tmp_path / "production.json"
    with pytest.raises(ValueError, match="must not overwrite"):
        MODULE.audit(
            tmp_path, "revision", baseline, tmp_path / "report.json", baseline,
        )


def test_audit_refuses_to_write_report_over_production_baseline(tmp_path):
    baseline = tmp_path / "production.json"
    with pytest.raises(ValueError, match="report output must not overwrite"):
        MODULE.audit(tmp_path, "revision", baseline, baseline)


def test_current_production_payload_compares_equal_to_itself():
    current = MODULE.load_payload(MODULE.DEFAULT_BASELINE)
    report = MODULE.compare_payloads(current, current)
    assert not report["requires_review"]
    assert not any(report["summary"].values())
