from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.poetore.poe2.parser import Poe2ItemParseError, TRADE_CATEGORY_BY_CATEGORY, parse_item_text


FIXTURES = Path(__file__).parent / "fixtures" / "poe2" / "minimal_items.json"
PHASE6_FIXTURES = Path(__file__).parent / "fixtures" / "poe2" / "phase6_special_items_ja.json"
AMBIGUOUS_BASE_FIXTURES = (
    Path(__file__).parent / "fixtures" / "poe2" / "ambiguous_bases_bilingual.json"
)


def _fixtures():
    return json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]


def _phase6_fixtures():
    return json.loads(PHASE6_FIXTURES.read_text(encoding="utf-8"))["fixtures"]


def _ambiguous_base_fixtures():
    return json.loads(AMBIGUOUS_BASE_FIXTURES.read_text(encoding="utf-8"))["fixtures"]


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda row: row["id"])
def test_parse_minimal_poe2_fixtures(fixture):
    item = parse_item_text(fixture["text"])
    expected = fixture["expected"]
    assert item.name == expected["name"]
    assert item.base_type == expected["base_type"]
    assert item.category == expected["category"]
    assert item.item_level == expected.get("item_level")
    assert TRADE_CATEGORY_BY_CATEGORY[item.category] == expected["trade_category"]


def test_bilingual_pairs_resolve_to_same_trade_identity():
    by_pair = {}
    for fixture in _fixtures():
        item = parse_item_text(fixture["text"])
        identity = (item.base_type, item.category, TRADE_CATEGORY_BY_CATEGORY[item.category])
        by_pair.setdefault(fixture["pair"], set()).add(identity)
    assert all(len(values) == 1 for values in by_pair.values())


@pytest.mark.parametrize("fixture", _ambiguous_base_fixtures(), ids=lambda row: row["id"])
@pytest.mark.parametrize("language", ("ja", "en"))
def test_user_captured_bilingual_ambiguous_bases_resolve_exactly(fixture, language):
    item = parse_item_text(fixture[language])
    assert item.base_type == fixture["expected_base_type"]
    assert item.category in {"body_armour", "boots", "gloves", "helmet"}


def test_ambiguous_localized_base_without_discriminator_is_not_guessed():
    text = (
        "アイテムクラス: 靴\nレアリティ: レア\nテスト品\n要塞のサバトン\n"
        "--------\nアイテムレベル: 80\n"
    )
    with pytest.raises(Poe2ItemParseError, match="base identity曖昧"):
        parse_item_text(text)


@pytest.mark.parametrize("fixture", _phase6_fixtures(), ids=lambda row: row["id"])
def test_phase6_special_categories_resolve_to_trade_identity(fixture):
    item = parse_item_text(fixture["text"])
    assert item.base_type == fixture["base_type"]
    assert item.category == fixture["category"]
    assert TRADE_CATEGORY_BY_CATEGORY[item.category] == fixture["trade_category"]
    if "name" in fixture:
        assert item.name == fixture["name"]


def test_phase6_relic_trial_and_timelost_properties_are_preserved():
    fixtures = {row["id"]: parse_item_text(row["text"]) for row in _phase6_fixtures()}
    relic = fixtures["sanctum_relic"]
    assert [(mod.kind, mod.stat_id, mod.values) for mod in relic.modifiers] == [
        ("sanctum", "sanctum.stat_4057192895", (5.0,)),
    ]
    assert fixtures["djinn_barya"].properties == {"エリアレベル": "80", "試練数": "3"}
    assert fixtures["inscribed_ultimatum"].properties["Ultimatum Hint"] == "Deadly"
    assert fixtures["timelost_jewel"].properties["半径"] == "大"
    assert fixtures["normal_tablet"].properties["残り使用回数"] == "10"


def test_poe2_roll_ranges_are_averaged_and_only_safe_ranges_get_better_direction():
    spear = parse_item_text(
        (Path(__file__).parent / "fixtures" / "poe2" / "rare_spear_ja.txt").read_text(
            encoding="utf-8"
        )
    )
    flat = next(mod for mod in spear.modifiers if mod.stat_id == "explicit.stat_1940865751")
    assert (flat.roll_min, flat.roll_max, flat.better) == (28.5, 42.0, 1)

    text = """アイテムクラス: ウェイストーン
レアリティ: マジック
減退する ウェイストーン (ティア15)
--------
アイテムレベル: 81
--------
{ サフィックスモッド }
モンスターがクリティカルヒットから受ける追加ダメージが28(26-30)%減少する
"""
    reduced = parse_item_text(text).modifiers[0]
    assert (reduced.roll_min, reduced.roll_max, reduced.better) == (26.0, 30.0, None)


def test_poe2_standalone_rune_line_counts_one_installed_augment():
    item = parse_item_text(
        (Path(__file__).parent / "fixtures" / "poe2" / "phase45_sceptre_ja.txt").read_text(
            encoding="utf-8"
        )
    )
    assert item.augment_count == 1


def test_unknown_base_is_not_silently_guessed():
    with pytest.raises(Poe2ItemParseError, match="base identity未解決"):
        parse_item_text("Item Class: Bows\nRarity: Rare\nTest Name\nUnknown Bow\n")


@pytest.mark.parametrize(
    ("item_class", "affixed_name", "expected_base", "expected_category"),
    [
        ("Focus", "Pulsing Antler Focus", "Antler Focus", "focus"),
        ("Two Hand Mace", "Reaver's Temple Maul of Stunning", "Temple Maul", "two_mace"),
        ("指輪", "火炎の アメジストの指輪", "Amethyst Ring", "ring"),
        ("鎧", "幻術の スリップストライクベスト", "Slipstrike Vest", "body_armour"),
    ],
)
def test_magic_items_extract_longest_category_matching_base_from_affixed_name(
    item_class, affixed_name, expected_base, expected_category,
):
    item = parse_item_text(
        f"アイテムクラス: {item_class}\n"
        f"レアリティ: マジック\n{affixed_name}\n--------\nアイテムレベル: 80\n"
    )

    assert item.base_type == expected_base
    assert item.category == expected_category
    assert affixed_name not in item.base_type


@pytest.mark.parametrize(
    ("item_class", "rare_name", "localized_base", "expected_base"),
    [
        ("スピア", "崇高なエッジ", "飛翔のスピア", "Soaring Spear"),
        ("鎧", "災いのカーテン", "スリップストライクベスト", "Slipstrike Vest"),
        ("指輪", "大渦の環", "アメジストの指輪", "Amethyst Ring"),
    ],
)
def test_rare_items_keep_generated_name_separate_from_exact_base_line(
    item_class, rare_name, localized_base, expected_base,
):
    item = parse_item_text(
        f"アイテムクラス: {item_class}\nレアリティ: レア\n"
        f"{rare_name}\n{localized_base}\n--------\nアイテムレベル: 80\n"
    )

    assert item.name == rare_name
    assert item.base_type == expected_base


def test_rare_properties_and_resolved_mod_are_kept_for_editable_trade_filters():
    text = (
        "Item Class: Bows\nRarity: Rare\nTest Name\nRider Bow\n--------\n"
        "Quality: +20%\nPhysical Damage: 12-34\n--------\nItem Level: 80\n--------\n"
        "123 to maximum Life\n999 unrecognised power\n"
    )
    item = parse_item_text(text)
    assert item.properties["Quality"] == "+20%"
    assert item.modifiers[0].stat_id == "explicit.stat_3299347043"
    assert item.modifiers[0].values == (123.0,)
    assert item.modifiers[1].stat_id is None
    assert item.modifiers[1].text == "999 unrecognised power"


def test_reported_japanese_mageblood_resolves_all_searchable_mods():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "mageblood_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.name == "Mageblood"
    assert item.base_type == "Utility Belt"
    assert item.category == "belt"
    assert item.properties["装備条件"] == "レベル 55"
    assert len(item.modifiers) == 7
    assert all(mod.stat_id for mod in item.modifiers)
    assert [mod.stat_id for mod in item.modifiers[2:6]] == [
        "explicit.stat_264262054|3", "explicit.stat_264262054|11",
        "explicit.stat_264262054|4", "explicit.stat_264262054|8",
    ]
    assert item.modifiers[1].values == (2.0,)
    assert item.modifiers[-1].values == (43.0,)


def test_reported_japanese_rare_gloves_resolve_chaos_and_desecrated_mods():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_gloves_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.base_type == "Grand Bracers"
    assert item.category == "gloves"
    assert len(item.modifiers) == 7
    assert all(mod.stat_id for mod in item.modifiers)
    chaos = next(mod for mod in item.modifiers if mod.text.startswith("混沌耐性"))
    assert chaos.stat_id == "explicit.stat_2923486259"
    assert chaos.values == (15.0,)
    cold = next(mod for mod in item.modifiers if "冷気ダメージ" in mod.text)
    assert cold.stat_id.startswith("desecrated.")


def test_reported_japanese_rare_spear_keeps_quality_and_both_flat_damage_values():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_spear_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.base_type == "Soaring Spear"
    assert item.category == "spear"
    assert item.properties["品質"] == "+20% (augmented)"
    flat = next(mod for mod in item.modifiers if "物理ダメージを追加" in mod.text)
    assert flat.stat_id == "explicit.stat_1940865751"
    assert flat.values == (25.0, 39.0)
    fractured = next(mod for mod in item.modifiers if "アタックスピードが28" in mod.text)
    assert fractured.kind == "fractured"
    assert "fractured" in item.flags


def test_reported_japanese_rare_body_armour_prefers_local_evasion_stats():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_body_armour_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    increased = [mod for mod in item.modifiers if mod.text.startswith("回避力が")]
    assert [(mod.stat_id, mod.values) for mod in increased] == [
        ("explicit.stat_124859000", (105.0,)),
        ("explicit.stat_124859000", (40.0,)),
    ]
    assert all(not mod.stat_ids for mod in increased)
    deflection = next(mod for mod in item.modifiers if "受け流し力" in mod.text)
    assert deflection.stat_id == "explicit.stat_3033371881"
    assert deflection.values == (17.0,)
    assert {"augment", "desecrated", "crafted", "corrupted"} <= set(item.flags)


def test_phase45_sceptre_parses_spirit_augment_sockets_and_sanctified_state():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "phase45_sceptre_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.category == "sceptre"
    assert item.properties["スピリット"] == "100"
    assert item.properties["ソケット"] == "S S"
    assert {"augment", "sanctified"} <= set(item.flags)
    augment = next(mod for mod in item.modifiers if mod.kind == "augment")
    assert augment.stat_id and augment.stat_id.startswith("rune.")


def test_phase45_waystone_parses_all_dedicated_properties():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "phase45_waystone_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.category == "waystone"
    assert item.base_type == "Waystone (Tier 15)"
    assert item.properties["ウェイストーンティア"] == "15"
    assert item.properties["復活が利用可能"] == "3"
    assert item.properties["モンスターパックサイズ"] == "+42%"


def test_reported_magic_waystone_extracts_affixed_base_and_resolves_all_mods():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "magic_waystone_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.rarity == "magic"
    assert item.category == "waystone"
    assert item.base_type == "Waystone (Tier 15)"
    assert item.properties["復活が利用可能"] == "4 (augmented)"
    assert item.properties["パックサイズ"] == "+16% (augmented)"
    assert item.properties["ウェイストーンドロップ確率"] == "+30% (augmented)"
    assert [(mod.stat_id, mod.values) for mod in item.modifiers] == [
        ("explicit.stat_2753083623", (224.0,)),
        ("explicit.stat_57326096", (25.0,)),
        ("explicit.stat_3477720557", ()),
    ]
    assert all(mod.confidence == 1.0 for mod in item.modifiers)


def test_reported_rare_waystone_keeps_affix_name_separate_from_trade_base():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_waystone_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)

    assert item.rarity == "rare"
    assert item.category == "waystone"
    assert item.name == "先祖の突撃"
    assert item.base_type == "Waystone (Tier 15)"


def test_phase45_runemastered_base_and_desecrated_state_are_not_collapsed():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "phase45_runemastered_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.base_type == "Runemastered Vaal Cuirass"
    assert {"runeforged", "desecrated", "fractured"} <= set(item.flags)
    desecrated = next(mod for mod in item.modifiers if mod.kind == "desecrated")
    assert desecrated.stat_id == "desecrated.stat_2923486259"


@pytest.mark.parametrize(
    "fixture",
    json.loads(
        (Path(__file__).parent / "fixtures" / "poe2" / "phase45_augment_items_ja.json").read_text(
            encoding="utf-8"
        )
    )["fixtures"],
    ids=lambda row: row["id"],
)
def test_phase45_standalone_rune_and_soul_core_categories(fixture):
    item = parse_item_text(fixture["text"])
    assert item.category == fixture["category"]
    assert item.base_type == fixture["base_type"]
    assert TRADE_CATEGORY_BY_CATEGORY[item.category] == fixture["trade_category"]


def test_phase45_gem_identity_and_socket_property():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "phase45_gem_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.rarity == "gem"
    assert item.base_type == "Arc"
    assert item.category == "active_gem"
    assert item.properties["ソケット"] == "S S"
