from __future__ import annotations

from dataclasses import dataclass

from ..models import ParsedItem
from ..poe_ninja import PoeNinjaPrice
from ..trade import PriceListing
from .metadata import augment_entries
from .parser import identify_installed_augments
from .trade import _augment_socket_count, _virtual_augment_effective_count


@dataclass(frozen=True)
class VirtualAugmentCost:
    ref_name: str
    count: int
    total_exalted: float


@dataclass(frozen=True)
class InstalledAugmentRecovery:
    refs: tuple[str, ...]
    materials_exalted: float
    extraction_exalted: float
    recovery_exalted: float
    cheapest_listing_exalted: float

    @property
    def difference_exalted(self) -> float:
        return self.recovery_exalted - self.cheapest_listing_exalted

    @property
    def extraction_may_be_worthwhile(self) -> bool:
        return self.difference_exalted > 0


def _entry(ref_name: str) -> dict | None:
    return next(
        (row for row in augment_entries() if row.get("ref_name") == ref_name),
        None,
    )


def effective_virtual_augment_count(ref_name: str, requested_count: int) -> int:
    entry = _entry(ref_name)
    if entry is None:
        return 0
    return _virtual_augment_effective_count(entry, max(0, int(requested_count)))


def installed_augment_refs(item: ParsedItem) -> tuple[str, ...]:
    socket_count = _augment_socket_count(item) or item.augment_count
    refs = identify_installed_augments(
        list(item.modifiers), item.category, int(socket_count or 0),
    )
    return refs if len(refs) == item.augment_count else ()


def poe_ninja_price_in_exalted(
    price: PoeNinjaPrice | None, exalted_chaos: float | None,
) -> float | None:
    if price is None or not exalted_chaos or exalted_chaos <= 0 or price.chaos <= 0:
        return None
    return price.chaos / exalted_chaos


def listing_price_in_exalted(
    listing: PriceListing, *, exalted_chaos: float | None,
    divine_exalted: float | None,
) -> float | None:
    if listing.pricing_method == "unpriced" or listing.amount <= 0:
        return None
    currency = str(listing.currency or "").casefold()
    if currency == "exalted":
        return listing.amount
    if currency == "chaos" and exalted_chaos and exalted_chaos > 0:
        return listing.amount / exalted_chaos
    if currency == "divine" and divine_exalted and divine_exalted > 0:
        return listing.amount * divine_exalted
    return None


def virtual_augment_cost(
    ref_name: str, requested_count: int, price: PoeNinjaPrice | None,
    exalted_chaos: float | None,
) -> VirtualAugmentCost | None:
    count = effective_virtual_augment_count(ref_name, requested_count)
    unit = poe_ninja_price_in_exalted(price, exalted_chaos)
    if count <= 0 or unit is None:
        return None
    return VirtualAugmentCost(ref_name, count, unit * count)


def installed_augment_recovery(
    item: ParsedItem,
    material_prices: dict[str, PoeNinjaPrice | None],
    extraction_price: PoeNinjaPrice | None,
    listings: tuple[PriceListing, ...],
    *,
    exalted_chaos: float | None,
    divine_exalted: float | None,
) -> InstalledAugmentRecovery | None:
    refs = installed_augment_refs(item)
    if not refs:
        return None
    units = [
        poe_ninja_price_in_exalted(material_prices.get(ref_name), exalted_chaos)
        for ref_name in refs
    ]
    extraction = poe_ninja_price_in_exalted(extraction_price, exalted_chaos)
    listing_values = [
        value for row in listings
        if (value := listing_price_in_exalted(
            row, exalted_chaos=exalted_chaos, divine_exalted=divine_exalted,
        )) is not None
    ]
    if extraction is None or not units or any(value is None for value in units) or not listing_values:
        return None
    materials = sum(float(value) for value in units if value is not None)
    return InstalledAugmentRecovery(
        refs, materials, extraction, materials - extraction, min(listing_values),
    )


def compact_exalted(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{value:.2f}".rstrip("0").rstrip(".")
