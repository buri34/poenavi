from PySide6.QtGui import QImage

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
