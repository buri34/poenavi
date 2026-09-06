#!/usr/bin/env python3
"""Build compact bilingual PoE2 identity/stat indexes from locked snapshots."""

from __future__ import annotations

import json
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "vendor-sources" / "poe2-trade-api-2026-08-09"
OUTPUT = ROOT / "data" / "poetore" / "poe2"
RELATED_JAPANESE_OVERRIDES = ROOT / "scripts" / "poetore-poe2-related-japanese-overrides.json"
EE2_SOUL_CORE_REVISION = "cf58adf17a06fe453da47f3672803a33594abcf6"
EE2_SOUL_CORE_IDENTITIES = {
    "Atziri's Soul Core of Alacrity", "Atziri's Soul Core of Devotion",
    "Atziri's Soul Core of Inoculation", "Atziri's Soul Core of Vitality",
    "Jiquani's Soul Core of Abundance", "Jiquani's Soul Core of Automation",
    "Jiquani's Soul Core of Malediction", "Jiquani's Soul Core of Munitions",
    "Jiquani's Soul Core of Quaking", "Jiquani's Soul Core of Radiance",
    "Jiquani's Soul Core of Rallying", "Jiquani's Soul Core of Rippling",
    "Jiquani's Soul Core of Severing", "Jiquani's Soul Core of Snares",
    "Jiquani's Soul Core of Squalls", "Jiquani's Soul Core of Targeting",
    "Jiquani's Soul Core of Thundering",
}
EE2_SOUL_CORE_CHANGED_AUGMENTS = {
    "Atmohua's Soul Core of Retreat", "Cholotl's Soul Core of War",
    "Citaqualotl's Thesis", "Emergent Possibility",
    "Estazunti's Soul Core of Convalescence", "Jiquani's Thesis",
    "Katla's Gloom", "Legacy of Chernobog's Pillar", "Soul Core of Atmohua",
    "Soul Core of Cholotl", "Soul Core of Citaqualotl", "Soul Core of Jiquani",
    "Soul Core of Opiloti", "Soul Core of Puhuarte", "Soul Core of Tacati",
    "Soul Core of Ticaba", "Soul Core of Topotante", "Soul Core of Tzamoto",
    "Soul Core of Xopec", "Soul Core of Zalatl", "Soul Core of Zantipi",
    "Uhtred's Sidereus", "Uromoti's Soul Core of Attenuation",
}
EE2_SOUL_CORE_STAT_IDS = {
    "rune.stat_1195319608", "rune.stat_138373935", "rune.stat_1519474779",
    "rune.stat_1839315243", "rune.stat_2139847597", "rune.stat_2203195791",
    "rune.stat_2305301734", "rune.stat_2336703514", "rune.stat_2487305362",
    "rune.stat_2527686725", "rune.stat_2621116283", "rune.stat_3148103963",
    "rune.stat_3174700878", "rune.stat_3268281424", "rune.stat_3791899485",
    "rune.stat_3985867204", "rune.stat_4081947835", "rune.stat_4169430079",
    "rune.stat_653358410", "rune.stat_995044379",
}
EE2_SOUL_CORE_OFFICIAL_STATS = {
    "rune.stat_2148999925": {
        "en": "# to Level of all Warcry Skill Gems",
        "ja": "全てのウォークライスキルジェムのレベル #",
    },
    "rune.stat_2296009672": {
        "en": "# to Level of all Plant Skill Gems",
        "ja": "全てのプラントスキルジェムのレベル #",
    },
    "rune.stat_1062190843": {
        "en": "# to Level of all Storm Skill Gems",
        "ja": "全てのストームスキルジェムのレベル #",
    },
}
EE2_WEAPON_CATEGORIES = [
    "Bow", "Claw", "Crossbow", "Dagger", "Flail", "One Hand Axe",
    "One Hand Mace", "One Hand Sword", "Spear", "Talisman", "Two Hand Axe",
    "Two Hand Mace", "Two Hand Sword", "Warstaff", "Wand", "Staff", "Sceptre",
]
EE2_SOUL_CORE_EXTRA_AUGMENTS = {
    "Jiquani's Soul Core of Rallying": {
        "ref_name": "Jiquani's Soul Core of Rallying",
        "names": {
            "en": "Jiquani's Soul Core of Rallying",
            "ja": "ジクアニの決起のソウルコア",
        },
        "effects": [{
            "categories": EE2_WEAPON_CATEGORIES,
            "text": {
                "en": "# to Level of all Warcry Skill Gems",
                "ja": "全てのウォークライスキルジェムのレベル #",
            },
            "values": [1], "trade_ids": ["rune.stat_2148999925"],
            "socket_bound": False,
        }],
    },
    "Jiquani's Soul Core of Abundance": {
        "ref_name": "Jiquani's Soul Core of Abundance",
        "names": {
            "en": "Jiquani's Soul Core of Abundance",
            "ja": "ジクアニの豊富さのソウルコア",
        },
        "effects": [{
            "categories": EE2_WEAPON_CATEGORIES,
            "text": {
                "en": "# to Level of all Plant Skill Gems",
                "ja": "全てのプラントスキルジェムのレベル #",
            },
            "values": [1], "trade_ids": ["rune.stat_2296009672"],
            "socket_bound": False,
        }],
    },
    "Jiquani's Soul Core of Thundering": {
        "ref_name": "Jiquani's Soul Core of Thundering",
        "names": {
            "en": "Jiquani's Soul Core of Thundering",
            "ja": "ジクアニの雷鳴のソウルコア",
        },
        "effects": [{
            "categories": EE2_WEAPON_CATEGORIES,
            "text": {
                "en": "# to Level of all Storm Skill Gems",
                "ja": "全てのストームスキルジェムのレベル #",
            },
            "values": [1], "trade_ids": ["rune.stat_1062190843"],
            "socket_bound": False,
        }],
    },
}


def _related_japanese_overrides() -> tuple[dict, ...]:
    payload = json.loads(RELATED_JAPANESE_OVERRIDES.read_text(encoding="utf-8"))
    return tuple(payload.get("overrides", ()))


def _apply_related_identity_overrides(entries: list[dict]) -> None:
    by_key = {(row.get("namespace"), row.get("ref_name")): row for row in entries}
    for override in _related_japanese_overrides():
        key = (override["namespace"], override["ref_name"])
        row = by_key.get(key)
        if row is None:
            row = {
                "namespace": override["namespace"],
                "ref_name": override["ref_name"],
                "names": {"en": override["ref_name"]},
            }
            if override.get("base_ref"):
                row["base_ref"] = override["base_ref"]
            entries.append(row)
            by_key[key] = row
        row.setdefault("names", {})["ja"] = override["japanese"]


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
            # Keep the EE2 base variant fingerprint.  Several PoE2 bases share
            # the same localized name (and occasionally even the same refName),
            # so flattening these fields makes exact Trade2 identity resolution
            # impossible for copied rare/magic equipment.
            if en.get("tags"):
                row["tags"] = list(en["tags"])
            if en.get("armour"):
                row["armour"] = {
                    key: list(value) for key, value in en["armour"].items()
                }
            if en.get("craftable", {}).get("category"):
                row["category"] = en["craftable"]["category"]
            if en.get("unique"):
                row["base_ref"] = en["unique"].get("base", "")
            entries.append(row)
        _apply_related_identity_overrides(entries)
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


def apply_v0162_soul_core_update(ee2_root: Path) -> None:
    """Merge only the reviewed v0.16.2 Soul Core changes into runtime indexes."""
    if __import__("subprocess").check_output(
        ["git", "-C", str(ee2_root), "rev-parse", "HEAD"], text=True,
    ).strip() != EE2_SOUL_CORE_REVISION:
        raise ValueError("EE2 checkout must be pinned to the reviewed v0.16.2 revision")

    identity = json.loads((OUTPUT / "identity_index.json").read_text(encoding="utf-8"))
    candidate_identity = build_identity_index(ee2_root)
    selected_identity = {
        row["ref_name"]: row for row in candidate_identity["entries"]
        if row["ref_name"] in EE2_SOUL_CORE_IDENTITIES
    }
    if selected_identity.keys() != EE2_SOUL_CORE_IDENTITIES:
        raise ValueError("reviewed Soul Core identity set is incomplete")
    identity["entries"] = [
        row for row in identity["entries"]
        if row["ref_name"] not in EE2_SOUL_CORE_IDENTITIES
    ] + [selected_identity[name] for name in sorted(selected_identity)]
    if EE2_SOUL_CORE_REVISION not in identity["source"]:
        identity["source"] += f" + selected EE2 {EE2_SOUL_CORE_REVISION} Soul Cores"

    augment = json.loads((OUTPUT / "augment_index.json").read_text(encoding="utf-8"))
    candidate_augment = {
        row["ref_name"]: row for row in build_augment_index(ee2_root)["entries"]
    }
    candidate_augment.update(EE2_SOUL_CORE_EXTRA_AUGMENTS)
    selected_augments = (
        (EE2_SOUL_CORE_IDENTITIES & candidate_augment.keys())
        | EE2_SOUL_CORE_CHANGED_AUGMENTS
    )
    if not selected_augments <= candidate_augment.keys():
        raise ValueError("reviewed Soul Core augment set is incomplete")
    by_augment = {row["ref_name"]: row for row in augment["entries"]}
    by_augment.update({name: candidate_augment[name] for name in selected_augments})
    augment["entries"] = list(by_augment.values())
    if EE2_SOUL_CORE_REVISION not in augment["source"]:
        augment["source"] += f" + selected EE2 {EE2_SOUL_CORE_REVISION} Soul Cores"

    localized_stats = {}
    for language in ("en", "ja"):
        path = ee2_root / "renderer" / "public" / "data" / language / "stats.ndjson"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        localized_stats[language] = {}
        for row in rows:
            for stat_id in ((row.get("trade") or {}).get("ids") or {}).get("rune", ()):
                if stat_id in EE2_SOUL_CORE_STAT_IDS:
                    localized_stats[language][stat_id] = row["matchers"][0]["string"]
    if any(set(rows) != EE2_SOUL_CORE_STAT_IDS for rows in localized_stats.values()):
        raise ValueError("reviewed Soul Core Stat ID set is incomplete")
    stats = json.loads((OUTPUT / "stat_index.json").read_text(encoding="utf-8"))
    by_stat = {row["id"]: row for row in stats["entries"]}
    by_stat.pop("rune.stat_3170380905", None)
    for stat_id in sorted(EE2_SOUL_CORE_STAT_IDS):
        by_stat[stat_id] = {
            "id": stat_id, "type": "augment",
            "text": {lang: localized_stats[lang][stat_id] for lang in ("en", "ja")},
        }
    for stat_id, text in EE2_SOUL_CORE_OFFICIAL_STATS.items():
        by_stat[stat_id] = {"id": stat_id, "type": "augment", "text": text}
    stats["entries"] = list(by_stat.values())
    if EE2_SOUL_CORE_REVISION not in stats["source"]:
        stats["source"] += f" + selected EE2 {EE2_SOUL_CORE_REVISION} Rune stats"

    for name, payload in (
        ("identity_index.json", identity), ("augment_index.json", augment),
        ("stat_index.json", stats),
    ):
        (OUTPUT / name).write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )


def _related_identity(value: str) -> dict:
    namespace, identity = value.split("::", 1)
    name, separator, variant = identity.partition(" // ")
    row = {"id": value, "namespace": namespace, "name": name}
    if separator:
        row["variant"] = variant
    return row


def _poe2_ninja_type(row: dict, identities: dict[tuple[str, str], list[dict]]) -> str | None:
    namespace, name = row["namespace"], row["name"]
    matches = identities.get((namespace, name), ())
    if namespace == "GEM":
        return "LineageSupportGems"
    if namespace == "UNIQUE":
        base = row.get("variant") or next(
            (match.get("unique", {}).get("base") for match in matches if match.get("unique")), ""
        )
        bases = identities.get(("ITEM", base), ())
        category = next(
            ((match.get("craftable") or {}).get("category") for match in bases
             if (match.get("craftable") or {}).get("category")), ""
        )
        if category in {"Ring", "Amulet", "Belt", "Talisman"}:
            return "UniqueAccessories"
        if category in {"Flask"}:
            return "UniqueFlasks"
        if category in {"Jewel"}:
            return "UniqueJewels"
        if category in {"Tablet"}:
            return "UniqueTablets"
        if category in {"SanctumRelic", "Relic"}:
            return "UniqueSanctumRelics"
        if category in {
            "Bow", "Crossbow", "Spear", "Flail", "Staff", "Quarterstaff", "Warstaff",
            "Wand", "Sceptre", "OneHandMace", "TwoHandMace", "One Hand Mace",
            "Two Hand Mace", "OneHandSword", "TwoHandSword", "One Hand Sword",
            "Two Hand Sword", "OneHandAxe", "TwoHandAxe", "One Hand Axe",
            "Two Hand Axe", "Dagger",
        }:
            return "UniqueWeapons"
        return "UniqueArmours" if category else None
    if namespace != "ITEM":
        return None
    category = next(
        ((match.get("craftable") or {}).get("category") for match in matches
         if (match.get("craftable") or {}).get("category")), ""
    )
    tags = {tag for match in matches for tag in match.get("tags", ())}
    if category == "SoulCore":
        return "Ultimatum"
    if category == "Omen":
        return "Ritual"
    if category in {"VaultKey", "MapFragment", "PinnacleKey", "MiscMapItem"}:
        return "Fragments"
    if "catalyst" in tags or "breachstone_splinter" in tags:
        return "Breach"
    if "mushrune" in tags or "affliction_orb" in tags:
        return "Delirium"
    if any(tag.startswith("expedition_currency") for tag in tags):
        return "Expedition"
    if not tags and any(token in name for token in ("Collarbone", "Jawbone", "Rib", "Cranium", "Vertebrae")):
        return "Abyss"
    return "Currency" if category == "Currency" else None


def build_related_item_groups(ee2_root: Path) -> dict:
    data_root = ee2_root / "renderer" / "public" / "data"
    localized = {}
    identity_rows: dict[tuple[str, str], list[dict]] = {}
    for language in ("en", "ja"):
        localized[language] = [
            json.loads(line) for line in (data_root / language / "items.ndjson").read_text(
                encoding="utf-8"
            ).splitlines() if line
        ]
    for row in localized["en"]:
        identity_rows.setdefault((row.get("namespace", ""), row.get("refName", "")), []).append(row)
    japanese = {
        (row.get("namespace", ""), row.get("refName", "")): row.get("name", "")
        for row in localized["ja"]
    }
    japanese.update({
        (row["namespace"], row["ref_name"]): row["japanese"]
        for row in _related_japanese_overrides()
    })

    def enrich(value: str) -> dict:
        row = _related_identity(value)
        display = japanese.get((row["namespace"], row["name"]))
        if display:
            row["display_name"] = display
        ninja_type = _poe2_ninja_type(row, identity_rows)
        if ninja_type:
            row["ninja_type"] = ninja_type
        return row

    raw_groups = json.loads((data_root / "item-drop.json").read_text(encoding="utf-8"))
    groups = [{
        "query": [enrich(value) for value in group.get("query", ())],
        "items": [enrich(value) for value in group.get("items", ())],
    } for group in raw_groups]
    return {
        "schema_version": 1,
        "source": "Exiled Exchange 2 d72afb83bc0888919a89d3c3744acee2c597e9c8",
        "groups": groups,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ee2-root", type=Path)
    parser.add_argument("--augment-only", action="store_true")
    parser.add_argument("--related-only", action="store_true")
    parser.add_argument("--v0162-soul-cores", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.v0162_soul_cores:
        if args.ee2_root is None:
            parser.error("--v0162-soul-cores requires --ee2-root")
        apply_v0162_soul_core_update(args.ee2_root)
        return
    if args.augment_only or args.related_only:
        if args.ee2_root is None:
            parser.error("--augment-only/--related-only requires --ee2-root")
        payloads = (("augment_index.json", build_augment_index(args.ee2_root)),) if args.augment_only else (
            ("related_item_groups.json", build_related_item_groups(args.ee2_root)),
        )
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
