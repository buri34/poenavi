from __future__ import annotations

from collections.abc import Callable
import json
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..models import ParsedItem
from ..trade import (
    PriceListing, PriceResult, TradeApiError, TradeLeague, _cached_request_json,
    _group_price_listings,
)
from .parser import TRADE_CATEGORY_BY_CATEGORY


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
        if not row.enabled or not row.stat_id:
            continue
        direct.append(_trade_filter_row(row.stat_id, row.min_value, row.max_value))
    return groups


def build_search_query(
    item: ParsedItem,
    status: str = "online",
    *,
    quality_min: int | None = None,
) -> dict:
    trade_category = TRADE_CATEGORY_BY_CATEGORY.get(item.category)
    if trade_category is None:
        raise ValueError(f"PoE2 Trade category未対応: {item.category}")
    type_filters = {"category": {"option": trade_category}}
    query = {
        "status": {"option": _STATUS_OPTIONS.get(status, status)},
        "type": item.base_type,
        "stats": _stat_groups_from_modifiers(item.modifiers),
        "filters": {"type_filters": {"filters": type_filters}},
    }
    misc = {}
    if item.item_level is not None and item.rarity == "rare":
        misc["ilvl"] = {"min": item.item_level}
    if quality_min is not None:
        misc["quality"] = {"min": quality_min}
    if misc:
        query["filters"]["misc_filters"] = {"filters": misc}
    if item.rarity == "unique":
        query["name"] = item.name
    return {"query": query, "sort": {"price": "asc"}}


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
    partial_result_callback: Callable[[PriceResult], None] | None = None,
) -> PriceResult:
    """Search Trade2 and adapt its rows to the existing shared price UI model."""
    payload = build_search_query(item, status=status, quality_min=quality_min)
    if stat_filters:
        payload["query"]["stats"] = _stat_groups_from_filters(stat_filters)
    search_url = f"{API_ROOT}/search/{quote(league, safe='')}"
    search, headers, search_cached = _cached_request_json(search_url, payload)
    query_id = str(search.get("id", ""))
    ids = list(search.get("result", ()))
    if not query_id:
        raise TradeApiError("PoE2 Trade APIから検索IDを取得できませんでした。")

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
                f"https://www.pathofexile.com/trade2/search/poe2/{quote(league, safe='')}/{query_id}",
                search_cached or fetch_cached,
            ))
        independent = sum(row.listed_times <= 2 for row in grouped)
        if fetched_count >= 20 and len(grouped) >= 10 and independent >= 7:
            break

    return PriceResult(
        league, query_id, len(ids), _group_price_listings(raw),
        headers.get("X-Rate-Limit-Ip-State", "") if headers else "",
        f"https://www.pathofexile.com/trade2/search/poe2/{quote(league, safe='')}/{query_id}",
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
