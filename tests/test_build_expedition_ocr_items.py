import json

import pytest

from scripts.build_expedition_ocr_items import (
    DEFAULT_EXCLUSIONS_PATH,
    build_aliases,
    load_excluded_names,
)


def test_build_aliases_pairs_supported_groups_and_drops_ambiguous_names():
    japanese = {"result": [
        {"id": "currency", "entries": [
            {"type": "高貴なオーブ"},
            {"type": "共通名"},
            {"type": "[DNT] 非表示"},
        ]},
        {"id": "gem", "entries": [{"type": "共通名"}]},
        {"id": "weapon", "entries": [{"type": "無視"}]},
    ]}
    english = {"result": [
        {"id": "currency", "entries": [
            {"type": "Exalted Orb"},
            {"type": "First"},
            {"type": "[DNT] Hidden"},
        ]},
        {"id": "gem", "entries": [{"type": "Second"}]},
        {"id": "weapon", "entries": [{"type": "Ignored"}]},
    ]}

    assert build_aliases(
        japanese, english, {"Exalted Orb", "First", "Second", "Ignored"},
    ) == [
        {"ja": "高貴なオーブ", "en": "Exalted Orb"},
    ]


def test_load_excluded_names_reads_unique_reviewed_names(tmp_path):
    path = tmp_path / "excluded.json"
    path.write_text(
        json.dumps({
            "leagues": {
                "Forbidden Rites": {
                    "items": ["Kamasa's Orb of Sacrifice", "Vaal Orb"],
                },
            },
        }),
        encoding="utf-8",
    )

    assert load_excluded_names(path, "Forbidden Rites") == {
        "Kamasa's Orb of Sacrifice",
        "Vaal Orb",
    }
    assert load_excluded_names(path, "Future League") == set()


def test_packaged_exclusions_match_buri_review_count():
    names = load_excluded_names(DEFAULT_EXCLUSIONS_PATH, "Forbidden Rites")

    assert len(names) == 61
    assert "Kamasa's Orb of Sacrifice" in names
    assert "Expedition Logbook" in names
    assert "Uncut Skill Gem (Level 1)" in names
    assert "Exalted Orb" not in names


@pytest.mark.parametrize("items", [["Vaal Orb", "Vaal Orb"], ["Vaal Orb", ""]])
def test_load_excluded_names_rejects_invalid_lists(tmp_path, items):
    path = tmp_path / "excluded.json"
    path.write_text(
        json.dumps({"leagues": {"Forbidden Rites": {"items": items}}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_excluded_names(path, "Forbidden Rites")
