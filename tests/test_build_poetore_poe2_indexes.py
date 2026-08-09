from __future__ import annotations

import json

from scripts.build_poetore_poe2_indexes import OUTPUT, _aligned, build_stat_index


def test_aligned_recovers_after_one_localized_entry_is_missing():
    english = [{"type": "A"}, {"type": "B", "name": "Unique"}, {"type": "C"}]
    japanese = [{"type": "あ"}, {"type": "し", "name": "ユニーク"}]
    pairs = list(_aligned(english, japanese))
    assert [(en["type"], ja["type"]) for en, ja in pairs] == [("A", "あ"), ("B", "し")]


def test_generated_stat_index_matches_locked_snapshot_builder():
    generated = json.loads((OUTPUT / "stat_index.json").read_text(encoding="utf-8"))
    assert generated == build_stat_index()
    assert len(generated["entries"]) > 8000
