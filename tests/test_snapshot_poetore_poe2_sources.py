from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import snapshot_poetore_poe2_sources as snapshot


def _blob(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode()


def _stats(*entries: dict) -> dict:
    return {"result": [{"id": "explicit", "label": "Explicit", "entries": list(entries)}]}


def _entry(stat_id: str, text: str, *, option_id: int | None = None) -> dict:
    entry = {"id": stat_id, "text": text, "type": "explicit"}
    if option_id is not None:
        entry["option"] = {"options": [{"id": option_id, "text": text}]}
    return entry


def _write_baseline(tmp_path: Path, sources: dict[str, dict]) -> tuple[Path, Path]:
    root = tmp_path / "root"
    source_dir = root / "vendor-sources" / "baseline"
    source_dir.mkdir(parents=True)
    locked = {}
    for source_id, payload in sources.items():
        blob = _blob(payload)
        path = source_dir / f"{source_id}.json"
        path.write_bytes(blob)
        locked[source_id] = snapshot.source_lock_entry(
            source_id, f"https://example.test/{source_id}", path, blob, root
        )
    lock = {"schema_version": 1, "generated_at": "baseline", "sources": locked}
    lock_path = root / "scripts" / "poetore-poe2-sources.lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    return root, lock_path


def _approve_all(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for delta in manifest["deltas"]:
        if delta["classification"] == "review_required":
            delta["decision"] = "adopt"
            delta["reason"] = "verified against official Trade2"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_count_entries_counts_groups_and_nested_entries():
    payload = {"result": [{"entries": [{}, {}]}, {"entries": [{}]}]}
    assert snapshot.count_entries(payload) == {"groups": 2, "entries": 3}


def test_verify_snapshot_detects_tampering(tmp_path):
    root, lock_path = _write_baseline(tmp_path, {"sample": _stats(_entry("a", "A"))})
    assert snapshot.verify_snapshot(lock_path, root) == []

    source = root / "vendor-sources" / "baseline" / "sample.json"
    source.write_text("{}", encoding="utf-8")
    errors = snapshot.verify_snapshot(lock_path, root)
    assert "sample: sha256 mismatch" in errors
    assert "sample: byte count mismatch" in errors


def test_create_candidate_never_changes_authoritative_snapshot(tmp_path, monkeypatch):
    sources = {
        "stats_en": _stats(_entry("explicit.a", "A")),
        "stats_ja": _stats(_entry("explicit.a", "Ａ")),
    }
    root, lock_path = _write_baseline(tmp_path, sources)
    before_lock = lock_path.read_bytes()
    before_files = {
        path.name: path.read_bytes()
        for path in (root / "vendor-sources" / "baseline").iterdir()
    }
    changed = {**sources, "stats_ja": _stats(_entry("explicit.a", "新しいＡ"))}
    monkeypatch.setattr(snapshot, "SOURCES", {key: f"https://example.test/{key}" for key in changed})
    monkeypatch.setattr(snapshot, "fetch_source", lambda url: _blob(changed[url.rsplit("/", 1)[-1]]))

    candidate = tmp_path / "candidate"
    snapshot.create_candidate(candidate, lock_path=lock_path, root=root)

    assert lock_path.read_bytes() == before_lock
    assert {
        path.name: path.read_bytes()
        for path in (root / "vendor-sources" / "baseline").iterdir()
    } == before_files
    manifest = json.loads((candidate / snapshot.REVIEW_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["baseline_lock_sha256"] == hashlib.sha256(before_lock).hexdigest()
    assert any(delta["classification"] == "review_required" for delta in manifest["deltas"])


def test_promotion_rejects_unreviewed_delta_and_keeps_lock_unchanged(tmp_path, monkeypatch):
    baseline = {
        "stats_en": _stats(_entry("explicit.a", "A")),
        "stats_ja": _stats(_entry("explicit.a", "Ａ")),
    }
    root, lock_path = _write_baseline(tmp_path, baseline)
    candidate_payload = {**baseline, "stats_ja": _stats(_entry("explicit.a", "新しいＡ"))}
    monkeypatch.setattr(snapshot, "SOURCES", {key: f"https://example.test/{key}" for key in baseline})
    monkeypatch.setattr(snapshot, "fetch_source", lambda url: _blob(candidate_payload[url.rsplit("/", 1)[-1]]))
    candidate = tmp_path / "candidate"
    snapshot.create_candidate(candidate, lock_path=lock_path, root=root)
    before = lock_path.read_bytes()

    with pytest.raises(snapshot.PromotionBlocked, match="unreviewed"):
        snapshot.promote_candidate(candidate, lock_path=lock_path, root=root)

    assert lock_path.read_bytes() == before


def test_promotion_rejects_removed_id_as_hard_block(tmp_path, monkeypatch):
    baseline = {
        "stats_en": _stats(_entry("explicit.a", "A"), _entry("explicit.b", "B")),
        "stats_ja": _stats(_entry("explicit.a", "Ａ"), _entry("explicit.b", "Ｂ")),
    }
    root, lock_path = _write_baseline(tmp_path, baseline)
    candidate_payload = {
        "stats_en": _stats(_entry("explicit.a", "A")),
        "stats_ja": _stats(_entry("explicit.a", "Ａ")),
    }
    monkeypatch.setattr(snapshot, "SOURCES", {key: f"https://example.test/{key}" for key in baseline})
    monkeypatch.setattr(snapshot, "fetch_source", lambda url: _blob(candidate_payload[url.rsplit("/", 1)[-1]]))
    candidate = tmp_path / "candidate"
    snapshot.create_candidate(candidate, lock_path=lock_path, root=root)
    manifest = json.loads((candidate / snapshot.REVIEW_MANIFEST).read_text(encoding="utf-8"))

    assert any(
        delta["kind"] == "removed" and delta["classification"] == "hard_block"
        for delta in manifest["deltas"]
    )
    with pytest.raises(snapshot.PromotionBlocked, match="hard block"):
        snapshot.promote_candidate(candidate, lock_path=lock_path, root=root)


def test_promotion_rejects_candidate_changed_after_review(tmp_path, monkeypatch):
    baseline = {
        "stats_en": _stats(_entry("explicit.a", "A")),
        "stats_ja": _stats(_entry("explicit.a", "Ａ")),
    }
    root, lock_path = _write_baseline(tmp_path, baseline)
    changed = {**baseline, "stats_ja": _stats(_entry("explicit.a", "新しいＡ"))}
    monkeypatch.setattr(snapshot, "SOURCES", {key: f"https://example.test/{key}" for key in baseline})
    monkeypatch.setattr(snapshot, "fetch_source", lambda url: _blob(changed[url.rsplit("/", 1)[-1]]))
    candidate = tmp_path / "candidate"
    snapshot.create_candidate(candidate, lock_path=lock_path, root=root)
    _approve_all(candidate / snapshot.REVIEW_MANIFEST)
    (candidate / "stats_ja.json").write_bytes(_blob(_stats(_entry("explicit.a", "tampered"))))

    with pytest.raises(snapshot.PromotionBlocked, match="candidate hash"):
        snapshot.promote_candidate(candidate, lock_path=lock_path, root=root)


def test_prior_approval_is_reused_only_for_unchanged_delta():
    old = {
        "deltas": [
            {
                "fingerprint": "same",
                "decision": "adopt",
                "reason": "officially verified",
            }
        ]
    }
    deltas = [
        {"fingerprint": "same", "classification": "review_required", "decision": None, "reason": ""},
        {"fingerprint": "changed", "classification": "review_required", "decision": None, "reason": ""},
    ]

    snapshot.reuse_prior_reviews(deltas, old)

    assert deltas[0]["decision"] == "adopt"
    assert deltas[1]["decision"] is None


def test_fully_reviewed_candidate_promotes_with_atomic_lock_switch(tmp_path, monkeypatch):
    baseline = {
        "stats_en": _stats(_entry("explicit.a", "A")),
        "stats_ja": _stats(_entry("explicit.a", "Ａ")),
    }
    root, lock_path = _write_baseline(tmp_path, baseline)
    changed = {
        "stats_en": _stats(_entry("explicit.a", "A"), _entry("explicit.b", "B")),
        "stats_ja": _stats(_entry("explicit.a", "Ａ"), _entry("explicit.b", "Ｂ")),
    }
    monkeypatch.setattr(snapshot, "SOURCES", {key: f"https://example.test/{key}" for key in baseline})
    monkeypatch.setattr(snapshot, "fetch_source", lambda url: _blob(changed[url.rsplit("/", 1)[-1]]))
    candidate = tmp_path / "candidate"
    snapshot.create_candidate(candidate, lock_path=lock_path, root=root)
    _approve_all(candidate / snapshot.REVIEW_MANIFEST)

    promoted = snapshot.promote_candidate(candidate, lock_path=lock_path, root=root)

    assert promoted["review"]["manifest_sha256"]
    assert snapshot.verify_snapshot(lock_path, root) == []
    assert "baseline" not in promoted["sources"]["stats_en"]["path"]
    path = root / promoted["sources"]["stats_en"]["path"]
    assert json.loads(path.read_text())["result"][0]["entries"][1]["id"] == "explicit.b"


def test_retain_baseline_decision_materializes_old_stat_value(tmp_path, monkeypatch):
    baseline = {
        "stats_en": _stats(_entry("explicit.a", "A")),
        "stats_ja": _stats(_entry("explicit.a", "旧訳")),
    }
    root, lock_path = _write_baseline(tmp_path, baseline)
    changed = {**baseline, "stats_ja": _stats(_entry("explicit.a", "怪しい新訳"))}
    monkeypatch.setattr(snapshot, "SOURCES", {key: f"https://example.test/{key}" for key in baseline})
    monkeypatch.setattr(snapshot, "fetch_source", lambda url: _blob(changed[url.rsplit("/", 1)[-1]]))
    candidate = tmp_path / "candidate"
    snapshot.create_candidate(candidate, lock_path=lock_path, root=root)
    manifest_path = candidate / snapshot.REVIEW_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed_delta = next(delta for delta in manifest["deltas"] if delta["source"] == "stats_ja")
    changed_delta["decision"] = "retain_baseline"
    changed_delta["reason"] = "official Japanese name is unchanged"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    promoted = snapshot.promote_candidate(candidate, lock_path=lock_path, root=root)

    payload = json.loads((root / promoted["sources"]["stats_ja"]["path"]).read_text())
    assert payload["result"][0]["entries"][0]["text"] == "旧訳"


def test_promotion_rejects_baseline_lock_changed_after_candidate_creation(tmp_path, monkeypatch):
    baseline = {
        "stats_en": _stats(_entry("explicit.a", "A")),
        "stats_ja": _stats(_entry("explicit.a", "Ａ")),
    }
    root, lock_path = _write_baseline(tmp_path, baseline)
    monkeypatch.setattr(snapshot, "SOURCES", {key: f"https://example.test/{key}" for key in baseline})
    monkeypatch.setattr(snapshot, "fetch_source", lambda url: _blob(baseline[url.rsplit("/", 1)[-1]]))
    candidate = tmp_path / "candidate"
    snapshot.create_candidate(candidate, lock_path=lock_path, root=root)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["generated_at"] = "changed concurrently"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    with pytest.raises(snapshot.PromotionBlocked, match="baseline lock changed"):
        snapshot.promote_candidate(candidate, lock_path=lock_path, root=root)


def test_option_id_change_is_hard_block_and_label_change_requires_review():
    baseline = _stats(_entry("explicit.a|1", "Old", option_id=1))
    changed_id = _stats(_entry("explicit.a|2", "Old", option_id=2))
    changed_label = _stats(_entry("explicit.a|1", "New", option_id=1))

    id_deltas = snapshot.diff_stat_payloads("stats_en", baseline, changed_id)
    label_deltas = snapshot.diff_stat_payloads("stats_en", baseline, changed_label)

    assert any(delta["classification"] == "hard_block" for delta in id_deltas)
    assert any(delta["classification"] == "review_required" for delta in label_deltas)
