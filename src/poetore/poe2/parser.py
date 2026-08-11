from __future__ import annotations

import re

from ..models import ItemModifier, ParsedItem
from .metadata import (
    resolve_identity,
    resolve_identity_candidates,
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
    "Life Flasks": "flask", "Life Flask": "flask", "ライフフラスコ": "flask",
    "Mana Flasks": "flask", "Mana Flask": "flask", "マナフラスコ": "flask",
    "Flask": "flask",
    "Map Fragments": "map_fragment", "Map Fragment": "map_fragment",
    "マップフラグメント": "map_fragment",
    "Expedition Logbooks": "expedition_logbook",
    "Expedition Logbook": "expedition_logbook", "エクスペディションログブック": "expedition_logbook",
    "Breachstones": "breachstone", "Breachstone": "breachstone", "ブリーチストーン": "breachstone",
    "Wombgifts": "wombgift", "Wombgift": "wombgift", "ウォンブギフト": "wombgift",
    "Uncut Skill Gems": "uncut_gem",
    "スキルジェムの原石": "uncut_gem",
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
    "Talismans": "talisman", "Talisman": "talisman", "タリスマン": "talisman",
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
    "life_flask": "flask.life",
    "mana_flask": "flask.mana",
    "map_fragment": "map.fragment",
    "pinnacle_key": "map.bosskey",
    "vault_key": "map.fragment",
    "expedition_logbook": "map.logbook",
    "breachstone": "map.breachstone",
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
    "uncut_gem": "currency",
    "talisman": "weapon.talisman",
}
_LOCAL_AFFIX_CATEGORIES = {
    "bow", "focus", "crossbow", "spear", "flail", "staff", "quarterstaff",
    "wand", "sceptre", "one_mace", "two_mace", "one_sword", "two_sword",
    "one_axe", "two_axe", "dagger", "talisman", "buckler", "shield", "body_armour",
    "helmet", "gloves", "boots", "quiver",
}
_WEAPON_LOCAL_AFFIX_CATEGORIES = {
    "bow", "crossbow", "spear", "flail", "staff", "quarterstaff", "wand",
    "sceptre", "one_mace", "two_mace", "one_sword", "two_sword", "one_axe",
    "two_axe", "dagger", "talisman",
}
_ARMOUR_LOCAL_AFFIX_CATEGORIES = {
    "focus", "buckler", "shield", "body_armour", "helmet", "gloves", "boots",
    "quiver",
}
_LOCAL_DEFENCE_TERMS = (
    "Armour", "Evasion Rating", "Energy Shield", "Runic Ward",
)
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
    "Mirrored": "mirrored", "ミラー状態": "mirrored", "ミラー化": "mirrored", "ミラー化アイテム": "mirrored",
    "Sanctified": "sanctified", "聖別化": "sanctified", "聖別化アイテム": "sanctified",
    "Desecrated": "desecrated", "冒涜": "desecrated", "冒涜アイテム": "desecrated",
    "Fractured Item": "fractured", "フラクチャーアイテム": "fractured",
}
_DESCRIPTION_PREFIXES = (
    "Can be used in a Map Device", "マップデバイスで使用すると",
)

_TABLET_USES = (
    re.compile(r"^(\d+)\s+uses?\s+remaining$", re.IGNORECASE),
    re.compile(r"^残り使用回数\s*(\d+)回$"),
)
_CHARM_DURATION = (
    re.compile(r"^Lasts\s+(\d+(?:\.\d+)?)\s+Seconds?$", re.IGNORECASE),
    re.compile(r"^(\d+(?:\.\d+)?)秒間持続$"),
)
_CHARM_CONSUMPTION = (
    re.compile(
        r"^Consumes\s+(\d+)\s*(?:\(augmented\)\s*)?of\s+(\d+)\s+Charges on use$",
        re.IGNORECASE,
    ),
    re.compile(r"^使用時に(\d+)中(\d+)\s*(?:\(augmented\))?チャージを消費$"),
)
_CHARM_CURRENT = (
    re.compile(r"^Currently has\s+(\d+)\s+Charges$", re.IGNORECASE),
    re.compile(r"^現在(\d+)チャージ$"),
)
_CHARM_EFFECT = (
    re.compile(r"^Grants\s+(.+)$", re.IGNORECASE),
    re.compile(r"^(.+)を付与する$"),
)


def _consume_special_property(category: str, line: str, properties: dict[str, str]) -> bool:
    """Consume non-Trade item properties using stable bilingual keys.

    EE2 consumes the whole Charm flask-property section so its duration,
    charge counters and granted effect never reach modifier matching.  Keep
    those useful display values in PoENavi while preserving the same Trade
    behaviour.
    """
    if category == "tablet":
        for pattern in _TABLET_USES:
            match = pattern.fullmatch(line)
            if match:
                properties["残り使用回数"] = match.group(1)
                return True
    if category != "charm":
        return False
    for pattern in _CHARM_DURATION:
        match = pattern.fullmatch(line)
        if match:
            properties["持続時間"] = match.group(1)
            return True
    for pattern in _CHARM_CONSUMPTION:
        match = pattern.fullmatch(line)
        if match:
            if line.startswith("使用時に"):
                properties["最大チャージ"] = match.group(1)
                properties["使用チャージ"] = match.group(2)
            else:
                properties["使用チャージ"] = match.group(1)
                properties["最大チャージ"] = match.group(2)
            return True
    for pattern in _CHARM_CURRENT:
        match = pattern.fullmatch(line)
        if match:
            properties["現在チャージ"] = match.group(1)
            return True
    for pattern in _CHARM_EFFECT:
        match = pattern.fullmatch(line)
        if match:
            properties["効果"] = match.group(1).strip()
            return True
    return False


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
    if category == "uncut_gem":
        return identity_category == "UncutSkillGem"
    if category == "flask":
        return identity_category == "Flask"
    if category == "wombgift":
        return identity_category == "BrequelFruit"
    if category == "map_fragment":
        return identity_category == "MapFragment"
    if category == "expedition_logbook":
        return identity_category in {"ExpeditionLogbook", "MapFragment"} and "logbook" in ref_name
    if category == "breachstone":
        return identity_category == "Breachstone"
    if category == "barya":
        return identity_category in {"MiscMapItem", "MapFragment"} and "barya" in ref_name
    if category == "ultimatum":
        return identity_category == "MiscMapItem" and "ultimatum" in ref_name
    return False


def _base_identity_candidates(
    raw_base: str, category: str | None, rarity: str,
) -> tuple[dict, ...]:
    exact = tuple(
        identity for identity in resolve_identity_candidates(raw_base, "ITEM")
        if _identity_matches_category(identity, category)
    )
    if exact:
        return exact
    if rarity != "magic":
        return ()
    fragments = tuple(
        identity for identity in resolve_identity_fragments(raw_base, "ITEM")
        if _identity_matches_category(identity, category)
    )
    if not fragments:
        return ()
    comparable = raw_base.strip().casefold()
    lengths = {
        id(identity): max(
            len(str(name)) for name in (identity.get("names") or {}).values()
            if str(name).strip().casefold() in comparable
        )
        for identity in fragments
    }
    longest = max(lengths.values())
    return tuple(identity for identity in fragments if lengths[id(identity)] == longest)


def _resolve_base_identity(
    raw_base: str, category: str | None, rarity: str,
    preferred_ref: str | None = None,
) -> dict | None:
    candidates = _base_identity_candidates(raw_base, category, rarity)
    if preferred_ref:
        preferred = next(
            (row for row in candidates if row.get("ref_name") == preferred_ref), None,
        )
        if preferred is not None:
            return preferred
    return candidates[0] if candidates else None


_BASE_DEFENCE_PROPERTIES = {
    "ar": ("アーマー", "Armour"),
    "ev": ("回避力", "Evasion Rating"),
    "es": ("エナジーシールド", "Energy Shield"),
    "ward": ("ルーンワード", "Runic Ward", "Ward"),
}
_BASE_DEFENCE_FLAT_REFS = {
    "ar": {"# to Armour"},
    "ev": {"# to Evasion Rating"},
    "es": {"# to maximum Energy Shield"},
    "ward": {"# to maximum Runic Ward", "# to Ward"},
}
_BASE_DEFENCE_INCREASED_REFS = {
    "ar": {
        "#% increased Armour", "#% increased Armour and Energy Shield",
        "#% increased Armour and Evasion", "#% increased Armour, Evasion and Energy Shield",
    },
    "ev": {
        "#% increased Evasion Rating", "#% increased Armour and Evasion",
        "#% increased Evasion and Energy Shield", "#% increased Armour, Evasion and Energy Shield",
    },
    "es": {
        "#% increased Energy Shield", "#% increased Armour and Energy Shield",
        "#% increased Evasion and Energy Shield", "#% increased Armour, Evasion and Energy Shield",
    },
    "ward": {"#% increased Runic Ward", "#% increased Ward"},
}


def _numeric_property(properties: dict[str, str], *labels: str) -> float | None:
    for label in labels:
        value = properties.get(label)
        if value is None:
            continue
        match = re.search(r"[-+]?\d+(?:\.\d+)?", value.replace(",", ""))
        if match:
            return float(match.group())
    return None


def _copied_base_defences(item: ParsedItem) -> dict[str, float]:
    """Undo copied quality/local modifiers for comparison with EE2 base data."""
    quality = _numeric_property(item.properties, "品質", "Quality") or 0.0
    result = {}
    for defence, labels in _BASE_DEFENCE_PROPERTIES.items():
        total = _numeric_property(item.properties, *labels)
        if total is None:
            continue
        flat = increased = 0.0
        for modifier in item.modifiers:
            ref = re.sub(r"\s*\((?:Local|ローカル)\)\s*$", "", modifier.ref or "")
            value = modifier.values[0] if modifier.values else 0.0
            if ref in _BASE_DEFENCE_FLAT_REFS[defence]:
                flat += value
            elif ref in _BASE_DEFENCE_INCREASED_REFS[defence]:
                increased += value
        denominator = (1.0 + quality / 100.0) * (1.0 + increased / 100.0)
        if denominator > 0:
            result[defence] = total / denominator - flat
    return result


def _refine_base_identity(
    raw_base: str, category: str, rarity: str, item: ParsedItem,
    preferred_ref: str | None = None,
) -> dict | None:
    candidates = _base_identity_candidates(raw_base, category, rarity)
    if preferred_ref:
        preferred = [row for row in candidates if row.get("ref_name") == preferred_ref]
        if len(preferred) == 1:
            return preferred[0]
        if preferred:
            candidates = tuple(preferred)
    distinct_refs = {str(row.get("ref_name", "")) for row in candidates}
    if len(distinct_refs) <= 1:
        return candidates[0] if candidates else None

    copied = _copied_base_defences(item)
    scored = []
    for candidate in candidates:
        armour = candidate.get("armour") or {}
        differences = []
        for defence, actual in copied.items():
            bounds = armour.get(defence)
            if not bounds:
                continue
            low, high = (float(bounds[0]), float(bounds[-1]))
            differences.append(0.0 if low <= actual <= high else min(abs(actual - low), abs(actual - high)))
        if differences:
            scored.append((max(differences), sum(differences), candidate))
    scored.sort(key=lambda row: (row[0], row[1]))
    if scored and scored[0][0] <= 1.5:
        if len(scored) == 1 or scored[1][:2] != scored[0][:2]:
            return scored[0][2]
    return None


def _is_local_stat_entry(entry: dict) -> bool:
    return bool(re.search(
        r"\s*\((?:Local|ローカル)\)\s*$",
        str((entry.get("text") or {}).get("en", "")),
        flags=re.IGNORECASE,
    ))


def _select_scoped_stat_candidate(candidates, category: str, line_kind: str):
    """Choose Local/Global scope from item domain, then preserve matcher priority."""
    if not candidates:
        return None
    local_candidates = tuple(row for row in candidates if _is_local_stat_entry(row[0]))
    non_local_candidates = tuple(row for row in candidates if not _is_local_stat_entry(row[0]))
    if not local_candidates or not non_local_candidates:
        return candidates[0]

    local_ref = str((local_candidates[0][0].get("text") or {}).get("en", ""))
    if category in _ARMOUR_LOCAL_AFFIX_CATEGORIES:
        prefer_local = any(term in local_ref for term in _LOCAL_DEFENCE_TERMS)
    elif category in _WEAPON_LOCAL_AFFIX_CATEGORIES:
        # The audited crafted accuracy hybrid on weapons uses the non-Local ID,
        # while ordinary weapon accuracy and attack properties remain Local.
        prefer_local = not (line_kind == "crafted" and "Accuracy Rating" in local_ref)
    else:
        prefer_local = False
    return (local_candidates if prefer_local else non_local_candidates)[0]


def parse_item_text(text: str) -> ParsedItem:
    labels, identity_lines = _header(text)
    item_class = labels.get("item_class", "")
    rarity = _RARITIES.get(labels.get("rarity", ""), labels.get("rarity", "").casefold())
    category = _CLASS_CATEGORY.get(item_class)
    unidentified = any(
        line.strip() in {"Unidentified", "未鑑定"} for line in text.splitlines()
    )
    if not item_class and rarity == "gem" and len(identity_lines) == 1:
        # PoE2 omits Item Class for Meta Gems.  EE2 handles that omission as a
        # dedicated special case; require both the copied Meta tag and the GEM
        # identity category so an arbitrary malformed Gem cannot enter it.
        tag_section = re.split(r"^--------\s*$", text.strip(), flags=re.MULTILINE)[1:2]
        tag_text = tag_section[0] if tag_section else ""
        candidate = resolve_identity(identity_lines[0], "GEM")
        if (
            candidate is not None
            and candidate.get("category") == "MetaSkillGem"
            and re.search(r"(?:^|,\s*)(?:Meta|メタ)(?:\s*,|$)", tag_text, re.MULTILINE)
        ):
            item_class = "Meta Gems"
            category = "gem"
    if not item_class or not rarity or not identity_lines:
        raise Poe2ItemParseError("PoE2アイテムのclass、rarity、identityを解決できません")

    raw_base = identity_lines[-1]
    identity_namespace = "GEM" if category == "gem" or rarity == "gem" else "ITEM"
    unique_identity = None
    if rarity == "unique" and not unidentified:
        if len(identity_lines) < 2:
            raise Poe2ItemParseError("PoE2 Unique名がありません")
        unique_identity = resolve_identity(identity_lines[-2], "UNIQUE")
        if unique_identity is None:
            raise Poe2ItemParseError(f"PoE2 Unique identity未解決: {identity_lines[-2]}")
    preferred_base_ref = str((unique_identity or {}).get("base_ref", "")) or None
    base_resolution_rarity = "magic" if unidentified else rarity
    base_identity = (
        resolve_identity(raw_base, identity_namespace)
        if identity_namespace != "ITEM"
        else _resolve_base_identity(
            raw_base, category, base_resolution_rarity, preferred_base_ref,
        )
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
    elif identity_category == "UncutSkillGem":
        category = "uncut_gem"
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
    elif identity_category == "Flask":
        category = "mana_flask" if "mana flask" in base_type.casefold() else "life_flask"
    elif identity_category == "PinnacleKey":
        category = "pinnacle_key"
    elif identity_category == "VaultKey":
        category = "vault_key"
    elif identity_category == "Breachstone":
        category = "breachstone"
    elif identity_category == "ExpeditionLogbook":
        category = "expedition_logbook"
    elif identity_category == "BrequelFruit":
        category = "wombgift"
    elif identity_category in {"MiscMapItem", "MapFragment"}:
        folded_base = base_type.casefold()
        if "logbook" in folded_base:
            category = "expedition_logbook"
        elif "barya" in folded_base:
            category = "barya"
        elif "ultimatum" in folded_base:
            category = "ultimatum"
        else:
            category = "map_fragment"
    if not category:
        raise Poe2ItemParseError(f"PoE2カテゴリ未解決: {item_class} / {base_type}")

    if rarity == "unique" and not unidentified:
        name = str(unique_identity["ref_name"])
    elif rarity == "currency":
        name = base_type
    else:
        name = identity_lines[-2] if len(identity_lines) >= 2 else ""

    item_level = None
    properties = {}
    modifiers = []
    flags = {"unidentified"} if unidentified else set()
    augment_count = 0
    if base_type.casefold().startswith("runemastered "):
        flags.add("runemastered")
    elif base_type.casefold().startswith("runeforged "):
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
        if _consume_special_property(category, line, properties):
            continue
        if line.startswith(_DESCRIPTION_PREFIXES):
            continue
        if any(line.startswith(f"{label}:") for label in _LABELS):
            continue
        # EE2 consumes Gem description/effect sections before its modifier
        # parser. Gem trade searches use identity, level, quality and sockets;
        # prose and skill effects are not item modifiers.
        if category in {"active_gem", "support_gem", "meta_gem", "uncut_gem"}:
            continue
        standalone_augment = bool(re.search(r"\(rune\)\s*$", line, re.IGNORECASE))
        line_kind = "augment" if standalone_augment else current_kind
        if standalone_augment and current_kind != "augment":
            augment_count += 1
        scoped_affix = (
            category in _LOCAL_AFFIX_CATEGORIES
            and line_kind in {"explicit", "fractured", "crafted", "desecrated"}
            and (rarity != "unique" or category in _ARMOUR_LOCAL_AFFIX_CATEGORIES)
        )
        preferred_stat_type = "rune" if line_kind == "augment" else line_kind
        candidates = resolve_stat_line_candidates(
            line, preferred_stat_type, include_local_variants=scoped_affix,
        )
        resolved = _select_scoped_stat_candidate(candidates, category, line_kind)
        if resolved:
            entry, values = resolved
            raw_stat_id = str(entry.get("id", ""))
            roll_min, roll_max, better = _roll_bounds(line)
            is_negated_match = bool(values) and all(value <= 0 for value in values) and (
                re.search(r"\breduced\b", line, re.IGNORECASE) is not None
                or "減少する" in line
            )
            if is_negated_match:
                if roll_min is not None and roll_max is not None:
                    roll_min, roll_max = sorted((-roll_min, -roll_max))
                better = -1
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
    item = ParsedItem(
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
    if identity_namespace == "ITEM":
        refined = _refine_base_identity(
            raw_base, category, base_resolution_rarity, item, preferred_base_ref,
        )
        candidate_refs = {
            str(row.get("ref_name", ""))
            for row in _base_identity_candidates(raw_base, category, base_resolution_rarity)
        }
        if refined is None and len(candidate_refs) > 1:
            raise Poe2ItemParseError(f"PoE2 base identity曖昧: {raw_base}")
        if refined is not None and refined.get("ref_name") != item.base_type:
            item = ParsedItem(**{**item.__dict__, "base_type": str(refined["ref_name"])})
    return item
