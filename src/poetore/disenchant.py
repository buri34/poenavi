from __future__ import annotations

import math
import re

from .metadata import unique_disenchant_value
from .models import ParsedItem

_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
_QUALITY_LABELS = {"quality", "品質"}
_ELDRITCH_INFLUENCE_FLAGS = {"searing_item", "tangled_item"}


def _quality(item: ParsedItem) -> float:
    for label, value in item.properties.items():
        if label.strip().casefold() not in _QUALITY_LABELS:
            continue
        match = _NUMBER.search(str(value).replace(",", ""))
        if match:
            return max(0.0, float(match.group()))
    return 0.0


def disenchant_dust(
    item: ParsedItem,
    *,
    unique_name: str | None = None,
    base_type: str | None = None,
) -> int | None:
    """Awakenedと同じ係数でUniqueのThaumaturgic Dust推定量を返す。"""
    if item.rarity.casefold() not in {"unique", "ユニーク"} or item.item_level is None:
        return None
    name = str(unique_name or item.name).strip()
    base = str(base_type or item.base_type).strip()
    base_value = unique_disenchant_value(name, base)
    if base_value is None:
        return None

    influence_count = sum(flag.startswith("influence:") for flag in item.flags)
    influence_count += sum(flag in _ELDRITCH_INFLUENCE_FLAGS for flag in item.flags)
    corrupted_implicit_count = sum(
        modifier.generation == "corrupted" or modifier.kind == "corrupted"
        for modifier in item.modifiers
    )
    increase_percent = (
        influence_count * 50
        + _quality(item) * 2
        + corrupted_implicit_count * 50
    )

    item_level = int(item.item_level)
    level_47_to_68 = min(max(item_level, 46), 68) - 46
    level_69_to_84 = min(max(item_level, 68), 84) - 68
    level_factor = (
        50
        + 2 * level_47_to_68
        + math.floor(3 * level_47_to_68 / 11)
        + 25 * level_69_to_84
    )
    total = base_value * 5 * level_factor * (100 + increase_percent) / 100
    return math.floor(total)
