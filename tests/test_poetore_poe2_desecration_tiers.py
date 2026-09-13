import hashlib
import json
from pathlib import Path

import pytest

from src.poetore.poe2.desecration_tiers import (
    TEMPLATE_NUMBER_RE,
    _match_part,
    _numeric_skeleton,
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


def test_same_display_stat_can_share_prefix_and_suffix_records():
    result = resolve_desecration_choice_fuzzy(
        "見つかるアイテムのレアリティが8%増加する", "ring",
    )
    assert result.tier == 3
    assert result.mod_ids == (
        "ItemFoundRarityIncrease1", "ItemFoundRarityIncreasePrefix1",
    )


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
