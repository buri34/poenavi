from __future__ import annotations

import re

from .models import ItemModifier, ParsedItem
from .metadata import default_metadata_index, gem_metadata, normalize_stat_text


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
    "メモリーの糸", "記憶の糸", "メモリーストランド", "Memory Strands",
    "ジェムレベル", "Gem Level", "レベル", "Level", "経験値", "Experience", "筋力", "Strength",
    "器用さ", "Dexterity", "知性", "Intelligence", "Spirit", "スピリット",
    "ブロック率", "Chance to Block", "移動速度", "Movement Speed",
    "ルーンソケット", "Rune Sockets",
    "アイテム数量", "Item Quantity", "アイテムレアリティ", "Item Rarity",
    "モンスターパックサイズ", "Monster Pack Size", "モンスターレベル", "Monster Level",
    "エリアレベル", "Area Level",
    "情報を聞いた区画", "情報を聞いた区画数", "Wings Revealed",
    "合計区画数", "Total Wings",
    "依頼書目標の価値", "ハイスト目標", "Heist Target",
    "必要なジョブ", "必要ジョブ", "Requires",
    "決心", "Resolve", "決心の最大値", "Maximum Resolve", "勇気", "Inspiration",
    "アウレウス", "Aureus", "マップ完了報酬", "Map Completion Reward",
    "追加マップ", "More Maps", "追加スカラベ", "More Scarabs",
    "追加カレンシー", "More Currency", "追加占いカード", "More Divination Cards",
}
_FLAG_LINES = {
    "未鑑定": "unidentified", "Unidentified": "unidentified",
    "コラプト状態": "corrupted", "Corrupted": "corrupted",
    "ミラー品": "mirrored", "ミラー状態": "mirrored", "Mirrored": "mirrored",
    "分割": "split", "スプリット": "split", "Split": "split",
    "Synthesised Item": "synthesised", "Synthesised": "synthesised",
    "シンセサイズアイテム": "synthesised", "シンセサイズ済みアイテム": "synthesised",
    "シンセシスアイテム": "synthesised",
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
    "Searing Exarch Item": "searing_item", "シアリング・エグザークアイテム": "searing_item",
    "Eater of Worlds Item": "tangled_item", "イーター・オブ・ワールズアイテム": "tangled_item",
    "Veiled": "veiled", "ヴェール状態": "veiled", "ヴェール済み": "veiled",
    "Fractured Item": "fractured", "フラクチャーアイテム": "fractured",
    "Unmodifiable": "unmodifiable", "変更不可": "unmodifiable",
}
_CATEGORY_WORDS = (
    (("Captured Beast", "捕獲したビースト", "捕獲済みビースト"), "captured_beast"),
    (("武器", "Weapon", "弓", "Bow", "ワンド", "Wand", "剣", "Sword", "斧", "Axe",
      "メイス", "Mace", "セプター", "Sceptre", "スタッフ", "Staff", "ダガー", "Dagger",
      "クロー", "Claw", "釣り竿", "Fishing Rod"), "weapon"),
    (("防具", "Armour", "ヘルメット", "Helmet", "兜", "グローブ", "Gloves", "手袋",
      "ブーツ", "Boots", "靴", "鎧", "胴体防具", "Body Armour", "盾", "Shield"), "armour"),
    (("アクセサリー", "Accessory", "指輪", "Ring", "アミュレット", "Amulet", "ベルト", "Belt",
      "矢筒", "Quiver"), "accessory"),
    (("クラスタージュエル", "Cluster Jewel"), "cluster_jewel"),
    (("アビスジュエル", "Abyss Jewel"), "abyss_jewel"),
    (("ジュエル", "Jewel"), "jewel"),
    (("ジェム", "Gem"), "gem"),
    (("マップ", "Map"), "map"),
    (("設計図", "計画書", "Blueprint"), "heist_blueprint"),
    (("契約書", "依頼書", "Contract"), "heist_contract"),
    (("招待状", "Invitation"), "invitation"),
    (("メモリー", "Memory Line", "Atlas Memory"), "memory_line"),
    (("ログブック", "Logbook"), "expedition_logbook"),
    (("フラスコ", "Flask"), "flask"),
    (("ティンクチャー", "チンキ", "Tincture"), "tincture"),
    (("強盗団装備", "Heist Equipment", "ブローチ", "Brooch", "道具", "Heist Tool",
      "クローク", "Heist Cloak", "トリンケット", "Trinket"), "heist_equipment"),
    (("インカージョンアイテム", "Incursion Item"), "incursion_item"),
    (("サンクタムレリック", "Sanctum Relic"), "sanctum_relic"),
    (("チャーム", "Charm"), "charm"),
    (("アイドル", "Idol"), "idol"),
    (("グラフト", "Graft"), "graft"),
    (("センチネル", "Sentinel"), "sentinel"),
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
    (("Veiled", "ヴェール"), "veiled"),
    (("Unique Mod", "Unique Modifier", "ユニークモッド", "ユニーク モディファイア"), "explicit"),
    (("Monster Mod", "モンスターモッド"), "explicit"),
)
_UNSCALABLE_VALUE_SUFFIX = re.compile(
    r"\s*(?:[-—–]\s*)?(?:スケールできない値|Unscalable Value)\s*$",
    re.IGNORECASE,
)
_MUTATED_SUFFIX = re.compile(r"\s*[（(]mutated[）)]\s*$", re.IGNORECASE)
_FOULBORN_NAME_PREFIX = re.compile(
    r"^(?:Foulborn|ファウルボーン)\s+(.+)$",
    re.IGNORECASE,
)
_GLOSSARY_HELP_LINE = re.compile(
    r"^[（(]\s*[^()（）:：\r\n]{1,80}\s*[:：].*[）)]$",
)
_JEWEL_HELP_LINES = {
    "パッシブツリーで割り当てられたジュエルソケットにはめる。右クリックしてソケットから取り外すことができる。",
    "パッシブツリーで割り当てられたジュエルソケット(大)または(中)にはめる。追加されたパッシブは他の半径を持つジュエルと相互作用しない。右クリックしてソケットから取り外すことができる。",
    "Place into an allocated Jewel Socket on the Passive Skill Tree. Right click to remove from the Socket.",
    "アイテムのアビスソケットまたはパッシブツリーで割り当てられたジュエルソケットにはめる。右クリックしてソケットから取り外すことができる。",
}
_MODIFIER_HELP_LINES = {
    "(アーマー、回避力、エナジーシールドは標準的な防御力である)",
    "(Armour, Evasion Rating and Energy Shield are the standard Defences)",
}
_INLINE_MODIFIER_MARKER = re.compile(
    r"[（(](?:implicit|暗黙|enchant|エンチャント|crafted|クラフト|fractured|フラクチャー)[）)]\s*$",
    re.IGNORECASE,
)
_PARENTHETICAL_LINE = re.compile(r"^[（(].*[）)]$")
_FOIL_VARIANT_LINE = re.compile(r"^(?:Foil|フォイル)\s*[（(].+[）)]$")
_CATEGORY_HELP_LINES = {
    "flask": {
        "右クリックして飲む。腰につけているときだけチャージを貯めることができる。モンスターを倒すことで充填される。",
        "Right click to drink. Can only hold charges while in belt. Refills as you kill monsters.",
    },
    "map": {
        "自身のマップデバイスで使用することでこのティアまたはそれよりティアの低いマップに移動する。マップは一度のみ使用できる。",
        "Travel to this Map by using it in a personal Map Device. Maps can only be used once.",
        "自身のマップデバイスでこのアイテムを使用してこのマップに移動する。一度のみ使用できる。マップ内のすべてレアおよびユニークモンスターを含む全モンスターの90%を倒すことで報酬を獲得できる。生成されるエリアはアトラス パッシブ ツリーの影響を受けず、マップ デバイスを介して強化されない。",
    },
    "heist_blueprint": {
        "ローグハーバーにいる特定のNPCに話しかけ、諜報を使って追加の区画や部屋の情報を聞くことができます。この計画書をアーディアに渡して、グランドハイストに着手してください。",
    },
    "expedition_logbook": {
        "このアイテムをダニグに渡し、自身の隠れ家でエクスペディションへのポータルを開く。",
        "Take this item to Dannig in your Hideout to open portals to an Expedition.",
    },
    "tincture": {
        "右クリックで活性化する。ベルトある一度に適用できるチンキは1個のみ。マナ燃焼によりスタックごとに毎秒最大マナの1%が失われる。手動で不活性化することができ、マナが0に達すると自動的に不活性化される。",
    },
    "captured_beast": {
        "右クリックしてこのモンスターを怪獣園に追加する。",
        "Right-click to add this to your bestiary.",
    },
}

# Replica固有Modなど、公式Trade statは「増加」を正方向として持つ一方、
# 詳細コピーでは同じstatが「減少」として出るものを明示的に正規化する。
# 広範な語句置換は別statの誤照合を招くため、確認済みテンプレートだけを扱う。
_DIRECTIONAL_STAT_ALIASES = {
    normalize_stat_text("アイテムおよびジェムの要求能力値が#%減少する"):
        "アイテムおよびジェムの要求能力値が#%増加する",
    normalize_stat_text("持続時間が#%減少する"):
        "持続時間が#%増加する",
    normalize_stat_text("左の指輪スロット: 受けている呪いの効果が#%減少する"):
        "左の指輪スロット: 受けている呪いの効果が#%増加する",
    normalize_stat_text("倒した敵1体ごとに#のマナを失う"):
        "倒した敵1体ごとに#のマナを獲得する",
}
# 固定文言中にも数値がある場合、検索値に対応する数値の位置を明示する。
# 「敵1体」の1ではなく、その後のMana値を使う。
_DIRECTIONAL_STAT_VALUE_INDEX = {
    normalize_stat_text("倒した敵1体ごとに#のマナを失う"): 1,
}
_JEWEL_CATEGORIES = {"jewel", "abyss_jewel", "cluster_jewel"}
_MAP_TIER_IN_NAME = re.compile(
    r"(?:\bMap|マップ)\s*[（(]\s*(?:Tier|ティア)\s*[:：]?\s*(\d+)\s*[）)]",
    re.IGNORECASE,
)
_LOGBOOK_FACTIONS = {
    "Black Scythe Mercenaries": ("Has Logbook Faction: Black Scythe Mercenaries", "pseudo.pseudo_logbook_faction_mercenaries"),
    "黒い鎌の傭兵団": ("Has Logbook Faction: Black Scythe Mercenaries", "pseudo.pseudo_logbook_faction_mercenaries"),
    "Druids of the Broken Circle": ("Has Logbook Faction: Druids of the Broken Circle", "pseudo.pseudo_logbook_faction_druids"),
    "壊れた環の祭司": ("Has Logbook Faction: Druids of the Broken Circle", "pseudo.pseudo_logbook_faction_druids"),
    "断たれた円環のドルイド": ("Has Logbook Faction: Druids of the Broken Circle", "pseudo.pseudo_logbook_faction_druids"),
    "Knights of the Sun": ("Has Logbook Faction: Knights of the Sun", "pseudo.pseudo_logbook_faction_knights"),
    "太陽の騎士団": ("Has Logbook Faction: Knights of the Sun", "pseudo.pseudo_logbook_faction_knights"),
    "Order of the Chalice": ("Has Logbook Faction: Order of the Chalice", "pseudo.pseudo_logbook_faction_order"),
    "杯の教団": ("Has Logbook Faction: Order of the Chalice", "pseudo.pseudo_logbook_faction_order"),
}


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


def _category_with_help_text(item_class: str, text: str) -> str:
    lowered = text.casefold()
    if ("right-click to add this to your bestiary" in lowered or
            "ビースト図鑑に追加" in text or "怪獣園に追加" in text):
        return "captured_beast"
    return _category(item_class)


def _category_with_item_identity(
    item_class: str, name: str, base_type: str, text: str,
) -> str:
    category = _category_with_help_text(item_class, text)
    identity = f"{name}\n{base_type}".casefold()
    if category == "jewel" and (
        "cluster jewel" in identity or "クラスタージュエル" in identity
    ):
        return "cluster_jewel"
    return category


def _numbers(text: str) -> tuple[float, ...]:
    values = []
    for match in _NUMBER.findall(text.replace(",", "")):
        values.append(float(match))
    return tuple(values)


def _normalized_modifier_line(line: str, item_category: str | None = None) -> str | None:
    """詳細コピー固有の注釈を除き、検索対象となるMod本文だけを返す。"""
    if item_category in _JEWEL_CATEGORIES and line.strip() in _JEWEL_HELP_LINES:
        return None
    if _GLOSSARY_HELP_LINE.fullmatch(line):
        return None
    if line.strip() in _MODIFIER_HELP_LINES:
        return None
    if line.strip() in _CATEGORY_HELP_LINES.get(item_category or "", set()):
        return None
    normalized = _MUTATED_SUFFIX.sub("", line)
    normalized = _UNSCALABLE_VALUE_SUFFIX.sub("", normalized).rstrip()
    return normalized or None


def _roll_bounds(text: str) -> tuple[float | None, float | None]:
    matches = re.findall(r"\(\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*\)", text)
    if not matches:
        return None, None
    endpoints = [float(value) for bounds in matches for value in bounds]
    return min(endpoints), max(endpoints)


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


def _section_has_modifier_evidence(section: list[str]) -> bool:
    """詳細コピーでMod区画と断定できる構造上の目印を返す。"""
    return any(
        _modifier_header_details(line) is not None
        or _INLINE_MODIFIER_MARKER.search(line) is not None
        for line in section
    )


def _modifier_header_details(
    line: str,
) -> tuple[str, int | None, str | None, str | None, str | None] | None:
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
        (("corrupted implicit", "コラプト暗黙"), "corrupted"),
        (("foulborn", "ファウルボーン"), "foulborn"),
        (("monster mod", "モンスターモッド"), "monster"),
        (("crusader", "クルセーダー"), "crusader"), (("warlord", "ウォーロード"), "warlord"),
        (("hunter", "ハンター"), "hunter"), (("redeemer", "リディーマー"), "redeemer"),
        (("shaper", "シェイパー"), "shaper"), (("elder", "エルダー"), "elder"),
        (("fractured", "フラクチャー"), "fractured"), (("crafted", "クラフト", "製作"), "crafted"),
        (("enchant", "エンチャント"), "enchant"),
        (("veiled", "ヴェール"), "veiled"),
        (("eldritch", "エルドリッチ", "searing exarch", "シアリング・エグザーク",
          "eater of worlds", "イーター・オブ・ワールズ"), "eldritch"),
        (("desecrated", "冒涜"), "desecrated"),
        (("incursion", "インカージョン"), "incursion"),
        (("delve", "デルヴ"), "delve"),
    ) if any(label in lowered or label in body for label in labels)), None)
    name_match = re.search(r'"([^"]*)"|「([^」]*)」', body)
    name = (
        next((value for value in name_match.groups() if value is not None), None)
        if name_match else None
    )
    return kind, int(tier_match.group(1)) if tier_match else None, affix, generation, name


def _is_unique_flavour_section(
    section: list[str], rarity: str, item_category: str, has_modifiers: bool,
) -> bool:
    """Unique末尾のフレーバーテキスト区画を検索Modから除外する。"""
    if rarity.casefold() not in {"unique", "ユニーク"} or not has_modifiers:
        return False
    if any(_modifier_header_details(line) for line in section):
        return False
    if any(line in _FLAG_LINES for line in section):
        return False
    candidates = [
        normalized
        for line in section
        if not _split_label(line)
        for normalized in [_normalized_modifier_line(line, item_category)]
        if normalized is not None
    ]
    if not candidates:
        return False
    # 通常コピーでは波括弧付き見出しがないため、公式Modへ解決できる区画は残す。
    return not any(
        default_metadata_index().match_with_option(text, "explicit")[0]
        for text in candidates
    )


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


def _vaal_gem_identity(sections: list[list[str]]) -> str | None:
    """Vaalジェム詳細コピー内の独立したVaalスキル名を返す。

    Vaalジェムのヘッダーは通常スキル名（例: Molten Strike）のため、
    後半セクションの `Vaal Molten Strike` を公式Gemメタデータで検証する。
    """
    for section in sections[1:]:
        if len(section) != 1:
            continue
        candidate = section[0].strip()
        if candidate.casefold().startswith("vaal ") and gem_metadata(candidate).get("vaal"):
            return candidate
    return None


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
    current_header_name: str | None = None
    current_modifier_group = 0
    item_category = _category_with_item_identity(
        header.get("item_class", ""), name, base_type, text,
    )
    if item_category == "gem":
        vaal_identity = _vaal_gem_identity(sections)
        if vaal_identity:
            name = base_type = vaal_identity
    detailed_copy = any(
        _modifier_header_details(line) is not None
        for section in sections[1:]
        for line in section
    )
    for section_index, section in enumerate(sections[1:], start=1):
        # Mod見出しの効果範囲は同一区画内だけ。次の区切り以降へ持ち越さない。
        current_header_kind = None
        current_header_tier = None
        current_header_affix = None
        current_header_generation = None
        current_header_name = None
        if reached_item_level and _is_unique_flavour_section(
            section, rarity, item_category, bool(modifiers),
        ):
            continue
        section_has_modifier_evidence = _section_has_modifier_evidence(section)
        logbook_area_section = (
            item_category == "expedition_logbook"
            and any(line in _LOGBOOK_FACTIONS for line in section)
        )
        # 装備性能・装備条件など、item levelより前の区画は検索Modではない。
        metadata_section = not reached_item_level
        for line in section:
            if line in _FLAG_LINES:
                flags.append(_FLAG_LINES[line])
                continue
            if _FOIL_VARIANT_LINE.fullmatch(line):
                flags.append("foil")
                properties["Foil Variant"] = line
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
                if (item_category == "gem"
                        and label in {"ジェムレベル", "Gem Level", "レベル", "Level"}):
                    # Gemコピーには本体Levelの後に、装備条件と次Level条件の
                    # `Level`が再登場する。最初の値だけを検索用に固定する。
                    properties.setdefault("ジェムレベル", value)
                if label in _PROPERTY_LABELS or metadata_section:
                    properties[label] = value
                    if (label in {"エリアレベル", "Area Level"}
                            and item_category in {"expedition_logbook", "incursion_item"}):
                        reached_item_level = True
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
                 current_header_generation, current_header_name) = header_details
                current_modifier_group += 1
                continue
            # 詳細コピーでは構造上Modと確認できる区画だけを解析する。
            # 通常コピーはMod見出しがないため、従来のメタデータ照合経路を維持する。
            if detailed_copy and not section_has_modifier_evidence:
                continue
            is_mutated = _MUTATED_SUFFIX.search(line) is not None
            line = _normalized_modifier_line(line, item_category)
            if line is None:
                continue
            if logbook_area_section and line == section[0] and line not in _LOGBOOK_FACTIONS:
                # Logbookの各区画先頭はエリア名であり、検索Modではない。
                continue
            if item_category == "expedition_logbook" and line in _LOGBOOK_FACTIONS:
                ref, stat_id = _LOGBOOK_FACTIONS[line]
                modifiers.append(ItemModifier(
                    text=line, kind="pseudo", group=section_index, ref=ref,
                    stat_id=stat_id, confidence=1.0, generation="pseudo",
                ))
                continue
            lowered = line.lower()
            is_veiled_placeholder = (
                lowered in {"veiled prefix", "veiled suffix"}
                or (
                    "ヴェール" in line
                    and ("プレフィックス" in line or "サフィックス" in line)
                )
            )
            if "(implicit)" in lowered or "（暗黙）" in line:
                kind = "implicit"
            elif "(enchant)" in lowered or "（エンチャント）" in line:
                kind = "enchant"
            elif "(crafted)" in lowered or "（クラフト）" in line:
                kind = "crafted"
            elif ("(veiled)" in lowered or "（ヴェール）" in line
                  or is_veiled_placeholder):
                kind = "veiled"
            elif current_header_generation == "veiled":
                kind = "veiled"
            else:
                kind = current_header_kind or "explicit"
            from_header = kind == current_header_kind or (
                kind == "veiled" and current_header_kind in {"prefix", "suffix", "veiled"}
            )
            metadata_text = (
                current_header_name if kind == "veiled" and current_header_name else line
            )
            metadata, option, confidence = default_metadata_index().match_with_option(
                metadata_text, kind,
            )
            direction_inverted = False
            direction_alias_key = None
            if metadata is None:
                direction_alias_key = normalize_stat_text(metadata_text)
                alias = _DIRECTIONAL_STAT_ALIASES.get(direction_alias_key)
                if alias:
                    metadata, option, confidence = default_metadata_index().match_with_option(
                        alias, kind,
                    )
                    direction_inverted = metadata is not None
            if metadata is None and kind == "veiled" and current_header_name:
                metadata, confidence = default_metadata_index().match_ref(
                    current_header_name, kind,
                )
            if metadata is None and detailed_copy and _PARENTHETICAL_LINE.fullmatch(line):
                # 詳細コピーでMod直後に付く用語説明・上限説明は検索条件ではない。
                continue
            roll_min, roll_max = _roll_bounds(line)
            inferred_affix = None
            if metadata and kind == "crafted":
                generations = {tier.generation for tier in metadata.tiers
                               if tier.generation in {"prefix", "suffix"}}
                if len(generations) == 1:
                    inferred_affix = generations.pop()
            values = _numbers(line)
            value_index = _DIRECTIONAL_STAT_VALUE_INDEX.get(direction_alias_key)
            if value_index is not None and len(values) > value_index:
                values = (values[value_index],)
            modifiers.append(ItemModifier(
                text=line, values=values, kind=kind,
                tier=current_header_tier if from_header else None,
                affix=current_header_affix if from_header else (
                    kind if kind in {"prefix", "suffix"} else inferred_affix
                ),
                group=(current_modifier_group if from_header else
                       section_index if item_category == "expedition_logbook" else None),
                ref=metadata.ref if metadata else None,
                stat_id=metadata.stat_id if metadata else None,
                confidence=confidence,
                roll_min=roll_min,
                roll_max=roll_max,
                better=metadata.better if metadata else None,
                inverted=(metadata.inverted ^ direction_inverted) if metadata else False,
                generation=(kind if kind == "veiled" else current_header_generation)
                if from_header else ("foulborn" if is_mutated else kind),
                option_value=option.value if option else None,
                option_text=option.japanese if option else None,
                oils=option.oils if option else (),
                decimal=metadata.decimal if metadata else False,
            ))

    # 日本語クライアントの詳細コピーでは、Map Tierが独立したプロパティ行ではなく
    # 名前行の `Map (Tier 16)` として出力される場合がある。
    if item_category == "map" and not any(
        label in properties for label in ("マップティア", "Map Tier")
    ):
        tier_match = _MAP_TIER_IN_NAME.search("\n".join(name_lines))
        if tier_match:
            properties["Map Tier"] = tier_match.group(1)

    if (
        "foulborn" in f"{name}\n{base_type}".casefold()
        or "ファウルボーン" in f"{name}\n{base_type}"
        or "ファウルボーンユニークモッド" in text
        or "Foulborn Unique Mod" in text
    ):
        flags.append("foulborn")
        # Awakenedと同様、Foulbornはユニーク名そのものではなく状態として扱う。
        # Trade APIには通常のユニーク名を送り、Foulborn Modで個体を絞る。
        if rarity.casefold() in {"unique", "ユニーク"} and "unidentified" not in flags:
            foulborn_name = _FOULBORN_NAME_PREFIX.fullmatch(name.strip())
            if foulborn_name:
                name = foulborn_name.group(1).strip()

    return ParsedItem(
        item_class=header.get("item_class", ""), rarity=rarity, name=name,
        base_type=base_type, category=item_category,
        item_level=item_level, properties=properties, modifiers=tuple(modifiers),
        flags=tuple(dict.fromkeys(flags + (["veiled"] if any(
            modifier.kind == "veiled" or modifier.generation == "veiled"
            for modifier in modifiers
        ) else []))), raw_text=text,
    )
