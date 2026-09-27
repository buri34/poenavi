"""Bundled catalog for the custom Currency Exchange rate selector."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.utils.poe_version_data import POE1, POE2

CATALOG_FILENAME = "exchange_item_catalog.json"
DIVINATION_CARD_ICON = "16px-Divination_card_inventory_icon.png"
PLACEHOLDER_ICON = "CurrencyExchangePlaceholder.svg"


@dataclass(frozen=True)
class ExchangeCatalogItem:
    item_id: str
    english_name: str
    japanese_name: str
    category: str
    category_order: int
    item_order: int
    icon_kind: str
    icon_url: str | None = None


def _runtime_roots() -> tuple[Path, ...]:
    source_root = Path(__file__).resolve().parents[2]
    executable_root = Path(sys.executable).resolve().parent
    return tuple(dict.fromkeys((
        executable_root,
        Path(getattr(sys, "_MEIPASS", source_root)),
        source_root,
    )))


def catalog_path() -> Path:
    relative = Path("data") / "poetore" / "currency_exchange" / CATALOG_FILENAME
    for root in _runtime_roots():
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return _runtime_roots()[-1] / relative


def divination_card_icon_path() -> Path:
    relative = Path("assets") / "icons" / DIVINATION_CARD_ICON
    for root in _runtime_roots():
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return _runtime_roots()[-1] / relative


def placeholder_icon_path() -> Path:
    relative = Path("assets") / "icons" / PLACEHOLDER_ICON
    for root in _runtime_roots():
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return _runtime_roots()[-1] / relative


@lru_cache(maxsize=1)
def _load_payload() -> dict:
    with catalog_path().open(encoding="utf-8") as source:
        payload = json.load(source)
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported Currency Exchange catalog schema")
    return payload


def category_labels(poe_version: str) -> tuple[str, ...]:
    if poe_version not in {POE1, POE2}:
        return ()
    realm = _load_payload()["realms"][poe_version]
    return tuple(category["label"] for category in realm["categories"])


def exchange_catalog_items(poe_version: str) -> tuple[ExchangeCatalogItem, ...]:
    if poe_version not in {POE1, POE2}:
        return ()
    realm = _load_payload()["realms"][poe_version]
    return tuple(ExchangeCatalogItem(
        item_id=row["id"],
        english_name=row["en"],
        japanese_name=row["ja"],
        category=row["category"],
        category_order=int(row["category_order"]),
        item_order=int(row["item_order"]),
        icon_kind=row["icon"]["kind"],
        icon_url=row["icon"].get("url"),
    ) for row in realm["items"])


def exchange_catalog_by_id(poe_version: str) -> dict[str, ExchangeCatalogItem]:
    return {item.item_id: item for item in exchange_catalog_items(poe_version)}
