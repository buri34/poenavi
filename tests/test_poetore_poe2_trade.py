from __future__ import annotations

import json
from pathlib import Path

from src.poetore.poe2 import build_search_query, fetch_listings, parse_item_text, search_items
from src.poetore.poe2.trade import available_pc_leagues, default_pc_league


FIXTURES = Path(__file__).parent / "fixtures" / "poe2" / "minimal_items.json"


def _unique_fixture():
    rows = json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    return next(row for row in rows if row["id"] == "unique_focus_en")


def test_unique_query_contains_only_minimal_identity_filters():
    item = parse_item_text(_unique_fixture()["text"])
    payload = build_search_query(item)
    query = payload["query"]
    assert query["name"] == "The Eternal Spark"
    assert query["type"] == "Crystal Focus"
    assert query["filters"] == {
        "type_filters": {"filters": {
            "category": {"option": "armour.focus"},
        }}
    }
    assert query["stats"] == [{"type": "and", "filters": []}]


def test_mock_search_and_fetch_complete_the_minimal_vertical_slice():
    item = parse_item_text(_unique_fixture()["text"])
    payload = build_search_query(item)
    seen = []

    def fake_request(request):
        seen.append(request)
        if request.get_method() == "POST":
            assert json.loads(request.data) == payload
            return {"id": "query-id", "total": 1, "result": ["listing-id"]}
        return {"result": [{"id": "listing-id", "item": {"name": item.name}}]}

    search = search_items("Standard", payload, request_json=fake_request)
    listings = fetch_listings(search["id"], search["result"], request_json=fake_request)
    assert listings["result"][0]["item"]["name"] == "The Eternal Spark"
    assert len(seen) == 2
    assert "/api/trade2/search/Standard" in seen[0].full_url
    assert "/api/trade2/fetch/listing-id?query=query-id" in seen[1].full_url


def test_poe2_leagues_are_filtered_and_auto_selects_current_softcore(monkeypatch):
    monkeypatch.setattr(
        "src.poetore.poe2.trade._cached_request_json",
        lambda _url: ({"result": [
            {"id": "Runes of Aldur", "realm": "poe2"},
            {"id": "HC Runes of Aldur", "realm": "poe2"},
            {"id": "Standard", "realm": "poe2"},
            {"id": "PoE1 League", "realm": "pc"},
        ]}, {}),
    )
    leagues = available_pc_leagues()
    assert [row.id for row in leagues] == ["Runes of Aldur", "HC Runes of Aldur", "Standard"]
    assert leagues[1].hardcore
    assert default_pc_league(leagues) == "Runes of Aldur"
