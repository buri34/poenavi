import importlib.util
import json
from pathlib import Path

SCRIPT = Path("scripts/generate_heist_unique_mod_templates.py")
SPEC = importlib.util.spec_from_file_location(
    "generate_heist_unique_mod_templates", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


def test_explicit_mod_ids_are_ordered_and_deduplicated():
    source = """
|explicit1 = FirstUniqueMod
|explicit2= SecondUniqueMod
|explicit3 = FirstUniqueMod
"""

    assert generator.explicit_mod_ids(source) == (
        "FirstUniqueMod",
        "SecondUniqueMod",
    )


def test_translation_ref_expands_missing_derived_stats_as_zero():
    mod = {
        "stats": [{"id": "local_physical_damage_+%", "min": 200, "max": 250}],
    }
    translations = {
        "local_physical_damage_+%": [
            {
                "ids": ("local_physical_damage_+%", "local_weapon_no_physical_damage"),
                "translation": {
                    "condition": ({"min": 1}, {"min": 0, "max": 0}),
                    "format": ("#", "ignore"),
                    "string": "{0}% increased Physical Damage",
                },
            }
        ],
    }

    assert (
        generator._translation_ref(mod, translations) == "#% increased Physical Damage"
    )


def test_local_trade_row_prefers_matching_item_category():
    rows = [
        {
            "kind": "explicit",
            "stat_id": "global",
            "local": True,
            "category_select": None,
        },
        {
            "kind": "explicit",
            "stat_id": "local",
            "local": True,
            "category_select": "ARMOUR",
        },
    ]

    selected = generator._choose_trade_row(rows, local=True, item_group="armour")

    assert selected["stat_id"] == "local"


def test_bundled_templates_only_reference_current_official_trade_stats():
    templates = json.loads(
        Path("data/poetore/poe1/heist_unique_mod_templates.json").read_text(
            encoding="utf-8"
        )
    )
    metadata = json.loads(
        Path("data/poetore/mod_metadata.json").read_text(encoding="utf-8")
    )
    valid_ids = {
        row["stat_id"] for row in metadata["mods"] if row["kind"] == "explicit"
    }

    assert len(templates["items"]) == 101
    assert sum(len(row["filters"]) for row in templates["items"]) == 412
    for item in templates["items"]:
        identities = [(row["stat_id"], row["inverted"]) for row in item["filters"]]
        assert len(identities) == len(set(identities))
        assert all(row["stat_id"] in valid_ids for row in item["filters"])
