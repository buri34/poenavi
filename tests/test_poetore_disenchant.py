from src.poetore.disenchant import disenchant_dust
from src.poetore.models import ItemModifier, ParsedItem


def _unique_item(**changes):
    values = {
        "item_class": "Amulets",
        "rarity": "Unique",
        "name": "Eternal Damnation",
        "base_type": "Agate Amulet",
        "category": "accessory",
        "item_level": 83,
        "properties": {"Quality": "+20% (augmented)"},
        "modifiers": (),
        "flags": (),
    }
    values.update(changes)
    return ParsedItem(**values)


def test_disenchant_dust_applies_level_quality_influences_and_corrupted_implicits(monkeypatch):
    monkeypatch.setattr(
        "src.poetore.disenchant.unique_disenchant_value",
        lambda name, base_type: 165.78,
    )
    item = _unique_item(
        flags=("influence:shaper", "influence:elder", "corrupted"),
        modifiers=(ItemModifier(
            "+1% to all maximum Resistances",
            kind="implicit",
            generation="corrupted",
        ),),
    )

    assert disenchant_dust(item) == 1_141_809


def test_unidentified_unique_candidate_recalculates_dust_by_selected_name(monkeypatch):
    values = {"eternal damnation": 165.78, "voll's devotion": 46.12}
    monkeypatch.setattr(
        "src.poetore.disenchant.unique_disenchant_value",
        lambda name, base_type: values.get(name.casefold()),
    )
    item = _unique_item(
        name="Agate Amulet",
        flags=("unidentified",),
    )

    assert disenchant_dust(item, unique_name="Eternal Damnation") == 551_218
    assert disenchant_dust(item, unique_name="Voll's Devotion") == 153_349


def test_disenchant_dust_is_unavailable_without_unique_metadata_or_item_level(monkeypatch):
    monkeypatch.setattr(
        "src.poetore.disenchant.unique_disenchant_value",
        lambda name, base_type: None,
    )
    assert disenchant_dust(_unique_item()) is None
    assert disenchant_dust(_unique_item(item_level=None)) is None
