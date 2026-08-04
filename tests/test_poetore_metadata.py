import json
from pathlib import Path

import pytest

from src.poetore.metadata import (
    MetadataIndex, ModMetadata, OptionValue, TierRange, pseudo_definitions, pseudo_relations,
    diff_pseudo_payloads, unique_fixed_stats, unique_icon_url, validate_pseudo_payload,
)
from src.poetore.metadata_builder import (
    apply_japanese_trade_overrides, audit_awakened_stat_rules,
    build_minimal_index, build_official_index,
    build_related_item_groups, diff_minimal_indexes,
    diff_official_trade_entries, excessive_removal, official_trade_entry_snapshot,
    unresolved_trade_entries, validate_minimal_index,
)
from scripts.extract_poetore_stat_rules import extract_rules


def test_official_builder_uses_official_japanese_repoe_tiers_and_poetore_rules():
    jp = {"result": [{"entries": [{
        "id": "explicit.stat_life", "type": "explicit", "text": "最大ライフ +#",
    }]}]}
    rules = {"rules": [{
        "ref": "+# to maximum Life", "stat_id": "explicit.stat_life",
        "kind": "explicit", "better": 1, "inverted": False,
        "negated": False, "exact": False, "decimal": False, "options": [],
    }]}
    repoe_stats = {"base_maximum_life": {"is_local": False}}
    repoe_mods = {"Life1": {
        "domain": "item", "text": "+# to maximum Life", "required_level": 1,
        "generation_type": "prefix", "stats": [{"id": "base_maximum_life", "min": 10, "max": 19}],
    }}

    row = build_official_index(jp, rules, repoe_stats, repoe_mods)["mods"][0]

    assert row["japanese"] == ["最大ライフ +#"]
    assert row["better"] == 1
    assert row["tiers"][0]["mod_id"] == "Life1"


def test_awakened_is_comparison_only_for_poetore_stat_rules():
    awakened = [json.dumps({
        "ref": "+# to maximum Life", "better": -1,
        "matchers": [{"string": "+# to maximum Life"}],
        "trade": {"ids": {"explicit": ["explicit.stat_life"]}},
    })]
    rules = {"rules": [{
        "ref": "+# to maximum Life", "stat_id": "explicit.stat_life",
        "kind": "explicit", "better": 1, "inverted": False,
        "negated": False, "exact": False, "decimal": False,
    }]}

    audit = audit_awakened_stat_rules(awakened, rules)

    assert audit["changed"] == [{
        "kind": "explicit", "stat_id": "explicit.stat_life", "fields": ["better"],
    }]


def test_official_trade_diff_lists_new_removed_and_reworded_stats():
    previous = {"entries": [
        {"kind": "explicit", "stat_id": "same", "japanese": "旧文面 #"},
        {"kind": "implicit", "stat_id": "removed", "japanese": "削除 #"},
    ]}
    current_payload = {"result": [{"entries": [
        {"type": "explicit", "id": "same", "text": "新文面 #"},
        {"type": "crafted", "id": "added", "text": "追加 #"},
        {"type": "pseudo", "id": "ignored", "text": "対象外 #"},
    ]}]}

    current = official_trade_entry_snapshot(current_payload)
    diff = diff_official_trade_entries(previous, current)

    assert diff["previous_count"] == 2
    assert diff["current_count"] == 2
    assert diff["added"] == [{
        "kind": "crafted", "stat_id": "added", "japanese": "追加 #",
    }]
    assert diff["removed"] == [{
        "kind": "implicit", "stat_id": "removed", "japanese": "削除 #",
    }]
    assert diff["changed"] == [{
        "kind": "explicit", "stat_id": "same",
        "previous_japanese": "旧文面 #", "current_japanese": "新文面 #",
    }]


def test_japanese_trade_override_preserves_known_translation_regression():
    upstream = {"result": [{"entries": [{
        "type": "veiled", "id": "veiled.mod_65000", "text": "Veiled",
    }]}]}
    overrides = {"overrides": [{
        "kind": "veiled", "stat_id": "veiled.mod_65000",
        "japanese": "ヴェールされた",
    }]}

    effective, applied = apply_japanese_trade_overrides(upstream, overrides)

    assert upstream["result"][0]["entries"][0]["text"] == "Veiled"
    assert effective["result"][0]["entries"][0]["text"] == "ヴェールされた"
    assert applied == [{
        "kind": "veiled", "stat_id": "veiled.mod_65000",
        "upstream": "Veiled", "effective": "ヴェールされた",
    }]


def test_japanese_trade_override_rejects_unknown_stat():
    try:
        apply_japanese_trade_overrides(
            {"result": []},
            {"overrides": [{
                "kind": "veiled", "stat_id": "veiled.missing", "japanese": "値",
            }]},
        )
    except ValueError as error:
        assert "veiled:veiled.missing" in str(error)
    else:
        raise AssertionError("unknown override must fail")


@pytest.mark.parametrize(("stat_id", "japanese"), [
    (
        "explicit.stat_1574578643",
        "ピュリティオブエレメントの影響を受けている間受ける反射元素ダメージの+#%を防ぐ",
    ),
    (
        "explicit.stat_2255585376",
        "デターミネーションの影響を受けている間受ける反射物理ダメージの+#%を防ぐ",
    ),
    (
        "explicit.stat_3829555156",
        "右の指輪スロット: プレイヤーおよびミニオンは反射物理ダメージの+#%を防ぐ",
    ),
    (
        "explicit.stat_3991837781",
        "左の指輪スロット: プレイヤーおよびミニオンは反射元素ダメージの+#%を防ぐ",
    ),
    (
        "implicit.stat_1973340656",
        "アトラスのピナクルボスが付近にいる場合、ミニオンは受ける反射ダメージの+#%を防ぐ",
    ),
    (
        "implicit.stat_2467518140",
        "ミニオンは受ける反射ダメージの+#%を防ぐ",
    ),
    (
        "crafted.stat_603134774",
        "効果中は反射ダメージの+#%を防ぐ",
    ),
    (
        "explicit.stat_603134774",
        "効果中は反射ダメージの+#%を防ぐ",
    ),
    (
        "implicit.stat_2173565521",
        "アトラスのピナクルボスが付近にいる場合、反射ダメージの+#%を防ぐ",
    ),
    (
        "implicit.stat_2510655429",
        "反射ダメージの+#%を防ぐ",
    ),
])
def test_default_metadata_keeps_reviewed_reflect_japanese(stat_id, japanese):
    payload = json.loads(Path("data/poetore/mod_metadata.json").read_text(encoding="utf-8"))
    row = next(row for row in payload["mods"] if row["stat_id"] == stat_id)
    assert row["japanese"] == [japanese]
    assert (row["better"], row["inverted"], row["negated"]) == (-1, True, True)


def test_stat_rule_extractor_drops_runtime_and_repoe_fields():
    rules = extract_rules({"mods": [{
        "ref": "r", "stat_id": "explicit.id", "kind": "explicit",
        "japanese": ["値 #"], "better": 1, "inverted": False,
        "negated": False, "exact": False, "local": True, "decimal": False,
        "tiers": [{"tier": 1}], "options": [],
    }]}, "abc123")

    assert rules["rules"] == [{
        "ref": "r", "stat_id": "explicit.id", "kind": "explicit",
        "better": 1, "inverted": False, "negated": False,
        "exact": False, "decimal": False, "options": [],
    }]
    assert rules["initial_source_sha256"] == "abc123"


def test_default_metadata_uses_latest_reviewed_awakened_snapshot():
    payload = json.loads(Path("data/poetore/mod_metadata.json").read_text(encoding="utf-8"))

    assert payload["sources"]["awakened_poe_trade"]["revision"] == (
        "31b3e0e8ba0a6bac2266603c2e170925c8f02b81"
    )
    assert payload["gems"]["coursing current support"]["max_level"] == 3
    assert payload["unique_fixed_stats"]["heroic tragedy"] == ["Historic"]
    assert any(
        row["stat_id"] == "explicit.pseudo_timeless_jewel_zorath"
        for row in payload["mods"]
    )
    assert any(
        any(item["name"] == "Reclaimed Malevolence" for item in group["items"])
        for group in payload["related_item_groups"]
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
        "ref", "stat_id", "kind", "japanese", "better", "inverted", "negated",
        "exact", "local", "decimal", "tiers", "options",
    }
    assert row["decimal"] is False


def test_builder_keeps_awakened_ref_matcher_negate_for_shared_increase_reduction_stat():
    awakened = [json.dumps({
        "ref": "#% reduced Effect of Curses on you during Effect",
        "better": -1,
        "matchers": [
            {"string": "#% increased Effect of Curses on you during Effect"},
            {
                "string": "#% reduced Effect of Curses on you during Effect",
                "negate": True,
            },
        ],
        "trade": {
            "ids": {"explicit": ["explicit.stat_4265534424"]},
            "inverted": True,
        },
    })]
    jp = {"result": [{"entries": [{
        "id": "explicit.stat_4265534424", "type": "explicit",
        "text": "効果中にプレイヤーに対する呪いの効果が#%減少する",
    }]}]}

    row = build_minimal_index(awakened, jp)["mods"][0]

    assert (row["better"], row["inverted"], row["negated"]) == (-1, True, True)


def test_builder_matches_ref_negate_when_only_literal_plus_differs():
    awakened = [json.dumps({
        "ref": "Minions prevent +#% of Reflected Damage they would take",
        "better": -1,
        "matchers": [{
            "string": "Minions prevent #% of Reflected Damage they would take",
            "negate": True,
        }],
        "trade": {
            "ids": {"implicit": ["implicit.stat_2467518140"]},
            "inverted": True,
        },
    })]
    jp = {"result": [{"entries": [{
        "id": "implicit.stat_2467518140", "type": "implicit",
        "text": "ミニオンは受ける反射ダメージの+#%を防ぐ",
    }]}]}

    row = build_minimal_index(awakened, jp)["mods"][0]
    assert row["negated"] is True
    rules = {"rules": [{
        "ref": row["ref"], "stat_id": row["stat_id"], "kind": row["kind"],
        "better": row["better"], "inverted": row["inverted"],
        "negated": row["negated"], "exact": row["exact"],
        "decimal": row["decimal"],
    }]}
    assert audit_awakened_stat_rules(awakened, rules)["changed"] == []


def test_builder_keeps_awakened_category_select_resolver():
    awakened = [json.dumps({
        "resolve": {"strat": "select", "test": [None, "WEAPON"]},
        "stats": [
            {
                "ref": "#% increased Attack Speed",
                "trade": {"ids": {"explicit": ["explicit.global_attack_speed"]}},
            },
            {
                "ref": "#% increased Attack Speed",
                "trade": {"ids": {"explicit": ["explicit.local_attack_speed"]}},
            },
        ],
    })]
    jp = {"result": [{"entries": [
        {
            "id": "explicit.global_attack_speed", "type": "explicit",
            "text": "アタックスピードが#%増加する",
        },
        {
            "id": "explicit.local_attack_speed", "type": "explicit",
            "text": "アタックスピードが#%増加する (ローカル)",
        },
    ]}]}

    payload = build_minimal_index(awakened, jp)
    rows = {row["stat_id"]: row for row in payload["mods"]}

    assert rows["explicit.global_attack_speed"]["category_select"] is None
    assert rows["explicit.local_attack_speed"]["category_select"] == "WEAPON"


def test_category_select_uses_global_attack_speed_for_accessory():
    index = MetadataIndex((
        ModMetadata(
            ref="#% increased Attack Speed", stat_id="explicit.global",
            kind="explicit", japanese=("アタックスピードが#%増加する",),
            category_select="",
        ),
        ModMetadata(
            ref="#% increased Attack Speed", stat_id="explicit.local",
            kind="explicit", japanese=("アタックスピードが#%増加する",),
            category_select="WEAPON",
        ),
    ))

    accessory, _, confidence = index.match_for_item_category(
        "アタックスピードが10%増加する", "explicit", "accessory",
    )
    weapon, _, _ = index.match_for_item_category(
        "アタックスピードが10%増加する", "explicit", "weapon",
    )

    assert accessory.stat_id == "explicit.global"
    assert weapon.stat_id == "explicit.local"
    assert confidence == 1.0


def test_builder_restores_official_cluster_option_entries_to_base_stat():
    jp = {
        "result": [{
            "entries": [
                {
                    "id": "enchant.stat_3948993189|23",
                    "type": "enchant",
                    "text": "追加される通常パッシブスキルは付与: 非ダメージ性状態異常の効果が10%増加する",
                },
                {
                    "id": "enchant.stat_3948993189|43",
                    "type": "enchant",
                    "text": "追加される通常パッシブスキルは付与: 回避力が15%増加する",
                },
            ],
        }],
    }

    payload = build_minimal_index([], jp)
    record = next(
        row for row in payload["mods"]
        if row["stat_id"] == "enchant.stat_3948993189"
    )

    assert record["exact"] is True
    assert [option["value"] for option in record["options"]] == [23, 43]
    assert record["options"][1]["japanese"].endswith("回避力が15%増加する")


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
    assert payload["schema_version"] == 3
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


def test_builder_keeps_official_unique_icon_url(tmp_path):
    icon = "https://web.poecdn.com/gen/image/example/WatchersEye.png"
    items = [json.dumps({
        "name": "Watcher's Eye", "refName": "Watcher's Eye", "namespace": "UNIQUE",
        "unique": {"base": "Prismatic Jewel"}, "icon": icon,
    })]
    payload = build_minimal_index([], {"result": []}, awakened_items=items)
    assert payload["unique_icons"] == {"watcher's eye": icon}
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert unique_icon_url("WATCHER'S EYE", path) == icon
    assert unique_icon_url("No Metadata", path) is None


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


def test_metadata_index_prefers_mutated_unique_stat_for_foulborn_heading():
    text = "ソケットされたジェムはレベル#投射物回帰によりサポートされる"
    index = MetadataIndex((
        ModMetadata(
            "random support", "explicit.random", "explicit", (text,),
        ),
        ModMetadata(
            "mutated unique", "explicit.foulborn", "explicit", (text,),
            tiers=(TierRange(
                None, 20, 20, generation="unique",
                mod_id="MutatedUniqueBow18DisplaySupportedByReturningProjectiles",
            ),),
        ),
        ModMetadata(
            "other", "explicit.other", "explicit", (text,),
        ),
    ))

    record, option, confidence = index.match_for_item_category(
        "ソケットされたジェムはレベル20投射物回帰によりサポートされる",
        "explicit", "weapon", "foulborn",
    )

    assert record and record.stat_id == "explicit.foulborn"
    assert option is None
    assert confidence == 1.0


def test_metadata_index_matches_unique_single_value_directional_inverse():
    index = MetadataIndex((ModMetadata(
        "#% increased Duration", "explicit.duration", "explicit",
        ("持続時間が#%増加する",),
    ),))
    record, option, confidence = index.match_directional_inverse(
        "持続時間が36(39-35)%低下する", "explicit",
    )
    assert record and record.stat_id == "explicit.duration"
    assert option is None
    assert confidence == 1.0


def test_metadata_index_rejects_ambiguous_or_multi_value_directional_inverse():
    records = (
        ModMetadata("first", "explicit.first", "explicit", ("効果が#%増加する",)),
        ModMetadata("second", "explicit.second", "explicit", ("効果が#%増加する",)),
        ModMetadata(
            "per attribute", "explicit.attribute", "explicit",
            ("筋力250ごとに受けるダメージが#%増加する",),
        ),
    )
    index = MetadataIndex(records)
    assert index.match_directional_inverse("効果が20%低下する", "explicit")[0] is None
    assert index.match_directional_inverse(
        "筋力250ごとに受けるダメージが1%低下する", "explicit",
    )[0] is None


def test_directional_inverse_uses_item_category_to_select_flask_stat():
    index = MetadataIndex((
        ModMetadata(
            "#% increased effect", "explicit.flask", "explicit",
            ("効果が#%増加する",), category_select="",
        ),
        ModMetadata(
            "#% increased effect", "explicit.tincture", "explicit",
            ("効果が#%増加する",), category_select="Tincture",
        ),
    ))

    record, option, confidence = index.match_directional_inverse(
        "効果が25%減少する", "prefix", "flask",
    )

    assert record is not None
    assert record.stat_id == "explicit.flask"
    assert option is None
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


def test_builder_keeps_trade_site_composite_stat_id_without_option_picker():
    awakened = [json.dumps({
        "ref": "Allocates Bastion of Elements if you have the matching modifier on Forbidden Flame",
        "better": 0,
        "matchers": [{
            "string": (
                "Allocates Bastion of Elements if you have the matching modifier "
                "on Forbidden Flame"
            ),
        }],
        "trade": {"ids": {"explicit": ["explicit.stat_2460506030|4917"]}},
    })]
    jp = {"result": [{"entries": [{
        "id": "explicit.stat_2460506030|4917",
        "type": "explicit",
        "text": "禁じられた炎に一致するモッドがあれば元素の要塞を割り当てる",
    }]}]}

    payload = build_minimal_index(awakened, jp)

    assert payload["mods"] == [{
        "ref": (
            "Allocates Bastion of Elements if you have the matching modifier "
            "on Forbidden Flame"
        ),
        "stat_id": "explicit.stat_2460506030|4917",
        "kind": "explicit",
        "japanese": ["禁じられた炎に一致するモッドがあれば元素の要塞を割り当てる"],
        "better": 0,
        "inverted": False,
        "negated": False,
        "exact": True,
        "local": False,
        "decimal": False,
        "tiers": (),
        "options": [],
    }]


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


def test_builder_expands_awakened_related_item_groups():
    items = [
        json.dumps({
            "namespace": "ITEM", "refName": "Chayula's Breachstone",
            "icon": "stone.png",
        }),
        json.dumps({
            "namespace": "UNIQUE", "refName": "Skin of the Loyal",
            "icon": "skin.png", "unique": {"base": "Simple Robe"},
        }),
    ]
    payload = build_minimal_index(
        [], {"result": []}, awakened_items=items,
        awakened_item_drops=[{
            "query": ["ITEM::Chayula's Breachstone"],
            "items": ["UNIQUE::Skin of the Loyal // Simple Robe"],
        }],
    )
    group = payload["related_item_groups"][0]
    assert group["query"][0]["name"] == "Chayula's Breachstone"
    assert group["items"][0]["icon"] == "skin.png"


def test_builder_normalizes_legacy_doryani_delusion_base_variants():
    groups = build_related_item_groups([], [{
        "query": ["UNIQUE::Doryani's Machinarium // T0"],
        "items": [
            "UNIQUE::Doryani's Delusion // Leviathan Greaves",
            "UNIQUE::Doryani's Delusion // Warlock Boots",
            "UNIQUE::Doryani's Delusion // Velour Boots",
        ],
    }])

    assert [row["variant"] for row in groups[0]["items"]] == [
        "Titan Greaves", "Sorcerer Boots", "Slink Boots",
    ]


def test_builder_labels_watchers_eye_beastcraft_group():
    groups = build_related_item_groups([], [{
        "query": [
            "UNIQUE::Watcher's Eye // Prismatic Jewel",
            "CAPTURED_BEAST::Wild Hellion Alpha",
        ],
        "items": [],
    }])

    assert groups[0]["query_label"] == "ビーストクラフト素材：Modをリロール"


def test_builder_supplements_all_uber_boss_groups_with_shared_drops():
    query_ids = (
        "Awakening Fragment", "Reality Fragment", "Devouring Fragment",
        "Blazing Fragment", "Cosmic Fragment", "Decaying Fragment",
        "Synthesising Fragment",
    )
    expected = {
        "Awakening Fragment": {"Awakener's Orb", "Orb of Dominance"},
        "Reality Fragment": {"Orb of Conflict", "Awakened Empower Support"},
        "Devouring Fragment": {"Forbidden Flesh", "Exceptional Eldritch Ichor"},
        "Blazing Fragment": {"Forbidden Flame", "Exceptional Eldritch Ember"},
        "Cosmic Fragment": {"Shaper's Exalted Orb", "Orb of Dominance"},
        "Decaying Fragment": {"Watcher's Eye", "Elder's Exalted Orb"},
        "Synthesising Fragment": {"Greater Kinetic Instability Support", "The Hook"},
    }
    items = [
        json.dumps({"namespace": "ITEM", "refName": name})
        for name in query_ids
    ]
    groups = build_related_item_groups(
        items,
        [{"query": [f"ITEM::{name}"], "items": []} for name in query_ids],
    )

    assert len(groups) == 7
    for group in groups:
        query_name = group["query"][0]["name"]
        assert expected[query_name] <= {row["name"] for row in group["items"]}


def test_builder_deduplicates_upstream_and_supplemental_uber_drops():
    groups = build_related_item_groups([], [{
        "query": ["ITEM::Awakening Fragment"],
        "items": ["ITEM::Orb of Dominance"],
    }])

    names = [row["name"] for row in groups[0]["items"]]
    assert names.count("Orb of Dominance") == 1


def test_builder_excludes_mf_and_levelling_comparison_groups():
    groups = build_related_item_groups([], [
        {
            "query": [
                "UNIQUE::Ventor's Gamble // Gold Ring",
                "UNIQUE::Sadima's Touch // Wool Gloves",
                "UNIQUE::Bisco's Leash // Heavy Belt",
                "UNIQUE::Goldwyrm // Nubuck Boots",
                "UNIQUE::Divination Distillate",
                "UNIQUE::The Ascetic // Gold Amulet",
                "UNIQUE::Greed's Embrace // Golden Plate",
                "UNIQUE::Sentari's Answer // Brass Spirit Shield",
            ],
            "items": [],
        },
        {
            "query": [
                "GEM::Cast on Death Support",
                "UNIQUE::Goldrim // Leather Cap",
                "UNIQUE::Tabula Rasa // Simple Robe, 6L",
                "UNIQUE::Lochtonial Caress // Iron Gauntlets",
                "UNIQUE::Wanderlust // Wool Shoes",
                "UNIQUE::Lifesprig // Driftwood Wand",
                "UNIQUE::Karui Ward // Jade Amulet",
            ],
            "items": [],
        },
        {
            "query": ["ITEM::Golden Oil", "ITEM::Silver Oil"],
            "items": [],
        },
    ])

    assert len(groups) == 1
    assert [row["name"] for row in groups[0]["query"]] == [
        "Golden Oil", "Silver Oil",
    ]


def test_builder_excludes_nightmare_map_drop_group():
    groups = build_related_item_groups([], [
        {
            "query": ["ITEM::Nightmare Map // T0, Atlas"],
            "items": ["UNIQUE::Yoke of Suffering // Onyx Amulet"],
        },
        {
            "query": ["ITEM::Golden Oil", "ITEM::Silver Oil"],
            "items": [],
        },
    ])

    assert len(groups) == 1
    assert [row["name"] for row in groups[0]["query"]] == [
        "Golden Oil", "Silver Oil",
    ]


def test_builder_excludes_removed_shadowed_crow_scarab_only():
    groups = build_related_item_groups([], [{
        "query": [
            "ITEM::Orb of Fusing",
            "ITEM::Omen of Connections",
            "ITEM::Bestiary Scarab of the Shadowed Crow",
            "CAPTURED_BEAST::Black Mórrigan",
            "CAPTURED_BEAST::Craicic Sand Spitter",
        ],
        "items": [],
    }])

    assert [row["id"] for row in groups[0]["query"]] == [
        "ITEM::Orb of Fusing",
        "ITEM::Omen of Connections",
        "CAPTURED_BEAST::Black Mórrigan",
        "CAPTURED_BEAST::Craicic Sand Spitter",
    ]


def test_builder_excludes_bestiary_armour_comparison_groups():
    groups = build_related_item_groups([], [
        {
            "query": [
                "UNIQUE::Farrul's Bite // Harlequin Mask",
                "UNIQUE::Farrul's Pounce // Hydrascale Gauntlets",
                "UNIQUE::Farrul's Fur // Triumphant Lamellar",
                "UNIQUE::Farrul's Chase // Slink Boots",
            ],
            "items": [],
        },
        {
            "query": ["ITEM::Abrasive Catalyst", "ITEM::Fertile Catalyst"],
            "items": [],
        },
    ])

    assert len(groups) == 1
    assert [row["name"] for row in groups[0]["query"]] == [
        "Abrasive Catalyst", "Fertile Catalyst",
    ]


def test_index_validation_reports_duplicates_empty_and_ambiguous_matchers():
    base = {
        "ref": "r", "kind": "explicit", "japanese": ["値 #"], "better": 1,
        "inverted": False, "negated": False, "exact": False, "local": False, "decimal": False,
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
            "better": 1, "inverted": False, "negated": False, "exact": False, "local": False, "tiers": [], "options": [],
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
