from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.poetore.poe2.parser import Poe2ItemParseError, TRADE_CATEGORY_BY_CATEGORY, parse_item_text


FIXTURES = Path(__file__).parent / "fixtures" / "poe2" / "minimal_items.json"


def _fixtures():
    return json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]


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


def test_unknown_base_is_not_silently_guessed():
    with pytest.raises(Poe2ItemParseError, match="base identity未解決"):
        parse_item_text("Item Class: Bows\nRarity: Rare\nTest Name\nUnknown Bow\n")


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
