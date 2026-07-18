from unittest.mock import patch

from src.poetore.parser import parse_item_text
from src.poetore.trade import (
    PriceListing, PriceResult, TradeStatFilter, active_pc_league, build_search_query, elemental_dps, physical_dps,
    resolve_trade_stat_filters, search_prices,
)


ITEM = """Item Class: Two Hand Swords
Rarity: Rare
Doom Sever
Reaver Sword
--------
Two Hand Sword
Physical Damage: 108-181 (augmented)
Attacks per Second: 1.74 (augmented)
--------
Item Level: 67
--------
74% increased Physical Damage
"""


def test_weapon_search_uses_english_base_rarity_and_comparable_pdps():
    item = parse_item_text(ITEM)
    filters = resolve_trade_stat_filters(item)
    query = build_search_query(item, "Reaver Sword", filters)["query"]
    assert query["type"] == "Reaver Sword"
    assert query["filters"]["type_filters"]["filters"]["rarity"]["option"] == "rare"
    assert query["filters"]["weapon_filters"]["filters"]["pdps"]["min"] == 226.3
    assert round(physical_dps(item), 2) == 251.43


def test_mixed_weapon_selects_total_dps_and_dominant_component_only():
    item = parse_item_text(ITEM.replace(
        "Physical Damage: 108-181 (augmented)",
        "Physical Damage: 108-181 (augmented)\nElemental Damage: 10-20, 20-30",
    ))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    enabled = {row.stat_id: row.min_value for row in filters if row.enabled}
    assert "property.total_dps" in enabled
    assert "property.physical_dps" in enabled
    assert "property.elemental_dps" not in enabled
    assert round(elemental_dps(item), 2) == 69.6


def test_non_physical_weapon_does_not_enable_pdps():
    item = parse_item_text(ITEM.replace("Two Hand Swords", "Wands"))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    assert not any(row.stat_id == "property.physical_dps" and row.enabled for row in filters)


def test_single_defence_armour_is_enabled_but_hybrid_is_not():
    single = parse_item_text(ITEM.replace("Two Hand Swords", "Body Armours").replace(
        "Physical Damage: 108-181 (augmented)\nAttacks per Second: 1.74 (augmented)",
        "Armour: 1000",
    ))
    hybrid = parse_item_text(single.raw_text.replace("Armour: 1000", "Armour: 1000\nEvasion Rating: 500"))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        assert [(row.stat_id, row.min_value) for row in resolve_trade_stat_filters(single) if row.enabled] == [
            ("property.armour", 900.0),
        ]
        assert not any(row.enabled for row in resolve_trade_stat_filters(hybrid))


def test_armour_also_enables_general_life_pseudo():
    item = parse_item_text(ITEM.replace("Two Hand Swords", "Body Armours").replace(
        "Physical Damage: 108-181 (augmented)\nAttacks per Second: 1.74 (augmented)",
        "Armour: 1000",
    ).replace("74% increased Physical Damage", "+80 to maximum Life"))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        enabled = {row.stat_id: row.min_value for row in resolve_trade_stat_filters(item) if row.enabled}
    assert enabled["property.armour"] == 900.0
    assert enabled["pseudo.pseudo_total_life"] == 72.0


def test_accessory_enables_aggregated_life_and_resistance_pseudos():
    item = parse_item_text("""Item Class: Rings
Rarity: Rare
Test Ring
Ruby Ring
--------
Item Level: 85
--------
+70 to maximum Life
+30% to Fire Resistance
+20% to Cold and Lightning Resistances
+10% to Chaos Resistance
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    enabled = {row.stat_id: row.min_value for row in filters if row.enabled}
    assert enabled == {
        "pseudo.pseudo_total_life": 63.0,
        "pseudo.pseudo_total_elemental_resistance": 63.0,
        "pseudo.pseudo_total_chaos_resistance": 9.0,
    }


def test_enabled_stat_filter_is_added_with_editable_minimum():
    item = parse_item_text(ITEM)
    stat = TradeStatFilter("explicit.stat_1", "Physical", 74, "prefix", True)
    query = build_search_query(item, "Reaver Sword", (stat,))["query"]
    assert query["stats"][0]["filters"] == [
        {"id": "explicit.stat_1", "value": {"min": 74}},
    ]


def test_japanese_modifier_resolves_to_official_trade_stat_id():
    item = parse_item_text(ITEM.replace("74% increased Physical Damage", "物理ダメージが74%\u5897加する"))
    entries = ({"id": "explicit.stat_1509134228", "text": "物理ダメージが#%増加する", "type": "explicit"},)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert filters[-1] == TradeStatFilter(
        "explicit.stat_1509134228", "物理ダメージが74%増加する", 74, "explicit", False,
    )


def test_hybrid_and_duplicate_stats_resolve_with_correct_values_and_sum():
    item = parse_item_text("""アイテムクラス: 両手剣
レアリティ: レア
地獄の破滅
略奪者の剣
--------
アイテムレベル: 67
--------
{ プレフィックスモッド「引き裂く者」(ティア: 6) }
物理ダメージが30(25-34)%増加する
命中力 +55(47-72)
{ プレフィックスモッド「重い」(ティア: 8) }
物理ダメージが44(40-49)%増加する
{ サフィックスモッド「吸収の」(ティア: 6) }
倒した敵1体ごとに4(4-6)のマナを獲得する
""")
    entries = (
        {"id": "explicit.phys", "text": "物理ダメージが#%増加する", "type": "explicit"},
        {"id": "explicit.accuracy", "text": "命中力 +# (ローカル)", "type": "explicit"},
        {"id": "explicit.mana", "text": "倒した敵1体ごとに#のマナを獲得する", "type": "explicit"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert [(row.stat_id, row.min_value) for row in filters] == [
        ("explicit.phys", 74), ("explicit.accuracy", 55), ("explicit.mana", 4),
    ]
    assert filters[0].text.endswith("(2行合計)")


def test_active_pc_league_skips_permanent_and_hard_modes():
    payload = {"result": [
        {"id": "Hardcore Mirage", "realm": "pc"},
        {"id": "Mirage", "realm": "pc"},
        {"id": "Standard", "realm": "pc"},
    ]}
    with patch("src.poetore.trade._request_json", return_value=(payload, {})):
        assert active_pc_league() == "Mirage"


def test_price_result_calculates_median_per_currency():
    result = PriceResult("Mirage", "q", 3, (
        PriceListing(3, "chaos"), PriceListing(7, "chaos"), PriceListing(1, "divine")
    ))
    assert result.median_by_currency() == {"chaos": 5, "divine": 1}


def test_search_prices_keeps_item_and_seller_for_list_display():
    search = ({"id": "query1", "result": ["item1"]}, {"X-Rate-Limit-Ip-State": "1:10:0"})
    fetch = ({"result": [{
        "listing": {"price": {"amount": 4, "currency": "chaos"}, "account": {"name": "seller"}},
        "item": {"name": "Doom Sever", "baseType": "Reaver Sword"},
    }]}, {})
    with patch("src.poetore.trade._request_json", side_effect=[search, fetch]):
        result = search_prices(parse_item_text(ITEM), "Reaver Sword", "Mirage")
    assert result.listings == (
        PriceListing(4, "chaos", "seller", "Doom Sever", "Reaver Sword"),
    )
