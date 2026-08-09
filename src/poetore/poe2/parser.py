from __future__ import annotations

import re

from ..models import ItemModifier, ParsedItem
from .metadata import (
    resolve_identity,
    resolve_identity_fragments,
    resolve_stat_line_candidates,
)


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
    "Charms": "charm", "Charm": "charm", "チャーム": "charm",
    "Tablets": "tablet", "Tablet": "tablet", "石板": "tablet", "タブレット": "tablet",
    "Relics": "relic", "Relic": "relic", "レリック": "relic",
    "Jewels": "jewel", "Jewel": "jewel", "ジュエル": "jewel",
    "Baryas": "barya", "Barya": "barya", "バリャ": "barya",
    "Ultimatums": "ultimatum", "Ultimatum": "ultimatum", "アルティメイタム": "ultimatum",
    "Waystones": "waystone", "Waystone": "waystone", "ウェイストーン": "waystone",
    "Runes": "rune", "Rune": "rune", "ルーン": "rune",
    "Soul Cores": "soul_core", "Soul Core": "soul_core", "ソウルコア": "soul_core",
    "Skill Gems": "gem", "スキルジェム": "gem",
    "Support Gems": "gem", "サポートジェム": "gem",
    "Meta Gems": "gem", "メタジェム": "gem",
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
    "charm": "flask.charm",
    "tablet": "map.tablet",
    "relic": "sanctum.relic",
    "jewel": "jewel",
    "barya": "map.barya",
    "ultimatum": "map.ultimatum",
    "waystone": "map.waystone",
    "rune": "currency.rune",
    "soul_core": "currency.soulcore",
    "active_gem": "gem.activegem",
    "support_gem": "gem.supportgem",
    "meta_gem": "gem.metagem",
}
_LOCAL_AFFIX_CATEGORIES = {
    "bow", "focus", "crossbow", "spear", "flail", "staff", "quarterstaff",
    "wand", "sceptre", "one_mace", "two_mace", "one_sword", "two_sword",
    "one_axe", "two_axe", "dagger", "buckler", "shield", "body_armour",
    "helmet", "gloves", "boots", "quiver",
}
_RARITIES = {
    "Currency": "currency",
    "カレンシー": "currency",
    "Rare": "rare",
    "レア": "rare",
    "Unique": "unique",
    "ユニーク": "unique",
    "Normal": "normal",
    "ノーマル": "normal",
    "Magic": "magic",
    "マジック": "magic",
    "Gem": "gem",
    "ジェム": "gem",
}
_PROPERTY_LABELS = {
    "Quality", "品質", "Armour", "アーマー", "Evasion Rating", "回避力",
    "Energy Shield", "エナジーシールド", "Spirit", "スピリット", "Block Chance", "ブロック率",
    "Physical Damage", "物理ダメージ", "Elemental Damage", "元素ダメージ",
    "Attacks per Second", "秒間アタック回数", "Critical Hit Chance", "クリティカルヒット率",
    "Reload Time", "リロード時間", "Requires", "要求値", "Sockets", "ソケット",
    "Requirements", "装備条件",
    "Runic Ward", "ルーンワード", "Deflection Rating", "受け流し力",
    "Waystone Tier", "ウェイストーンティア", "Revives Available", "復活が利用可能",
    "Monster Pack Size", "モンスターパックサイズ", "Pack Size", "パックサイズ",
    "Waystone Drop Chance", "ウェイストーンドロップ確率", "ウェイストーンドロップ率",
    "Magic Monsters", "モンスターエフェクティブ",
    "Rare Monsters", "モンスターレアリティ", "Area Level", "エリアレベル",
    "Unidentified Tier", "未鑑定ティア",
    "Number of Trials", "試練数", "Radius", "半径",
    "Uses Remaining", "残り使用回数", "使用回数残り",
}

_ULTIMATUM_HINT_LINES = {
    "Victorious": "Victorious", "勝利": "Victorious", "勝利の": "Victorious",
    "Cowardly": "Cowardly", "卑怯者": "Cowardly", "臆病者": "Cowardly", "臆病者の": "Cowardly",
    "Deadly": "Deadly", "致死": "Deadly", "致命的": "Deadly", "致命的な": "Deadly",
}

_STATE_LINES = {
    "Corrupted": "corrupted", "コラプト状態": "corrupted", "コラプト": "corrupted",
    "Mirrored": "mirrored", "ミラー化": "mirrored", "ミラー化アイテム": "mirrored",
    "Sanctified": "sanctified", "聖別化": "sanctified", "聖別化アイテム": "sanctified",
    "Desecrated": "desecrated", "冒涜": "desecrated", "冒涜アイテム": "desecrated",
    "Fractured Item": "fractured", "フラクチャーアイテム": "fractured",
}
_DESCRIPTION_PREFIXES = (
    "Can be used in a Map Device", "マップデバイスで使用すると",
)


def _roll_bounds(text: str) -> tuple[float | None, float | None, int | None]:
    ranges = re.findall(
        r"-?\d+(?:\.\d+)?\s*\(\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*\)",
        text,
    )
    if not ranges:
        return None, None, None
    minimum = sum(float(low) for low, _high in ranges) / len(ranges)
    maximum = sum(float(high) for _low, high in ranges) / len(ranges)
    # Only expose the convenience slider when larger values are unambiguously
    # beneficial. Ambiguous/inverted lines remain editable as normal min/max.
    lowered = text.casefold()
    negative_markers = ("reduced", "less", "減少", "低下", "失う", "受ける")
    better = None if any(marker in lowered for marker in negative_markers) else 1
    return minimum, maximum, better


def _mod_kind_from_heading(heading: str, previous: str | None) -> str | None:
    lowered = heading.casefold()
    if "冒涜" in heading or "desecrated" in lowered:
        return "desecrated"
    if "聖別" in heading or "sanctified" in lowered:
        return "sanctified"
    if "破砕" in heading or "フラクチャー" in heading or "fractured" in lowered:
        return "fractured"
    if "クラフト" in heading or "crafted" in lowered:
        return "crafted"
    if "エンチャント" in heading or "enchant" in lowered:
        return "enchant"
    if "ルーン" in heading or "rune" in lowered:
        return "augment"
    if "暗黙" in heading or "implicit" in lowered:
        return "implicit"
    if "レリック" in heading or "sanctum" in lowered or "relic" in lowered:
        return "sanctum"
    if any(label in heading for label in ("プレフィックス", "サフィックス", "ユニーク")):
        return "explicit"
    if any(label in lowered for label in ("prefix", "suffix", "unique")):
        return "explicit"
    return previous


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


def _identity_matches_category(identity: dict, category: str | None) -> bool:
    if category is None:
        return True
    identity_category = str(identity.get("category", ""))
    mapped = _CLASS_CATEGORY.get(identity_category)
    if mapped == category:
        return True
    ref_name = str(identity.get("ref_name", "")).casefold()
    if category == "waystone":
        return identity_category == "Map" and "waystone" in ref_name
    if category in {"rune", "soul_core"}:
        return identity_category == "SoulCore"
    if category == "tablet":
        return identity_category == "TowerAugment"
    if category == "relic":
        return identity_category == "Relic"
    if category == "charm":
        return identity_category == "Charm"
    if category == "jewel":
        return identity_category == "Jewel"
    return False


def _resolve_base_identity(raw_base: str, category: str | None, rarity: str) -> dict | None:
    exact = resolve_identity(raw_base, "ITEM")
    if exact is not None:
        return exact
    if rarity != "magic":
        return None
    return next(
        (
            identity
            for identity in resolve_identity_fragments(raw_base, "ITEM")
            if _identity_matches_category(identity, category)
        ),
        None,
    )


def parse_item_text(text: str) -> ParsedItem:
    labels, identity_lines = _header(text)
    item_class = labels.get("item_class", "")
    rarity = _RARITIES.get(labels.get("rarity", ""), labels.get("rarity", "").casefold())
    category = _CLASS_CATEGORY.get(item_class)
    if not item_class or not rarity or not identity_lines:
        raise Poe2ItemParseError("PoE2アイテムのclass、rarity、identityを解決できません")

    raw_base = identity_lines[-1]
    identity_namespace = "GEM" if category == "gem" or rarity == "gem" else "ITEM"
    base_identity = (
        resolve_identity(raw_base, identity_namespace)
        if identity_namespace != "ITEM"
        else _resolve_base_identity(raw_base, category, rarity)
    )
    if base_identity is None:
        raise Poe2ItemParseError(f"PoE2 base identity未解決: {raw_base}")
    base_type = str(base_identity["ref_name"])
    category = category or _CLASS_CATEGORY.get(str(base_identity.get("category", "")))
    identity_category = str(base_identity.get("category", ""))
    if identity_namespace == "GEM":
        category = {
            "Active Skill Gem": "active_gem",
            "Support Skill Gem": "support_gem",
            "MetaSkillGem": "meta_gem",
        }.get(identity_category, category)
    if category is None and identity_category == "Map" and "waystone" in base_type.casefold():
        category = "waystone"
    if identity_category == "SoulCore":
        identity_text = f"{raw_base} {base_type}".casefold()
        category = "soul_core" if ("soul core" in identity_text or "ソウルコア" in identity_text) else "rune"
    elif identity_category == "TowerAugment":
        category = "tablet"
    elif identity_category == "Relic":
        category = "relic"
    elif identity_category == "Charm":
        category = "charm"
    elif identity_category == "Jewel":
        category = "jewel"
    elif identity_category in {"MiscMapItem", "MapFragment"}:
        folded_base = base_type.casefold()
        if "barya" in folded_base:
            category = "barya"
        elif "ultimatum" in folded_base or folded_base.endswith(" fate"):
            category = "ultimatum"
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
    flags = set()
    augment_count = 0
    if base_type.casefold().startswith(("runeforged ", "runemastered ")):
        flags.add("runeforged")
    current_kind = None
    for line in text.splitlines():
        line = line.strip().replace("：", ":")
        if line.startswith("{") and line.endswith("}"):
            heading = line.strip("{} ")
            current_kind = _mod_kind_from_heading(heading, current_kind)
            if current_kind == "augment":
                augment_count += 1
            continue
        state = _STATE_LINES.get(line)
        if state:
            flags.add(state)
            continue
        ultimatum_hint = _ULTIMATUM_HINT_LINES.get(line)
        if ultimatum_hint:
            properties["Ultimatum Hint"] = ultimatum_hint
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
        if line.startswith(_DESCRIPTION_PREFIXES):
            continue
        if any(line.startswith(f"{label}:") for label in _LABELS):
            continue
        standalone_augment = bool(re.search(r"\(rune\)\s*$", line, re.IGNORECASE))
        line_kind = "augment" if standalone_augment else current_kind
        if standalone_augment and current_kind != "augment":
            augment_count += 1
        prefer_local = (
            rarity != "unique"
            and category in _LOCAL_AFFIX_CATEGORIES
            and line_kind in {"explicit", "fractured", "crafted", "desecrated"}
        )
        preferred_stat_type = "rune" if line_kind == "augment" else line_kind
        resolved = resolve_stat_line_candidates(
            line, preferred_stat_type, include_local_variants=prefer_local,
        )
        if resolved:
            entry, values = resolved[0]
            raw_stat_id = str(entry.get("id", ""))
            roll_min, roll_max, better = _roll_bounds(line)
            modifiers.append(ItemModifier(
                text=line, values=values, kind=str(entry.get("type", current_kind or "explicit")),
                ref=str((entry.get("text") or {}).get("en", line)),
                stat_id=raw_stat_id, confidence=1.0,
                roll_min=roll_min, roll_max=roll_max, better=better,
            ))
            if line_kind in {"augment", "desecrated", "fractured", "crafted", "sanctified"}:
                flags.add(line_kind)
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
        flags=tuple(sorted(flags)),
        raw_text=text,
        augment_count=augment_count,
    )
