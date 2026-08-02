from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Iterable

from .metadata import normalize_stat_text


SUPPORTED_KINDS = {"explicit", "implicit", "crafted", "fractured", "enchant", "veiled"}
INDEX_FIELDS = (
    "ref", "stat_id", "kind", "japanese", "better", "inverted", "negated", "exact",
    "local", "decimal", "tiers", "options",
)

# Awakenedの配布statsから消えていても、公式Trade APIでは現在も有効なoption型stat。
# 公式側は ``stat_id|option`` の個別entryだけを返すため、ぽえとれ用には従来どおり
# ``stat_id`` + ``value.option`` へ復元する。
OFFICIAL_OPTION_COMPATIBILITY = {
    ("enchant", "enchant.stat_3948993189"): {
        "ref": "Added Small Passive Skills grant: #",
        "japanese": "追加される通常パッシブスキルは付与: #",
    },
}


def _awakened_stats(lines: Iterable[str]) -> list[dict]:
    rows = []
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        nested = row.get("stats")
        if nested is None:
            rows.append(row)
            continue
        resolve = row.get("resolve") or {}
        tests = resolve.get("test", ()) if resolve.get("strat") == "select" else ()
        for index, stat in enumerate(nested):
            stat = dict(stat)
            if index < len(tests):
                # nullはAwakenedのfallback候補、文字列はそのカテゴリ専用候補。
                stat["category_select"] = tests[index]
            rows.append(stat)
    return rows


def _trade_entries(payload: dict) -> dict[tuple[str, str], dict]:
    return {
        (str(entry.get("type", "")), str(entry.get("id", ""))): entry
        for group in payload.get("result", ()) for entry in group.get("entries", ())
    }


def _official_option_compatibility_records(
    trade_entries: dict[tuple[str, str], dict],
) -> list[dict]:
    """公式APIの合成IDを、検索送信用のbase stat＋optionへ戻す。"""
    records = []
    for (kind, stat_id), definition in OFFICIAL_OPTION_COMPATIBILITY.items():
        prefix = f"{stat_id}|"
        options = []
        for (entry_kind, entry_id), entry in trade_entries.items():
            if entry_kind != kind or not entry_id.startswith(prefix):
                continue
            option_id = entry_id[len(prefix):]
            if not option_id:
                continue
            try:
                value: int | str = int(option_id)
            except ValueError:
                value = option_id
            options.append({
                "value": value,
                "japanese": str(entry.get("text", "")),
                "english": "",
                "oils": [],
            })
        if not options:
            continue
        options.sort(key=lambda row: (isinstance(row["value"], str), row["value"]))
        records.append({
            "ref": definition["ref"],
            "stat_id": stat_id,
            "kind": kind,
            "japanese": [definition["japanese"]],
            "better": 0,
            "inverted": False,
            "negated": False,
            "exact": True,
            "local": False,
            "decimal": False,
            "tiers": [],
            "options": options,
        })
    return records


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


def _unique_icons(items_lines: Iterable[str]) -> dict[str, str]:
    """AwakenedのUnique名とPoE公式CDNアイコンURLだけを抽出する。"""
    result = {}
    for line in items_lines:
        if not line.strip():
            continue
        row = json.loads(line)
        name = str(row.get("refName", "")).strip()
        icon = str(row.get("icon", "")).strip()
        if row.get("namespace") == "UNIQUE" and name and icon:
            result[name.casefold()] = icon
    return dict(sorted(result.items()))


UBER_BOSS_DROP_SUPPLEMENTS = {
    # Awakenedのitem-drop.jsonはUber固有枠を中心に収録しており、
    # 通常版とUber版に共通する取引可能ドロップが各入場券から欠けている。
    "ITEM::Awakening Fragment": (
        "UNIQUE::Thread of Hope // Crimson Jewel",
        "UNIQUE::Zana's Ingenuity // Prismatic Ring",
        "GEM::Annihilation Support",
        "ITEM::Orb of Dominance",
        "ITEM::Awakener's Orb",
        "DIVINATION_CARD::A Fate Worse Than Death",
    ),
    "ITEM::Reality Fragment": (
        "GEM::Awakened Empower Support",
        "GEM::Awakened Enhance Support",
        "GEM::Awakened Enlighten Support",
        "GEM::Eclipse Support",
        "GEM::Invert the Rules Support",
        "ITEM::Orb of Conflict",
        "DIVINATION_CARD::Auspicious Ambitions",
    ),
    "ITEM::Devouring Fragment": (
        "UNIQUE::Forbidden Flesh // Cobalt Jewel",
        "GEM::Gluttony Support",
        "ITEM::Exceptional Eldritch Ichor",
        "ITEM::Eldritch Orb of Annulment",
        "ITEM::Eldritch Chaos Orb",
        "ITEM::Eldritch Exalted Orb",
        "DIVINATION_CARD::Auspicious Ambitions",
    ),
    "ITEM::Blazing Fragment": (
        "UNIQUE::Forbidden Flame // Crimson Jewel",
        "GEM::Overheat Support",
        "ITEM::Exceptional Eldritch Ember",
        "ITEM::Eldritch Orb of Annulment",
        "ITEM::Eldritch Chaos Orb",
        "ITEM::Eldritch Exalted Orb",
        "DIVINATION_CARD::Auspicious Ambitions",
    ),
    "ITEM::Cosmic Fragment": (
        "UNIQUE::The Unblinking Eye // Harlequin Mask",
        "ITEM::Fragment of Knowledge",
        "ITEM::Fragment of Shape",
        "GEM::Voidstorm Support",
        "ITEM::Shaper's Exalted Orb",
        "ITEM::Orb of Dominance",
    ),
    "ITEM::Decaying Fragment": (
        "UNIQUE::Impresence // Onyx Amulet",
        "GEM::Void Shockwave Support",
        "GEM::Cooldown Recovery Support",
        "UNIQUE::Watcher's Eye // Prismatic Jewel",
        "ITEM::Shaper's Exalted Orb",
        "ITEM::Elder's Exalted Orb",
        "ITEM::Orb of Dominance",
        "DIVINATION_CARD::Void of the Elements",
        "DIVINATION_CARD::Auspicious Ambitions",
    ),
    "ITEM::Synthesising Fragment": (
        "GEM::Greater Kinetic Instability Support",
        "DIVINATION_CARD::The Hook",
        "DIVINATION_CARD::Imperfect Memories",
    ),
}

# Awakenedのitem-drop.jsonには、素材・報酬・派生関係ではなく、単に用途が
# 近い装備を横並びにする比較用グループも含まれる。ぽえとれでは価格一覧の
# 意味を明確にするため、比較用途のグループと、個体ごとの価値判断に
# 関連ドロップ価格が役立たないナイトメアマップを表示対象外にする。
EXCLUDED_RELATED_ITEM_QUERY_GROUPS = {
    frozenset({"ITEM::Nightmare Map // T0, Atlas"}),
    frozenset({
        "UNIQUE::Ventor's Gamble // Gold Ring",
        "UNIQUE::Sadima's Touch // Wool Gloves",
        "UNIQUE::Bisco's Leash // Heavy Belt",
        "UNIQUE::Goldwyrm // Nubuck Boots",
        "UNIQUE::Divination Distillate",
        "UNIQUE::The Ascetic // Gold Amulet",
        "UNIQUE::Greed's Embrace // Golden Plate",
        "UNIQUE::Sentari's Answer // Brass Spirit Shield",
    }),
    frozenset({
        "GEM::Cast on Death Support",
        "UNIQUE::Goldrim // Leather Cap",
        "UNIQUE::Tabula Rasa // Simple Robe, 6L",
        "UNIQUE::Lochtonial Caress // Iron Gauntlets",
        "UNIQUE::Wanderlust // Wool Shoes",
        "UNIQUE::Lifesprig // Driftwood Wand",
        "UNIQUE::Karui Ward // Jade Amulet",
    }),
    frozenset({
        "UNIQUE::Farrul's Bite // Harlequin Mask",
        "UNIQUE::Farrul's Pounce // Hydrascale Gauntlets",
        "UNIQUE::Farrul's Fur // Triumphant Lamellar",
        "UNIQUE::Farrul's Chase // Slink Boots",
    }),
    frozenset({
        "UNIQUE::Craiceann's Chitin // Magistrate Crown",
        "UNIQUE::Craiceann's Carapace // Golden Plate",
        "UNIQUE::Craiceann's Pincers // Titan Gauntlets",
        "UNIQUE::Craiceann's Tracks // Goliath Greaves",
    }),
    frozenset({
        "UNIQUE::Fenumus' Toxins // Necromancer Circlet",
        "UNIQUE::Fenumus' Shroud // Widowsilk Robe",
        "UNIQUE::Fenumus' Weave // Carnal Mitts",
        "UNIQUE::Fenumus' Spinnerets // Assassin's Boots",
    }),
    frozenset({
        "UNIQUE::Saqawal's Flock // Silken Hood",
        "UNIQUE::Saqawal's Nest // Blood Raiment",
        "UNIQUE::Saqawal's Winds // Soldier Gloves",
        "UNIQUE::Saqawal's Talons // Hydrascale Boots",
    }),
}


def build_related_item_groups(items_lines: Iterable[str], drop_rows: Iterable[dict]) -> list[dict]:
    """Awakenedの関連品定義を、表示に必要な名前・variant・iconへ展開する。"""
    items = {}
    for line in items_lines:
        if not line.strip():
            continue
        row = json.loads(line)
        namespace = str(row.get("namespace", "")).strip()
        name = str(row.get("refName", "")).strip()
        if not namespace or not name:
            continue
        variant = ""
        if namespace == "UNIQUE":
            variant = str((row.get("unique") or {}).get("base", "")).strip()
        items.setdefault((namespace, name, variant), row)

    def resolve(query_id: str) -> dict:
        namespace, encoded = query_id.split("::", 1)
        name, separator, variant = encoded.partition(" // ")
        row = items.get((namespace, name, variant if separator else ""))
        if row is None and namespace == "UNIQUE":
            candidates = [
                value for (ns, item_name, _variant), value in items.items()
                if ns == namespace and item_name == name
            ]
            row = candidates[0] if len(candidates) == 1 else None
        return {
            "id": query_id,
            "namespace": namespace,
            "name": name,
            "variant": variant if separator else None,
            "icon": str((row or {}).get("icon", "")),
        }

    groups = []
    for row in drop_rows:
        query_ids = [str(value) for value in row.get("query", ())]
        if frozenset(query_ids) in EXCLUDED_RELATED_ITEM_QUERY_GROUPS:
            continue
        related_ids = [str(value) for value in row.get("items", ())]
        for query_id in query_ids:
            related_ids.extend(UBER_BOSS_DROP_SUPPLEMENTS.get(query_id, ()))
        related_ids = list(dict.fromkeys(related_ids))
        queries = [resolve(value) for value in query_ids]
        related = [resolve(value) for value in related_ids]
        if queries:
            groups.append({"query": queries, "items": related})
    return groups


def build_minimal_index(awakened_lines: Iterable[str], jp_trade: dict,
                        repoe_stats: dict | None = None,
                        repoe_mods: dict | None = None,
                        awakened_items: Iterable[str] = (),
                        awakened_item_drops: Iterable[dict] = (),
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
                record = {
                    "ref": str(stat.get("ref", "")),
                    "stat_id": stat_id,
                    "kind": kind,
                    "japanese": [str(entry.get("text", ""))],
                    "better": int(stat.get("better", 1)),
                    "inverted": bool(trade.get("inverted", False)),
                    # Awakenedは表示文ごとのmatcher.negateで内部値の符号を
                    # 正規化した後、trade.invertedでAPI値へ変換する。公式Tradeの
                    # 日本語文はrefに対応するため、refと同じmatcherの属性を保持する。
                    "negated": bool(next((
                        matcher.get("negate", False)
                        for matcher in stat.get("matchers", ())
                        if matcher.get("string") == stat.get("ref")
                    ), False)),
                    "exact": int(stat.get("better", 1)) == 0 or bool(trade.get("option", False)),
                    "local": bool(repoe_row.get("local", False)),
                    # Awakenedのdpフラグがあるstatだけ小数精度を維持する。
                    "decimal": bool(stat.get("dp", False)),
                    "tiers": repoe_row.get("tiers", ()),
                    "options": options,
                }
                if "category_select" in stat:
                    record["category_select"] = stat["category_select"]
                records.append(record)
    for record in _official_option_compatibility_records(jp):
        key = (record["kind"], record["stat_id"])
        if key not in seen:
            records.append(record)
            seen.add(key)
    records.sort(key=lambda row: (row["kind"], row["stat_id"]))
    awakened_items = tuple(awakened_items)
    return {
        "schema_version": 3,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "sources": sources or {},
        "scope": "PoE1 trade stat matching for equipment and gems",
        "base_armour": _base_armour(awakened_items),
        "gems": _gems(awakened_items),
        "unique_fixed_stats": _unique_fixed_stats(awakened_items),
        "unique_icons": _unique_icons(awakened_items),
        "related_item_groups": build_related_item_groups(
            awakened_items, awakened_item_drops,
        ),
        "mods": records,
    }


def build_official_index(jp_trade: dict, stat_rules: dict,
                         repoe_stats: dict | None = None,
                         repoe_mods: dict | None = None,
                         awakened_items: Iterable[str] = (),
                         awakened_item_drops: Iterable[dict] = (),
                         sources: dict | None = None,
                         generated_at: str | None = None) -> dict:
    """公式Tradeを骨格、RePoEと独自台帳を補足情報として派生indexを作る。

    ``stat_rules`` は一度監査した意味判断だけを保持するPoENavi正本であり、
    Awakenedの稼働や取得可否に依存しない。公式APIに存在しない古いruleは出力せず、
    未登録の公式statは ``unresolved_trade_entries`` で明示する。
    """
    jp = _trade_entries(jp_trade)
    repoe = _repoe_by_ref(repoe_stats or {}, repoe_mods or {})
    records = []
    seen = set()
    for rule in stat_rules.get("rules", ()):
        kind = str(rule.get("kind", ""))
        stat_id = str(rule.get("stat_id", ""))
        entry = jp.get((kind, stat_id))
        if kind not in SUPPORTED_KINDS or not entry or (kind, stat_id) in seen:
            continue
        seen.add((kind, stat_id))
        ref = str(rule.get("ref", ""))
        repoe_row = repoe.get(normalize_stat_text(ref), {})
        record = {
            "ref": ref,
            "stat_id": stat_id,
            "kind": kind,
            "japanese": [str(entry.get("text", ""))],
            "better": int(rule.get("better", 1)),
            "inverted": bool(rule.get("inverted", False)),
            "negated": bool(rule.get("negated", False)),
            "exact": bool(rule.get("exact", False)),
            "local": bool(repoe_row.get("local", False)),
            "decimal": bool(rule.get("decimal", False)),
            "tiers": repoe_row.get("tiers", ()),
            "options": list(rule.get("options", ())),
        }
        if "category_select" in rule:
            record["category_select"] = rule["category_select"]
        records.append(record)
    for record in _official_option_compatibility_records(jp):
        key = (record["kind"], record["stat_id"])
        if key not in seen:
            records.append(record)
            seen.add(key)
    records.sort(key=lambda row: (row["kind"], row["stat_id"]))
    awakened_items = tuple(awakened_items)
    return {
        "schema_version": 3,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "sources": sources or {},
        "scope": "PoE1 trade stat matching for equipment and gems",
        "base_armour": _base_armour(awakened_items),
        "gems": _gems(awakened_items),
        "unique_fixed_stats": _unique_fixed_stats(awakened_items),
        "unique_icons": _unique_icons(awakened_items),
        "related_item_groups": build_related_item_groups(
            awakened_items, awakened_item_drops,
        ),
        "mods": records,
    }


def audit_awakened_stat_rules(awakened_lines: Iterable[str], stat_rules: dict) -> dict:
    """Awakenedを入力正本にせず、独自台帳との差分だけを報告する。"""
    upstream = {}
    for stat in _awakened_stats(awakened_lines):
        trade = stat.get("trade") or {}
        for kind, ids in (trade.get("ids") or {}).items():
            for stat_id in ids:
                upstream[(kind, stat_id)] = {
                    "ref": str(stat.get("ref", "")),
                    "better": int(stat.get("better", 1)),
                    "inverted": bool(trade.get("inverted", False)),
                    "negated": bool(next((
                        matcher.get("negate", False)
                        for matcher in stat.get("matchers", ())
                        if matcher.get("string") == stat.get("ref")
                    ), False)),
                    "exact": int(stat.get("better", 1)) == 0 or bool(trade.get("option", False)),
                    "decimal": bool(stat.get("dp", False)),
                }
    local = {
        (str(row.get("kind", "")), str(row.get("stat_id", ""))): row
        for row in stat_rules.get("rules", ())
    }
    common = set(upstream) & set(local)
    fields = ("ref", "better", "inverted", "negated", "exact", "decimal")
    changed = [
        {"kind": key[0], "stat_id": key[1], "fields": [
            field for field in fields if upstream[key].get(field) != local[key].get(field)
        ]}
        for key in sorted(common)
        if any(upstream[key].get(field) != local[key].get(field) for field in fields)
    ]
    return {
        "only_in_awakened": [
            {"kind": kind, "stat_id": stat_id} for kind, stat_id in sorted(set(upstream) - set(local))
        ],
        "only_in_poetore": [
            {"kind": kind, "stat_id": stat_id} for kind, stat_id in sorted(set(local) - set(upstream))
        ],
        "changed": changed,
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
    for unique_name, icon_url in payload.get("unique_icons", {}).items():
        if (not unique_name or not isinstance(icon_url, str)
                or not icon_url.startswith("https://web.poecdn.com/")):
            errors.append(f"invalid unique icon: {unique_name}")
    keys: set[tuple[str, str]] = set()
    matchers: dict[tuple[str, str], list[str]] = {}
    for index, row in enumerate(mods):
        missing = [field for field in INDEX_FIELDS if field not in row]
        if missing:
            errors.append(f"mods[{index}] missing fields: {', '.join(missing)}")
            continue
        key = (str(row["kind"]), str(row["stat_id"]))
        if not isinstance(row.get("negated"), bool):
            errors.append(f"invalid negated flag: {key[0]}:{key[1]}")
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
