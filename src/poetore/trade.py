from __future__ import annotations

from dataclasses import dataclass, replace
import json
import re
from statistics import median
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import ParsedItem
from .metadata import default_metadata_index, normalize_stat_text


API_ROOT = "https://www.pathofexile.com/api/trade"
JP_API_ROOT = "https://jp.pathofexile.com/api/trade"
USER_AGENT = "PoENavi/poetore-local-spike (github.com/buri34/poenavi)"
DEFAULT_SEARCH_RANGE = 0.10
TRADE_STATUS_OPTIONS = {
    "instant": "securable",
    "available": "available",
    "online": "online",
}
TRADE_CURRENCY_OPTIONS = {
    "any": None,
    "chaos": "chaos",
    "divine": "divine",
    "chaos_divine": "chaos_divine",
}
CONSUMABLE_CRAFTABLE_CATEGORIES = {
    "map", "heist_blueprint", "heist_contract", "invitation",
    "memory_line", "expedition_logbook",
}
NON_CRAFTABLE_CATEGORIES = {"gem", "flask", "currency", "divination_card"}
PRESET_FINISHED = "finished"
PRESET_BASE = "base"
TRADE_PRESETS = (PRESET_FINISHED, PRESET_BASE)
_INFLUENCE_STATS = {
    "shaper": ("pseudo.pseudo_has_shaper_influence", "Shaper影響"),
    "elder": ("pseudo.pseudo_has_elder_influence", "Elder影響"),
    "crusader": ("pseudo.pseudo_has_crusader_influence", "Crusader影響"),
    "hunter": ("pseudo.pseudo_has_hunter_influence", "Hunter影響"),
    "redeemer": ("pseudo.pseudo_has_redeemer_influence", "Redeemer影響"),
    "warlord": ("pseudo.pseudo_has_warlord_influence", "Warlord影響"),
}


def _trade_log(message: str) -> None:
    print(f"[POETORE TRADE] {message}", flush=True)


def _trade_log_payload(payload: dict) -> None:
    formatted = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    _trade_log(f"request payload:\n{formatted}")

_PROPERTY_FILTERS = {
    "property.total_dps": ("weapon_filters", "dps"),
    "property.elemental_dps": ("weapon_filters", "edps"),
    "property.physical_dps": ("weapon_filters", "pdps"),
    "property.aps": ("weapon_filters", "aps"),
    "property.crit": ("weapon_filters", "crit"),
    "property.armour": ("armour_filters", "ar"),
    "property.evasion": ("armour_filters", "ev"),
    "property.energy_shield": ("armour_filters", "es"),
    "property.ward": ("armour_filters", "ward"),
    "property.item_level": ("misc_filters", "ilvl"),
    "property.quality": ("misc_filters", "quality"),
    "property.sockets": ("socket_filters", "sockets"),
    "property.links": ("socket_filters", "links"),
}

_WEAPON_PHYSICAL_STAT_KEYS = {"1509134228", "1940865751"}
_WEAPON_ELEMENTAL_STAT_KEYS = {"3336890334", "1037193709", "709508406"}
_WEAPON_SPEED_STAT_KEYS = {"210067635"}
_WEAPON_CRIT_STAT_KEYS = {"2375316951"}
_ARMOUR_STAT_KEYS = {
    "4052037485", "124859000", "4015621042", "53045048", "1062208444",
    "3484657501", "3321629045", "2451402625", "1999113824", "3523867985",
}

_RESISTANCE_REFS = {
    "+#% to All Resistances": (("fire", "cold", "lightning"), True),
    "+#% to all Elemental Resistances": (("fire", "cold", "lightning"), False),
    "+#% to Fire Resistance": (("fire",), False),
    "+#% to Cold Resistance": (("cold",), False),
    "+#% to Lightning Resistance": (("lightning",), False),
    "+#% to Fire and Lightning Resistances": (("fire", "lightning"), False),
    "+#% to Fire and Cold Resistances": (("fire", "cold"), False),
    "+#% to Cold and Lightning Resistances": (("cold", "lightning"), False),
    "+#% to Chaos Resistance": ((), True),
    "+#% to Fire and Chaos Resistances": (("fire",), True),
    "+#% to Cold and Chaos Resistances": (("cold",), True),
    "+#% to Lightning and Chaos Resistances": (("lightning",), True),
}
_ATTRIBUTE_REFS = {
    "+# to all Attributes": ("str", "dex", "int"),
    "+# to Strength": ("str",), "+# to Dexterity": ("dex",),
    "+# to Intelligence": ("int",),
    "+# to Strength and Intelligence": ("str", "int"),
    "+# to Strength and Dexterity": ("str", "dex"),
    "+# to Dexterity and Intelligence": ("dex", "int"),
}
_SIMPLE_PSEUDOS = (
    ("#% increased maximum Energy Shield", "pseudo.pseudo_increased_energy_shield", "最大ES増加率合計"),
    ("+# to maximum Energy Shield", "pseudo.pseudo_total_energy_shield", "最大ES合計"),
    ("#% increased Attack Speed", "pseudo.pseudo_total_attack_speed", "アタックスピード合計"),
    ("#% increased Cast Speed", "pseudo.pseudo_total_cast_speed", "キャストスピード合計"),
    ("#% increased Movement Speed", "pseudo.pseudo_increased_movement_speed", "移動スピード"),
    ("#% increased Global Physical Damage", "pseudo.pseudo_increased_physical_damage", "物理ダメージ増加合計"),
    ("#% increased Global Critical Strike Chance", "pseudo.pseudo_global_critical_strike_chance", "グローバルクリティカル率"),
    ("+#% to Global Critical Strike Multiplier", "pseudo.pseudo_global_critical_strike_multiplier", "グローバルクリティカル倍率"),
    ("#% increased Elemental Damage", "pseudo.pseudo_increased_elemental_damage", "元素ダメージ増加"),
    ("#% increased Lightning Damage", "pseudo.pseudo_increased_lightning_damage", "雷ダメージ増加"),
    ("#% increased Cold Damage", "pseudo.pseudo_increased_cold_damage", "冷気ダメージ増加"),
    ("#% increased Fire Damage", "pseudo.pseudo_increased_fire_damage", "火ダメージ増加"),
    ("#% increased Spell Damage", "pseudo.pseudo_increased_spell_damage", "スペルダメージ増加"),
    ("#% increased Lightning Spell Damage", "pseudo.pseudo_increased_lightning_spell_damage", "雷スペルダメージ増加"),
    ("#% increased Cold Spell Damage", "pseudo.pseudo_increased_cold_spell_damage", "冷気スペルダメージ増加"),
    ("#% increased Fire Spell Damage", "pseudo.pseudo_increased_fire_spell_damage", "火スペルダメージ増加"),
    ("Regenerate # Life per second", "pseudo.pseudo_total_life_regen", "毎秒ライフ自動回復"),
    ("Regenerate #% of Life per second", "pseudo.pseudo_percent_life_regen", "毎秒ライフ自動回復率"),
    ("#% of Physical Attack Damage Leeched as Life", "pseudo.pseudo_physical_attack_damage_leeched_as_life", "物理アタックのライフリーチ"),
    ("#% of Physical Attack Damage Leeched as Mana", "pseudo.pseudo_physical_attack_damage_leeched_as_mana", "物理アタックのマナリーチ"),
    ("#% increased Mana Regeneration Rate", "pseudo.pseudo_increased_mana_regen", "マナ自動回復レート"),
)


class TradeApiError(RuntimeError):
    pass


def default_trade_currency(item: ParsedItem) -> str:
    """Awakened PoE Trade相当の、アイテム種別別の初期通貨条件。"""
    if _is_unique(item):
        return "any"
    if item.category in CONSUMABLE_CRAFTABLE_CATEGORIES | NON_CRAFTABLE_CATEGORIES:
        return "chaos_divine"
    return "any"


@dataclass(frozen=True)
class PriceListing:
    amount: float
    currency: str
    account: str = ""
    item_name: str = ""
    base_type: str = ""


@dataclass(frozen=True)
class TradeStatFilter:
    stat_id: str
    text: str
    min_value: float | None
    kind: str
    enabled: bool = False
    max_value: float | None = None
    ref: str | None = None
    confidence: float = 0.0
    inverted: bool = False
    read_value: float | None = None
    tier: int | None = None
    roll_min: float | None = None
    roll_max: float | None = None
    affix: str | None = None
    generation: str | None = None
    selection_reason: str = ""
    exact: bool = False
    better: int | None = None


@dataclass(frozen=True)
class PriceResult:
    league: str
    query_id: str
    total: int
    listings: tuple[PriceListing, ...]
    rate_limit: str = ""

    def median_by_currency(self) -> dict[str, float]:
        grouped: dict[str, list[float]] = {}
        for listing in self.listings:
            grouped.setdefault(listing.currency, []).append(listing.amount)
        return {currency: median(values) for currency, values in grouped.items()}


def _request_json(url: str, payload: dict | None = None) -> tuple[dict, object]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8")), response.headers
    except Exception as exc:
        _trade_log(f"request failed: {request.get_method()} {url} error={exc!r}")
        raise TradeApiError(f"PoE Trade APIへの接続に失敗しました: {exc}") from exc


def active_pc_league() -> str:
    url = f"{API_ROOT}/data/leagues"
    _trade_log(f"request: GET {url}")
    data, _ = _request_json(url)
    leagues = [row for row in data.get("result", ()) if row.get("realm") == "pc"]
    for row in leagues:
        name = str(row.get("id", ""))
        lowered = name.lower()
        if name and all(word not in lowered for word in ("hardcore", "ruthless", "standard")):
            _trade_log(f"active PC league: {name}")
            return name
    _trade_log("active PC league: Standard (fallback)")
    return "Standard"


def physical_dps(item: ParsedItem) -> float | None:
    damage = item.properties.get("物理ダメージ") or item.properties.get("Physical Damage")
    speed = item.properties.get("秒間アタック回数") or item.properties.get("Attacks per Second")
    if not damage or not speed:
        return None
    damage_values = re.findall(r"\d+(?:\.\d+)?", damage)
    speed_values = re.findall(r"\d+(?:\.\d+)?", speed)
    if len(damage_values) < 2 or not speed_values:
        return None
    return ((float(damage_values[0]) + float(damage_values[1])) / 2) * float(speed_values[0])


def elemental_dps(item: ParsedItem) -> float | None:
    damage = item.properties.get("元素ダメージ") or item.properties.get("Elemental Damage")
    speed = item.properties.get("秒間アタック回数") or item.properties.get("Attacks per Second")
    if not damage or not speed:
        return None
    damage_values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", damage)]
    speed_values = re.findall(r"\d+(?:\.\d+)?", speed)
    if len(damage_values) < 2 or not speed_values:
        return None
    average_damage = sum(
        (damage_values[index] + damage_values[index + 1]) / 2
        for index in range(0, len(damage_values) - 1, 2)
    )
    return average_damage * float(speed_values[0])


def _quality_at_least_20(value: float, item: ParsedItem) -> float:
    """表示プロパティをAwakened同様、最低品質20%時の値へ換算する。"""
    quality = _property_value(item, "品質", "Quality") or 0.0
    target_quality = max(20.0, quality)
    return value * (1 + target_quality / 100) / (1 + quality / 100)


def physical_dps_at_20_quality(item: ParsedItem) -> float | None:
    value = physical_dps(item)
    return _quality_at_least_20(value, item) if value is not None else None


def _relaxed(value: float) -> float:
    return round(value * (1 - DEFAULT_SEARCH_RANGE), 1)


def _physical_dps_is_important(item: ParsedItem) -> bool:
    important = (
        "axe", "斧", "sword", "剣", "bow", "弓", "warstaff", "ウォースタッフ",
    )
    lowered = item.item_class.lower()
    return any(word in lowered for word in important)


def _property_value(item: ParsedItem, *labels: str) -> float | None:
    for label in labels:
        value = item.properties.get(label)
        if value:
            match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
            if match:
                return float(match.group())
    return None


def available_trade_presets(item: ParsedItem) -> tuple[str, ...]:
    """完成品を基本とし、未完成でクラフト価値がある装備だけベース検索を追加する。"""
    if item.category not in {"weapon", "armour", "accessory"} or _is_unique(item):
        return (PRESET_FINISHED,)
    quality = _property_value(item, "品質", "Quality")
    likely_finished = (
        any(modifier.kind == "crafted" for modifier in item.modifiers)
        or quality == 20
        or "corrupted" in item.flags
        or "mirrored" in item.flags
    )
    has_crafting_value = (
        any(modifier.kind == "fractured" for modifier in item.modifiers)
        or "synthesised" in item.flags
        or any(flag.startswith("influence:") for flag in item.flags)
        or bool(item.item_level is not None and item.item_level >= 82)
    )
    if likely_finished or not has_crafting_value:
        return (PRESET_FINISHED,)
    return (PRESET_FINISHED, PRESET_BASE)


def _base_item_filters(item: ParsedItem) -> tuple[TradeStatFilter, ...]:
    filters: list[TradeStatFilter] = []
    if item.item_level is not None:
        filters.append(TradeStatFilter(
            "property.item_level", "アイテムレベル",
            float(min(item.item_level, 86)), "base", True,
        ))
    for flag in item.flags:
        if not flag.startswith("influence:"):
            continue
        influence = flag.split(":", 1)[1]
        stat = _INFLUENCE_STATS.get(influence)
        if stat:
            filters.append(TradeStatFilter(stat[0], stat[1], None, "influence", True))
    exact_modifiers = [
        modifier for modifier in item.modifiers
        if modifier.kind == "fractured"
        or (modifier.kind in {"prefix", "suffix"} and modifier.tier in {1, 2})
    ]
    entries = _trade_stat_entries() if exact_modifiers else ()
    for modifier in exact_modifiers:
        api_kind = "fractured" if modifier.kind == "fractured" else "explicit"
        source = _normalized_stat_text(modifier.text)
        candidates = [
            entry for entry in entries
            if entry.get("type") == api_kind
            and _normalized_stat_text(str(entry.get("text", ""))) == source
        ]
        if not candidates:
            continue
        if item.category == "weapon" and len(candidates) > 1:
            local = [entry for entry in candidates if "(ローカル)" in str(entry.get("text", ""))]
            if local:
                candidates = local
        entry = candidates[0]
        value = _value_for_template(modifier.text, str(entry.get("text", "")))
        if value is None:
            value = modifier.values[0] if modifier.values else None
        filters.append(TradeStatFilter(
            str(entry["id"]), modifier.text, value,
            "fractured" if modifier.kind == "fractured" else f"T{modifier.tier}", True,
        ))
    return tuple(filters) + _item_detail_filters(item) + _empty_affix_filters(item)


def _socket_summary(item: ParsedItem) -> tuple[int, int, int]:
    text = item.properties.get("ソケット") or item.properties.get("Sockets") or ""
    groups = re.findall(r"[RGBW](?:-[RGBW])*", text.upper())
    sizes = [len(group.split("-")) for group in groups]
    total = sum(sizes)
    linked = max(sizes, default=0)
    white = len(re.findall(r"W", text.upper()))
    return total, linked, white


def _item_detail_filters(item: ParsedItem) -> tuple[TradeStatFilter, ...]:
    filters: list[TradeStatFilter] = []
    quality = _property_value(item, "品質", "Quality")
    if quality is not None and quality >= 20:
        filters.append(TradeStatFilter(
            "property.quality", "品質", quality, "property", quality > 20,
        ))
    sockets, links, white = _socket_summary(item)
    if sockets:
        filters.append(TradeStatFilter(
            "property.sockets", "ソケット数", float(sockets), "socket", sockets >= 6,
        ))
    if links > 1:
        filters.append(TradeStatFilter(
            "property.links", "最大リンク数", float(links), "socket", True,
        ))
    if white:
        filters.append(TradeStatFilter(
            "property.white_sockets", "白ソケット数", float(white), "socket", True,
        ))
    return tuple(filters)


def _empty_affix_filters(item: ParsedItem) -> tuple[TradeStatFilter, ...]:
    if item.rarity.casefold() not in {"rare", "レア"}:
        return ()
    groups: dict[str, set[object]] = {"prefix": set(), "suffix": set()}
    for index, modifier in enumerate(item.modifiers):
        if modifier.affix not in groups:
            continue
        groups[modifier.affix].add(modifier.group if modifier.group is not None else ("line", index))
    if not groups["prefix"] and not groups["suffix"]:
        # 通常コピーなどでPrefix/Suffix情報がない場合は推測しない。
        return ()
    filters: list[TradeStatFilter] = []
    for affix, stat_id, label in (
        ("prefix", "pseudo.pseudo_number_of_empty_prefix_mods", "空きPrefix枠"),
        ("suffix", "pseudo.pseudo_number_of_empty_suffix_mods", "空きSuffix枠"),
    ):
        empty = max(0, 3 - len(groups[affix]))
        if empty:
            filters.append(TradeStatFilter(
                stat_id, f"{label}（現在{empty}枠）", 1.0, "craft", False,
            ))
    return tuple(filters)


def _initial_property_filters(item: ParsedItem) -> list[TradeStatFilter]:
    filters: list[TradeStatFilter] = []
    if item.category == "weapon":
        pdps = physical_dps_at_20_quality(item) or 0
        edps = elemental_dps(item) or 0
        total = pdps + edps
        if pdps and edps:
            filters.append(TradeStatFilter(
                "property.total_dps", "合計DPS", _relaxed(total), "property", True,
            ))
        if edps and (not total or edps / total >= 0.67):
            filters.append(TradeStatFilter(
                "property.elemental_dps", "元素DPS", _relaxed(edps), "property", True,
            ))
        if pdps and _physical_dps_is_important(item) and (not total or pdps / total >= 0.67):
            filters.append(TradeStatFilter(
                "property.physical_dps", "物理DPS", _relaxed(pdps), "property", True,
            ))
        aps = _property_value(item, "秒間アタック回数", "Attacks per Second")
        if aps is not None:
            filters.append(TradeStatFilter(
                "property.aps", "秒間アタック回数", _relaxed(aps), "property", False,
            ))
        crit = _property_value(item, "クリティカル率", "Critical Strike Chance")
        if crit is not None:
            filters.append(TradeStatFilter(
                "property.crit", "クリティカル率", _relaxed(crit), "property", False,
            ))
    elif item.category == "armour":
        defenses = [
            ("property.armour", "アーマー", _property_value(item, "アーマー", "防具", "Armour")),
            ("property.evasion", "回避力", _property_value(item, "回避力", "Evasion Rating")),
            ("property.energy_shield", "エナジーシールド", _property_value(item, "エナジーシールド", "Energy Shield")),
            ("property.ward", "Ward", _property_value(item, "Ward")),
        ]
        present = [
            (stat_id, text, _quality_at_least_20(value, item))
            for stat_id, text, value in defenses if value
        ]
        for stat_id, text, value in present:
            filters.append(TradeStatFilter(stat_id, text, _relaxed(value), "property", True))
    return filters


def _gear_pseudo_filters(item: ParsedItem) -> list[TradeStatFilter]:
    if item.category not in {"weapon", "armour", "accessory"}:
        return []
    totals = {"life": 0.0, "mana": 0.0, "fire": 0.0, "cold": 0.0,
              "lightning": 0.0, "chaos": 0.0, "str": 0.0, "dex": 0.0, "int": 0.0}
    simple: dict[tuple[str, str], float] = {}
    for modifier in item.modifiers:
        value = modifier.values[0] if modifier.values else 0
        ref = modifier.ref or ""
        if not ref:
            normalized = normalize_stat_text(modifier.text)
            known_refs = tuple(_RESISTANCE_REFS) + tuple(_ATTRIBUTE_REFS) + (
                "+# to maximum Life", "+# to maximum Mana",
            ) + tuple(row[0] for row in _SIMPLE_PSEUDOS)
            ref = next((candidate for candidate in known_refs
                        if normalize_stat_text(candidate) == normalized), "")
        if ref == "+# to maximum Life": totals["life"] += value
        if ref == "+# to maximum Mana": totals["mana"] += value
        for attr in _ATTRIBUTE_REFS.get(ref, ()):
            totals[attr] += value
        resistance = _RESISTANCE_REFS.get(ref)
        if resistance:
            elements, chaos = resistance
            for element in elements: totals[element] += value
            if chaos: totals["chaos"] += value
        for source_ref, stat_id, label in _SIMPLE_PSEUDOS:
            if ref == source_ref and not (
                source_ref == "#% increased Attack Speed" and
                modifier.stat_id and modifier.stat_id.rsplit("_", 1)[-1] in _WEAPON_SPEED_STAT_KEYS
            ):
                simple[(stat_id, label)] = simple.get((stat_id, label), 0.0) + value
    filters = []
    totals["life"] += totals["str"] * 0.5
    totals["mana"] += totals["int"] * 0.5
    elemental = totals["fire"] + totals["cold"] + totals["lightning"]
    if totals["life"]:
        filters.append(TradeStatFilter(
            "pseudo.pseudo_total_life", "最大ライフ合計", _relaxed(totals["life"]), "pseudo", True,
        ))
    if totals["mana"]:
        filters.append(TradeStatFilter("pseudo.pseudo_total_mana", "最大マナ合計", _relaxed(totals["mana"]), "pseudo"))
    if elemental:
        filters.append(TradeStatFilter(
            "pseudo.pseudo_total_elemental_resistance", "元素耐性合計", _relaxed(elemental), "pseudo", True,
        ))
    for element, stat_id, label in (("fire", "pseudo.pseudo_total_fire_resistance", "火耐性合計"),
                                    ("cold", "pseudo.pseudo_total_cold_resistance", "冷気耐性合計"),
                                    ("lightning", "pseudo.pseudo_total_lightning_resistance", "雷耐性合計")):
        if totals[element]: filters.append(TradeStatFilter(stat_id, label, _relaxed(totals[element]), "pseudo"))
    if totals["chaos"]:
        filters.append(TradeStatFilter(
            "pseudo.pseudo_total_chaos_resistance", "混沌耐性合計", _relaxed(totals["chaos"]), "pseudo", True,
        ))
    for attr, stat_id, label in (("str", "pseudo.pseudo_total_strength", "筋力合計"),
                                 ("dex", "pseudo.pseudo_total_dexterity", "器用さ合計"),
                                 ("int", "pseudo.pseudo_total_intelligence", "知性合計")):
        if totals[attr]: filters.append(TradeStatFilter(stat_id, label, _relaxed(totals[attr]), "pseudo"))
    if all(totals[attr] and totals[attr] == totals["str"] for attr in ("str", "dex", "int")):
        filters = [f for f in filters if f.stat_id not in {"pseudo.pseudo_total_strength", "pseudo.pseudo_total_dexterity", "pseudo.pseudo_total_intelligence"}]
        filters.append(TradeStatFilter("pseudo.pseudo_total_all_attributes", "全能力値合計", _relaxed(totals["str"]), "pseudo"))
    filters.extend(TradeStatFilter(stat_id, label, _relaxed(value), "pseudo") for (stat_id, label), value in simple.items())
    return filters


def _pseudo_consumed_stat_ids(item: ParsedItem) -> set[str]:
    """pseudoへ集約した元Modを個別条件として二重表示しない。"""
    known_refs = set(_RESISTANCE_REFS) | set(_ATTRIBUTE_REFS) | {
        "+# to maximum Life", "+# to maximum Mana",
    } | {row[0] for row in _SIMPLE_PSEUDOS}
    consumed = set()
    for modifier in item.modifiers:
        if not modifier.stat_id or modifier.ref not in known_refs:
            continue
        if (modifier.ref == "#% increased Attack Speed" and
                modifier.stat_id.rsplit("_", 1)[-1] in _WEAPON_SPEED_STAT_KEYS):
            continue
        consumed.add(modifier.stat_id)
    return consumed


_stat_entries_cache: tuple[dict, ...] | None = None
_item_entries_cache: tuple[dict, ...] | None = None


def _normalized_stat_text(text: str) -> str:
    text = re.sub(r"\([^)]*(?:\d|implicit|crafted|enchant)[^)]*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\d+(?:\.\d+)?", "#", text)
    return re.sub(r"\s+", " ", text).strip()


def _value_for_template(source: str, template: str) -> float | None:
    source = re.sub(r"\([^)]*(?:\d|implicit|crafted|enchant)[^)]*\)", "", source, flags=re.IGNORECASE).strip()
    template = template.replace(" (ローカル)", "").strip()
    pattern = re.escape(template).replace(r"\#", r"(-?\d+(?:\.\d+)?)")
    match = re.fullmatch(pattern, source)
    if not match or not match.groups():
        return None
    return float(match.group(1))


def _trade_stat_entries() -> tuple[dict, ...]:
    global _stat_entries_cache
    if _stat_entries_cache is None:
        data, _ = _request_json(f"{JP_API_ROOT}/data/stats")
        _stat_entries_cache = tuple(
            entry for group in data.get("result", ()) for entry in group.get("entries", ())
        )
    return _stat_entries_cache


def unique_candidates(base_type: str) -> tuple[str, ...]:
    """未鑑定ユニークの英語ベースから、公式データの同名検索候補を返す。"""
    global _item_entries_cache
    if _item_entries_cache is None:
        data, _ = _request_json(f"{API_ROOT}/data/items")
        _item_entries_cache = tuple(
            entry for group in data.get("result", ()) for entry in group.get("entries", ())
        )
    target = base_type.strip().casefold()
    names = {
        str(entry.get("name", "")).strip()
        for entry in _item_entries_cache
        if str(entry.get("type", "")).strip().casefold() == target
        and bool((entry.get("flags") or {}).get("unique"))
        and str(entry.get("name", "")).strip()
    }
    return tuple(sorted(names))


def unique_variants(name: str, base_type: str) -> tuple[tuple[str, str | None], ...]:
    """同名・同ベースの公式Trade discriminator候補を返す。"""
    global _item_entries_cache
    if _item_entries_cache is None:
        unique_candidates(base_type)
    target_name, target_base = name.strip().casefold(), base_type.strip().casefold()
    variants = {
        (str(entry.get("text") or entry.get("name") or name),
         str(entry["disc"]) if entry.get("disc") else None)
        for entry in (_item_entries_cache or ())
        if str(entry.get("name", "")).strip().casefold() == target_name
        and str(entry.get("type", "")).strip().casefold() == target_base
        and bool((entry.get("flags") or {}).get("unique"))
    }
    return tuple(sorted(variants, key=lambda row: (row[1] is not None, row[0])))


def _is_unique(item: ParsedItem) -> bool:
    return item.rarity.casefold() in {"unique", "ユニーク"}


def _aggregated_local_property_stat(item: ParsedItem, stat_id: str) -> bool:
    """完成品のプロパティ値へ既に集約済みのローカルstatか。"""
    key = stat_id.rsplit("_", 1)[-1]
    if item.category == "weapon":
        if key in _WEAPON_PHYSICAL_STAT_KEYS:
            return physical_dps(item) is not None
        if key in _WEAPON_ELEMENTAL_STAT_KEYS:
            return elemental_dps(item) is not None
        if key in _WEAPON_SPEED_STAT_KEYS:
            return _property_value(item, "秒間アタック回数", "Attacks per Second") is not None
        if key in _WEAPON_CRIT_STAT_KEYS:
            return _property_value(item, "クリティカル率", "Critical Strike Chance") is not None
    if item.category == "armour" and key in _ARMOUR_STAT_KEYS:
        return any(_property_value(item, label) is not None for label in (
            "アーマー", "防具", "Armour", "回避力", "Evasion Rating",
            "エナジーシールド", "Energy Shield", "Ward",
        ))
    return False


def _unique_roll_bounds(text: str) -> tuple[float, float] | None:
    """Ctrl+Alt+Cの `実数(下限-上限)` から可変範囲を取得する。"""
    matches = re.findall(r"\(\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*\)", text)
    if not matches:
        return None
    lows = [float(low) for low, _ in matches]
    highs = [float(high) for _, high in matches]
    return min(lows), max(highs)


def _unique_minimum(value: float | None, bounds: tuple[float, float]) -> float | None:
    if value is None:
        return None
    low, high = bounds
    # 実数値の一定割合ではなく、ユニーク固有の可変幅の10%だけ緩和。
    return round(value - abs(high - low) * DEFAULT_SEARCH_RANGE, 1)


def unresolved_modifier_warnings(item: ParsedItem) -> tuple[str, ...]:
    """新メタデータで未解決のMod。検索時は従来の公式API照合を試す。"""
    return tuple(
        modifier.text for modifier in item.modifiers
        if modifier.stat_id is None and modifier.kind not in {"desecrated"}
    )


def _decorate_filters(item: ParsedItem, filters: tuple[TradeStatFilter, ...],
                      unique_item: bool = False) -> tuple[TradeStatFilter, ...]:
    by_stat: dict[str, list] = {}
    for modifier in item.modifiers:
        if modifier.stat_id:
            by_stat.setdefault(modifier.stat_id, []).append(modifier)
    decorated = []
    property_reasons = {
        "property.total_dps": "物理・元素を含む主要な合計DPS",
        "property.elemental_dps": "元素ダメージ主体の武器性能",
        "property.physical_dps": "物理ダメージ主体の武器性能",
        "property.armour": "防具の主要アーマー値", "property.evasion": "防具の主要回避力",
        "property.energy_shield": "防具の主要エナジーシールド値", "property.ward": "防具の主要Ward値",
        "property.links": "リンク数は価格への影響が大きい", "property.white_sockets": "白ソケットを保持",
        "property.quality": "品質20%超を保持", "property.item_level": "クラフト価値のあるアイテムレベル",
    }
    sockets, links, white = _socket_summary(item)
    property_values = {
        "property.total_dps": (physical_dps_at_20_quality(item) or 0) + (elemental_dps(item) or 0),
        "property.elemental_dps": elemental_dps(item),
        "property.physical_dps": physical_dps_at_20_quality(item),
        "property.aps": _property_value(item, "秒間アタック回数", "Attacks per Second"),
        "property.crit": _property_value(item, "クリティカル率", "Critical Strike Chance"),
        "property.armour": _property_value(item, "アーマー", "防具", "Armour"),
        "property.evasion": _property_value(item, "回避力", "Evasion Rating"),
        "property.energy_shield": _property_value(item, "エナジーシールド", "Energy Shield"),
        "property.ward": _property_value(item, "Ward"),
        "property.item_level": float(item.item_level) if item.item_level is not None else None,
        "property.quality": _property_value(item, "品質", "Quality"),
        "property.sockets": float(sockets) if sockets else None,
        "property.links": float(links) if links else None,
        "property.white_sockets": float(white) if white else None,
    }
    simple_sources = {stat_id: source_ref for source_ref, stat_id, _ in _SIMPLE_PSEUDOS}
    pseudo_refs: dict[str, set[str]] = {
        "pseudo.pseudo_total_life": {"+# to maximum Life", *(
            ref for ref, attrs in _ATTRIBUTE_REFS.items() if "str" in attrs
        )},
        "pseudo.pseudo_total_mana": {"+# to maximum Mana", *(
            ref for ref, attrs in _ATTRIBUTE_REFS.items() if "int" in attrs
        )},
        "pseudo.pseudo_total_energy_shield": {"+# to maximum Energy Shield"},
        "pseudo.pseudo_total_elemental_resistance": {
            ref for ref, (elements, _) in _RESISTANCE_REFS.items() if elements
        },
        "pseudo.pseudo_total_chaos_resistance": {
            ref for ref, (_, chaos) in _RESISTANCE_REFS.items() if chaos
        },
        "pseudo.pseudo_total_fire_resistance": {
            ref for ref, (elements, _) in _RESISTANCE_REFS.items() if "fire" in elements
        },
        "pseudo.pseudo_total_cold_resistance": {
            ref for ref, (elements, _) in _RESISTANCE_REFS.items() if "cold" in elements
        },
        "pseudo.pseudo_total_lightning_resistance": {
            ref for ref, (elements, _) in _RESISTANCE_REFS.items() if "lightning" in elements
        },
        "pseudo.pseudo_total_all_attributes": {"+# to all Attributes"},
        "pseudo.pseudo_total_strength": {ref for ref, attrs in _ATTRIBUTE_REFS.items() if "str" in attrs},
        "pseudo.pseudo_total_dexterity": {ref for ref, attrs in _ATTRIBUTE_REFS.items() if "dex" in attrs},
        "pseudo.pseudo_total_intelligence": {ref for ref, attrs in _ATTRIBUTE_REFS.items() if "int" in attrs},
    }
    pseudo_refs.update({stat_id: {ref} for stat_id, ref in simple_sources.items()})
    for row in filters:
        sources = by_stat.get(row.stat_id, ())
        source = sources[0] if sources else None
        pseudo_sources = [modifier for modifier in item.modifiers
                          if modifier.ref in pseudo_refs.get(row.stat_id, set())]
        if source is None and len(pseudo_sources) == 1:
            source = pseudo_sources[0]
        reason = row.selection_reason
        if not reason:
            if row.enabled and row.stat_id in property_reasons:
                reason = property_reasons[row.stat_id]
            elif row.enabled and row.kind == "pseudo":
                reason = "複数Modを集約した主要pseudo条件"
            elif row.enabled and unique_item:
                reason = "ユニークの可変Modが3個以下のため自動選択"
            elif row.enabled and source and source.tier in {1, 2}:
                reason = f"クラフトベース向けT{source.tier} Mod"
            elif row.enabled:
                reason = "アイテム種別に応じた主要条件"
            else:
                reason = "候補として表示（初期未選択）"
        exact = row.exact or (
            row.min_value is not None and row.max_value is not None and row.min_value == row.max_value
        )
        read_value = source.values[0] if source and source.values else row.read_value
        if read_value is None:
            read_value = property_values.get(row.stat_id)
        if read_value is None and row.kind == "pseudo" and row.min_value is not None:
            read_value = round(row.min_value / (1 - DEFAULT_SEARCH_RANGE), 2)
        decorated.append(replace(
            row,
            read_value=read_value,
            tier=source.tier if source else row.tier,
            roll_min=source.roll_min if source else row.roll_min,
            roll_max=source.roll_max if source else row.roll_max,
            affix=source.affix if source else row.affix,
            generation=("複数Mod集約" if len(pseudo_sources) > 1 else
                        ((source.generation or source.kind) if source else row.generation)),
            selection_reason=reason,
            exact=exact,
            better=source.better if source else row.better,
        ))
    return tuple(decorated)


def resolve_trade_stat_filters(
    item: ParsedItem, preset: str = PRESET_FINISHED,
) -> tuple[TradeStatFilter, ...]:
    if preset not in TRADE_PRESETS:
        raise ValueError(f"未対応の検索プリセットです: {preset}")
    if preset == PRESET_BASE:
        if PRESET_BASE not in available_trade_presets(item):
            raise ValueError("このアイテムはクラフトベース検索の対象外です。")
        return _decorate_filters(item, _base_item_filters(item))
    entries = _trade_stat_entries()
    resolved: list[TradeStatFilter] = []
    unique_item = _is_unique(item)
    for modifier in item.modifiers:
        roll_bounds = _unique_roll_bounds(modifier.text) if unique_item else None
        if unique_item and roll_bounds is None:
            # 固定値は同名ユニーク間で価格比較に寄与しない。
            continue
        api_kind = "explicit" if modifier.kind in {"prefix", "suffix"} else modifier.kind
        source = _normalized_stat_text(modifier.text)
        candidates = []
        for entry in entries:
            if entry.get("type") != api_kind:
                continue
            candidate = str(entry.get("text", ""))
            comparable = candidate.replace(" (ローカル)", "")
            if _normalized_stat_text(comparable) == source:
                candidates.append(entry)
        if not candidates:
            continue
        if item.category == "weapon" and len(candidates) > 1:
            local = [entry for entry in candidates if "(ローカル)" in str(entry.get("text", ""))]
            if local:
                candidates = local
        entry = candidates[0]
        if _aggregated_local_property_stat(item, str(entry["id"])):
            # DPS・APS・クリ率・防御値へ反映済みなので二重条件化しない。
            continue
        value = _value_for_template(modifier.text, str(entry.get("text", "")))
        if value is None:
            value = modifier.values[0] if modifier.values else None
        maximum = None
        if modifier.stat_id == str(entry["id"]):
            metadata, _ = default_metadata_index().match(modifier.text, modifier.kind)
            if metadata:
                value, maximum = metadata.search_bounds(
                    value,
                    modifier.roll_min if unique_item else None,
                    modifier.roll_max if unique_item else None,
                    DEFAULT_SEARCH_RANGE,
                )
        if unique_item and roll_bounds is not None and modifier.stat_id != str(entry["id"]):
            value = _unique_minimum(value, roll_bounds)
        resolved.append(TradeStatFilter(
            str(entry["id"]), modifier.text, value, modifier.kind, False,
            maximum, modifier.ref, modifier.confidence, modifier.inverted,
        ))
    combined: dict[str, TradeStatFilter] = {}
    counts: dict[str, int] = {}
    for stat_filter in resolved:
        previous = combined.get(stat_filter.stat_id)
        if previous is None:
            combined[stat_filter.stat_id] = stat_filter
            counts[stat_filter.stat_id] = 1
            continue
        counts[stat_filter.stat_id] += 1
        total = None
        if previous.min_value is not None and stat_filter.min_value is not None:
            total = previous.min_value + stat_filter.min_value
        combined[stat_filter.stat_id] = TradeStatFilter(
            stat_filter.stat_id, previous.text, total, previous.kind, False,
            stat_filter.max_value, stat_filter.ref, min(previous.confidence, stat_filter.confidence),
            stat_filter.inverted,
        )
    enable_unique_rolls = unique_item and len(combined) <= 3
    consumed_stat_ids = _pseudo_consumed_stat_ids(item)
    individual = tuple(
        TradeStatFilter(
            row.stat_id,
            f"{row.text} ({counts[row.stat_id]}行合計)" if counts[row.stat_id] > 1 else row.text,
            row.min_value, row.kind, enable_unique_rolls or row.enabled,
            row.max_value, row.ref, row.confidence, row.inverted,
        )
        for row in combined.values() if row.stat_id not in consumed_stat_ids
    )
    if unique_item:
        return _decorate_filters(item, individual + _item_detail_filters(item), True)
    filters = (
        tuple(_initial_property_filters(item) + _gear_pseudo_filters(item))
        + individual + _item_detail_filters(item) + _empty_affix_filters(item)
    )
    return _decorate_filters(item, filters)


def build_search_query(
    item: ParsedItem, trade_base_type: str | None = None,
    stat_filters: tuple[TradeStatFilter, ...] = (),
    trade_status: str = "instant",
    trade_name: str | None = None,
    preset: str = PRESET_FINISHED,
    trade_currency: str = "any",
    include_corrupted: bool | None = None,
    include_split: bool | None = None,
    trade_discriminator: str | None = None,
) -> dict:
    if trade_status not in TRADE_STATUS_OPTIONS:
        raise ValueError(f"未対応の取引方式です: {trade_status}")
    if preset not in TRADE_PRESETS:
        raise ValueError(f"未対応の検索プリセットです: {preset}")
    if trade_currency not in TRADE_CURRENCY_OPTIONS:
        raise ValueError(f"未対応の価格通貨です: {trade_currency}")
    if preset == PRESET_BASE and PRESET_BASE not in available_trade_presets(item):
        raise ValueError("このアイテムはクラフトベース検索の対象外です。")
    if include_corrupted is None:
        include_corrupted = "corrupted" in item.flags
    if include_split is None:
        include_split = "split" in item.flags
    base_type = (trade_base_type or item.base_type).strip()
    query: dict = {
        "status": {"option": TRADE_STATUS_OPTIONS[trade_status]},
        "type": base_type,
        "stats": [{"type": "and", "filters": []}],
        "filters": {},
    }
    currency_option = TRADE_CURRENCY_OPTIONS[trade_currency]
    if currency_option is not None:
        query["filters"]["trade_filters"] = {
            "filters": {"price": {"option": currency_option}}
        }
    if _is_unique(item) and trade_name and trade_name.strip():
        query["name"] = ({"option": trade_name.strip(), "discriminator": trade_discriminator}
                         if trade_discriminator else trade_name.strip())
    if _is_unique(item) and "unidentified" in item.flags:
        query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]["identified"] = {"option": "false"}
    rarity = item.rarity.lower()
    rarity_option = "nonunique" if preset == PRESET_BASE else {
        "レア": "rare", "rare": "rare", "ユニーク": "unique", "unique": "unique",
    }.get(rarity)
    if "foil" in item.flags:
        rarity_option = "uniquefoil"
    if rarity_option:
        query["filters"]["type_filters"] = {"filters": {"rarity": {"option": rarity_option}}}
    if preset == PRESET_BASE:
        misc = query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
        if not include_corrupted:
            misc["corrupted"] = {"option": "false"}
        misc["mirrored"] = {"option": "false"}
        misc["fractured_item"] = {"option": "true" if any(
            modifier.kind == "fractured" for modifier in item.modifiers
        ) else "false"}
        misc["synthesised_item"] = {
            "option": "true" if "synthesised" in item.flags else "false"
        }
        if not include_split:
            misc["split"] = {"option": "false"}
    elif item.category in {"weapon", "armour", "accessory"}:
        misc = query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
        if not include_corrupted:
            misc["corrupted"] = {"option": "false"}
        if "mirrored" in item.flags:
            misc["mirrored"] = {"option": "true"}
        if not include_split:
            misc["split"] = {"option": "false"}
        if "foulborn" not in item.flags:
            misc["foulborn_item"] = {"option": "false"}
    for stat_filter in stat_filters:
        if not stat_filter.enabled:
            continue
        if stat_filter.stat_id == "property.white_sockets":
            sockets = query["filters"].setdefault(
                "socket_filters", {"filters": {}}
            )["filters"].setdefault("sockets", {})
            if stat_filter.min_value is not None:
                sockets["w"] = int(stat_filter.min_value)
            continue
        property_target = _PROPERTY_FILTERS.get(stat_filter.stat_id)
        if property_target:
            group, name = property_target
            minimum = stat_filter.min_value
            if minimum is not None and group == "socket_filters":
                minimum = int(minimum)
            value = {"min": minimum} if minimum is not None else {}
            query["filters"].setdefault(group, {"filters": {}})["filters"][name] = value
            continue
        value = {}
        minimum, maximum = stat_filter.min_value, stat_filter.max_value
        if stat_filter.inverted:
            minimum, maximum = (
                -maximum if maximum is not None else None,
                -minimum if minimum is not None else None,
            )
        if minimum is not None:
            value["min"] = minimum
        if maximum is not None:
            value["max"] = maximum
        query["stats"][0]["filters"].append({"id": stat_filter.stat_id, "value": value})
    return {"query": query, "sort": {"price": "asc"}}


def search_prices(
    item: ParsedItem, trade_base_type: str | None = None, league: str | None = None,
    stat_filters: tuple[TradeStatFilter, ...] = (),
    trade_status: str = "instant",
    trade_name: str | None = None,
    preset: str = PRESET_FINISHED,
    trade_currency: str = "any",
    include_corrupted: bool | None = None,
    include_split: bool | None = None,
    trade_discriminator: str | None = None,
) -> PriceResult:
    league = league or active_pc_league()
    payload = build_search_query(
        item, trade_base_type, stat_filters, trade_status, trade_name, preset,
        trade_currency, include_corrupted, include_split, trade_discriminator,
    )
    search_url = f"{API_ROOT}/search/{quote(league, safe='')}"
    _trade_log(
        f"search: league={league!r} preset={preset!r} trade_status={trade_status!r} "
        f"api_status={TRADE_STATUS_OPTIONS[trade_status]!r} "
        f"trade_currency={trade_currency!r} "
        f"api_currency={TRADE_CURRENCY_OPTIONS[trade_currency]!r} url={search_url}"
    )
    _trade_log_payload(payload)
    search, headers = _request_json(
        search_url, payload,
    )
    query_id = str(search.get("id", ""))
    ids = list(search.get("result", ()))
    _trade_log(f"search response: query_id={query_id!r} candidates={len(ids)}")
    if not query_id:
        _trade_log("search failed: response did not contain a query ID")
        raise TradeApiError("検索IDを取得できませんでした。")
    listings: list[PriceListing] = []
    if ids:
        fetch_ids = ",".join(ids[:10])
        fetch_url = f"{API_ROOT}/fetch/{fetch_ids}?query={quote(query_id)}"
        _trade_log(f"request: GET {fetch_url} (first {min(len(ids), 10)} candidates)")
        fetched, _ = _request_json(fetch_url)
        for row in fetched.get("result", ()):
            listing = row.get("listing", {})
            fetched_item = row.get("item", {})
            price = listing.get("price") or {}
            if price.get("amount") is None or not price.get("currency"):
                continue
            account = (listing.get("account") or {}).get("name", "")
            listings.append(PriceListing(
                float(price["amount"]), str(price["currency"]), str(account),
                str(fetched_item.get("name", "")), str(fetched_item.get("baseType", "")),
            ))
    rate_limit = headers.get("X-Rate-Limit-Ip-State", "") if headers else ""
    _trade_log(
        f"completed: query_id={query_id!r} candidates={len(ids)} "
        f"priced_listings={len(listings)} rate_limit={rate_limit!r}"
    )
    return PriceResult(league, query_id, len(ids), tuple(listings), rate_limit)
