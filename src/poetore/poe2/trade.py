from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
import json
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..models import ParsedItem
from ..trade import (
    LISTED_WITHIN_OPTIONS, PRESET_BASE, PRESET_FINISHED,
    PriceListing, PriceResult, TradeApiError, TradeLeague, TradeStatFilter, _cached_request_json,
    _defence_at_20_quality, _group_price_listings, _property_value,
    physical_dps_at_20_quality,
)
from .parser import TRADE_CATEGORY_BY_CATEGORY
from .metadata import augment_entries, explicit_variant_id, resolve_identity


API_ROOT = "https://www.pathofexile.com/api/trade2"
USER_AGENT = "PoENavi/poetore-poe2-development (github.com/buri34/poenavi)"
LEAGUES_URL = f"{API_ROOT}/data/leagues"
FALLBACK_LEAGUES = (
    TradeLeague("Runes of Aldur"),
    TradeLeague("HC Runes of Aldur", True),
    TradeLeague("Standard"),
    TradeLeague("Hardcore", True),
)


def available_pc_leagues() -> tuple[TradeLeague, ...]:
    """Return only official PoE2 trade leagues in display order."""
    data, _ = _cached_request_json(LEAGUES_URL)
    rows = data.get("result", ())
    leagues = []
    for row in rows:
        league_id = str(row.get("id", "")).strip()
        if not league_id or str(row.get("realm", "poe2")) != "poe2":
            continue
        lowered = league_id.casefold()
        leagues.append(TradeLeague(league_id, "hardcore" in lowered or lowered.startswith("hc ")))
    return tuple(leagues)


def default_pc_league(leagues: tuple[TradeLeague, ...]) -> str:
    for league in leagues:
        if league.id not in {"Standard", "Hardcore"} and not league.hardcore:
            return league.id
    return "Standard"


_STATUS_OPTIONS = {
    "instant": "securable", "available": "available", "online": "online", "offline": "any",
}

_WEAPON_CATEGORIES = {
    "bow", "crossbow", "spear", "flail", "staff", "quarterstaff", "wand",
    "sceptre", "one_mace", "two_mace", "one_sword", "two_sword", "one_axe",
    "two_axe", "dagger",
}
_ARMOUR_CATEGORIES = {
    "focus", "buckler", "shield", "body_armour", "helmet", "gloves", "boots",
}
_EE2_CATEGORY_BY_CATEGORY = {
    "bow": "Bow", "crossbow": "Crossbow", "spear": "Spear", "flail": "Flail",
    "staff": "Staff", "quarterstaff": "Warstaff", "wand": "Wand",
    "sceptre": "Sceptre", "one_mace": "One Hand Mace", "two_mace": "Two Hand Mace",
    "one_sword": "One Hand Sword", "two_sword": "Two Hand Sword",
    "one_axe": "One Hand Axe", "two_axe": "Two Hand Axe", "dagger": "Dagger",
    "focus": "Focus", "buckler": "Buckler", "shield": "Shield",
    "body_armour": "Body Armour", "helmet": "Helmet", "gloves": "Gloves",
    "boots": "Boots",
}


def trade_stat_value(values: tuple[float, ...]) -> float | None:
    """Return Trade2's scalar value for a parsed stat roll."""
    if not values:
        return None
    if len(values) in {2, 4}:
        return sum(values) / len(values)
    return values[0]


def _trade_filter_row(stat_id: str, min_value=None, max_value=None) -> dict:
    row = {"id": stat_id}
    if min_value is not None or max_value is not None:
        row["value"] = {
            **({"min": min_value} if min_value is not None else {}),
            **({"max": max_value} if max_value is not None else {}),
        }
    return row


def _stat_groups_from_modifiers(modifiers) -> list[dict]:
    direct = []
    groups = [{"type": "and", "filters": direct}]
    for modifier in modifiers:
        if not modifier.stat_id:
            continue
        value = trade_stat_value(modifier.values)
        direct.append(_trade_filter_row(modifier.stat_id, value))
    return groups


def _stat_groups_from_filters(filters) -> list[dict]:
    direct = []
    groups = [{"type": "and", "filters": direct}]
    for row in filters:
        if not row.enabled or not row.stat_id or row.stat_id.startswith("property."):
            continue
        alternatives = tuple(dict.fromkeys((row.stat_id, *row.alternative_stat_ids)))
        if row.kind == "virtual-rune" and len(alternatives) > 1:
            groups.append({
                "type": "count", "value": {"min": 1},
                "filters": [
                    _trade_filter_row(stat_id, row.min_value, row.max_value)
                    for stat_id in alternatives
                ],
            })
            continue
        direct.append(_trade_filter_row(row.stat_id, row.min_value, row.max_value))
    return groups


def _property_float(item: ParsedItem, *names: str) -> float | None:
    wanted = {name.casefold() for name in names}
    for name, raw_value in item.properties.items():
        if name.casefold() not in wanted:
            continue
        match = re.search(r"[+-]?\d+(?:\.\d+)?", str(raw_value).replace(",", ""))
        if match:
            return float(match.group())
    return None


def poe2_elemental_dps(item: ParsedItem) -> float | None:
    """Calculate weapon eDPS from PoE2's per-element copied properties."""
    speed = _property_float(item, "秒間アタック回数", "Attacks per Second")
    if speed is None:
        return None

    properties = {name.casefold(): raw for name, raw in item.properties.items()}
    aggregate = properties.get("元素ダメージ".casefold()) or properties.get(
        "Elemental Damage".casefold()
    )
    if aggregate is not None:
        damage_rows = (aggregate,)
    else:
        damage_rows = tuple(
            raw
            for names in (
                ("火ダメージ", "Fire Damage"),
                ("冷気ダメージ", "Cold Damage"),
                ("雷ダメージ", "Lightning Damage"),
            )
            for raw in (
                next(
                    (properties[name.casefold()] for name in names if name.casefold() in properties),
                    None,
                ),
            )
            if raw is not None
        )

    average_damage = 0.0
    found_range = False
    for raw in damage_rows:
        values = [
            float(value)
            for value in re.findall(r"\d+(?:\.\d+)?", str(raw).replace(",", ""))
        ]
        for index in range(0, len(values) - 1, 2):
            average_damage += (values[index] + values[index + 1]) / 2
            found_range = True
    return average_damage * speed if found_range else None


def gem_socket_count(item: ParsedItem) -> int | None:
    """Count PoE2 Gem sockets using EE2's colour-agnostic rule."""
    raw = item.properties.get("Sockets") or item.properties.get("ソケット") or ""
    count = len(re.sub(r"[\s-]", "", str(raw)))
    return count or None


def _augment_socket_count(item: ParsedItem) -> int | None:
    raw = item.properties.get("Sockets") or item.properties.get("ソケット") or ""
    if item.category in {"active_gem", "support_gem", "meta_gem"}:
        return gem_socket_count(item)
    count = len(re.findall(r"(?<![A-Za-z])S(?![A-Za-z])", str(raw), re.IGNORECASE))
    return count or None


def empty_augment_socket_count(item: ParsedItem) -> int:
    """Return a conservative count of sockets that can accept a virtual augment."""
    total = _augment_socket_count(item) or 0
    # PoE2ではCorrupted品にもRune／Soul Coreを挿入できる。
    # EE2と同様にUniqueでは仮挿入UIを出さず、変更不能なMirrored品も対象外にする。
    if total <= 0 or item.rarity == "unique" or "mirrored" in item.flags:
        return 0
    installed = item.augment_count
    return max(0, total - installed)


def _virtual_augment_effect_family(effect: dict) -> tuple[int, int, str]:
    """Group virtual augments by player-facing effect before rune series.

    Elemental siblings intentionally share one family so fire/cold/lightning
    candidates stay adjacent instead of being scattered by augment name.
    """
    texts = effect.get("text") or {}
    text = f"{texts.get('ja', '')} {texts.get('en', '')}".casefold()
    families = (
        (10, 0, ("アーマー、回避力およびエナジーシールド", "armour, evasion and energy shield")),
        (11, 0, ("ルーンワード", "runic ward")),
        (20, 0, ("最大ライフ", "maximum life")),
        (21, 0, ("最大マナ", "maximum mana")),
        (30, 0, ("火耐性", "fire resistance")),
        (30, 1, ("冷気耐性", "cold resistance")),
        (30, 2, ("雷耐性", "lightning resistance")),
        (30, 3, ("混沌耐性", "chaos resistance")),
        (31, 0, ("全ての元素耐性", "all elemental resistances")),
        (40, 0, ("物理ダメージ", "physical damage")),
        (41, 0, ("火ダメージ", "fire damage")),
        (41, 1, ("冷気ダメージ", "cold damage")),
        (41, 2, ("雷ダメージ", "lightning damage")),
        (41, 3, ("混沌ダメージ", "chaos damage")),
        (50, 0, ("アタックスピード", "attack speed")),
        (50, 1, ("キャストスピード", "cast speed")),
        (60, 0, ("筋力", "strength")),
        (60, 1, ("器用さ", "dexterity")),
        (60, 2, ("知性", "intelligence")),
    )
    for rank, sibling_rank, needles in families:
        if any(needle in text for needle in needles):
            return rank, sibling_rank, ""
    normalized = re.sub(r"[#\d.+%(),—-]+", " ", text)
    return 999, 0, " ".join(normalized.split())


def _virtual_augment_series(ref_name: str) -> str:
    return re.sub(r"^(?:Perfect|Greater|Lesser)\s+", "", ref_name, flags=re.IGNORECASE).casefold()


def _virtual_augment_tier(ref_name: str) -> int:
    lowered = ref_name.casefold()
    if lowered.startswith("perfect "):
        return 4
    if lowered.startswith("greater "):
        return 3
    if lowered.startswith("lesser "):
        return 1
    return 2


def _virtual_augment_sort_key(choice: dict) -> tuple:
    effects = tuple(choice.get("effects") or ())
    primary = effects[0] if effects else {}
    ref_name = str(choice.get("ref_name") or "")
    values = tuple(float(value) for value in primary.get("values") or ())
    strength = trade_stat_value(values) or 0.0
    names = choice.get("names") or {}
    return (
        _virtual_augment_effect_family(primary),
        _virtual_augment_series(ref_name),
        -_virtual_augment_tier(ref_name),
        -strength,
        str(names.get("ja") or names.get("en") or ref_name).casefold(),
    )


def available_virtual_augments(item: ParsedItem) -> tuple[dict, ...]:
    """Return bilingual augment choices applicable to the copied item category."""
    category = _EE2_CATEGORY_BY_CATEGORY.get(item.category)
    if category is None or empty_augment_socket_count(item) <= 0:
        return ()
    choices = []
    for entry in augment_entries():
        effects = tuple(
            effect for effect in entry.get("effects", ())
            if category in (effect.get("categories") or ())
        )
        if effects:
            choices.append({**entry, "effects": effects})
    return tuple(sorted(choices, key=_virtual_augment_sort_key))


def _virtual_augment_effect_text(effect: dict, socket_count: int) -> str:
    texts = effect.get("text") or {}
    text = str(texts.get("ja") or texts.get("en") or "")
    values = iter(float(value) * socket_count for value in effect.get("values") or ())

    def replace_value(match: re.Match[str]) -> str:
        value = next(values, None)
        if value is None:
            return match.group()
        return str(int(value)) if value.is_integer() else f"{value:g}"

    return re.sub(r"#", replace_value, text)


def virtual_augment_choice_label(item: ParsedItem, choice: dict) -> str:
    """Return an effect-first label matching the virtual stats sent to Trade2."""
    socket_count = empty_augment_socket_count(item)
    names = choice.get("names") or {}
    name = str(names.get("ja") or names.get("en") or choice.get("ref_name") or "")
    effects = tuple(
        _virtual_augment_effect_text(effect, socket_count)
        for effect in choice.get("effects") or ()
    )
    effect_text = " / ".join(text for text in effects if text)
    count_text = f" ×{socket_count}" if socket_count > 1 else ""
    return f"{effect_text}（{name}{count_text}）" if effect_text else f"{name}{count_text}"


def virtual_augment_filters(item: ParsedItem, ref_name: str | None) -> tuple[TradeStatFilter, ...]:
    """Build disabled-by-default Rune stat rows for one user-selected virtual augment."""
    if not ref_name:
        return ()
    empty = empty_augment_socket_count(item)
    choice = next((row for row in available_virtual_augments(item) if row["ref_name"] == ref_name), None)
    if choice is None or empty <= 0:
        return ()
    rows = []
    for effect in choice["effects"]:
        values = tuple(float(value) * empty for value in effect.get("values") or ())
        value = trade_stat_value(values)
        names = choice.get("names") or {}
        text = str((effect.get("text") or {}).get("ja") or (effect.get("text") or {}).get("en") or "")
        trade_ids = tuple(effect.get("trade_ids") or ())
        if trade_ids:
            rows.append(TradeStatFilter(
                str(trade_ids[0]), f"仮想: {names.get('ja') or names.get('en')} — {text}", value,
                "virtual-rune", True, read_value=value, source_texts=(
                    f"空きソケット{empty}個へ仮挿入（実アイテムは変更しません）",
                ),
                alternative_stat_ids=tuple(str(stat_id) for stat_id in trade_ids[1:]),
            ))
    return tuple(rows)


def _waystone_tier(item: ParsedItem) -> float | None:
    value = _property_float(item, "Waystone Tier", "ウェイストーンティア", "Map Tier", "マップティア")
    if value is not None:
        return value
    match = re.search(r"(?:Tier|ティア)\s*(\d+)", item.base_type, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _poe2_item_property_filters(item: ParsedItem) -> tuple[TradeStatFilter, ...]:
    """Build EE2-style calculated weapon/armour rows from copied final properties."""
    rows: list[TradeStatFilter] = []
    if item.category in _WEAPON_CATEGORIES:
        pdps = physical_dps_at_20_quality(item) or 0.0
        edps = poe2_elemental_dps(item) or 0.0
        total = pdps + edps
        if pdps and edps:
            rows.append(TradeStatFilter(
                "property.total_dps", "合計DPS", total, "property", True,
                read_value=total,
            ))
        if pdps:
            rows.append(TradeStatFilter(
                "property.physical_dps", "物理DPS（品質20%換算）", pdps,
                "property", not edps or pdps / total >= 0.67, read_value=pdps,
            ))
        if edps:
            rows.append(TradeStatFilter(
                "property.elemental_dps", "元素DPS", edps, "property",
                not pdps or edps / total >= 0.67, read_value=edps,
            ))
        aps = _property_value(item, "秒間アタック回数", "Attacks per Second")
        if aps is not None:
            rows.append(TradeStatFilter(
                "property.aps", "秒間アタック回数", aps, "property",
                False, read_value=aps, decimal=True,
            ))
        crit = _property_value(item, "クリティカルヒット率", "Critical Hit Chance")
        if crit is not None:
            rows.append(TradeStatFilter(
                "property.crit", "クリティカルヒット率", crit,
                "property", False, read_value=crit, decimal=True,
            ))
    elif item.category in _ARMOUR_CATEGORIES:
        for stat_id, label, defence, names in (
            ("property.armour", "アーマー（品質20%換算）", "ar", ("アーマー", "Armour")),
            ("property.evasion", "回避力（品質20%換算）", "ev", ("回避力", "Evasion Rating")),
            ("property.energy_shield", "エナジーシールド（品質20%換算）", "es", ("エナジーシールド", "Energy Shield")),
            ("property.ward", "ルーンワード（品質20%換算）", "ward", ("ルーンワード", "Runic Ward", "Ward")),
        ):
            value = _property_value(item, *names)
            if value is None:
                continue
            q20 = _defence_at_20_quality(value, item, defence)
            rows.append(TradeStatFilter(
                stat_id, label, q20, "property", True, read_value=q20,
            ))
        block = _property_value(item, "ブロック率", "Block Chance", "Chance to Block")
        if block is not None:
            rows.append(TradeStatFilter(
                "property.block", "ブロック率", block, "property", False,
                read_value=block,
            ))
    return tuple(rows)


_RESISTANCE_REFS = {
    "#% to All Resistances": (("fire", "cold", "lightning", "chaos"),),
    "#% to all Elemental Resistances": (("fire", "cold", "lightning"),),
    "#% to Fire Resistance": (("fire",),),
    "#% to Cold Resistance": (("cold",),),
    "#% to Lightning Resistance": (("lightning",),),
    "#% to Chaos Resistance": (("chaos",),),
    "#% to Fire and Lightning Resistances": (("fire", "lightning"),),
    "#% to Fire and Cold Resistances": (("fire", "cold"),),
    "#% to Cold and Lightning Resistances": (("cold", "lightning"),),
    "#% to Fire and Chaos Resistances": (("fire", "chaos"),),
    "#% to Cold and Chaos Resistances": (("cold", "chaos"),),
    "#% to Lightning and Chaos Resistances": (("lightning", "chaos"),),
}
_ATTRIBUTE_REFS = {
    "# to all Attributes": ("str", "dex", "int"),
    "# to Strength": ("str",), "# to Dexterity": ("dex",),
    "# to Intelligence": ("int",),
    "# to Strength and Intelligence": ("str", "int"),
    "# to Strength and Dexterity": ("str", "dex"),
    "# to Dexterity and Intelligence": ("dex", "int"),
}


def _poe2_pseudo_filters(item: ParsedItem) -> tuple[tuple[TradeStatFilter, ...], set[str]]:
    """Return useful aggregate pseudos and direct stat IDs replaced by enabled pseudos."""
    resistances = {key: 0.0 for key in ("fire", "cold", "lightning", "chaos")}
    attributes = {key: 0.0 for key in ("str", "dex", "int")}
    sources = {key: [] for key in (*resistances, *attributes, "life", "mana")}
    life = mana = 0.0
    direct_life = direct_mana = False
    for modifier in item.modifiers:
        if not modifier.stat_id or not modifier.ref:
            continue
        value = trade_stat_value(modifier.values)
        if value is None:
            continue
        for elements_group in _RESISTANCE_REFS.get(modifier.ref, ()):
            for element in elements_group:
                resistances[element] += value
                sources[element].append(modifier)
        for attribute in _ATTRIBUTE_REFS.get(modifier.ref, ()):
            attributes[attribute] += value
            sources[attribute].append(modifier)
        if modifier.ref == "# to maximum Life":
            life += value
            direct_life = True
            sources["life"].append(modifier)
        elif modifier.ref == "# to maximum Mana":
            mana += value
            direct_mana = True
            sources["mana"].append(modifier)

    rows: list[TradeStatFilter] = []
    replaced: set[str] = set()

    def add(stat_id: str, text: str, value: float, enabled: bool, used) -> None:
        if not used:
            return
        unique = list(dict.fromkeys(used))
        rows.append(TradeStatFilter(
            stat_id, text, value, "pseudo", enabled, read_value=value,
            source_texts=tuple(mod.text for mod in unique),
        ))
        if enabled:
            replaced.update(mod.stat_id for mod in unique if mod.stat_id)

    elemental_sources = sources["fire"] + sources["cold"] + sources["lightning"]
    add(
        "pseudo.pseudo_total_elemental_resistance", "元素耐性合計",
        resistances["fire"] + resistances["cold"] + resistances["lightning"],
        True, elemental_sources,
    )
    for element, stat_id, label in (
        ("fire", "pseudo.pseudo_total_fire_resistance", "火耐性合計"),
        ("cold", "pseudo.pseudo_total_cold_resistance", "冷気耐性合計"),
        ("lightning", "pseudo.pseudo_total_lightning_resistance", "雷耐性合計"),
    ):
        add(stat_id, label, resistances[element], False, sources[element])
    add(
        "pseudo.pseudo_total_chaos_resistance", "混沌耐性合計",
        resistances["chaos"], True, sources["chaos"],
    )
    for attribute, stat_id, label in (
        ("str", "pseudo.pseudo_total_strength", "筋力合計"),
        ("dex", "pseudo.pseudo_total_dexterity", "器用さ合計"),
        ("int", "pseudo.pseudo_total_intelligence", "知性合計"),
    ):
        add(stat_id, label, attributes[attribute], False, sources[attribute])
    if direct_life:
        add(
            "pseudo.pseudo_total_life", "最大ライフ合計",
            life + attributes["str"] * 2, True, sources["life"] + sources["str"],
        )
    if direct_mana:
        add(
            "pseudo.pseudo_total_mana", "最大マナ合計",
            mana + attributes["int"] * 2, False, sources["mana"] + sources["int"],
        )
    return tuple(rows), replaced


_POE2_PROPERTY_SPECS = (
    ("property.spirit", "スピリット", ("Spirit", "スピリット"), "property", False),
    ("property.runic_ward", "ルーンワード", ("Runic Ward", "ルーンワード", "Ward"), "property", False),
    ("property.reload_time", "リロード時間", ("Reload Time", "リロード時間", "再装填時間"), "property", False),
    ("property.map_revives", "復活回数", ("Revives Available", "復活が利用可能"), "property", False),
    ("property.map_pack_size", "ウェイストーンパックサイズ", ("Monster Pack Size", "モンスターパックサイズ", "Pack Size", "パックサイズ"), "property", False),
    ("property.map_bonus", "ウェイストーンドロップ率", ("Waystone Drop Chance", "ウェイストーンドロップ確率", "ウェイストーンドロップ率"), "property", False),
    ("property.map_magic_monsters", "モンスターエフェクティブ", ("Magic Monsters", "モンスターエフェクティブ"), "property", False),
    ("property.map_rare_monsters", "モンスターレアリティ", ("Rare Monsters", "モンスターレアリティ"), "property", False),
    ("property.area_level", "エリアレベル", ("Area Level", "エリアレベル"), "property", False),
    ("property.unidentified_tier", "未鑑定ティア", ("Unidentified Tier", "未鑑定ティア"), "property", False),
)

_POE2_STATE_LABELS = {
    "corrupted": "コラプト状態",
    "mirrored": "ミラー状態",
    "sanctified": "聖別化",
    "unidentified": "未鑑定",
}

_POE2_STATE_FILTER_NAMES = {
    "corrupted": "corrupted",
    "mirrored": "mirrored",
    "sanctified": "sanctified",
    "unidentified": "identified",
}


def poe2_search_filters(item: ParsedItem) -> tuple[TradeStatFilter, ...]:
    """Build editable Trade2 property/state rows beside resolved modifier rows."""
    rows: list[TradeStatFilter] = []
    for stat_id, label, names, kind, enabled in _POE2_PROPERTY_SPECS:
        value = _property_float(item, *names)
        if value is not None:
            if stat_id == "property.area_level" and item.category in {"barya", "ultimatum"}:
                enabled = True
            rows.append(TradeStatFilter(
                stat_id, label, value, kind, enabled=enabled, read_value=value,
                exact=stat_id == "property.unidentified_tier",
            ))
    sockets = _augment_socket_count(item)
    if sockets is not None:
        is_gem = item.category in {"active_gem", "support_gem", "meta_gem"}
        stat_id = "property.gem_sockets" if is_gem else "property.augment_sockets"
        label = "ジェムソケット" if is_gem else "オーグメントソケット"
        rows.append(TradeStatFilter(stat_id, label, float(sockets), "property", False, read_value=float(sockets)))
    if item.category == "waystone":
        tier = _waystone_tier(item)
        if tier is not None:
            rows.append(TradeStatFilter(
                "property.map_tier", "ウェイストーンティア", tier, "property", True,
                max_value=tier, read_value=tier, exact=True,
            ))
    ultimatum_hint = str(item.properties.get("Ultimatum Hint") or "").strip()
    if item.category == "ultimatum" and ultimatum_hint:
        rows.append(TradeStatFilter(
            "property.ultimatum_hint", "アルティメイタムの試練のヒント", None,
            "property", False, option_value=ultimatum_hint,
            option_text={
                "Victorious": "勝利の", "Cowardly": "臆病者の", "Deadly": "致命的な",
            }.get(ultimatum_hint, ultimatum_hint),
        ))
    if item.category == "tablet":
        uses = _property_float(item, "Uses Remaining", "残り使用回数", "使用回数残り")
        if uses is not None:
            rows.append(TradeStatFilter(
                "pseudo.pseudo_number_of_uses_remaining", "石板の残り使用回数",
                uses, "pseudo", True, read_value=uses, exact=True,
            ))
    for flag, label in _POE2_STATE_LABELS.items():
        if flag in item.flags:
            rows.append(TradeStatFilter(
                f"property.state.{flag}", label, None, "state",
                flag not in {"crafted", "fractured", "desecrated"},
            ))
    return tuple(rows)


def _poe2_modifier_rows(
    item: ParsedItem, replaced_ids: set[str], preset: str,
) -> tuple[TradeStatFilter, ...]:
    rows: list[TradeStatFilter] = []
    positions: dict[str, int] = {}
    normalized_ids: set[str] = set()
    # Finished-item searches compare obtainable performance rather than Mod
    # provenance.  Normalize every Crafted/Fractured/Desecrated Stat that has
    # an official explicit counterpart, even when the item is immutable
    # (Corrupted, Mirrored, or Sanctified).  Base searches retain provenance.
    normalize_special = preset == PRESET_FINISHED
    for modifier in item.modifiers:
        if not modifier.stat_id:
            continue
        original_id = modifier.stat_id
        converted = explicit_variant_id(original_id) if normalize_special else None
        stat_id = converted or original_id
        value = trade_stat_value(modifier.values)
        provenance_tags = (
            (modifier.kind,)
            if modifier.kind in {"crafted", "fractured", "desecrated"}
            else ()
        )
        row = TradeStatFilter(
            stat_id, modifier.text,
            None if modifier.better == -1 else value,
            "explicit" if converted else modifier.kind,
            enabled=original_id not in replaced_ids,
            max_value=(value if modifier.better == -1 else None),
            ref=modifier.ref, confidence=modifier.confidence,
            read_value=value, roll_min=modifier.roll_min,
            roll_max=modifier.roll_max, better=modifier.better,
            provenance_tags=provenance_tags,
        )
        position = positions.get(stat_id)
        if (
            position is not None
            and (converted or stat_id in normalized_ids)
            and row.better != -1
            and rows[position].better != -1
        ):
            previous = rows[position]
            merged_provenance = tuple(dict.fromkeys(
                previous.provenance_tags + row.provenance_tags
            ))
            rows[position] = replace(
                previous,
                min_value=(previous.min_value or 0.0) + (row.min_value or 0.0),
                read_value=(previous.read_value or 0.0) + (row.read_value or 0.0),
                enabled=previous.enabled or row.enabled,
                provenance_tags=merged_provenance,
            )
            if converted:
                normalized_ids.add(stat_id)
            continue
        rows.append(row)
        # Only merge equal IDs when at least one source was normalized. Natural
        # duplicate explicit rows retain PoENavi's existing independent controls.
        if converted:
            normalized_ids.add(stat_id)
        if converted or stat_id.startswith("explicit."):
            positions.setdefault(stat_id, len(rows) - 1)
    return tuple(rows)


def poe2_trade_filters(
    item: ParsedItem, virtual_augment_ref: str | None = None,
    preset: str = PRESET_FINISHED,
) -> tuple[TradeStatFilter, ...]:
    """Return the complete editable PoE2 filter set, including Phase 7 aggregates."""
    pseudos, replaced_ids = _poe2_pseudo_filters(item)
    modifier_rows = _poe2_modifier_rows(item, set(replaced_ids), preset)
    filters = (
        modifier_rows + pseudos + _poe2_item_property_filters(item)
        + poe2_search_filters(item) + virtual_augment_filters(item, virtual_augment_ref)
    )
    if preset == PRESET_BASE:
        return tuple(
            row for row in filters
            if row.kind == "state" or row.kind in {"crafted", "fractured", "desecrated"}
        )
    return filters


_POE2_FILTER_TARGETS = {
    "property.total_dps": ("equipment_filters", "dps"),
    "property.physical_dps": ("equipment_filters", "pdps"),
    "property.elemental_dps": ("equipment_filters", "edps"),
    "property.aps": ("equipment_filters", "aps"),
    "property.crit": ("equipment_filters", "crit"),
    "property.armour": ("equipment_filters", "ar"),
    "property.evasion": ("equipment_filters", "ev"),
    "property.energy_shield": ("equipment_filters", "es"),
    "property.ward": ("equipment_filters", "ward"),
    "property.block": ("equipment_filters", "block"),
    "property.spirit": ("equipment_filters", "spirit"),
    "property.runic_ward": ("equipment_filters", "ward"),
    "property.reload_time": ("equipment_filters", "reload_time"),
    "property.augment_sockets": ("equipment_filters", "rune_sockets"),
    "property.gem_sockets": ("misc_filters", "gem_sockets"),
    "property.map_tier": ("map_filters", "map_tier"),
    "property.map_revives": ("map_filters", "map_revives"),
    "property.map_pack_size": ("map_filters", "map_packsize"),
    "property.map_bonus": ("map_filters", "map_bonus"),
    "property.map_magic_monsters": ("map_filters", "map_magic_monsters"),
    "property.map_rare_monsters": ("map_filters", "map_rare_monsters"),
    "property.area_level": ("misc_filters", "area_level"),
    "property.unidentified_tier": ("misc_filters", "unidentified_tier"),
    "property.ultimatum_hint": ("map_filters", "ultimatum_hint"),
}


def _apply_poe2_filter_rows(query: dict, filters) -> None:
    for row in filters:
        if not row.enabled:
            continue
        if row.stat_id.startswith("property.state."):
            state = row.stat_id.rsplit(".", 1)[-1]
            filter_name = _POE2_STATE_FILTER_NAMES.get(state)
            if filter_name is None:
                continue
            query["filters"].setdefault("misc_filters", {"filters": {}})["filters"][filter_name] = {
                "option": "false" if state == "unidentified" else "true"
            }
            continue
        target = _POE2_FILTER_TARGETS.get(row.stat_id)
        if target is None:
            continue
        group, name = target
        if row.option_value is not None:
            query["filters"].setdefault(group, {"filters": {}})["filters"][name] = {
                "option": row.option_value
            }
            continue
        value = {
            **({"min": row.min_value} if row.min_value is not None else {}),
            **({"max": row.max_value} if row.max_value is not None else {}),
        }
        if value:
            query["filters"].setdefault(group, {"filters": {}})["filters"][name] = value


def build_search_query(
    item: ParsedItem,
    status: str = "online",
    *,
    quality_min: int | None = None,
    stat_filters: tuple | None = None,
    item_level_min: int | None = None,
    item_level_max: int | None = None,
    gem_level_min: int | None = None,
    gem_sockets_min: int | None = None,
    exact_base_type: bool = True,
    trade_currency: str = "any",
    listed_within: str = "any",
) -> dict:
    trade_category = TRADE_CATEGORY_BY_CATEGORY.get(item.category)
    if trade_category is None and item.category != "wombgift":
        raise ValueError(f"PoE2 Trade category未対応: {item.category}")
    type_filters = (
        {"category": {"option": trade_category}}
        if trade_category is not None else {}
    )
    query = {
        "status": {"option": _STATUS_OPTIONS.get(status, status)},
        "stats": (
            _stat_groups_from_filters(stat_filters)
            if stat_filters is not None else _stat_groups_from_modifiers(item.modifiers)
        ),
        "filters": {"type_filters": {"filters": type_filters}},
    }
    if exact_base_type:
        query["type"] = item.base_type
    type_filter_values = query["filters"]["type_filters"]["filters"]
    if item_level_min is not None or item_level_max is not None:
        type_filter_values["ilvl"] = {
            **({"min": item_level_min} if item_level_min is not None else {}),
            **({"max": item_level_max} if item_level_max is not None else {}),
        }
    if quality_min is not None:
        type_filter_values["quality"] = {"min": quality_min}
    if item.rarity == "unique":
        if item.name:
            query["name"] = item.name
        else:
            type_filter_values["rarity"] = {"option": "unique"}
    else:
        rarity = item.rarity.casefold()
        if exact_base_type and rarity in {"normal", "ノーマル"}:
            type_filter_values["rarity"] = {"option": "normal"}
        elif exact_base_type and rarity in {"magic", "マジック"}:
            type_filter_values["rarity"] = {"option": "magic"}
        elif rarity in {"normal", "ノーマル", "magic", "マジック", "rare", "レア"}:
            type_filter_values["rarity"] = {"option": "nonunique"}
    if stat_filters is not None:
        _apply_poe2_filter_rows(query, stat_filters)
    if gem_level_min is not None or gem_sockets_min is not None:
        misc = query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
        if gem_level_min is not None:
            misc["gem_level"] = {"min": gem_level_min}
        if gem_sockets_min is not None:
            misc["gem_sockets"] = {"min": gem_sockets_min}
    indexed = LISTED_WITHIN_OPTIONS.get(listed_within)
    if trade_currency != "any" or indexed is not None:
        trade = query["filters"].setdefault("trade_filters", {"filters": {}})["filters"]
        if trade_currency != "any":
            trade["price"] = {"option": trade_currency}
        if indexed is not None:
            trade["indexed"] = {"option": indexed}
    return {"query": query, "sort": {"price": "asc"}}


def _localized_identity(ref_name: str, namespace: str) -> str | None:
    entry = resolve_identity(ref_name, namespace)
    if entry is None:
        return None
    localized = str((entry.get("names") or {}).get("ja", "")).strip()
    return localized or None


def build_web_trade_url(
    item: ParsedItem, league: str, payload: dict, query_id: str,
) -> str:
    """Build a Japanese Trade2 URL, falling back when identity is unverified."""
    identity_namespace = (
        "GEM" if item.category in {"active_gem", "support_gem", "meta_gem"} else "ITEM"
    )
    localized_type = _localized_identity(item.base_type, identity_namespace)
    localized_name = (
        _localized_identity(item.name, "UNIQUE") if item.rarity == "unique" else None
    )
    if localized_type is None or (
        item.rarity == "unique" and item.name and localized_name is None
    ):
        return (
            f"https://www.pathofexile.com/trade2/search/poe2/"
            f"{quote(league, safe='')}/{quote(query_id, safe='')}"
        )

    web_payload = deepcopy(payload)
    web_query = web_payload["query"]
    if "type" in web_query:
        web_query["type"] = localized_type
    if item.rarity == "unique" and "name" in web_query:
        web_query["name"] = localized_name
    encoded_query = quote(
        json.dumps(web_payload, ensure_ascii=False, separators=(",", ":")), safe="",
    )
    return (
        f"https://jp.pathofexile.com/trade2/search/poe2/{quote(league, safe='')}"
        f"?q={encoded_query}"
    )


def _request_json(request: Request) -> dict:
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def search_items(
    league: str,
    payload: dict,
    request_json: Callable[[Request], dict] = _request_json,
) -> dict:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        f"{API_ROOT}/search/{quote(league, safe='')}",
        data=body,
        method="POST",
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
    )
    return request_json(request)


def _property_number(item: dict, *names: str) -> int | None:
    wanted = {name.casefold() for name in names}
    for prop in item.get("properties") or ():
        if str(prop.get("name", "")).casefold() not in wanted:
            continue
        values = prop.get("values") or ()
        if values:
            match = re.search(r"-?\d+", str(values[0][0]))
            if match:
                return int(match.group())
    return None


def search_prices(
    item: ParsedItem,
    league: str,
    *,
    status: str = "online",
    stat_filters: tuple | None = None,
    quality_min: int | None = None,
    item_level_min: int | None = None,
    item_level_max: int | None = None,
    gem_level_min: int | None = None,
    gem_sockets_min: int | None = None,
    exact_base_type: bool = True,
    trade_currency: str = "any",
    listed_within: str = "any",
    include_corrupted=None,
    include_mirrored: bool | None = None,
    include_sanctified=None,
    partial_result_callback: Callable[[PriceResult], None] | None = None,
) -> PriceResult:
    """Search Trade2 and adapt its rows to the existing shared price UI model."""
    payload = build_search_query(
        item, status=status, quality_min=quality_min, stat_filters=stat_filters,
        item_level_min=item_level_min, item_level_max=item_level_max,
        gem_level_min=gem_level_min, gem_sockets_min=gem_sockets_min,
        exact_base_type=exact_base_type, trade_currency=trade_currency,
        listed_within=listed_within,
    )
    misc = payload["query"]["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
    if include_corrupted == "only":
        misc["corrupted"] = {"option": "true"}
    elif include_corrupted is False:
        misc["corrupted"] = {"option": "false"}
    if include_mirrored is False:
        misc["mirrored"] = {"option": "false"}
    if include_sanctified == "only":
        misc["sanctified"] = {"option": "true"}
    elif include_sanctified is False:
        misc["sanctified"] = {"option": "false"}
    if not misc:
        payload["query"]["filters"].pop("misc_filters", None)
    search_url = f"{API_ROOT}/search/{quote(league, safe='')}"
    search, headers, search_cached = _cached_request_json(search_url, payload)
    query_id = str(search.get("id", ""))
    ids = list(search.get("result", ()))
    if not query_id:
        raise TradeApiError("PoE2 Trade APIから検索IDを取得できませんでした。")
    web_url = build_web_trade_url(item, league, payload, query_id)

    raw: list[PriceListing] = []
    fetch_cached = False
    fetched_count = 0
    while fetched_count < min(len(ids), 100):
        fetch_ids = ",".join(ids[fetched_count:fetched_count + 10])
        fetched, _, block_cached = _cached_request_json(
            f"{API_ROOT}/fetch/{fetch_ids}?query={quote(query_id)}"
        )
        fetch_cached = fetch_cached or block_cached
        for row in fetched.get("result", ()):
            listing = row.get("listing") or {}
            fetched_item = row.get("item") or {}
            price = listing.get("price") or {}
            has_price = price.get("amount") is not None and bool(price.get("currency"))
            raw.append(PriceListing(
                float(price["amount"]) if has_price else 0.0,
                str(price["currency"]) if has_price else "",
                str((listing.get("account") or {}).get("name", "")),
                str(fetched_item.get("name", "")),
                str(fetched_item.get("baseType", "")),
                str(listing.get("indexed", "")),
                int(fetched_item["ilvl"]) if fetched_item.get("ilvl") is not None else None,
                _property_number(fetched_item, "Level", "レベル", "Gem Level", "ジェムレベル"),
                _property_number(fetched_item, "Quality", "品質"),
                int(fetched_item["stackSize"]) if fetched_item.get("stackSize") is not None else None,
                pricing_method=(
                    "instant" if listing.get("fee") is not None
                    else "face_to_face" if has_price or fetched_item.get("note") is not None
                    else "unpriced"
                ),
            ))
        fetched_count += 10
        grouped = _group_price_listings(raw)
        if partial_result_callback is not None and fetched_count == 10 and len(ids) > 10:
            partial_result_callback(PriceResult(
                league, query_id, len(ids), grouped,
                headers.get("X-Rate-Limit-Ip-State", "") if headers else "",
                web_url,
                search_cached or fetch_cached,
            ))
        independent = sum(row.listed_times <= 2 for row in grouped)
        if fetched_count >= 20 and len(grouped) >= 10 and independent >= 7:
            break

    return PriceResult(
        league, query_id, len(ids), _group_price_listings(raw),
        headers.get("X-Rate-Limit-Ip-State", "") if headers else "",
        web_url,
        search_cached or fetch_cached,
    )


def fetch_listings(
    query_id: str,
    result_ids: list[str],
    request_json: Callable[[Request], dict] = _request_json,
) -> dict:
    ids = ",".join(result_ids[:10])
    request = Request(
        f"{API_ROOT}/fetch/{ids}?query={quote(query_id, safe='')}",
        headers={"User-Agent": USER_AGENT},
    )
    return request_json(request)
