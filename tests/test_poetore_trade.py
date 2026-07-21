from io import BytesIO
from dataclasses import replace
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from src.poetore.parser import parse_item_text
from src.poetore.models import ItemModifier, ParsedItem
from src.poetore.trade import (
    PRESET_BASE, PRESET_FINISHED, PriceListing, PriceResult, TradeStatFilter,
    active_pc_league, available_pc_leagues, available_trade_presets, build_search_query,
    default_pc_league, elemental_dps,
    default_trade_currency, physical_dps, physical_dps_at_20_quality,
    resolve_trade_stat_filters, search_prices, unique_candidates, unique_variants,
)
from src.poetore.trade import _request_json
from src.poetore.trade import _base_defence_percentile
from src.poetore.trade import _trade_response_cache


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


def test_trade_api_retries_429_once_using_retry_after():
    error = HTTPError(
        "https://example.invalid", 429, "rate limited", {"Retry-After": "2"},
        BytesIO(b'{}'),
    )
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = b'{"ok": true}'
    response.headers = {"X-Rate-Limit-Ip-State": "1:10:0"}
    with patch("src.poetore.trade.urlopen", side_effect=[error, response]), patch(
        "src.poetore.trade.time.sleep"
    ) as sleep:
        payload, headers = _request_json("https://example.invalid")
    assert payload == {"ok": True}
    assert headers["X-Rate-Limit-Ip-State"] == "1:10:0"
    sleep.assert_called_once_with(2.0)


def test_weapon_search_uses_english_base_rarity_and_comparable_pdps():
    item = parse_item_text(ITEM)
    filters = resolve_trade_stat_filters(item)
    query = build_search_query(item, "Reaver Sword", filters)["query"]
    assert query["type"] == "Reaver Sword"
    assert query["filters"]["type_filters"]["filters"]["rarity"]["option"] == "rare"
    assert query["filters"]["weapon_filters"]["filters"]["pdps"]["min"] == 271.5
    assert query["status"]["option"] == "securable"
    assert round(physical_dps(item), 2) == 251.43
    assert round(physical_dps_at_20_quality(item), 2) == 301.72


def test_normal_equipment_defaults_to_any_currency():
    item = parse_item_text(ITEM)
    assert default_trade_currency(item) == "any"
    query = build_search_query(item, "Reaver Sword")["query"]
    assert "trade_filters" not in query["filters"]


def test_consumable_craftable_item_defaults_to_chaos_and_divine():
    item = parse_item_text("""Item Class: Expedition Logbooks
Rarity: Rare
Test Logbook
Expedition Logbook
--------
Item Level: 83
""")
    assert item.category == "expedition_logbook"
    assert default_trade_currency(item) == "chaos_divine"
    query = build_search_query(item, trade_currency=default_trade_currency(item))["query"]
    assert query["filters"]["trade_filters"]["filters"]["price"] == {
        "option": "chaos_divine"
    }


def test_unique_item_defaults_to_any_currency_even_when_not_craftable():
    item = parse_item_text("""Item Class: Flasks
Rarity: Unique
Test Flask
Silver Flask
--------
Item Level: 80
""")
    assert default_trade_currency(item) == "any"


def test_all_supported_trade_currency_options_map_to_api_values():
    item = parse_item_text(ITEM)
    expected = {
        "chaos": "chaos", "divine": "divine", "chaos_divine": "chaos_divine",
    }
    for selected, api_value in expected.items():
        query = build_search_query(item, trade_currency=selected)["query"]
        assert query["filters"]["trade_filters"]["filters"]["price"]["option"] == api_value


def test_stat_filter_supports_maximum_exact_and_trade_inversion():
    item = parse_item_text(ITEM)
    filters = (
        TradeStatFilter("explicit.low", "低いほど良い", None, "suffix", True, 12),
        TradeStatFilter("explicit.exact", "完全一致", 3, "suffix", True, 3),
        TradeStatFilter("explicit.inverted", "API符号反転", 10, "suffix", True, 20, None, 1.0, True),
    )
    query = build_search_query(item, "Reaver Sword", filters)["query"]
    assert query["stats"][0]["filters"] == [
        {"id": "explicit.low", "value": {"max": 12}},
        {"id": "explicit.exact", "value": {"min": 3, "max": 3}},
        {"id": "explicit.inverted", "value": {"min": -20, "max": -10}},
    ]


def test_high_item_level_unfinished_rare_has_finished_and_base_presets():
    item = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 85"))
    assert available_trade_presets(item) == (PRESET_FINISHED, PRESET_BASE)
    assert resolve_trade_stat_filters(item, PRESET_BASE) == (
        TradeStatFilter(
            "property.item_level", "アイテムレベル", 85.0, "base", True,
            read_value=85.0,
            selection_reason="クラフト価値のあるアイテムレベル",
        ),
    )


def test_base_preset_uses_exact_base_nonunique_ilvl_and_craftable_state():
    item = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 88"))
    filters = resolve_trade_stat_filters(item, PRESET_BASE)
    query = build_search_query(
        item, "Reaver Sword", filters, preset=PRESET_BASE,
    )["query"]
    assert query["type"] == "Reaver Sword"
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "nonunique"}
    misc = query["filters"]["misc_filters"]["filters"]
    assert misc["ilvl"] == {"min": 86.0}
    assert misc["corrupted"] == {"option": "false"}
    assert misc["mirrored"] == {"option": "false"}
    assert query["stats"][0]["filters"] == []


def test_finished_or_low_level_items_do_not_offer_base_preset():
    low_level = parse_item_text(ITEM)
    crafted = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 85").replace(
        "74% increased Physical Damage", "+50 to maximum Life (crafted)",
    ))
    quality_20 = parse_item_text(ITEM.replace(
        "Physical Damage: 108-181 (augmented)",
        "Quality: +20% (augmented)\nPhysical Damage: 108-181 (augmented)",
    ).replace("Item Level: 67", "Item Level: 85"))
    corrupted = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 85").replace(
        "74% increased Physical Damage", "74% increased Physical Damage\nCorrupted",
    ))
    for item in (low_level, crafted, quality_20, corrupted):
        assert available_trade_presets(item) == (PRESET_FINISHED,)


def test_fractured_item_can_offer_base_preset_below_ilvl_82():
    item = parse_item_text(ITEM.replace(
        "74% increased Physical Damage",
        '{ Fractured Prefix Modifier }\n74% increased Physical Damage',
    ))
    entries = ({
        "id": "fractured.phys", "text": "#% increased Physical Damage", "type": "fractured",
    },)
    assert available_trade_presets(item) == (PRESET_FINISHED, PRESET_BASE)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item, PRESET_BASE)
    assert filters == (
        TradeStatFilter(
            "property.item_level", "アイテムレベル", 67.0, "base", True,
            read_value=67.0,
            selection_reason="クラフト価値のあるアイテムレベル",
        ),
        TradeStatFilter(
            "fractured.phys", "74% increased Physical Damage", 74.0, "fractured", True,
            selection_reason="アイテム種別に応じた主要条件",
        ),
        TradeStatFilter(
            "pseudo.pseudo_number_of_empty_prefix_mods", "空きPrefix枠（現在2枠）",
            1.0, "craft", False, selection_reason="候補として表示（初期未選択）",
        ),
        TradeStatFilter(
            "pseudo.pseudo_number_of_empty_suffix_mods", "空きSuffix枠（現在3枠）",
            1.0, "craft", False, selection_reason="候補として表示（初期未選択）",
        ),
    )
    query = build_search_query(item, "Reaver Sword", filters, preset=PRESET_BASE)["query"]
    misc = query["filters"]["misc_filters"]["filters"]
    assert misc["fractured_item"] == {"option": "true"}
    assert misc["synthesised_item"] == {"option": "false"}
    assert query["stats"][0]["filters"] == [
        {"id": "fractured.phys", "value": {"min": 74.0}},
    ]


def test_influenced_and_synthesised_items_add_strict_base_conditions():
    item = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 70").replace(
        "74% increased Physical Damage",
        "74% increased Physical Damage\nShaper Item\nElder Item\nSynthesised Item",
    ))
    assert available_trade_presets(item) == (PRESET_FINISHED, PRESET_BASE)
    filters = resolve_trade_stat_filters(item, PRESET_BASE)
    assert [(row.stat_id, row.enabled) for row in filters] == [
        ("property.item_level", True),
        ("pseudo.pseudo_has_shaper_influence", True),
        ("pseudo.pseudo_has_elder_influence", True),
    ]
    query = build_search_query(item, "Reaver Sword", filters, preset=PRESET_BASE)["query"]
    assert query["filters"]["misc_filters"]["filters"]["synthesised_item"] == {"option": "true"}
    assert query["filters"]["misc_filters"]["filters"]["fractured_item"] == {"option": "false"}
    assert query["stats"][0]["filters"] == [
        {"id": "pseudo.pseudo_has_shaper_influence", "value": {}},
        {"id": "pseudo.pseudo_has_elder_influence", "value": {}},
    ]


def test_base_preset_preselects_t1_t2_but_not_lower_tiers():
    item = parse_item_text("""アイテムクラス: 指輪
レアリティ: レア
試作品
ルビーの指輪
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「健康な」 (ティア: 1) }
最大ライフ +100(90-100)
{ プレフィックスモッド「普通の」 (ティア: 3) }
最大マナ +50(45-55)
{ サフィックスモッド「火炎の」 (ティア: 2) }
火耐性 +40(36-41)%
""")
    entries = (
        {"id": "explicit.life", "text": "最大ライフ +#", "type": "explicit"},
        {"id": "explicit.mana", "text": "最大マナ +#", "type": "explicit"},
        {"id": "explicit.fire", "text": "火耐性 +#%", "type": "explicit"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item, PRESET_BASE)
    enabled = [(row.stat_id, row.min_value) for row in filters if row.enabled]
    assert enabled == [
        ("property.item_level", 85.0),
        ("explicit.life", 100.0),
        ("explicit.fire", 40.0),
    ]
    assert not any(row.stat_id == "explicit.mana" for row in filters)
    empty = {row.stat_id: row.text for row in filters if row.kind == "craft"}
    assert empty == {
        "pseudo.pseudo_number_of_empty_prefix_mods": "空きPrefix枠（現在1枠）",
        "pseudo.pseudo_number_of_empty_suffix_mods": "空きSuffix枠（現在2枠）",
    }


def test_finished_preset_does_not_force_special_base_state():
    item = parse_item_text(ITEM.replace(
        "74% increased Physical Damage", "74% increased Physical Damage\nHunter Item",
    ))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item, PRESET_FINISHED)
    query = build_search_query(item, "Reaver Sword", filters, preset=PRESET_FINISHED)["query"]
    misc = query["filters"].get("misc_filters", {}).get("filters", {})
    assert "synthesised_item" not in misc
    assert "fractured_item" not in misc
    assert not any(
        row.get("id") == "pseudo.pseudo_has_hunter_influence"
        for row in query["stats"][0]["filters"]
    )


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


def test_single_and_hybrid_armour_enable_every_present_defence():
    single = parse_item_text(ITEM.replace("Two Hand Swords", "Body Armours").replace(
        "Physical Damage: 108-181 (augmented)\nAttacks per Second: 1.74 (augmented)",
        "Armour: 1000",
    ))
    hybrid = parse_item_text(single.raw_text.replace("Armour: 1000", "Armour: 1000\nEvasion Rating: 500"))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        assert [(row.stat_id, row.min_value) for row in resolve_trade_stat_filters(single) if row.enabled] == [
            ("property.armour", 1080.0),
        ]
        assert [(row.stat_id, row.min_value) for row in resolve_trade_stat_filters(hybrid) if row.enabled] == [
            ("property.armour", 1080.0),
            ("property.evasion", 540.0),
        ]


def test_quality_above_20_is_not_normalized_down():
    item = parse_item_text(ITEM.replace(
        "Two Hand Sword\nPhysical Damage", "Two Hand Sword\nQuality: +30% (augmented)\nPhysical Damage",
    ))
    assert physical_dps_at_20_quality(item) == physical_dps(item)


def test_quality_below_20_is_normalized_to_20():
    item = parse_item_text(ITEM.replace(
        "Two Hand Sword\nPhysical Damage", "Two Hand Sword\nQuality: +10% (augmented)\nPhysical Damage",
    ))
    expected = physical_dps(item) * 1.2 / 1.1
    assert round(physical_dps_at_20_quality(item), 4) == round(expected, 4)


def test_local_weapon_mods_are_replaced_by_property_filters():
    item = parse_item_text(ITEM.replace(
        "Attacks per Second: 1.74 (augmented)",
        "Attacks per Second: 1.74 (augmented)\nCritical Strike Chance: 5.50% (augmented)",
    ).replace(
        "74% increased Physical Damage",
        "74% increased Physical Damage\n16% increased Attack Speed\n25% increased Critical Strike Chance",
    ))
    entries = (
        {"id": "explicit.stat_1509134228", "text": "#% increased Physical Damage", "type": "explicit"},
        {"id": "explicit.stat_210067635", "text": "#% increased Attack Speed", "type": "explicit"},
        {"id": "explicit.stat_2375316951", "text": "#% increased Critical Strike Chance", "type": "explicit"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    ids = {row.stat_id for row in filters}
    assert "explicit.stat_1509134228" not in ids
    assert "explicit.stat_210067635" not in ids
    assert "explicit.stat_2375316951" not in ids
    assert {"property.physical_dps", "property.aps", "property.crit"} <= ids
    assert not next(row for row in filters if row.stat_id == "property.aps").enabled
    assert not next(row for row in filters if row.stat_id == "property.crit").enabled


def test_local_armour_mod_is_replaced_by_normalized_armour_property():
    item = parse_item_text(ITEM.replace("Two Hand Swords", "Body Armours").replace(
        "Physical Damage: 108-181 (augmented)\nAttacks per Second: 1.74 (augmented)",
        "Quality: +10% (augmented)\nArmour: 1000 (augmented)",
    ).replace("74% increased Physical Damage", "100% increased Armour"))
    entries = ({
        "id": "explicit.stat_1062208444", "text": "#% increased Armour", "type": "explicit",
    },)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert not any(row.stat_id == "explicit.stat_1062208444" for row in filters)
    armour = next(row for row in filters if row.stat_id == "property.armour")
    assert armour.min_value == 981.8


def test_japanese_armour_energy_shield_hybrid_enables_both_properties():
    item = parse_item_text("""アイテムクラス: 鎧
レアリティ: レア
Kraken Pelt
Sacred Chainmail
--------
品質: +30% (augmented)
アーマー: 2940 (augmented)
エナジーシールド: 642 (augmented)
--------
アイテムレベル: 94
--------
{プレフィックスモッド「神々しい」}
アーマー +306(301-375)
最大エナジーシールド +80(73-80)
--------
スプリット
--------
クルセイダーアイテム
ウォーロードアイテム
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        enabled = {row.stat_id: row.min_value for row in resolve_trade_stat_filters(item) if row.enabled}
    assert enabled == {
        "property.armour": 2646.0,
        "property.energy_shield": 577.8,
        "property.base_percentile": 90.0,
        "property.quality": 30.0,
    }
    assert item.flags == ("split", "influence:crusader", "influence:warlord")


def test_armour_base_percentile_block_and_memory_strands_build_official_filters(tmp_path, monkeypatch):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({
        "base_armour": {"sacred chainmail": {"ar": [723, 831]}}, "mods": [],
    }), encoding="utf-8")
    monkeypatch.setenv("POETORE_METADATA_PATH", str(metadata_path))
    item = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Plate
Sacred Chainmail
--------
Armour: 777
Chance to Block: 25%
Memory Strands: 70
--------
Item Level: 85
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item, trade_base_type="Sacred Chainmail")
    by_id = {row.stat_id: row for row in filters}
    assert by_id["property.base_percentile"].read_value == 50.0
    assert by_id["property.base_percentile"].min_value == 45.0
    assert by_id["property.base_percentile"].enabled is True
    assert by_id["property.block"].enabled is False
    assert by_id["property.memory_strands"].min_value == 63.0
    assert by_id["property.memory_strands"].enabled is True
    query = build_search_query(item, "Sacred Chainmail", filters)["query"]["filters"]
    assert query["armour_filters"]["filters"]["base_defence_percentile"] == {"min": 45.0}
    assert query["misc_filters"]["filters"]["memory_level"] == {"min": 63.0}
    block_query = build_search_query(item, "Sacred Chainmail", (
        TradeStatFilter("property.block", "ブロック率", 22.5, "property", True),
    ))["query"]["filters"]
    assert block_query["armour_filters"]["filters"]["block"] == {"min": 22.5}


def test_base_percentile_removes_quality_and_local_increase_multiplicatively(tmp_path, monkeypatch):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({
        "base_armour": {"test armour": {"ar": [100, 200]}}, "mods": [],
    }), encoding="utf-8")
    monkeypatch.setenv("POETORE_METADATA_PATH", str(metadata_path))
    item = ParsedItem(
        item_class="Body Armours", rarity="Rare", name="Test", base_type="Test Armour",
        category="armour", properties={"Armour": "270", "Quality": "+20%"},
        modifiers=(ItemModifier(
            "50% increased Armour", values=(50.0,), ref="#% increased Armour",
        ),),
    )
    # 270 / 1.20 / 1.50 = 150。100～200の中央なので50 percentile。
    assert _base_defence_percentile(item, "Test Armour") == 50.0


def test_cluster_jewel_item_level_is_normalized_to_awakened_bracket():
    item = parse_item_text("""Item Class: Cluster Jewels
Rarity: Rare
Test Cluster
Large Cluster Jewel
--------
Item Level: 72
""")
    assert item.category == "cluster_jewel"
    assert available_trade_presets(item) == (PRESET_FINISHED, PRESET_BASE)
    filters = resolve_trade_stat_filters(item, PRESET_BASE)
    level = next(row for row in filters if row.stat_id == "property.item_level")
    assert (level.min_value, level.max_value) == (68.0, 74.0)
    query = build_search_query(item, "Large Cluster Jewel", filters, preset=PRESET_BASE)["query"]
    assert query["filters"]["misc_filters"]["filters"]["ilvl"] == {"min": 68.0, "max": 74.0}


def test_magic_jewel_search_requires_magic_rarity_and_exact_corruption_state():
    item = parse_item_text("""Item Class: Jewels
Rarity: Magic
Healthy Crimson Jewel
Crimson Jewel
--------
Item Level: 84
""")
    assert item.category == "jewel"
    query = build_search_query(item, "Crimson Jewel")["query"]
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "magic"}
    assert query["filters"]["misc_filters"]["filters"]["corrupted"] == {"option": "false"}
    corrupted = parse_item_text(item.raw_text + "--------\nCorrupted\n")
    query = build_search_query(corrupted, "Crimson Jewel")["query"]
    assert query["filters"]["misc_filters"]["filters"]["corrupted"] == {"option": "true"}


def test_quality_sockets_and_item_states_are_added_to_finished_search():
    item = parse_item_text("""アイテムクラス: 鎧
レアリティ: レア
Kraken Pelt
Sacred Chainmail
--------
品質: +30% (augmented)
アーマー: 2940 (augmented)
ソケット: W-W-W-R-B-B
--------
アイテムレベル: 94
--------
コラプト状態
ミラー品
スプリット
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    details = {row.stat_id: (row.min_value, row.enabled) for row in filters}
    assert details["property.quality"] == (30.0, True)
    assert details["property.sockets"] == (6.0, True)
    assert details["property.links"] == (6.0, True)
    assert details["property.white_sockets"] == (3.0, True)
    query = build_search_query(item, "Sacred Chainmail", filters)["query"]
    misc = query["filters"]["misc_filters"]["filters"]
    assert misc["quality"] == {"min": 30.0}
    assert misc["mirrored"] == {"option": "true"}
    assert "corrupted" not in misc
    assert "split" not in misc
    sockets = query["filters"]["socket_filters"]["filters"]
    assert sockets == {"sockets": {"min": 6, "w": 3}, "links": {"min": 6}}
    assert query["stats"][0]["filters"] == []


def test_finished_search_state_filters_can_exclude_or_include_items():
    item = parse_item_text(ITEM)
    excluded = build_search_query(
        item, include_corrupted=False, include_split=False,
    )["query"]["filters"]["misc_filters"]["filters"]
    assert excluded["corrupted"] == {"option": "false"}
    assert excluded["split"] == {"option": "false"}

    included = build_search_query(
        item, include_corrupted=True, include_split=True,
    )["query"]["filters"]["misc_filters"]["filters"]
    assert "corrupted" not in included
    assert "split" not in included


def test_split_uncorrupted_item_defaults_to_uncorrupted_and_includes_split():
    item = parse_item_text(ITEM + "--------\nSplit\n")
    misc = build_search_query(item)["query"]["filters"]["misc_filters"]["filters"]
    assert misc["corrupted"] == {"option": "false"}
    assert "split" not in misc


def test_quality_20_and_non_six_socket_count_are_visible_but_not_preselected():
    item = parse_item_text(ITEM.replace(
        "Physical Damage: 108-181 (augmented)",
        "Quality: +20% (augmented)\nSockets: R-G B\nPhysical Damage: 108-181 (augmented)",
    ))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    details = {row.stat_id: row for row in filters}
    assert details["property.quality"].enabled is False
    assert details["property.sockets"].min_value == 3.0
    assert details["property.sockets"].enabled is False
    assert details["property.links"].min_value == 2.0
    assert details["property.links"].enabled is True


def test_armour_also_enables_general_life_pseudo():
    item = parse_item_text(ITEM.replace("Two Hand Swords", "Body Armours").replace(
        "Physical Damage: 108-181 (augmented)\nAttacks per Second: 1.74 (augmented)",
        "Armour: 1000",
    ).replace("74% increased Physical Damage", "+80 to maximum Life"))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        enabled = {row.stat_id: row.min_value for row in resolve_trade_stat_filters(item) if row.enabled}
    assert enabled["property.armour"] == 1080.0
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


def test_pseudo_mods_cover_attributes_resources_speed_damage_crit_and_recovery():
    item = parse_item_text("""アイテムクラス: アミュレット
レアリティ: レア
試作品
ゴールドアミュレット
--------
アイテムレベル: 85
--------
全ての能力値 +20
最大マナ +60
最大エナジーシールド +40
キャストスピードが12%増加する
スペルダメージが30%増加する
火ダメージが25%増加する
グローバルクリティカルダメージ倍率 +35%
移動スピードが10%増加する
毎秒15のライフを自動回復する
マナ自動回復レートが40%増加する
""")
    filters = {row.stat_id: row for row in resolve_trade_stat_filters(item)}
    expected = {
        "pseudo.pseudo_total_all_attributes": 18.0,
        "pseudo.pseudo_total_life": 9.0,
        "pseudo.pseudo_total_mana": 63.0,
        "pseudo.pseudo_total_energy_shield": 36.0,
        "pseudo.pseudo_total_cast_speed": 10.8,
        "pseudo.pseudo_increased_spell_damage": 27.0,
        "pseudo.pseudo_increased_fire_damage": 22.5,
        "pseudo.pseudo_global_critical_strike_multiplier": 31.5,
        "pseudo.pseudo_increased_movement_speed": 9.0,
        "pseudo.pseudo_total_life_regen": 13.5,
        "pseudo.pseudo_increased_mana_regen": 36.0,
    }
    assert {stat_id: filters[stat_id].min_value for stat_id in expected} == expected
    assert filters["pseudo.pseudo_total_life"].enabled is True
    assert all(not filters[stat_id].enabled for stat_id in expected if stat_id != "pseudo.pseudo_total_life")
    assert all(row.kind == "pseudo" for row in filters.values())


def _pseudo_test_item(modifiers, category="accessory"):
    return ParsedItem(
        item_class="Rings", rarity="Rare", name="Test", base_type="Ring",
        category=category, item_level=85, modifiers=tuple(modifiers),
    )


def test_pseudo_replaces_more_general_damage_and_crit_groups():
    item = _pseudo_test_item((
        ItemModifier("", (20,), ref="#% increased Elemental Damage"),
        ItemModifier("", (30,), ref="#% increased Fire Damage"),
        ItemModifier("", (40,), ref="#% increased Burning Damage"),
        ItemModifier("", (10,), ref="#% increased Global Critical Strike Chance"),
        ItemModifier("", (25,), ref="#% increased Spell Critical Strike Chance"),
    ))
    rows = {row.stat_id: row for row in resolve_trade_stat_filters(item)}
    assert "pseudo.pseudo_increased_elemental_damage" not in rows
    assert "pseudo.pseudo_increased_fire_damage" not in rows
    assert rows["pseudo.pseudo_increased_burning_damage"].min_value == 81.0
    assert "pseudo.pseudo_global_critical_strike_chance" not in rows
    assert rows["pseudo.pseudo_critical_strike_chance_for_spells"].min_value == 31.5


def test_new_relational_pseudos_parse_from_japanese_detail_copy():
    item = parse_item_text("""アイテムクラス: アミュレット
レアリティ: レア
試作品
ゴールドアミュレット
--------
アイテムレベル: 85
--------
スペルのクリティカル率が25%増加する
アタックスキルの元素ダメージが30%増加する
燃焼ダメージが40%増加する
""")
    rows = {row.stat_id: row for row in resolve_trade_stat_filters(item)}
    assert rows["pseudo.pseudo_critical_strike_chance_for_spells"].min_value == 22.5
    assert rows["pseudo.pseudo_increased_elemental_damage_with_attack_skills"].min_value == 27.0
    assert rows["pseudo.pseudo_increased_burning_damage"].min_value == 36.0


def test_pseudo_group_output_is_independent_of_modifier_input_order():
    modifiers = (
        ItemModifier("", (20,), ref="+#% to Fire Resistance"),
        ItemModifier("", (35,), ref="+#% to Cold Resistance"),
        ItemModifier("", (10,), ref="+#% to Lightning Resistance"),
        ItemModifier("", (12,), ref="+# to Strength"),
        ItemModifier("", (30,), ref="+# to Dexterity"),
        ItemModifier("", (5,), ref="+# to Intelligence"),
    )
    forward = resolve_trade_stat_filters(_pseudo_test_item(modifiers))
    backward = resolve_trade_stat_filters(_pseudo_test_item(reversed(modifiers)))
    signature = lambda rows: tuple((row.stat_id, row.min_value, row.enabled) for row in rows)
    assert signature(forward) == signature(backward)
    ids = {row.stat_id for row in forward}
    assert ids & {
        "pseudo.pseudo_total_fire_resistance",
        "pseudo.pseudo_total_cold_resistance",
        "pseudo.pseudo_total_lightning_resistance",
    } == {"pseudo.pseudo_total_cold_resistance"}
    assert "pseudo.pseudo_total_intelligence" not in ids


def test_equal_elemental_resistances_do_not_leave_an_arbitrary_individual_pseudo():
    item = _pseudo_test_item((
        ItemModifier("", (20,), ref="+#% to Fire Resistance"),
        ItemModifier("", (20,), ref="+#% to Cold Resistance"),
    ))
    ids = {row.stat_id for row in resolve_trade_stat_filters(item)}
    assert not ids & {
        "pseudo.pseudo_total_fire_resistance",
        "pseudo.pseudo_total_cold_resistance",
        "pseudo.pseudo_total_lightning_resistance",
    }
    assert "pseudo.pseudo_total_elemental_resistance" in ids


def test_crafted_chaos_only_is_hidden_but_mixed_sources_are_aggregated():
    crafted = ItemModifier("", (16,), kind="crafted", ref="+#% to Chaos Resistance")
    assert "pseudo.pseudo_total_chaos_resistance" not in {
        row.stat_id for row in resolve_trade_stat_filters(_pseudo_test_item((crafted,)))
    }
    natural = ItemModifier("", (20,), ref="+#% to Fire and Chaos Resistances")
    rows = {row.stat_id: row for row in resolve_trade_stat_filters(
        _pseudo_test_item((crafted, natural))
    )}
    assert rows["pseudo.pseudo_total_chaos_resistance"].min_value == 32.4
    assert rows["pseudo.pseudo_total_chaos_resistance"].enabled is True


def test_unresolved_modifier_does_not_remove_unrelated_pseudos():
    item = _pseudo_test_item((
        ItemModifier("未解決Mod", (999,), ref=None, stat_id=None),
        ItemModifier("", (80,), ref="+# to maximum Life"),
        ItemModifier("", (30,), ref="+#% to Fire Resistance"),
    ))
    ids = {row.stat_id for row in resolve_trade_stat_filters(item)}
    assert "pseudo.pseudo_total_life" in ids
    assert "pseudo.pseudo_total_elemental_resistance" in ids


def test_enabled_stat_filter_is_added_with_editable_minimum():
    item = parse_item_text(ITEM)
    stat = TradeStatFilter("explicit.stat_1", "Physical", 74, "prefix", True)
    query = build_search_query(item, "Reaver Sword", (stat,))["query"]
    assert query["stats"][0]["filters"] == [
        {"id": "explicit.stat_1", "value": {"min": 74}},
    ]


def test_unique_search_uses_exact_english_name_and_hides_fixed_mods():
    item = parse_item_text("""Item Class: Amulets
Rarity: Unique
The Example
Gold Amulet
--------
Item Level: 70
--------
+40(30-50) to maximum Life
+10% to Fire Resistance
""")
    entries = (
        {"id": "explicit.life", "text": "+# to maximum Life", "type": "explicit"},
        {"id": "explicit.fire", "text": "+#% to Fire Resistance", "type": "explicit"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert filters == (TradeStatFilter(
        "explicit.life", "+40(30-50) to maximum Life", 38.0, "explicit", True,
        selection_reason="ユニークの可変Modが3個以下のため自動選択",
    ),)
    query = build_search_query(item, "Gold Amulet", filters, trade_name="The Example")["query"]
    assert query["name"] == "The Example"
    assert query["type"] == "Gold Amulet"
    assert query["stats"][0]["filters"] == [
        {"id": "explicit.life", "value": {"min": 38.0}},
    ]


def test_unique_with_more_than_three_variable_mods_does_not_preselect_all():
    labels = ("Alpha", "Beta", "Gamma", "Delta")
    body = "\n".join(
        f"+{value}({value - 5}-{value + 5}) to {label}"
        for label, value in zip(labels, (20, 30, 40, 50))
    )
    item = parse_item_text(f"""Item Class: Belts
Rarity: Unique
Many Rolls
Heavy Belt
--------
Item Level: 70
--------
{body}
""")
    entries = tuple(
        {"id": f"explicit.stat_{index}", "text": f"+# to {label}", "type": "explicit"}
        for index, label in enumerate(labels)
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert len(filters) == 4
    assert not any(row.enabled for row in filters)


def test_unidentified_unique_query_requires_unidentified_state():
    item = parse_item_text("""Item Class: Amulets
Rarity: Unique
Gold Amulet
--------
Item Level: 70
--------
Unidentified
""")
    assert item.name == item.base_type == "Gold Amulet"
    query = build_search_query(item, "Gold Amulet", trade_name="The Example")["query"]
    assert query["name"] == "The Example"
    assert query["filters"]["misc_filters"]["filters"]["identified"] == {"option": "false"}


def test_unique_candidates_come_from_official_item_data():
    payload = {"result": [{"entries": [
        {"name": "The Example", "type": "Gold Amulet", "flags": {"unique": True}},
        {"name": "Another Example", "type": "Gold Amulet", "flags": {"unique": True}},
        {"name": "Not Unique", "type": "Gold Amulet", "flags": {}},
    ]}]}
    with patch("src.poetore.trade._item_entries_cache", None), patch(
        "src.poetore.trade._request_json", return_value=(payload, {}),
    ):
        assert unique_candidates("Gold Amulet") == ("Another Example", "The Example")


def test_unique_variants_preserve_trade_discriminator():
    entries = (
        {"name": "Auxium", "type": "Chain Belt", "text": "Auxium Chain Belt", "flags": {"unique": True}},
        {"name": "Auxium", "type": "Chain Belt", "text": "Auxium Chain Belt (Legacy)", "disc": "legacy", "flags": {"unique": True}},
    )
    with patch("src.poetore.trade._item_entries_cache", entries):
        assert unique_variants("Auxium", "Chain Belt") == (
            ("Auxium Chain Belt", None), ("Auxium Chain Belt (Legacy)", "legacy"),
        )


def test_unique_variant_foil_and_foulborn_conditions_are_sent_exactly():
    foil = parse_item_text("""Item Class: Belts
Rarity: Unique
Auxium
Chain Belt
--------
Item Level: 70
--------
Foil
""")
    query = build_search_query(
        foil, "Chain Belt", trade_name="Auxium", trade_discriminator="legacy",
    )["query"]
    assert query["name"] == {"option": "Auxium", "discriminator": "legacy"}
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "uniquefoil"}
    assert query["filters"]["misc_filters"]["filters"]["foulborn_item"] == {"option": "false"}

    foulborn = parse_item_text(foil.raw_text.replace("Foil", "Foulborn"))
    misc = build_search_query(foulborn, "Chain Belt", trade_name="Auxium")["query"]["filters"]["misc_filters"]["filters"]
    assert "foulborn_item" not in misc


def test_crafted_affix_header_is_counted_for_exact_empty_slots():
    item = parse_item_text("""アイテムクラス: 指輪
レアリティ: レア
試作品
ルビーの指輪
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「健康な」 (ティア: 1) }
最大ライフ +100(90-100)
{ マスタークラフト サフィックスモッド「製作の」 }
火耐性 +20%
""")
    empty = {row.stat_id: row.text for row in resolve_trade_stat_filters(item) if row.kind == "craft"}
    assert empty == {
        "pseudo.pseudo_number_of_empty_prefix_mods": "空きPrefix枠（現在2枠）",
        "pseudo.pseudo_number_of_empty_suffix_mods": "空きSuffix枠（現在2枠）",
    }


def test_trade_status_modes_map_to_official_api_options():
    item = parse_item_text(ITEM)
    assert build_search_query(item, trade_status="instant")["query"]["status"] == {"option": "securable"}
    assert build_search_query(item, trade_status="available")["query"]["status"] == {"option": "available"}
    assert build_search_query(item, trade_status="online")["query"]["status"] == {"option": "online"}


def test_unknown_trade_status_is_rejected():
    item = parse_item_text(ITEM)
    try:
        build_search_query(item, trade_status="carrier_pigeon")
    except ValueError as exc:
        assert "未対応の取引方式" in str(exc)
    else:
        raise AssertionError("unknown trade status was accepted")


def test_offline_and_listing_age_are_sent_to_trade_api():
    query = build_search_query(
        parse_item_text(ITEM), trade_status="offline", listed_within="1week",
    )["query"]
    assert query["status"] == {"option": "any"}
    assert query["filters"]["trade_filters"]["filters"]["indexed"] == {
        "option": "1week"
    }


def test_captured_beast_uses_exact_english_type_without_rarity_filter():
    item = parse_item_text("""Item Class: Captured Beasts
Rarity: Rare
Craicic Chimeral
Craicic Chimeral
--------
Right-click to add this to your bestiary.
""")
    query = build_search_query(item, "Craicic Chimeral")["query"]
    assert query["type"] == "Craicic Chimeral"
    assert "type_filters" not in query["filters"]


def test_japanese_local_physical_modifier_is_not_duplicated_after_pdps_aggregation():
    item = parse_item_text(ITEM.replace("74% increased Physical Damage", "物理ダメージが74%\u5897加する"))
    entries = ({"id": "explicit.stat_1509134228", "text": "物理ダメージが#%増加する", "type": "explicit"},)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert not any(row.stat_id == "explicit.stat_1509134228" for row in filters)
    assert any(row.stat_id == "property.physical_dps" for row in filters)


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
    assert [(row.stat_id, row.min_value) for row in filters if row.kind != "craft"] == [
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


def test_available_pc_leagues_matches_awakened_filters():
    payload = [
        {"id": "Standard", "realm": "pc", "rules": []},
        {"id": "Hardcore", "realm": "pc", "rules": [{"id": "Hardcore"}]},
        {"id": "Mirage", "realm": "pc", "rules": []},
        {"id": "Hardcore Mirage", "realm": "pc", "rules": [{"id": "Hardcore"}]},
        {"id": "SSF Mirage", "realm": "pc", "rules": [{"id": "NoParties"}]},
        {"id": "Ruthless", "realm": "pc", "rules": [{"id": "HardMode"}]},
    ]
    with patch("src.poetore.trade._request_json", return_value=(payload, {})):
        leagues = available_pc_leagues()
    assert [(league.id, league.hardcore) for league in leagues] == [
        ("Standard", False), ("Mirage", False), ("Hardcore Mirage", True),
    ]
    assert default_pc_league(leagues) == "Mirage"


def test_price_result_calculates_median_per_currency():
    result = PriceResult("Mirage", "q", 3, (
        PriceListing(3, "chaos"), PriceListing(7, "chaos"), PriceListing(1, "divine")
    ))
    assert result.median_by_currency() == {"chaos": 5, "divine": 1}


def test_search_prices_keeps_item_and_seller_for_list_display():
    _trade_response_cache.clear()
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


def test_search_prices_logs_request_payload_and_response_summary(capsys):
    _trade_response_cache.clear()
    search = ({"id": "query1", "result": ["item1"]}, {"X-Rate-Limit-Ip-State": "1:10:0"})
    fetch = ({"result": [{
        "listing": {"price": {"amount": 4, "currency": "chaos"}},
        "item": {"baseType": "Reaver Sword"},
    }]}, {})
    with patch("src.poetore.trade._request_json", side_effect=[search, fetch]):
        search_prices(
            parse_item_text(ITEM), "Reaver Sword", "Mirage",
            trade_status="available",
        )

    output = capsys.readouterr().out
    assert "[POETORE TRADE] search: league='Mirage'" in output
    assert "trade_status='available' api_status='available'" in output
    assert '"type": "Reaver Sword"' in output
    assert '"status": {' in output
    assert '"option": "available"' in output
    assert "search response: query_id='query1' candidates=1" in output
    assert "priced_listings=1 rate_limit='1:10:0'" in output


def test_search_result_exposes_japanese_trade_url_and_reuses_cache():
    _trade_response_cache.clear()
    response = ({"id": "qid", "result": [], "total": 0}, {})
    item = replace(parse_item_text(ITEM), name="破滅の切断", base_type="略奪者の剣")
    with patch("src.poetore.trade._request_json", return_value=response) as request:
        first = search_prices(item, "Reaver Sword", "Standard")
        second = search_prices(item, "Reaver Sword", "Standard")
    assert request.call_count == 1
    assert first.cached is False and second.cached is True
    parsed_url = urlsplit(first.web_url)
    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "jp.pathofexile.com"
    assert parsed_url.path == "/trade/search/Standard"
    web_payload = json.loads(parse_qs(parsed_url.query)["q"][0])
    assert web_payload["query"]["type"] == "略奪者の剣"
    assert "qid" not in first.web_url


def test_query_supports_option_not_count_and_special_item_states():
    item = parse_item_text(ITEM)
    item = replace(item, flags=item.flags + ("searing_item", "tangled_item", "veiled"))
    filters = (
        TradeStatFilter("enchant.allocates", "処刑人 を割り当てる", None, "enchant", True,
                        option_value=10016),
        TradeStatFilter("explicit.bad", "除外", None, "explicit", True,
                        group_type="not", group_key="exclude"),
        TradeStatFilter("explicit.one", "候補1", None, "explicit", True,
                        group_type="count", group_key="either", group_min=1),
        TradeStatFilter("explicit.two", "候補2", None, "explicit", True,
                        group_type="count", group_key="either", group_min=1),
    )
    query = build_search_query(item, stat_filters=filters)["query"]
    assert query["stats"][0]["filters"][0] == {
        "id": "enchant.allocates", "value": {"option": 10016},
    }
    assert {group["type"] for group in query["stats"]} == {"and", "not", "count"}
    count = next(group for group in query["stats"] if group["type"] == "count")
    assert count["value"] == {"min": 1}
    misc = query["filters"]["misc_filters"]["filters"]
    assert misc["searing_item"] == misc["tangled_item"] == misc["veiled"] == {"option": "true"}


def _gem_item(name="アーク", level=20, quality=20, corrupted=False):
    return parse_item_text(f"""アイテムクラス: スキルジェム
レアリティ: ジェム
{name}
--------
レベル: {level}
品質: +{quality}%
--------
アイテムレベル: 1
--------
{"コラプト状態" if corrupted else ""}
""")


def test_gem_filters_use_awakened_max_level_quality_and_corruption_rules():
    normal = _gem_item(level=20, quality=16)
    filters = {row.stat_id: row for row in resolve_trade_stat_filters(normal, trade_base_type="Arc")}
    assert filters["property.gem_level"].enabled is True
    assert filters["property.quality"].enabled is True
    query = build_search_query(normal, "Arc", tuple(filters.values()))["query"]
    assert query["filters"]["misc_filters"]["filters"] == {
        "corrupted": {"option": "false"}, "gem_level": {"min": 20.0}, "quality": {"min": 16.0},
    }

    low = _gem_item(level=19, quality=15)
    assert all(not row.enabled for row in resolve_trade_stat_filters(low, trade_base_type="Arc"))


def test_transfigured_vaal_awakened_and_exceptional_gem_identity():
    transfigured = _gem_item("サージングのアーク", 20, 16)
    filters = resolve_trade_stat_filters(transfigured, trade_base_type="Arc of Surging")
    assert next(row for row in filters if row.stat_id == "property.quality").enabled is False
    query = build_search_query(transfigured, "Arc of Surging", filters)["query"]
    assert query["type"] == {"option": "Arc", "discriminator": "alt_x"}

    empower = _gem_item("エンパワーサポート", 3, 0)
    level = next(row for row in resolve_trade_stat_filters(empower, trade_base_type="Empower Support")
                 if row.stat_id == "property.gem_level")
    assert level.enabled is True
    awakened = _gem_item("覚醒のエンパワーサポート", 3, 0)
    awakened_level = next(row for row in resolve_trade_stat_filters(
        awakened, trade_base_type="Awakened Empower Support"
    ) if row.stat_id == "property.gem_level")
    assert awakened_level.enabled is False
    assert build_search_query(_gem_item("ヴァールアーク", 20, 20, True), "Vaal Arc")["query"]["type"] == "Vaal Arc"


def test_unique_item_level_exceptions_match_awakened():
    watchers = replace(parse_item_text("""Item Class: Jewels
Rarity: Unique
Prismatic Jewel
--------
Item Level: 86
--------
Unidentified
"""), name="Watcher's Eye")
    query = build_search_query(watchers, "Prismatic Jewel", trade_name="Watcher's Eye")["query"]
    assert query["filters"]["misc_filters"]["filters"]["ilvl"] == {"min": 86}

    agnerod = replace(watchers, name="Agnerod West", flags=(), item_level=81)
    filters = resolve_trade_stat_filters(agnerod)
    level = next(row for row in filters if row.stat_id == "property.item_level")
    assert level.min_value == 80
    query = build_search_query(agnerod, "Imperial Staff", filters, trade_name="Agnerod West")["query"]
    assert query["filters"]["misc_filters"]["filters"]["ilvl"] == {"min": 80.0}


def test_map_properties_blight_and_valdo_safety_filters():
    item = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
ブライトに破壊された峡谷マップ
峡谷マップ
--------
マップティア: 16
アイテム数量: +120%
アイテムレアリティ: +75%
モンスターパックサイズ: +42%
追加マップ: +25%
追加スカラベ: +30%
マップ完了報酬: Mageblood
--------
アイテムレベル: 83
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    enabled = {row.stat_id: row for row in filters if row.enabled}
    assert enabled["property.map_tier"].min_value == 16
    assert enabled["property.map_quantity"].min_value == 120
    assert enabled["property.map_rarity"].min_value == 75
    assert enabled["property.map_pack_size"].min_value == 42
    assert enabled["pseudo.pseudo_map_more_map_drops"].min_value == 25
    assert enabled["pseudo.pseudo_map_more_scarab_drops"].min_value == 30
    assert enabled["property.map_uberblighted"].enabled
    assert enabled["explicit.stat_1095765106"].group_type == "not"
    query = build_search_query(item, "Canyon Map", filters)["query"]
    map_filters = query["filters"]["map_filters"]["filters"]
    assert map_filters["map_tier"] == {"min": 16.0}
    assert map_filters["map_uberblighted"] == {"option": "true"}
    assert map_filters["map_completion_reward"] == {"option": "Mageblood"}


def test_heist_blueprint_contract_and_logbook_rules():
    blueprint = parse_item_text("""アイテムクラス: 設計図
レアリティ: レア
試作品
設計図
--------
エリアレベル: 83
情報を聞いた区画数: 4
--------
アイテムレベル: 83
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(blueprint)
    ids = {row.stat_id: row for row in filters}
    assert ids["property.area_level"].enabled
    assert ids["property.heist_wings"].min_value == 4
    assert ids["pseudo.pseudo_number_of_enchant_mods"].group_type == "not"
    query = build_search_query(blueprint, "Blueprint", filters)["query"]
    assert query["filters"]["heist_filters"]["filters"]["heist_wings"] == {"min": 4.0}

    contract = parse_item_text("""アイテムクラス: 契約書
レアリティ: レア
試作品
契約書
--------
エリアレベル: 81
必要なジョブ: 知覚能力 レベル 3
依頼書目標の価値: プライスレス
--------
アイテムレベル: 81
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(contract)
    ids = {row.stat_id: row for row in filters}
    assert ids["property.heist_perception"].min_value == 3
    assert ids["property.heist_objective_value"].option_value == "priceless"

    logbook = parse_item_text("""アイテムクラス: ログブック
レアリティ: レア
遠征ログブック
ログブック
--------
エリアレベル: 82
--------
アイテムレベル: 82
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(logbook)
    assert next(row for row in filters if row.stat_id == "property.area_level").min_value == 81


def test_flask_hybrid_cluster_and_special_area_rules():
    flask = ParsedItem(
        item_class="Utility Flasks", rarity="Magic", name="Test", base_type="Granite Flask",
        category="flask", item_level=84,
        modifiers=(ItemModifier(
            "20% increased Charge Recovery", (20,), ref="#% increased Charge Recovery",
            stat_id="explicit.stat_3196823591",
        ),),
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(flask)
    hybrid = next(row for row in filters if row.kind == "flask hybrid")
    assert hybrid.group_type == "not" and hybrid.enabled

    cluster = parse_item_text("""Item Class: Cluster Jewels
Rarity: Rare
Test
Large Cluster Jewel
--------
Item Level: 72
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(cluster)
    level = next(row for row in filters if row.stat_id == "property.item_level")
    assert (level.min_value, level.max_value, level.enabled) == (68, 74, True)

    chronicle = parse_item_text("""アイテムクラス: インカージョンアイテム
レアリティ: ノーマル
アトゾアトルの年代記
--------
エリアレベル: 79
--------
アイテムレベル: 1
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(chronicle)
    assert next(row for row in filters if row.stat_id == "property.area_level").min_value == 78
