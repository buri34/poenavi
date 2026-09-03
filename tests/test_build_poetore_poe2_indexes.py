from __future__ import annotations

import json
from pathlib import Path
import pytest
from src.poetore.poe2.metadata import related_item_group

from scripts.build_poetore_poe2_indexes import (
    OUTPUT, _aligned, build_augment_index, build_identity_index,
    build_related_item_groups, build_stat_index,
)


def test_aligned_recovers_after_one_localized_entry_is_missing():
    english = [{"type": "A"}, {"type": "B", "name": "Unique"}, {"type": "C"}]
    japanese = [{"type": "あ"}, {"type": "し", "name": "ユニーク"}]
    pairs = list(_aligned(english, japanese))
    assert [(en["type"], ja["type"]) for en, ja in pairs] == [("A", "あ"), ("B", "し")]


def test_generated_stat_index_matches_locked_snapshot_builder():
    generated = json.loads((OUTPUT / "stat_index.json").read_text(encoding="utf-8"))
    assert generated == build_stat_index()
    assert len(generated["entries"]) > 8000


def test_generated_identity_index_keeps_ambiguous_base_fingerprints():
    generated = json.loads((OUTPUT / "identity_index.json").read_text(encoding="utf-8"))
    rows = [
        row for row in generated["entries"]
        if (row.get("names") or {}).get("ja") == "要塞のサバトン"
    ]
    assert {row["ref_name"] for row in rows} == {"Bastion Sabatons", "Fortress Sabatons"}
    assert {tuple(row["armour"]["ar"]) for row in rows} == {(123, 123), (147, 147)}
    assert all(row["tags"] == ["str_dex_armour"] for row in rows)


def test_generated_augment_index_has_fixed_source_and_trade_ids():
    generated = json.loads((OUTPUT / "augment_index.json").read_text(encoding="utf-8"))
    assert generated["source"].endswith("d72afb83bc0888919a89d3c3744acee2c597e9c8")
    assert len(generated["entries"]) == 259
    effects = [effect for row in generated["entries"] for effect in row["effects"]]
    assert len(effects) == 475
    assert all(effect["categories"] and effect["trade_ids"] for effect in effects)


def test_build_augment_index_keeps_bilingual_effects_and_trade_ids(tmp_path):
    data = tmp_path / "renderer" / "public" / "data"
    for language, name, effect in (
        ("en", "Body Rune", "+# to Life"),
        ("ja", "肉体のルーン", "ライフ +#"),
    ):
        target = data / language
        target.mkdir(parents=True)
        row = {
            "name": name, "refName": "Body Rune", "namespace": "ITEM",
            "augment": [{
                "categories": ["Body Armour"], "string": effect, "values": [45],
                "tradeId": ["rune.stat_1"], "socketBound": False,
            }],
        }
        (target / "items.ndjson").write_text(
            json.dumps(row, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    payload = build_augment_index(tmp_path)
    assert payload["entries"] == [{
        "ref_name": "Body Rune",
        "names": {"en": "Body Rune", "ja": "肉体のルーン"},
        "effects": [{
            "categories": ["Body Armour"],
            "text": {"en": "+# to Life", "ja": "ライフ +#"},
            "values": [45], "trade_ids": ["rune.stat_1"], "socket_bound": False,
        }],
    }]


def test_build_identity_index_keeps_duplicate_variant_tags_and_base_armour(tmp_path):
    data = tmp_path / "renderer" / "public" / "data"
    rows = {
        "en": [
            {"name": "Bastion Sabatons", "refName": "Bastion Sabatons"},
            {"name": "Fortress Sabatons", "refName": "Fortress Sabatons"},
        ],
        "ja": [
            {"name": "要塞のサバトン", "refName": "Bastion Sabatons"},
            {"name": "要塞のサバトン", "refName": "Fortress Sabatons"},
        ],
    }
    for language in ("en", "ja"):
        target = data / language
        target.mkdir(parents=True)
        enriched = []
        for index, row in enumerate(rows[language]):
            enriched.append({
                **row, "namespace": "ITEM", "tags": ["str_dex_armour"],
                "armour": {"ar": [123 + index * 24] * 2, "ev": [111 + index * 23] * 2},
                "craftable": {"category": "Boots"},
            })
        (target / "items.ndjson").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in enriched),
            encoding="utf-8",
        )

    entries = build_identity_index(tmp_path)["entries"]
    assert [row["ref_name"] for row in entries[:2]] == ["Bastion Sabatons", "Fortress Sabatons"]
    assert entries[0]["tags"] == ["str_dex_armour"]
    assert entries[0]["armour"] == {"ar": [123, 123], "ev": [111, 111]}
    assert entries[1]["armour"] == {"ar": [147, 147], "ev": [134, 134]}


def test_generated_related_items_match_locked_ee2_and_have_price_hints():
    generated = json.loads((OUTPUT / "related_item_groups.json").read_text(encoding="utf-8"))
    assert generated["source"].endswith("d72afb83bc0888919a89d3c3744acee2c597e9c8")
    assert len(generated["groups"]) == 115
    first = generated["groups"][0]
    assert first["query"][0] == {
        "id": "ITEM::Primary Calamity Fragment", "namespace": "ITEM",
        "name": "Primary Calamity Fragment", "display_name": "第一の災厄のフラグメント",
        "ninja_type": "Fragments",
    }
    prism = next(row for row in first["items"] if row["name"] == "Prism of Belief")
    assert prism["variant"] == "Diamond"
    assert prism["ninja_type"] == "UniqueJewels"


def test_reviewed_related_item_japanese_overrides_are_in_runtime_indexes():
    overrides = json.loads(
        Path("scripts/poetore-poe2-related-japanese-overrides.json").read_text(encoding="utf-8")
    )["overrides"]
    identity = json.loads((OUTPUT / "identity_index.json").read_text(encoding="utf-8"))
    related = json.loads((OUTPUT / "related_item_groups.json").read_text(encoding="utf-8"))
    expected = {
        (row["namespace"], row["ref_name"]): row["japanese"] for row in overrides
    }
    identity_names = {
        (row["namespace"], row["ref_name"]): row["names"].get("ja")
        for row in identity["entries"]
    }
    related_names = {
        (row["namespace"], row["name"]): row.get("display_name")
        for group in related["groups"]
        for row in (*group.get("query", ()), *group.get("items", ()))
    }
    assert {key: identity_names.get(key) for key in expected} == expected
    assert {key: related_names.get(key) for key in expected} == expected
    assert len(expected) == 21


def test_build_related_items_is_reproducible_from_locked_ee2():
    ee2_root = __import__("pathlib").Path("/tmp/poe2-upstream-audit.SsKQia/ee2")
    if not ee2_root.exists():
        pytest.skip("locked EE2 checkout is not available")
    generated = json.loads((OUTPUT / "related_item_groups.json").read_text(encoding="utf-8"))
    assert generated == build_related_item_groups(ee2_root)


def test_related_item_group_requires_the_unique_base_variant_when_known():
    assert related_item_group("UNIQUE", "The Last Flame", "Incense Relic") is not None
    assert related_item_group("UNIQUE", "The Last Flame", "Vase Relic") is None
