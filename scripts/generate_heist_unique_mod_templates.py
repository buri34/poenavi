"""Generate searchable Mod candidates for Grand Heist unique rewards.

PoE Wiki is used only to associate a unique item with internal game Mod IDs.
The runtime artifact contains normalized official Trade stat IDs and Japanese
labels; it does not contain Wiki prose or raw page content.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CURIO_PATH = ROOT / "data" / "poetore" / "poe1" / "heist_curio_ja_dictionary.json"
METADATA_PATH = ROOT / "data" / "poetore" / "mod_metadata.json"
OUTPUT_PATH = ROOT / "data" / "poetore" / "poe1" / "heist_unique_mod_templates.json"
AUDIT_PATH = ROOT / "docs" / "development" / "heist_unique_mod_audit.json"
WIKI_API = "https://www.poewiki.net/w/api.php"
UNIQUE_CATEGORIES = {"replica_unique", "replacement_unique"}
_EXPLICIT_RE = re.compile(r"^\s*\|\s*explicit\d+\s*=\s*([^\n|<]+)", re.MULTILINE)
_PLACEHOLDER_RE = re.compile(r"\{(\d+)\}")


def fetch_wiki_wikitext(titles: list[str], *, batch_size: int = 20) -> dict[str, str]:
    """Fetch page source in batches to avoid one request per unique."""
    result: dict[str, str] = {}
    for offset in range(0, len(titles), batch_size):
        batch = titles[offset : offset + batch_size]
        query = urlencode(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(batch),
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            }
        )
        request = Request(
            f"{WIKI_API}?{query}",
            headers={"User-Agent": "PoENavi dictionary generator/1.0"},
        )
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        for page in payload["query"]["pages"]:
            revisions = page.get("revisions") or []
            if page.get("missing") or not revisions:
                continue
            source = revisions[0]["slots"]["main"]["content"]
            result[str(page["title"])] = str(source)
        redirects = {
            str(row["from"]): str(row["to"])
            for row in payload["query"].get("redirects", ())
        }
        for original in batch:
            resolved = redirects.get(original, original)
            if resolved in result:
                result[original] = result[resolved]
    return result


def explicit_mod_ids(wikitext: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            match.group(1).strip() for match in _EXPLICIT_RE.finditer(wikitext)
        )
    )


def _condition_matches(condition: dict, minimum: float, maximum: float) -> bool:
    if "min" in condition and maximum < float(condition["min"]):
        return False
    return not ("max" in condition and minimum > float(condition["max"]))


def _translation_ref(
    mod: dict, translations_by_stat: dict[str, list[dict]]
) -> str | None:
    stats = tuple(mod.get("stats") or ())
    values = {str(row["id"]): row for row in stats}
    if not values:
        return None
    candidates = translations_by_stat.get(next(iter(values)), ())
    if not candidates:
        return None
    for candidate in candidates:
        ids = tuple(str(value) for value in candidate.get("ids") or ())
        if not set(values).issubset(ids):
            continue
        expanded_stats = tuple(
            values.get(stat_id, {"id": stat_id, "min": 0, "max": 0}) for stat_id in ids
        )
        translation = candidate["translation"]
        conditions = tuple(translation.get("condition") or ())
        if len(conditions) != len(expanded_stats):
            continue
        if not all(
            _condition_matches(
                condition,
                float(stat.get("min", 0)),
                float(stat.get("max", 0)),
            )
            for condition, stat in zip(conditions, expanded_stats, strict=True)
        ):
            continue
        formats = tuple(translation.get("format") or ())
        template = str(translation.get("string") or "")

        def replace_placeholder(
            match: re.Match[str],
            tokens: tuple = formats,
        ) -> str:
            index = int(match.group(1))
            token = tokens[index] if index < len(tokens) else "#"
            return "" if token == "ignore" else str(token)

        return re.sub(
            r"\s+", " ", _PLACEHOLDER_RE.sub(replace_placeholder, template)
        ).strip()
    return None


def _swap_direction(ref: str) -> str | None:
    replacements = (
        (" increased ", " reduced "),
        (" reduced ", " increased "),
        (" more ", " less "),
        (" less ", " more "),
    )
    padded = f" {ref} "
    for source, target in replacements:
        if source in padded:
            return padded.replace(source, target, 1).strip()
    return None


def _choose_trade_row(rows: list[dict], *, local: bool, item_group: str) -> dict | None:
    rows = [row for row in rows if row.get("kind") == "explicit"]
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    category = (
        "WEAPON"
        if item_group == "weapon"
        else "ARMOUR"
        if item_group == "armour"
        else None
    )
    if local:
        exact_category = [
            row for row in rows if category and row.get("category_select") == category
        ]
        if len(exact_category) == 1:
            return exact_category[0]
        preferred = [row for row in rows if row.get("local")]
    else:
        preferred = [
            row
            for row in rows
            if not row.get("local") and not row.get("category_select")
        ]
    return preferred[0] if len(preferred) == 1 else None


def resolve_mod(
    mod_id: str,
    *,
    item_group: str,
    repoe_mods: dict[str, dict],
    translations_by_stat: dict[str, list[dict]],
    trade_by_mod_id: dict[str, list[dict]],
    trade_by_ref: dict[str, list[dict]],
) -> tuple[dict | None, str]:
    mod = repoe_mods.get(mod_id)
    if mod is None:
        return None, "missing_repoe_mod"
    raw_ids = tuple(str(row["id"]) for row in mod.get("stats") or ())
    local = mod_id.startswith("Local") or any(
        value.startswith("local_") for value in raw_ids
    )
    row = _choose_trade_row(
        trade_by_mod_id.get(mod_id, []), local=local, item_group=item_group
    )
    inverted = False
    ref = _translation_ref(mod, translations_by_stat)
    if row is None and ref:
        row = _choose_trade_row(
            trade_by_ref.get(ref, []), local=local, item_group=item_group
        )
    if row is None and ref and (inverse_ref := _swap_direction(ref)):
        row = _choose_trade_row(
            trade_by_ref.get(inverse_ref, []),
            local=local,
            item_group=item_group,
        )
        inverted = row is not None
    if row is None:
        return None, "unresolved_trade_stat"
    japanese = tuple(str(value) for value in row.get("japanese") or () if value)
    if not japanese:
        return None, "missing_japanese_label"
    return {
        "stat_id": str(row["stat_id"]),
        "text_ja": japanese[0],
        "ref": str(row.get("ref") or ref or ""),
        "inverted": bool(row.get("inverted", False)) ^ inverted,
        "better": row.get("better"),
        "decimal": bool(row.get("decimal", False)),
    }, "resolved"


def generate_payload(
    curio_payload: dict,
    metadata_payload: dict,
    repoe_mods: dict[str, dict],
    stat_translations: list[dict],
    wiki_sources: dict[str, str],
    *,
    repoe_revision: str,
) -> tuple[dict, dict]:
    unique_items = [
        row for row in curio_payload["items"] if row["category"] in UNIQUE_CATEGORIES
    ]
    translations_by_stat: dict[str, list[dict]] = defaultdict(list)
    for translation in stat_translations:
        ids = tuple(str(value) for value in translation.get("ids") or ())
        for candidate in translation.get("English") or ():
            for stat_id in ids:
                translations_by_stat[stat_id].append(
                    {
                        "ids": ids,
                        "translation": candidate,
                    }
                )
    trade_by_mod_id: dict[str, list[dict]] = defaultdict(list)
    trade_by_ref: dict[str, list[dict]] = defaultdict(list)
    for row in metadata_payload["mods"]:
        if row.get("kind") != "explicit":
            continue
        trade_by_ref[str(row.get("ref") or "")].append(row)
        for tier in row.get("tiers") or ():
            if tier.get("mod_id"):
                trade_by_mod_id[str(tier["mod_id"])].append(row)

    entries = []
    unresolved: dict[str, list[str]] = defaultdict(list)
    for item in unique_items:
        title = str(item["name_en"])
        mod_ids = explicit_mod_ids(wiki_sources.get(title, ""))
        is_random_veiled = bool(mod_ids) and all(
            mod_id.startswith(("VeiledPrefix", "VeiledSuffix")) for mod_id in mod_ids
        )
        filters: list[dict] = []
        seen_stat_ids: set[tuple[str, bool]] = set()
        for mod_id in mod_ids:
            resolved, reason = resolve_mod(
                mod_id,
                item_group=str(item["search"].get("item_group") or ""),
                repoe_mods=repoe_mods,
                translations_by_stat=translations_by_stat,
                trade_by_mod_id=trade_by_mod_id,
                trade_by_ref=trade_by_ref,
            )
            if resolved is None:
                unresolved[reason].append(f"{title}: {mod_id}")
                continue
            key = (resolved["stat_id"], resolved["inverted"])
            if key in seen_stat_ids:
                continue
            seen_stat_ids.add(key)
            filters.append(resolved)
        if is_random_veiled:
            status = "random_veiled"
            filters = []
        elif filters and len(filters) == len(mod_ids):
            status = "fixed"
        elif filters:
            status = "partial"
        else:
            status = "no_searchable_filters"
        entries.append(
            {
                "stable_id": item["stable_id"],
                "category": item["category"],
                "name_en": item["name_en"],
                "name_ja": item["name_ja"],
                "status": status,
                "source_mod_count": len(mod_ids),
                "filters": filters,
            }
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "sources": {
            "poe_wiki": {"api": WIKI_API, "usage": "unique name to internal Mod IDs"},
            "repoe": {"revision": repoe_revision, "usage": "Mod and stat structures"},
            "poe_trade_metadata": {"path": "data/poetore/mod_metadata.json"},
        },
        "items": entries,
    }
    audit = {
        "schema_version": 1,
        "generated_at": generated_at,
        "unique_count": len(entries),
        "wiki_page_count": sum(
            bool(wiki_sources.get(row["name_en"])) for row in unique_items
        ),
        "missing_wiki_pages": sorted(
            row["name_en"]
            for row in unique_items
            if not wiki_sources.get(row["name_en"])
        ),
        "category_counts": {
            category: sum(row["category"] == category for row in entries)
            for category in sorted(UNIQUE_CATEGORIES)
        },
        "status_counts": {
            status: sum(row["status"] == status for row in entries)
            for status in ("fixed", "partial", "random_veiled", "no_searchable_filters")
        },
        "source_mod_count": sum(row["source_mod_count"] for row in entries),
        "searchable_filter_count": sum(len(row["filters"]) for row in entries),
        "unresolved": {
            key: sorted(values) for key, values in sorted(unresolved.items())
        },
    }
    return payload, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repoe-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--audit", type=Path, default=AUDIT_PATH)
    args = parser.parse_args()
    repoe_root = args.repoe_root.resolve()
    data_root = repoe_root / "RePoE" / "data"
    curio_payload = json.loads(CURIO_PATH.read_text(encoding="utf-8"))
    metadata_payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    unique_names = [
        str(row["name_en"])
        for row in curio_payload["items"]
        if row["category"] in UNIQUE_CATEGORIES
    ]
    wiki_sources = fetch_wiki_wikitext(unique_names)
    revision = subprocess.check_output(
        ["git", "-C", str(repoe_root), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    payload, audit = generate_payload(
        curio_payload,
        metadata_payload,
        json.loads((data_root / "mods.json").read_text(encoding="utf-8")),
        json.loads((data_root / "stat_translations.json").read_text(encoding="utf-8")),
        wiki_sources,
        repoe_revision=revision,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.audit.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
