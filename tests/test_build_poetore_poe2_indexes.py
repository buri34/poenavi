from __future__ import annotations

import json

from scripts.build_poetore_poe2_indexes import (
    OUTPUT, _aligned, build_augment_index, build_stat_index,
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
        (target / "items.ndjson").write_text(json.dumps(row, ensure_ascii=False) + "\n")
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
