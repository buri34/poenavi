from __future__ import annotations

from dataclasses import dataclass, replace
from collections import OrderedDict
import json
import re
from statistics import median
import threading
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import ParsedItem
from .metadata import (
    base_armour_bounds, default_metadata_index, gem_metadata, normalize_stat_text,
    pseudo_relations,
)


API_ROOT = "https://www.pathofexile.com/api/trade"
JP_API_ROOT = "https://jp.pathofexile.com/api/trade"
LEAGUES_API_URL = "https://www.pathofexile.com/api/leagues?type=main&realm=pc"
USER_AGENT = "PoENavi/poetore-local-spike (github.com/buri34/poenavi)"
DEFAULT_SEARCH_RANGE = 0.10
TRADE_STATUS_OPTIONS = {
    "instant": "securable",
    "available": "available",
    "online": "online",
    "offline": "any",
}
LISTED_WITHIN_OPTIONS = {
    "any": None, "1day": "1day", "3days": "3days", "1week": "1week",
    "2weeks": "2weeks", "1month": "1month", "2months": "2months",
}
TRADE_CACHE_TTL = 300.0
TRADE_CACHE_MAX_ENTRIES = 128
TRADE_CURRENCY_OPTIONS = {
    "any": None,
    "chaos": "chaos",
    "divine": "divine",
    "chaos_divine": "chaos_divine",
}

_ITEM_CLASS_TRADE_CATEGORIES = {
    "Body Armours": "armour.chest", "鎧": "armour.chest",
    "Boots": "armour.boots", "ブーツ": "armour.boots", "靴": "armour.boots",
    "Gloves": "armour.gloves", "グローブ": "armour.gloves", "手袋": "armour.gloves",
    "Helmets": "armour.helmet", "ヘルメット": "armour.helmet", "兜": "armour.helmet",
    "Shields": "armour.shield", "盾": "armour.shield",
    "Bows": "weapon.bow", "弓": "weapon.bow",
    "Claws": "weapon.claw", "鉤爪": "weapon.claw",
    "Daggers": "weapon.dagger", "短剣": "weapon.dagger",
    "Rune Daggers": "weapon.runedagger", "ルーンの短剣": "weapon.runedagger",
    "Fishing Rods": "weapon.rod", "釣り竿": "weapon.rod",
    "One Hand Axes": "weapon.oneaxe", "片手斧": "weapon.oneaxe",
    "One Hand Maces": "weapon.onemace", "片手メイス": "weapon.onemace",
    "Sceptres": "weapon.sceptre", "セプター": "weapon.sceptre",
    "One Hand Swords": "weapon.onesword", "片手剣": "weapon.onesword",
    "Staves": "weapon.staff", "スタッフ": "weapon.staff",
    "Warstaves": "weapon.warstaff", "ウォースタッフ": "weapon.warstaff",
    "Two Hand Axes": "weapon.twoaxe", "両手斧": "weapon.twoaxe",
    "Two Hand Maces": "weapon.twomace", "両手メイス": "weapon.twomace",
    "Two Hand Swords": "weapon.twosword", "両手剣": "weapon.twosword",
    "Wands": "weapon.wand", "ワンド": "weapon.wand",
    "Rings": "accessory.ring", "指輪": "accessory.ring",
    "Amulets": "accessory.amulet", "アミュレット": "accessory.amulet",
    "Belts": "accessory.belt", "ベルト": "accessory.belt",
    "Jewels": "jewel.base", "ジュエル": "jewel.base",
    "Abyss Jewels": "jewel.abyss", "アビスジュエル": "jewel.abyss",
}


def item_class_trade_category(item_class: str) -> str | None:
    return _ITEM_CLASS_TRADE_CATEGORIES.get(item_class.strip())
CONSUMABLE_CRAFTABLE_CATEGORIES = {
    "map", "heist_blueprint", "heist_contract", "invitation",
    "memory_line", "expedition_logbook",
}
NON_CRAFTABLE_CATEGORIES = {"gem", "flask", "currency", "divination_card"}
DEDICATED_EXACT_CATEGORIES = {
    "gem", "captured_beast", "map", "memory_line", "invitation",
    "heist_contract", "heist_blueprint", "charm",
}
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
    "property.block": ("armour_filters", "block"),
    "property.base_percentile": ("armour_filters", "base_defence_percentile"),
    "property.memory_strands": ("misc_filters", "memory_level"),
    "property.item_level": ("misc_filters", "ilvl"),
    "property.quality": ("misc_filters", "quality"),
    "property.gem_level": ("misc_filters", "gem_level"),
    "property.sockets": ("socket_filters", "sockets"),
    "property.links": ("socket_filters", "links"),
    "property.map_tier": ("map_filters", "map_tier"),
    "property.map_quantity": ("map_filters", "map_iiq"),
    "property.map_rarity": ("map_filters", "map_iir"),
    "property.map_pack_size": ("map_filters", "map_packsize"),
    "property.area_level": ("map_filters", "area_level"),
    "property.heist_wings": ("heist_filters", "heist_wings"),
    "property.heist_lockpicking": ("heist_filters", "heist_lockpicking"),
    "property.heist_brute_force": ("heist_filters", "heist_brute_force"),
    "property.heist_perception": ("heist_filters", "heist_perception"),
    "property.heist_demolition": ("heist_filters", "heist_demolition"),
    "property.heist_counter_thaumaturgy": ("heist_filters", "heist_counter_thaumaturgy"),
    "property.heist_trap_disarmament": ("heist_filters", "heist_trap_disarmament"),
    "property.heist_agility": ("heist_filters", "heist_agility"),
    "property.heist_deception": ("heist_filters", "heist_deception"),
    "property.heist_engineering": ("heist_filters", "heist_engineering"),
    "property.sanctum_resolve": ("sanctum_filters", "sanctum_resolve"),
    "property.sanctum_max_resolve": ("sanctum_filters", "sanctum_max_resolve"),
    "property.sanctum_inspiration": ("sanctum_filters", "sanctum_inspiration"),
    "property.sanctum_gold": ("sanctum_filters", "sanctum_gold"),
}

_WEAPON_PHYSICAL_STAT_KEYS = {"1509134228", "1940865751"}
_WEAPON_ELEMENTAL_STAT_KEYS = {"3336890334", "1037193709", "709508406"}
_WEAPON_SPEED_STAT_KEYS = {"210067635"}
_WEAPON_CRIT_STAT_KEYS = {"2375316951"}
_ARMOUR_STAT_KEYS = {
    "4052037485", "124859000", "4015621042", "53045048", "1062208444",
    "3484657501", "3321629045", "2451402625", "1999113824", "3523867985",
    "4253454700",
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

_RELATIONAL_SOURCE_REFS = {
    "#% increased Spell Critical Strike Chance",
    "#% increased Elemental Damage with Attack Skills",
    "#% increased Burning Damage",
}


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
    indexed: str = ""
    item_level: int | None = None
    gem_level: int | None = None
    quality: int | None = None
    stack_size: int | None = None


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
    option_value: int | str | None = None
    option_text: str | None = None
    oils: tuple[int, ...] = ()
    group_type: str = "and"
    group_key: str = ""
    group_min: int | None = None


@dataclass(frozen=True)
class TradeLeague:
    id: str
    hardcore: bool = False


@dataclass(frozen=True)
class PriceResult:
    league: str
    query_id: str
    total: int
    listings: tuple[PriceListing, ...]
    rate_limit: str = ""
    web_url: str = ""
    cached: bool = False

    def median_by_currency(self) -> dict[str, float]:
        grouped: dict[str, list[float]] = {}
        for listing in self.listings:
            grouped.setdefault(listing.currency, []).append(listing.amount)
        return {currency: median(values) for currency, values in grouped.items()}


class _TtlLruCache:
    def __init__(self, max_entries: int = TRADE_CACHE_MAX_ENTRIES):
        self.max_entries = max_entries
        self._rows: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str):
        now = time.monotonic()
        with self._lock:
            row = self._rows.get(key)
            if row is None:
                return None
            expires, value = row
            if expires <= now:
                self._rows.pop(key, None)
                return None
            self._rows.move_to_end(key)
            return value

    def set(self, key: str, value, ttl: float = TRADE_CACHE_TTL) -> None:
        with self._lock:
            self._rows[key] = (time.monotonic() + ttl, value)
            self._rows.move_to_end(key)
            while len(self._rows) > self.max_entries:
                self._rows.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._rows.clear()


_trade_response_cache = _TtlLruCache()


def _cached_request_json(url: str, payload: dict | None = None) -> tuple[dict, object, bool]:
    key = json.dumps([url, payload], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cached = _trade_response_cache.get(key)
    if cached is not None:
        data, headers = cached
        return data, headers, True
    data, headers = _request_json(url, payload)
    _trade_response_cache.set(key, (data, headers))
    return data, headers, False


def _request_json(url: str, payload: dict | None = None) -> tuple[dict, object]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers)
    for attempt in range(2):
        try:
            with urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8")), response.headers
        except HTTPError as exc:
            if exc.code == 429 and attempt == 0:
                try:
                    retry_after = float(exc.headers.get("Retry-After", "1"))
                except (TypeError, ValueError):
                    retry_after = 1.0
                delay = min(30.0, max(0.2, retry_after))
                _trade_log(f"rate limited; retrying once after {delay:g}s")
                time.sleep(delay)
                continue
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
                error_payload = json.loads(error_body)
                api_message = str((error_payload.get("error") or {}).get("message") or "").strip()
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                api_message = ""
            _trade_log(
                f"request failed: {request.get_method()} {url} error={exc!r} "
                f"api_message={api_message!r}"
            )
            detail = f"（{api_message}）" if api_message else ""
            raise TradeApiError(
                f"PoE Trade APIが検索条件を受理しませんでした: HTTP {exc.code}{detail}"
            ) from exc
        except Exception as exc:
            _trade_log(f"request failed: {request.get_method()} {url} error={exc!r}")
            raise TradeApiError(f"PoE Trade APIへの接続に失敗しました: {exc}") from exc
    raise TradeApiError("PoE Trade APIへの再接続に失敗しました。")


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


def available_pc_leagues() -> tuple[TradeLeague, ...]:
    """Awakened相当の、取引可能なPCリーグ一覧。"""
    _trade_log(f"request: GET {LEAGUES_API_URL}")
    data, _ = _request_json(LEAGUES_API_URL)
    if not isinstance(data, list):
        raise TradeApiError("リーグ一覧の形式を認識できませんでした。")

    leagues = []
    for row in data:
        league_id = str(row.get("id", "")).strip()
        rule_ids = {str(rule.get("id", "")) for rule in row.get("rules", ())}
        if not league_id or str(row.get("realm", "pc")) != "pc":
            continue
        if league_id == "Hardcore" or "NoParties" in rule_ids:
            continue
        if "HardMode" in rule_ids and not row.get("event"):
            continue
        leagues.append(TradeLeague(league_id, "Hardcore" in rule_ids))
    return tuple(leagues)


def default_pc_league(leagues: tuple[TradeLeague, ...]) -> str:
    for league in leagues:
        if league.id != "Standard" and not league.hardcore:
            return league.id
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


def _memory_strands(item: ParsedItem) -> float | None:
    return _property_value(
        item, "メモリーの糸", "記憶の糸", "メモリーストランド", "Memory Strands",
    )


_DEFENCE_REFS = {
    "ar": ({"+# to Armour"}, {
        "#% increased Armour", "#% increased Armour and Energy Shield",
        "#% increased Armour and Evasion", "#% increased Armour, Evasion and Energy Shield",
    }),
    "ev": ({"+# to Evasion Rating"}, {
        "#% increased Evasion Rating", "#% increased Armour and Evasion",
        "#% increased Evasion and Energy Shield", "#% increased Armour, Evasion and Energy Shield",
    }),
    "es": ({"+# to maximum Energy Shield"}, {
        "#% increased Energy Shield", "#% increased Armour and Energy Shield",
        "#% increased Evasion and Energy Shield", "#% increased Armour, Evasion and Energy Shield",
    }),
    "ward": ({"+# to Ward"}, {"#% increased Ward"}),
}


def _base_defence_percentile(item: ParsedItem, trade_base_type: str | None) -> float | None:
    bounds = base_armour_bounds(trade_base_type or item.base_type)
    properties = {
        "ar": _property_value(item, "アーマー", "防具", "Armour"),
        "ev": _property_value(item, "回避力", "Evasion Rating"),
        "es": _property_value(item, "エナジーシールド", "Energy Shield"),
        "ward": _property_value(item, "Ward"),
    }
    quality = _property_value(item, "品質", "Quality") or 0.0
    for defence in ("ar", "ev", "es", "ward"):
        total, base_range = properties[defence], bounds.get(defence)
        if not total or not base_range or base_range[0] == base_range[1]:
            continue
        flat_refs, increased_refs = _DEFENCE_REFS[defence]
        flat = increased = 0.0
        for modifier in item.modifiers:
            value = modifier.values[0] if modifier.values else 0.0
            if modifier.ref in flat_refs:
                flat += value
            elif modifier.ref in increased_refs:
                increased += value
        rolled_base = total / (1.0 + quality / 100.0) / (1.0 + increased / 100.0) - flat
        percentile = round((rolled_base - base_range[0]) * 100.0 / (base_range[1] - base_range[0]))
        return float(min(100, max(0, percentile)))
    return None


def available_trade_presets(item: ParsedItem) -> tuple[str, ...]:
    """完成品を基本とし、未完成でクラフト価値がある装備だけベース検索を追加する。"""
    rarity = item.rarity.casefold()
    if (item.category not in {"weapon", "armour", "accessory", "cluster_jewel", "jewel", "abyss_jewel"}
            or _is_unique(item) or rarity in {"normal", "ノーマル"}
            or "unidentified" in item.flags):
        return (PRESET_FINISHED,)
    quality = _property_value(item, "品質", "Quality")
    likely_finished = (
        any(modifier.kind == "crafted" for modifier in item.modifiers)
        or (quality == 20 and _memory_strands(item) is None)
        or "corrupted" in item.flags
        or "mirrored" in item.flags
    )
    has_crafting_value = (
        any(modifier.kind == "fractured" for modifier in item.modifiers)
        or "synthesised" in item.flags
        or any(flag.startswith("influence:") for flag in item.flags)
        or item.category == "cluster_jewel"
        or (item.category == "jewel" and rarity in {"magic", "マジック"})
        or bool(item.category not in {"jewel", "abyss_jewel"}
                and item.item_level is not None and item.item_level >= 82)
    )
    if likely_finished or not has_crafting_value:
        return (PRESET_FINISHED,)
    return (PRESET_FINISHED, PRESET_BASE)


def uses_dedicated_exact_preset(item: ParsedItem) -> bool:
    """Awakenedの単一Exactプリセットへ入るアイテムかを返す。

    Sentinelは製品判断で対象外。Logbookは本来エリア別Exactだが、検索条件の
    共通部分もExactとして扱う。
    """
    rarity = item.rarity.casefold()
    if item.category == "expedition_logbook":
        return True
    if item.category in DEDICATED_EXACT_CATEGORIES:
        return True
    if item.category in {"flask", "tincture", "sanctum_relic", "idol"}:
        return not _is_unique(item)
    return rarity in {"normal", "ノーマル"} or "unidentified" in item.flags


def _apply_dedicated_exact_rules(
    item: ParsedItem, filters: tuple[TradeStatFilter, ...],
) -> tuple[TradeStatFilter, ...]:
    """汎用完成品候補からAwakenedのcreateExactStatFilters相当だけを残す。"""
    keep_modifier_kinds = {"pseudo", "fractured", "enchant", "necropolis", "imbued"}
    if (not any(flag.startswith("influence:") for flag in item.flags)
            and not any(mod.kind == "fractured" for mod in item.modifiers)
            and item.category not in {"tincture", "idol"}):
        keep_modifier_kinds.add("implicit")
    rarity = item.rarity.casefold()
    if (rarity in {"magic", "マジック"}
            and item.category not in {
                "cluster_jewel", "map", "heist_contract", "heist_blueprint", "sentinel",
            }):
        keep_modifier_kinds.update({"prefix", "suffix", "explicit"})
    elif rarity in {"rare", "レア"} and item.category == "idol":
        keep_modifier_kinds.update({"prefix", "suffix", "explicit"})
    if item.category == "flask":
        keep_modifier_kinds.add("crafted")

    property_ids = {
        "property.base_percentile", "property.memory_strands", "property.quality",
        "property.sockets", "property.links", "property.white_sockets",
    }
    special_kinds = {
        "map", "map pseudo", "map safety", "cluster", "heist", "expedition",
        "special", "sanctum", "flask hybrid", "unique exception",
    }
    result = []
    logbook_faction_seen = False
    enable_all = item.category in {"memory_line", "sanctum_relic", "charm"}
    blighted_map = _map_blight_state(item) is not None
    for row in filters:
        if blighted_map and row.stat_id not in {
            "property.map_tier", "property.map_blighted", "property.map_uberblighted",
            "property.map_completion_reward",
        } and row.kind in {"map", "map pseudo", "map safety", "prefix", "suffix", "explicit"}:
            continue
        if row.kind in keep_modifier_kinds or row.kind in special_kinds:
            enabled = row.enabled
            if enable_all or item.category == "map" or row.kind not in {"prefix", "suffix", "explicit"}:
                enabled = True
            elif row.kind in {"prefix", "suffix", "explicit"}:
                enabled = row.tier in {1, 2}
            if item.category == "idol" and row.kind in {"prefix", "suffix", "explicit"}:
                if row.roll_min is None or row.roll_max is None or row.roll_min == row.roll_max:
                    enabled = True
                elif row.read_value is not None:
                    goodness = (row.read_value - row.roll_min) / (row.roll_max - row.roll_min)
                    if row.better == -1:
                        goodness = 1 - goodness
                    enabled = goodness >= 0.66
            if item.category == "expedition_logbook" and row.stat_id.startswith(
                "pseudo.pseudo_logbook_faction_"
            ):
                enabled = not logbook_faction_seen
                logbook_faction_seen = True
            result.append(replace(row, enabled=enabled))
        elif row.stat_id in property_ids:
            result.append(row)
    return tuple(result)


def _dedicated_exact_identity_filters(item: ParsedItem) -> tuple[TradeStatFilter, ...]:
    """createFilters(exact=true)で表示されるilvl/Influenceの候補。"""
    filters: list[TradeStatFilter] = []
    excluded_ilvl = {
        "map", "jewel", "heist_blueprint", "heist_contract", "memory_line",
        "sanctum_relic", "charm", "idol", "expedition_logbook",
    }
    if (item.item_level is not None and not _is_unique(item)
            and item.category not in excluded_ilvl):
        if item.category == "cluster_jewel":
            minimum = max(value for value in (1, 50, 68, 75, 84) if value <= item.item_level)
            maximum = next((value for value in (49, 67, 74, 100) if value >= item.item_level), 100)
            filters.append(TradeStatFilter(
                "property.item_level", "アイテムレベル帯", float(minimum), "base", True,
                max_value=float(maximum), selection_reason="Cluster JewelのMod出現帯へ正規化",
            ))
        else:
            filters.append(TradeStatFilter(
                "property.item_level", "アイテムレベル", float(min(item.item_level, 86)),
                "base", item.category not in {"flask", "tincture"},
            ))
    for flag in item.flags:
        if not flag.startswith("influence:"):
            continue
        stat = _INFLUENCE_STATS.get(flag.split(":", 1)[1])
        if stat:
            filters.append(TradeStatFilter(stat[0], stat[1], None, "influence", True))
    return tuple(filters)


def _base_item_filters(item: ParsedItem, trade_base_type: str | None = None) -> tuple[TradeStatFilter, ...]:
    filters: list[TradeStatFilter] = []
    if item.item_level is not None:
        if item.category == "cluster_jewel":
            minimum = max(value for value in (1, 50, 68, 75, 84) if value <= item.item_level)
            maximum = next((value for value in (49, 67, 74, 100) if value >= item.item_level), 100)
            filters.append(TradeStatFilter(
                "property.item_level", "アイテムレベル帯", float(minimum), "base", True,
                max_value=float(maximum), selection_reason="Cluster JewelのMod出現帯へ正規化",
            ))
        elif item.category not in {"jewel", "abyss_jewel"}:
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
    rarity = item.rarity.casefold()
    has_influence = any(flag.startswith("influence:") for flag in item.flags)
    has_fractured = any(modifier.kind == "fractured" for modifier in item.modifiers)
    exact_modifiers = []
    for modifier in item.modifiers:
        if modifier.kind in {"fractured", "enchant"}:
            exact_modifiers.append(modifier)
        elif modifier.kind == "implicit" and not has_influence and not has_fractured:
            exact_modifiers.append(modifier)
        elif (rarity in {"magic", "マジック"} and item.category != "cluster_jewel"
              and modifier.kind in {"prefix", "suffix"}):
            exact_modifiers.append(modifier)
    entries = _trade_stat_entries() if exact_modifiers else ()
    for modifier in exact_modifiers:
        api_kind = "explicit" if modifier.kind in {"prefix", "suffix"} else modifier.kind
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
        if modifier.stat_id:
            exact_id = [entry for entry in candidates if str(entry.get("id")) == modifier.stat_id]
            if exact_id:
                candidates = exact_id
        # 同じ日本語テンプレートでも意味の異なる公式statがあるため、文字列の曖昧候補を
        # COUNT(OR)にはしない。COUNTはUI指定または確定済み論理グループだけに使う。
        candidates = candidates[:1]
        entry = candidates[0]
        value = _value_for_template(modifier.text, str(entry.get("text", "")))
        if value is None:
            value = modifier.values[0] if modifier.values else None
        enabled = modifier.kind not in {"prefix", "suffix"} or modifier.tier in {1, 2}
        filters.append(TradeStatFilter(
            str(entry["id"]), modifier.text, value,
            (modifier.kind if modifier.kind not in {"prefix", "suffix"}
             else f"T{modifier.tier}" if modifier.tier else "explicit"), enabled,
        ))
    special_properties = tuple(
        row for row in _initial_property_filters(item, trade_base_type)
        if row.stat_id in {"property.base_percentile", "property.memory_strands"}
    )
    return tuple(filters) + special_properties + _item_detail_filters(item)


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


def _gem_filters(item: ParsedItem, trade_base_type: str | None) -> tuple[TradeStatFilter, ...]:
    info = gem_metadata(trade_base_type or item.base_type)
    level = _property_value(item, "ジェムレベル", "レベル", "Level")
    quality = _property_value(item, "品質", "Quality")
    maximum = int(info.get("max_level", 20))
    filters = []
    if level is not None:
        filters.append(TradeStatFilter(
            "property.gem_level", "ジェムレベル", level, "gem", level >= maximum,
            read_value=level, selection_reason=(
                f"最大レベル{maximum}以上を保持" if level >= maximum
                else f"最大レベル{maximum}未満のため初期未選択"
            ),
        ))
    if quality is not None and quality > 0:
        enabled = (
            maximum == 1
            or (maximum == 20 and not info.get("transfigured") and quality >= 16)
            or ((maximum != 20 or info.get("transfigured")) and quality >= 20)
        )
        filters.append(TradeStatFilter(
            "property.quality", "品質", quality, "gem", enabled,
            read_value=quality, selection_reason="Gem種別に応じた品質閾値",
        ))
    if "corrupted" in item.flags and level is not None and level >= 20:
        filters.append(TradeStatFilter(
            "property.gem_imbued", "注入ジェム", None, "gem", False,
            selection_reason="コラプト済み高レベルGemの注入候補",
        ))
    return tuple(filters)


def _floor_bracket(value: float, brackets: tuple[int, ...]) -> float:
    return float(max(level for level in brackets if level <= value))


def _map_blight_state(item: ParsedItem) -> str | None:
    """詳細コピーの日英表記からBlight Mapの種類を判定する。"""
    if item.category != "map":
        return None
    raw = item.raw_text.casefold()
    identity = f"{item.name}\n{item.base_type}".casefold()
    if "blight-ravaged map" in identity or "blight-ravaged" in raw or "ブライトに破壊" in item.raw_text:
        return "ravaged"
    if (
        "blighted map" in identity
        or "blighted map" in raw
        or "ブライトマップ" in item.raw_text
        or (
            "エリアは真菌に覆われている" in item.raw_text
            and "3回アノイントすることができる" in item.raw_text
        )
    ):
        return "blighted"
    return None


def _special_content_filters(item: ParsedItem) -> tuple[TradeStatFilter, ...]:
    filters: list[TradeStatFilter] = []
    area_level = _property_value(item, "エリアレベル", "Area Level")
    if item.category == "cluster_jewel" and item.item_level is not None:
        minimum = max(value for value in (1, 50, 68, 75, 84) if value <= item.item_level)
        maximum = next((value for value in (49, 67, 74, 100) if value >= item.item_level), 100)
        filters.append(TradeStatFilter(
            "property.item_level", "アイテムレベル帯", float(minimum), "cluster", True,
            max_value=float(maximum), selection_reason="Cluster JewelのMod出現帯へ正規化",
        ))
    if item.category == "map":
        for stat_id, label, value in (
            ("property.map_tier", "マップティア", _property_value(item, "マップティア", "Map Tier")),
            ("property.map_quantity", "アイテム数量", _property_value(item, "アイテム数量", "Item Quantity")),
            ("property.map_rarity", "アイテムレアリティ", _property_value(item, "アイテムレアリティ", "Item Rarity")),
            ("property.map_pack_size", "モンスターパックサイズ", _property_value(item, "モンスターパックサイズ", "Monster Pack Size")),
        ):
            if value is not None:
                filters.append(TradeStatFilter(stat_id, label, value, "map", True))
        for stat_id, label, labels in (
            ("pseudo.pseudo_map_more_map_drops", "追加マップ", ("追加マップ", "More Maps")),
            ("pseudo.pseudo_map_more_scarab_drops", "追加スカラベ", ("追加スカラベ", "More Scarabs")),
            ("pseudo.pseudo_map_more_currency_drops", "追加カレンシー", ("追加カレンシー", "More Currency")),
            ("pseudo.pseudo_map_more_card_drops", "追加占いカード", ("追加占いカード", "More Divination Cards")),
        ):
            value = _property_value(item, *labels)
            if value is not None:
                filters.append(TradeStatFilter(stat_id, label, value, "map pseudo", True))
        blight_state = _map_blight_state(item)
        if blight_state == "ravaged":
            filters.append(TradeStatFilter("property.map_uberblighted", "ブライトに破壊されたマップ", None, "map", True))
        elif blight_state == "blighted":
            filters.append(TradeStatFilter("property.map_blighted", "ブライトマップ", None, "map", True))
        completion = item.properties.get("マップ完了報酬") or item.properties.get("Map Completion Reward")
        if completion:
            filters.append(TradeStatFilter(
                "property.map_completion_reward", f"完了報酬: {completion}", None, "map", True,
                option_value=completion,
            ))
            if not any(modifier.ref == "Players who Die in area are sent to the Void" for modifier in item.modifiers):
                filters.append(TradeStatFilter(
                    "explicit.stat_1095765106", "死亡時にVoidへ送られるマップを除外", None,
                    "map safety", True, group_type="not", group_key="valdo-lethal",
                ))
    elif item.category == "expedition_logbook" and area_level is not None:
        filters.append(TradeStatFilter(
            "property.area_level", "エリアレベル帯",
            _floor_bracket(area_level, (1, 68, 73, 78, 81, 83)), "expedition", True,
        ))
    elif item.category in {"heist_blueprint", "heist_contract"}:
        if area_level is not None:
            filters.append(TradeStatFilter(
                "property.area_level", "エリアレベル", area_level, "heist", True,
            ))
        wings = _property_value(item, "情報を聞いた区画数", "Wings Revealed")
        if item.category == "heist_blueprint" and wings is not None:
            filters.append(TradeStatFilter("property.heist_wings", "情報を聞いた区画数", wings, "heist", True))
        if item.category == "heist_blueprint" and not any(
            modifier.kind == "enchant" for modifier in item.modifiers
        ):
            filters.append(TradeStatFilter(
                "pseudo.pseudo_number_of_enchant_mods", "Enchant ModがないBlueprint", None,
                "heist", True, group_type="not", group_key="blueprint-enchant",
            ))
        job_names = {
            "lockpicking": "property.heist_lockpicking", "錠前破り": "property.heist_lockpicking",
            "brute force": "property.heist_brute_force", "怪力": "property.heist_brute_force",
            "perception": "property.heist_perception", "知覚能力": "property.heist_perception",
            "demolition": "property.heist_demolition", "爆破": "property.heist_demolition",
            "counter-thaumaturgy": "property.heist_counter_thaumaturgy", "対魔術": "property.heist_counter_thaumaturgy",
            "trap disarmament": "property.heist_trap_disarmament", "罠解除": "property.heist_trap_disarmament",
            "agility": "property.heist_agility", "敏捷性": "property.heist_agility",
            "deception": "property.heist_deception", "欺瞞": "property.heist_deception",
            "engineering": "property.heist_engineering", "工作": "property.heist_engineering",
        }
        for line in item.raw_text.splitlines():
            match = re.search(r"(?:level|レベル)\s*(\d+)", line, re.I)
            if not match:
                continue
            lowered = line.casefold()
            stat_id = next((stat for name, stat in job_names.items() if name in lowered), None)
            if stat_id:
                filters.append(TradeStatFilter(stat_id, line.strip(), float(match.group(1)), "heist", True))
                break
        if re.search(r"(?:Heist Target|依頼書目標).*?(?:Priceless|プライスレス)", item.raw_text, re.I):
            filters.append(TradeStatFilter(
                "property.heist_objective_value", "依頼書目標: プライスレス", None, "heist", True,
                option_value="priceless",
            ))
    elif area_level is not None:
        name = f"{item.name} {item.base_type}".casefold()
        if "chronicle of atzoatl" in name or "アトゾアトルの年代記" in name:
            area_level = _floor_bracket(area_level, (1, 68, 73, 75, 78, 80))
        maximum = None
        if (("forbidden tome" in name or "禁断の書" in name or "禁じられた書" in name)
                and area_level < 83):
            maximum = area_level
        filters.append(TradeStatFilter(
            "property.area_level", "エリアレベル", area_level, "special", True,
            max_value=maximum,
        ))
    if item.category == "sanctum_relic":
        for stat_id, labels in (
            ("property.sanctum_resolve", ("決心", "Resolve")),
            ("property.sanctum_max_resolve", ("決心の最大値", "Maximum Resolve")),
            ("property.sanctum_inspiration", ("勇気", "Inspiration")),
            ("property.sanctum_gold", ("アウレウス", "Aureus")),
        ):
            value = _property_value(item, *labels)
            if value is not None:
                filters.append(TradeStatFilter(stat_id, labels[0], value, "sanctum", True))
    return tuple(filters)


def _unique_exception_filters(item: ParsedItem) -> tuple[TradeStatFilter, ...]:
    if not _is_unique(item) or item.item_level is None:
        return ()
    name = item.name.casefold()
    if "unidentified" in item.flags and name in {"watcher's eye", "ウォッチャーズアイ"}:
        return (TradeStatFilter(
            "property.item_level", "アイテムレベル", float(item.item_level),
            "unique exception", True, selection_reason="未鑑定Watcher's EyeのMod数を固定",
        ),)
    agnerod = ("agnerod", "アグネロッド")
    if item.item_level >= 75 and any(token in name for token in agnerod):
        normalized = 82 if item.item_level >= 82 else 80 if item.item_level >= 80 else 78 if item.item_level >= 78 else 75
        return (TradeStatFilter(
            "property.item_level", "アイテムレベル帯", float(normalized),
            "unique exception", True, selection_reason="AgnerodのVinktar Square生成帯へ正規化",
        ),)
    return ()


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


def _initial_property_filters(item: ParsedItem, trade_base_type: str | None = None) -> list[TradeStatFilter]:
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
        block = _property_value(item, "ブロック率", "Chance to Block")
        if block is not None:
            filters.append(TradeStatFilter(
                "property.block", "ブロック率", _relaxed(block), "property", False,
            ))
        percentile = _base_defence_percentile(item, trade_base_type)
        if percentile is not None:
            filters.append(TradeStatFilter(
                "property.base_percentile", "ベース防御値パーセンタイル",
                _relaxed(percentile), "property", percentile >= 50,
                read_value=percentile,
            ))
    strands = _memory_strands(item)
    if strands is not None:
        filters.append(TradeStatFilter(
            "property.memory_strands", "メモリーの糸", _relaxed(strands),
            "property", strands >= 60, read_value=strands,
        ))
    return filters


def _gear_pseudo_filters(item: ParsedItem) -> list[TradeStatFilter]:
    if item.category not in {"weapon", "armour", "accessory"}:
        return []
    totals = {"life": 0.0, "mana": 0.0, "fire": 0.0, "cold": 0.0,
              "lightning": 0.0, "chaos": 0.0, "str": 0.0, "dex": 0.0, "int": 0.0}
    simple: dict[str, float] = {}
    for modifier in item.modifiers:
        value = modifier.values[0] if modifier.values else 0
        ref = modifier.ref or ""
        if not ref:
            normalized = normalize_stat_text(modifier.text)
            known_refs = tuple(_RESISTANCE_REFS) + tuple(_ATTRIBUTE_REFS) + (
                "+# to maximum Life", "+# to maximum Mana",
            ) + tuple(row[0] for row in _SIMPLE_PSEUDOS) + tuple(_RELATIONAL_SOURCE_REFS)
            ref = next((candidate for candidate in known_refs
                        if normalize_stat_text(candidate) == normalized), "")
        if ref == "+# to maximum Life": totals["life"] += value
        if ref == "+# to maximum Mana": totals["mana"] += value
        for attr in _ATTRIBUTE_REFS.get(ref, ()):
            totals[attr] += value
        if ref == "+# to all Attributes":
            simple[ref] = simple.get(ref, 0.0) + value
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
                simple[source_ref] = simple.get(source_ref, 0.0) + value
        if ref in _RELATIONAL_SOURCE_REFS:
            simple[ref] = simple.get(ref, 0.0) + value
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
    chaos_sources = [
        modifier for modifier in item.modifiers
        if modifier.ref in _RESISTANCE_REFS and _RESISTANCE_REFS[modifier.ref][1]
    ]
    crafted_chaos_only = len(chaos_sources) == 1 and chaos_sources[0].kind == "crafted"
    if totals["chaos"] and not crafted_chaos_only:
        filters.append(TradeStatFilter(
            "pseudo.pseudo_total_chaos_resistance", "混沌耐性合計", _relaxed(totals["chaos"]), "pseudo", True,
        ))
    for attr, stat_id, label in (("str", "pseudo.pseudo_total_strength", "筋力合計"),
                                 ("dex", "pseudo.pseudo_total_dexterity", "器用さ合計"),
                                 ("int", "pseudo.pseudo_total_intelligence", "知性合計")):
        if totals[attr]: filters.append(TradeStatFilter(stat_id, label, _relaxed(totals[attr]), "pseudo"))
    all_attributes = simple.get("+# to all Attributes", 0.0)
    if all_attributes:
        filters.append(TradeStatFilter(
            "pseudo.pseudo_total_all_attributes", "全能力値合計",
            _relaxed(all_attributes), "pseudo",
        ))

    simple_definitions = {
        ref: (stat_id, label) for ref, stat_id, label in _SIMPLE_PSEUDOS
        if ref not in {
            "#% increased Global Critical Strike Chance",
            "#% increased Elemental Damage", "#% increased Lightning Damage",
            "#% increased Cold Damage", "#% increased Fire Damage",
            "#% increased Spell Damage", "#% increased Lightning Spell Damage",
            "#% increased Cold Spell Damage", "#% increased Fire Spell Damage",
        }
    }
    for ref, (stat_id, label) in simple_definitions.items():
        if simple.get(ref):
            filters.append(TradeStatFilter(stat_id, label, _relaxed(simple[ref]), "pseudo"))

    def add(stat_id: str, label: str, required_ref: str, *shared_refs: str) -> None:
        if not simple.get(required_ref):
            return
        value = sum(simple.get(ref, 0.0) for ref in (required_ref, *shared_refs))
        filters.append(TradeStatFilter(stat_id, label, _relaxed(value), "pseudo"))

    add("pseudo.pseudo_global_critical_strike_chance", "グローバルクリティカル率",
        "#% increased Global Critical Strike Chance")
    add("pseudo.pseudo_critical_strike_chance_for_spells", "スペルクリティカル率合計",
        "#% increased Spell Critical Strike Chance", "#% increased Global Critical Strike Chance")
    add("pseudo.pseudo_increased_elemental_damage", "元素ダメージ増加",
        "#% increased Elemental Damage")
    for element, japanese in (("Lightning", "雷"), ("Cold", "冷気"), ("Fire", "火")):
        add(f"pseudo.pseudo_increased_{element.lower()}_damage", f"{japanese}ダメージ増加",
            f"#% increased {element} Damage", "#% increased Elemental Damage")
    add("pseudo.pseudo_increased_spell_damage", "スペルダメージ増加",
        "#% increased Spell Damage")
    for element, japanese in (("Lightning", "雷"), ("Cold", "冷気"), ("Fire", "火")):
        add(f"pseudo.pseudo_increased_{element.lower()}_spell_damage", f"{japanese}スペルダメージ増加",
            f"#% increased {element} Spell Damage", "#% increased Spell Damage")
    add("pseudo.pseudo_increased_elemental_damage_with_attack_skills", "アタックスキルの元素ダメージ増加",
        "#% increased Elemental Damage with Attack Skills", "#% increased Elemental Damage")
    add("pseudo.pseudo_increased_burning_damage", "燃焼ダメージ増加",
        "#% increased Burning Damage", "#% increased Fire Damage", "#% increased Elemental Damage")
    return _apply_pseudo_relations(filters)


def _apply_pseudo_relations(filters: list[TradeStatFilter]) -> list[TradeStatFilter]:
    """Awakenedのgroup/replacesを候補の入力順に依存せず適用する。"""
    relations = pseudo_relations()
    groups = {row["stat_id"]: row["group"] for row in relations if row.get("group")}
    replaces = {row["stat_id"]: row["replaces"] for row in relations if row.get("replaces")}
    by_id = {row.stat_id: row for row in filters}
    replaced_groups = {
        group for stat_id, group in replaces.items() if stat_id in by_id
    }
    kept = [
        row for row in filters
        if groups.get(row.stat_id) not in replaced_groups
    ]

    # 個別元素耐性は一意に最大の1種だけ表示。同率ならどれも表示しない。
    elemental_ids = {
        stat_id for stat_id, group in groups.items() if group == "to_x_ele_res"
    }
    elemental = [row for row in kept if row.stat_id in elemental_ids]
    if elemental:
        maximum = max(row.min_value or 0 for row in elemental)
        winners = [row for row in elemental if (row.min_value or 0) == maximum]
        winner_id = winners[0].stat_id if len(winners) == 1 else None
        kept = [row for row in kept if row.stat_id not in elemental_ids or row.stat_id == winner_id]

    # 能力値はAwakenedと同じく、all attributesと個別値のどちらかを残す。
    attr_ids = {
        stat_id for stat_id, group in groups.items() if group == "to_x_attr"
    }
    attrs = sorted((row for row in kept if row.stat_id in attr_ids),
                   key=lambda row: (-(row.min_value or 0), row.stat_id))
    all_id = "pseudo.pseudo_total_all_attributes"
    if len(attrs) == 3:
        if len({row.min_value for row in attrs}) == 1 and all_id in by_id:
            kept = [row for row in kept if row.stat_id not in attr_ids]
        else:
            kept = [row for row in kept if row.stat_id != all_id]
            if (attrs[-1].min_value or 0) / (attrs[0].min_value or 1) < 0.3:
                remove = {attrs[-1].stat_id}
                if attrs[-1].min_value == attrs[-2].min_value:
                    remove.add(attrs[-2].stat_id)
                kept = [row for row in kept if row.stat_id not in remove]

    return sorted(kept, key=lambda row: (row.kind != "property", row.stat_id, row.text))


def _pseudo_consumed_stat_ids(item: ParsedItem) -> set[str]:
    """pseudoへ集約した元Modを個別条件として二重表示しない。"""
    known_refs = set(_RESISTANCE_REFS) | set(_ATTRIBUTE_REFS) | {
        "+# to maximum Life", "+# to maximum Mana",
    } | {row[0] for row in _SIMPLE_PSEUDOS} | _RELATIONAL_SOURCE_REFS
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


def _trade_item_entries() -> tuple[dict, ...]:
    global _item_entries_cache
    if _item_entries_cache is None:
        data, _ = _request_json(f"{API_ROOT}/data/items")
        _item_entries_cache = tuple(
            entry for group in data.get("result", ()) for entry in group.get("entries", ())
        )
    return _item_entries_cache


def resolve_official_base_type(value: str) -> str:
    """Affix込みのMagic一行名から、公式英語base typeを復元する。"""
    candidate = _normalize_trade_base_type(value)
    lowered = candidate.casefold()
    base_types = {
        str(entry.get("type", "")).strip()
        for entry in _trade_item_entries()
        if str(entry.get("type", "")).strip()
        and not bool((entry.get("flags") or {}).get("unique"))
    }
    exact = next((base for base in base_types if base.casefold() == lowered), None)
    if exact:
        return exact
    matches = [
        base for base in base_types
        if re.search(rf"(?<![A-Za-z]){re.escape(base)}(?![A-Za-z])", candidate, re.IGNORECASE)
    ]
    return max(matches, key=len) if matches else candidate


def unique_candidates(base_type: str) -> tuple[str, ...]:
    """未鑑定ユニークの英語ベースから、公式データの同名検索候補を返す。"""
    entries = _trade_item_entries()
    target = base_type.strip().casefold()
    names = {
        str(entry.get("name", "")).strip()
        for entry in entries
        if str(entry.get("type", "")).strip().casefold() == target
        and bool((entry.get("flags") or {}).get("unique"))
        and str(entry.get("name", "")).strip()
    }
    return tuple(sorted(names))


def unique_variants(name: str, base_type: str) -> tuple[tuple[str, str | None], ...]:
    """同名・同ベースの公式Trade discriminator候補を返す。"""
    entries = _trade_item_entries()
    target_name, target_base = name.strip().casefold(), base_type.strip().casefold()
    variants = {
        (str(entry.get("text") or entry.get("name") or name),
         str(entry["disc"]) if entry.get("disc") else None)
        for entry in entries
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
        "property.base_percentile": "防具ベース固有値のロールを保持",
        "property.memory_strands": "高いメモリーの糸を保持",
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
        "pseudo.pseudo_critical_strike_chance_for_spells": {
            "#% increased Spell Critical Strike Chance",
            "#% increased Global Critical Strike Chance",
        },
        "pseudo.pseudo_increased_elemental_damage_with_attack_skills": {
            "#% increased Elemental Damage with Attack Skills", "#% increased Elemental Damage",
        },
        "pseudo.pseudo_increased_burning_damage": {
            "#% increased Burning Damage", "#% increased Fire Damage", "#% increased Elemental Damage",
        },
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
    trade_base_type: str | None = None,
) -> tuple[TradeStatFilter, ...]:
    if preset not in TRADE_PRESETS:
        raise ValueError(f"未対応の検索プリセットです: {preset}")
    if preset == PRESET_BASE:
        if PRESET_BASE not in available_trade_presets(item):
            raise ValueError("このアイテムはクラフトベース検索の対象外です。")
        return _decorate_filters(item, _base_item_filters(item, trade_base_type))
    if item.category == "gem":
        return _gem_filters(item, trade_base_type)
    if item.category == "invitation":
        return ()
    entries = _trade_stat_entries()
    resolved: list[TradeStatFilter] = []
    unique_item = _is_unique(item)
    for modifier in item.modifiers:
        if modifier.ref == "Allocates #" and modifier.oils:
            talisman = "talisman" in item.item_class.casefold() or "タリスマン" in item.item_class
            modifiable_amulet = (
                item.category == "accessory" and not talisman
                and "corrupted" not in item.flags and "mirrored" not in item.flags
            )
            if modifiable_amulet and not any(oil in {12, 13} for oil in modifier.oils):
                # Awakened同様、付け直しやすい安価なAnointmentは候補自体を隠す。
                continue
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
            if modifier.stat_id and str(entry.get("id")) == modifier.stat_id:
                candidates.append(entry)
                continue
            candidate = str(entry.get("text", ""))
            comparable = candidate.replace(" (ローカル)", "")
            if _normalized_stat_text(comparable) == source:
                candidates.append(entry)
        if not candidates:
            continue
        if modifier.stat_id:
            exact_candidates = [
                entry for entry in candidates
                if str(entry.get("id")) == modifier.stat_id
            ]
            if exact_candidates:
                # 日本語Trade APIには同じ表示テンプレートを持つ別statがある。
                # メタデータでIDを確定できた場合は曖昧候補を増やさない。
                candidates = exact_candidates
        if item.category == "weapon" and len(candidates) > 1:
            local = [entry for entry in candidates if "(ローカル)" in str(entry.get("text", ""))]
            if local:
                candidates = local
        alternatives = len(candidates) > 1
        group_key = f"mod:{len(resolved)}" if alternatives else ""
        for entry in candidates:
            if _aggregated_local_property_stat(item, str(entry["id"])):
                # DPS・APS・クリ率・防御値へ反映済みなので二重条件化しない。
                continue
            value = _value_for_template(modifier.text, str(entry.get("text", "")))
            if value is None:
                value = modifier.values[0] if modifier.values else None
            maximum = None
            if modifier.stat_id == str(entry["id"]):
                metadata, _ = default_metadata_index().match(modifier.text, modifier.kind)
                if metadata is None and modifier.ref:
                    metadata, _ = default_metadata_index().match_ref(
                        modifier.ref, modifier.kind,
                    )
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
                str(entry["id"]), modifier.text, value, modifier.kind,
                modifier.ref == "Allocates #" and (
                    "talisman" in item.item_class.casefold() or "タリスマン" in item.item_class
                ),
                maximum, modifier.ref, modifier.confidence, modifier.inverted,
                option_value=modifier.option_value, option_text=modifier.option_text,
                oils=modifier.oils,
                group_type="count" if alternatives else "and",
                group_key=group_key, group_min=1 if alternatives else None,
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
            option_value=stat_filter.option_value, option_text=stat_filter.option_text,
            oils=stat_filter.oils,
            group_type=stat_filter.group_type, group_key=stat_filter.group_key,
            group_min=stat_filter.group_min,
        )
    enable_unique_rolls = unique_item and len(combined) <= 3
    # ユニーク品はpseudo集約を表示しないため、元の可変Modを消費扱いにしない。
    # 非ユニーク品だけ、pseudoと個別Modの二重表示を避ける。
    consumed_stat_ids = set() if unique_item else _pseudo_consumed_stat_ids(item)
    consumed_refs = {
        modifier.ref for modifier in item.modifiers
        if modifier.stat_id in consumed_stat_ids and modifier.ref
    }
    individual = tuple(
        TradeStatFilter(
            row.stat_id,
            f"{row.text} ({counts[row.stat_id]}行合計)" if counts[row.stat_id] > 1 else row.text,
            row.min_value, row.kind, enable_unique_rolls or row.enabled,
            row.max_value, row.ref, row.confidence, row.inverted,
            option_value=row.option_value, option_text=row.option_text, oils=row.oils,
            group_type=row.group_type, group_key=row.group_key, group_min=row.group_min,
        )
        for row in combined.values()
        if row.stat_id not in consumed_stat_ids and not (not unique_item and row.ref in consumed_refs)
    )
    if unique_item:
        special_properties = tuple(
            row for row in _initial_property_filters(item, trade_base_type)
            if row.stat_id in {"property.base_percentile", "property.block", "property.memory_strands"}
        )
        return _decorate_filters(
            item, special_properties + individual + _item_detail_filters(item)
            + _unique_exception_filters(item) + _special_content_filters(item), True,
        )
    filters = (
        tuple(_initial_property_filters(item, trade_base_type) + _gear_pseudo_filters(item))
        + individual + _item_detail_filters(item) + _empty_affix_filters(item)
        + _special_content_filters(item)
    )
    decorated = list(_decorate_filters(item, filters))
    if item.category in {"flask", "tincture"}:
        used_enkindling = any(
            modifier.ref == "Gains no Charges during Flask Effect" for modifier in item.modifiers
        )
        if item.category == "flask" and not used_enkindling:
            decorated = [row for row in decorated if row.kind != "enchant"]
        has_recovery = any(modifier.ref == "#% increased Charge Recovery" for modifier in item.modifiers)
        has_effect = any(modifier.ref == "#% increased effect" for modifier in item.modifiers)
        if item.rarity.casefold() in {"magic", "マジック"} and has_recovery and not has_effect:
            decorated.append(TradeStatFilter(
                "explicit.stat_2448920197", "効果増加hybrid Modを除外", None,
                "flask hybrid", True, group_type="not", group_key="flask-effect",
                selection_reason="Charge Recovery単独品を検索",
            ))
    special_name = f"{item.name} {item.base_type}".casefold()
    if "chronicle of atzoatl" in special_name or "アトゾアトルの年代記" in special_name:
        valuable_rooms = {
            "Has Room: Apex of Atzoatl", "Has Room: Locus of Corruption (Tier 3)",
            "Has Room: Doryani's Institute (Tier 3)", "Has Room: Apex of Ascension (Tier 3)",
        }
        decorated = [row for row in decorated if not (row.ref and "(Tier 1)" in row.ref)]
        decorated = [replace(
            row, enabled=True, selection_reason="Atzoatlの主要Tier 3部屋"
        ) if row.ref in valuable_rooms else row for row in decorated]
    if "mirrored tablet" in special_name or "ミラーされたタブレット" in special_name:
        premium = ("Reflection of Kalandra", "Reflection of the Sun", "Reflection of Paradise", "Reflection of Angling")
        decorated = [row for row in decorated if not (
            row.ref and row.ref.startswith("Reflection of ")
            and row.read_value is not None and row.read_value < 8
            and not any(name in row.ref for name in premium)
        )]
        decorated = [replace(
            row, enabled=True, selection_reason="高価値Reflection"
        ) if row.ref and any(name in row.ref for name in premium) else row for row in decorated]
    if item.category == "cluster_jewel":
        adjusted = []
        for row in decorated:
            if row.ref == "# Added Passive Skills are Jewel Sockets":
                continue
            if row.ref == "Adds # Passive Skills" and row.read_value is not None:
                value = row.read_value
                minimum, maximum = row.min_value, row.max_value
                if value == 4:
                    minimum, maximum = None, 5.0
                elif value == 5:
                    minimum, maximum = 5.0, 5.0
                elif value in {3, 6, 10, 11, 12}:
                    minimum, maximum = value, None
                adjusted.append(replace(
                    row, min_value=minimum, max_value=maximum, enabled=True,
                    selection_reason="Cluster Jewelの最適Passive数へ正規化",
                ))
            else:
                adjusted.append(row)
        decorated = adjusted
    if uses_dedicated_exact_preset(item):
        decorated = list(_apply_dedicated_exact_rules(item, tuple(decorated)))
        existing_ids = {row.stat_id for row in decorated}
        decorated.extend(
            row for row in _dedicated_exact_identity_filters(item)
            if row.stat_id not in existing_ids
        )
    return tuple(decorated)


def build_search_query(
    item: ParsedItem, trade_base_type: str | None = None,
    stat_filters: tuple[TradeStatFilter, ...] = (),
    trade_status: str = "instant",
    trade_name: str | None = None,
    preset: str = PRESET_FINISHED,
    trade_currency: str = "any",
    include_corrupted: bool | str | None = None,
    include_split: bool | None = None,
    include_mirrored: bool | None = None,
    trade_discriminator: str | None = None,
    listed_within: str = "any",
    magic_exact: bool = False,
    exact_base_type: bool = True,
    item_level_min: int | None = None,
    item_level_max: int | None = None,
    gem_level_min: int | None = None,
    quality_min: int | None = None,
    links_min: int | None = None,
    include_unidentified: bool | None = None,
    include_veiled: bool | None = None,
    include_foil: bool | None = None,
) -> dict:
    if trade_status not in TRADE_STATUS_OPTIONS:
        raise ValueError(f"未対応の取引方式です: {trade_status}")
    if preset not in TRADE_PRESETS:
        raise ValueError(f"未対応の検索プリセットです: {preset}")
    if trade_currency not in TRADE_CURRENCY_OPTIONS:
        raise ValueError(f"未対応の価格通貨です: {trade_currency}")
    if listed_within not in LISTED_WITHIN_OPTIONS:
        raise ValueError(f"未対応の出品期間です: {listed_within}")
    if item_level_min is not None and not 1 <= item_level_min <= 100:
        raise ValueError("アイテムレベルは1～100で指定してください。")
    if item_level_max is not None and not 1 <= item_level_max <= 100:
        raise ValueError("アイテムレベルは1～100で指定してください。")
    if item_level_min is not None and item_level_max is not None and item_level_min > item_level_max:
        raise ValueError("アイテムレベルの最小値は最大値以下にしてください。")
    if gem_level_min is not None and not 1 <= gem_level_min <= 40:
        raise ValueError("ジェムレベルは1～40で指定してください。")
    if quality_min is not None and not 0 <= quality_min <= 100:
        raise ValueError("品質は0～100で指定してください。")
    if links_min is not None and not 1 <= links_min <= 6:
        raise ValueError("リンク数は1～6で指定してください。")
    if preset == PRESET_BASE and PRESET_BASE not in available_trade_presets(item):
        raise ValueError("このアイテムはクラフトベース検索の対象外です。")
    corruption_mode_explicit = include_corrupted is not None
    if include_corrupted is None:
        include_corrupted = "corrupted" in item.flags
    if include_corrupted not in {False, True, "only"}:
        raise ValueError(f"未対応のコラプト条件です: {include_corrupted}")
    craftable = (
        not _is_unique(item)
        and item.category not in {"gem", "flask", "currency", "divination_card", "captured_beast"}
    )
    if include_split is None:
        has_special_state = (
            "corrupted" in item.flags
            or "mirrored" in item.flags
            or "synthesised" in item.flags
            or any(flag.startswith("influence:") for flag in item.flags)
            or any(modifier.kind == "fractured" for modifier in item.modifiers)
        )
        include_split = "split" in item.flags or not (craftable and not has_special_state)
    if include_mirrored is None:
        include_mirrored = "mirrored" in item.flags or not (
            craftable and "corrupted" not in item.flags
        )
    base_type = _normalize_trade_base_type(trade_base_type or item.base_type)
    gem_info = gem_metadata(base_type) if item.category == "gem" else {}
    query_type: str | dict = str(gem_info.get("trade_type") or base_type)
    if gem_info.get("discriminator"):
        query_type = {"option": query_type, "discriminator": gem_info["discriminator"]}
    query: dict = {
        "status": {"option": TRADE_STATUS_OPTIONS[trade_status]},
        "stats": [{"type": "and", "filters": []}],
        "filters": {},
    }
    if exact_base_type and not _is_generic_map_copy_type(item, base_type):
        query["type"] = query_type
    currency_option = TRADE_CURRENCY_OPTIONS[trade_currency]
    if currency_option is not None:
        query["filters"]["trade_filters"] = {
            "filters": {"price": {"option": currency_option}}
        }
    listed_option = LISTED_WITHIN_OPTIONS[listed_within]
    if listed_option is not None:
        query["filters"].setdefault("trade_filters", {"filters": {}})["filters"]["indexed"] = {
            "option": listed_option
        }
    if _is_unique(item) and trade_name and trade_name.strip():
        query["name"] = ({"option": trade_name.strip(), "discriminator": trade_discriminator}
                         if trade_discriminator else trade_name.strip())
    if include_unidentified is None:
        include_unidentified = _is_unique(item) and "unidentified" in item.flags
    if include_unidentified:
        query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]["identified"] = {"option": "false"}
    if include_veiled is None:
        include_veiled = "veiled" in item.flags
    if item.category == "gem" and include_corrupted != True:
        misc = query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
        misc["corrupted"] = {
            "option": "true" if include_corrupted == "only" else "false"
        }
    if _is_unique(item) and item.item_level is not None and trade_name:
        lowered_name = trade_name.casefold()
        misc = query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
        if "unidentified" in item.flags and lowered_name in {"watcher's eye", "ウォッチャーズアイ"}:
            misc["ilvl"] = {"min": item.item_level}
        elif item.item_level >= 75 and any(
            token in lowered_name for token in ("agnerod", "アグネロッド")
        ):
            normalized = 82 if item.item_level >= 82 else 80 if item.item_level >= 80 else 78 if item.item_level >= 78 else 75
            misc["ilvl"] = {"min": normalized}
    rarity = item.rarity.lower()
    if preset == PRESET_BASE:
        rarity_option = "magic" if magic_exact else "nonunique"
    elif _is_unique(item):
        rarity_option = "unique"
    elif rarity in {"ノーマル", "normal", "マジック", "magic", "レア", "rare"}:
        # AwakenedのExact/Pseudoはいずれも、Adorned用Jewelを除き
        # 現在のrarityではなく「ユニーク以外」を比較対象にする。
        rarity_option = "nonunique"
        if (item.category in {"jewel", "abyss_jewel"}
                and rarity in {"マジック", "magic"}):
            rarity_option = "magic"
    else:
        rarity_option = None
    if include_foil is None:
        include_foil = "foil" in item.flags
    if include_foil:
        rarity_option = "uniquefoil"
    if rarity_option and item.category != "captured_beast":
        query["filters"]["type_filters"] = {"filters": {"rarity": {"option": rarity_option}}}
    if not exact_base_type:
        category = item_class_trade_category(item.item_class)
        if category is None:
            raise ValueError("このアイテムクラスではベースを限定しない検索を利用できません。")
        type_filters = query["filters"].setdefault("type_filters", {"filters": {}})["filters"]
        type_filters["category"] = {"option": category}
    if preset == PRESET_BASE:
        misc = query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
        if include_corrupted != True:
            misc["corrupted"] = {
                "option": "true" if include_corrupted == "only" else "false"
            }
        misc["mirrored"] = {"option": "false"}
        misc["fractured_item"] = {"option": "true" if any(
            modifier.kind == "fractured" for modifier in item.modifiers
        ) else "false"}
        misc["synthesised_item"] = {
            "option": "true" if "synthesised" in item.flags else "false"
        }
        if not include_split:
            misc["split"] = {"option": "false"}
    elif (item.category in {"weapon", "armour", "accessory", "cluster_jewel", "jewel", "abyss_jewel"}
          or uses_dedicated_exact_preset(item)):
        misc = query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
        stateful = item.category not in {
            "gem", "captured_beast", "currency", "divination_card", "invitation",
        }
        if stateful and include_corrupted != True:
            misc["corrupted"] = {
                "option": "true" if include_corrupted == "only" else "false"
            }
        if stateful and "mirrored" in item.flags:
            misc["mirrored"] = {"option": "true"}
        if stateful and not include_split:
            misc["split"] = {"option": "false"}
        if (item.category in {"weapon", "armour", "accessory", "cluster_jewel", "jewel", "abyss_jewel"}
                and "foulborn" not in item.flags):
            misc["foulborn_item"] = {"option": "false"}
        if "searing_item" in item.flags:
            misc["searing_item"] = {"option": "true"}
        if "tangled_item" in item.flags:
            misc["tangled_item"] = {"option": "true"}
        if (not corruption_mode_explicit
                and item.category in {"jewel", "abyss_jewel"}
                and rarity in {"magic", "マジック"}):
            misc["corrupted"] = {
                "option": "true" if "corrupted" in item.flags else "false"
            }
    if corruption_mode_explicit and include_corrupted != True:
        misc = query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
        misc["corrupted"] = {
            "option": "true" if include_corrupted == "only" else "false"
        }
    misc = query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
    if include_mirrored:
        misc.pop("mirrored", None)
    else:
        misc["mirrored"] = {"option": "false"}
    # Awakened準拠: Veiled全般のmisc条件ではなく、詳細コピーで読み取った
    # Veiled Mod名に対応するstat IDをAND条件として検索する。
    stat_filters = tuple(row for row in stat_filters if row.kind != "veiled")
    if include_veiled:
        seen_veiled_ids: set[str] = set()
        veiled_filters = []
        for modifier in item.modifiers:
            if (modifier.kind != "veiled" and modifier.generation != "veiled"):
                continue
            if not modifier.stat_id or modifier.stat_id in seen_veiled_ids:
                continue
            seen_veiled_ids.add(modifier.stat_id)
            veiled_filters.append(TradeStatFilter(
                modifier.stat_id, modifier.ref or modifier.text, None,
                "veiled", True, ref=modifier.ref,
                confidence=modifier.confidence,
                selection_reason="読み取ったVeiled Mod種別と一致",
            ))
        stat_filters += tuple(veiled_filters)
    stat_groups: dict[tuple[str, str], dict] = {("and", ""): query["stats"][0]}
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
        if stat_filter.stat_id == "property.gem_imbued":
            query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]["gem_imbued"] = {
                "option": "true"
            }
            continue
        if stat_filter.stat_id in {"property.map_blighted", "property.map_uberblighted"}:
            filter_name = ("map_blighted" if stat_filter.stat_id == "property.map_blighted"
                           else "map_uberblighted")
            query["filters"].setdefault("map_filters", {"filters": {}})["filters"][filter_name] = {
                "option": "true"
            }
            continue
        if stat_filter.stat_id == "property.map_completion_reward":
            query["filters"].setdefault("map_filters", {"filters": {}})["filters"]["map_completion_reward"] = {
                "option": stat_filter.option_value
            }
            continue
        if stat_filter.stat_id == "property.heist_objective_value":
            query["filters"].setdefault("heist_filters", {"filters": {}})["filters"]["heist_objective_value"] = {
                "option": stat_filter.option_value
            }
            continue
        property_target = _PROPERTY_FILTERS.get(stat_filter.stat_id)
        if property_target:
            group, name = property_target
            minimum = stat_filter.min_value
            if minimum is not None and group == "socket_filters":
                minimum = int(minimum)
            value = {"min": minimum} if minimum is not None else {}
            if stat_filter.max_value is not None:
                value["max"] = (int(stat_filter.max_value)
                                if group == "socket_filters" else stat_filter.max_value)
            query["filters"].setdefault(group, {"filters": {}})["filters"][name] = value
            continue
        value = {}
        if stat_filter.option_value is not None:
            value["option"] = stat_filter.option_value
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
        group_type = stat_filter.group_type if stat_filter.group_type in {"and", "not", "count"} else "and"
        group_key = (group_type, stat_filter.group_key)
        group = stat_groups.get(group_key)
        if group is None:
            group = {"type": group_type, "filters": []}
            if group_type == "count":
                group["value"] = {"min": stat_filter.group_min or 1}
            query["stats"].append(group)
            stat_groups[group_key] = group
        group["filters"].append({"id": stat_filter.stat_id, "value": value})
    if item_level_min is not None:
        level_filter = {"min": item_level_min}
        if item_level_max is not None:
            level_filter["max"] = item_level_max
        query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]["ilvl"] = level_filter
    if gem_level_min is not None:
        query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]["gem_level"] = {
            "min": gem_level_min
        }
    if quality_min is not None:
        query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]["quality"] = {
            "min": quality_min
        }
    if links_min is not None:
        query["filters"].setdefault("socket_filters", {"filters": {}})["filters"]["links"] = {
            "min": links_min
        }
    return {"query": query, "sort": {"price": "asc"}}


def _normalize_trade_base_type(value: str) -> str:
    """品質付き通常名の表示接頭辞を、公式Tradeのベース名から除く。"""
    normalized = value.strip()
    normalized = re.sub(r"^Superior\s+", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^上質な[\s　]*", "", normalized)
    return normalized.strip()


def _is_generic_map_copy_type(item: ParsedItem, base_type: str) -> bool:
    """詳細コピーの汎用Map表記を、公式Tradeのベース名として送らない。"""
    if item.category != "map":
        return False
    return bool(re.fullmatch(
        r"(?:(?:Blighted|Blight-ravaged)\s+)?Map\s*[（(]\s*Tier\s*\d+\s*[）)]",
        base_type.strip(), flags=re.IGNORECASE,
    ))


def _contains_japanese_text(value: object) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", str(value)))


def _require_english_search_identity(payload: dict) -> None:
    """通常検索へ表示用の日本語名が混入するのをAPI送信前に防ぐ。"""
    query = payload.get("query") or {}
    query_type = query.get("type", "")
    query_type_text = (
        query_type.get("option", "") if isinstance(query_type, dict) else query_type
    )
    query_name = query.get("name", "")
    query_name_text = (
        query_name.get("option", "") if isinstance(query_name, dict) else query_name
    )
    if _contains_japanese_text(query_type_text) or _contains_japanese_text(query_name_text):
        raise TradeApiError(
            "英語のアイテム名またはベースタイプを取得できませんでした。"
            "アイテムへカーソルを合わせ、Alt+Dでもう一度読み取ってください。"
        )


def search_prices(
    item: ParsedItem, trade_base_type: str | None = None, league: str | None = None,
    stat_filters: tuple[TradeStatFilter, ...] = (),
    trade_status: str = "instant",
    trade_name: str | None = None,
    preset: str = PRESET_FINISHED,
    trade_currency: str = "any",
    include_corrupted: bool | str | None = None,
    include_split: bool | None = None,
    include_mirrored: bool | None = None,
    trade_discriminator: str | None = None,
    listed_within: str = "any",
    magic_exact: bool = False,
    exact_base_type: bool = True,
    item_level_min: int | None = None,
    item_level_max: int | None = None,
    gem_level_min: int | None = None,
    quality_min: int | None = None,
    links_min: int | None = None,
    include_unidentified: bool | None = None,
    include_veiled: bool | None = None,
    include_foil: bool | None = None,
) -> PriceResult:
    league = league or active_pc_league()
    if (item.rarity.casefold() in {"magic", "マジック"}
            and trade_base_type and item.name == item.base_type):
        trade_base_type = resolve_official_base_type(trade_base_type)
    payload = build_search_query(
        item, trade_base_type, stat_filters, trade_status, trade_name, preset,
        trade_currency, include_corrupted, include_split, include_mirrored,
        trade_discriminator, listed_within,
        magic_exact, exact_base_type, item_level_min, item_level_max, gem_level_min,
        quality_min,
        links_min,
        include_unidentified, include_veiled, include_foil,
    )
    _require_english_search_identity(payload)
    search_url = f"{API_ROOT}/search/{quote(league, safe='')}"
    _trade_log(
        f"search: league={league!r} preset={preset!r} trade_status={trade_status!r} "
        f"api_status={TRADE_STATUS_OPTIONS[trade_status]!r} "
        f"trade_currency={trade_currency!r} "
        f"listed_within={listed_within!r} "
        f"api_currency={TRADE_CURRENCY_OPTIONS[trade_currency]!r} url={search_url}"
    )
    _trade_log_payload(payload)
    search, headers, search_cached = _cached_request_json(
        search_url, payload,
    )
    query_id = str(search.get("id", ""))
    ids = list(search.get("result", ()))
    _trade_log(f"search response: query_id={query_id!r} candidates={len(ids)}")
    if not query_id:
        _trade_log("search failed: response did not contain a query ID")
        raise TradeApiError("検索IDを取得できませんでした。")
    listings: list[PriceListing] = []
    fetch_cached = False
    if ids:
        fetch_ids = ",".join(ids[:10])
        fetch_url = f"{API_ROOT}/fetch/{fetch_ids}?query={quote(query_id)}"
        _trade_log(f"request: GET {fetch_url} (first {min(len(ids), 10)} candidates)")
        fetched, _, fetch_cached = _cached_request_json(fetch_url)
        for row in fetched.get("result", ()):
            listing = row.get("listing", {})
            fetched_item = row.get("item", {})
            price = listing.get("price") or {}
            if price.get("amount") is None or not price.get("currency"):
                continue
            account = (listing.get("account") or {}).get("name", "")
            fetched_properties = fetched_item.get("properties") or ()

            def property_number(*names: str) -> int | None:
                wanted = {name.casefold() for name in names}
                for prop in fetched_properties:
                    if str(prop.get("name", "")).casefold() not in wanted:
                        continue
                    values = prop.get("values") or ()
                    if not values:
                        continue
                    match = re.search(r"-?\d+", str(values[0][0]))
                    if match:
                        return int(match.group())
                return None

            listings.append(PriceListing(
                float(price["amount"]), str(price["currency"]), str(account),
                str(fetched_item.get("name", "")), str(fetched_item.get("baseType", "")),
                str(listing.get("indexed", "")),
                int(fetched_item["ilvl"]) if fetched_item.get("ilvl") is not None else None,
                property_number("Level", "レベル", "Gem Level", "ジェムレベル"),
                property_number("Quality", "品質"),
                int(fetched_item["stackSize"]) if fetched_item.get("stackSize") is not None else None,
            ))
    rate_limit = headers.get("X-Rate-Limit-Ip-State", "") if headers else ""
    _trade_log(
        f"completed: query_id={query_id!r} candidates={len(ids)} "
        f"priced_listings={len(listings)} rate_limit={rate_limit!r}"
    )
    # 検索IDはAPIホストごとに管理されるため、www側のIDをjp側へ渡せない。
    # 日本語アイテム文から得た名称を使った検索JSONをURLへ埋め込み、
    # 日本語Trade画面自身に検索状態を読み込ませる。
    web_payload = json.loads(json.dumps(payload))
    web_query = web_payload["query"]
    localized_type = _normalize_trade_base_type(item.base_type)
    if localized_type:
        if isinstance(web_query.get("type"), dict):
            web_query["type"]["option"] = localized_type
        else:
            web_query["type"] = localized_type
    localized_name = item.name.strip()
    if "name" in web_query and localized_name:
        if isinstance(web_query["name"], dict):
            web_query["name"]["option"] = localized_name
        else:
            web_query["name"] = localized_name
    encoded_query = quote(
        json.dumps(web_payload, ensure_ascii=False, separators=(",", ":")),
        safe="",
    )
    web_url = (
        f"https://jp.pathofexile.com/trade/search/{quote(league, safe='')}"
        f"?q={encoded_query}"
    )
    return PriceResult(
        league, query_id, len(ids), tuple(listings), rate_limit,
        web_url, search_cached or fetch_cached,
    )
