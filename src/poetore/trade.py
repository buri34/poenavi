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

_PROPERTY_FILTERS = {
    "property.total_dps": ("weapon_filters", "dps"),
    "property.elemental_dps": ("weapon_filters", "edps"),
    "property.physical_dps": ("weapon_filters", "pdps"),
    "property.armour": ("armour_filters", "ar"),
    "property.evasion": ("armour_filters", "ev"),
    "property.energy_shield": ("armour_filters", "es"),
    "property.ward": ("armour_filters", "ward"),
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
        raise TradeApiError(f"PoE Trade APIへの接続に失敗しました: {exc}") from exc


def active_pc_league() -> str:
    data, _ = _request_json(f"{API_ROOT}/data/leagues")
    leagues = [row for row in data.get("result", ()) if row.get("realm") == "pc"]
    for row in leagues:
        name = str(row.get("id", ""))
        lowered = name.lower()
        if name and all(word not in lowered for word in ("hardcore", "ruthless", "standard")):
            return name
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
            ("property.armour", "防具", _property_value(item, "防具", "Armour")),
            ("property.evasion", "回避力", _property_value(item, "回避力", "Evasion Rating")),
            ("property.energy_shield", "エナジーシールド", _property_value(item, "エナジーシールド", "Energy Shield")),
            ("property.ward", "Ward", _property_value(item, "Ward")),
        ]
        present = [(stat_id, text, value) for stat_id, text, value in defenses if value]
        if len(present) == 1:
            stat_id, text, value = present[0]
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


def resolve_trade_stat_filters(item: ParsedItem) -> tuple[TradeStatFilter, ...]:
    entries = _trade_stat_entries()
    resolved: list[TradeStatFilter] = []
    for modifier in item.modifiers:
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
        resolved.append(TradeStatFilter(
            str(entry["id"]), modifier.text, value, modifier.kind, False,
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
        )
    individual = tuple(
        TradeStatFilter(
            row.stat_id,
            f"{row.text} ({counts[row.stat_id]}行合計)" if counts[row.stat_id] > 1 else row.text,
            row.min_value, row.kind, row.enabled,
        )
        for row in combined.values()
    )
    return tuple(_initial_property_filters(item) + _gear_pseudo_filters(item)) + individual


def build_search_query(
    item: ParsedItem, trade_base_type: str | None = None,
    stat_filters: tuple[TradeStatFilter, ...] = (),
) -> dict:
    base_type = (trade_base_type or item.base_type).strip()
    query: dict = {
        "status": {"option": "online"},
        "type": base_type,
        "stats": [{"type": "and", "filters": []}],
        "filters": {"trade_filters": {"filters": {"price": {"option": "chaos"}}}},
    }
    rarity = item.rarity.lower()
    rarity_option = {"レア": "rare", "rare": "rare", "ユニーク": "unique", "unique": "unique"}.get(rarity)
    if rarity_option:
        query["filters"]["type_filters"] = {"filters": {"rarity": {"option": rarity_option}}}
    for stat_filter in stat_filters:
        if not stat_filter.enabled:
            continue
        property_target = _PROPERTY_FILTERS.get(stat_filter.stat_id)
        if property_target:
            group, name = property_target
            value = {"min": stat_filter.min_value} if stat_filter.min_value is not None else {}
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
) -> PriceResult:
    league = league or active_pc_league()
    search, headers = _request_json(
        f"{API_ROOT}/search/{quote(league, safe='')}",
        build_search_query(item, trade_base_type, stat_filters),
    )
    query_id = str(search.get("id", ""))
    ids = list(search.get("result", ()))
    if not query_id:
        raise TradeApiError("検索IDを取得できませんでした。")
    listings: list[PriceListing] = []
    if ids:
        fetch_ids = ",".join(ids[:10])
        fetched, _ = _request_json(f"{API_ROOT}/fetch/{fetch_ids}?query={quote(query_id)}")
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
    return PriceResult(league, query_id, len(ids), tuple(listings), rate_limit)
