#!/usr/bin/env python3
"""Build the compact PoE2 Desecration Reveal tier database.

The input is a pinned Path of Building Community PoE2 checkout.  PoB stores
the source modifier family, required level, roll ranges and ordered spawn
weights; Tier numbers are derived per concrete base-tag profile from those
fields.  Japanese display templates come from PoENavi's locked Trade2 index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAT_INDEX = ROOT / "data" / "poetore" / "poe2" / "stat_index.json"
DEFAULT_OUTPUT = ROOT / "data" / "poetore" / "poe2" / "desecration_tiers.json"
ROW_RE = re.compile(r'^\s*\["([^"]+)"\] = \{(.*)\},\s*$')
BASE_RE = re.compile(r'itemBases\["([^"]+)"\]\s*=\s*\{(.*?)\n\}', re.DOTALL)
NUMBER = r"[+-]?\d+(?:\.\d+)?"
RANGE_RE = re.compile(rf"^\(\s*({NUMBER})\s*-\s*({NUMBER})\s*\)$")
NAMED_DESECRATION_TAGS = {"ulaman_mod", "amanamu_mod", "kurgal_mod"}
JEWEL_TAGS = {"strjewel", "dexjewel", "intjewel"}
BASE_TAGS = {
    "amulet", "armour", "axe", "belt", "body_armour", "boots", "bow",
    "cannon", "claw", "crossbow", "dagger", "dex_armour", "dex_int_armour",
    "dexjewel", "flail", "focus", "gloves", "helmet", "int_armour",
    "intjewel", "mace", "one_hand_weapon", "quiver", "ring", "sceptre",
    "shield", "spear", "staff", "str_armour", "str_dex_armour",
    "str_dex_int_armour", "str_int_armour", "strjewel", "sword", "talisman",
    "two_hand_weapon", "wand", "warstaff", "weapon",
}
EXCLUDED_CATEGORIES = {
    "charm", "fishing_rod", "flask", "incursion_limb", "transcendent_limb",
    "trap", "traptool",
}
MISSING_PROFILE_OVERRIDES = {
    "AbyssModBootsUlamanSuffixReducedMovementPenaltyWhileSkilling": "boots",
    "AbyssModGlovesAmanamuSuffixPercentOfLifeLeechInstant": "gloves",
}
DIRECTION_RULES = (
    ("increased", "reduced", "増加", "減少", "decrease"),
    ("reduced", "increased", "減少", "増加", "increase"),
)


def quoted_list(text: str) -> list[str]:
    return re.findall(r'"((?:\\.|[^"\\])*)"', text)


def field(body: str, name: str, default: str = "") -> str:
    match = re.search(rf'{re.escape(name)} = "([^"]*)"', body)
    return match.group(1) if match else default


def number_field(body: str, name: str, default: int = 0) -> int:
    match = re.search(rf"{re.escape(name)} = (-?\d+)", body)
    return int(match.group(1)) if match else default


def weight_rules(body: str) -> list[tuple[str, float]]:
    keys_match = re.search(r"weightKey = \{([^}]*)\}", body)
    vals_match = re.search(r"weightVal = \{([^}]*)\}", body)
    if not keys_match or not vals_match:
        return []
    keys = quoted_list(keys_match.group(1))
    values = [float(value) for value in re.findall(NUMBER, vals_match.group(1))]
    return list(zip(keys, values))


def trade_hashes(body: str) -> dict[str, list[str]]:
    if "tradeHashes = {" not in body:
        return {}
    section = body.split("tradeHashes = {", 1)[1]
    return {
        match.group(1): quoted_list(match.group(2))
        for match in re.finditer(r"\[(\d+)\] = \{(.*?)\},", section)
    }


def parse_mod_file(path: Path, source: str) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ROW_RE.match(line)
        if not match:
            continue
        mod_id, body = match.groups()
        tags_match = re.search(r"modTags = \{([^}]*)\}", body)
        rows.append({
            "source": source,
            "mod_id": mod_id,
            "type": field(body, "type"),
            "affix": field(body, "affix"),
            "group": field(body, "group"),
            "level": number_field(body, "level"),
            "weights": weight_rules(body),
            "mod_tags": quoted_list(tags_match.group(1)) if tags_match else [],
            "trade_hashes": trade_hashes(body),
        })
    return rows


def category_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def concrete_base_category(category: str, tags: tuple[str, ...]) -> str:
    """Split PoB's shared Staff base type into its concrete PoE2 categories."""
    if category == "staff" and "warstaff" in tags:
        return "quarterstaff"
    return category


def parse_base_profiles(bases_dir: Path) -> list[dict]:
    profiles: dict[tuple[str, tuple[str, ...]], dict] = {}
    for path in sorted(bases_dir.glob("*.lua")):
        for _name, body in BASE_RE.findall(path.read_text(encoding="utf-8")):
            type_match = re.search(r'\btype = "([^"]+)"', body)
            tags_match = re.search(r"\btags = \{([^}]*)\}", body)
            if not type_match or not tags_match:
                continue
            category = category_key(type_match.group(1))
            if category in EXCLUDED_CATEGORIES:
                continue
            tags = tuple(sorted(re.findall(r"([a-z0-9_]+)\s*=\s*true", tags_match.group(1))))
            if not tags:
                continue
            category = concrete_base_category(category, tags)
            key = (category, tags)
            profiles.setdefault(key, {"category": category, "tags": list(tags)})
    result = []
    for index, profile in enumerate(sorted(profiles.values(), key=lambda row: (row["category"], row["tags"]))):
        result.append({"id": f"p{index:03d}", **profile})
    return result


def spawn_weight(row: dict, profile: dict) -> float:
    tags = set(profile["tags"])
    for key, value in row["weights"]:
        if key in tags:
            return value
    return 0


def classify(rows: list[dict], profiles: list[dict]) -> list[dict]:
    selected = []
    for row in rows:
        mod_tags = set(row["mod_tags"])
        positive_tags = {key for key, value in row["weights"] if value > 0}
        if row["source"] in {"ModItem", "ModJewel"} and positive_tags & BASE_TAGS:
            pool = "normal"
        elif row["source"] == "ModVeiled" and mod_tags & NAMED_DESECRATION_TAGS:
            pool = "desecration_exclusive"
        elif row["source"] == "ModVeiled" and row["mod_id"].startswith("AbyssModJewel"):
            pool = "desecration_exclusive_jewel"
        else:
            continue
        applicable = [profile["id"] for profile in profiles if spawn_weight(row, profile) > 0]
        override = MISSING_PROFILE_OVERRIDES.get(row["mod_id"])
        if override:
            applicable = [profile["id"] for profile in profiles if profile["category"] == override]
        if pool == "desecration_exclusive_jewel":
            applicable = [
                profile["id"] for profile in profiles
                if set(profile["tags"]) & JEWEL_TAGS and spawn_weight(row, profile) > 0
            ]
        if not applicable or not row["trade_hashes"]:
            continue
        row = dict(row)
        row["pool"] = pool
        row["profiles"] = applicable
        selected.append(row)
    return selected


def merge_duplicate_records(rows: list[dict]) -> list[dict]:
    merged: dict[tuple, dict] = {}
    for row in rows:
        signature = (
            row["pool"], row["type"], row["group"], row["level"],
            json.dumps(row["trade_hashes"], sort_keys=True),
        )
        if signature not in merged:
            merged[signature] = row
            continue
        current = merged[signature]
        current["mod_id"] += ";" + row["mod_id"]
        current["profiles"] = sorted(set(current["profiles"]) | set(row["profiles"]))
    return list(merged.values())


def assign_profile_tiers(rows: list[dict], profiles: list[dict]) -> None:
    buckets: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        for profile_id in row["profiles"]:
            buckets[(row["pool"], row["type"], row["group"], profile_id)].append(row)
    tiers: dict[str, dict[str, int]] = defaultdict(dict)
    for (_pool, _type, _group, profile_id), candidates in buckets.items():
        levels = sorted({row["level"] for row in candidates}, reverse=True)
        by_level = {level: index + 1 for index, level in enumerate(levels)}
        for row in candidates:
            tiers[row["mod_id"]][profile_id] = by_level[row["level"]]
    for row in rows:
        row["tiers"] = tiers[row["mod_id"]]


def load_stats(path: Path) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for entry in json.loads(path.read_text(encoding="utf-8"))["entries"]:
        match = re.search(r"\.stat_(\d+)$", entry["id"])
        if match and entry.get("type") in {"explicit", "desecrated"}:
            result[match.group(1)].append(entry)
    return result


def preferred_stat(entries: list[dict]) -> dict | None:
    for kind in ("desecrated", "explicit"):
        for entry in entries:
            if entry.get("type") == kind:
                return entry
    return None


def value_ranges(template: str, rendered: str) -> list[list[float]] | None:
    template = re.sub(r"\s*\(Local\)\s*$", "", template, flags=re.IGNORECASE)
    parts = re.split(r"(\#)", template)
    pattern = ""
    captures = 0
    token = rf"\+?(?:\(\s*{NUMBER}\s*-\s*{NUMBER}\s*\)|{NUMBER})"
    for part in parts:
        if part == "#":
            pattern += f"({token})"
            captures += 1
        else:
            pattern += re.escape(part)
    match = re.fullmatch(pattern, rendered, re.IGNORECASE)
    if not match or len(match.groups()) != captures:
        return None
    ranges = []
    for value in match.groups():
        comparable = value[1:] if value.startswith("+(") else value
        ranged = RANGE_RE.match(comparable)
        if ranged:
            ranges.append([float(ranged.group(1)), float(ranged.group(2))])
        else:
            numeric = float(comparable)
            ranges.append([numeric, numeric])
    return ranges


def resolve_directional_part(
    en_template: str, ja_template: str, rendered: str,
) -> dict | None:
    """Resolve a strict PoB2 polarity mismatch without guessing other text."""
    for source_word, target_word, ja_source, ja_target, direction in DIRECTION_RULES:
        if len(re.findall(rf"\b{source_word}\b", en_template, re.IGNORECASE)) != 1:
            continue
        if ja_template.count(ja_source) != 1:
            continue
        adjusted_en = re.sub(
            rf"\b{source_word}\b", target_word, en_template,
            count=1, flags=re.IGNORECASE,
        )
        ranges = value_ranges(adjusted_en, rendered)
        if ranges is None:
            continue
        return {
            "en": adjusted_en,
            "ja": ja_template.replace(ja_source, ja_target, 1),
            "ranges": [
                [min(abs(low), abs(high)), max(abs(low), abs(high))]
                for low, high in ranges
            ],
            "direction": direction,
        }
    return None


def build_parts(row: dict, stats: dict[str, list[dict]]) -> list[dict]:
    parts = []
    for hash_value, descriptions in row["trade_hashes"].items():
        stat = preferred_stat(stats.get(hash_value, []))
        if not stat:
            continue
        en_template = str(stat["text"].get("en", ""))
        ja_template = str(stat["text"].get("ja", ""))
        for description in descriptions:
            ranges = value_ranges(en_template, description)
            directional = None
            if ranges is None:
                directional = resolve_directional_part(
                    en_template, ja_template, description,
                )
            part = {
                "stat_hash": hash_value,
                "stat_id": f"desecrated.stat_{hash_value}",
                "text": {
                    "en": directional["en"] if directional else en_template,
                    "ja": directional["ja"] if directional else ja_template,
                },
                "ranges": directional["ranges"] if directional else ranges,
                "source_text": description,
            }
            if directional:
                part["direction"] = directional["direction"]
            parts.append(part)
    return parts


def template_audit(entries: list[dict]) -> dict:
    mixed = []
    skeletons: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        for part in entry["parts"]:
            template = str(part["text"]["ja"])
            if "#" in template and re.search(r"\d", template):
                mixed.append({"mod_id": entry["mod_id"], "template": template})
            skeleton = re.sub(NUMBER, "#", template)
            skeletons[skeleton].add(template)
    collisions = [
        {"numeric_skeleton": skeleton, "templates": sorted(templates)}
        for skeleton, templates in sorted(skeletons.items()) if len(templates) > 1
    ]
    return {
        "mixed_fixed_dynamic_parts": len(mixed),
        "mixed_fixed_dynamic_templates": len({row["template"] for row in mixed}),
        "numeric_skeleton_collisions": collisions,
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(path.glob("*.lua")):
        digest.update(child.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(child.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def git_revision(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True,
    ).strip()


def build(pob2: Path, stat_index: Path, output: Path, expected_revision: str | None) -> dict:
    revision = git_revision(pob2)
    if expected_revision and revision != expected_revision:
        raise ValueError(f"PoB2 revision mismatch: expected {expected_revision}, got {revision}")
    profiles = parse_base_profiles(pob2 / "src" / "Data" / "Bases")
    all_rows = []
    source_paths = []
    for filename, source in (("ModItem.lua", "ModItem"), ("ModJewel.lua", "ModJewel"), ("ModVeiled.lua", "ModVeiled")):
        path = pob2 / "src" / "Data" / filename
        source_paths.append(path)
        all_rows.extend(parse_mod_file(path, source))
    rows = merge_duplicate_records(classify(all_rows, profiles))
    assign_profile_tiers(rows, profiles)
    stats = load_stats(stat_index)
    entries = []
    skipped_parts = []
    polarity_adjusted_rows = []
    for row in rows:
        parts = build_parts(row, stats)
        if len(parts) != len(row["trade_hashes"]) or any(part["ranges"] is None for part in parts):
            skipped_parts.append(row["mod_id"])
        if any("direction" in part for part in parts):
            polarity_adjusted_rows.append(row["mod_id"])
        entries.append({
            "mod_id": row["mod_id"],
            "pool": row["pool"],
            "type": row["type"],
            "group": row["group"],
            "required_level": row["level"],
            "profile_tiers": row["tiers"],
            "parts": parts,
        })
    payload = {
        "schema_version": 1,
        "source": {
            "pob2_url": "https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2",
            "pob2_revision": revision,
            "pob2_files": {path.name: sha256(path) for path in source_paths},
            "pob2_bases_sha256": tree_sha256(pob2 / "src" / "Data" / "Bases"),
            "trade_stat_index": str(stat_index.relative_to(ROOT)),
            "trade_stat_index_sha256": sha256(stat_index),
            "tier_derivation": "required levels descending within pool/type/group/base-tag profile",
        },
        "profiles": profiles,
        "entries": sorted(entries, key=lambda row: (row["pool"], row["mod_id"])),
        "diagnostics": {
            "selected_rows": len(rows),
            "emitted_rows": len(entries),
            "fully_matchable_rows": len(entries) - len(skipped_parts),
            "rows_with_unparsed_parts": sorted(skipped_parts),
            "polarity_adjusted_rows": sorted(polarity_adjusted_rows),
            **template_audit(entries),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pob2", type=Path, required=True)
    parser.add_argument("--expected-revision")
    parser.add_argument("--stat-index", type=Path, default=DEFAULT_STAT_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build(args.pob2, args.stat_index, args.output, args.expected_revision)
    print(f"profiles: {len(payload['profiles'])}")
    print(f"entries: {len(payload['entries'])}")
    print(f"unparsed: {len(payload['diagnostics']['rows_with_unparsed_parts'])}")
    print(f"output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
