from __future__ import annotations

import argparse
import json
from pathlib import Path
import tarfile


DEFAULT_ARCHIVE = Path("vendor-sources/awakened-poe-trade-3c8e0320.tar.gz")
DEFAULT_METADATA = Path("data/poetore/mod_metadata.json")
DEFAULT_OUTPUT = Path("data/poetore/map_mods.json")


def _flatten_stats(rows: list[dict]) -> list[dict]:
    flattened = []
    for row in rows:
        nested = row.get("stats")
        if nested is None:
            flattened.append(row)
            continue
        resolve = row.get("resolve") or {}
        tests = resolve.get("test", ()) if resolve.get("strat") == "select" else ()
        for index, stat in enumerate(nested):
            stat = dict(stat)
            if index < len(tests):
                stat["category_select"] = tests[index]
            flattened.append(stat)
    return flattened


def build_catalog(archive: Path, metadata_path: Path) -> dict:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    by_id = {
        (str(row["kind"]), str(row["stat_id"])): row
        for row in metadata.get("mods", ())
    }
    with tarfile.open(archive, "r:gz") as tar:
        member = next(
            value for value in tar.getmembers()
            if value.name.endswith("/renderer/public/data/en/stats.ndjson")
        )
        handle = tar.extractfile(member)
        if handle is None:
            raise ValueError("Awakened stats.ndjson was not found")
        awakened = _flatten_stats([
            json.loads(line) for line in handle.read().decode("utf-8").splitlines()
            if line.strip()
        ])

    entries = []
    for stat in awakened:
        scope = stat.get("fromAreaMods")
        if not scope:
            continue
        pairs = []
        for kind, stat_ids in ((stat.get("trade") or {}).get("ids") or {}).items():
            for stat_id in stat_ids:
                if (kind, stat_id) in by_id:
                    pairs.append((kind, stat_id))
        if not pairs:
            raise ValueError(f"Area Mod has no poetore Trade ID: {stat.get('ref')}")
        preferred = next((pair for pair in pairs if pair[0] == "explicit"), pairs[0])
        row = by_id[preferred]
        entries.append({
            "key": preferred[1],
            "ref": str(stat.get("ref", "")),
            "japanese": str((row.get("japanese") or [""])[0]),
            "scope": {
                "yes": "normal",
                "heist_exclusive": "heist_exclusive",
                "ubermap_exclusive": "ubermap_exclusive",
            }[scope],
            "stat_ids": sorted({stat_id for _kind, stat_id in pairs}),
        })
    entries.sort(key=lambda row: (row["scope"], row["japanese"], row["key"]))
    return {
        "schema_version": 1,
        "source_revision": "3c8e0320",
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_catalog(args.archive, args.metadata)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(payload['entries'])} Map Mods: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
