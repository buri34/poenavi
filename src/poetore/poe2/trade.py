from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import json
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..models import ParsedItem
from ..trade import (
    PriceListing, PriceResult, TradeApiError, TradeLeague, TradeStatFilter, _cached_request_json,
    _group_price_listings,
)
from .parser import TRADE_CATEGORY_BY_CATEGORY
from .metadata import resolve_identity


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


def _augment_socket_count(item: ParsedItem) -> int | None:
    raw = item.properties.get("Sockets") or item.properties.get("ソケット") or ""
    count = len(re.findall(r"(?<![A-Za-z])S(?![A-Za-z])", str(raw), re.IGNORECASE))
    return count or None


def _waystone_tier(item: ParsedItem) -> float | None:
    value = _property_float(item, "Waystone Tier", "ウェイストーンティア", "Map Tier", "マップティア")
    if value is not None:
        return value
    match = re.search(r"(?:Tier|ティア)\s*(\d+)", item.base_type, re.IGNORECASE)
    return float(match.group(1)) if match else None


_POE2_PROPERTY_SPECS = (
    ("property.spirit", "スピリット", ("Spirit", "スピリット"), "property", False),
    ("property.runic_ward", "ルーンワード", ("Runic Ward", "ルーンワード", "Ward"), "property", False),
    ("property.reload_time", "リロード時間", ("Reload Time", "リロード時間", "再装填時間"), "property", False),
    ("property.map_revives", "復活回数", ("Revives Available", "復活が利用可能"), "property", False),
    ("property.map_pack_size", "モンスターパックサイズ", ("Monster Pack Size", "モンスターパックサイズ"), "property", False),
    ("property.map_magic_monsters", "モンスターエフェクティブ", ("Magic Monsters", "モンスターエフェクティブ"), "property", False),
    ("property.map_rare_monsters", "モンスターレアリティ", ("Rare Monsters", "モンスターレアリティ"), "property", False),
    ("property.area_level", "エリアレベル", ("Area Level", "エリアレベル"), "property", False),
    ("property.unidentified_tier", "未鑑定ティア", ("Unidentified Tier", "未鑑定ティア"), "property", False),
)

_POE2_STATE_LABELS = {
    "sanctified": "聖別化",
    "desecrated": "冒涜",
    "fractured": "フラクチャー",
    "crafted": "クラフト済み",
}

_POE2_STATE_FILTER_NAMES = {
    "sanctified": "sanctified",
    "desecrated": "desecrated",
    "fractured": "fractured_item",
    "crafted": "crafted",
}


def poe2_search_filters(item: ParsedItem) -> tuple[TradeStatFilter, ...]:
    """Build editable Trade2 property/state rows beside resolved modifier rows."""
    rows: list[TradeStatFilter] = []
    for stat_id, label, names, kind, enabled in _POE2_PROPERTY_SPECS:
        value = _property_float(item, *names)
        if value is not None:
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
    for flag, label in _POE2_STATE_LABELS.items():
        if flag in item.flags:
            rows.append(TradeStatFilter(
                f"property.state.{flag}", label, None, "state", True,
            ))
    return tuple(rows)


_POE2_FILTER_TARGETS = {
    "property.spirit": ("equipment_filters", "spirit"),
    "property.runic_ward": ("equipment_filters", "ward"),
    "property.reload_time": ("equipment_filters", "reload_time"),
    "property.augment_sockets": ("equipment_filters", "rune_sockets"),
    "property.gem_sockets": ("misc_filters", "gem_sockets"),
    "property.map_tier": ("map_filters", "map_tier"),
    "property.map_revives": ("map_filters", "map_revives"),
    "property.map_pack_size": ("map_filters", "map_packsize"),
    "property.map_magic_monsters": ("map_filters", "map_magic_monsters"),
    "property.map_rare_monsters": ("map_filters", "map_rare_monsters"),
    "property.area_level": ("misc_filters", "area_level"),
    "property.unidentified_tier": ("misc_filters", "unidentified_tier"),
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
                "option": "true"
            }
            continue
        target = _POE2_FILTER_TARGETS.get(row.stat_id)
        if target is None:
            continue
        group, name = target
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
    stat_filters: tuple = (),
) -> dict:
    trade_category = TRADE_CATEGORY_BY_CATEGORY.get(item.category)
    if trade_category is None:
        raise ValueError(f"PoE2 Trade category未対応: {item.category}")
    type_filters = {"category": {"option": trade_category}}
    query = {
        "status": {"option": _STATUS_OPTIONS.get(status, status)},
        "type": item.base_type,
        "stats": (
            _stat_groups_from_filters(stat_filters)
            if stat_filters else _stat_groups_from_modifiers(item.modifiers)
        ),
        "filters": {"type_filters": {"filters": type_filters}},
    }
    type_filter_values = query["filters"]["type_filters"]["filters"]
    if item.item_level is not None and item.rarity == "rare":
        type_filter_values["ilvl"] = {"min": item.item_level}
    if quality_min is not None:
        type_filter_values["quality"] = {"min": quality_min}
    if item.rarity == "unique":
        query["name"] = item.name
    if stat_filters:
        _apply_poe2_filter_rows(query, stat_filters)
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
    if localized_type is None or (item.rarity == "unique" and localized_name is None):
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
    stat_filters: tuple = (),
    quality_min: int | None = None,
    include_corrupted=None,
    include_mirrored: bool | None = None,
    partial_result_callback: Callable[[PriceResult], None] | None = None,
) -> PriceResult:
    """Search Trade2 and adapt its rows to the existing shared price UI model."""
    payload = build_search_query(
        item, status=status, quality_min=quality_min, stat_filters=stat_filters,
    )
    misc = payload["query"]["filters"].setdefault("misc_filters", {"filters": {}})["filters"]
    if include_corrupted == "only":
        misc["corrupted"] = {"option": "true"}
    elif include_corrupted is False:
        misc["corrupted"] = {"option": "false"}
    if include_mirrored is False:
        misc["mirrored"] = {"option": "false"}
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
