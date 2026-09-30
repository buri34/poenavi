"""Convert the audited Heist Trinket Mod dataset into minimal runtime data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = (
    ROOT / "data" / "poetore" / "poe1" / "heist_trinket_mod_dictionary.json"
)


def _valid_values(entry: dict) -> list[int]:
    values: set[int] = set()
    for value_range in entry.get("active_valid_ranges", ()):
        for value in value_range.get("values", ()):
            minimum = int(value["min"])
            maximum = int(value["max"])
            values.update(range(minimum, maximum + 1))
    return sorted(values)


def build_runtime_payload(source: dict) -> dict:
    mods = []
    for entry in source.get("entries", ()):
        if entry.get("availability") != "active" or entry.get("status") != "searchable":
            continue
        text_ja = str(entry.get("text_ja") or "").strip()
        stat_id = str(entry.get("trade_stat_id") or "").strip()
        values = _valid_values(entry)
        if not text_ja or not stat_id or not values:
            raise ValueError("現行トリンケットModに必須データがありません。")
        mods.append(
            {
                "stat_id": stat_id,
                "text_ja": text_ja,
                "valid_values": values,
            }
        )
    mods.sort(key=lambda row: row["stat_id"])
    if len(mods) != 39 or len({row["stat_id"] for row in mods}) != 39:
        raise ValueError("現行トリンケットMod辞書は39種類である必要があります。")
    return {
        "schema_version": 1,
        "generated_at": str(source.get("generated_at") or ""),
        "source": {
            "repoe_mods": dict(
                source.get("sources", {}).get("repoe_mods", {})
            ),
            "official_trade_stats_en": dict(
                source.get("sources", {}).get("trade_stats_en", {})
            ),
            "official_trade_stats_ja": dict(
                source.get("sources", {}).get("trade_stats_ja", {})
            ),
        },
        "base_type_en": "Thief's Trinket",
        "base_type_ja": "盗賊のトリンケット",
        "mods": mods,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    payload = build_runtime_payload(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
