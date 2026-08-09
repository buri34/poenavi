from __future__ import annotations

from collections.abc import Callable
import json
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..models import ParsedItem
from .parser import TRADE_CATEGORY_BY_CATEGORY


API_ROOT = "https://www.pathofexile.com/api/trade2"
USER_AGENT = "PoENavi/poetore-poe2-development (github.com/buri34/poenavi)"
def build_search_query(item: ParsedItem, status: str = "online") -> dict:
    trade_category = TRADE_CATEGORY_BY_CATEGORY.get(item.category)
    if trade_category is None:
        raise ValueError(f"PoE2 Trade category未対応: {item.category}")
    type_filters = {"category": {"option": trade_category}}
    query = {
        "status": {"option": status},
        "type": item.base_type,
        "stats": [{"type": "and", "filters": []}],
        "filters": {"type_filters": {"filters": type_filters}},
    }
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
