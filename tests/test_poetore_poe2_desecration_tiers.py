import hashlib
import json
import re
from pathlib import Path

import pytest

from src.poetore.poe2.desecration_tiers import (
    TEMPLATE_NUMBER_RE,
    _match_part,
    _numeric_skeleton,
    _soft_wrap_layouts,
    _stat_identity,
    available_categories,
    resolve_desecration_choice,
    resolve_desecration_choice_fuzzy,
    resolve_desecration_choices_fuzzy,
    resolve_desecration_reveal,
    tier_data,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "poetore" / "poe2" / "desecration"
FIXTURE = json.loads((FIXTURE_DIR / "reveal_cases.json").read_text(encoding="utf-8"))
CHOICES = [
    (choice["text"], case["category"], choice["tier"], choice["mod_id"])
    for case in FIXTURE["cases"]
    for choice in case["choices"]
]


@pytest.mark.parametrize(
    ("text", "category", "tier", "mod_id"),
    CHOICES,
)
def test_user_supplied_reveal_choices_resolve_to_tier(text, category, tier, mod_id):
    result = resolve_desecration_choice(text, category)
    assert result.reason == "matched"
    assert result.tier == tier
    assert result.mod_ids == (mod_id,)


def test_user_supplied_images_are_preserved_exactly():
    for case in FIXTURE["cases"]:
        image = FIXTURE_DIR / case["image"]
        assert hashlib.sha256(image.read_bytes()).hexdigest() == case["image_sha256"]


def test_category_is_required_to_prevent_cross_equipment_guessing():
    result = resolve_desecration_choice("アーマー +27", "spear")
    assert result.tier is None
    assert result.reason == "no_match"


def test_staff_and_quarterstaff_use_separate_profile_families():
    assert {"staff", "quarterstaff"} <= set(available_categories())

    caster_staff = resolve_desecration_choice(
        "ダメージの45%を追加混沌ダメージとして獲得する", "staff",
    )
    quarterstaff = resolve_desecration_choice(
        "この武器によるアタックは20%の火耐性を貫通する", "quarterstaff",
    )
    assert caster_staff.tier == 1
    assert resolve_desecration_choice(
        "ダメージの45%を追加混沌ダメージとして獲得する", "quarterstaff",
    ).tier is None
    assert quarterstaff.tier == 1
    assert resolve_desecration_choice(
        "この武器によるアタックは20%の火耐性を貫通する", "staff",
    ).tier is None


def test_database_keeps_unparsed_template_rows_explicitly_diagnostic():
    payload = tier_data()
    assert len(payload["entries"]) == 1713
    assert payload["diagnostics"]["fully_matchable_rows"] == 1698
    assert len(payload["diagnostics"]["rows_with_unparsed_parts"]) == 15


def test_fuzzy_match_tolerates_one_character_but_keeps_numbers_strict():
    result = resolve_desecration_choice_fuzzy(
        "物理ダメージが28%増加する\n病中力 +57", "spear"
    )
    assert result.tier == 6
    assert result.score == 0.875
    assert resolve_desecration_choice_fuzzy("最大マナ +999", "boots").tier is None


def test_soft_wrap_layouts_are_bounded_by_the_largest_mod_structure():
    layouts = _soft_wrap_layouts(tuple(f"line-{index}" for index in range(20)))

    assert layouts[0] == tuple(f"line-{index}" for index in range(20))
    assert max(len(layout) for layout in layouts[1:]) == 3
    assert len(layouts) == 192


def test_all_category_resolution_matches_individual_category_results():
    text = "物理ダメージが28%増加する\n病中力 +57"
    categories = ("spear", "staff", "ring", "boots")
    together = resolve_desecration_choices_fuzzy(text, categories)
    assert together == {
        category: resolve_desecration_choice_fuzzy(text, category)
        for category in categories
    }


def test_fuzzy_match_distinguishes_fixed_numbers_from_tier_values():
    result = resolve_desecration_choice_fuzzy(
        "倒した敵1体ごとに3のマナを獲得する", "spear",
    )
    assert result.tier == 8
    assert result.mod_ids == ("ManaGainedFromEnemyDeath1",)
    assert result.reason == "matched"


def test_fixed_number_rescue_is_used_only_for_a_unique_valid_mod():
    result = resolve_desecration_choice_fuzzy(
        "投射物は8mより遠くにいる敵に対するヒットダメージが60%増加する",
        "spear",
    )
    assert result.tier == 1
    assert result.mod_ids == ("AbyssModBowSpearUlamanPrefixProjectileDamageFar",)
    assert result.reason == "fixed_number_rescue"


def test_short_mod_rescue_keeps_number_and_candidate_identity_strict():
    rescued = resolve_desecration_choice_fuzzy("回避カ +76", "ring")
    assert rescued.tier == 6
    assert rescued.mod_ids == ("IncreasedEvasionRating4",)
    assert rescued.reason == "short_text_rescue"
    assert resolve_desecration_choice_fuzzy("回避カ +999", "ring").tier is None


def test_short_mod_rescue_accepts_windows_ocr_inter_character_spaces():
    rescued = resolve_desecration_choice_fuzzy("回 避 カ + 13", "ring")

    assert rescued.tier == 9
    assert rescued.mod_ids == ("IncreasedEvasionRating1",)
    assert rescued.reason == "short_text_rescue"
    assert rescued.range_labels == ("8–17",)


def test_short_mod_rescue_rejects_text_ambiguous_between_different_stats():
    assert resolve_desecration_choice_fuzzy("命力 +33", "ring").tier is None
    assert resolve_desecration_choice_fuzzy("回力 +33", "ring").tier is None


def test_short_mod_rescue_allows_one_changed_short_line_in_compound_mod():
    rescued = resolve_desecration_choice_fuzzy(
        "物理ダメージが28%増加する\n命中カ +57", "spear",
    )

    assert rescued.tier == 6
    assert rescued.reason == "short_text_rescue"


def test_same_display_stat_can_share_prefix_and_suffix_records():
    result = resolve_desecration_choice_fuzzy(
        "見つかるアイテムのレアリティが8%増加する", "ring",
    )
    assert result.tier == 3
    assert result.mod_ids == (
        "ItemFoundRarityIncrease1", "ItemFoundRarityIncreasePrefix1",
    )
    assert tuple(
        (option.affix, option.tier, option.range_labels)
        for option in result.affix_options
    ) == (
        ("prefix", 3, ("8–11%",)),
        ("suffix", 3, ("6–10%",)),
    )


def test_affix_options_keep_different_tiers_linked_to_their_affix():
    rarity = resolve_desecration_choice_fuzzy(
        "見つかるアイテムのレアリティが11%増加する", "ring",
    )
    grenade = resolve_desecration_choice_fuzzy(
        "グレネードスキルのクールダウン使用回数 +1", "crossbow",
    )

    assert rarity.tier_candidates == (2, 3)
    assert tuple((row.affix, row.tier, row.range_labels) for row in rarity.affix_options) == (
        ("prefix", 3, ("8–11%",)),
        ("suffix", 2, ("11–14%",)),
    )
    assert tuple((row.affix, row.tier, row.range_labels) for row in grenade.affix_options) == (
        ("prefix", 1, ("1",)),
        ("suffix", 2, ("1",)),
    )


def test_all_identical_prefix_suffix_displays_are_limited_to_audited_cases():
    payload = tier_data()
    categories = {profile["id"]: profile["category"] for profile in payload["profiles"]}
    rows = {}
    for entry in payload["entries"]:
        affix = entry.get("type", "").casefold()
        if affix not in {"prefix", "suffix"}:
            continue
        signature = tuple(sorted(
            re.sub(
                r"\s*\((?:Local|ローカル)\)\s*$", "", part["text"]["ja"],
                flags=re.IGNORECASE,
            )
            for part in entry["parts"]
        ))
        for profile_id in entry["profile_tiers"]:
            rows.setdefault((profile_id, signature), set()).add(affix)
    affected = {
        (categories[profile_id], signature)
        for (profile_id, signature), affixes in rows.items()
        if affixes == {"prefix", "suffix"}
    }

    assert affected == {
        (category, ("見つかるアイテムのレアリティが#%増加する",))
        for category in ("amulet", "helmet", "ring")
    } | {
        ("crossbow", ("グレネードスキルのクールダウン使用回数 +#",)),
    }


def test_all_mixed_fixed_and_dynamic_templates_keep_numeric_roles():
    checked = 0
    diagnostic = 0
    for entry in tier_data()["entries"]:
        for part in entry["parts"]:
            template = part["text"]["ja"]
            if "#" not in template or not any(char.isdigit() for char in template):
                continue
            if part["ranges"] is None:
                diagnostic += 1
                continue
            checked += 1
            ranges = iter(part["ranges"])

            def render(token, *, change_fixed=False, ranges=ranges):
                raw = token.group()
                if raw == "#":
                    low, _high = next(ranges)
                    return str(int(low) if float(low).is_integer() else low)
                if change_fixed:
                    return str(int(float(raw)) + 1)
                return raw

            observed = TEMPLATE_NUMBER_RE.sub(render, template)
            assert _match_part(part, observed), (entry["mod_id"], observed)

            ranges = iter(part["ranges"])
            changed = False
            pieces = []
            cursor = 0
            for token in TEMPLATE_NUMBER_RE.finditer(template):
                pieces.append(template[cursor:token.start()])
                raw = token.group()
                if raw == "#":
                    low, _high = next(ranges)
                    pieces.append(str(int(low) if float(low).is_integer() else low))
                else:
                    pieces.append(str(int(float(raw)) + 1) if not changed else raw)
                    changed = True
                cursor = token.end()
            pieces.append(template[cursor:])
            wrong_fixed = "".join(pieces)
            assert not _match_part(part, wrong_fixed)
            assert _numeric_skeleton(
                template, wrong_fixed, part["ranges"], allow_fixed_mismatch=True,
            ) is not None
    assert checked == 59
    assert diagnostic == 2


def test_reveal_infers_category_from_all_three_choices():
    result = resolve_desecration_reveal((
        "アーマー +27", "最大マナ +108", "移動スピードが30%増加する",
    ))
    assert "boots" in result.categories
    assert result.tiers_by_category["boots"] == (7, 1, 2)


def test_reduced_requirement_generated_from_pob2_resolves_normally():
    result = resolve_desecration_choice("要求能力値が25%減少する", "body_armour")
    assert result.tier == 3
    assert result.mod_ids == ("ReducedLocalAttributeRequirements3",)


def test_roll_ranges_follow_the_visible_value_order():
    cold = resolve_desecration_choice_fuzzy(
        "26から43の冷気ダメージを追加する", "spear"
    )
    assert cold.range_labels == ("22–29", "34–44")

    compound = resolve_desecration_choice_fuzzy(
        "物理ダメージが28%増加する\n命中力 +57", "spear"
    )
    assert compound.range_labels == ("25–34%", "47–72")


def test_overlapping_tiers_keep_one_stat_identity_and_all_tier_candidates():
    result = resolve_desecration_choice_fuzzy(
        "2から5の物理ダメージをアタックに追加する", "ring",
    )

    assert result.tier is None
    assert result.tier_candidates == (7, 8)
    assert result.reason == "multiple_tiers"
    assert len({_stat_identity(entry) for entry in tier_data()["entries"]
                if entry["mod_id"] in result.mod_ids}) == 1


def test_all_tier_range_overlaps_are_limited_to_the_audited_stat_series():
    """New overlaps must be reviewed instead of silently changing resolution."""
    overlapping_stats = set()
    rows_by_profile_stat = {}
    for entry in tier_data()["entries"]:
        if any(part.get("ranges") is None for part in entry["parts"]):
            continue
        ranges = tuple(
            tuple(map(float, value_range))
            for part in entry["parts"] for value_range in part["ranges"]
        )
        for profile_id, tier in entry["profile_tiers"].items():
            rows_by_profile_stat.setdefault((profile_id, _stat_identity(entry)), []).append(
                (int(tier), ranges)
            )
    for (_profile_id, stat_identity), rows in rows_by_profile_stat.items():
        for index, first in enumerate(rows):
            for second in rows[index + 1:]:
                same_shape = len(first[1]) == len(second[1])
                overlaps = same_shape and all(
                    max(first_low, second_low) <= min(first_high, second_high)
                    for (first_low, first_high), (second_low, second_high)
                    in zip(first[1], second[1])
                )
                if first[0] != second[0] and overlaps:
                    overlapping_stats.add(stat_identity)

    assert overlapping_stats == {
        ("desecrated.stat_1574590649",),
        ("desecrated.stat_1940865751",),
        ("desecrated.stat_2250681686",),
        ("desecrated.stat_3032590688",),
        ("desecrated.stat_3917489142",),
        ("desecrated.stat_789117908",),
    }
