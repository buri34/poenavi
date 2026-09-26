"""PoE2 Trade API snapshotを候補作成・レビュー・promotionの順で安全に更新する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK_PATH = ROOT / "scripts" / "poetore-poe2-sources.lock.json"
DEFAULT_CANDIDATE_DIR = ROOT / "build" / "poe2-trade-candidate"
REVIEW_MANIFEST = "review-manifest.json"
CANDIDATE_LOCK = "candidate-lock.json"
USER_AGENT = "PoENavi/poetore-poe2-source-snapshot (github.com/buri34/poenavi)"
EE2_REVISION = "d72afb83bc0888919a89d3c3744acee2c597e9c8"
EE2_URL = f"https://github.com/Kvan7/Exiled-Exchange-2/tree/{EE2_REVISION}"

SOURCES = {
    "stats_en": "https://www.pathofexile.com/api/trade2/data/stats",
    "stats_ja": "https://jp.pathofexile.com/api/trade2/data/stats",
    "items_en": "https://www.pathofexile.com/api/trade2/data/items",
    "items_ja": "https://jp.pathofexile.com/api/trade2/data/items",
    "filters_en": "https://www.pathofexile.com/api/trade2/data/filters",
    "filters_ja": "https://jp.pathofexile.com/api/trade2/data/filters",
    "static_en": "https://www.pathofexile.com/api/trade2/data/static",
    "static_ja": "https://jp.pathofexile.com/api/trade2/data/static",
    "leagues": "https://www.pathofexile.com/api/trade2/data/leagues",
}


class PromotionBlocked(RuntimeError):
    """レビュー条件を満たさない候補のpromotionを拒否する。"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def canonical_sha256(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(blob)


def count_entries(payload: dict) -> dict[str, int]:
    groups = payload.get("result", ())
    return {
        "groups": len(groups),
        "entries": sum(len(group.get("entries", ())) for group in groups),
    }


def fetch_source(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return response.read()


def source_lock_entry(
    source_id: str,
    url: str,
    path: Path,
    blob: bytes,
    root: Path = ROOT,
) -> dict:
    payload = json.loads(blob)
    return {
        "url": url,
        "path": str(path.relative_to(root)),
        "sha256": sha256_bytes(blob),
        "bytes": len(blob),
        **count_entries(payload),
    }


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_snapshot(
    lock_path: Path = DEFAULT_LOCK_PATH,
    root: Path = ROOT,
) -> list[str]:
    lock = _load_json(lock_path)
    errors = []
    for source_id, source in lock.get("sources", {}).items():
        path = root / source["path"]
        if not path.is_file():
            errors.append(f"{source_id}: missing {path}")
            continue
        blob = path.read_bytes()
        if sha256_bytes(blob) != source["sha256"]:
            errors.append(f"{source_id}: sha256 mismatch")
        if len(blob) != source["bytes"]:
            errors.append(f"{source_id}: byte count mismatch")
        try:
            counts = count_entries(json.loads(blob))
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"{source_id}: invalid JSON")
            continue
        for key in ("groups", "entries"):
            if counts[key] != source[key]:
                errors.append(f"{source_id}: {key} mismatch")
    return errors


def _stat_records(payload: dict) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    records: dict[str, dict] = {}
    duplicates: dict[str, list[dict]] = defaultdict(list)
    for group in payload.get("result", ()):
        group_id = str(group.get("id", ""))
        group_type = group.get("type")
        for entry in group.get("entries", ()):
            stat_id = str(entry.get("id", ""))
            record = {
                "id": stat_id,
                "group": group_id,
                "group_type": group_type,
                "type": entry.get("type"),
                "text": entry.get("text"),
                "option_ids": [
                    option.get("id") for option in entry.get("option", {}).get("options", ())
                ],
                "option_labels": [
                    option.get("text") for option in entry.get("option", {}).get("options", ())
                ],
                "raw": entry,
            }
            if stat_id in records:
                duplicates[stat_id].append(record)
            else:
                records[stat_id] = record
    return records, duplicates


def _delta(
    source_id: str,
    stat_id: str,
    kind: str,
    classification: str,
    before: dict | None,
    after: dict | None,
    detail: str,
) -> dict:
    stable = {
        "source": source_id,
        "id": stat_id,
        "kind": kind,
        "before": before,
        "after": after,
        "detail": detail,
    }
    return {
        **stable,
        "classification": classification,
        "fingerprint": canonical_sha256(stable),
        "decision": None if classification == "review_required" else "blocked" if classification == "hard_block" else "informational",
        "reason": "",
    }


def diff_stat_payloads(source_id: str, baseline: dict, candidate: dict) -> list[dict]:
    old, old_duplicates = _stat_records(baseline)
    new, new_duplicates = _stat_records(candidate)
    deltas = []
    for stat_id in sorted(set(old_duplicates) | set(new_duplicates)):
        if old_duplicates.get(stat_id) != new_duplicates.get(stat_id):
            deltas.append(
                _delta(
                    source_id,
                    stat_id,
                    "duplicate_key_change",
                    "hard_block",
                    {"count": 1 + len(old_duplicates.get(stat_id, ()))},
                    {"count": 1 + len(new_duplicates.get(stat_id, ()))},
                    "duplicate complete Stat ID count changed",
                )
            )
    for stat_id in sorted(old.keys() - new.keys()):
        deltas.append(
            _delta(source_id, stat_id, "removed", "hard_block", old[stat_id], None, "complete Stat ID removed")
        )
    for stat_id in sorted(new.keys() - old.keys()):
        deltas.append(
            _delta(source_id, stat_id, "added", "review_required", None, new[stat_id], "new complete Stat ID")
        )
    for stat_id in sorted(old.keys() & new.keys()):
        before = old[stat_id]
        after = new[stat_id]
        if before == after:
            continue
        structural = any(
            before.get(field) != after.get(field)
            for field in ("group", "group_type", "type", "option_ids")
        )
        classification = "hard_block" if structural else "review_required"
        detail = "group/type/option ID changed" if structural else "text or option label changed"
        deltas.append(_delta(source_id, stat_id, "changed", classification, before, after, detail))
    return deltas


def _text_duplicate_counts(payload: dict) -> dict[str, int]:
    records, _ = _stat_records(payload)
    counts = Counter(str(record.get("text", "")) for record in records.values())
    return {text: count for text, count in counts.items() if text and count > 1}


def _stat_summary(payload: dict) -> dict:
    records, duplicates = _stat_records(payload)
    return {
        "entry_count": len(records),
        "duplicate_keys": {key: 1 + len(value) for key, value in sorted(duplicates.items())},
        "duplicate_text": _text_duplicate_counts(payload),
    }


def _bilingual_deltas(
    baseline_en: dict,
    baseline_ja: dict,
    candidate_en: dict,
    candidate_ja: dict,
) -> list[dict]:
    old_en, _ = _stat_records(baseline_en)
    old_ja, _ = _stat_records(baseline_ja)
    new_en, _ = _stat_records(candidate_en)
    new_ja, _ = _stat_records(candidate_ja)
    old_mismatch = old_en.keys() ^ old_ja.keys()
    new_mismatch = new_en.keys() ^ new_ja.keys()
    deltas = []
    for stat_id in sorted(new_mismatch - old_mismatch):
        deltas.append(
            _delta(
                "stats_bilingual",
                stat_id,
                "key_mismatch",
                "hard_block",
                None,
                {"in_en": stat_id in new_en, "in_ja": stat_id in new_ja},
                "new English/Japanese complete Stat ID mismatch",
            )
        )
    for stat_id in sorted(new_en.keys() & new_ja.keys()):
        before_same = stat_id in old_en and stat_id in old_ja and old_en[stat_id]["text"] == old_ja[stat_id]["text"]
        after_same = new_en[stat_id]["text"] == new_ja[stat_id]["text"]
        if after_same and not before_same:
            deltas.append(
                _delta(
                    "stats_bilingual",
                    stat_id,
                    "new_identical_text",
                    "review_required",
                    None,
                    {"text": new_en[stat_id]["text"]},
                    "newly identical English/Japanese text requires verification",
                )
            )
    return deltas


def reuse_prior_reviews(deltas: list[dict], prior_manifest: dict | None) -> None:
    if not prior_manifest:
        return
    approved = {
        delta.get("fingerprint"): delta
        for delta in prior_manifest.get("deltas", ())
        if delta.get("decision") in {"adopt", "retain_baseline"} and delta.get("reason")
    }
    for delta in deltas:
        previous = approved.get(delta["fingerprint"])
        if previous and delta["classification"] == "review_required":
            delta["decision"] = previous["decision"]
            delta["reason"] = previous["reason"]


def _source_payload(lock: dict, source_id: str, root: Path) -> dict:
    return _load_json(root / lock["sources"][source_id]["path"])


def _candidate_manifest(
    baseline_lock: dict,
    candidate_lock: dict,
    lock_path: Path,
    candidate_dir: Path,
    root: Path,
    prior_manifest: dict | None,
) -> dict:
    deltas = []
    summaries = {}
    for source_id in candidate_lock["sources"]:
        baseline_payload = _source_payload(baseline_lock, source_id, root)
        candidate_payload = _load_json(candidate_dir / f"{source_id}.json")
        if source_id.startswith("stats_"):
            deltas.extend(diff_stat_payloads(source_id, baseline_payload, candidate_payload))
            summaries[source_id] = {
                "baseline": _stat_summary(baseline_payload),
                "candidate": _stat_summary(candidate_payload),
            }
        elif baseline_lock["sources"][source_id]["sha256"] != candidate_lock["sources"][source_id]["sha256"]:
            deltas.append(
                _delta(
                    source_id,
                    source_id,
                    "source_changed",
                    "review_required",
                    {"sha256": baseline_lock["sources"][source_id]["sha256"]},
                    {"sha256": candidate_lock["sources"][source_id]["sha256"]},
                    "non-Stat Trade2 source changed",
                )
            )
    required = {"stats_en", "stats_ja"}
    if required <= candidate_lock["sources"].keys() and required <= baseline_lock["sources"].keys():
        deltas.extend(
            _bilingual_deltas(
                _source_payload(baseline_lock, "stats_en", root),
                _source_payload(baseline_lock, "stats_ja", root),
                _load_json(candidate_dir / "stats_en.json"),
                _load_json(candidate_dir / "stats_ja.json"),
            )
        )
    reuse_prior_reviews(deltas, prior_manifest)
    return {
        "schema_version": 1,
        "created_at": utc_now(),
        "baseline_lock_path": str(lock_path),
        "baseline_lock_sha256": sha256_bytes(lock_path.read_bytes()),
        "candidate_sources": {
            source_id: {"sha256": source["sha256"], "bytes": source["bytes"]}
            for source_id, source in candidate_lock["sources"].items()
        },
        "stat_summaries": summaries,
        "allowed_decisions": ["adopt", "retain_baseline", "hold"],
        "deltas": deltas,
    }


def create_candidate(
    candidate_dir: Path = DEFAULT_CANDIDATE_DIR,
    *,
    lock_path: Path = DEFAULT_LOCK_PATH,
    root: Path = ROOT,
    prior_manifest_path: Path | None = None,
) -> dict:
    errors = verify_snapshot(lock_path, root)
    if errors:
        raise PromotionBlocked("baseline snapshot is invalid: " + "; ".join(errors))
    if candidate_dir.exists() and any(candidate_dir.iterdir()):
        raise FileExistsError(f"candidate directory is not empty: {candidate_dir}")
    candidate_dir.mkdir(parents=True, exist_ok=True)
    baseline_lock = _load_json(lock_path)
    locked_sources = {}
    for source_id, url in SOURCES.items():
        if source_id not in baseline_lock.get("sources", {}):
            raise PromotionBlocked(f"baseline lock does not contain source: {source_id}")
        blob = fetch_source(url)
        json.loads(blob)
        path = candidate_dir / f"{source_id}.json"
        path.write_bytes(blob)
        locked_sources[source_id] = source_lock_entry(source_id, url, path, blob, candidate_dir)
    candidate_lock = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "sources": locked_sources,
        "reference_implementations": deepcopy(baseline_lock.get("reference_implementations", {})),
    }
    _write_json(candidate_dir / CANDIDATE_LOCK, candidate_lock)
    prior = _load_json(prior_manifest_path) if prior_manifest_path else None
    manifest = _candidate_manifest(
        baseline_lock, candidate_lock, lock_path, candidate_dir, root, prior
    )
    _write_json(candidate_dir / REVIEW_MANIFEST, manifest)
    return manifest


def _validate_candidate_hashes(candidate_dir: Path, manifest: dict, candidate_lock: dict) -> None:
    for source_id, expected in manifest.get("candidate_sources", {}).items():
        path = candidate_dir / f"{source_id}.json"
        blob = path.read_bytes()
        if sha256_bytes(blob) != expected["sha256"] or len(blob) != expected["bytes"]:
            raise PromotionBlocked(f"candidate hash changed after review: {source_id}")
        if candidate_lock["sources"][source_id]["sha256"] != expected["sha256"]:
            raise PromotionBlocked(f"candidate lock mismatch: {source_id}")


def _validate_reviews(manifest: dict, candidate_sources: set[str]) -> None:
    hard = [delta for delta in manifest.get("deltas", ()) if delta.get("classification") == "hard_block"]
    if hard:
        raise PromotionBlocked(f"hard block remains: {len(hard)}")
    unreviewed = [
        delta
        for delta in manifest.get("deltas", ())
        if delta.get("classification") == "review_required"
        and (delta.get("decision") not in {"adopt", "retain_baseline"} or not delta.get("reason"))
    ]
    if unreviewed:
        raise PromotionBlocked(f"unreviewed or held delta remains: {len(unreviewed)}")
    unsupported_retains = [
        delta
        for delta in manifest.get("deltas", ())
        if delta.get("decision") == "retain_baseline"
        and delta.get("source") not in candidate_sources
    ]
    if unsupported_retains:
        raise PromotionBlocked(
            "retain_baseline requires editing the underlying language source: "
            f"{len(unsupported_retains)} derived delta(s)"
        )


def _find_group(payload: dict, group_id: str) -> dict:
    for group in payload.get("result", ()):
        if str(group.get("id", "")) == group_id:
            return group
    raise PromotionBlocked(f"cannot retain baseline Stat: missing group {group_id}")


def _apply_retain_decisions(
    source_id: str,
    candidate_payload: dict,
    manifest: dict,
) -> dict:
    result = deepcopy(candidate_payload)
    relevant = [
        delta
        for delta in manifest.get("deltas", ())
        if delta.get("source") == source_id and delta.get("decision") == "retain_baseline"
    ]
    for delta in relevant:
        if delta["kind"] == "added":
            for group in result.get("result", ()):
                group["entries"] = [entry for entry in group.get("entries", ()) if entry.get("id") != delta["id"]]
            continue
        before = delta.get("before")
        if not before or "raw" not in before:
            raise PromotionBlocked(f"cannot retain non-record delta: {source_id}/{delta['id']}")
        group = _find_group(result, before["group"])
        entries = group.setdefault("entries", [])
        entries[:] = [entry for entry in entries if entry.get("id") != delta["id"]]
        entries.append(before["raw"])
    return result


def promote_candidate(
    candidate_dir: Path = DEFAULT_CANDIDATE_DIR,
    *,
    lock_path: Path = DEFAULT_LOCK_PATH,
    root: Path = ROOT,
) -> dict:
    manifest_path = candidate_dir / REVIEW_MANIFEST
    manifest = _load_json(manifest_path)
    candidate_lock = _load_json(candidate_dir / CANDIDATE_LOCK)
    baseline_lock = _load_json(lock_path)
    if sha256_bytes(lock_path.read_bytes()) != manifest.get("baseline_lock_sha256"):
        raise PromotionBlocked("baseline lock changed after candidate creation")
    errors = verify_snapshot(lock_path, root)
    if errors:
        raise PromotionBlocked("baseline snapshot is invalid: " + "; ".join(errors))
    _validate_candidate_hashes(candidate_dir, manifest, candidate_lock)
    _validate_reviews(manifest, set(candidate_lock["sources"]))

    effective_blobs = {}
    for source_id in candidate_lock["sources"]:
        retained_source = any(
            delta.get("source") == source_id
            and delta.get("kind") == "source_changed"
            and delta.get("decision") == "retain_baseline"
            for delta in manifest.get("deltas", ())
        )
        if retained_source:
            effective_blobs[source_id] = (
                root / baseline_lock["sources"][source_id]["path"]
            ).read_bytes()
            continue
        payload = _load_json(candidate_dir / f"{source_id}.json")
        if source_id.startswith("stats_"):
            payload = _apply_retain_decisions(source_id, payload, manifest)
        effective_blobs[source_id] = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        )
    content_hash = sha256_bytes(b"".join(effective_blobs[key] for key in sorted(effective_blobs)))[:12]
    final_dir = root / "vendor-sources" / f"poe2-trade-api-reviewed-{content_hash}"
    if final_dir.exists():
        raise PromotionBlocked(f"promoted snapshot already exists: {final_dir}")

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{final_dir.name}-", dir=final_dir.parent))
    try:
        locked_sources = {}
        for source_id, blob in effective_blobs.items():
            path = staging / f"{source_id}.json"
            path.write_bytes(blob)
            final_path = final_dir / path.name
            locked_sources[source_id] = source_lock_entry(
                source_id,
                candidate_lock["sources"][source_id]["url"],
                final_path,
                blob,
                root,
            )
        review_blob = manifest_path.read_bytes()
        (staging / REVIEW_MANIFEST).write_bytes(review_blob)
        new_lock = {
            "schema_version": 2,
            "generated_at": utc_now(),
            "sources": locked_sources,
            "reference_implementations": deepcopy(candidate_lock.get("reference_implementations", {})),
            "review": {
                "path": str((final_dir / REVIEW_MANIFEST).relative_to(root)),
                "manifest_sha256": sha256_bytes(review_blob),
                "baseline_lock_sha256": manifest["baseline_lock_sha256"],
            },
        }
        os.replace(staging, final_dir)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{lock_path.name}-", dir=lock_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(new_lock, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, lock_path)
        finally:
            Path(temporary_name).unlink(missing_ok=True)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if final_dir.exists() and sha256_bytes(lock_path.read_bytes()) == manifest.get("baseline_lock_sha256"):
            shutil.rmtree(final_dir)
        raise
    return new_lock


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify")
    candidate = subparsers.add_parser("candidate")
    candidate.add_argument("--output", type=Path, default=DEFAULT_CANDIDATE_DIR)
    candidate.add_argument("--prior-review", type=Path)
    promote = subparsers.add_parser("promote")
    promote.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE_DIR)
    args = parser.parse_args()
    try:
        if args.command == "verify":
            errors = verify_snapshot()
            if errors:
                print("\n".join(errors))
                return 1
            print(f"verified: {DEFAULT_LOCK_PATH}")
            return 0
        if args.command == "candidate":
            manifest = create_candidate(args.output, prior_manifest_path=args.prior_review)
            print(f"candidate: {args.output}")
            print(f"review: {args.output / REVIEW_MANIFEST}")
            print(f"deltas: {len(manifest['deltas'])}")
            return 0
        lock = promote_candidate(args.candidate)
        print(f"promoted lock: {DEFAULT_LOCK_PATH}")
        print(f"sources: {len(lock['sources'])}")
        return 0
    except (PromotionBlocked, FileExistsError, ValueError, json.JSONDecodeError) as exc:
        print(f"blocked: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
