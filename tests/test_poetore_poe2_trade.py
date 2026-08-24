from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from src.poetore.poe2 import build_search_query, fetch_listings, parse_item_text, search_items
from src.poetore.poe2.trade import (
    _stat_groups_from_filters, available_pc_leagues, build_web_trade_url,
    augment_socket_edit_counts, available_virtual_augments, default_pc_league,
    empty_augment_socket_count,
    poe2_search_filters, poe2_trade_filters, search_prices, trade_stat_value,
    virtual_augment_choice_label, virtual_augment_filters,
)
from src.poetore.models import ItemModifier, ParsedItem
from src.poetore.trade import PRESET_BASE, PRESET_FINISHED, TradeStatFilter


FIXTURES = Path(__file__).parent / "fixtures" / "poe2" / "minimal_items.json"
PHASE6_FIXTURES = Path(__file__).parent / "fixtures" / "poe2" / "phase6_special_items_ja.json"
AMBIGUOUS_BASE_FIXTURES = (
    Path(__file__).parent / "fixtures" / "poe2" / "ambiguous_bases_bilingual.json"
)


def _unique_fixture():
    rows = json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    return next(row for row in rows if row["id"] == "unique_focus_en")


def _web_payload(url: str) -> dict:
    encoded = parse_qs(urlparse(url).query)["q"][0]
    return json.loads(unquote(encoded))


@pytest.mark.parametrize(
    "fixture",
    json.loads(AMBIGUOUS_BASE_FIXTURES.read_text(encoding="utf-8"))["fixtures"],
    ids=lambda row: row["id"],
)
def test_user_captured_ambiguous_bases_send_exact_trade2_type(fixture):
    for language in ("ja", "en"):
        item = parse_item_text(fixture[language])
        assert build_search_query(item)["query"]["type"] == fixture["expected_base_type"]
    japanese_item = parse_item_text(fixture["ja"])
    payload = build_search_query(japanese_item)
    localized_query = _web_payload(
        build_web_trade_url(japanese_item, "Standard", payload, "query-id")
    )["query"]
    assert localized_query["type"] == fixture["expected_ja_base_type"]


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


def test_unidentified_unique_searches_base_with_unique_and_unidentified_filters():
    item = ParsedItem(
        item_class="Talismans", rarity="unique", name="", base_type="Nettle Talisman",
        category="talisman", flags=("unidentified",),
    )
    payload = build_search_query(item, stat_filters=poe2_trade_filters(item))
    query = payload["query"]
    assert query["type"] == "Nettle Talisman"
    assert "name" not in query
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "unique"}
    assert query["filters"]["misc_filters"]["filters"]["identified"] == {"option": "false"}
    web_query = _web_payload(
        build_web_trade_url(item, "Standard", payload, "query-id")
    )["query"]
    assert web_query["type"] == "イラクサのタリスマン"
    assert "name" not in web_query


@pytest.mark.parametrize("state", ["crafted", "fractured", "desecrated"])
def test_special_mod_provenance_does_not_create_a_dedicated_state_row(state):
    item = ParsedItem(
        item_class="Gloves", rarity="rare", name="Test", base_type="Grand Bracers",
        category="gloves", flags=(state,),
    )
    assert not any(
        row.stat_id == f"property.state.{state}"
        for row in poe2_trade_filters(item)
    )
    query = build_search_query(item, stat_filters=poe2_trade_filters(item))
    misc = query["query"]["filters"].get("misc_filters", {}).get("filters", {})
    assert {"crafted", "fractured_item", "desecrated"}.isdisjoint(misc)


@pytest.mark.parametrize("kind", ["crafted", "fractured", "desecrated"])
def test_finished_preset_uses_explicit_counterpart_for_special_mod_like_ee2(kind):
    item = ParsedItem(
        item_class="Gloves", rarity="rare", name="Test", base_type="Grand Bracers",
        category="gloves", flags=(kind,), modifiers=(
            ItemModifier(
                "Chaos Resistance", (21.0,), kind=kind,
                stat_id=f"{kind}.stat_2923486259",
            ),
        ),
    )
    rows = poe2_trade_filters(item)
    direct = next(row for row in rows if row.text == "Chaos Resistance")
    assert (direct.stat_id, direct.kind, direct.enabled) == (
        "explicit.stat_2923486259", "explicit", True,
    )
    assert direct.provenance_tags == (kind,)
    sent = build_search_query(item, stat_filters=rows)["query"]["stats"][0]["filters"]
    assert sent == [{"id": "explicit.stat_2923486259", "value": {"min": 21.0}}]


def test_finished_preset_keeps_special_stat_without_explicit_counterpart():
    item = ParsedItem(
        item_class="Gloves", rarity="rare", name="Test", base_type="Grand Bracers",
        category="gloves", flags=("desecrated",), modifiers=(
            ItemModifier("Special", (12.0,), kind="desecrated", stat_id="desecrated.missing"),
        ),
    )
    direct = next(row for row in poe2_trade_filters(item) if row.text == "Special")
    assert (direct.stat_id, direct.kind, direct.enabled) == (
        "desecrated.missing", "desecrated", True,
    )
    assert direct.provenance_tags == ("desecrated",)


@pytest.mark.parametrize("kind", ["crafted", "fractured", "desecrated"])
@pytest.mark.parametrize("immutable_state", ["corrupted", "mirrored", "sanctified"])
def test_base_keeps_provenance_but_finished_normalizes_immutable_items(
    kind, immutable_state,
):
    modifier = ItemModifier(
        "Chaos Resistance", (21.0,), kind=kind,
        stat_id=f"{kind}.stat_2923486259",
    )
    item = ParsedItem(
        item_class="Gloves", rarity="rare", name="Test", base_type="Grand Bracers",
        category="gloves", flags=(kind,), modifiers=(modifier,),
    )
    base = next(row for row in poe2_trade_filters(item, preset=PRESET_BASE) if row.kind != "state")
    assert base.stat_id == f"{kind}.stat_2923486259"
    immutable = replace(item, flags=(kind, immutable_state))
    finished = next(
        row for row in poe2_trade_filters(immutable)
        if row.text == "Chaos Resistance"
    )
    assert finished.stat_id == "explicit.stat_2923486259"


def test_finished_preset_merges_natural_and_normalized_special_sources():
    item = ParsedItem(
        item_class="Gloves", rarity="rare", name="Test", base_type="Grand Bracers",
        category="gloves", flags=("crafted",), modifiers=(
            ItemModifier("Chaos Resistance", (15.0,), stat_id="explicit.stat_2923486259"),
            ItemModifier(
                "Crafted Chaos Resistance", (6.0,), kind="crafted",
                stat_id="crafted.stat_2923486259",
            ),
        ),
    )
    rows = [row for row in poe2_trade_filters(item) if row.stat_id == "explicit.stat_2923486259"]
    assert len(rows) == 1
    assert (rows[0].min_value, rows[0].read_value, rows[0].enabled) == (21.0, 21.0, True)
    assert rows[0].provenance_tags == ("crafted",)


def test_finished_preset_preserves_each_special_origin_when_rows_are_merged():
    item = ParsedItem(
        item_class="Gloves", rarity="rare", name="Test", base_type="Grand Bracers",
        category="gloves", flags=("crafted", "fractured"), modifiers=(
            ItemModifier(
                "Crafted Chaos Resistance", (6.0,), kind="crafted",
                stat_id="crafted.stat_2923486259",
            ),
            ItemModifier(
                "Fractured Chaos Resistance", (15.0,), kind="fractured",
                stat_id="fractured.stat_2923486259",
            ),
        ),
    )
    row = next(
        row for row in poe2_trade_filters(item)
        if row.stat_id == "explicit.stat_2923486259"
    )
    assert row.provenance_tags == ("crafted", "fractured")


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

    def fake_cached_request(url, payload=None, **kwargs):
        assert "/api/trade2/search/Runes%20of%20Aldur" in url
        assert payload["query"]["name"] == "Mageblood"
        assert kwargs == {"prevent_queue": True}
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


def test_phase45_search_prices_omits_mod_provenance_state_filters(monkeypatch):
    item = _phase45_item("phase45_runemastered_ja.txt")
    rows = tuple(
        replace(row, enabled=True) for row in poe2_trade_filters(item)
    )

    def fake_cached_request(url, payload=None, **kwargs):
        assert "/api/trade2/search/Standard" in url
        assert kwargs == {"prevent_queue": True}
        misc = payload["query"]["filters"]["misc_filters"]["filters"]
        assert "desecrated" not in misc
        assert "fractured_item" not in misc
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


@pytest.mark.parametrize(("selection", "expected"), [
    ("only", {"option": "true"}),
    (False, {"option": "false"}),
    (True, None),
])
def test_search_prices_sends_three_state_sanctified_filter(
    monkeypatch, selection, expected,
):
    item = _phase45_item("phase45_sceptre_ja.txt")

    def fake_cached_request(_url, payload=None, **kwargs):
        assert kwargs == {"prevent_queue": True}
        misc = payload["query"].get("filters", {}).get(
            "misc_filters", {},
        ).get("filters", {})
        assert misc.get("sanctified") == expected
        return {"id": "sanctified-query", "result": []}, {}, False

    monkeypatch.setattr(
        "src.poetore.poe2.trade._cached_request_json", fake_cached_request,
    )
    result = search_prices(
        item, "Standard", include_sanctified=selection,
    )
    assert result.query_id == "sanctified-query"


def test_poe2_price_search_fetches_only_top_twenty_even_for_one_seller(monkeypatch):
    item = parse_item_text(_unique_fixture()["text"])
    ids = [f"listing-{index}" for index in range(30)]
    calls = []

    def fake_cached_request(url, payload=None, **kwargs):
        calls.append((url, kwargs))
        if "/search/" in url:
            assert kwargs == {"prevent_queue": True}
            return {"id": "query-id", "result": ids}, {}, False
        assert kwargs == {}
        fetched_ids = url.split("/fetch/", 1)[1].split("?", 1)[0].split(",")
        return {"result": [{
            "listing": {
                "price": {"amount": 10, "currency": "divine"},
                "account": {"name": "same-seller"},
            },
            "item": {"baseType": "Utility Belt"},
        } for _item_id in fetched_ids]}, {}, False

    monkeypatch.setattr(
        "src.poetore.poe2.trade._cached_request_json", fake_cached_request,
    )
    result = search_prices(item, "Standard")

    assert len(calls) == 3
    assert sum("/fetch/" in url for url, _kwargs in calls) == 2
    assert len(result.listings) == 1
    assert result.listings[0].listed_times == 20


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
    assert "ilvl" not in type_filters
    assert type_filters["rarity"] == {"option": "nonunique"}

    with_item_level = build_search_query(item, item_level_min=80, item_level_max=84)
    assert with_item_level["query"]["filters"]["type_filters"]["filters"]["ilvl"] == {
        "min": 80, "max": 84,
    }

    with_quality = build_search_query(item, quality_min=20)
    assert with_quality["query"]["filters"]["type_filters"]["filters"]["quality"] == {
        "min": 20
    }


@pytest.mark.parametrize(
    "properties",
    (
        {
            "物理ダメージ": "29-53",
            "火ダメージ": "19-29 (fire)",
            "冷気ダメージ": "10-20 (cold)",
            "雷ダメージ": "1-9 (lightning)",
            "秒間アタック回数": "1.60",
        },
        {
            "Physical Damage": "29-53",
            "Fire Damage": "19-29 (fire)",
            "Cold Damage": "10-20 (cold)",
            "Lightning Damage": "1-9 (lightning)",
            "Attacks per Second": "1.60",
        },
    ),
)
def test_poe2_individual_elemental_damage_properties_build_edps_and_total_dps(
    properties,
):
    item = ParsedItem(
        item_class="Spears", rarity="rare", name="Test Spear",
        base_type="Seaglass Spear", category="spear", properties=properties,
    )

    rows = {row.stat_id: row for row in poe2_trade_filters(item)}
    assert rows["property.physical_dps"].read_value == pytest.approx(78.72)
    assert rows["property.elemental_dps"].read_value == pytest.approx(70.4)
    assert rows["property.total_dps"].read_value == pytest.approx(149.12)
    assert rows["property.total_dps"].enabled is True
    assert rows["property.physical_dps"].enabled is False
    assert rows["property.elemental_dps"].enabled is False

    payload = build_search_query(item, stat_filters=tuple(rows.values()))
    equipment = payload["query"]["filters"]["equipment_filters"]["filters"]
    assert equipment["dps"]["min"] == pytest.approx(149.12)
    assert "pdps" not in equipment
    assert "edps" not in equipment


def test_poe2_single_elemental_damage_property_enables_edps_filter():
    item = ParsedItem(
        item_class="Spears", rarity="rare", name="Test Spear",
        base_type="Seaglass Spear", category="spear",
        properties={
            "火ダメージ": "19-29 (fire)",
            "秒間アタック回数": "1.60",
        },
    )
    rows = poe2_trade_filters(item)
    edps = next(row for row in rows if row.stat_id == "property.elemental_dps")
    assert edps.read_value == pytest.approx(38.4)
    assert edps.enabled is True

    payload = build_search_query(item, stat_filters=rows)
    equipment = payload["query"]["filters"]["equipment_filters"]["filters"]
    assert equipment["edps"]["min"] == pytest.approx(38.4)


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


def _phase6_items():
    rows = json.loads(PHASE6_FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    return {row["id"]: (row, parse_item_text(row["text"])) for row in rows}


def test_phase6_special_categories_build_exact_trade2_queries():
    for row, item in _phase6_items().values():
        payload = build_search_query(item, stat_filters=_phase45_rows(item))
        assert payload["query"]["type"] == row["base_type"]
        assert payload["query"]["filters"]["type_filters"]["filters"]["category"] == {
            "option": row["trade_category"],
        }
        if "name" in row:
            assert payload["query"]["name"] == row["name"]


def test_phase6_relic_barya_and_ultimatum_send_dedicated_filters():
    items = {key: item for key, (_row, item) in _phase6_items().items()}

    relic = build_search_query(items["sanctum_relic"], stat_filters=_phase45_rows(items["sanctum_relic"]))
    assert relic["query"]["stats"][0]["filters"] == [
        {"id": "sanctum.stat_4057192895", "value": {"min": 5.0}},
    ]

    barya_rows = poe2_search_filters(items["djinn_barya"])
    barya_area = next(row for row in barya_rows if row.stat_id == "property.area_level")
    assert barya_area.enabled
    assert barya_area.exact
    barya = build_search_query(items["djinn_barya"], stat_filters=barya_rows)
    assert barya["query"]["filters"]["misc_filters"]["filters"]["area_level"] == {
        "min": 80.0,
    }

    ultimatum_rows = poe2_search_filters(items["inscribed_ultimatum"])
    hint = next(row for row in ultimatum_rows if row.stat_id == "property.ultimatum_hint")
    assert not hint.enabled
    enabled_rows = tuple(
        row.__class__(**{**row.__dict__, "enabled": True})
        if row.stat_id == "property.ultimatum_hint" else row
        for row in ultimatum_rows
    )
    ultimatum = build_search_query(items["inscribed_ultimatum"], stat_filters=enabled_rows)
    assert ultimatum["query"]["filters"]["map_filters"]["filters"]["ultimatum_hint"] == {
        "option": "Deadly",
    }

    tablet_rows = poe2_trade_filters(items["normal_tablet"])
    uses = next(row for row in tablet_rows if row.stat_id == "pseudo.pseudo_number_of_uses_remaining")
    assert (uses.min_value, uses.enabled) == (10.0, True)
    tablet = build_search_query(items["normal_tablet"], stat_filters=tablet_rows)
    assert {"id": "pseudo.pseudo_number_of_uses_remaining", "value": {"min": 10.0}} in (
        tablet["query"]["stats"][0]["filters"]
    )


def test_phase7_weapon_and_armour_calculated_properties_use_trade2_equipment_filters():
    fixtures = Path(__file__).parent / "fixtures" / "poe2"
    spear = parse_item_text((fixtures / "rare_spear_ja.txt").read_text(encoding="utf-8"))
    spear_rows = poe2_trade_filters(spear)
    by_id = {row.stat_id: row for row in spear_rows}
    assert by_id["property.physical_dps"].enabled
    assert by_id["property.physical_dps"].read_value == pytest.approx(241.325)
    assert by_id["property.physical_dps"].min_value == pytest.approx(241.325)
    assert not by_id["property.aps"].enabled
    spear_query = build_search_query(spear, stat_filters=spear_rows)
    equipment = spear_query["query"]["filters"]["equipment_filters"]["filters"]
    assert equipment["pdps"]["min"] == pytest.approx(241.325)
    assert "aps" not in equipment

    armour = parse_item_text((fixtures / "rare_body_armour_ja.txt").read_text(encoding="utf-8"))
    armour_rows = poe2_trade_filters(armour)
    evasion = next(row for row in armour_rows if row.stat_id == "property.evasion")
    assert evasion.enabled
    assert evasion.read_value == pytest.approx(3090.0)
    armour_query = build_search_query(armour, stat_filters=armour_rows)
    assert (
        armour_query["query"]["filters"]["equipment_filters"]["filters"]["ev"]["min"]
        == pytest.approx(3090.0)
    )


def test_phase7_pseudo_replaces_direct_chaos_filter_without_duplicate_constraint():
    item = parse_item_text(
        (Path(__file__).parent / "fixtures" / "poe2" / "rare_body_armour_ja.txt").read_text(
            encoding="utf-8"
        )
    )
    rows = poe2_trade_filters(item)
    direct = next(row for row in rows if row.stat_id == "explicit.stat_2923486259")
    pseudo = next(row for row in rows if row.stat_id == "pseudo.pseudo_total_chaos_resistance")
    assert not direct.enabled
    assert pseudo.enabled and pseudo.min_value == 21.0
    query = build_search_query(item, stat_filters=rows)
    sent = query["query"]["stats"][0]["filters"]
    assert {"id": "pseudo.pseudo_total_chaos_resistance", "value": {"min": 21.0}} in sent
    assert not any(row["id"] == "crafted.stat_2923486259" for row in sent)


def test_phase7_elemental_and_life_pseudos_sum_shared_sources_once():
    item = ParsedItem(
        item_class="Rings", rarity="rare", name="Test", base_type="Prismatic Ring",
        category="ring", modifiers=(
            ItemModifier("all res", (10.0,), ref="#% to all Elemental Resistances", stat_id="explicit.all"),
            ItemModifier("fire res", (15.0,), ref="#% to Fire Resistance", stat_id="explicit.fire"),
            ItemModifier("life", (100.0,), ref="# to maximum Life", stat_id="explicit.life"),
            ItemModifier("strength", (20.0,), ref="# to Strength", stat_id="explicit.str"),
        ),
    )
    rows = poe2_trade_filters(item)
    by_id = {row.stat_id: row for row in rows}
    assert by_id["pseudo.pseudo_total_elemental_resistance"].min_value == 45.0
    assert by_id["pseudo.pseudo_total_life"].min_value == 140.0
    assert by_id["pseudo.pseudo_total_elemental_resistance"].enabled
    assert by_id["pseudo.pseudo_total_life"].enabled
    assert not by_id["explicit.all"].enabled
    assert not by_id["explicit.fire"].enabled
    assert not by_id["explicit.life"].enabled
    assert not by_id["explicit.str"].enabled


def test_phase7_virtual_augment_uses_only_empty_sockets_and_sends_rune_stat():
    item = _phase45_item("phase45_sceptre_ja.txt")
    assert empty_augment_socket_count(item) == 1
    assert augment_socket_edit_counts(item) == (
        (1, "空き1個に追加"), (2, "全2個を置換"),
    )
    choices = available_virtual_augments(item)
    adept = next(row for row in choices if row["ref_name"] == "Adept Rune")
    assert adept["names"]["ja"]
    rows = virtual_augment_filters(item, "Adept Rune")
    assert len(rows) == 1
    assert rows[0].kind == "virtual-rune"
    assert rows[0].min_value == 9.0
    payload = build_search_query(item, stat_filters=poe2_trade_filters(item, "Adept Rune"))
    sent = payload["query"]["stats"][0]["filters"]
    assert any(row["id"].startswith("rune.") and row.get("value") == {"min": 9.0} for row in sent)

    replacement = poe2_trade_filters(item, "Adept Rune", PRESET_FINISHED, 2)
    assert all(not row.enabled for row in replacement if row.kind == "augment")
    replacement_virtual = next(row for row in replacement if row.kind == "virtual-rune")
    assert replacement_virtual.min_value == 18.0

    body = item.__class__(**{
        **item.__dict__,
        "category": "body_armour",
        "properties": {**item.properties, "Sockets": "S S"},
        "augment_count": 0,
    })
    greater_iron = next(
        row for row in available_virtual_augments(body)
        if row["ref_name"] == "Greater Iron Rune"
    )
    assert virtual_augment_choice_label(body, greater_iron) == (
        "アーマー、回避力およびエナジーシールドが36%増加する"
        "（鉄のグレータールーン ×2）"
    )

    corrupted = item.__class__(**{**item.__dict__, "flags": (*item.flags, "corrupted")})
    assert empty_augment_socket_count(corrupted) == 1
    assert available_virtual_augments(corrupted)

    unique = item.__class__(**{**item.__dict__, "rarity": "unique"})
    assert empty_augment_socket_count(unique) == 0
    assert not available_virtual_augments(unique)

    mirrored = item.__class__(**{**item.__dict__, "flags": (*item.flags, "mirrored")})
    assert empty_augment_socket_count(mirrored) == 0
    assert not available_virtual_augments(mirrored)

    wand = item.__class__(**{**item.__dict__, "category": "wand"})
    body_rune = virtual_augment_filters(wand, "Body Rune")
    assert len(body_rune) == 1
    assert body_rune[0].alternative_stat_ids
    wand_payload = build_search_query(
        wand, stat_filters=poe2_trade_filters(wand, "Body Rune"),
    )
    groups = wand_payload["query"]["stats"]
    alternate = next(group for group in groups if group["type"] == "count")
    assert alternate["value"] == {"min": 1}
    assert len(alternate["filters"]) == 2


def test_augment_socket_filter_stays_off_for_non_exceptional_equipment():
    item = _phase45_item("phase45_sceptre_ja.txt")
    row = next(
        row for row in poe2_search_filters(item)
        if row.stat_id == "property.augment_sockets"
    )
    assert not row.enabled


def test_virtual_augments_group_elemental_resistances_and_sort_tiers_descending():
    item = _phase45_item("phase45_sceptre_ja.txt")
    body = item.__class__(**{
        **item.__dict__,
        "category": "body_armour",
        "properties": {**item.properties, "Sockets": "S S"},
        "augment_count": 0,
    })
    refs = [row["ref_name"] for row in available_virtual_augments(body)]

    iron = [
        "Perfect Iron Rune", "Greater Iron Rune", "Iron Rune", "Lesser Iron Rune",
    ]
    elemental = [
        "Perfect Desert Rune", "Greater Desert Rune", "Desert Rune", "Lesser Desert Rune",
        "Perfect Glacial Rune", "Greater Glacial Rune", "Glacial Rune", "Lesser Glacial Rune",
        "Perfect Storm Rune", "Greater Storm Rune", "Storm Rune", "Lesser Storm Rune",
    ]
    assert [ref for ref in refs if ref in iron] == iron
    assert [ref for ref in refs if ref in elemental] == elemental
    positions = [refs.index(ref) for ref in elemental]
    assert positions == list(range(min(positions), max(positions) + 1))


def test_phase7_unique_roll_range_reaches_shared_editable_filter_model():
    item = parse_item_text(
        (Path(__file__).parent / "fixtures" / "poe2" / "mageblood_ja.txt").read_text(
            encoding="utf-8"
        )
    )
    row = next(
        row for row in poe2_trade_filters(item)
        if row.stat_id == "explicit.stat_3874491706"
    )
    assert (row.read_value, row.roll_min, row.roll_max, row.better) == (43.0, 25.0, 50.0, 1)


def test_phase6_special_items_open_japanese_trade_with_localized_identity():
    items = {key: item for key, (_row, item) in _phase6_items().items()}
    expected = {
        "unique_charm": ("ヴァラコの雄叫び", "トパーズチャーム"),
        "unique_tablet": ("予期せぬ結果", "アビスの石板"),
        "unique_relic": ("最後の炎", "香のレリック"),
        "unique_timelost_jewel": ("闇との対立", "タイムロストダイヤモンド"),
    }
    for fixture_id, (name, base_type) in expected.items():
        item = items[fixture_id]
        payload = build_search_query(item, stat_filters=poe2_search_filters(item))
        url = build_web_trade_url(item, "Standard", payload, "english-query-id")
        assert urlparse(url).netloc == "jp.pathofexile.com"
        query = _web_payload(url)["query"]
        assert query["name"] == name
        assert query["type"] == base_type


def test_phase45_equipment_properties_use_official_filter_groups_without_inline_state():
    item = _phase45_item("phase45_sceptre_ja.txt")
    rows = _phase45_rows(item)
    payload = build_search_query(item, stat_filters=rows)
    filters = payload["query"]["filters"]
    assert filters["equipment_filters"]["filters"] == {
        "spirit": {"min": 100.0},
        "rune_sockets": {"min": 2.0},
    }
    assert "misc_filters" not in filters
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


def test_reported_magic_waystone_uses_tier_packsize_bonus_and_three_mods():
    item = _phase45_item("magic_waystone_ja.txt")
    modifier_rows = tuple(
        TradeStatFilter(
            mod.stat_id, mod.text, trade_stat_value(mod.values), mod.kind,
            enabled=True, ref=mod.ref, confidence=mod.confidence,
        )
        for mod in item.modifiers
    )
    property_rows = tuple(
        row.__class__(**{**row.__dict__, "enabled": True})
        for row in poe2_search_filters(item)
    )
    payload = build_search_query(item, stat_filters=modifier_rows + property_rows)
    assert payload["query"]["type"] == "Waystone (Tier 15)"
    assert payload["query"]["filters"]["map_filters"]["filters"] == {
        "map_revives": {"min": 4.0},
        "map_packsize": {"min": 16.0},
        "map_bonus": {"min": 30.0},
        "map_tier": {"min": 15.0, "max": 15.0},
    }
    assert [row["id"] for row in payload["query"]["stats"][0]["filters"]] == [
        "explicit.stat_2753083623",
        "explicit.stat_57326096",
        "explicit.stat_3477720557",
    ]


def test_reported_rare_waystone_sends_tier_base_instead_of_affix_name():
    item = _phase45_item("rare_waystone_ja.txt")
    rows = _phase45_rows(item)
    payload = build_search_query(item, stat_filters=rows)

    assert payload["query"]["type"] == "Waystone (Tier 15)"
    assert payload["query"].get("name") != "先祖の突撃"


@pytest.mark.parametrize(
    ("item_class", "affixed_name", "expected_type"),
    [
        ("Focus", "Pulsing Antler Focus", "Antler Focus"),
        ("Two Hand Mace", "Reaver's Temple Maul of Stunning", "Temple Maul"),
        ("指輪", "火炎の アメジストの指輪", "Amethyst Ring"),
        ("鎧", "幻術の スリップストライクベスト", "Slipstrike Vest"),
    ],
)
def test_magic_trade_query_never_sends_affixed_display_name_as_type(
    item_class, affixed_name, expected_type,
):
    item = parse_item_text(
        f"アイテムクラス: {item_class}\nレアリティ: マジック\n"
        f"{affixed_name}\n--------\nアイテムレベル: 80\n"
    )
    payload = build_search_query(item)

    assert payload["query"]["type"] == expected_type
    assert payload["query"]["type"] != affixed_name


def test_phase45_runemastered_normalizes_special_mods_without_state_filters():
    item = _phase45_item("phase45_runemastered_ja.txt")
    rows = tuple(
        replace(row, enabled=True) for row in poe2_trade_filters(item)
    )
    payload = build_search_query(item, stat_filters=rows)
    assert payload["query"]["type"] == "Runemastered Vaal Cuirass"
    assert payload["query"]["filters"]["equipment_filters"]["filters"]["ward"] == {
        "min": 500.0
    }
    misc = payload["query"]["filters"].get("misc_filters", {}).get("filters", {})
    assert "desecrated" not in misc
    assert "fractured_item" not in misc
    sent = payload["query"]["stats"][0]["filters"]
    assert {
        "id": "explicit.stat_2923486259", "value": {"min": 21.0},
    } in sent
    assert not any(row["id"].startswith(("desecrated.", "fractured.")) for row in sent)


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


def test_poe2_gem_socket_property_counts_g_markers_like_ee2():
    item = parse_item_text("""アイテムクラス: スキルジェム
レアリティ: ジェム
アーク
--------
レベル: 20
ソケット: G G G G
""")
    row = next(row for row in poe2_search_filters(item) if row.stat_id == "property.gem_sockets")
    assert row.min_value == 4


@pytest.mark.parametrize(
    ("item_class", "base_type", "category"),
    [
        ("Life Flasks", "Ultimate Life Flask", "flask.life"),
        ("Mana Flasks", "Ultimate Mana Flask", "flask.mana"),
        ("Expedition Logbooks", "Expedition Logbook", "map.logbook"),
    ],
)
def test_special_poe2_items_use_dedicated_trade2_categories(
    item_class, base_type, category,
):
    item = parse_item_text(
        f"Item Class: {item_class}\nRarity: Normal\n{base_type}\n--------\n"
    )
    query = build_search_query(item)["query"]
    assert query["type"] == base_type
    assert query["filters"]["type_filters"]["filters"]["category"] == {
        "option": category
    }


def test_wombgift_uses_exact_type_without_nonexistent_trade2_category():
    item = parse_item_text(
        "Item Class: Wombgifts\nRarity: Normal\nOrnate Wombgift\n--------\n"
    )
    query = build_search_query(item)["query"]
    assert query["type"] == "Ornate Wombgift"
    assert "category" not in query["filters"]["type_filters"]["filters"]
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {
        "option": "normal"
    }


@pytest.mark.parametrize(
    ("rarity", "exact_base_type", "expected"),
    [
        ("Normal", True, "normal"),
        ("Magic", True, "magic"),
        ("Rare", True, "nonunique"),
        ("Normal", False, "nonunique"),
        ("Magic", False, "nonunique"),
        ("Rare", False, "nonunique"),
    ],
)
def test_poe2_nonunique_rarity_matches_ee2_exact_scope_rules(
    rarity, exact_base_type, expected,
):
    item = parse_item_text(
        f"Item Class: Belts\nRarity: {rarity}\nHeavy Belt\n--------\n"
    )
    query = build_search_query(item, exact_base_type=exact_base_type)["query"]
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {
        "option": expected
    }


def test_shared_trade_options_are_sent_to_trade2_query():
    item = _phase45_item("phase45_gem_ja.txt")
    payload = build_search_query(
        item,
        quality_min=20,
        gem_level_min=19,
        gem_sockets_min=3,
        exact_base_type=False,
        trade_currency="exalted_divine",
        listed_within="3days",
    )
    query = payload["query"]
    assert "type" not in query
    assert query["filters"]["type_filters"]["filters"]["quality"] == {"min": 20}
    assert query["filters"]["misc_filters"]["filters"] == {
        "gem_level": {"min": 19},
        "gem_sockets": {"min": 3},
    }
    assert query["filters"]["trade_filters"]["filters"] == {
        "price": {"option": "exalted_divine"},
        "indexed": {"option": "3days"},
    }


def test_explicit_empty_filter_set_does_not_restore_item_modifiers():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_spear_ja.txt").read_text(
        encoding="utf-8"
    )
    query = build_search_query(parse_item_text(text), stat_filters=())["query"]
    assert query["stats"] == [{"type": "and", "filters": []}]
