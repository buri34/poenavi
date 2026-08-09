"""PoE2 Trade APIの固定snapshotとsource lockを生成・検証する。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_DIR = ROOT / "vendor-sources" / "poe2-trade-api-2026-08-09"
DEFAULT_LOCK_PATH = ROOT / "scripts" / "poetore-poe2-sources.lock.json"
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


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


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


def build_snapshot(
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    lock_path: Path = DEFAULT_LOCK_PATH,
) -> dict:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    locked_sources = {}
    for source_id, url in SOURCES.items():
        blob = fetch_source(url)
        payload = json.loads(blob)
        path = snapshot_dir / f"{source_id}.json"
        path.write_bytes(blob)
        locked_sources[source_id] = {
            "url": url,
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256_bytes(blob),
            "bytes": len(blob),
            **count_entries(payload),
        }
    lock = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": locked_sources,
        "reference_implementations": {
            "exiled_exchange_2": {
                "url": EE2_URL,
                "revision": EE2_REVISION,
                "usage": "PoE2 parser fixtures, categories, and query behavior reference",
            }
        },
    }
    lock_path.write_text(
        json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return lock


def verify_snapshot(
    lock_path: Path = DEFAULT_LOCK_PATH,
    root: Path = ROOT,
) -> list[str]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        errors = verify_snapshot()
        if errors:
            print("\n".join(errors))
            return 1
        print(f"verified: {DEFAULT_LOCK_PATH}")
        return 0
    lock = build_snapshot()
    print(f"snapshot: {DEFAULT_SNAPSHOT_DIR}")
    print(f"lock: {DEFAULT_LOCK_PATH}")
    print(f"sources: {len(lock['sources'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
