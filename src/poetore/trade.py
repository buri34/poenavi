from __future__ import annotations

from dataclasses import dataclass, replace
from collections import OrderedDict
import json
import math
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
    pseudo_definitions, pseudo_relations, unique_fixed_stats, unique_icon_url,
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
    "Quivers": "accessory.quiver", "矢筒": "accessory.quiver",
    "Jewels": "jewel.base", "ジュエル": "jewel.base",
    "Abyss Jewels": "jewel.abyss", "アビスジュエル": "jewel.abyss",
}


def item_class_trade_category(item_class: str) -> str | None:
    return _ITEM_CLASS_TRADE_CATEGORIES.get(item_class.strip())
CONSUMABLE_CRAFTABLE_CATEGORIES = {
    "map", "heist_blueprint", "heist_contract", "invitation",
    "memory_line", "expedition_logbook",
}
NON_CRAFTABLE_CATEGORIES = {"gem", "flask", "currency", "divination_card", "corpse"}
DEDICATED_EXACT_CATEGORIES = {
    "gem", "captured_beast", "map", "memory_line", "invitation",
    "heist_contract", "heist_blueprint", "charm", "cluster_jewel", "corpse",
}
PRESET_FINISHED = "finished"
PRESET_BASE = "base"
TRADE_PRESETS = (PRESET_FINISHED, PRESET_BASE)
_INSCRIBED_ULTIMATUM_NAMES = {
    "inscribed ultimatum", "アルティメイタムの刻印",
}
_JEWEL_AFFIX_CATEGORIES = {"jewel", "abyss_jewel", "cluster_jewel"}
# Experimental bases whose implicits change the normal rare-item 3/3 limits.
# Values come from RePoE's local_maximum_prefixes_allowed_+ /
# local_maximum_suffixes_allowed_+ stats.
_SPECIAL_AFFIX_LIMITS = {
    "cogwork ring": (2, 4),
    "geodesic ring": (4, 2),
    "manifold ring": (4, 1),
    "helical ring": (1, 4),
    "simplex amulet": (1, 2),
    "focused amulet": (2, 1),
}
_INFLUENCE_STATS = {
    "shaper": ("pseudo.pseudo_has_shaper_influence", "Shaper影響"),
    "elder": ("pseudo.pseudo_has_elder_influence", "Elder影響"),
    "crusader": ("pseudo.pseudo_has_crusader_influence", "Crusader影響"),
    "hunter": ("pseudo.pseudo_has_hunter_influence", "Hunter影響"),
    "redeemer": ("pseudo.pseudo_has_redeemer_influence", "Redeemer影響"),
    "warlord": ("pseudo.pseudo_has_warlord_influence", "Warlord影響"),
}
# Awakened stats.ndjson の resolve/select と同じ、アイテム種別で分岐する
# 同名Trade stat。日本語Trade APIでは表示文だけでは区別できない。
_CATEGORY_STAT_OVERRIDES = {
    ("tincture", "explicit", "効果が#%増加する"): "explicit.stat_3529940209",
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

# Allflameの日本語Trade APIで、固定文言中の数字をmin値として送る旧条件が0件、
# 値なし条件が1件以上になることを新旧比較で確認したStatだけを対象にする。
# 出品なしで判定不能、または新旧同数のStatは従来の数値抽出を維持する。
_API_VERIFIED_VALUELESS_FIXED_STAT_IDS = {
    "explicit.stat_1021552211",
    "explicit.stat_1060931694",
    "explicit.stat_1091613629",
    "explicit.stat_1099200124",
    "explicit.stat_1121911611",
    "explicit.stat_1142276332",
    "explicit.stat_1168138239",
    "explicit.stat_130616495",
    "explicit.stat_133804429",
    "explicit.stat_1357409216",
    "explicit.stat_1358422215",
    "explicit.stat_1389615049",
    "explicit.stat_1433144735",
    "explicit.stat_1463929958",
    "explicit.stat_1493090598",
    "explicit.stat_1531241759",
    "explicit.stat_1640259660",
    "explicit.stat_179010262",
    "explicit.stat_181229988",
    "explicit.stat_185598681",
    "explicit.stat_1904031052",
    "explicit.stat_1917661185",
    "explicit.stat_1919069577",
    "explicit.stat_1963540179",
    "explicit.stat_2044840211",
    "explicit.stat_2064503808",
    "explicit.stat_207863952",
    "explicit.stat_224931623",
    "explicit.stat_2295303426",
    "explicit.stat_2384145996",
    "explicit.stat_2439129490",
    "explicit.stat_2501671832",
    "explicit.stat_2517037025",
    "explicit.stat_2554328719",
    "explicit.stat_262773569",
    "explicit.stat_2713909980",
    "explicit.stat_2716882575",
    "explicit.stat_2750004091",
    "explicit.stat_2773026887",
    "explicit.stat_282325999",
    "explicit.stat_285624304",
    "explicit.stat_2878779644|2",
    "explicit.stat_2878779644|3",
    "explicit.stat_2918150296",
    "explicit.stat_2921954092",
    "explicit.stat_2959020308",
    "explicit.stat_3183988184",
    "explicit.stat_3259812992",
    "explicit.stat_3266609002",
    "explicit.stat_3269060224",
    "explicit.stat_328131617",
    "explicit.stat_3339663313",
    "explicit.stat_3345955207",
    "explicit.stat_3362271649",
    "explicit.stat_3423343084",
    "explicit.stat_3525542360",
    "explicit.stat_3598983877",
    "explicit.stat_3616500790",
    "explicit.stat_3714446071",
    "explicit.stat_3768948090",
    "explicit.stat_3772848194",
    "explicit.stat_3778002979",
    "explicit.stat_3797685329",
    "explicit.stat_3844045281",
    "explicit.stat_3910756536",
    "explicit.stat_3938394827",
    "explicit.stat_4077357269",
    "explicit.stat_40907696",
    "explicit.stat_4194606073",
    "explicit.stat_456916387",
    "explicit.stat_5955083",
    "explicit.stat_609019022",
    "explicit.stat_621302497",
    "explicit.stat_637690626",
    "explicit.stat_642457541",
    "explicit.stat_684268017",
    "explicit.stat_708913352",
    "explicit.stat_824024007",
    "explicit.stat_849085925",
    "explicit.stat_877233648",
    "explicit.stat_91505809",
    "explicit.stat_933024928",
    "explicit.stat_940684417",
    "explicit.stat_971937289",
    "explicit.stat_986616727",
    "implicit.stat_1021552211",
    "implicit.stat_1493090598",
    "implicit.stat_1640259660",
    "implicit.stat_1917661185",
    "implicit.stat_2878779644|2",
    "implicit.stat_2918150296",
    "implicit.stat_3811649872",
    "implicit.stat_4282426229",
    "implicit.stat_5955083",
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
_PSEUDO_DEFINITIONS = pseudo_definitions()
_SIMPLE_PSEUDOS = tuple(
    (row["source_ref"], row["stat_id"], row["label"])
    for row in _PSEUDO_DEFINITIONS if not row.get("relational")
)

_RELATIONAL_SOURCE_REFS = {
    row["source_ref"] for row in _PSEUDO_DEFINITIONS if row.get("relational")
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
    listed_times: int = 1
    pricing_method: str = "face_to_face"


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
    decimal: bool = False
    # Awakened同様、集約したproperty/pseudo行にも寄与元Modの高Tierを表示する。
    # Trade APIへは送らない表示専用情報。
    tier_tags: tuple[int, ...] = ()
    hidden_reason: str = ""
    source_texts: tuple[str, ...] = ()
    # source_textsと同じ順序の、検索条件への寄与値と元Mod見出し。
    # Trade APIへは送らないAwakened風の表示専用情報。
    source_contributions: tuple[float | None, ...] = ()
    source_headings: tuple[str, ...] = ()


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
            if listing.pricing_method == "unpriced":
                continue
            grouped.setdefault(listing.currency, []).append(listing.amount)
        return {currency: median(values) for currency, values in grouped.items()}


def _group_price_listings(listings: list[PriceListing]) -> tuple[PriceListing, ...]:
    """Awakened同様、同一出品者の同価格連投を相場サンプル1件へ集約する。"""
    grouped: list[PriceListing] = []
    positions: dict[tuple[str, str, float, str], int] = {}
    for listing in listings:
        key = (
            listing.account, listing.currency, listing.amount,
            listing.pricing_method,
        )
        if not listing.account or key not in positions:
            positions[key] = len(grouped)
            grouped.append(listing)
            continue
        index = positions[key]
        previous = grouped[index]
        stack_size = previous.stack_size
        if stack_size is not None and listing.stack_size is not None:
            stack_size += listing.stack_size
        grouped[index] = replace(
            previous,
            stack_size=stack_size,
            listed_times=previous.listed_times + 1,
        )
    return tuple(grouped)


def apply_search_range(
    filters: tuple[TradeStatFilter, ...], percent: float, item: ParsedItem | None = None,
) -> tuple[TradeStatFilter, ...]:
    """検索値をAwakenedの共通幅設定で再計算する（0～50%）。"""
    if item is not None and item.rarity.casefold() in {"magic", "マジック"} and (
        "mirrored" in item.flags or "corrupted" in item.flags or "unmodifiable" in item.flags
    ):
        percent = 0
    percent = max(0.0, min(float(percent), 50.0)) / 100.0
    adjusted = []
    discrete_socket_stats = {
        "property.sockets",
        "property.links",
    }
    for row in filters:
        if (
            row.read_value is None
            or row.stat_id in discrete_socket_stats
            or (
                item is not None
                and item.category == "cluster_jewel"
                and row.ref == "Adds # Passive Skills"
                and row.read_value in {2, 8}
            )
            or row.option_value is not None
            or row.exact
            or row.inverted
            or row.hidden_reason
            or (
                row.generation == "foulborn"
                and row.roll_min is None and row.roll_max is None
            )
            or (row.min_value is None and row.max_value is None)
        ):
            adjusted.append(row)
            continue
        api_value = row.read_value
        if row.roll_min is not None and row.roll_max is not None:
            delta = abs(row.roll_max - row.roll_min) * percent
        else:
            delta = abs(api_value) * percent
        minimum = row.min_value
        maximum = row.max_value
        if minimum is not None:
            minimum = (
                api_value if percent == 0
                else math.floor(api_value - delta) if not row.decimal
                else api_value - delta
            )
        if maximum is not None:
            maximum = (
                api_value if percent == 0
                else math.ceil(api_value + delta) if not row.decimal
                else api_value + delta
            )
        adjusted.append(replace(row, min_value=minimum, max_value=maximum))
    return tuple(adjusted)


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
            if exc.code == 429:
                try:
                    retry_after = max(0, int(float(exc.headers.get("Retry-After", ""))))
                except (AttributeError, TypeError, ValueError):
                    retry_after = 0
                if retry_after:
                    retry_minutes = max(1, (retry_after + 59) // 60)
                    retry_note = f" 約{retry_minutes}分後に、もう一度検索してください。"
                else:
                    retry_note = " しばらく時間を置いてから、もう一度検索してください。"
                raise TradeApiError(
                    "検索回数が多いため、PoE Trade APIの利用制限に達しました。"
                    f"{retry_note}"
                ) from exc
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
    """Awakened同様、整数statの検索下限は10%緩和後に切り下げる。"""
    return float(math.floor(value * (1 - DEFAULT_SEARCH_RANGE) + 1e-9))


def _relaxed_decimal(value: float) -> float:
    """小数精度を持つproperty用のAwakened互換丸め。"""
    decimals = 2 if abs(value) < 2.3 else 1 if abs(value) < 10 else 0
    scale = 10 ** decimals
    return math.floor((value * (1 - DEFAULT_SEARCH_RANGE) + 1e-9) * scale) / scale


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


def _local_defence_components(item: ParsedItem, defence: str) -> tuple[float, float]:
    """Return local flat and increased defence totals used by Awakened's q20 calculation."""
    flat_refs, increased_refs = _DEFENCE_REFS[defence]
    flat = increased = 0.0
    for modifier in item.modifiers:
        value = modifier.values[0] if modifier.values else 0.0
        if modifier.ref in flat_refs:
            flat += value
        elif modifier.ref in increased_refs:
            increased += value
    return flat, increased


def _defence_at_20_quality(value: float, item: ParsedItem, defence: str) -> float:
    """Reconstruct a defence property at minimum 20% quality like Awakened."""
    quality = _property_value(item, "品質", "Quality") or 0.0
    target_quality = max(20.0, quality)
    flat, increased = _local_defence_components(item, defence)
    quality_multiplier = 1.0 + quality / 100.0
    increased_multiplier = 1.0 + increased / 100.0
    if quality_multiplier == 0.0 or increased_multiplier == 0.0:
        return value
    base = value / quality_multiplier / increased_multiplier - flat
    return (base + flat) * increased_multiplier * (1.0 + target_quality / 100.0)


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
        flat, increased = _local_defence_components(item, defence)
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
        or (quality == 20 and item.category in {"weapon", "armour"}
            and _memory_strands(item) is None)
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


def is_inscribed_ultimatum(item: ParsedItem) -> bool:
    """供物・報酬をTrade API条件へ変換しない名前一致検索品かを返す。"""
    return any(
        value.strip().casefold() in _INSCRIBED_ULTIMATUM_NAMES
        for value in (item.name, item.base_type)
    )


def _apply_dedicated_exact_rules(
    item: ParsedItem, filters: tuple[TradeStatFilter, ...],
) -> tuple[TradeStatFilter, ...]:
    """汎用完成品候補からAwakenedのcreateExactStatFilters相当だけを残す。"""
    keep_modifier_kinds = {
        "pseudo", "fractured", "enchant", "necropolis", "imbued", "craft",
    }
    if (not any(flag.startswith("influence:") for flag in item.flags)
            and not any(mod.kind == "fractured" for mod in item.modifiers)
            and item.category not in {"tincture", "idol"}):
        keep_modifier_kinds.add("implicit")
    rarity = item.rarity.casefold()
    if (rarity in {"magic", "マジック"}
            and item.category not in {
                "map", "heist_contract", "heist_blueprint", "sentinel",
            }):
        keep_modifier_kinds.update({"prefix", "suffix", "explicit"})
    elif rarity in {"rare", "レア"} and item.category == "idol":
        keep_modifier_kinds.update({"prefix", "suffix", "explicit"})
    if item.category == "flask":
        keep_modifier_kinds.add("crafted")
    if item.category in {"map", "invitation"} and not _is_unique(item):
        keep_modifier_kinds.update({"prefix", "suffix", "explicit"})

    property_ids = {
        "property.armour", "property.evasion", "property.energy_shield",
        "property.ward", "property.block", "property.base_percentile",
        "property.memory_strands", "property.quality",
        "property.sockets", "property.links",
    }
    special_kinds = {
        "map", "map pseudo", "map safety", "cluster", "heist", "expedition",
        "special", "sanctum", "flask hybrid", "unique exception",
    }
    result = []
    logbook_faction_seen = False
    logbook_groups = sorted({mod.group for mod in item.modifiers if mod.group is not None})
    first_logbook_group = logbook_groups[0] if logbook_groups else None
    enable_all = item.category in {"memory_line", "sanctum_relic", "charm"}
    blighted_map = _map_blight_state(item) is not None
    for row in filters:
        # AwakenedのcreateExactStatFiltersはBlighted Mapのstat条件を空にし、
        # Map本体のTier・Blighted種別だけをitem filterとして扱う。
        if blighted_map and row.stat_id not in {
            "property.map_tier", "property.map_blighted", "property.map_uberblighted",
            "property.map_completion_reward",
        }:
            continue
        if row.kind in keep_modifier_kinds or row.kind in special_kinds:
            enabled = row.enabled
            if enable_all or (
                item.category != "map"
                and row.kind not in {"prefix", "suffix", "explicit"}
            ):
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
            is_valdo = item.category == "map" and item.base_type.casefold() == "valdo map"
            if is_valdo and row.kind in {"prefix", "suffix", "explicit"}:
                enabled = True
            if item.category == "map" and not is_valdo and row.kind in {
                "prefix", "suffix", "explicit", "map pseudo",
            }:
                enabled = False
            if item.category == "invitation" and row.kind in {
                "prefix", "suffix", "explicit", "map", "map pseudo",
            }:
                enabled = False
            if item.category == "cluster_jewel":
                source = f"{row.ref or ''} {row.text}".casefold()
                if "added passive skill is" in source or "追加されたパッシブスキル" in source:
                    enabled = True
            if item.category == "expedition_logbook" and row.stat_id.startswith(
                "pseudo.pseudo_logbook_faction_"
            ):
                enabled = not logbook_faction_seen
                logbook_faction_seen = True
            if item.category == "expedition_logbook" and row.selection_reason.startswith(
                "logbook-area:"
            ):
                enabled = row.selection_reason == f"logbook-area:{first_logbook_group}"
            result.append(replace(row, enabled=enabled))
        elif row.stat_id in property_ids:
            if item.category == "armour" and row.stat_id in {
                "property.armour", "property.evasion", "property.energy_shield",
                "property.ward", "property.block",
            }:
                result.append(replace(row, enabled=False))
            elif row.stat_id == "property.base_percentile":
                result.append(replace(row, enabled=True))
            else:
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
        elif item.category not in {
            "jewel", "abyss_jewel", "heist_blueprint", "heist_contract",
            "memory_line", "sanctum_relic", "charm", "idol", "expedition_logbook",
        }:
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
        # 3.29の詳細コピー本文には、Trade APIの表示用補足
        # 「(ローカル)」が付かない。パーサーが確定したstat IDを優先し、
        # IDがない古いコピー形式だけ正規化文字列で照合する。
        candidates = (
            [
                entry for entry in entries
                if entry.get("type") == api_kind
                and str(entry.get("id")) == modifier.stat_id
            ]
            if modifier.stat_id else []
        )
        if not candidates:
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
        entry_text = str(entry.get("text", ""))
        value = _value_for_template(modifier.text, entry_text)
        if value is None and (
            "#" in entry_text
            or modifier.option_value is not None
            or str(entry["id"]) not in _API_VERIFIED_VALUELESS_FIXED_STAT_IDS
        ):
            value = modifier.values[0] if modifier.values else None
        enabled = modifier.kind not in {"prefix", "suffix"} or modifier.tier in {1, 2}
        filters.append(TradeStatFilter(
            str(entry["id"]), modifier.text, value,
            (modifier.kind if modifier.kind not in {"prefix", "suffix"}
             else f"T{modifier.tier}" if modifier.tier else "explicit"), enabled,
        ))
    base_property_ids = {
        "property.total_dps", "property.physical_dps", "property.elemental_dps",
        "property.aps", "property.crit",
        "property.armour", "property.evasion", "property.energy_shield",
        "property.ward", "property.block", "property.base_percentile",
        "property.memory_strands",
    }
    special_properties = tuple(
        replace(
            row,
            enabled=(
                True if row.stat_id == "property.base_percentile"
                else row.enabled if row.stat_id == "property.memory_strands"
                else False
            ),
        )
        for row in _initial_property_filters(item, trade_base_type)
        if row.stat_id in base_property_ids
    )
    return tuple(filters) + special_properties + _item_detail_filters(item)


def _socket_summary(item: ParsedItem) -> tuple[int, int]:
    text = item.properties.get("ソケット") or item.properties.get("Sockets") or ""
    groups = re.findall(r"[RGBW](?:-[RGBW])*", text.upper())
    sizes = [len(group.split("-")) for group in groups]
    total = sum(sizes)
    linked = max(sizes, default=0)
    return total, linked


def _item_detail_filters(item: ParsedItem) -> tuple[TradeStatFilter, ...]:
    filters: list[TradeStatFilter] = []
    quality = _property_value(item, "品質", "Quality")
    if quality is not None and quality >= 20:
        filters.append(TradeStatFilter(
            "property.quality", "品質", quality, "property", quality > 20,
        ))
    sockets, links = _socket_summary(item)
    if sockets:
        filters.append(TradeStatFilter(
            "property.sockets", "ソケット数", float(sockets), "socket", sockets >= 6,
        ))
    if links > 1:
        filters.append(TradeStatFilter(
            "property.links", "最大リンク数", float(links), "socket", True,
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
                filters.append(TradeStatFilter(
                    stat_id, label, value, "map", stat_id == "property.map_tier",
                ))
        for stat_id, label, labels in (
            ("pseudo.pseudo_map_more_map_drops", "追加マップ", ("追加マップ", "More Maps")),
            ("pseudo.pseudo_map_more_scarab_drops", "追加スカラベ", ("追加スカラベ", "More Scarabs")),
            ("pseudo.pseudo_map_more_currency_drops", "追加カレンシー", ("追加カレンシー", "More Currency")),
            ("pseudo.pseudo_map_more_card_drops", "追加占いカード", ("追加占いカード", "More Divination Cards")),
        ):
            value = _property_value(item, *labels)
            if value is not None:
                filters.append(TradeStatFilter(stat_id, label, value, "map pseudo", False))
        blight_state = _map_blight_state(item)
        if blight_state == "ravaged":
            filters.append(TradeStatFilter("property.map_uberblighted", "ブライトに破壊されたマップ", None, "map", True))
        elif blight_state == "blighted":
            filters.append(TradeStatFilter("property.map_blighted", "ブライトマップ", None, "map", True))
        completion = item.properties.get("マップ完了報酬") or item.properties.get("Map Completion Reward")
        if not completion and item.base_type.casefold() == "valdo map":
            completion = item.properties.get("報酬") or item.properties.get("Reward")
            if completion:
                completion = re.sub(r"^(?:フォイル|Foil)\s+", "", completion).strip()
        if completion:
            localized_completion = completion
            completion = _english_trade_item_name(localized_completion) or localized_completion
            filters.append(TradeStatFilter(
                "property.map_completion_reward", f"完了報酬: {localized_completion}",
                None, "map", True, option_value=completion,
                option_text=localized_completion,
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
        # 現行日本語コピーは `情報を聞いた区画: 1/4`。
        # Awakenedと同じく分子（公開済み区画数）をTradeの最小値へ使う。
        wings = _property_value(
            item, "情報を聞いた区画", "情報を聞いた区画数", "Wings Revealed",
        )
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
        # AwakenedはBlueprintの必要Jobを検索条件にせず、Contractだけを扱う。
        for line in item.raw_text.splitlines() if item.category == "heist_contract" else ():
            match = re.search(r"(?:level|レベル)\s*(\d+)", line, re.I)
            if not match:
                continue
            lowered = line.casefold()
            stat_id = next((stat for name, stat in job_names.items() if name in lowered), None)
            if stat_id:
                filters.append(TradeStatFilter(stat_id, line.strip(), float(match.group(1)), "heist", True))
                break
        if re.search(
            r"(?:Heist Target|依頼書目標|ハイスト目標).*?(?:Priceless|プライスレス)",
            item.raw_text, re.I,
        ):
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


def _affix_limits(
    item: ParsedItem, trade_base_type: str | None = None,
) -> tuple[int, int] | None:
    """Return the maximum prefix/suffix counts for craftable item rarities."""
    rarity = item.rarity.casefold()
    if rarity in {"magic", "マジック"}:
        return (1, 1)
    if rarity not in {"rare", "レア"}:
        return None
    if item.category in _JEWEL_AFFIX_CATEGORIES:
        return (2, 2)
    identity = (trade_base_type or item.base_type or item.name).strip().casefold()
    return _SPECIAL_AFFIX_LIMITS.get(identity, (3, 3))


def _empty_affix_filters(
    item: ParsedItem, trade_base_type: str | None = None,
) -> tuple[TradeStatFilter, ...]:
    # The official empty-affix pseudos are only useful for rare-item crafting.
    # Corrupted and mirrored items cannot have an affix added, so do not imply
    # that their mathematically unused slots are craftable.
    if (
        item.rarity.casefold() not in {"rare", "レア"}
        or "corrupted" in item.flags
        or "mirrored" in item.flags
    ):
        return ()
    limits = _affix_limits(item, trade_base_type)
    if limits is None:
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
    for affix, maximum, stat_id, label in (
        ("prefix", limits[0], "pseudo.pseudo_number_of_empty_prefix_mods", "空きPrefix枠"),
        ("suffix", limits[1], "pseudo.pseudo_number_of_empty_suffix_mods", "空きSuffix枠"),
    ):
        empty = max(0, maximum - len(groups[affix]))
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
        if pdps and _physical_dps_is_important(item) and (not total or pdps / total >= 0.67):
            filters.append(TradeStatFilter(
                "property.physical_dps", "物理DPS", _relaxed(pdps), "property", True,
            ))
        if edps and (not total or edps / total >= 0.67):
            filters.append(TradeStatFilter(
                "property.elemental_dps", "元素DPS", _relaxed(edps), "property", True,
            ))
        aps = _property_value(item, "秒間アタック回数", "Attacks per Second")
        if aps is not None:
            filters.append(TradeStatFilter(
                "property.aps", "秒間アタック回数", _relaxed_decimal(aps), "property", False,
            ))
        crit = _property_value(item, "クリティカル率", "Critical Strike Chance")
        if crit is not None:
            filters.append(TradeStatFilter(
                "property.crit", "クリティカル率", _relaxed_decimal(crit), "property", False,
            ))
    elif item.category == "armour":
        block = _property_value(item, "ブロック率", "Chance to Block")
        if block is not None:
            filters.append(TradeStatFilter(
                "property.block", "ブロック率", _relaxed(block), "property", True,
            ))
        defenses = [
            ("property.armour", "アーマー", _property_value(item, "アーマー", "防具", "Armour")),
            ("property.evasion", "回避力", _property_value(item, "回避力", "Evasion Rating")),
            ("property.energy_shield", "エナジーシールド", _property_value(item, "エナジーシールド", "Energy Shield")),
            ("property.ward", "Ward", _property_value(item, "Ward")),
        ]
        defence_keys = {
            "property.armour": "ar",
            "property.evasion": "ev",
            "property.energy_shield": "es",
            "property.ward": "ward",
        }
        present = [
            (stat_id, text, _defence_at_20_quality(value, item, defence_keys[stat_id]))
            for stat_id, text, value in defenses if value
        ]
        for stat_id, text, value in present:
            filters.append(TradeStatFilter(stat_id, text, _relaxed(value), "property", True))
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
_jp_item_entries_cache: tuple[dict, ...] | None = None
_item_groups_cache: tuple[tuple[str, tuple[dict, ...]], ...] | None = None
_jp_item_groups_cache: tuple[tuple[str, tuple[dict, ...]], ...] | None = None


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


def _jp_trade_item_entries() -> tuple[dict, ...]:
    global _jp_item_entries_cache
    if _jp_item_entries_cache is None:
        data, _ = _request_json(f"{JP_API_ROOT}/data/items")
        _jp_item_entries_cache = tuple(
            entry for group in data.get("result", ()) for entry in group.get("entries", ())
        )
    return _jp_item_entries_cache


def _trade_item_groups() -> tuple[tuple[str, tuple[dict, ...]], ...]:
    global _item_groups_cache
    if _item_groups_cache is None:
        data, _ = _request_json(f"{API_ROOT}/data/items")
        _item_groups_cache = tuple(
            (str(group.get("id", "")), tuple(group.get("entries", ())))
            for group in data.get("result", ())
            if str(group.get("id", ""))
        )
    return _item_groups_cache


def _jp_trade_item_groups() -> tuple[tuple[str, tuple[dict, ...]], ...]:
    global _jp_item_groups_cache
    if _jp_item_groups_cache is None:
        data, _ = _request_json(f"{JP_API_ROOT}/data/items")
        _jp_item_groups_cache = tuple(
            (str(group.get("id", "")), tuple(group.get("entries", ())))
            for group in data.get("result", ())
            if str(group.get("id", ""))
        )
    return _jp_item_groups_cache


def _aligned_trade_item_pairs():
    """日英itemsを構造境界で再同期しながら対応付ける。

    公式APIは翻訳側だけentryが欠けることがあり、グループ総数が異なるだけで
    グループ全体を捨てると、正常なbase typeやUnique名まで翻訳できなくなる。
    Unique/variantなどのentry構造がずれた地点で短いlookaheadを行い、片側の
    欠落entryを飛ばして以降の対応を復元する。
    """
    def signature(entry: dict) -> tuple:
        flags = entry.get("flags") or {}
        return (
            str(entry.get("disc", "")),
            bool(entry.get("name")),
            bool(flags.get("unique")),
            tuple(sorted(flags)),
        )

    japanese_groups = dict(_jp_trade_item_groups())
    for group_id, english_group in _trade_item_groups():
        japanese_group = japanese_groups.get(group_id)
        if japanese_group is None:
            continue
        if len(english_group) == len(japanese_group):
            yield from zip(english_group, japanese_group)
            continue
        english_index = japanese_index = 0
        while english_index < len(english_group) and japanese_index < len(japanese_group):
            english = english_group[english_index]
            japanese = japanese_group[japanese_index]
            if signature(english) == signature(japanese):
                yield english, japanese
                english_index += 1
                japanese_index += 1
                continue

            # 欠落数は通常1～2件。過度に遠い一致は別セクションを誤対応し得るため、
            # 短い範囲で片側だけを進められる場合に限り再同期する。
            lookahead = 8
            english_skip = next((
                offset for offset in range(1, lookahead + 1)
                if english_index + offset < len(english_group)
                and signature(english_group[english_index + offset]) == signature(japanese)
            ), None)
            japanese_skip = next((
                offset for offset in range(1, lookahead + 1)
                if japanese_index + offset < len(japanese_group)
                and signature(japanese_group[japanese_index + offset]) == signature(english)
            ), None)
            if english_skip is not None and (
                japanese_skip is None or english_skip < japanese_skip
            ):
                english_index += english_skip
            elif japanese_skip is not None and (
                english_skip is None or japanese_skip < english_skip
            ):
                japanese_index += japanese_skip
            else:
                break


def _english_trade_item_name(japanese_name: str) -> str | None:
    """公式日英itemsの同一グループ・同一位置から英語固有名を得る。"""
    wanted = japanese_name.strip()
    if not wanted:
        return None
    candidates: set[str] = set()
    for english, japanese in _aligned_trade_item_pairs():
        if str(japanese.get("name", "")).strip() != wanted:
            continue
        if bool((english.get("flags") or {}).get("unique")) != bool(
            (japanese.get("flags") or {}).get("unique")
        ):
            continue
        translated = str(english.get("name", "")).strip()
        if translated:
            candidates.add(translated)
    return next(iter(candidates)) if len(candidates) == 1 else None


_CONFIRMED_ENGLISH_TRADE_TYPE_OVERRIDES = {
    ("accessory", "重い矢筒"): "Heavy Arrow Quiver",
    ("accessory", "原始の矢筒"): "Primal Arrow Quiver",
    ("accessory", "羽根付きの矢筒"): "Feathered Arrow Quiver",
    ("accessory", "灼熱の矢筒"): "Blazing Arrow Quiver",
    ("divination_card", "狂犬病のロア"): "The Rabid Rhoa",
}


def _english_trade_item_type(
    japanese_type: str,
    category: str | None = None,
) -> str | None:
    """公式日英itemsから日本語の一行名に対応する英語typeを得る。"""
    wanted = japanese_type.strip()
    if not wanted:
        return None
    confirmed = _CONFIRMED_ENGLISH_TRADE_TYPE_OVERRIDES.get((category or "", wanted))
    if confirmed:
        return confirmed
    if category == "gem":
        gem_text_matches = {
            str(english.get("text", "")).strip()
            for english, japanese in _aligned_trade_item_pairs()
            if str(japanese.get("text", "")).strip() == wanted
            and str(english.get("text", "")).strip()
        }
        if len(gem_text_matches) == 1:
            # 変容ジェムはtypeが通常版と共通で、textとdiscだけが異なる。
            # 英語textを返せば固定メタデータから正しいtrade_type/alt_xを引ける。
            return next(iter(gem_text_matches))
    exact: set[str] = set()
    contained: list[tuple[int, str]] = []
    for english, japanese in _aligned_trade_item_pairs():
        source = str(japanese.get("type", "")).strip()
        translated = str(english.get("type", "")).strip()
        if not source or not translated:
            continue
        if source == wanted:
            exact.add(translated)
            continue
        # Magic/Veiled/Synthesised等はPrefix/Suffixを含む一行名になる。
        # 内包される最長の公式base typeを採用する。
        if source in wanted:
            contained.append((len(source), translated))
    if exact:
        return next(iter(exact)) if len(exact) == 1 else None
    if not contained:
        return None
    longest = max(length for length, _translated in contained)
    candidates = {
        translated for length, translated in contained if length == longest
    }
    return next(iter(candidates)) if len(candidates) == 1 else None


def _japanese_trade_item_name(english_name: str) -> str | None:
    """公式日英itemsの同一グループ・同一位置から日本語固有名を得る。"""
    wanted = english_name.strip()
    if not wanted:
        return None
    for english, japanese in _aligned_trade_item_pairs():
        if str(english.get("name", "")).strip() != wanted:
            continue
        if bool((english.get("flags") or {}).get("unique")) != bool(
            (japanese.get("flags") or {}).get("unique")
        ):
            continue
        return str(japanese.get("name", "")).strip() or None
    return None


def _japanese_trade_item_type(english_type: str) -> str | None:
    """公式日英itemsの同一位置から日本語Trade用typeを得る。"""
    wanted = english_type.strip()
    if not wanted:
        return None
    for english, japanese in _aligned_trade_item_pairs():
        if str(english.get("type", "")).strip() != wanted:
            continue
        localized = str(japanese.get("type", "")).strip()
        if localized:
            return localized
    return None


def japanese_trade_item_label(
    namespace: str,
    english_name: str,
    variant: str | None = None,
) -> str:
    """関連アイテム用に公式Tradeの日英itemsから日本語表示名を得る。

    価格照合に使う英語identityは変更せず、公式側に日本語entryがない場合だけ
    英語名へフォールバックする。variantは将来の表示拡張用に受け取るが、
    Uniqueは固有名、その他はアイテムtype/nameを正本にする。
    """
    del variant
    name = str(english_name or "").strip()
    if not name:
        return ""
    if str(namespace or "").strip().upper() == "UNIQUE":
        return _japanese_trade_item_name(name) or name
    return _japanese_trade_item_type(name) or name


def _localized_web_trade_type(item: ParsedItem, web_query: dict) -> str:
    """日本語Tradeへ渡すtypeを、variantの基礎Gem名まで正規化する。"""
    query_type = web_query.get("type")
    query_type_value = (
        str(query_type.get("option", "")).strip()
        if isinstance(query_type, dict)
        else str(query_type or "").strip()
    )
    # Magic品はitem.base_typeにもAffix込みの一行名が残る。
    # 実際に英語APIへ渡す正規化済みtypeを、日本語type変換の正本にする。
    localized = _normalize_trade_base_type(
        item.base_type if item.category == "gem" else (query_type_value or item.base_type)
    )
    if item.category != "gem":
        return _japanese_trade_item_type(localized) or localized
    if localized.casefold().startswith("vaal "):
        from src.utils.gem_resolver import load_gem_names_ja

        normal_name = localized[5:].strip()
        localized_normal = load_gem_names_ja().get(normal_name.casefold())
        candidate = f"ヴァール{localized_normal}" if localized_normal else ""
        if candidate and any(
            str(entry.get("type", "")).strip() == candidate
            and not str(entry.get("disc", "")).strip()
            for entry in _jp_trade_item_entries()
        ):
            return candidate
    if not isinstance(query_type, dict):
        return localized
    discriminator = str(query_type.get("discriminator", "")).strip()
    if not discriminator:
        return localized
    lowered = localized.casefold()
    match = next((
        entry for entry in _jp_trade_item_entries()
        if str(entry.get("disc", "")).strip() == discriminator
        and str(entry.get("text", "")).strip().casefold() == lowered
        and str(entry.get("type", "")).strip()
    ), None)
    return str(match["type"]).strip() if match else localized


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


@dataclass(frozen=True)
class UniqueCandidate:
    name: str
    icon_url: str | None
    display_name: str | None = None


def unique_candidate_details(base_type: str) -> tuple[UniqueCandidate, ...]:
    """未鑑定Unique候補へ、日本語表示名と公式CDNアイコンURLを付ける。"""
    return tuple(
        UniqueCandidate(
            name,
            unique_icon_url(name) or _poewiki_unique_icon_url(name),
            _japanese_trade_item_name(name) or name,
        )
        for name in unique_candidates(base_type)
    )


def _poewiki_unique_icon_url(name: str) -> str:
    """現行Awakenedデータから消えた旧Uniqueの画像をPoE Wikiから補う。"""
    filename = f"{name.strip()} inventory icon.png".replace(" ", "_")
    return (
        "https://www.poewiki.net/wiki/Special:Redirect/file/"
        + quote(filename, safe="_")
    )


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
    if (
        _is_unique(item)
        and key == "4253454700"
        and _property_value(item, "ブロック率", "Chance to Block") is not None
    ):
        # Unique盾では総ブロック率だけでなく、価格差になる可変Unique Modの
        # ロールも独立して比較できるよう候補へ残す。
        return False
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


def _property_tier_sources(item: ParsedItem, stat_id: str) -> tuple:
    """最終プロパティ値へ寄与したローカルModを返す。"""
    if stat_id.startswith("property."):
        weapon_keys: set[str] = set()
        if stat_id == "property.total_dps":
            weapon_keys = _WEAPON_PHYSICAL_STAT_KEYS | _WEAPON_ELEMENTAL_STAT_KEYS
        elif stat_id == "property.physical_dps":
            weapon_keys = _WEAPON_PHYSICAL_STAT_KEYS
        elif stat_id == "property.elemental_dps":
            weapon_keys = _WEAPON_ELEMENTAL_STAT_KEYS
        elif stat_id == "property.aps":
            weapon_keys = _WEAPON_SPEED_STAT_KEYS
        elif stat_id == "property.crit":
            weapon_keys = _WEAPON_CRIT_STAT_KEYS
        if weapon_keys:
            return tuple(
                modifier for modifier in item.modifiers
                if modifier.stat_id and modifier.stat_id.rsplit("_", 1)[-1] in weapon_keys
            )

        defence = {
            "property.armour": "ar",
            "property.evasion": "ev",
            "property.energy_shield": "es",
            "property.ward": "ward",
        }.get(stat_id)
        if defence:
            flat_refs, increased_refs = _DEFENCE_REFS[defence]
            refs = flat_refs | increased_refs
            return tuple(modifier for modifier in item.modifiers if modifier.ref in refs)
    return ()


def _awakened_tier_tags(modifiers) -> tuple[int, ...]:
    """通常のproperty/pseudo/explicit行でAwakenedが強調するT1/T2だけ返す。"""
    return tuple(sorted(
        modifier.tier for modifier in modifiers if modifier.tier in {1, 2}
    ))


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


def unresolved_modifier_warnings(
    item: ParsedItem,
    resolved_filters: tuple[TradeStatFilter, ...] = (),
) -> tuple[str, ...]:
    """派生メタデータでも公式API照合でも未解決のModだけを返す。"""
    # Blighted MapはAwakened同様、rolled Modやブライト固有暗黙Modを
    # stat検索しないため、解決対象外のModを警告しない。
    if _map_blight_state(item) is not None:
        return ()
    # AwakenedはHeist Blueprint/Contractのrolled Prefix/Suffixを
    # 検索候補にしない。対象外Modを「未解決」として警告しない。
    if item.category in {"heist_blueprint", "heist_contract"}:
        return ()
    # Captured BeastはBeast種別だけを検索し、個体のMonster Modは照合しない。
    if item.category == "captured_beast":
        return ()
    # Awakenedは現在のアイテム化スペクター死体をCurrencyのExact検索として扱う。
    # 固有能力は個体差のない説明であり、公式Tradeにも完全な検索Statがないため、
    # Mod候補や「未解決」警告には含めない。
    if item.category == "corpse":
        return ()
    # Pinnacle boss invitations display this fixed implicit without the
    # percentage found in the official Trade stat template. It has no
    # per-item value and the invitation name already identifies the product.
    invitation_fixed_implicits = {
        _normalized_stat_text(
            "アイテムの数量のモッドはボスからドロップする報酬の量に影響する"
        ),
        _normalized_stat_text(
            "Modifiers to Item Quantity affect the amount of rewards dropped by the boss"
        ),
    }
    resolved_lines = {
        _normalized_stat_text(line)
        for row in resolved_filters
        if row.stat_id.startswith(("explicit.", "implicit.", "enchant."))
        for line in row.text.splitlines()
        if line.strip()
    }
    fixed_unique_refs = unique_fixed_stats(item.name) if _is_unique(item) else None

    def should_warn(modifier) -> bool:
        if modifier.stat_id is not None or modifier.kind in {"desecrated"}:
            return False
        if (
            item.category == "invitation"
            and modifier.kind == "implicit"
            and _normalized_stat_text(modifier.text) in invitation_fixed_implicits
        ):
            return False
        if _normalized_stat_text(modifier.text) in resolved_lines:
            return False
        if _is_unique(item) and _unique_roll_bounds(modifier.text) is None:
            # Awakenedのitems.ndjsonにfixedStatsがないUniqueでは、数値なしModを
            # Variant検索候補として扱わない。SvalinnのLucky block等も警告不要。
            if fixed_unique_refs is None or modifier.ref in fixed_unique_refs:
                return False
        return True

    return tuple(
        modifier.text for modifier in item.modifiers
        if should_warn(modifier)
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
        "property.links": "リンク数は価格への影響が大きい",
        "property.quality": "品質20%超を保持", "property.item_level": "クラフト価値のあるアイテムレベル",
        "property.base_percentile": "防具ベース固有値のロールを保持",
        "property.memory_strands": "高いメモリーの糸を保持",
    }
    sockets, links = _socket_summary(item)
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
    known_source_refs = set().union(*pseudo_refs.values())

    def effective_source_ref(modifier) -> str:
        if modifier.ref:
            return modifier.ref
        normalized = normalize_stat_text(modifier.text)
        return next((
            ref for ref in known_source_refs
            if normalize_stat_text(ref) == normalized
        ), "")

    def source_contribution(stat_id: str, modifier) -> float | None:
        if not modifier.values:
            return None
        value = modifier.values[0]
        ref = effective_source_ref(modifier)
        if stat_id == "pseudo.pseudo_total_life":
            if ref == "+# to maximum Life":
                return value
            if "str" in _ATTRIBUTE_REFS.get(ref, ()):
                return value * 0.5
        if stat_id == "pseudo.pseudo_total_mana":
            if ref == "+# to maximum Mana":
                return value
            if "int" in _ATTRIBUTE_REFS.get(ref, ()):
                return value * 0.5
        resistance_targets = {
            "pseudo.pseudo_total_fire_resistance": "fire",
            "pseudo.pseudo_total_cold_resistance": "cold",
            "pseudo.pseudo_total_lightning_resistance": "lightning",
        }
        resistance = _RESISTANCE_REFS.get(ref)
        if resistance:
            elements, chaos = resistance
            if stat_id == "pseudo.pseudo_total_elemental_resistance":
                return value * len(elements)
            if stat_id == "pseudo.pseudo_total_chaos_resistance" and chaos:
                return value
            if resistance_targets.get(stat_id) in elements:
                return value
        attribute_targets = {
            "pseudo.pseudo_total_strength": "str",
            "pseudo.pseudo_total_dexterity": "dex",
            "pseudo.pseudo_total_intelligence": "int",
        }
        if attribute_targets.get(stat_id) in _ATTRIBUTE_REFS.get(ref, ()):
            return value
        if (stat_id == "pseudo.pseudo_total_all_attributes"
                and ref == "+# to all Attributes"):
            return value
        if ref in pseudo_refs.get(stat_id, set()):
            return value
        return value if modifier.stat_id == stat_id else None

    def source_heading(modifier) -> str:
        labels = {
            "prefix": "プレフィックス",
            "suffix": "サフィックス",
            "implicit": "暗黙Mod",
            "crafted": "クラフトMod",
            "fractured": "フラクチャーMod",
            "enchant": "エンチャント",
            "veiled": "ヴェールドMod",
            "explicit": "明示Mod",
        }
        heading = labels.get(modifier.affix or modifier.kind, "元Mod")
        if modifier.tier is not None:
            heading += f" (T{modifier.tier})"
        return heading

    for row in filters:
        sources = by_stat.get(row.stat_id, ())
        source = sources[0] if sources else None
        pseudo_sources = [modifier for modifier in item.modifiers
                          if effective_source_ref(modifier)
                          in pseudo_refs.get(row.stat_id, set())]
        property_sources = _property_tier_sources(item, row.stat_id)
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
                reason = f"ベースアイテム向けT{source.tier} Mod"
            elif row.enabled:
                reason = "アイテム種別に応じた主要条件"
            else:
                reason = "候補として表示（初期未選択）"
        exact = row.exact or (
            row.min_value is not None and row.max_value is not None and row.min_value == row.max_value
        )
        fixed_foulborn = (
            source is not None
            and source.generation == "foulborn"
            and _unique_roll_bounds(source.text) is None
        )
        read_value = (
            row.min_value if fixed_foulborn else
            source.values[0] if source and source.values else row.read_value
        )
        if read_value is None:
            read_value = property_values.get(row.stat_id)
        if read_value is None and row.kind == "pseudo" and row.min_value is not None:
            read_value = round(row.min_value / (1 - DEFAULT_SEARCH_RANGE), 2)
        contributing_sources = property_sources or pseudo_sources or sources
        unique_sources = tuple(dict.fromkeys(
            modifier
            for modifier in contributing_sources
            if modifier.text and modifier.text != row.text
        ))
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
            decimal=source.decimal if source else row.decimal,
            tier_tags=(
                _awakened_tier_tags(property_sources or pseudo_sources or sources)
                or row.tier_tags
            ),
            source_texts=tuple(modifier.text for modifier in unique_sources),
            source_contributions=tuple(
                source_contribution(row.stat_id, modifier)
                for modifier in unique_sources
            ),
            source_headings=tuple(
                source_heading(modifier) for modifier in unique_sources
            ),
        ))
    return tuple(decorated)


def resolve_trade_stat_filters(
    item: ParsedItem, preset: str = PRESET_FINISHED,
    trade_base_type: str | None = None,
    trade_name: str | None = None,
) -> tuple[TradeStatFilter, ...]:
    if preset not in TRADE_PRESETS:
        raise ValueError(f"未対応の検索プリセットです: {preset}")
    if preset == PRESET_BASE:
        if PRESET_BASE not in available_trade_presets(item):
            raise ValueError("このアイテムはベースアイテム検索の対象外です。")
        return _decorate_filters(item, _base_item_filters(item, trade_base_type))
    if is_inscribed_ultimatum(item):
        # Awakenedと同じく名前完全一致だけを使う。供物・報酬・試練Modは
        # Trade API上で高信頼に個体照合できないため、曖昧な条件へ変換しない。
        return ()
    if item.category == "captured_beast":
        # AwakenedはCaptured BeastをBeast種別の完全一致だけで検索する。
        # ilvl・rare/monster Mod・空きAffixはいずれも検索条件にしない。
        return ()
    if item.category == "gem":
        return _gem_filters(item, trade_base_type)
    entries = _trade_stat_entries()
    resolved: list[TradeStatFilter] = []
    unique_item = _is_unique(item)
    fixed_unique_refs = unique_fixed_stats(
        trade_name or item.name
    ) if unique_item else None
    modifiers = _combine_valdo_multiline_modifiers(item, entries)
    for modifier in modifiers:
        hidden_reason = ""
        if (
            item.category in {"heist_blueprint", "heist_contract"}
            and modifier.kind in {"prefix", "suffix", "crafted"}
        ):
            # AwakenedのkeepByTypeに合わせ、Heistのrolled Modは検索しない。
            continue
        if modifier.ref == "Allocates #" and modifier.oils:
            talisman = "talisman" in item.item_class.casefold() or "タリスマン" in item.item_class
            modifiable_amulet = (
                item.category == "accessory" and not talisman
                and "corrupted" not in item.flags and "mirrored" not in item.flags
            )
            if modifiable_amulet and not any(oil in {11, 12, 13} for oil in modifier.oils):
                # Awakenedの銀・金に加え、相場が高くなりやすい乳白色を使う
                # Anointmentも候補へ表示する。その他の付け直しやすいものは隠す。
                continue
        roll_bounds = _unique_roll_bounds(modifier.text) if unique_item else None
        standalone_variant = (
            unique_item
            and modifier.kind == "explicit"
            and modifier.option_value is None
            and "|" in (modifier.stat_id or "")
        )
        unique_variant = (
            standalone_variant
            or (
                unique_item
                and modifier.kind == "explicit"
                and fixed_unique_refs is not None
                and modifier.ref not in fixed_unique_refs
            )
        )
        if unique_item and roll_bounds is None:
            corrupted_implicit = (
                modifier.kind == "implicit" and modifier.generation == "corrupted"
            )
            foulborn_variant = modifier.generation == "foulborn"
            if not standalone_variant and not corrupted_implicit and not foulborn_variant and (
                fixed_unique_refs is None or modifier.ref in fixed_unique_refs
            ):
                # Awakened準拠: 常設Modでも可変ロールがあれば候補へ残す。
                # 固定Modも「隠された候補」から確認できるよう保持する。
                hidden_reason = "ユニーク固定値のため初期非表示"
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
        preferred_stat_id = _CATEGORY_STAT_OVERRIDES.get((
            item.category, api_kind, source,
        ))
        if preferred_stat_id:
            preferred_candidates = [
                entry for entry in candidates
                if str(entry.get("id")) == preferred_stat_id
            ]
            if preferred_candidates:
                candidates = preferred_candidates
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
            entry_text = str(entry.get("text", ""))
            value = _value_for_template(modifier.text, entry_text)
            if value is None and (
                "#" in entry_text
                or modifier.option_value is not None
                or str(entry["id"]) not in _API_VERIFIED_VALUELESS_FIXED_STAT_IDS
            ):
                value = modifier.values[0] if modifier.values else None
            maximum = None
            if modifier.stat_id == str(entry["id"]):
                metadata, _ = default_metadata_index().match(modifier.text, modifier.kind)
                if metadata is None and modifier.ref:
                    metadata, _ = default_metadata_index().match_ref(
                        modifier.ref, modifier.kind,
                    )
                if metadata and not preferred_stat_id:
                    fixed_foulborn_value = (
                        value
                        if modifier.generation == "foulborn" and roll_bounds is None
                        else None
                    )
                    value, maximum = metadata.search_bounds(
                        value,
                        fixed_foulborn_value if fixed_foulborn_value is not None else (
                            modifier.roll_min if unique_item else None
                        ),
                        fixed_foulborn_value if fixed_foulborn_value is not None else (
                            modifier.roll_max if unique_item else None
                        ),
                        DEFAULT_SEARCH_RANGE,
                    )
            if hidden_reason and value is not None:
                # 初期非表示の固定Unique Modは、ユーザーが明示的に選んだ時だけ
                # 現在値を完全一致で検索する。共通の許容幅を適用すると、
                # 4(3)%の変異値が3%以上になり通常品まで混ざってしまう。
                current_value = _value_for_template(
                    modifier.text, str(entry.get("text", "")),
                )
                if current_value is not None:
                    value = maximum = current_value
            if unique_item and roll_bounds is not None and modifier.stat_id != str(entry["id"]):
                value = _unique_minimum(value, roll_bounds)
            valdo_exact = item.category == "map" and item.base_type.casefold() == "valdo map"
            resolved.append(TradeStatFilter(
                str(entry["id"]), modifier.text, value, modifier.kind,
                unique_variant or valdo_exact or (modifier.ref == "Allocates #" and (
                    "talisman" in item.item_class.casefold() or "タリスマン" in item.item_class
                )),
                maximum, modifier.ref, modifier.confidence, modifier.inverted,
                option_value=modifier.option_value, option_text=modifier.option_text,
                oils=modifier.oils,
                selection_reason=(
                    f"logbook-area:{modifier.group}"
                    if item.category == "expedition_logbook" and modifier.group is not None else ""
                ),
                group_type="count" if alternatives else "and",
                group_key=group_key, group_min=1 if alternatives else None,
                hidden_reason=hidden_reason,
            ))
    combined: dict[str, TradeStatFilter] = {}
    counts: dict[str, int] = {}
    for stat_filter in resolved:
        combine_key = (
            f"{stat_filter.stat_id}@{stat_filter.selection_reason}"
            if item.category == "expedition_logbook" and stat_filter.selection_reason
            else stat_filter.stat_id
        )
        previous = combined.get(combine_key)
        if previous is None:
            combined[combine_key] = stat_filter
            counts[combine_key] = 1
            continue
        counts[combine_key] += 1
        total = None
        if previous.min_value is not None and stat_filter.min_value is not None:
            total = previous.min_value + stat_filter.min_value
        combined[combine_key] = TradeStatFilter(
            stat_filter.stat_id, previous.text, total, previous.kind, False,
            stat_filter.max_value, stat_filter.ref, min(previous.confidence, stat_filter.confidence),
            stat_filter.inverted,
            option_value=stat_filter.option_value, option_text=stat_filter.option_text,
            oils=stat_filter.oils,
            selection_reason=previous.selection_reason or stat_filter.selection_reason,
            group_type=stat_filter.group_type, group_key=stat_filter.group_key,
            group_min=stat_filter.group_min,
            hidden_reason=previous.hidden_reason or stat_filter.hidden_reason,
        )
    enable_unique_rolls = unique_item and len(combined) <= 3
    # AwakenedはFoulborn品について、置換されたFoulborn Modだけでなく、
    # 置換されずに残った通常Unique Modも個体差として初期選択する。
    enable_foulborn_rolls = unique_item and "foulborn" in item.flags
    # ユニーク品はpseudo集約を表示しないため、元の可変Modを消費扱いにしない。
    # 非ユニーク品だけ、pseudoと個別Modの二重表示を避ける。
    consumed_stat_ids = (
        set() if unique_item or item.category in {"jewel", "abyss_jewel"}
        else _pseudo_consumed_stat_ids(item)
    )
    consumed_refs = {
        modifier.ref for modifier in item.modifiers
        if modifier.stat_id in consumed_stat_ids and modifier.ref
    }
    individual = tuple(
        TradeStatFilter(
            row.stat_id,
            f"{row.text} ({counts[combine_key]}行合計)" if counts[combine_key] > 1 else row.text,
            row.min_value, row.kind,
            False if row.hidden_reason else (
                enable_unique_rolls or enable_foulborn_rolls or row.enabled
            ),
            row.max_value, row.ref, row.confidence, row.inverted,
            option_value=row.option_value, option_text=row.option_text, oils=row.oils,
            selection_reason=row.selection_reason,
            group_type=row.group_type, group_key=row.group_key, group_min=row.group_min,
            hidden_reason=row.hidden_reason,
        )
        for combine_key, row in combined.items()
        if row.stat_id not in consumed_stat_ids and not (not unique_item and row.ref in consumed_refs)
    )
    if unique_item:
        unique_property_ids = {
            "property.total_dps", "property.physical_dps",
            "property.elemental_dps", "property.aps", "property.crit",
            "property.block", "property.memory_strands",
        }
        special_properties = tuple(
            row for row in _initial_property_filters(item, trade_base_type)
            if row.stat_id in unique_property_ids
        )
        # AwakenedのUnique Map Exactは固有名・Map種別・Tierだけで照合し、
        # 個体ごとのUnique Modロールを検索条件へ追加しない。
        exact_individual = () if item.category == "map" else individual
        return _decorate_filters(
            item, special_properties + exact_individual + _item_detail_filters(item)
            + _unique_exception_filters(item) + _special_content_filters(item), True,
        )
    initial_properties = [
        row for row in _initial_property_filters(item, trade_base_type)
        if (row.stat_id != "property.base_percentile"
            or uses_dedicated_exact_preset(item))
    ]
    filters = (
        tuple(initial_properties + (
            [] if item.category in {"jewel", "abyss_jewel"}
            else list(_gear_pseudo_filters(item))
        ))
        + individual + _item_detail_filters(item) + _empty_affix_filters(item, trade_base_type)
        + _special_content_filters(item)
    )
    decorated = list(_decorate_filters(item, filters))
    if item.category == "weapon":
        gem_level_markers = (
            "level of all", "level of socketed", "skill gems", "gemのレベル",
            "ジェムのレベル", "ソケットされたジェム",
        )

        def is_gem_level(row: TradeStatFilter) -> bool:
            source = f"{row.ref or ''} {row.text}".casefold()
            return any(marker.casefold() in source for marker in gem_level_markers)

        spell_markers = (
            "spell", "スペル", "cast speed", "キャストスピード",
            "skill gems", "ジェムのレベル",
        )
        spell_weapon = any(
            any(marker.casefold() in f"{row.stat_id} {row.ref or ''} {row.text}".casefold()
                for marker in spell_markers)
            for row in decorated
        )
        decorated = [
            replace(row, enabled=True, selection_reason="スペル武器の主要ジェムレベルMod")
            if is_gem_level(row) else row
            for row in decorated
        ]
        attack_priority = {
            "property.total_dps": 0,
            "property.physical_dps": 1,
            "property.elemental_dps": 2,
            "property.aps": 3,
            "property.crit": 4,
        }

        def spell_priority(row: TradeStatFilter) -> int:
            source = f"{row.stat_id} {row.ref or ''} {row.text}".casefold()
            if is_gem_level(row):
                return 0
            if "spell_damage" in source or "スペルダメージ" in source:
                return 1
            if any(word in source for word in (
                "elemental_damage", "fire_damage", "cold_damage", "lightning_damage",
                "元素ダメージ", "火ダメージ", "冷気ダメージ", "雷ダメージ",
            )):
                return 2
            if "cast_speed" in source or "キャストスピード" in source:
                return 3
            if ("critical_strike_chance_for_spells" in source
                    or "スペルクリティカル" in source):
                return 4
            if "critical_strike_multiplier" in source or "クリティカル倍率" in source:
                return 5
            if "mana" in source or "マナ" in source:
                return 6
            if row.stat_id in attack_priority:
                return 30 + attack_priority[row.stat_id]
            return 20 if row.kind == "pseudo" else 40

        decorated = [row for _, row in sorted(
            enumerate(decorated),
            key=lambda pair: (
                spell_priority(pair[1]) if spell_weapon
                else attack_priority.get(pair[1].stat_id, 20 if pair[1].kind == "pseudo" else 40),
                pair[0],
            ),
        )]
    if item.category == "accessory":
        # Awakenedのpseudo優先順を土台に、利用頻度の高いLifeとESを先頭へ出す。
        # Anointmentは後段、未分類の個別Modは読み取り順を維持する。
        accessory_priority = {
            "pseudo.pseudo_total_life": 0,
            "pseudo.pseudo_total_energy_shield": 1,
            "pseudo.pseudo_total_elemental_resistance": 2,
            "pseudo.pseudo_total_chaos_resistance": 3,
            "pseudo.pseudo_total_all_attributes": 4,
            "pseudo.pseudo_total_strength": 5,
            "pseudo.pseudo_total_dexterity": 6,
            "pseudo.pseudo_total_intelligence": 7,
            "pseudo.pseudo_total_mana": 8,
        }

        def accessory_sort_key(pair):
            index, row = pair
            if row.stat_id in accessory_priority:
                return (accessory_priority[row.stat_id], index)
            if row.ref == "Allocates #" or row.oils:
                return (90, index)
            if row.kind == "pseudo":
                return (20, index)
            return (100, index)

        decorated = [row for _, row in sorted(
            enumerate(decorated), key=accessory_sort_key,
        )]
    if item.category in {"jewel", "abyss_jewel"}:
        rarity = item.rarity.casefold()
        magic = rarity in {"magic", "マジック"}
        rare = rarity in {"rare", "レア"}

        def jewel_priority(pair):
            index, row = pair
            source = f"{row.stat_id} {row.ref or ''} {row.text}".casefold()
            if "life" in source or "ライフ" in source:
                return (0, index)
            if "energy_shield" in source or "エナジーシールド" in source:
                return (1, index)
            if "critical" in source or "クリティカル" in source:
                return (2, index)
            if "speed" in source or "スピード" in source:
                return (3, index)
            if "damage" in source or "ダメージ" in source:
                return (4, index)
            if any(word in source for word in (
                "armour", "evasion", "resistance", "attribute",
                "アーマー", "回避", "耐性", "能力値", "筋力", "器用さ", "知性",
            )):
                return (5, index)
            return (10, index)

        adjusted = []
        for row in decorated:
            enabled = row.enabled
            if rare and row.kind in {"prefix", "suffix", "explicit", "pseudo"}:
                enabled = False
            elif magic and row.kind in {"prefix", "suffix", "explicit"}:
                enabled = True
            adjusted.append(replace(row, enabled=enabled))
        decorated = [row for _, row in sorted(enumerate(adjusted), key=jewel_priority)]
    if item.category in {"flask", "tincture"}:
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
                if value in {2, 8}:
                    minimum, maximum = None, value
                elif value == 4:
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


def _combine_valdo_multiline_modifiers(item: ParsedItem, entries: tuple[dict, ...]) -> tuple:
    """Valdo固有の複数行statを、公式Tradeの改行テンプレート単位へ戻す。"""
    if item.category != "map" or item.base_type.casefold() != "valdo map":
        return item.modifiers
    official = {
        _normalized_stat_text(str(entry.get("text", ""))): entry
        for entry in entries
        if entry.get("type") == "explicit" and "\n" in str(entry.get("text", ""))
    }
    result, index = [], 0
    while index < len(item.modifiers):
        matched = None
        for size in range(min(3, len(item.modifiers) - index), 1, -1):
            group = item.modifiers[index:index + size]
            text = "\n".join(row.text for row in group)
            entry = official.get(_normalized_stat_text(text))
            if entry:
                matched = replace(
                    group[0], text=text, values=tuple(
                        value for row in group for value in row.values
                    ), stat_id=str(entry["id"]), confidence=1.0,
                )
                result.append(matched)
                index += size
                break
        if matched is None:
            result.append(item.modifiers[index])
            index += 1
    return tuple(result)


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
    if item.category == "map":
        # Awakened準拠: MapはTier・種類・固有条件で検索し、ilvlは使わない。
        # UIの古い状態や直接呼び出しから渡されてもクエリへ混入させない。
        item_level_min = None
        item_level_max = None
        stat_filters = tuple(
            row for row in stat_filters if row.stat_id != "property.item_level"
        )
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
        raise ValueError("このアイテムはベースアイテム検索の対象外です。")
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
    elif item.category == "map" and base_type == "Map":
        query_type = {"option": query_type, "discriminator": "map"}
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
        name_discriminator = trade_discriminator
        if name_discriminator is None and item.category == "map" and base_type == "Map":
            name_discriminator = "map"
        query["name"] = (
            {"option": trade_name.strip(), "discriminator": name_discriminator}
            if name_discriminator else trade_name.strip()
        )
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
        # Trade APIのoption型statは選択肢自体が値を表す。
        # コピー文中の数値をmin/maxとして併記すると、正しいoptionでも0件になる。
        minimum, maximum = (
            (None, None)
            if stat_filter.option_value is not None
            else (stat_filter.min_value, stat_filter.max_value)
        )
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
        api_stat_id = (
            stat_filter.stat_id.split("|", 1)[0]
            if stat_filter.option_value is not None
            else stat_filter.stat_id
        )
        group["filters"].append({"id": api_stat_id, "value": value})
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
    query["filters"] = {
        group_name: group
        for group_name, group in query["filters"].items()
        if group.get("filters")
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
    return bool(
        re.fullmatch(
            r"(?:(?:Blighted|Blight-ravaged)\s+)?Map\s*[（(]\s*Tier\s*\d+\s*[）)]",
            base_type.strip(), flags=re.IGNORECASE,
        )
        or re.fullmatch(
            r"(?:(?:ブライトに覆われた|ブライトに蹂躙された)\s*)?"
            r"マップ\s*[（(]\s*ティア\s*\d+\s*[）)]",
            base_type.strip(),
        )
    )


def _contains_japanese_text(value: object) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", str(value)))


def english_trade_identity(
    item: ParsedItem,
    base_type: str | None = None,
    name: str | None = None,
) -> tuple[str | None, str | None]:
    """3.29以降のローカライズ済み詳細コピーを英語Trade検索用IDへ変換する。"""
    resolved_type = str(base_type or item.base_type or "").strip() or None
    if resolved_type and _contains_japanese_text(resolved_type):
        resolved_type = (
            _english_trade_item_type(resolved_type, item.category) or resolved_type
        )

    resolved_name = str(name or "").strip() or None
    if resolved_name and resolved_name == str(item.base_type or "").strip():
        resolved_name = None
    if (
        resolved_name
        and _is_unique(item)
        and _contains_japanese_text(resolved_name)
    ):
        resolved_name = _english_trade_item_name(resolved_name) or resolved_name
    return resolved_type, resolved_name


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
    trade_base_type, trade_name = english_trade_identity(
        item, trade_base_type, trade_name,
    )
    if (item.rarity.casefold() in {"magic", "マジック"}
            and trade_base_type and item.name == item.base_type):
        # 日本語詳細コピーのMagic品はAffix込み英語名がname/base_typeの両方へ
        # 入るため、検索候補を公式base typeへ正規化する。
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
    raw_listings: list[PriceListing] = []
    fetch_cached = False
    fetched_count = 0
    while fetched_count < min(len(ids), 100):
        fetch_ids = ",".join(ids[fetched_count:fetched_count + 10])
        fetch_url = f"{API_ROOT}/fetch/{fetch_ids}?query={quote(query_id)}"
        _trade_log(
            f"request: GET {fetch_url} "
            f"(candidates {fetched_count + 1}-{min(fetched_count + 10, len(ids))})"
        )
        fetched, _, block_cached = _cached_request_json(fetch_url)
        fetch_cached = fetch_cached or block_cached
        for row in fetched.get("result", ()):
            listing = row.get("listing", {})
            fetched_item = row.get("item", {})
            price = listing.get("price") or {}
            has_price = (
                price.get("amount") is not None
                and bool(price.get("currency"))
            )
            pricing_method = (
                "instant" if listing.get("fee") is not None
                else "face_to_face" if has_price or fetched_item.get("note") is not None
                else "unpriced"
            )
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

            raw_listings.append(PriceListing(
                float(price["amount"]) if has_price else 0.0,
                str(price["currency"]) if has_price else "",
                str(account),
                str(fetched_item.get("name", "")), str(fetched_item.get("baseType", "")),
                str(listing.get("indexed", "")),
                int(fetched_item["ilvl"]) if fetched_item.get("ilvl") is not None else None,
                property_number("Level", "レベル", "Gem Level", "ジェムレベル"),
                property_number("Quality", "品質"),
                int(fetched_item["stackSize"]) if fetched_item.get("stackSize") is not None else None,
                pricing_method=pricing_method,
            ))
        fetched_count += 10
        grouped = _group_price_listings(raw_listings)
        ungrouped = sum(row.listed_times <= 2 for row in grouped)
        # Awakened準拠: 最初の20件は必ず確認し、価格操作らしい同一出品者の
        # 連投が多い時だけ、十分な独立サンプルが得られるまで最大100件取得する。
        if fetched_count >= 20 and len(grouped) >= 10 and ungrouped >= 7:
            break
    listings = _group_price_listings(raw_listings)
    rate_limit = headers.get("X-Rate-Limit-Ip-State", "") if headers else ""
    _trade_log(
        f"completed: query_id={query_id!r} candidates={len(ids)} "
        f"priced_listings={len(listings)} rate_limit={rate_limit!r} "
        f"raw_listings={len(raw_listings)}"
    )
    # 検索IDはAPIホストごとに管理されるため、www側のIDをjp側へ渡せない。
    # 日本語アイテム文から得た名称を使った検索JSONをURLへ埋め込み、
    # 日本語Trade画面自身に検索状態を読み込ませる。
    web_payload = json.loads(json.dumps(payload))
    web_query = web_payload["query"]
    localized_type = _localized_web_trade_type(item, web_query)
    # ベース全体検索ではAPIクエリにtypeが存在しない。Magic品の通常コピーは
    # Affix込みの1行名になるため、ここでtypeを新規追加すると公式Tradeが
    # 「存在しないベースタイプ」として検索状態の読込を拒否する。
    if localized_type and "type" in web_query:
        if isinstance(web_query.get("type"), dict):
            web_query["type"]["option"] = localized_type
        else:
            web_query["type"] = localized_type
    localized_name = str(trade_name or item.name or "").strip()
    if _is_unique(item):
        # 未鑑定Uniqueではitem.nameがベースタイプになるため、候補選択で確定した
        # trade_nameを正本にする。日本語Tradeへは公式itemsの日英対応から得た
        # 正式な日本語Unique名を渡す。
        localized_name = _japanese_trade_item_name(localized_name) or localized_name
    if "name" in web_query and localized_name:
        if isinstance(web_query["name"], dict):
            web_query["name"]["option"] = localized_name
        else:
            web_query["name"] = localized_name
    completion_reward = next((
        row for row in stat_filters
        if row.enabled and row.stat_id == "property.map_completion_reward"
    ), None)
    if completion_reward is not None and completion_reward.option_text:
        map_filters = web_query.get("filters", {}).get("map_filters", {}).get("filters", {})
        if "map_completion_reward" in map_filters:
            map_filters["map_completion_reward"]["option"] = completion_reward.option_text
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
