from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Iterable

from .metadata import normalize_stat_text


SUPPORTED_KINDS = {"explicit", "implicit", "crafted", "fractured", "enchant"}
INDEX_FIELDS = ("ref", "stat_id", "kind", "japanese", "better", "inverted", "exact", "local", "tiers")


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


def build_minimal_index(awakened_lines: Iterable[str], jp_trade: dict,
                        repoe_stats: dict | None = None,
                        repoe_mods: dict | None = None,
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
                records.append({
                    "ref": str(stat.get("ref", "")),
                    "stat_id": stat_id,
                    "kind": kind,
                    "japanese": [str(entry.get("text", ""))],
                    "better": int(stat.get("better", 1)),
                    "inverted": bool(trade.get("inverted", False)),
                    "exact": int(stat.get("better", 1)) == 0 or bool(trade.get("option", False)),
                    "local": bool(repoe_row.get("local", False)),
                    "tiers": repoe_row.get("tiers", ()),
                })
    records.sort(key=lambda row: (row["kind"], row["stat_id"]))
    return {
        "schema_version": 1,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "sources": sources or {},
        "scope": "PoE1 trade stat matching for weapons, armour and accessories",
        "mods": records,
    }


def validate_minimal_index(payload: dict) -> dict:
    """更新前に、壊れた・曖昧な派生インデックスを検出する。"""
    mods = payload.get("mods", ())
    errors: list[str] = []
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
