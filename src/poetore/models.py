from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field


def apply_roll_increase(
    value: float, percent: float | None, *, decimal: bool = False,
) -> float:
    """Apply advanced-description roll increase using Awakened/PoE truncation."""
    if not percent:
        return value
    scale = 100 if decimal else 1
    increased = value + value * percent / 100.0
    return math.trunc((increased + sys.float_info.epsilon) * scale) / scale


@dataclass(frozen=True)
class ItemModifier:
    text: str
    values: tuple[float, ...] = ()
    kind: str = "explicit"
    tier: int | None = None
    affix: str | None = None
    group: int | None = None
    ref: str | None = None
    stat_id: str | None = None
    confidence: float = 0.0
    roll_min: float | None = None
    roll_max: float | None = None
    better: int | None = None
    inverted: bool = False
    generation: str | None = None
    option_value: int | str | None = None
    option_text: str | None = None
    oils: tuple[int, ...] = ()
    decimal: bool = False
    # 詳細コピーのMod見出しに品質によるロール増加が明示される。
    # Noneは通常コピー等で由来を判定できない場合、Falseは明示的な非対象。
    quality_affected: bool | None = None
    roll_increase: float | None = None
    # 将来のPoE2 Local／Global監査で比較候補を保持できる予約フィールド。
    # 通常検索ではカテゴリから選んだstat_idだけを送る。
    stat_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedItem:
    item_class: str
    rarity: str
    name: str
    base_type: str
    category: str
    item_level: int | None = None
    properties: dict[str, str] = field(default_factory=dict)
    modifiers: tuple[ItemModifier, ...] = ()
    flags: tuple[str, ...] = ()
    raw_text: str = ""
    # PoE2のRune/Soul Coreセクション数。複数行効果を複数ソケットと誤認しない。
    augment_count: int = 0
