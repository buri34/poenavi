from __future__ import annotations

import re

from ..models import ParsedItem
from .metadata import resolve_identity


class Poe2ItemParseError(ValueError):
    """PoE2コピー文面から最低限のidentityを取得できない場合。"""


_LABELS = {
    "Item Class": "item_class",
    "アイテムクラス": "item_class",
    "Rarity": "rarity",
    "レアリティ": "rarity",
}
_ITEM_LEVEL = re.compile(r"^(?:Item Level|アイテムレベル):\s*(\d+)\s*$")
_CLASS_CATEGORY = {
    "Currency": "currency",
    "カレンシー": "currency",
    "Bows": "bow",
    "弓": "bow",
    "Foci": "focus",
    "Focus": "focus",
    "フォーカス": "focus",
}
TRADE_CATEGORY_BY_CATEGORY = {
    "currency": "currency",
    "bow": "weapon.bow",
    "focus": "armour.focus",
}
_RARITIES = {
    "Currency": "currency",
    "カレンシー": "currency",
    "Rare": "rare",
    "レア": "rare",
    "Unique": "unique",
    "ユニーク": "unique",
}


def _header(text: str) -> tuple[dict[str, str], list[str]]:
    first_section = re.split(r"^--------\s*$", text.strip(), maxsplit=1, flags=re.MULTILINE)[0]
    labels: dict[str, str] = {}
    identity_lines = []
    for raw in first_section.splitlines():
        line = raw.strip()
        if not line:
            continue
        key, separator, value = line.partition(":")
        normalized = _LABELS.get(key.strip()) if separator else None
        if normalized:
            labels[normalized] = value.strip()
        else:
            identity_lines.append(line)
    return labels, identity_lines


def parse_item_text(text: str) -> ParsedItem:
    labels, identity_lines = _header(text)
    item_class = labels.get("item_class", "")
    rarity = _RARITIES.get(labels.get("rarity", ""), labels.get("rarity", "").casefold())
    category = _CLASS_CATEGORY.get(item_class)
    if not item_class or not rarity or not identity_lines or not category:
        raise Poe2ItemParseError("PoE2アイテムのclass、rarity、identityを解決できません")

    raw_base = identity_lines[-1]
    base_identity = resolve_identity(raw_base)
    if base_identity is None:
        raise Poe2ItemParseError(f"PoE2 base identity未解決: {raw_base}")
    base_type = str(base_identity["ref_name"])

    if rarity == "unique":
        if len(identity_lines) < 2:
            raise Poe2ItemParseError("PoE2 Unique名がありません")
        unique_identity = resolve_identity(identity_lines[-2])
        if unique_identity is None or unique_identity.get("namespace") != "UNIQUE":
            raise Poe2ItemParseError(f"PoE2 Unique identity未解決: {identity_lines[-2]}")
        name = str(unique_identity["ref_name"])
    elif rarity == "currency":
        name = base_type
    else:
        name = identity_lines[-2] if len(identity_lines) >= 2 else ""

    item_level = None
    for line in text.splitlines():
        match = _ITEM_LEVEL.match(line.strip())
        if match:
            item_level = int(match.group(1))
            break
    return ParsedItem(
        item_class=item_class,
        rarity=rarity,
        name=name,
        base_type=base_type,
        category=category,
        item_level=item_level,
        raw_text=text,
    )
