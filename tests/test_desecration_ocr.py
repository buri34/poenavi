from unittest.mock import patch

from PySide6.QtGui import QColor, QImage

from src.poetore.poe2.desecration_ocr import (
    _green_mask,
    _green_text_rect,
    choice_bands,
    desecration_panel_diagnostics,
    looks_like_desecration_panel,
    prepare_desecration_frame,
    resolve_ocr_variants,
)
from src.poetore.poe2.desecration_tiers import resolve_desecration_choices_fuzzy


def _legacy_green_text_rect(image, padding=8):
    left, top, right, bottom = image.width(), image.height(), -1, -1
    count = 0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if (
                color.green() >= 75
                and color.green() - color.blue() >= 10
                and color.green() - color.red() >= 5
            ):
                left, top = min(left, x), min(top, y)
                right, bottom = max(right, x), max(bottom, y)
                count += 1
    if right < left or bottom < top:
        return None, 0
    from PySide6.QtCore import QRect
    return QRect(
        max(0, left - padding), max(0, top - padding),
        min(image.width() - 1, right + padding) - max(0, left - padding) + 1,
        min(image.height() - 1, bottom + padding) - max(0, top - padding) + 1,
    ), count


def _legacy_green_mask(image):
    result = QImage(image.size(), QImage.Format_RGB32)
    result.fill(QColor("white"))
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if (
                color.green() >= 75
                and color.green() - color.blue() >= 10
                and color.green() - color.red() >= 5
            ):
                result.setPixelColor(x, y, QColor("black"))
    return result


def test_supplied_panels_have_three_valid_choice_bands():
    for name in ("boots-reveal.png", "spear-reveal.png"):
        image = QImage(f"tests/fixtures/poetore/poe2/desecration/{name}")
        frame = prepare_desecration_frame(image)
        diagnostics = desecration_panel_diagnostics(image)
        assert frame.valid_panel
        assert len(choice_bands(image)) == 3
        assert all(len(variants) == 3 for variants in frame.variants)
        assert diagnostics["matched"]
        assert diagnostics["band_count"] == 3
        assert len(diagnostics["green_pixel_counts"]) == 3
        assert len(diagnostics["green_text_widths"]) == 3
        assert looks_like_desecration_panel(image)


def test_expedition_region_is_not_mistaken_for_desecration():
    image = QImage("assets/images/expedition_region_example.png").copy(
        47, 162, 605, 652
    )
    assert not looks_like_desecration_panel(image)


def test_bulk_pixel_processing_matches_the_original_pixel_api_results():
    for name in ("boots-reveal.png", "spear-reveal.png"):
        image = QImage(f"tests/fixtures/poetore/poe2/desecration/{name}")
        for band in choice_bands(image):
            card = image.copy(0, band.top, image.width(), band.bottom - band.top)
            actual_rect, actual_count = _green_text_rect(card)
            expected_rect, expected_count = _legacy_green_text_rect(card)
            assert (actual_rect, actual_count) == (expected_rect, expected_count)
            crop = card.copy(actual_rect)
            actual = _green_mask(crop).convertToFormat(QImage.Format_RGBA8888)
            expected = _legacy_green_mask(crop).convertToFormat(QImage.Format_RGBA8888)
            assert bytes(actual.bits()) == bytes(expected.bits())


def test_tiny_or_uniform_crops_are_not_mistaken_for_a_three_choice_panel():
    tiny = QImage(16, 180, QImage.Format_RGB32)
    tiny.fill(QColor("#2f7f4f"))
    uniform = QImage(620, 291, QImage.Format_RGB32)
    uniform.fill(QColor("#2f7f4f"))

    assert not prepare_desecration_frame(tiny).valid_panel
    assert not prepare_desecration_frame(uniform).valid_panel


def test_ocr_variants_resolve_safe_typo_and_reject_bad_number():
    result = resolve_ocr_variants((
        ("この武器によるアタックは20%の火耐性を貫通する",),
        ("26から43の冷気ダメージを追加する",),
        (
            "物理ダメージが28%増加する\n病中力 +57",
            "物理ダメージが28%増加する\n病中力 +57",
        ),
    ), ("spear",))
    assert result.tiers == (1, 5, 6)
    assert result.ranges == (
        ("15–25%",),
        ("22–29", "34–44"),
        ("25–34%", "47–72"),
    )
    assert result.statuses == ("matched", "matched", "matched")

    bad = resolve_ocr_variants((("最大マナ +999",),), ("boots",))
    assert bad.categories == ()
    assert bad.fallback_statuses == ("read_failed",)


def test_ocr_resolution_separates_stable_unsupported_text_from_read_failure():
    unsupported = "未知の効果が123%増加する"
    result = resolve_ocr_variants(((unsupported, unsupported, unsupported),), ("boots",))
    assert result.categories == ()
    assert result.fallback_statuses == ("unsupported",)

    failed = resolve_ocr_variants((("読取不能", "", "別の誤読"),), ("boots",))
    assert failed.fallback_statuses == ("read_failed",)


def test_ocr_variants_reject_conflicting_tiers_even_when_one_text_scores_better():
    """Different valid numbers from the same crop must never be score-tiebroken."""
    result = resolve_ocr_variants((
        ("最大マナ +108", "最大マナが +100"),
    ), ("boots",))

    assert result.categories == ()
    assert result.fallback_statuses == ("read_failed",)


def test_ocr_variants_accept_two_of_three_matching_mod_number_and_tier():
    result = resolve_ocr_variants(((
        "物理ダメージが64%増加する",
        "物理ダメージが64%増加する",
        "物理ダメージが84%増加する",
    ),), ("spear",))

    assert result.categories == ("spear",)
    assert result.tiers == (7,)
    assert result.texts_by_category["spear"] == (
        "物理ダメージが64%増加する",
    )


def test_ocr_variants_do_not_vote_across_different_numbers_in_the_same_tier():
    result = resolve_ocr_variants(((
        "物理ダメージが60%増加する",
        "物理ダメージが61%増加する",
        "物理ダメージが62%増加する",
    ),), ("spear",))

    assert result.categories == ()
    assert result.fallback_statuses == ("read_failed",)


def test_ocr_variants_reject_different_mods_that_happen_to_share_a_tier():
    """Agreement on T1 alone is insufficient when OCR variants name different mods."""
    result = resolve_ocr_variants((
        ("最大マナ +108", "火耐性 +43%"),
    ), ("boots",))

    assert result.categories == ()
    assert result.fallback_statuses == ("read_failed",)


def test_ocr_resolution_rejects_an_extra_number_from_a_neighbouring_ui_element():
    result = resolve_ocr_variants((
        ("最大マナ +108 レベル81",),
    ), ("boots",))

    assert result.categories == ()
    assert result.fallback_statuses == ("read_failed",)


def test_short_text_rescue_requires_multiple_ocr_variants_to_agree():
    rescued = resolve_ocr_variants((("回避カ +76", "回避カ +76", ""),), ("ring",))
    assert rescued.categories == ("ring",)
    assert rescued.tiers == (6,)

    single = resolve_ocr_variants((("回避カ +76", "", ""),), ("ring",))
    assert single.categories == ()
    assert single.fallback_statuses == ("read_failed",)


def test_windows_ocr_evasion_output_is_rescued_by_two_of_three_agreement():
    result = resolve_ocr_variants((
        ("回 避 カ + 13", "回 避 カ + 13", "回 避 カ + 13"),
    ), ("ring",))

    assert result.categories == ("ring",)
    assert result.tiers == (9,)
    assert result.ranges == (("8–17",),)


def test_compound_short_text_rescue_accepts_exact_and_rescued_variant_agreement():
    rescued_text = "物理ダメージが28%増加する\n命中カ +57"
    exact_text = "物理ダメージが28%増加する\n命中力 +57"

    single = resolve_ocr_variants(((rescued_text, "", ""),), ("spear",))
    mixed = resolve_ocr_variants(((rescued_text, exact_text, ""),), ("spear",))
    agreed = resolve_ocr_variants(((rescued_text, rescued_text, ""),), ("spear",))

    assert single.categories == ()
    assert single.fallback_statuses == ("read_failed",)
    assert mixed.categories == ("spear",)
    assert mixed.tiers == (6,)
    assert agreed.categories == ("spear",)
    assert agreed.tiers == (6,)


def test_fixed_number_rescue_requires_multiple_ocr_variants_to_agree():
    text = "投射物は8mより遠くにいる敵に対するヒットダメージが60%増加する"
    rescued = resolve_ocr_variants(((text, text, ""),), ("spear",))
    assert rescued.categories == ("spear",)
    assert rescued.tiers == (1,)

    single = resolve_ocr_variants(((text, "", ""),), ("spear",))
    assert single.categories == ()


def test_supplied_short_mod_panel_texts_use_the_three_mod_intersection():
    result = resolve_ocr_variants((
        ("見つかるアイテムのレアリティが8%増加する",) * 3,
        ("4から6の冷気ダメージをアタックに追加する",) * 3,
        ("回避カ +76", "回避カ +76", ""),
    ), ("ring", "amulet", "boots", "gloves", "quiver"))
    assert result.categories == ("ring", "gloves")
    assert result.tiers_by_category == {
        "ring": (3, 8, 6),
        "gloves": (3, 8, 4),
    }


def test_affix_options_survive_ocr_resolution_for_result_rendering():
    result = resolve_ocr_variants((
        ("見つかるアイテムのレアリティが9%増加する",) * 3,
        ("最大ライフ +22",) * 3,
    ), ("ring",))

    options = result.affix_options_by_category["ring"][0]
    assert tuple((row.affix, row.tier, row.range_labels) for row in options) == (
        ("prefix", 3, ("8–11%",)),
        ("suffix", 3, ("6–10%",)),
    )
    assert result.affix_options == (options, ())


def test_category_panel_uses_two_recognized_mods_when_one_is_unsupported():
    result = resolve_ocr_variants((
        ("アーマー +27", "アーマー +27", "アーマー +27"),
        ("移動スピードが30%増加する",) * 3,
        ("未知の効果が123%増加する",) * 3,
    ), ("boots", "amulet"))

    assert result.categories == ("boots",)
    assert result.tiers == (7, 2, None)
    assert result.statuses == ("matched", "matched", "unsupported")
    assert result.fallback_tiers == (7, 2, None)
    assert result.fallback_statuses == ("matched", "matched", "unsupported")


def test_one_recognized_mod_does_not_open_an_overbroad_category_panel():
    result = resolve_ocr_variants((
        ("最大マナ +25",) * 3,
        ("未知の効果が123%増加する",) * 3,
        ("さらに未知の効果が456%増加する",) * 3,
    ), ("ring", "amulet", "boots", "gloves"))

    assert result.categories == ()
    assert result.fallback_tiers[0] is None


def test_ring_overlap_keeps_category_and_only_marks_that_mod_multi_tier():
    result = resolve_ocr_variants((
        ("最大マナ +25",) * 3,
        ("2から5の物理ダメージをアタックに追加する",) * 3,
        ("1から6の雷ダメージをアタックに追加する",) * 3,
    ), ("ring", "gloves", "amulet", "boots"))

    assert result.categories == ("ring", "gloves")
    assert result.tiers_by_category["ring"] == (10, (7, 8), 9)
    assert result.statuses_by_category["ring"] == (
        "matched", "multiple_tiers", "matched",
    )


def test_conflicting_recognized_mods_preserve_safe_individual_results():
    result = resolve_ocr_variants((
        ("移動スピードが30%増加する",) * 3,
        ("この武器によるアタックは20%の火耐性を貫通する",) * 3,
        ("未知の効果が123%増加する",) * 3,
    ), ("boots", "spear"))

    assert result.categories == ()
    assert result.category_conflict
    assert result.fallback_tiers == (2, 1, None)
    assert result.fallback_statuses == ("matched", "matched", "unsupported")


def test_duplicate_ocr_texts_are_resolved_once_for_all_categories():
    variants = (
        ("最大マナ +108",) * 3,
        ("移動スピードが30%増加する",) * 3,
        ("アーマー +27",) * 3,
    )
    with patch(
        "src.poetore.poe2.desecration_ocr.resolve_desecration_choices_fuzzy",
        wraps=resolve_desecration_choices_fuzzy,
    ) as resolver:
        result = resolve_ocr_variants(variants, ("boots", "body_armour"))

    assert result.categories == ("boots",)
    assert resolver.call_count == 3
