from __future__ import annotations

import argparse
import json
from pathlib import Path


SOURCE_REVISION = "037015480c82bd183a6a4c9415d43cde269c2c2c"


def build_mercenary_data(stats_path: Path, builds_path: Path) -> dict:
    stats = []
    for line in stats_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        mercenary = row.get("mercenary")
        if not mercenary:
            continue
        stats.append({
            "ref": row["ref"],
            "ids": row.get("trade", {}).get("ids", {}).get("pseudo", []),
            "text": row.get("matchers", [{}])[0].get("string", row["ref"]),
            "advanced": row.get("matchers", [{}])[0].get("advanced"),
            "mod_family": row.get("modFamily", []),
            "tier": mercenary.get("tier"),
            "canonical": mercenary.get("canonical"),
            "synthetic_family": mercenary.get("syntheticFamily"),
            "supports": mercenary.get("supports", []),
            "icon": mercenary.get("icon"),
        })
    return {
        "schema_version": 1,
        "source": {
            "repository": "SnosMe/awakened-poe-trade",
            "revision": SOURCE_REVISION,
        },
        "builds": json.loads(builds_path.read_text(encoding="utf-8")),
        "stats": stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--builds", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_mercenary_data(args.stats, args.builds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
