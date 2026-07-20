import json

from src.poetore.metadata import MetadataIndex, ModMetadata
from src.poetore.metadata_builder import (
    build_minimal_index, diff_minimal_indexes, excessive_removal, unresolved_trade_entries,
    validate_minimal_index,
)


def test_builder_joins_awakened_and_japanese_by_trade_id_and_keeps_minimal_fields():
    awakened = [json.dumps({
        "ref": "+# to maximum Life", "better": 1,
        "matchers": [{"string": "+# to maximum Life"}],
        "trade": {"ids": {"explicit": ["explicit.stat_life"]}},
    })]
    jp = {"result": [{"entries": [{
        "id": "explicit.stat_life", "type": "explicit", "text": "最大ライフ +#",
    }]}]}
    repoe_stats = {"base_maximum_life": {"is_local": False}}
    repoe_mods = {"Life1": {
        "domain": "item", "text": "+(10-19) to maximum Life", "required_level": 1,
        "generation_type": "prefix", "stats": [{"id": "base_maximum_life", "min": 10, "max": 19}],
    }}
    payload = build_minimal_index(awakened, jp, repoe_stats, repoe_mods)
    row = payload["mods"][0]
    assert row["stat_id"] == "explicit.stat_life"
    assert row["japanese"] == ["最大ライフ +#"]
    assert set(row) == {"ref", "stat_id", "kind", "japanese", "better", "inverted", "exact", "local", "tiers"}


def test_metadata_search_bounds_support_minimum_maximum_and_exact():
    assert ModMetadata("r", "id", "explicit", ("被ダメージが#%増加する",), better=-1).search_bounds(20) == (None, 22.0)
    assert ModMetadata("r", "id", "explicit", ("値 #",), better=0).search_bounds(3) == (3, 3)
    assert ModMetadata("r", "id", "explicit", ("値 #",), better=1).search_bounds(100, 90, 100) == (100.0, None)


def test_metadata_index_matches_normalized_japanese_detail_copy():
    index = MetadataIndex((ModMetadata(
        "+# to maximum Life", "explicit.life", "explicit", ("最大ライフ +#",),
    ),))
    record, confidence = index.match("最大ライフ +100(90-100)", "prefix")
    assert record and record.stat_id == "explicit.life"
    assert confidence == 1.0


def test_builder_is_reproducible_when_generation_time_and_sources_are_locked():
    awakened = [json.dumps({
        "ref": "+# to maximum Life", "better": 1,
        "trade": {"ids": {"explicit": ["explicit.life"]}},
    })]
    jp = {"result": [{"entries": [{
        "id": "explicit.life", "type": "explicit", "text": "最大ライフ +#",
    }]}]}
    kwargs = {"sources": {"source": {"sha256": "abc"}}, "generated_at": "locked"}
    first = build_minimal_index(awakened, jp, **kwargs)
    second = build_minimal_index(awakened, jp, **kwargs)
    assert first == second


def test_index_validation_reports_duplicates_empty_and_ambiguous_matchers():
    base = {
        "ref": "r", "kind": "explicit", "japanese": ["値 #"], "better": 1,
        "inverted": False, "exact": False, "local": False, "tiers": [],
    }
    payload = {"mods": [
        {**base, "stat_id": "one"},
        {**base, "stat_id": "two"},
        {**base, "stat_id": "two", "japanese": []},
    ]}
    result = validate_minimal_index(payload)
    assert any("duplicate stat ID" in error for error in result["errors"])
    assert any("empty Japanese matcher" in error for error in result["errors"])
    assert result["ambiguous_matchers"] == [{
        "kind": "explicit", "matcher": "値 #", "stat_ids": ["one", "two"],
    }]


def test_index_diff_reports_added_removed_and_changed_fields():
    def row(stat_id, ref="r"):
        return {
            "ref": ref, "stat_id": stat_id, "kind": "explicit", "japanese": ["値 #"],
            "better": 1, "inverted": False, "exact": False, "local": False, "tiers": [],
        }
    result = diff_minimal_indexes(
        {"mods": [row("removed"), row("changed")]},
        {"mods": [row("added"), row("changed", "new ref")]},
    )
    assert result["added"] == [{"kind": "explicit", "stat_id": "added"}]
    assert result["removed"] == [{"kind": "explicit", "stat_id": "removed"}]
    assert result["changed"] == [{
        "kind": "explicit", "stat_id": "changed", "fields": ["ref"],
    }]


def test_unresolved_trade_entries_only_lists_supported_unjoined_japanese_stats():
    payload = {"mods": [{"kind": "explicit", "stat_id": "joined"}]}
    jp = {"result": [{"entries": [
        {"id": "joined", "type": "explicit", "text": "結合済み"},
        {"id": "missing", "type": "explicit", "text": "未解決"},
        {"id": "pseudo", "type": "pseudo", "text": "対象外"},
    ]}]}
    assert unresolved_trade_entries(payload, jp) == [{
        "kind": "explicit", "stat_id": "missing", "japanese": "未解決",
    }]


def test_excessive_removal_rejects_more_than_ten_percent_or_one_hundred():
    excessive, limit = excessive_removal({"previous_count": 9270, "removed": [{}] * 928})
    assert excessive is True and limit == 927
    assert excessive_removal({"previous_count": 9270, "removed": [{}] * 927}) == (False, 927)
