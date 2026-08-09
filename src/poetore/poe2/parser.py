from __future__ import annotations

import re

from ..models import ItemModifier, ParsedItem
from .metadata import resolve_identity, resolve_stat_line


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
    "Crossbows": "crossbow", "クロスボウ": "crossbow",
    "Spears": "spear", "槍": "spear",
    "Flails": "flail", "フレイル": "flail",
    "Staves": "staff", "スタッフ": "staff",
    "Quarterstaves": "quarterstaff", "クォータースタッフ": "quarterstaff",
    "Wands": "wand", "ワンド": "wand",
    "Sceptres": "sceptre", "セプター": "sceptre",
    "One Hand Maces": "one_mace", "片手メイス": "one_mace",
    "Two Hand Maces": "two_mace", "両手メイス": "two_mace",
    "One Hand Swords": "one_sword", "片手剣": "one_sword",
    "Two Hand Swords": "two_sword", "両手剣": "two_sword",
    "One Hand Axes": "one_axe", "片手斧": "one_axe",
    "Two Hand Axes": "two_axe", "両手斧": "two_axe",
    "Daggers": "dagger", "短剣": "dagger",
    "Bucklers": "buckler", "バックラー": "buckler",
    "Shields": "shield", "盾": "shield",
    "Body Armours": "body_armour", "鎧": "body_armour",
    "Helmets": "helmet", "兜": "helmet", "ヘルメット": "helmet",
    "Gloves": "gloves", "手袋": "gloves", "グローブ": "gloves",
    "Boots": "boots", "靴": "boots", "ブーツ": "boots",
    "Quivers": "quiver", "矢筒": "quiver",
    "Rings": "ring", "指輪": "ring",
    "Amulets": "amulet", "アミュレット": "amulet",
    "Belts": "belt", "ベルト": "belt",
    "Bow": "bow", "Crossbow": "crossbow", "Spear": "spear", "Flail": "flail",
    "Staff": "staff", "Warstaff": "quarterstaff", "Wand": "wand", "Sceptre": "sceptre",
    "One Hand Mace": "one_mace", "Two Hand Mace": "two_mace",
    "One Hand Sword": "one_sword", "Two Hand Sword": "two_sword",
    "One Hand Axe": "one_axe", "Two Hand Axe": "two_axe", "Dagger": "dagger",
    "Buckler": "buckler", "Shield": "shield", "Body Armour": "body_armour",
    "Helmet": "helmet", "Gloves": "gloves", "Boots": "boots", "Quiver": "quiver",
    "Ring": "ring", "Amulet": "amulet", "Belt": "belt", "Focus": "focus",
}
TRADE_CATEGORY_BY_CATEGORY = {
    "currency": "currency",
    "bow": "weapon.bow",
    "focus": "armour.focus",
    "crossbow": "weapon.crossbow", "spear": "weapon.spear", "flail": "weapon.flail",
    "staff": "weapon.staff", "quarterstaff": "weapon.warstaff", "wand": "weapon.wand",
    "sceptre": "weapon.sceptre", "one_mace": "weapon.onemace", "two_mace": "weapon.twomace",
    "one_sword": "weapon.onesword", "two_sword": "weapon.twosword",
    "one_axe": "weapon.oneaxe", "two_axe": "weapon.twoaxe", "dagger": "weapon.dagger",
    "buckler": "armour.buckler", "shield": "armour.shield", "body_armour": "armour.chest",
    "helmet": "armour.helmet", "gloves": "armour.gloves", "boots": "armour.boots",
    "quiver": "armour.quiver", "ring": "accessory.ring", "amulet": "accessory.amulet",
    "belt": "accessory.belt",
}
_RARITIES = {
    "Currency": "currency",
    "カレンシー": "currency",
    "Rare": "rare",
    "レア": "rare",
    "Unique": "unique",
    "ユニーク": "unique",
}
_PROPERTY_LABELS = {
    "Quality", "品質", "Armour", "アーマー", "Evasion Rating", "回避力",
    "Energy Shield", "エナジーシールド", "Spirit", "スピリット", "Block Chance", "ブロック率",
    "Physical Damage", "物理ダメージ", "Elemental Damage", "元素ダメージ",
    "Attacks per Second", "秒間アタック回数", "Critical Hit Chance", "クリティカルヒット率",
    "Reload Time", "リロード時間", "Requires", "要求値", "Sockets", "ソケット",
    "Requirements", "装備条件",
}
_MOD_HEADER_KIND = {
    "暗黙モッド": "implicit",
    "ユニークモッド": "explicit",
    "Implicit Modifiers": "implicit",
    "Unique Modifiers": "explicit",
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
    if not item_class or not rarity or not identity_lines:
        raise Poe2ItemParseError("PoE2アイテムのclass、rarity、identityを解決できません")

    raw_base = identity_lines[-1]
    base_identity = resolve_identity(raw_base, "ITEM")
    if base_identity is None:
        raise Poe2ItemParseError(f"PoE2 base identity未解決: {raw_base}")
    base_type = str(base_identity["ref_name"])
    category = category or _CLASS_CATEGORY.get(str(base_identity.get("category", "")))
    if not category:
        raise Poe2ItemParseError(f"PoE2カテゴリ未解決: {item_class} / {base_type}")

    if rarity == "unique":
        if len(identity_lines) < 2:
            raise Poe2ItemParseError("PoE2 Unique名がありません")
        unique_identity = resolve_identity(identity_lines[-2], "UNIQUE")
        if unique_identity is None:
            raise Poe2ItemParseError(f"PoE2 Unique identity未解決: {identity_lines[-2]}")
        name = str(unique_identity["ref_name"])
    elif rarity == "currency":
        name = base_type
    else:
        name = identity_lines[-2] if len(identity_lines) >= 2 else ""

    item_level = None
    properties = {}
    modifiers = []
    current_kind = None
    for line in text.splitlines():
        line = line.strip().replace("：", ":")
        if line.startswith("{") and line.endswith("}"):
            heading = line.strip("{} ")
            current_kind = next(
                (kind for label, kind in _MOD_HEADER_KIND.items() if heading.startswith(label)),
                current_kind,
            )
            continue
        match = _ITEM_LEVEL.match(line.strip())
        if match:
            item_level = int(match.group(1))
            continue
        key, separator, value = line.partition(":")
        if separator and key.strip() in _PROPERTY_LABELS:
            properties[key.strip()] = value.strip()
            continue
        if separator and key.strip() not in _LABELS and not _ITEM_LEVEL.match(line):
            properties[key.strip()] = value.strip()
            continue
        if not line or line == "--------" or line in identity_lines:
            continue
        if any(line.startswith(f"{label}:") for label in _LABELS):
            continue
        resolved = resolve_stat_line(line, current_kind)
        if resolved is not None:
            entry, values = resolved
            raw_stat_id = str(entry.get("id", ""))
            modifiers.append(ItemModifier(
                text=line, values=values, kind=str(entry.get("type", current_kind or "explicit")),
                ref=str((entry.get("text") or {}).get("en", line)),
                stat_id=raw_stat_id, confidence=1.0,
            ))
        elif re.search(r"\d", line) and not separator:
            # Keep suspicious numeric lines visible to the user instead of silently dropping them.
            modifiers.append(ItemModifier(text=line, confidence=0.0))
    return ParsedItem(
        item_class=item_class,
        rarity=rarity,
        name=name,
        base_type=base_type,
        category=category,
        item_level=item_level,
        properties=properties,
        modifiers=tuple(modifiers),
        raw_text=text,
    )
