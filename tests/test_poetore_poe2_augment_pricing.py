from __future__ import annotations

from src.poetore.models import ItemModifier, ParsedItem
from src.poetore.poe2.augment_pricing import (
    installed_augment_recovery,
    installed_augment_refs,
    listing_price_in_exalted,
    virtual_augment_cost,
)
from src.poetore.poe_ninja import PoeNinjaPrice
from src.poetore.trade import PriceListing


def _price(name: str, chaos: float) -> PoeNinjaPrice:
    return PoeNinjaPrice(name, None, chaos, (), "", 200)


def _adept_item(*, value: float = 9, count: int = 1) -> ParsedItem:
    return ParsedItem(
        "Body Armours", "normal", "", "Expert Mail", "body_armour",
        properties={"ソケット": " ".join("S" for _ in range(count))},
        modifiers=(ItemModifier(
            "器用さ", (value,), "augment", stat_id="rune.stat_3261801346",
        ),),
        augment_count=count,
    )


def test_virtual_augment_cost_bills_added_units_and_caps_legacy():
    price = _price("Adept Rune", 6)
    assert virtual_augment_cost("Adept Rune", 2, price, 3).total_exalted == 4

    legacy = _price("Legacy of Alkem Eira", 30)
    estimate = virtual_augment_cost("Legacy of Alkem Eira", 2, legacy, 3)
    assert estimate.count == 1
    assert estimate.total_exalted == 10


def test_virtual_augment_cost_is_unavailable_when_price_is_missing():
    assert virtual_augment_cost("Adept Rune", 1, None, 3) is None


def test_installed_augment_recovery_uses_copy_source_and_cheapest_convertible_listing():
    item = _adept_item()
    assert installed_augment_refs(item) == ("Adept Rune",)
    estimate = installed_augment_recovery(
        item,
        {"Adept Rune": _price("Adept Rune", 30)},
        _price("Orb of Extraction", 6),
        (
            PriceListing(1, "divine"),
            PriceListing(7, "exalted"),
            PriceListing(1, "mirror"),
        ),
        exalted_chaos=3,
        divine_exalted=20,
    )
    assert estimate is not None
    assert estimate.materials_exalted == 10
    assert estimate.extraction_exalted == 2
    assert estimate.recovery_exalted == 8
    assert estimate.cheapest_listing_exalted == 7
    assert estimate.extraction_may_be_worthwhile


def test_installed_augment_recovery_hides_when_any_required_price_is_missing():
    item = _adept_item()
    assert installed_augment_recovery(
        item, {"Adept Rune": None}, _price("Orb of Extraction", 6),
        (PriceListing(7, "exalted"),),
        exalted_chaos=3, divine_exalted=20,
    ) is None
    assert installed_augment_recovery(
        item, {"Adept Rune": _price("Adept Rune", 30)}, None,
        (PriceListing(7, "exalted"),),
        exalted_chaos=3, divine_exalted=20,
    ) is None
    assert installed_augment_recovery(
        item, {"Adept Rune": _price("Adept Rune", 30)},
        _price("Orb of Extraction", 6), (PriceListing(1, "mirror"),),
        exalted_chaos=3, divine_exalted=20,
    ) is None


def test_listing_conversion_rejects_unpriced_and_unsupported_currency():
    assert listing_price_in_exalted(
        PriceListing(1, "exalted", pricing_method="unpriced"),
        exalted_chaos=3, divine_exalted=20,
    ) is None
    assert listing_price_in_exalted(
        PriceListing(1, "mirror"), exalted_chaos=3, divine_exalted=20,
    ) is None
