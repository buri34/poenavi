from __future__ import annotations

import hashlib
import json

from scripts import snapshot_poetore_poe2_sources as snapshot


def test_count_entries_counts_groups_and_nested_entries():
    payload = {"result": [{"entries": [{}, {}]}, {"entries": [{}]}]}
    assert snapshot.count_entries(payload) == {"groups": 2, "entries": 3}


def test_verify_snapshot_detects_tampering(tmp_path):
    source = tmp_path / "source.json"
    blob = json.dumps({"result": [{"entries": [{}]}]}).encode()
    source.write_bytes(blob)
    lock = {
        "sources": {
            "sample": {
                "path": "source.json",
                "sha256": hashlib.sha256(blob).hexdigest(),
                "bytes": len(blob),
                "groups": 1,
                "entries": 1,
            }
        }
    }
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    assert snapshot.verify_snapshot(lock_path, tmp_path) == []

    source.write_text("{}", encoding="utf-8")
    errors = snapshot.verify_snapshot(lock_path, tmp_path)
    assert "sample: sha256 mismatch" in errors
    assert "sample: byte count mismatch" in errors
