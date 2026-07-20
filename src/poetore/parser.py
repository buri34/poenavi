from __future__ import annotations

import re

from .models import ItemModifier, ParsedItem
from .metadata import default_metadata_index


class ItemParseError(ValueError):
    """貼り付け文から最低限のアイテム情報を取得できない場合。"""


_LABELS = {
    "アイテムクラス": "item_class",
    "Item Class": "item_class",
    "レアリティ": "rarity",
    "Rarity": "rarity",
    "アイテムレベル": "item_level",
    "Item Level": "item_level",
}
_PROPERTY_LABELS = {
    "品質", "Quality", "防具", "アーマー", "Armour", "回避力", "Evasion Rating",
    "エナジーシールド", "Energy Shield", "物理ダメージ", "Physical Damage",
    "元素ダメージ", "Elemental Damage", "クリティカル率", "Critical Strike Chance",
    "秒間アタック回数", "Attacks per Second", "装備条件", "Requirements",
    "ソケット", "Sockets", "スタックサイズ", "Stack Size", "マップティア", "Map Tier",
    "ジェムレベル", "Level", "経験値", "Experience", "筋力", "Strength",
    "器用さ", "Dexterity", "知性", "Intelligence", "Spirit", "スピリット",
    "ブロック率", "Chance to Block", "移動速度", "Movement Speed",
    "ルーンソケット", "Rune Sockets",
}
_FLAG_LINES = {
    "未鑑定": "unidentified", "Unidentified": "unidentified",
    "コラプト状態": "corrupted", "Corrupted": "corrupted",
    "ミラー品": "mirrored", "Mirrored": "mirrored",
    "分割": "split", "スプリット": "split", "Split": "split",
    "Synthesised Item": "synthesised", "Synthesised": "synthesised",
    "シンセサイズアイテム": "synthesised", "シンセサイズ済みアイテム": "synthesised",
    "Foil": "foil", "Foil Unique": "foil", "フォイル": "foil", "フォイルユニーク": "foil",
    "Foulborn": "foulborn", "Foulborn Item": "foulborn", "穢れしアイテム": "foulborn",
    "Shaper Item": "influence:shaper", "シェイパーアイテム": "influence:shaper",
    "シェイパーのアイテム": "influence:shaper",
    "Elder Item": "influence:elder", "エルダーアイテム": "influence:elder",
    "エルダーのアイテム": "influence:elder",
    "Crusader Item": "influence:crusader", "クルセイダーアイテム": "influence:crusader",
    "Hunter Item": "influence:hunter", "ハンターアイテム": "influence:hunter",
    "Redeemer Item": "influence:redeemer", "リディーマーアイテム": "influence:redeemer",
    "Warlord Item": "influence:warlord", "ウォーロードアイテム": "influence:warlord",
}
_CATEGORY_WORDS = (
    (("武器", "Weapon", "弓", "Bow", "ワンド", "Wand", "剣", "Sword", "斧", "Axe",
      "メイス", "Mace", "セプター", "Sceptre", "スタッフ", "Staff", "ダガー", "Dagger",
      "クロー", "Claw", "釣り竿", "Fishing Rod"), "weapon"),
    (("防具", "Armour", "ヘルメット", "Helmet", "グローブ", "Gloves", "ブーツ", "Boots",
      "鎧", "Body Armour", "盾", "Shield"), "armour"),
    (("アクセサリー", "Accessory", "指輪", "Ring", "アミュレット", "Amulet", "ベルト", "Belt"), "accessory"),
    (("ジェム", "Gem"), "gem"),
    (("マップ", "Map"), "map"),
    (("設計図", "Blueprint"), "heist_blueprint"),
    (("契約書", "Contract"), "heist_contract"),
    (("招待状", "Invitation"), "invitation"),
    (("メモリー", "Memory Line", "Atlas Memory"), "memory_line"),
    (("ログブック", "Logbook"), "expedition_logbook"),
    (("フラスコ", "Flask"), "flask"),
    (("カレンシー", "Currency"), "currency"),
    (("カード", "Divination Card"), "divination_card"),
)
_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")
_JAPANESE_TEXT = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_MODIFIER_HEADER = re.compile(r"^\{(?P<body>.*)\}$")
_MODIFIER_KINDS = (
    (("Crafted", "クラフト"), "crafted"),
    (("Fractured", "フラクチャー"), "fractured"),
    (("Desecrated", "冒涜"), "desecrated"),
    (("Prefix", "プレフィックス"), "prefix"),
    (("Suffix", "サフィックス"), "suffix"),
    (("Implicit", "暗黙"), "implicit"),
    (("Enchant", "エンチャント"), "enchant"),
)


def _sections(text: str) -> list[list[str]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    sections: list[list[str]] = [[]]
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if line == "--------":
            if sections[-1]:
                sections.append([])
        elif line:
            sections[-1].append(line)
    return [section for section in sections if section]


def _split_label(line: str) -> tuple[str, str] | None:
    if ": " in line:
        return tuple(line.split(": ", 1))
    if "：" in line:
        return tuple(line.split("：", 1))
    if line.endswith(":"):
        return line[:-1], ""
    return None


def _category(item_class: str) -> str:
    for words, category in _CATEGORY_WORDS:
        if any(word.lower() in item_class.lower() for word in words):
            return category
    return "unknown"


def _numbers(text: str) -> tuple[float, ...]:
    values = []
    for match in _NUMBER.findall(text.replace(",", "")):
        values.append(float(match))
    return tuple(values)


def _roll_bounds(text: str) -> tuple[float | None, float | None]:
    matches = re.findall(r"\(\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*\)", text)
    if not matches:
        return None, None
    return min(float(low) for low, _ in matches), max(float(high) for _, high in matches)


def _modifier_header_kind(line: str) -> str | None:
    """詳細コピーの波括弧付きMod見出しを日英両方で分類する。"""
    match = _MODIFIER_HEADER.match(line)
    if not match:
        return None
    body = match.group("body").lower()
    for labels, kind in _MODIFIER_KINDS:
        if any(label.lower() in body for label in labels):
            return kind
    return None


def _modifier_header_details(line: str) -> tuple[str, int | None, str | None, str | None] | None:
    kind = _modifier_header_kind(line)
    if kind is None:
        return None
    body = _MODIFIER_HEADER.match(line).group("body")
    tier_match = re.search(r"(?:Tier|ティア)\s*:\s*(\d+)", body, re.IGNORECASE)
    lowered = body.lower()
    if "prefix" in lowered or "プレフィックス" in body:
        affix = "prefix"
    elif "suffix" in lowered or "サフィックス" in body:
        affix = "suffix"
    else:
        affix = kind if kind in {"prefix", "suffix"} else None
    generation = next((value for labels, value in (
        (("crusader", "クルセーダー"), "crusader"), (("warlord", "ウォーロード"), "warlord"),
        (("hunter", "ハンター"), "hunter"), (("redeemer", "リディーマー"), "redeemer"),
        (("shaper", "シェイパー"), "shaper"), (("elder", "エルダー"), "elder"),
        (("fractured", "フラクチャー"), "fractured"), (("crafted", "クラフト", "製作"), "crafted"),
        (("enchant", "エンチャント"), "enchant"),
    ) if any(label in lowered or label in body for label in labels)), None)
    return kind, int(tier_match.group(1)) if tier_match else None, affix, generation


def _localized_name_lines(name_lines: list[str], rarity: str) -> tuple[str, str]:
    """日英両方の名前がある場合は、日本語表示用の組を優先する。"""
    separate_base = rarity.lower() in {"rare", "unique", "レア", "ユニーク"}
    if separate_base:
        japanese_lines = [line for line in name_lines if _JAPANESE_TEXT.search(line)]
        selected = japanese_lines if len(japanese_lines) >= 2 else name_lines
        if len(selected) == 1:
            # 未鑑定ユニークは固有名が表示されず、ベース名1行だけの場合がある。
            return selected[0], selected[0]
        return selected[0], selected[1]
    japanese_lines = [line for line in name_lines if _JAPANESE_TEXT.search(line)]
    selected = japanese_lines or name_lines
    return selected[0], selected[-1]


def parse_item_text(text: str) -> ParsedItem:
    """PoEの詳細コピー文を、価格検索に渡せる最小構造へ変換する。"""
    if not text or not text.strip():
        raise ItemParseError("アイテム文章が空です。")
    sections = _sections(text)
    if not sections:
        raise ItemParseError("アイテム文章を読み取れませんでした。")

    header: dict[str, str] = {}
    name_lines: list[str] = []
    for line in sections[0]:
        pair = _split_label(line)
        key = _LABELS.get(pair[0]) if pair else None
        if key:
            header[key] = pair[1]
        else:
            name_lines.append(line)
    if not header.get("rarity") or not name_lines:
        raise ItemParseError("レアリティまたはアイテム名を取得できませんでした。")

    rarity = header["rarity"]
    # Rare/Uniqueは固有名とベースを分ける。日英併記なら日本語の組を表示に使う。
    name, base_type = _localized_name_lines(name_lines, rarity)
    properties: dict[str, str] = {}
    flags: list[str] = []
    modifiers: list[ItemModifier] = []
    item_level = None

    reached_item_level = False
    current_header_kind: str | None = None
    current_header_tier: int | None = None
    current_header_affix: str | None = None
    current_header_generation: str | None = None
    current_modifier_group = 0
    for section in sections[1:]:
        # 装備性能・装備条件など、item levelより前の区画は検索Modではない。
        metadata_section = not reached_item_level
        for line in section:
            if line in _FLAG_LINES:
                flags.append(_FLAG_LINES[line])
                continue
            pair = _split_label(line)
            if pair:
                label, value = pair
                mapped = _LABELS.get(label)
                if mapped == "item_level":
                    level_match = re.search(r"\d+", value)
                    item_level = int(level_match.group()) if level_match else None
                    reached_item_level = True
                    continue
                if label in _PROPERTY_LABELS or metadata_section:
                    properties[label] = value
                    continue
            if metadata_section:
                # 「Bow」「両手剣」のような値を持たない性能区画の見出しも保持する。
                properties.setdefault(line, "")
                continue
            header_details = _modifier_header_details(line)
            if header_details:
                # 1つのModが複数行の効果を持つ場合がある。
                # 次の見出しまで同じPrefix/Suffix種別を維持する。
                (current_header_kind, current_header_tier, current_header_affix,
                 current_header_generation) = header_details
                current_modifier_group += 1
                continue
            lowered = line.lower()
            if "(implicit)" in lowered or "（暗黙）" in line:
                kind = "implicit"
            elif "(enchant)" in lowered or "（エンチャント）" in line:
                kind = "enchant"
            elif "(crafted)" in lowered or "（クラフト）" in line:
                kind = "crafted"
            else:
                kind = current_header_kind or "explicit"
            from_header = kind == current_header_kind
            metadata, confidence = default_metadata_index().match(line, kind)
            roll_min, roll_max = _roll_bounds(line)
            inferred_affix = None
            if metadata and kind == "crafted":
                generations = {tier.generation for tier in metadata.tiers
                               if tier.generation in {"prefix", "suffix"}}
                if len(generations) == 1:
                    inferred_affix = generations.pop()
            modifiers.append(ItemModifier(
                text=line, values=_numbers(line), kind=kind,
                tier=current_header_tier if from_header else None,
                affix=current_header_affix if from_header else (
                    kind if kind in {"prefix", "suffix"} else inferred_affix
                ),
                group=current_modifier_group if from_header else None,
                ref=metadata.ref if metadata else None,
                stat_id=metadata.stat_id if metadata else None,
                confidence=confidence,
                roll_min=roll_min,
                roll_max=roll_max,
                better=metadata.better if metadata else None,
                inverted=metadata.inverted if metadata else False,
                generation=current_header_generation if from_header else kind,
            ))

    return ParsedItem(
        item_class=header.get("item_class", ""), rarity=rarity, name=name,
        base_type=base_type, category=_category(header.get("item_class", "")),
        item_level=item_level, properties=properties, modifiers=tuple(modifiers),
        flags=tuple(dict.fromkeys(flags)), raw_text=text,
    )
