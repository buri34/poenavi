from __future__ import annotations

from dataclasses import dataclass, field


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
