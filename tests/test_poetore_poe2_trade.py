from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from src.poetore.poe2 import build_search_query, fetch_listings, parse_item_text, search_items
from src.poetore.poe2.trade import (
    _stat_groups_from_filters, available_pc_leagues, build_web_trade_url,
    default_pc_league, poe2_search_filters, search_prices, trade_stat_value,
)
from src.poetore.models import ParsedItem
from src.poetore.trade import TradeStatFilter


FIXTURES = Path(__file__).parent / "fixtures" / "poe2" / "minimal_items.json"


def _unique_fixture():
    rows = json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    return next(row for row in rows if row["id"] == "unique_focus_en")


def _web_payload(url: str) -> dict:
    encoded = parse_qs(urlparse(url).query)["q"][0]
    return json.loads(unquote(encoded))


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


def test_poe2_web_trade_localizes_unique_identity_and_keeps_option_stat_ids():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "mageblood_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    payload = build_search_query(item)
    url = build_web_trade_url(item, "Runes of Aldur", payload, "english-query-id")
    parsed = urlparse(url)
    assert parsed.netloc == "jp.pathofexile.com"
    assert parsed.path == "/trade2/search/poe2/Runes%20of%20Aldur"
    query = _web_payload(url)["query"]
    assert query["name"] == "メイジブラッド"
    assert query["type"] == "実用的なベルト"
    option_ids = [
        row["id"] for row in query["stats"][0]["filters"]
        if row["id"].startswith("explicit.stat_264262054|")
    ]
    assert option_ids == [
        "explicit.stat_264262054|3", "explicit.stat_264262054|11",
        "explicit.stat_264262054|4", "explicit.stat_264262054|8",
    ]


def test_poe2_web_trade_localizes_taming_name_and_base_type():
    item = ParsedItem(
        item_class="Rings", rarity="unique", name="The Taming",
        base_type="Prismatic Ring", category="ring",
    )
    query = _web_payload(build_web_trade_url(
        item, "Standard", build_search_query(item), "english-query-id",
    ))["query"]
    assert query["name"] == "テイミング"
    assert query["type"] == "プリズムの指輪"


def test_poe2_web_trade_localizes_rare_weapon_and_armour_bases():
    fixtures = (
        ("rare_spear_ja.txt", "飛翔のスピア"),
        ("rare_body_armour_ja.txt", "スリップストライクベスト"),
    )
    for filename, expected_type in fixtures:
        text = (Path(__file__).parent / "fixtures" / "poe2" / filename).read_text(
            encoding="utf-8"
        )
        item = parse_item_text(text)
        query = _web_payload(build_web_trade_url(
            item, "Standard", build_search_query(item), "english-query-id",
        ))["query"]
        assert query["type"] == expected_type
        assert "name" not in query


def test_poe2_web_trade_falls_back_to_english_query_id_when_identity_is_missing(
    monkeypatch,
):
    item = parse_item_text(_unique_fixture()["text"])
    monkeypatch.setattr(
        "src.poetore.poe2.trade._localized_identity", lambda *_args: None,
    )
    url = build_web_trade_url(item, "Standard", build_search_query(item), "query/id")
    assert url == (
        "https://www.pathofexile.com/trade2/search/poe2/Standard/query%2Fid"
    )


def test_poe2_price_result_exposes_japanese_web_trade_url(monkeypatch):
    text = (Path(__file__).parent / "fixtures" / "poe2" / "mageblood_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)

    def fake_cached_request(url, payload=None):
        assert "/api/trade2/search/Runes%20of%20Aldur" in url
        assert payload["query"]["name"] == "Mageblood"
        return {"id": "english-query-id", "result": []}, {}, False

    monkeypatch.setattr(
        "src.poetore.poe2.trade._cached_request_json", fake_cached_request,
    )
    result = search_prices(item, "Runes of Aldur")
    assert result.web_url.startswith(
        "https://jp.pathofexile.com/trade2/search/poe2/Runes%20of%20Aldur?q="
    )
    query = _web_payload(result.web_url)["query"]
    assert query["name"] == "メイジブラッド"
    assert query["type"] == "実用的なベルト"


def test_phase45_search_prices_sends_corrupted_and_mirrored_state_filters(monkeypatch):
    item = _phase45_item("phase45_runemastered_ja.txt")
    rows = _phase45_rows(item)

    def fake_cached_request(url, payload=None):
        assert "/api/trade2/search/Standard" in url
        misc = payload["query"]["filters"]["misc_filters"]["filters"]
        assert misc["desecrated"] == {"option": "true"}
        assert misc["fractured_item"] == {"option": "true"}
        assert misc["corrupted"] == {"option": "true"}
        assert misc["mirrored"] == {"option": "false"}
        return {"id": "phase45-query", "result": []}, {}, False

    monkeypatch.setattr(
        "src.poetore.poe2.trade._cached_request_json", fake_cached_request,
    )
    result = search_prices(
        item, "Standard", stat_filters=rows,
        include_corrupted="only", include_mirrored=False,
    )
    assert result.query_id == "phase45-query"


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
    type_filters = without_quality["query"]["filters"]["type_filters"]["filters"]
    assert type_filters["ilvl"] == {"min": 81}

    with_quality = build_search_query(item, quality_min=20)
    assert with_quality["query"]["filters"]["type_filters"]["filters"]["quality"] == {
        "min": 20
    }


def test_reported_rare_body_armour_sends_only_category_selected_local_stat():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_body_armour_ja.txt").read_text(
        encoding="utf-8"
    )
    payload = build_search_query(parse_item_text(text))
    filters = payload["query"]["stats"][0]["filters"]
    evasion = [row for row in filters if row["id"] == "explicit.stat_124859000"]
    assert evasion == [
        {"id": "explicit.stat_124859000", "value": {"min": 105.0}},
        {"id": "explicit.stat_124859000", "value": {"min": 40.0}},
    ]
    assert all(row["id"] != "explicit.stat_2106365538" for row in filters)


def test_poe2_filter_ignores_audit_alternatives_in_normal_search():
    row = TradeStatFilter(
        "explicit.stat_124859000", "回避力が増加する", 90, "explicit",
        enabled=True, max_value=120,
        alternative_stat_ids=("explicit.stat_2106365538",),
    )
    assert _stat_groups_from_filters((row,)) == [
        {"type": "and", "filters": [
            {"id": "explicit.stat_124859000", "value": {"min": 90, "max": 120}},
        ]},
    ]
    assert _stat_groups_from_filters((row.__class__(
        **{**row.__dict__, "enabled": False}
    ),)) == [{"type": "and", "filters": []}]


def _phase45_item(filename: str):
    text = (Path(__file__).parent / "fixtures" / "poe2" / filename).read_text(
        encoding="utf-8"
    )
    return parse_item_text(text)


def _phase45_rows(item):
    modifier_rows = tuple(
        TradeStatFilter(
            mod.stat_id, mod.text, trade_stat_value(mod.values), mod.kind,
            enabled=True, ref=mod.ref, confidence=mod.confidence,
        )
        for mod in item.modifiers if mod.stat_id
    )
    property_rows = tuple(
        row.__class__(**{**row.__dict__, "enabled": True})
        for row in poe2_search_filters(item)
    )
    return modifier_rows + property_rows


def test_phase45_equipment_properties_and_states_use_official_filter_groups():
    item = _phase45_item("phase45_sceptre_ja.txt")
    rows = _phase45_rows(item)
    payload = build_search_query(item, stat_filters=rows)
    filters = payload["query"]["filters"]
    assert filters["equipment_filters"]["filters"] == {
        "spirit": {"min": 100.0},
        "rune_sockets": {"min": 2.0},
    }
    assert filters["misc_filters"]["filters"]["sanctified"] == {"option": "true"}
    assert any(row["id"].startswith("rune.") for row in payload["query"]["stats"][0]["filters"])


def test_phase45_waystone_properties_use_official_map_and_misc_filters():
    item = _phase45_item("phase45_waystone_ja.txt")
    rows = _phase45_rows(item)
    payload = build_search_query(item, stat_filters=rows)
    filters = payload["query"]["filters"]
    assert filters["map_filters"]["filters"] == {
        "map_revives": {"min": 3.0},
        "map_packsize": {"min": 42.0},
        "map_magic_monsters": {"min": 18.0},
        "map_rare_monsters": {"min": 11.0},
        "map_tier": {"min": 15.0, "max": 15.0},
    }
    assert filters["misc_filters"]["filters"] == {
        "area_level": {"min": 79.0},
        "unidentified_tier": {"min": 5.0},
    }


def test_phase45_runemastered_desecrated_and_fractured_filters_are_distinct():
    item = _phase45_item("phase45_runemastered_ja.txt")
    rows = _phase45_rows(item)
    payload = build_search_query(item, stat_filters=rows)
    assert payload["query"]["type"] == "Runemastered Vaal Cuirass"
    assert payload["query"]["filters"]["equipment_filters"]["filters"]["ward"] == {
        "min": 500.0
    }
    assert payload["query"]["filters"]["misc_filters"]["filters"] == {
        "desecrated": {"option": "true"},
        "fractured_item": {"option": "true"},
    }
    assert payload["query"]["stats"][0]["filters"] == [{
        "id": "desecrated.stat_2923486259", "value": {"min": 21.0},
    }]


def test_phase45_rune_and_soul_core_queries_use_separate_categories():
    fixtures = json.loads(
        (Path(__file__).parent / "fixtures" / "poe2" / "phase45_augment_items_ja.json").read_text(
            encoding="utf-8"
        )
    )["fixtures"]
    for fixture in fixtures:
        item = parse_item_text(fixture["text"])
        payload = build_search_query(item)
        assert payload["query"]["type"] == fixture["base_type"]
        assert payload["query"]["filters"]["type_filters"]["filters"]["category"] == {
            "option": fixture["trade_category"]
        }


def test_phase45_gem_socket_uses_official_misc_filter():
    item = _phase45_item("phase45_gem_ja.txt")
    rows = tuple(
        row.__class__(**{**row.__dict__, "enabled": True})
        for row in poe2_search_filters(item)
    )
    payload = build_search_query(item, stat_filters=rows)
    assert payload["query"]["filters"]["type_filters"]["filters"]["category"] == {
        "option": "gem.activegem"
    }
    assert payload["query"]["filters"]["misc_filters"]["filters"]["gem_sockets"] == {
        "min": 2.0
    }
