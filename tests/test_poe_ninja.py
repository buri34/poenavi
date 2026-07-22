from src.poetore.models import ParsedItem
from src.poetore.poe_ninja import (
    CACHE_TTL_SECONDS, PoeNinjaPrice, PoeNinjaPriceService, match_poe_ninja_price,
)


def _payload():
    return {
        "currencyOverviews": [{
            "type": "Currency", "lines": [
                {"name": "Divine Orb", "chaos": 200, "graph": [0, 1, 2, 3, 4, 5, 6]},
                {"name": "Chaos Orb", "chaos": 1, "graph": [0, -1, -2, -1, 0, 1, 2]},
            ],
        }],
        "itemOverviews": [
            {"type": "UniqueAccessory", "lines": [
                {"name": "Mageblood", "variant": "4 Flasks, Heavy Belt", "chaos": 40000,
                 "graph": [0, 1, 2, 3, 4, 5, 6]},
            ]},
            {"type": "SkillGem", "lines": [
                {"name": "Arc", "variant": "20/20c", "chaos": 60,
                 "graph": [-2, -1, 0, 1, 2, 3, 4]},
            ]},
            {"type": "BlightedMap", "lines": [
                {"name": "Blighted Map (Tier 16)", "variant": "T0, Gen-24", "chaos": 12,
                 "graph": [0, 0, 1, 1, 2, 2, 3]},
            ]},
            {"type": "DivinationCard", "lines": [
                {"name": "The Doctor", "chaos": 1800, "graph": [0, 1, 0, -1, 0, 1, 0]},
            ]},
            {"type": "BaseType", "lines": [
                {"name": "Heavy Belt", "variant": "86+", "chaos": 50, "graph": []},
            ]},
            {"type": "ClusterJewel", "lines": [
                {"name": "12% increased Fire Damage", "variant": "8 passives, 84", "chaos": 80,
                 "graph": []},
            ]},
        ],
    }


def test_unique_price_uses_name_and_formats_divines():
    item = ParsedItem("Belts", "Unique", "Mageblood", "Heavy Belt", "accessory")
    price = match_poe_ninja_price(
        _payload(), item, "Standard", trade_name="Mageblood", trade_base_type="Heavy Belt",
    )
    assert price is not None
    assert price.display_price() == "200 div"
    assert price.graph_points() == (0, 1, 2, 3, 4, 5, 6)
    assert "/unique-accessories/mageblood-4-flasks-heavy-belt" in price.url
    assert price.source_type == "UniqueAccessory"


def test_trend_summary_uses_signed_total_change_instead_of_graph_deviation():
    falling = PoeNinjaPrice(
        "Test", None, 8, (0, 0, 0, 0, 0, 0, -20), "https://example.com",
        total_change=-20,
    )
    rising = PoeNinjaPrice(
        "Test", None, 8, (0, 0, 0, 0, 0, 0, 12), "https://example.com",
        total_change=12,
    )
    assert falling.trend_summary() == ("↘", "-20%")
    assert rising.trend_summary() == ("↗", "+12%")


def test_gem_price_uses_level_quality_and_corruption_variant():
    item = ParsedItem(
        "Skill Gems", "Gem", "Arc", "Arc", "gem",
        properties={"Gem Level": "20", "Quality": "+20%"}, flags=("corrupted",),
    )
    price = match_poe_ninja_price(_payload(), item, "Standard", trade_base_type="Arc")
    assert price is not None and price.name == "Arc" and price.variant == "20/20c"


def test_blighted_map_price_uses_tier_and_state():
    item = ParsedItem(
        "Maps", "Rare", "Map (Tier 16)", "Map (Tier 16)", "map",
        raw_text="Blighted Map (Tier 16)\nArea is infested with Fungal Growth",
    )
    price = match_poe_ninja_price(_payload(), item, "Standard")
    assert price is not None and price.name == "Blighted Map (Tier 16)"


def test_exact_name_item_price_is_supported():
    item = ParsedItem("Divination Cards", "Normal", "The Doctor", "The Doctor", "divination_card")
    price = match_poe_ninja_price(_payload(), item, "Standard", trade_base_type="The Doctor")
    assert price is not None and price.chaos == 1800


def test_duplicate_currency_overviews_are_deduplicated():
    payload = _payload()
    payload["itemOverviews"].append(payload["currencyOverviews"][0])
    item = ParsedItem("Currency", "Currency", "Chaos Orb", "Chaos Orb", "currency")
    price = match_poe_ninja_price(payload, item, "Standard", trade_base_type="Chaos Orb")
    assert price is not None and price.chaos == 1


def test_nonunique_basetype_and_cluster_jewel_are_intentionally_excluded():
    base = ParsedItem("Belts", "Rare", "Test", "Heavy Belt", "accessory", item_level=86)
    cluster = ParsedItem(
        "Cluster Jewels", "Rare", "Test", "Large Cluster Jewel", "cluster_jewel", item_level=84,
    )
    assert match_poe_ninja_price(_payload(), base, "Standard", trade_base_type="Heavy Belt") is None
    assert match_poe_ninja_price(_payload(), cluster, "Standard") is None


def test_service_caches_each_league_for_31_minutes():
    calls = []
    now = [100.0]

    def fetcher(league):
        calls.append(league)
        return _payload()

    service = PoeNinjaPriceService(
        fetcher=fetcher, stash_fetcher=lambda _league, _type: {"lines": []},
        clock=lambda: now[0],
    )
    item = ParsedItem("Divination Cards", "Normal", "The Doctor", "The Doctor", "divination_card")
    assert service.lookup(item, "Standard") is not None
    assert service.lookup(item, "Standard") is not None
    assert calls == ["Standard"]
    now[0] += CACHE_TTL_SECONDS + 1
    assert service.lookup(item, "Standard") is not None
    assert calls == ["Standard", "Standard"]


def test_private_league_is_not_fetched():
    service = PoeNinjaPriceService(fetcher=lambda _league: (_ for _ in ()).throw(AssertionError()))
    item = ParsedItem("Divination Cards", "Normal", "The Doctor", "The Doctor", "divination_card")
    assert service.lookup(item, "My League (PL12345)") is None


def test_service_refreshes_item_price_and_trend_from_current_stash_overview():
    stash_calls = []

    def stash_fetcher(league, type_name):
        stash_calls.append((league, type_name))
        return {"lines": [{
            "detailsId": "mageblood-4-flasks-heavy-belt",
            "chaosValue": 42000,
            "sparkLine": {"totalChange": -20, "data": [0, 0, 0, 0, 0, 0, -20]},
        }]}

    service = PoeNinjaPriceService(fetcher=lambda _league: _payload(), stash_fetcher=stash_fetcher)
    item = ParsedItem("Belts", "Unique", "Mageblood", "Heavy Belt", "accessory")
    price = service.lookup(
        item, "Standard", trade_name="Mageblood", trade_base_type="Heavy Belt",
    )
    assert price is not None
    assert price.chaos == 42000
    assert price.graph_points() == (0, 0, 0, 0, 0, 0, -20)
    assert price.trend_summary() == ("↘", "-20%")
    assert stash_calls == [("Standard", "UniqueAccessory")]
