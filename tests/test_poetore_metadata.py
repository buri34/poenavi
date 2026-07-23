import json
from pathlib import Path

from src.poetore.metadata import (
    MetadataIndex, ModMetadata, OptionValue, pseudo_definitions, pseudo_relations,
    diff_pseudo_payloads, unique_fixed_stats, validate_pseudo_payload,
)
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
    assert set(row) == {
        "ref", "stat_id", "kind", "japanese", "better", "inverted",
        "exact", "local", "decimal", "tiers", "options",
    }
    assert row["decimal"] is False


def test_pseudo_relations_are_fixed_to_audited_awakened_source():
    path = Path("data/poetore/pseudo_relations.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source_revision"] == "fa31bfbbe99e04e386b4af2d71d633e2b6823c0f"
    assert payload["source_sha256"] == "50209531e87e8d3d2f87d98b51ca6371dd4c2c2e4dce9c37302333e44c0a4b70"
    relations = pseudo_relations(path)
    assert len(relations) == 19
    assert any(row["stat_id"] == "pseudo.pseudo_increased_burning_damage" and
               row["replaces"] == "incr_fire_dmg" for row in relations)


def test_pseudo_definitions_are_reviewable_and_validated():
    definitions = pseudo_definitions()
    assert len(definitions) == 24
    assert {row["source_ref"] for row in definitions if row.get("relational")} == {
        "#% increased Spell Critical Strike Chance",
        "#% increased Elemental Damage with Attack Skills",
        "#% increased Burning Damage",
    }
    payload = {"definitions": definitions, "relations": pseudo_relations()}
    assert validate_pseudo_payload(payload, {row["stat_id"] for row in definitions}) == []


def test_pseudo_validation_rejects_duplicate_unknown_and_cyclic_data():
    payload = {
        "definitions": [
            {"source_ref": "same", "stat_id": "pseudo.a", "label": "A"},
            {"source_ref": "same", "stat_id": "pseudo.missing", "label": "B"},
        ],
        "relations": [
            {"stat_id": "pseudo.a", "replaces": "pseudo.b"},
            {"stat_id": "pseudo.b", "replaces": "pseudo.a"},
        ],
    }
    errors = validate_pseudo_payload(payload, {"pseudo.a"})
    assert any("duplicate source_ref" in row for row in errors)
    assert any("unknown stat_id" in row for row in errors)
    assert any("cyclic replaces" in row for row in errors)


def test_pseudo_diff_reports_added_removed_and_changed_counts():
    previous = {"definitions": [
        {"source_ref": "same", "stat_id": "pseudo.old"},
        {"source_ref": "removed", "stat_id": "pseudo.removed"},
    ]}
    candidate = {"definitions": [
        {"source_ref": "same", "stat_id": "pseudo.changed"},
        {"source_ref": "added", "stat_id": "pseudo.added"},
    ]}
    assert diff_pseudo_payloads(previous, candidate) == {
        "previous": 2, "candidate": 2, "added": 1, "removed": 1, "changed": 1,
    }


def test_builder_keeps_only_variable_base_armour_bounds():
    items = [
        json.dumps({"refName": "Sacred Chainmail", "armour": {"ar": [723, 831], "es": [145, 167]}}),
        json.dumps({"refName": "Fixed Base", "armour": {"ar": [100, 100]}}),
    ]
    payload = build_minimal_index([], {"result": []}, awakened_items=items)
    assert payload["schema_version"] == 2
    assert payload["base_armour"] == {
        "sacred chainmail": {"ar": [723, 831], "es": [145, 167]},
    }


def test_builder_keeps_minimal_gem_level_and_variant_metadata():
    items = [json.dumps({
        "name": "Arc of Surging", "refName": "Arc of Surging", "namespace": "GEM",
        "tradeDisc": "alt_x",
        "gem": {"transfigured": True, "normalVariant": "Arc", "maxLevel": 20},
    })]
    payload = build_minimal_index([], {"result": []}, awakened_items=items)
    assert payload["gems"] == {"arc of surging": {
        "trade_type": "Arc", "max_level": 20, "transfigured": True,
        "vaal": False, "discriminator": "alt_x",
    }}


def test_builder_keeps_awakened_unique_fixed_stats_and_loader_distinguishes_missing(tmp_path):
    items = [
        json.dumps({
            "name": "Watcher's Eye", "refName": "Watcher's Eye", "namespace": "UNIQUE",
            "unique": {
                "base": "Prismatic Jewel",
                "fixedStats": [
                    "#% increased maximum Energy Shield",
                    "#% increased maximum Life",
                    "#% increased maximum Mana",
                ],
            },
        }),
        json.dumps({
            "name": "No Metadata", "refName": "No Metadata", "namespace": "UNIQUE",
            "unique": {"base": "Ring"},
        }),
    ]
    payload = build_minimal_index([], {"result": []}, awakened_items=items)
    expected = {
        "#% increased maximum Energy Shield",
        "#% increased maximum Life",
        "#% increased maximum Mana",
    }
    assert set(payload["unique_fixed_stats"]["watcher's eye"]) == expected
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert unique_fixed_stats("WATCHER'S EYE", path) == frozenset(expected)
    assert unique_fixed_stats("No Metadata", path) is None


def test_metadata_search_bounds_support_minimum_maximum_and_exact():
    assert ModMetadata("r", "id", "explicit", ("被ダメージが#%増加する",), better=-1).search_bounds(20) == (None, 22.0)
    assert ModMetadata("r", "id", "explicit", ("値 #",), better=0).search_bounds(3) == (3, 3)
    assert ModMetadata("r", "id", "explicit", ("値 #",), better=1).search_bounds(100, 90, 100) == (100.0, None)
    assert ModMetadata("r", "id", "explicit", ("値 #",)).search_bounds(11) == (9.0, None)
    assert ModMetadata(
        "r", "id", "explicit", ("吸収 #%",), decimal=True,
    ).search_bounds(0.5) == (0.45, None)


def test_awakened_integer_stats_floor_relaxed_defaults_without_decimals():
    metadata = ModMetadata("r", "id", "explicit", ("値 #",))
    assert [metadata.search_bounds(value)[0] for value in (8, 11, 35, 3, 1)] == [
        7.0, 9.0, 31.0, 2.0, 0.0,
    ]


def test_metadata_index_matches_normalized_japanese_detail_copy():
    index = MetadataIndex((ModMetadata(
        "+# to maximum Life", "explicit.life", "explicit", ("最大ライフ +#",),
    ),))
    record, confidence = index.match("最大ライフ +100(90-100)", "prefix")
    assert record and record.stat_id == "explicit.life"
    assert confidence == 1.0


def test_builder_and_index_match_option_by_shared_trade_option_id():
    awakened = [json.dumps({
        "ref": "Allocates #", "better": 0,
        "matchers": [{"string": "Allocates Executioner", "value": 10016, "oils": "3,4,6"}],
        "trade": {"ids": {"enchant": ["enchant.allocates"]}, "option": True},
    })]
    jp = {"result": [{"entries": [{
        "id": "enchant.allocates", "type": "enchant", "text": "# を割り当てる",
        "option": {"options": [{"id": 10016, "text": "処刑人"}]},
    }]}]}
    payload = build_minimal_index(awakened, jp)
    option = payload["mods"][0]["options"][0]
    assert option == {
        "value": 10016, "japanese": "処刑人 を割り当てる",
        "english": "Allocates Executioner", "oils": [3, 4, 6],
    }
    index = MetadataIndex((ModMetadata(
        "Allocates #", "enchant.allocates", "enchant", ("# を割り当てる",),
        options=(OptionValue(10016, "処刑人 を割り当てる", "Allocates Executioner", (3, 4, 6)),),
    ),))
    record, matched, confidence = index.match_with_option("処刑人 を割り当てる (enchant)", "enchant")
    assert record and record.stat_id == "enchant.allocates"
    assert matched and matched.value == 10016 and matched.oils == (3, 4, 6)
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
        "inverted": False, "exact": False, "local": False, "decimal": False,
        "tiers": [], "options": [],
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
            "better": 1, "inverted": False, "exact": False, "local": False, "tiers": [], "options": [],
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
