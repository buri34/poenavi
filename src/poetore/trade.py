from __future__ import annotations

from dataclasses import dataclass
import json
import re
from statistics import median
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import ParsedItem


API_ROOT = "https://www.pathofexile.com/api/trade"
JP_API_ROOT = "https://jp.pathofexile.com/api/trade"
USER_AGENT = "PoENavi/poetore-local-spike (github.com/buri34/poenavi)"
DEFAULT_SEARCH_RANGE = 0.10
TRADE_STATUS_OPTIONS = {
    "instant": "securable",
    "available": "available",
    "online": "online",
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
    "property.armour": ("armour_filters", "ar"),
    "property.evasion": ("armour_filters", "ev"),
    "property.energy_shield": ("armour_filters", "es"),
    "property.ward": ("armour_filters", "ward"),
    "property.item_level": ("misc_filters", "ilvl"),
    "property.quality": ("misc_filters", "quality"),
    "property.sockets": ("socket_filters", "sockets"),
    "property.links": ("socket_filters", "links"),
}


class TradeApiError(RuntimeError):
    pass


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
        pdps = physical_dps(item) or 0
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
    elif item.category == "armour":
        defenses = [
            ("property.armour", "アーマー", _property_value(item, "アーマー", "防具", "Armour")),
            ("property.evasion", "回避力", _property_value(item, "回避力", "Evasion Rating")),
            ("property.energy_shield", "エナジーシールド", _property_value(item, "エナジーシールド", "Energy Shield")),
            ("property.ward", "Ward", _property_value(item, "Ward")),
        ]
        present = [(stat_id, text, value) for stat_id, text, value in defenses if value]
        for stat_id, text, value in present:
            filters.append(TradeStatFilter(stat_id, text, _relaxed(value), "property", True))
    return filters


def _gear_pseudo_filters(item: ParsedItem) -> list[TradeStatFilter]:
    if item.category not in {"weapon", "armour", "accessory"}:
        return []
    life = elemental = chaos = 0.0
    for modifier in item.modifiers:
        text = modifier.text.lower()
        value = modifier.values[0] if modifier.values else 0
        if ("最大ライフ" in text or "maximum life" in text) and "minion" not in text and "ミニオン" not in text:
            life += value
        if ("筋力" in text or "strength" in text) and "require" not in text and "装備要求" not in text:
            life += value * 0.5
        if "混沌耐性" in text or "chaos resistance" in text:
            chaos += value
        element_count = 0
        if "耐性" in text:
            element_count += sum(word in text for word in ("火", "冷気", "雷"))
        if "resist" in text:
            element_count += sum(word in text for word in ("fire", "cold", "lightning"))
        if "全ての元素耐性" in text or "all elemental resistances" in text:
            element_count = max(element_count, 3)
        elemental += value * element_count
    filters = []
    if life:
        filters.append(TradeStatFilter(
            "pseudo.pseudo_total_life", "最大ライフ合計", _relaxed(life), "pseudo", True,
        ))
    if elemental:
        filters.append(TradeStatFilter(
            "pseudo.pseudo_total_elemental_resistance", "元素耐性合計", _relaxed(elemental), "pseudo", True,
        ))
    if chaos:
        filters.append(TradeStatFilter(
            "pseudo.pseudo_total_chaos_resistance", "混沌耐性合計", _relaxed(chaos), "pseudo", True,
        ))
    return filters


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


def _is_unique(item: ParsedItem) -> bool:
    return item.rarity.casefold() in {"unique", "ユニーク"}


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


def resolve_trade_stat_filters(
    item: ParsedItem, preset: str = PRESET_FINISHED,
) -> tuple[TradeStatFilter, ...]:
    if preset not in TRADE_PRESETS:
        raise ValueError(f"未対応の検索プリセットです: {preset}")
    if preset == PRESET_BASE:
        if PRESET_BASE not in available_trade_presets(item):
            raise ValueError("このアイテムはクラフトベース検索の対象外です。")
        return _base_item_filters(item)
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
        value = _value_for_template(modifier.text, str(entry.get("text", "")))
        if value is None:
            value = modifier.values[0] if modifier.values else None
        if unique_item and roll_bounds is not None:
            value = _unique_minimum(value, roll_bounds)
        resolved.append(TradeStatFilter(str(entry["id"]), modifier.text, value, modifier.kind, False))
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
        )
    enable_unique_rolls = unique_item and len(combined) <= 3
    individual = tuple(
        TradeStatFilter(
            row.stat_id,
            f"{row.text} ({counts[row.stat_id]}行合計)" if counts[row.stat_id] > 1 else row.text,
            row.min_value, row.kind, enable_unique_rolls or row.enabled,
        )
        for row in combined.values()
    )
    if unique_item:
        return individual + _item_detail_filters(item)
    return (
        tuple(_initial_property_filters(item) + _gear_pseudo_filters(item))
        + individual + _item_detail_filters(item) + _empty_affix_filters(item)
    )


def build_search_query(
    item: ParsedItem, trade_base_type: str | None = None,
    stat_filters: tuple[TradeStatFilter, ...] = (),
    trade_status: str = "instant",
    trade_name: str | None = None,
    preset: str = PRESET_FINISHED,
) -> dict:
    if trade_status not in TRADE_STATUS_OPTIONS:
        raise ValueError(f"未対応の取引方式です: {trade_status}")
    if preset not in TRADE_PRESETS:
        raise ValueError(f"未対応の検索プリセットです: {preset}")
    if preset == PRESET_BASE and PRESET_BASE not in available_trade_presets(item):
        raise ValueError("このアイテムはクラフトベース検索の対象外です。")
    base_type = (trade_base_type or item.base_type).strip()
    query: dict = {
        "status": {"option": TRADE_STATUS_OPTIONS[trade_status]},
        "type": base_type,
        "stats": [{"type": "and", "filters": []}],
        "filters": {"trade_filters": {"filters": {"price": {"option": "chaos"}}}},
    }
    if _is_unique(item) and trade_name and trade_name.strip():
        query["name"] = trade_name.strip()
    if _is_unique(item) and "unidentified" in item.flags:
        query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]["identified"] = {"option": "false"}
    rarity = item.rarity.lower()
    rarity_option = "nonunique" if preset == PRESET_BASE else {
        "レア": "rare", "rare": "rare", "ユニーク": "unique", "unique": "unique",
    }.get(rarity)
    if rarity_option:
        query["filters"]["type_filters"] = {"filters": {"rarity": {"option": rarity_option}}}
    if preset == PRESET_BASE:
        misc = query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
        misc["corrupted"] = {"option": "false"}
        misc["mirrored"] = {"option": "false"}
        misc["fractured_item"] = {"option": "true" if any(
            modifier.kind == "fractured" for modifier in item.modifiers
        ) else "false"}
        misc["synthesised_item"] = {
            "option": "true" if "synthesised" in item.flags else "false"
        }
        misc["split"] = {"option": "true" if "split" in item.flags else "false"}
    elif item.category in {"weapon", "armour", "accessory"}:
        misc = query["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
        misc["corrupted"] = {"option": "true" if "corrupted" in item.flags else "false"}
        if "mirrored" in item.flags:
            misc["mirrored"] = {"option": "true"}
        misc["split"] = {"option": "true" if "split" in item.flags else "false"}
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
        if stat_filter.min_value is not None:
            value["min"] = stat_filter.min_value
        query["stats"][0]["filters"].append({"id": stat_filter.stat_id, "value": value})
    return {"query": query, "sort": {"price": "asc"}}


def search_prices(
    item: ParsedItem, trade_base_type: str | None = None, league: str | None = None,
    stat_filters: tuple[TradeStatFilter, ...] = (),
    trade_status: str = "instant",
    trade_name: str | None = None,
    preset: str = PRESET_FINISHED,
) -> PriceResult:
    league = league or active_pc_league()
    payload = build_search_query(
        item, trade_base_type, stat_filters, trade_status, trade_name, preset,
    )
    search_url = f"{API_ROOT}/search/{quote(league, safe='')}"
    _trade_log(
        f"search: league={league!r} preset={preset!r} trade_status={trade_status!r} "
        f"api_status={TRADE_STATUS_OPTIONS[trade_status]!r} url={search_url}"
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
