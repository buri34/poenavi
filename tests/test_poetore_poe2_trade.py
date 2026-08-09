from __future__ import annotations

import json
from pathlib import Path

from src.poetore.poe2 import build_search_query, fetch_listings, parse_item_text, search_items
from src.poetore.poe2.trade import (
    _stat_groups_from_filters, available_pc_leagues, default_pc_league, trade_stat_value,
)
from src.poetore.trade import TradeStatFilter


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


def test_mageblood_option_stats_use_trade2_pipe_suffix_ids():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "mageblood_ja.txt").read_text(
        encoding="utf-8"
    )
    payload = build_search_query(parse_item_text(text))
    filters = payload["query"]["stats"][0]["filters"]
    legacy = [row for row in filters if row["id"].startswith("explicit.stat_264262054|")]
    assert [row["id"] for row in legacy] == [
        "explicit.stat_264262054|3", "explicit.stat_264262054|11",
        "explicit.stat_264262054|4", "explicit.stat_264262054|8",
    ]
    assert all("value" not in row for row in legacy)


def test_reported_rare_gloves_send_chaos_resistance_to_trade2():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_gloves_ja.txt").read_text(
        encoding="utf-8"
    )
    payload = build_search_query(parse_item_text(text))
    filters = payload["query"]["stats"][0]["filters"]
    chaos = next(row for row in filters if row["id"] == "explicit.stat_2923486259")
    assert chaos["value"] == {"min": 15.0}


def test_multi_value_trade_stats_use_same_arithmetic_mean_as_ee2():
    assert trade_stat_value((25.0, 39.0)) == 32.0
    assert trade_stat_value((1.0, 3.0, 5.0, 7.0)) == 4.0
    assert trade_stat_value((8.0,)) == 8.0
    assert trade_stat_value(()) is None


def test_reported_rare_spear_sends_flat_damage_average_and_optional_quality():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_spear_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    without_quality = build_search_query(item)
    flat = next(
        row for row in without_quality["query"]["stats"][0]["filters"]
        if row["id"] == "explicit.stat_1940865751"
    )
    assert flat["value"] == {"min": 32.0}
    misc = without_quality["query"]["filters"]["misc_filters"]["filters"]
    assert misc == {"ilvl": {"min": 81}}

    with_quality = build_search_query(item, quality_min=20)
    assert with_quality["query"]["filters"]["misc_filters"]["filters"]["quality"] == {
        "min": 20
    }


def test_reported_rare_body_armour_sends_local_and_global_as_ee2_or_group():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_body_armour_ja.txt").read_text(
        encoding="utf-8"
    )
    payload = build_search_query(parse_item_text(text))
    groups = payload["query"]["stats"]
    evasion = [
        group for group in groups
        if {row["id"] for row in group["filters"]} == {
            "explicit.stat_124859000", "explicit.stat_2106365538",
        }
    ]
    assert evasion == [
        {
            "type": "count", "value": {"min": 1},
            "filters": [
                {"id": "explicit.stat_124859000", "value": {"min": 105.0}},
                {"id": "explicit.stat_2106365538", "value": {"min": 105.0}},
            ],
        },
        {
            "type": "count", "value": {"min": 1},
            "filters": [
                {"id": "explicit.stat_124859000", "value": {"min": 40.0}},
                {"id": "explicit.stat_2106365538", "value": {"min": 40.0}},
            ],
        },
    ]


def test_edited_or_filter_applies_bounds_to_both_ids_and_off_removes_group():
    row = TradeStatFilter(
        "explicit.stat_124859000", "回避力が増加する", 90, "explicit",
        enabled=True, max_value=120,
        alternative_stat_ids=("explicit.stat_2106365538",),
    )
    assert _stat_groups_from_filters((row,)) == [
        {"type": "and", "filters": []},
        {
            "type": "count", "value": {"min": 1},
            "filters": [
                {"id": "explicit.stat_124859000", "value": {"min": 90, "max": 120}},
                {"id": "explicit.stat_2106365538", "value": {"min": 90, "max": 120}},
            ],
        },
    ]
    assert _stat_groups_from_filters((row.__class__(
        **{**row.__dict__, "enabled": False}
    ),)) == [{"type": "and", "filters": []}]
