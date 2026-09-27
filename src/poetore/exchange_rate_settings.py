"""Domain model and persistent store for custom Currency Exchange rate pairs."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any

from src.poetore.exchange_catalog import exchange_catalog_by_id
from src.utils.poe_version_data import POE1, POE2

MAX_RATE_PAIRS = 5
DIVINE_ORB_ID = "Metadata/Items/Currency/CurrencyModValues"
CHAOS_ORB_ID = "Metadata/Items/Currency/CurrencyRerollRare"
EXALTED_ORB_ID = "Metadata/Items/Currency/CurrencyAddModToRare"
SUPPORTED_POE_VERSIONS = (POE1, POE2)


@dataclass(frozen=True)
class RatePair:
    left_item_id: str
    right_item_id: str

    def to_config(self) -> dict[str, str]:
        return {
            "left_item_id": self.left_item_id,
            "right_item_id": self.right_item_id,
        }


DEFAULT_RATE_PAIRS = {
    POE1: RatePair(DIVINE_ORB_ID, CHAOS_ORB_ID),
    POE2: RatePair(DIVINE_ORB_ID, EXALTED_ORB_ID),
}


class RatePairValidationError(ValueError):
    """Raised when a requested pair operation violates the domain rules."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def default_rate_pairs_config() -> dict[str, list[dict[str, str]]]:
    """Return a fresh config payload containing each realm's initial pair."""
    return {
        poe_version: [DEFAULT_RATE_PAIRS[poe_version].to_config()]
        for poe_version in SUPPORTED_POE_VERSIONS
    }


def ensure_rate_pair_config(config: dict[str, Any]) -> None:
    """Add only missing rate-pair keys while preserving explicit empty lists."""
    poetore = config.get("poetore")
    if not isinstance(poetore, dict):
        poetore = {}
        config["poetore"] = poetore

    rate_pairs = poetore.get("exchange_rate_pairs")
    if not isinstance(rate_pairs, dict):
        rate_pairs = {}
        poetore["exchange_rate_pairs"] = rate_pairs

    defaults = default_rate_pairs_config()
    for poe_version in SUPPORTED_POE_VERSIONS:
        if poe_version not in rate_pairs:
            rate_pairs[poe_version] = defaults[poe_version]


def normalize_rate_pairs(
    raw_pairs: object,
    valid_item_ids: Collection[str],
) -> tuple[RatePair, ...]:
    """Normalize untrusted persisted pairs, preserving the first valid order."""
    if not isinstance(raw_pairs, list):
        return ()

    normalized: list[RatePair] = []
    seen: set[tuple[str, str]] = set()
    for raw_pair in raw_pairs:
        if not isinstance(raw_pair, dict):
            continue
        left_item_id = raw_pair.get("left_item_id")
        right_item_id = raw_pair.get("right_item_id")
        if not isinstance(left_item_id, str) or not isinstance(right_item_id, str):
            continue
        if left_item_id == right_item_id:
            continue
        if left_item_id not in valid_item_ids or right_item_id not in valid_item_ids:
            continue
        key = (left_item_id, right_item_id)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(RatePair(left_item_id, right_item_id))
        if len(normalized) == MAX_RATE_PAIRS:
            break
    return tuple(normalized)


class ExchangeRatePairStore:
    """Own ordered rate-pair mutations and issue exactly one save per change."""

    def __init__(
        self,
        config: dict[str, Any],
        save_config: Callable[[dict[str, Any]], None],
        *,
        catalog_ids: Callable[[str], Collection[str]] | None = None,
    ):
        self._config = config
        self._save_config = save_config
        self._catalog_ids = catalog_ids or (
            lambda poe_version: exchange_catalog_by_id(poe_version).keys()
        )

    def pairs(self, poe_version: str) -> tuple[RatePair, ...]:
        self._require_poe_version(poe_version)
        poetore = self._config.get("poetore")
        pair_config = poetore.get("exchange_rate_pairs") if isinstance(poetore, dict) else None
        raw_pairs = pair_config.get(poe_version) if isinstance(pair_config, dict) else None
        return normalize_rate_pairs(raw_pairs, self._catalog_ids(poe_version))

    def add(self, poe_version: str, left_item_id: str, right_item_id: str) -> RatePair:
        current = list(self.pairs(poe_version))
        valid_ids = self._catalog_ids(poe_version)
        if left_item_id not in valid_ids or right_item_id not in valid_ids:
            raise RatePairValidationError("unknown_item", "The pair contains an unknown item ID")
        if left_item_id == right_item_id:
            raise RatePairValidationError("same_item", "Both sides of a pair must differ")
        pair = RatePair(left_item_id, right_item_id)
        if pair in current:
            raise RatePairValidationError("duplicate", "The same directed pair is already registered")
        if len(current) >= MAX_RATE_PAIRS:
            raise RatePairValidationError("limit", "No more than five pairs can be registered")
        current.append(pair)
        self._replace(poe_version, current)
        return pair

    def remove(self, poe_version: str, index: int) -> RatePair:
        current = list(self.pairs(poe_version))
        self._require_index(index, len(current))
        removed = current.pop(index)
        self._replace(poe_version, current)
        return removed

    def move_up(self, poe_version: str, index: int) -> bool:
        return self._move(poe_version, index, index - 1)

    def move_down(self, poe_version: str, index: int) -> bool:
        return self._move(poe_version, index, index + 1)

    def _move(self, poe_version: str, index: int, destination: int) -> bool:
        current = list(self.pairs(poe_version))
        self._require_index(index, len(current))
        if destination < 0 or destination >= len(current):
            return False
        current[index], current[destination] = current[destination], current[index]
        self._replace(poe_version, current)
        return True

    def _replace(self, poe_version: str, pairs: list[RatePair]) -> None:
        ensure_rate_pair_config(self._config)
        self._config["poetore"]["exchange_rate_pairs"][poe_version] = [
            pair.to_config() for pair in pairs
        ]
        self._save_config(self._config)

    @staticmethod
    def _require_poe_version(poe_version: str) -> None:
        if poe_version not in SUPPORTED_POE_VERSIONS:
            raise RatePairValidationError("poe_version", "Unsupported PoE version")

    @staticmethod
    def _require_index(index: int, size: int) -> None:
        if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= size:
            raise RatePairValidationError("index", "Pair index is out of range")
