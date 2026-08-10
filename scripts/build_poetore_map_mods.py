from __future__ import annotations

import argparse
import json
from pathlib import Path
import tarfile


DEFAULT_ARCHIVE = Path("vendor-sources/awakened-poe-trade-31b3e0e8.tar.gz")
DEFAULT_METADATA = Path("data/poetore/mod_metadata.json")
DEFAULT_OUTPUT = Path("data/poetore/map_mods.json")

# Awakened marks this generic item stat as ``fromAreaMods``, but it is not
# available under the official Trade site's Map stat category.  Keeping it in
# Map Check would therefore expose a modifier that cannot occur on maps.
NON_MAP_AREA_STAT_IDS = {
    "explicit.stat_1953432004",
    "implicit.stat_1953432004",
}

# Nightmare Mapの詳細コピーにのみ現れ、固定Awakened revision／公式Tradeの
# Area Mod一覧には独立Statがない項目。類似する確率付きStatへ統合せず、
# Map Checkの危険度設定を個別に保持する。
POETORE_NIGHTMARE_MAP_STATS = ({
    "key": "nightmare.stat_monsters_inflict_withered_on_hit",
    "ref": "Monsters inflict Withered for 2 seconds on Hit",
    "japanese": "モンスターによるヒット時に衰弱を2秒間付与する",
    "scope": "normal",
    "stat_ids": ["nightmare.stat_monsters_inflict_withered_on_hit"],
},)


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
        trade_ids = (stat.get("trade") or {}).get("ids") or {}
        if any(
            stat_id in NON_MAP_AREA_STAT_IDS
            for stat_ids in trade_ids.values()
            for stat_id in stat_ids
        ):
            continue
        pairs = []
        for kind, stat_ids in trade_ids.items():
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
    entries.extend(dict(row) for row in POETORE_NIGHTMARE_MAP_STATS)
    entries.sort(key=lambda row: (row["scope"], row["japanese"], row["key"]))
    return {
        "schema_version": 1,
        "source_revision": "31b3e0e8",
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
