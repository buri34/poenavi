from unittest.mock import patch

from PySide6.QtGui import QColor, QImage

from src.poetore.poe2.desecration_ocr import (
    _green_mask,
    _green_text_rect,
    choice_bands,
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
        assert frame.valid_panel
        assert len(choice_bands(image)) == 3
        assert all(len(variants) == 3 for variants in frame.variants)


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
        ("物理ダメージが28%増加する\n病中力 +57",),
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


def test_category_panel_requires_all_three_mods_not_the_best_partial_match():
    result = resolve_ocr_variants((
        ("アーマー +27", "アーマー +27", "アーマー +27"),
        ("移動スピードが30%増加する",) * 3,
        ("未知の効果が123%増加する",) * 3,
    ), ("boots", "amulet"))

    assert result.categories == ()
    assert result.fallback_tiers == (7, 2, None)
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
