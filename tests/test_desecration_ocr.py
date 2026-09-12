from PySide6.QtGui import QColor, QImage

from src.poetore.poe2.desecration_ocr import (
    choice_bands,
    prepare_desecration_frame,
    resolve_ocr_variants,
)


def test_supplied_panels_have_three_valid_choice_bands():
    for name in ("boots-reveal.png", "spear-reveal.png"):
        image = QImage(f"tests/fixtures/poetore/poe2/desecration/{name}")
        frame = prepare_desecration_frame(image)
        assert frame.valid_panel
        assert len(choice_bands(image)) == 3
        assert all(len(variants) == 3 for variants in frame.variants)


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
