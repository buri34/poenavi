#!/usr/bin/env python3
"""Build compact bilingual PoE2 identity/stat indexes from locked snapshots."""

from __future__ import annotations

import json
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "vendor-sources" / "poe2-trade-api-2026-08-09"
OUTPUT = ROOT / "data" / "poetore" / "poe2"


def _load(name: str) -> dict:
    return json.loads((SNAPSHOT / name).read_text(encoding="utf-8"))


def _signature(entry: dict) -> tuple:
    flags = entry.get("flags") or {}
    return (
        str(entry.get("disc", "")), bool(entry.get("name")),
        bool(flags.get("unique")), tuple(sorted(flags)),
    )


def _aligned(english: list[dict], japanese: list[dict]):
    ei = ji = 0
    while ei < len(english) and ji < len(japanese):
        en, ja = english[ei], japanese[ji]
        if _signature(en) == _signature(ja):
            yield en, ja
            ei += 1
            ji += 1
            continue
        lookahead = 8
        en_skip = next((n for n in range(1, lookahead + 1)
                        if ei + n < len(english) and _signature(english[ei + n]) == _signature(ja)), None)
        ja_skip = next((n for n in range(1, lookahead + 1)
                        if ji + n < len(japanese) and _signature(japanese[ji + n]) == _signature(en)), None)
        if en_skip is not None and (ja_skip is None or en_skip < ja_skip):
            ei += en_skip
        elif ja_skip is not None and (en_skip is None or ja_skip < en_skip):
            ji += ja_skip
        else:
            ei += 1
            ji += 1


def build_identity_index(ee2_root: Path | None = None) -> dict:
    if ee2_root is not None:
        localized = {}
        for language in ("en", "ja"):
            path = ee2_root / "renderer" / "public" / "data" / language / "items.ndjson"
            localized[language] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        entries = []
        for en, ja in zip(localized["en"], localized["ja"]):
            if not en.get("refName") and not ja.get("refName"):
                continue
            if en.get("refName") != ja.get("refName") or en.get("namespace") != ja.get("namespace"):
                raise ValueError("EE2 bilingual item rows are not aligned")
            row = {
                "namespace": en["namespace"], "ref_name": en["refName"],
                "names": {"en": en["name"], "ja": ja["name"]},
            }
            if en.get("craftable", {}).get("category"):
                row["category"] = en["craftable"]["category"]
            if en.get("unique"):
                row["base_ref"] = en["unique"].get("base", "")
            entries.append(row)
        return {
            "schema_version": 2,
            "source": "Exiled Exchange 2 d72afb83bc0888919a89d3c3744acee2c597e9c8",
            "entries": entries,
        }

    en_groups = {row["id"]: row["entries"] for row in _load("items_en.json")["result"]}
    ja_groups = {row["id"]: row["entries"] for row in _load("items_ja.json")["result"]}
    entries = []
    seen = set()
    for group_id, english in en_groups.items():
        for en, ja in _aligned(english, ja_groups.get(group_id, [])):
            base = str(en.get("type", "")).strip()
            ja_base = str(ja.get("type", "")).strip()
            name = str(en.get("name", "")).strip()
            ja_name = str(ja.get("name", "")).strip()
            if base and ("ITEM", base) not in seen:
                entries.append({
                    "namespace": "ITEM", "ref_name": base, "group": group_id,
                    "names": {"en": base, "ja": ja_base or base},
                })
                seen.add(("ITEM", base))
            if name and ("UNIQUE", name) not in seen:
                entries.append({
                    "namespace": "UNIQUE", "ref_name": name, "base_ref": base,
                    "group": group_id, "names": {"en": name, "ja": ja_name or name},
                })
                seen.add(("UNIQUE", name))
    return {"schema_version": 2, "source": "scripts/poetore-poe2-sources.lock.json", "entries": entries}


def build_stat_index() -> dict:
    en = {entry["id"]: entry for group in _load("stats_en.json")["result"] for entry in group["entries"]}
    ja = {entry["id"]: entry for group in _load("stats_ja.json")["result"] for entry in group["entries"]}
    entries = []
    for stat_id, english in en.items():
        japanese = ja.get(stat_id)
        if japanese is None:
            continue
        entries.append({
            "id": stat_id,
            "type": str(english.get("type", "")),
            "text": {"en": str(english.get("text", "")), "ja": str(japanese.get("text", ""))},
        })
    return {"schema_version": 1, "source": "scripts/poetore-poe2-sources.lock.json", "entries": entries}


def build_augment_index(ee2_root: Path) -> dict:
    """Build the compact bilingual Rune/Soul Core editor index from fixed EE2 data."""
    localized = {}
    for language in ("en", "ja"):
        path = ee2_root / "renderer" / "public" / "data" / language / "items.ndjson"
        localized[language] = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
        ]
    entries = []
    for en, ja in zip(localized["en"], localized["ja"]):
        effects = en.get("augment") or ()
        if not effects:
            continue
        if en.get("refName") != ja.get("refName"):
            raise ValueError("EE2 bilingual augment rows are not aligned")
        ja_effects = ja.get("augment") or ()
        built_effects = []
        for index, effect in enumerate(effects):
            trade_ids = tuple(str(value) for value in effect.get("tradeId") or () if value)
            if not trade_ids:
                continue
            localized_effect = ja_effects[index] if index < len(ja_effects) else {}
            built_effects.append({
                "categories": list(effect.get("categories") or ()),
                "text": {
                    "en": str(effect.get("string", "")),
                    "ja": str(localized_effect.get("string") or effect.get("string", "")),
                },
                "values": list(effect.get("values") or ()),
                "trade_ids": list(trade_ids),
                "socket_bound": bool(effect.get("socketBound")),
            })
        if built_effects:
            entries.append({
                "ref_name": str(en.get("refName", "")),
                "names": {"en": str(en.get("name", "")), "ja": str(ja.get("name", ""))},
                "effects": built_effects,
            })
    return {
        "schema_version": 1,
        "source": "Exiled Exchange 2 d72afb83bc0888919a89d3c3744acee2c597e9c8",
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ee2-root", type=Path)
    parser.add_argument("--augment-only", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.augment_only:
        if args.ee2_root is None:
            parser.error("--augment-only requires --ee2-root")
        payloads = (("augment_index.json", build_augment_index(args.ee2_root)),)
    else:
        payloads = (
            ("identity_index.json", build_identity_index(args.ee2_root)),
            ("stat_index.json", build_stat_index()),
        )
    for name, payload in payloads:
        (OUTPUT / name).write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
