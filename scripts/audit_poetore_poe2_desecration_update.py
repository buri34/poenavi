#!/usr/bin/env python3
"""Build and compare a candidate PoE2 Desecration tier database safely."""

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "data" / "poetore" / "poe2" / "desecration_tiers.json"
BUILDER_PATH = ROOT / "scripts" / "build_poetore_poe2_desecration_tiers.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("desecration_tier_builder", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load builder: {BUILDER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_payload(payload: dict[str, Any], label: str) -> None:
    if payload.get("schema_version") != 1:
        raise ValueError(f"{label}: unsupported schema_version")
    profiles = payload.get("profiles")
    entries = payload.get("entries")
    if not isinstance(profiles, list) or not isinstance(entries, list):
        raise TypeError(f"{label}: profiles/entries must be lists")
    profile_ids = [str(row.get("id", "")) for row in profiles]
    if not all(profile_ids) or len(profile_ids) != len(set(profile_ids)):
        raise ValueError(f"{label}: missing or duplicate profile ids")
    mod_ids = [str(row.get("mod_id", "")) for row in entries]
    if not all(mod_ids) or len(mod_ids) != len(set(mod_ids)):
        raise ValueError(f"{label}: missing or duplicate mod ids")
    known_profiles = set(profile_ids)
    for row in entries:
        referenced = set(row.get("profile_tiers", {}))
        missing = sorted(referenced - known_profiles)
        if missing:
            raise ValueError(
                f"{label}: {row['mod_id']} references missing profiles: {missing}"
            )


def profile_signature(profile: dict[str, Any]) -> str:
    category = str(profile.get("category", ""))
    tags = ",".join(sorted(str(tag) for tag in profile.get("tags", ())))
    return f"{category}|{tags}"


def canonical_entry(
    entry: dict[str, Any], profile_by_id: dict[str, str],
) -> dict[str, Any]:
    profile_tiers = [
        {"profile": profile_by_id[profile_id], "tier": tier}
        for profile_id, tier in entry.get("profile_tiers", {}).items()
    ]
    profile_tiers.sort(key=lambda row: (row["profile"], row["tier"]))
    parts = sorted(
        entry.get("parts", ()),
        key=lambda row: (
            str(row.get("stat_hash", "")),
            str(row.get("source_text", "")),
        ),
    )
    return {
        "pool": entry.get("pool"),
        "type": entry.get("type"),
        "group": entry.get("group"),
        "required_level": entry.get("required_level"),
        "profile_tiers": profile_tiers,
        "parts": parts,
    }


def _diagnostic_ids(payload: dict[str, Any], key: str) -> set[str]:
    values = payload.get("diagnostics", {}).get(key, ())
    return {str(value) for value in values} if isinstance(values, list) else set()


def compare_payloads(
    baseline: dict[str, Any], candidate: dict[str, Any],
) -> dict[str, Any]:
    validate_payload(baseline, "baseline")
    validate_payload(candidate, "candidate")

    baseline_profiles = {
        str(row["id"]): profile_signature(row) for row in baseline["profiles"]
    }
    candidate_profiles = {
        str(row["id"]): profile_signature(row) for row in candidate["profiles"]
    }
    baseline_profile_set = set(baseline_profiles.values())
    candidate_profile_set = set(candidate_profiles.values())

    baseline_entries = {
        str(row["mod_id"]): canonical_entry(row, baseline_profiles)
        for row in baseline["entries"]
    }
    candidate_entries = {
        str(row["mod_id"]): canonical_entry(row, candidate_profiles)
        for row in candidate["entries"]
    }
    baseline_ids = set(baseline_entries)
    candidate_ids = set(candidate_entries)
    changed = []
    for mod_id in sorted(baseline_ids & candidate_ids):
        before = baseline_entries[mod_id]
        after = candidate_entries[mod_id]
        fields = [key for key in before if before[key] != after[key]]
        if fields:
            changed.append({
                "mod_id": mod_id,
                "fields": fields,
                "baseline": before,
                "candidate": after,
            })

    unparsed_key = "rows_with_unparsed_parts"
    before_unparsed = _diagnostic_ids(baseline, unparsed_key)
    after_unparsed = _diagnostic_ids(candidate, unparsed_key)
    collisions = candidate.get("diagnostics", {}).get(
        "numeric_skeleton_collisions", []
    )
    result = {
        "schema_version": 1,
        "baseline": {
            "revision": baseline.get("source", {}).get("pob2_revision"),
            "profiles": len(baseline_profiles),
            "entries": len(baseline_entries),
            "fully_matchable_rows": baseline.get("diagnostics", {}).get(
                "fully_matchable_rows"
            ),
        },
        "candidate": {
            "revision": candidate.get("source", {}).get("pob2_revision"),
            "profiles": len(candidate_profiles),
            "entries": len(candidate_entries),
            "fully_matchable_rows": candidate.get("diagnostics", {}).get(
                "fully_matchable_rows"
            ),
        },
        "summary": {
            "profiles_added": len(candidate_profile_set - baseline_profile_set),
            "profiles_removed": len(baseline_profile_set - candidate_profile_set),
            "mods_added": len(candidate_ids - baseline_ids),
            "mods_removed": len(baseline_ids - candidate_ids),
            "mods_changed": len(changed),
            "new_unparsed_rows": len(after_unparsed - before_unparsed),
            "resolved_unparsed_rows": len(before_unparsed - after_unparsed),
            "numeric_skeleton_collisions": len(collisions),
        },
        "changes": {
            "profiles_added": sorted(candidate_profile_set - baseline_profile_set),
            "profiles_removed": sorted(baseline_profile_set - candidate_profile_set),
            "mods_added": sorted(candidate_ids - baseline_ids),
            "mods_removed": sorted(baseline_ids - candidate_ids),
            "mods_changed": changed,
            "new_unparsed_rows": sorted(after_unparsed - before_unparsed),
            "resolved_unparsed_rows": sorted(before_unparsed - after_unparsed),
            "numeric_skeleton_collisions": collisions,
        },
    }
    result["requires_review"] = any(result["summary"].values())
    return result


def audit(
    pob2: Path,
    expected_revision: str,
    baseline_path: Path,
    report_path: Path,
    candidate_output: Path | None = None,
    stat_index: Path | None = None,
) -> dict[str, Any]:
    baseline_path = baseline_path.resolve()
    report_path = report_path.resolve()
    if report_path == baseline_path:
        raise ValueError("report output must not overwrite the production baseline")
    if candidate_output is not None and candidate_output.resolve() == baseline_path:
        raise ValueError("candidate output must not overwrite the production baseline")
    if candidate_output is not None and candidate_output.resolve() == report_path:
        raise ValueError("candidate output and report output must be different")
    builder = _load_builder()
    with tempfile.TemporaryDirectory(prefix="poenavi-desecration-audit-") as tmp:
        candidate_path = candidate_output or Path(tmp) / "candidate.json"
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        builder.build(
            pob2.resolve(), (stat_index or builder.DEFAULT_STAT_INDEX).resolve(), candidate_path,
            expected_revision,
        )
        baseline = load_payload(baseline_path)
        candidate = load_payload(candidate_path)
        report = compare_payloads(baseline, candidate)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pob2", type=Path, required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidate-output", type=Path)
    parser.add_argument("--stat-index", type=Path)
    args = parser.parse_args()
    report = audit(
        args.pob2, args.expected_revision, args.baseline, args.report,
        args.candidate_output, args.stat_index,
    )
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    print(f"requires_review: {str(report['requires_review']).lower()}")
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
