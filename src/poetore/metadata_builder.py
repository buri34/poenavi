from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Iterable

from .metadata import normalize_stat_text


SUPPORTED_KINDS = {"explicit", "implicit", "crafted", "fractured", "enchant", "veiled"}
INDEX_FIELDS = (
    "ref", "stat_id", "kind", "japanese", "better", "inverted", "exact",
    "local", "decimal", "tiers", "options",
)


def _awakened_stats(lines: Iterable[str]) -> list[dict]:
    rows = []
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        rows.extend(row.get("stats", ())) if "stats" in row else rows.append(row)
    return rows


def _trade_entries(payload: dict) -> dict[tuple[str, str], dict]:
    return {
        (str(entry.get("type", "")), str(entry.get("id", ""))): entry
        for group in payload.get("result", ()) for entry in group.get("entries", ())
    }


def _repoe_by_ref(stats: dict, mods: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for mod_id, mod in mods.items():
        if mod.get("domain") != "item" or not mod.get("stats"):
            continue
        ref = normalize_stat_text(str(mod.get("text", "")))
        if not ref:
            continue
        local = any(bool(stats.get(stat.get("id"), {}).get("is_local")) for stat in mod["stats"])
        tier_rows = result.setdefault(ref, {"local": False, "tiers": []})
        tier_rows["local"] = tier_rows["local"] or local
        first = mod["stats"][0]
        tier_rows["tiers"].append({
            "tier": None,
            "minimum": float(first.get("min", 0)),
            "maximum": float(first.get("max", 0)),
            "required_level": int(mod.get("required_level", 0)) or None,
            "generation": mod.get("generation_type"),
            "mod_id": mod_id,
        })
    return result


def _base_armour(items_lines: Iterable[str]) -> dict[str, dict[str, list[int]]]:
    result = {}
    for line in items_lines:
        if not line.strip():
            continue
        row = json.loads(line)
        armour = row.get("armour") or {}
        bounds = {
            key: [int(value[0]), int(value[1])]
            for key, value in armour.items()
            if key in {"ar", "ev", "es", "ward"}
            and isinstance(value, list) and len(value) == 2 and value[0] != value[1]
        }
        if bounds and row.get("refName"):
            result[str(row["refName"]).strip().casefold()] = bounds
    return dict(sorted(result.items()))


def _gems(items_lines: Iterable[str]) -> dict[str, dict]:
    result = {}
    for line in items_lines:
        if not line.strip():
            continue
        row = json.loads(line)
        gem = row.get("gem")
        if row.get("namespace") != "GEM" or not gem or not row.get("refName"):
            continue
        result[str(row["refName"]).strip().casefold()] = {
            "trade_type": str(gem.get("normalVariant") or row["refName"]),
            "max_level": int(gem.get("maxLevel", 20)),
            "transfigured": bool(gem.get("transfigured", False)),
            "vaal": bool(gem.get("vaal", False)),
            "discriminator": str(row.get("tradeDisc", "")) or None,
        }
    return dict(sorted(result.items()))


def _unique_fixed_stats(items_lines: Iterable[str]) -> dict[str, list[str]]:
    """Awakenedのユニーク別fixedStatsを名前で引ける派生データへ縮小する。"""
    result = {}
    for line in items_lines:
        if not line.strip():
            continue
        row = json.loads(line)
        unique = row.get("unique") or {}
        fixed_stats = unique.get("fixedStats")
        if row.get("namespace") != "UNIQUE" or not row.get("refName") or fixed_stats is None:
            continue
        result[str(row["refName"]).strip().casefold()] = [
            str(ref) for ref in fixed_stats if str(ref).strip()
        ]
    return dict(sorted(result.items()))


def build_minimal_index(awakened_lines: Iterable[str], jp_trade: dict,
                        repoe_stats: dict | None = None,
                        repoe_mods: dict | None = None,
                        awakened_items: Iterable[str] = (),
                        sources: dict | None = None,
                        generated_at: str | None = None) -> dict:
    """必要な照合・検索項目だけに縮小した派生インデックスを生成する。"""
    jp = _trade_entries(jp_trade)
    repoe = _repoe_by_ref(repoe_stats or {}, repoe_mods or {})
    records = []
    seen = set()
    for stat in _awakened_stats(awakened_lines):
        trade = stat.get("trade") or {}
        for kind, ids in (trade.get("ids") or {}).items():
            if kind not in SUPPORTED_KINDS:
                continue
            for stat_id in ids:
                entry = jp.get((kind, stat_id))
                if not entry or (kind, stat_id) in seen:
                    continue
                seen.add((kind, stat_id))
                repoe_row = repoe.get(normalize_stat_text(str(stat.get("ref", ""))), {})
                options = []
                if trade.get("option"):
                    jp_options = {
                        str(option.get("id")): str(option.get("text", ""))
                        for option in (entry.get("option") or {}).get("options", ())
                    }
                    template = str(entry.get("text", ""))
                    for matcher in stat.get("matchers", ()):
                        if "value" not in matcher:
                            continue
                        value = matcher["value"]
                        japanese_value = jp_options.get(str(value))
                        if not japanese_value:
                            continue
                        oils = [int(oil) for oil in str(matcher.get("oils", "")).split(",") if oil]
                        options.append({
                            "value": value,
                            "japanese": template.replace("#", japanese_value, 1),
                            "english": str(matcher.get("string", "")),
                            "oils": oils,
                        })
                records.append({
                    "ref": str(stat.get("ref", "")),
                    "stat_id": stat_id,
                    "kind": kind,
                    "japanese": [str(entry.get("text", ""))],
                    "better": int(stat.get("better", 1)),
                    "inverted": bool(trade.get("inverted", False)),
                    "exact": int(stat.get("better", 1)) == 0 or bool(trade.get("option", False)),
                    "local": bool(repoe_row.get("local", False)),
                    # Awakenedのdpフラグがあるstatだけ小数精度を維持する。
                    "decimal": bool(stat.get("dp", False)),
                    "tiers": repoe_row.get("tiers", ()),
                    "options": options,
                })
    records.sort(key=lambda row: (row["kind"], row["stat_id"]))
    return {
        "schema_version": 2,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "sources": sources or {},
        "scope": "PoE1 trade stat matching for equipment and gems",
        "base_armour": _base_armour(awakened_items),
        "gems": _gems(awakened_items),
        "unique_fixed_stats": _unique_fixed_stats(awakened_items),
        "mods": records,
    }


def validate_minimal_index(payload: dict) -> dict:
    """更新前に、壊れた・曖昧な派生インデックスを検出する。"""
    mods = payload.get("mods", ())
    errors: list[str] = []
    for name, gem in payload.get("gems", {}).items():
        if (not name or not gem.get("trade_type") or not isinstance(gem.get("max_level"), int)
                or gem["max_level"] < 1):
            errors.append(f"invalid gem metadata: {name}")
        if gem.get("transfigured") and not gem.get("discriminator"):
            errors.append(f"transfigured gem missing discriminator: {name}")
    for base_type, armour in payload.get("base_armour", {}).items():
        if not base_type or not armour:
            errors.append("empty base armour record")
            continue
        for defence, bounds in armour.items():
            if (defence not in {"ar", "ev", "es", "ward"}
                    or not isinstance(bounds, list) or len(bounds) != 2
                    or bounds[0] >= bounds[1]):
                errors.append(f"invalid base armour bounds: {base_type}:{defence}={bounds}")
    for unique_name, fixed_stats in payload.get("unique_fixed_stats", {}).items():
        if (not unique_name or not isinstance(fixed_stats, list)
                or any(not isinstance(ref, str) or not ref.strip() for ref in fixed_stats)
                or len(fixed_stats) != len(set(fixed_stats))):
            errors.append(f"invalid unique fixed stats: {unique_name}")
    keys: set[tuple[str, str]] = set()
    matchers: dict[tuple[str, str], list[str]] = {}
    for index, row in enumerate(mods):
        missing = [field for field in INDEX_FIELDS if field not in row]
        if missing:
            errors.append(f"mods[{index}] missing fields: {', '.join(missing)}")
            continue
        key = (str(row["kind"]), str(row["stat_id"]))
        if key in keys:
            errors.append(f"duplicate stat ID: {key[0]}:{key[1]}")
        keys.add(key)
        japanese = row.get("japanese") or []
        if not japanese or any(not str(value).strip() for value in japanese):
            errors.append(f"empty Japanese matcher: {key[0]}:{key[1]}")
        for matcher in japanese:
            normalized = normalize_stat_text(str(matcher))
            matchers.setdefault((key[0], normalized), []).append(key[1])
        option_keys = set()
        for option in row.get("options", ()):
            option_key = str(option.get("value", ""))
            if not option_key or not str(option.get("japanese", "")).strip():
                errors.append(f"invalid option: {key[0]}:{key[1]}")
            if option_key in option_keys:
                errors.append(f"duplicate option: {key[0]}:{key[1]}:{option_key}")
            option_keys.add(option_key)
    ambiguous = [
        {"kind": kind, "matcher": matcher, "stat_ids": sorted(set(stat_ids))}
        for (kind, matcher), stat_ids in sorted(matchers.items())
        if len(set(stat_ids)) > 1
    ]
    return {
        "record_count": len(mods),
        "errors": errors,
        "ambiguous_matchers": ambiguous,
    }


def diff_minimal_indexes(previous: dict, candidate: dict) -> dict:
    """レビュー可能なMod単位の新旧差分を返す。時刻など非解析項目は比較しない。"""
    def keyed(payload: dict) -> dict[tuple[str, str], dict]:
        return {
            (str(row.get("kind", "")), str(row.get("stat_id", ""))): row
            for row in payload.get("mods", ())
        }

    old, new = keyed(previous), keyed(candidate)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = []
    for key in sorted(set(old) & set(new)):
        fields = [
            field for field in INDEX_FIELDS
            if json.dumps(old[key].get(field), sort_keys=True)
            != json.dumps(new[key].get(field), sort_keys=True)
        ]
        if fields:
            changed.append({"kind": key[0], "stat_id": key[1], "fields": fields})
    return {
        "previous_count": len(old),
        "candidate_count": len(new),
        "added": [{"kind": kind, "stat_id": stat_id} for kind, stat_id in added],
        "removed": [{"kind": kind, "stat_id": stat_id} for kind, stat_id in removed],
        "changed": changed,
    }


def unresolved_trade_entries(payload: dict, jp_trade: dict) -> list[dict]:
    """公式日本語statのうち、派生インデックスへ結合できなかった対象を列挙する。"""
    resolved = {
        (str(row.get("kind", "")), str(row.get("stat_id", "")))
        for row in payload.get("mods", ())
    }
    rows = []
    for (kind, stat_id), entry in sorted(_trade_entries(jp_trade).items()):
        if kind not in SUPPORTED_KINDS or (kind, stat_id) in resolved:
            continue
        rows.append({"kind": kind, "stat_id": stat_id, "japanese": str(entry.get("text", ""))})
    return rows


def excessive_removal(diff: dict) -> tuple[bool, int]:
    """小規模インデックスは100件、大規模は10%を超える削除を危険とする。"""
    limit = max(100, int(int(diff.get("previous_count", 0)) * 0.10))
    return len(diff.get("removed", ())) > limit, limit
