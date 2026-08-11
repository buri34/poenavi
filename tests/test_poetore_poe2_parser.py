from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.poetore.poe2.parser import Poe2ItemParseError, TRADE_CATEGORY_BY_CATEGORY, parse_item_text
from src.poetore.poe2.trade import build_search_query, poe2_trade_filters
from src.poetore.poe2.fixture_loader import load_real_copy_rows


FIXTURES = Path(__file__).parent / "fixtures" / "poe2" / "minimal_items.json"
PHASE6_FIXTURES = Path(__file__).parent / "fixtures" / "poe2" / "phase6_special_items_ja.json"
AMBIGUOUS_BASE_FIXTURES = (
    Path(__file__).parent / "fixtures" / "poe2" / "ambiguous_bases_bilingual.json"
)
REAL_COPY_FIXTURES = Path(__file__).parent / "fixtures" / "poe2" / "real_copy_bilingual.csv"


def _fixtures():
    return json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]


def _phase6_fixtures():
    return json.loads(PHASE6_FIXTURES.read_text(encoding="utf-8"))["fixtures"]


def _ambiguous_base_fixtures():
    return json.loads(AMBIGUOUS_BASE_FIXTURES.read_text(encoding="utf-8"))["fixtures"]


def _real_copy_fixtures():
    return load_real_copy_rows(REAL_COPY_FIXTURES)


def _real_copy(fixture_id):
    return next(row for row in _real_copy_fixtures() if row["fixture_id"] == fixture_id)


def test_real_copy_fixture_file_references_are_resolved_and_sandboxed(tmp_path):
    fixture = tmp_path / "copy.txt"
    fixture.write_text("Item Class: Belts\nRarity: Unique\nMageblood\nUtility Belt\n", encoding="utf-8")
    csv_source = tmp_path / "fixtures.csv"
    csv_source.write_text(
        "fixture_id,日本語設定の詳細コピー全文,英語設定の詳細コピー全文\n"
        "FX,@copy.txt,@copy.txt\n", encoding="utf-8",
    )
    rows = load_real_copy_rows(csv_source)
    assert rows[0]["日本語設定の詳細コピー全文"].startswith("Item Class: Belts")
    csv_source.write_text(
        "fixture_id,日本語設定の詳細コピー全文,英語設定の詳細コピー全文\n"
        "FX,@../outside.txt,@copy.txt\n", encoding="utf-8",
    )
    with pytest.raises(ValueError, match="不正なfixture参照"):
        load_real_copy_rows(csv_source)


def test_new_user_captured_special_pairs_preserve_state_stats_and_values():
    fixtures = {row["fixture_id"]: row for row in _real_copy_fixtures()}
    expected = {
        "FX019": ("Anvil Maul", {"crafted", "desecrated", "sanctified"}, {
            "implicit.stat_1503146834", "explicit.stat_9187492", "desecrated.stat_53386210",
        }),
        "FX024": ("Ornate Ringmail", {"mirrored"}, {"explicit.stat_3032590688"}),
        "FX026": ("Utility Belt", set(), {
            "implicit.stat_1416292992", "explicit.stat_264262054|3",
            "explicit.stat_264262054|11", "explicit.stat_264262054|4",
            "explicit.stat_264262054|8",
        }),
        "FX027": ("Time-Lost Diamond", {"corrupted"}, {
            "explicit.stat_2948688907", "explicit.stat_2217513089",
        }),
        "FX028": ("Gold Ring", set(), {
            "explicit.stat_3372524247", "explicit.stat_4220027924",
            "explicit.stat_1671376347",
        }),
    }
    for fixture_id, (base_type, flags, expected_ids) in expected.items():
        parsed = [parse_item_text(fixtures[fixture_id][column]) for column in (
            "日本語設定の詳細コピー全文", "英語設定の詳細コピー全文",
        )]
        assert all(item.base_type == base_type for item in parsed)
        assert [set(item.flags) for item in parsed] == [flags, flags]
        assert all(not [modifier for modifier in item.modifiers if not modifier.ref] for item in parsed)
        filter_ids = [
            {row.stat_id for row in poe2_trade_filters(item)} for item in parsed
        ]
        assert expected_ids <= filter_ids[0] == filter_ids[1]

    sanctified = parse_item_text(fixtures["FX019"]["日本語設定の詳細コピー全文"])
    sanctified_rows = {row.stat_id: row for row in poe2_trade_filters(sanctified)}
    assert sanctified_rows["explicit.stat_709508406"].read_value == 118.5
    assert sanctified_rows["explicit.stat_9187492"].read_value == 4
    assert sanctified_rows["property.state.sanctified"].enabled is True

    ventor = parse_item_text(fixtures["FX028"]["英語設定の詳細コピー全文"])
    ventor_rows = {row.stat_id: row for row in poe2_trade_filters(ventor)}
    assert [ventor_rows[stat_id].read_value for stat_id in (
        "explicit.stat_3372524247", "explicit.stat_4220027924",
        "explicit.stat_1671376347",
    )] == [-22, -21, -2]

    for fixture_id, state, trade_filter in (
        ("FX019", "sanctified", "sanctified"),
        ("FX024", "mirrored", "mirrored"),
        ("FX027", "corrupted", "corrupted"),
    ):
        item = parse_item_text(fixtures[fixture_id]["日本語設定の詳細コピー全文"])
        rows = poe2_trade_filters(item)
        state_row = next(row for row in rows if row.stat_id == f"property.state.{state}")
        assert state_row.enabled is True
        query = build_search_query(item, stat_filters=rows)["query"]
        assert query["filters"]["misc_filters"]["filters"][trade_filter] == {
            "option": "true",
        }


@pytest.mark.parametrize(
    "fixture",
    tuple(
        row for row in _real_copy_fixtures()
        if row["日本語設定の詳細コピー全文"].strip()
        and not row["日本語設定の詳細コピー全文"].startswith("ちょっと一旦保留")
        and row["fixture_id"] != "FX008"
    ),
    ids=lambda row: row["fixture_id"],
)
def test_user_captured_real_copy_pairs_resolve_to_same_identity(fixture):
    ja = parse_item_text(fixture["日本語設定の詳細コピー全文"])
    en = parse_item_text(fixture["英語設定の詳細コピー全文"])
    assert (ja.base_type, ja.category, ja.rarity) == (en.base_type, en.category, en.rarity)


def test_meta_gem_without_item_class_requires_meta_tag_and_metadata_identity():
    fixture = _real_copy("FX007")
    for language in ("日本語設定の詳細コピー全文", "英語設定の詳細コピー全文"):
        item = parse_item_text(fixture[language])
        assert (item.base_type, item.category, item.modifiers) == ("Blasphemy", "meta_gem", ())
        without_meta = fixture[language].replace("メタ", "永続").replace("Meta", "Persistent")
        with pytest.raises(Poe2ItemParseError, match="class、rarity、identity"):
            parse_item_text(without_meta)


def test_gem_prose_is_not_reported_as_unresolved_item_modifiers():
    for fixture_id in ("FX005", "FX006", "FX007"):
        fixture = _real_copy(fixture_id)
        assert parse_item_text(fixture["日本語設定の詳細コピー全文"]).modifiers == ()
        assert parse_item_text(fixture["英語設定の詳細コピー全文"]).modifiers == ()


def test_charm_properties_and_searchable_mods_resolve_equally_in_both_languages():
    charm = _real_copy("FX009")
    charm_items = [parse_item_text(charm[key]) for key in (
        "日本語設定の詳細コピー全文", "英語設定の詳細コピー全文",
    )]
    assert [len(item.modifiers) for item in charm_items] == [2, 2]
    assert all(any(mod.stat_id == "implicit.stat_1691862754" for mod in item.modifiers) for item in charm_items)
    assert all(any(
        mod.stat_id == "explicit.stat_388617051" and mod.values == (-20.0,)
        for mod in item.modifiers
    ) for item in charm_items)
    assert all(item.properties["持続時間"] == "3" for item in charm_items)
    assert all(item.properties["使用チャージ"] == "32" for item in charm_items)
    assert all(item.properties["最大チャージ"] == "40" for item in charm_items)
    assert all(item.properties["現在チャージ"] == "0" for item in charm_items)
    assert all(item.properties["効果"] for item in charm_items)
    for item in charm_items:
        payload = build_search_query(item, stat_filters=poe2_trade_filters(item))
        sent_ids = {
            row["id"]
            for group in payload["query"]["stats"]
            for row in group["filters"]
        }
        assert sent_ids == {"implicit.stat_1691862754", "explicit.stat_388617051"}
        charge_filter = next(
            row
            for group in payload["query"]["stats"]
            for row in group["filters"]
            if row["id"] == "explicit.stat_388617051"
        )
        assert charge_filter["value"] == {"max": -20.0}


def test_timelost_unscalable_suffixes_resolve_equally_in_both_languages():

    jewel = _real_copy("FX014")
    jewel_items = [parse_item_text(jewel[key]) for key in (
        "日本語設定の詳細コピー全文", "英語設定の詳細コピー全文",
    )]
    assert all(len(item.modifiers) == 5 for item in jewel_items)
    assert all(sum(not mod.stat_id for mod in item.modifiers) == 0 for item in jewel_items)
    assert all({"crafted", "desecrated"}.issubset(item.flags) for item in jewel_items)


@pytest.mark.parametrize("fixture_id", ("FX001", "FX003", "FX010", "FX022", "FX023"))
def test_real_copy_previously_unresolved_numeric_lines_are_resolved(fixture_id):
    fixture = _real_copy(fixture_id)
    for language in ("日本語設定の詳細コピー全文", "英語設定の詳細コピー全文"):
        item = parse_item_text(fixture[language])
        assert all(mod.stat_id for mod in item.modifiers), [
            mod.text for mod in item.modifiers if not mod.stat_id
        ]
    if fixture_id == "FX010":
        ja = parse_item_text(fixture["日本語設定の詳細コピー全文"])
        en = parse_item_text(fixture["英語設定の詳細コピー全文"])
        assert ja.properties["残り使用回数"] == en.properties["残り使用回数"] == "10"


def test_runemastered_and_unidentified_unique_are_preserved_as_distinct_states():
    runemastered = parse_item_text(_real_copy("FX022")["英語設定の詳細コピー全文"])
    assert "runemastered" in runemastered.flags
    assert "runeforged" not in runemastered.flags
    evasion = next(mod for mod in runemastered.modifiers if "Evasion Rating" in (mod.ref or ""))
    assert evasion.stat_id == "explicit.stat_124859000"

    unidentified = _real_copy("FX025")
    for language in ("日本語設定の詳細コピー全文", "英語設定の詳細コピー全文"):
        item = parse_item_text(unidentified[language])
        assert (item.name, item.base_type, item.category) == ("", "Nettle Talisman", "talisman")
        assert "unidentified" in item.flags


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


@pytest.mark.parametrize("fixture", _ambiguous_base_fixtures(), ids=lambda row: row["id"])
@pytest.mark.parametrize("language", ("ja", "en"))
def test_user_captured_bilingual_ambiguous_bases_resolve_exactly(fixture, language):
    item = parse_item_text(fixture[language])
    assert item.base_type == fixture["expected_base_type"]
    assert item.category in {"body_armour", "boots", "gloves", "helmet"}


def test_ambiguous_localized_base_without_discriminator_is_not_guessed():
    text = (
        "アイテムクラス: 靴\nレアリティ: レア\nテスト品\n要塞のサバトン\n"
        "--------\nアイテムレベル: 80\n"
    )
    with pytest.raises(Poe2ItemParseError, match="base identity曖昧"):
        parse_item_text(text)


@pytest.mark.parametrize("fixture", _phase6_fixtures(), ids=lambda row: row["id"])
def test_phase6_special_categories_resolve_to_trade_identity(fixture):
    item = parse_item_text(fixture["text"])
    assert item.base_type == fixture["base_type"]
    assert item.category == fixture["category"]
    assert TRADE_CATEGORY_BY_CATEGORY[item.category] == fixture["trade_category"]
    if "name" in fixture:
        assert item.name == fixture["name"]


def test_phase6_relic_trial_and_timelost_properties_are_preserved():
    fixtures = {row["id"]: parse_item_text(row["text"]) for row in _phase6_fixtures()}
    relic = fixtures["sanctum_relic"]
    assert [(mod.kind, mod.stat_id, mod.values) for mod in relic.modifiers] == [
        ("sanctum", "sanctum.stat_4057192895", (5.0,)),
    ]
    assert fixtures["djinn_barya"].properties == {"エリアレベル": "80", "試練数": "3"}
    assert fixtures["inscribed_ultimatum"].properties["Ultimatum Hint"] == "Deadly"
    assert fixtures["timelost_jewel"].properties["半径"] == "大"
    assert fixtures["normal_tablet"].properties["残り使用回数"] == "10"


def test_poe2_roll_ranges_are_averaged_and_only_safe_ranges_get_better_direction():
    spear = parse_item_text(
        (Path(__file__).parent / "fixtures" / "poe2" / "rare_spear_ja.txt").read_text(
            encoding="utf-8"
        )
    )
    flat = next(mod for mod in spear.modifiers if mod.stat_id == "explicit.stat_1940865751")
    assert (flat.roll_min, flat.roll_max, flat.better) == (28.5, 42.0, 1)

    text = """アイテムクラス: ウェイストーン
レアリティ: マジック
減退する ウェイストーン (ティア15)
--------
アイテムレベル: 81
--------
{ サフィックスモッド }
モンスターがクリティカルヒットから受ける追加ダメージが28(26-30)%減少する
"""
    reduced = parse_item_text(text).modifiers[0]
    assert (reduced.roll_min, reduced.roll_max, reduced.better) == (26.0, 30.0, None)


def test_poe2_standalone_rune_line_counts_one_installed_augment():
    item = parse_item_text(
        (Path(__file__).parent / "fixtures" / "poe2" / "phase45_sceptre_ja.txt").read_text(
            encoding="utf-8"
        )
    )
    assert item.augment_count == 1


def test_unknown_base_is_not_silently_guessed():
    with pytest.raises(Poe2ItemParseError, match="base identity未解決"):
        parse_item_text("Item Class: Bows\nRarity: Rare\nTest Name\nUnknown Bow\n")


@pytest.mark.parametrize(
    ("item_class", "affixed_name", "expected_base", "expected_category"),
    [
        ("Focus", "Pulsing Antler Focus", "Antler Focus", "focus"),
        ("Two Hand Mace", "Reaver's Temple Maul of Stunning", "Temple Maul", "two_mace"),
        ("指輪", "火炎の アメジストの指輪", "Amethyst Ring", "ring"),
        ("鎧", "幻術の スリップストライクベスト", "Slipstrike Vest", "body_armour"),
    ],
)
def test_magic_items_extract_longest_category_matching_base_from_affixed_name(
    item_class, affixed_name, expected_base, expected_category,
):
    item = parse_item_text(
        f"アイテムクラス: {item_class}\n"
        f"レアリティ: マジック\n{affixed_name}\n--------\nアイテムレベル: 80\n"
    )

    assert item.base_type == expected_base
    assert item.category == expected_category
    assert affixed_name not in item.base_type


@pytest.mark.parametrize(
    ("item_class", "rare_name", "localized_base", "expected_base"),
    [
        ("スピア", "崇高なエッジ", "飛翔のスピア", "Soaring Spear"),
        ("鎧", "災いのカーテン", "スリップストライクベスト", "Slipstrike Vest"),
        ("指輪", "大渦の環", "アメジストの指輪", "Amethyst Ring"),
    ],
)
def test_rare_items_keep_generated_name_separate_from_exact_base_line(
    item_class, rare_name, localized_base, expected_base,
):
    item = parse_item_text(
        f"アイテムクラス: {item_class}\nレアリティ: レア\n"
        f"{rare_name}\n{localized_base}\n--------\nアイテムレベル: 80\n"
    )

    assert item.name == rare_name
    assert item.base_type == expected_base


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
    attack_speed = next(mod for mod in item.modifiers if "アタックスピード" in mod.text)
    assert attack_speed.stat_id == "explicit.stat_681332047"


def test_reported_japanese_rare_spear_keeps_quality_and_both_flat_damage_values():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_spear_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.base_type == "Soaring Spear"
    assert item.category == "spear"
    assert item.properties["品質"] == "+20% (augmented)"
    flat = next(mod for mod in item.modifiers if "物理ダメージを追加" in mod.text)
    assert flat.stat_id == "explicit.stat_1940865751"
    assert flat.values == (25.0, 39.0)
    fractured = next(mod for mod in item.modifiers if "アタックスピードが28" in mod.text)
    assert fractured.kind == "fractured"
    assert "fractured" in item.flags
    crafted_accuracy = next(mod for mod in item.modifiers if mod.text.startswith("命中力"))
    assert crafted_accuracy.stat_id == "crafted.stat_803737631"
    crafted_speed = next(mod for mod in item.modifiers if "アタックスピードが8" in mod.text)
    assert crafted_speed.stat_id == "crafted.stat_210067635"


def test_audited_crossbow_accuracy_keeps_local_scope_when_both_ids_have_results():
    fixture = _real_copy("FX001")
    for language in ("日本語設定の詳細コピー全文", "英語設定の詳細コピー全文"):
        item = parse_item_text(fixture[language])
        accuracy = next(
            mod for mod in item.modifiers if "命中" in mod.text or "Accuracy" in mod.text
        )
        assert accuracy.stat_id == "explicit.stat_691932474"


@pytest.mark.parametrize(
    ("base_type", "needle", "expected_id"),
    (
        ("Swathed Cap", "Accuracy", "explicit.stat_803737631"),
        ("Runeforged Swathed Cap", "Accuracy", "explicit.stat_803737631"),
        ("Runemastered Fine Bracers", "Evasion Rating", "explicit.stat_124859000"),
        ("Runemastered Spined Bracers", "Evasion Rating", "explicit.stat_124859000"),
    ),
)
def test_audited_ambiguous_base_stats_use_confirmed_scope(base_type, needle, expected_id):
    fixture = next(
        row for row in _ambiguous_base_fixtures()
        if row["expected_base_type"] == base_type
    )
    for language in ("ja", "en"):
        item = parse_item_text(fixture[language])
        matching = [
            mod for mod in item.modifiers
            if needle in (mod.ref or "") and mod.stat_id in {
                "explicit.stat_803737631", "explicit.stat_691932474",
                "explicit.stat_124859000", "explicit.stat_2106365538",
            }
        ]
        assert matching and all(mod.stat_id == expected_id for mod in matching)


def test_reported_japanese_rare_body_armour_prefers_local_evasion_stats():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_body_armour_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    increased = [mod for mod in item.modifiers if mod.text.startswith("回避力が")]
    assert [(mod.stat_id, mod.values) for mod in increased] == [
        ("explicit.stat_124859000", (105.0,)),
        ("explicit.stat_124859000", (40.0,)),
    ]
    assert all(not mod.stat_ids for mod in increased)
    deflection = next(mod for mod in item.modifiers if "受け流し力" in mod.text)
    assert deflection.stat_id == "explicit.stat_3033371881"
    assert deflection.values == (17.0,)
    assert {"augment", "desecrated", "crafted", "corrupted"} <= set(item.flags)


def test_phase45_sceptre_parses_spirit_augment_sockets_and_sanctified_state():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "phase45_sceptre_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.category == "sceptre"
    assert item.properties["スピリット"] == "100"
    assert item.properties["ソケット"] == "S S"
    assert {"augment", "sanctified"} <= set(item.flags)
    augment = next(mod for mod in item.modifiers if mod.kind == "augment")
    assert augment.stat_id and augment.stat_id.startswith("rune.")


def test_phase45_waystone_parses_all_dedicated_properties():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "phase45_waystone_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.category == "waystone"
    assert item.base_type == "Waystone (Tier 15)"
    assert item.properties["ウェイストーンティア"] == "15"
    assert item.properties["復活が利用可能"] == "3"
    assert item.properties["モンスターパックサイズ"] == "+42%"


def test_reported_magic_waystone_extracts_affixed_base_and_resolves_all_mods():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "magic_waystone_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.rarity == "magic"
    assert item.category == "waystone"
    assert item.base_type == "Waystone (Tier 15)"
    assert item.properties["復活が利用可能"] == "4 (augmented)"
    assert item.properties["パックサイズ"] == "+16% (augmented)"
    assert item.properties["ウェイストーンドロップ確率"] == "+30% (augmented)"
    assert [(mod.stat_id, mod.values) for mod in item.modifiers] == [
        ("explicit.stat_2753083623", (224.0,)),
        ("explicit.stat_57326096", (25.0,)),
        ("explicit.stat_3477720557", ()),
    ]
    assert all(mod.confidence == 1.0 for mod in item.modifiers)


def test_reported_rare_waystone_keeps_affix_name_separate_from_trade_base():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_waystone_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)

    assert item.rarity == "rare"
    assert item.category == "waystone"
    assert item.name == "先祖の突撃"
    assert item.base_type == "Waystone (Tier 15)"


def test_phase45_runemastered_base_and_desecrated_state_are_not_collapsed():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "phase45_runemastered_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.base_type == "Runemastered Vaal Cuirass"
    assert {"runemastered", "desecrated", "fractured"} <= set(item.flags)
    assert "runeforged" not in item.flags
    desecrated = next(mod for mod in item.modifiers if mod.kind == "desecrated")
    assert desecrated.stat_id == "desecrated.stat_2923486259"


@pytest.mark.parametrize(
    "fixture",
    json.loads(
        (Path(__file__).parent / "fixtures" / "poe2" / "phase45_augment_items_ja.json").read_text(
            encoding="utf-8"
        )
    )["fixtures"],
    ids=lambda row: row["id"],
)
def test_phase45_standalone_rune_and_soul_core_categories(fixture):
    item = parse_item_text(fixture["text"])
    assert item.category == fixture["category"]
    assert item.base_type == fixture["base_type"]
    assert TRADE_CATEGORY_BY_CATEGORY[item.category] == fixture["trade_category"]


def test_phase45_gem_identity_and_socket_property():
    text = (Path(__file__).parent / "fixtures" / "poe2" / "phase45_gem_ja.txt").read_text(
        encoding="utf-8"
    )
    item = parse_item_text(text)
    assert item.rarity == "gem"
    assert item.base_type == "Arc"
    assert item.category == "active_gem"
    assert item.properties["ソケット"] == "S S"


def test_real_meta_gem_without_item_class_accepts_windows_leading_marker():
    item = parse_item_text("""\ufeffレアリティ: ジェム
ブラスファミー
--------
バフ, 永続, 範囲効果, オーラ, メタ
レベル: 10
--------
装備条件：レベル 36, 65 知性
--------
ソケット: G G
--------
ソケットされたすべての呪いスキルをオーラに変化させる。
""")
    assert item.category == "meta_gem"
    assert item.base_type == "Blasphemy"
    assert item.properties["ソケット"] == "G G"
def test_real_uncut_skill_gem_is_exchange_identity_without_description_mods():
    import csv
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "poe2" / "real_copy_bilingual.csv"
    with fixture.open(encoding="utf-8-sig", newline="") as stream:
        row = next(row for row in csv.DictReader(stream) if row["収集対象"] == "Uncut Gem")
    for column in ("日本語設定の詳細コピー全文", "英語設定の詳細コピー全文"):
        item = parse_item_text(row[column])
        assert item.name == "Uncut Skill Gem (Level 18)"
        assert item.base_type == "Uncut Skill Gem (Level 18)"
        assert item.category == "uncut_gem"
        assert item.modifiers == ()


@pytest.mark.parametrize(
    ("item_class", "base_type", "category"),
    [
        ("Life Flasks", "Ultimate Life Flask", "life_flask"),
        ("Mana Flasks", "Ultimate Mana Flask", "mana_flask"),
        ("Wombgifts", "Ornate Wombgift", "wombgift"),
        ("Map Fragments", "Simulacrum", "map_fragment"),
        ("Pinnacle Keys", "Ancient Crisis Fragment", "pinnacle_key"),
        ("Vault Keys", "Zarokh's Reliquary Key: Against the Darkness", "vault_key"),
        ("Expedition Logbooks", "Expedition Logbook", "expedition_logbook"),
        ("Breachstones", "Breachstone", "breachstone"),
    ],
)
def test_special_trade_and_exchange_categories_resolve_from_identity(
    item_class, base_type, category,
):
    item = parse_item_text(
        f"Item Class: {item_class}\nRarity: Normal\n{base_type}\n--------\n"
    )
    assert (item.base_type, item.category) == (base_type, category)


def test_magic_poe2_flask_resolves_affixed_name_to_base():
    item = parse_item_text(
        "Item Class: Life Flasks\nRarity: Magic\nHealthy Ultimate Life Flask\n"
        "--------\nQuality: +20%\n"
    )
    assert (item.base_type, item.category) == ("Ultimate Life Flask", "life_flask")
