from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
import re

from .models import ItemModifier, ParsedItem
from .metadata import (
    default_metadata_index,
    gem_metadata,
    multi_value_rule,
    normalize_stat_text,
)


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
    "エリアレベル", "Area Level", "死人の硫黄", "Dead Man's Sulphur",
    "情報を聞いた区画", "情報を聞いた区画数", "Wings Revealed",
    "合計区画数", "Total Wings",
    "依頼書目標の価値", "ハイスト目標", "Heist Target",
    "必要なジョブ", "必要ジョブ", "Requires",
    "決心", "Resolve", "決心の最大値", "Maximum Resolve", "勇気", "Inspiration",
    "アウレウス", "Aureus", "マップ完了報酬", "Map Completion Reward",
    "追加マップ", "マップ量が上昇", "More Maps",
    "追加スカラベ", "スカラベ量が上昇", "More Scarabs",
    "追加カレンシー", "カレンシー量が上昇", "More Currency",
    "追加占いカード", "占いカード増加", "More Divination Cards",
    "マップエリア", "Map Area",
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
    "シアリング・エグザークのアイテム": "searing_item",
    "Eater of Worlds Item": "tangled_item", "イーター・オブ・ワールズアイテム": "tangled_item",
    "イーター・オブ・ワールズのアイテム": "tangled_item",
    "Veiled": "veiled", "ヴェール状態": "veiled", "ヴェール済み": "veiled",
    "Fractured Item": "fractured", "フラクチャーアイテム": "fractured",
    "Unmodifiable": "unmodifiable", "変更不可": "unmodifiable",
}
_CATEGORY_WORDS = (
    (("Captured Beast", "捕獲したビースト", "捕獲済みビースト"), "captured_beast"),
    (("Corpse", "死体"), "corpse"),
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
    (("海図", "Chart"), "chart"),
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
    (("母胎ギフト",), "incubator"),
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
_VESTIGIAL_BASE_PREFIX = re.compile(
    r"^(?:Vestigial|痕跡)\s+(.+)$",
    re.IGNORECASE,
)
_ITEM_USABILITY_WARNING = re.compile(
    r"^(?:"
    r"このアイテムを使用できません。アイテムの効果は無視されます"
    r"|(?:You cannot use|This item cannot be used).*?"
    r"(?:stats?|effects?).*?ignored"
    r")\.?$",
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
_JAPANESE_RANDOM_SKILL_GEM_LEVEL = re.compile(
    r"^全ての(?P<skill>.+?)[（(][^()（）]+[）)]ジェムのレベル\s*[+]\d+(?:\.\d+)?$"
)
_JAPANESE_RANDOM_SUPPORT_GEM = re.compile(
    r"^(?P<prefix>ソケットされたジェムはレベル\d+(?:\.\d+)?(?:[（(][^()（）]+[）)])?)"
    r"(?P<support>[^()（）]+?)[（(][^()（）]+[）)](?P<suffix>によりサポートされる)$"
)
_FOIL_VARIANT_LINE = re.compile(r"^(?:Foil|フォイル)\s*[（(].+[）)]$")
_MERCENARY_WARRANT_NAMES = {
    "傭兵の召喚状", "Mercenary's Warrant", "Mercenary Warrant",
}
_MERCENARY_SUPPORT_TIER = re.compile(
    r"\s*[（(](?:ティア|Tier)\s*[:：]\s*(\d+)[）)]\s*$", re.IGNORECASE,
)
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
    "corpse": {
        "このアイテムを右クリックしてこの死体を生成する。",
        "Right click this item to create this corpse.",
    },
    "incubator": {
        "創生の樹でユニークアイテムに成長させられる",
        "このアイテムを創生の樹の割り当て済みのユニークアイテムの母胎に配置する。右クリックで創生の樹から取り除ける。",
    },
}

# 方向語だけでは扱えない不規則な反転表現を明示的に正規化する。
# 「減少する／低下する」はMetadataIndexの一意照合で汎用的に扱う。
_DIRECTIONAL_STAT_ALIASES = {
    # Doppelgänger's Guiseはゲーム内コピーが「低下する」だが、公式Tradeの
    # 対応statはmore Damage Takenの負数を受け取る「上昇する」表記である。
    normalize_stat_text(
        "正気状態の時に受ける物理ダメージおよび混沌ダメージが#%低下する"
    ): "正気状態の時に受ける物理ダメージおよび混沌ダメージが#%上昇する",
    normalize_stat_text("倒した敵1体ごとに#のマナを失う"):
        "倒した敵1体ごとに#のマナを獲得する",
    normalize_stat_text("プレイヤーの防御力が#%低下する"):
        "プレイヤーの防御力が#%上昇する",
    # 3.29日本語クライアントはArea Modを低下表記でコピーする一方、
    # 公式Trade statは同じStatを上昇表記で公開している。
    normalize_stat_text("全てのプレイヤーの命中力が#%低下する"):
        "全てのプレイヤーの命中力が#%上昇する",
    normalize_stat_text("全てのプレイヤーのクールダウン解消レートが#%低下する"):
        "全てのプレイヤーのクールダウン解消レートが#%上昇する",
    normalize_stat_text("プレイヤーは適用されるフラスコの効果が#%低下する"):
        "プレイヤーは適用されるフラスコの効果が#%上昇する",
}
_STAT_TEXT_ALIASES = {
    # Nightmare Mapは確率100%の一部Modから確率部分を省略して表示する。
    normalize_stat_text("レアモンスターはボラタイルコアを持つ"):
        "レアモンスターは100%の確率でボラタイルコアを持つ",
    normalize_stat_text("モンスターはヒット時にエンデュランスチャージを1個獲得する"):
        "モンスターはヒット時に100%の確率でエンデュランスチャージを1個獲得する",
    normalize_stat_text("モンスターはヒット時にパワーチャージを1個獲得する"):
        "モンスターはヒット時に100%の確率でパワーチャージを1個獲得する",
    normalize_stat_text("モンスターはヒット時にフレンジーチャージを1個獲得する"):
        "モンスターはヒット時に100%の確率でフレンジーチャージを1個獲得する",
    normalize_stat_text("モンスターはアタックによるヒット時に重傷を付与する"):
        "モンスターはアタックによるヒット時に100%の確率で重傷を付与する",
    normalize_stat_text("モンスターはヒット時に盲目を付与する"):
        "モンスターはヒット時に100%の確率で盲目を付与する",
    normalize_stat_text(
        "モンスターはヒット時にパワーチャージ、フレンジーチャージおよび"
        "エンデュランスチャージのスタックを盗む"
    ):
        "モンスターはヒット時に100%の確率でパワーチャージ、フレンジーチャージ"
        "およびエンデュランスチャージのスタックを盗む",
    # ゲーム内コピーでは公式Trade stat先頭の「マップで」が省略される。
    normalize_stat_text("マジックモンスターの数が#%増加する"):
        "マップでマジックモンスターの数が#%増加する",
    normalize_stat_text("レアモンスターの数が#%増加する"):
        "マップでレアモンスターの数が#%増加する",
    # 3.29日本語クライアントのMapコピーと公式Trade statで主語が異なる同一Mod。
    normalize_stat_text("ユニークボスのダメージが#%増加する"):
        "マップボスのダメージが#%増加する",
    normalize_stat_text("ユニークボスのライフが#%増加する"):
        "マップボスのライフが#%増加する",
    # 確率100%のHinder Modは、ゲーム内コピーで確率部分を省略する。
    normalize_stat_text("モンスターはスペルによるヒット時に阻害を付与する"):
        "モンスターはスペルによるヒット時に100%の確率で阻害を付与する",
    normalize_stat_text("それぞれのレアモンスターはモッドを追加で#個持つ"):
        "マップに出現するレアモンスターは追加のモッドを#個持つ",
    normalize_stat_text("モンスターはヒットを受けた時にエンデュランスチャージを1個獲得する"):
        "モンスターはヒットを受けた時に100%の確率でエンデュランスチャージを1個獲得する",
    normalize_stat_text("モンスターの投射物は地形と衝突した時に連鎖することができる"):
        "モンスターの投射物は地形と衝突した時に100%の確率で連鎖することができる",
    # 3.29日本語クライアントのMapコピーでは、公式Trade statにある
    # 所有格の「その」が省略される。
    normalize_stat_text("モンスターは物理ダメージの#%を追加混沌ダメージとして獲得する"):
        "モンスターはその物理ダメージの#%を追加混沌ダメージとして獲得する",
    # 詳細コピーと公式Trade statで語順が異なる同一Mod。
    normalize_stat_text("全てのプレイヤーはスペルダメージを抑制して防ぐダメージ割合が#%される"):
        "全てのプレイヤーはスペルダメージを抑制すると#%のダメージを防ぐ",
}
_STAT_VALUE_OVERRIDES = {
    normalize_stat_text("レアモンスターはボラタイルコアを持つ"): (100.0,),
    normalize_stat_text("モンスターはヒット時にエンデュランスチャージを1個獲得する"): (100.0,),
    normalize_stat_text("モンスターはヒット時にパワーチャージを1個獲得する"): (100.0,),
    normalize_stat_text("モンスターはヒット時にフレンジーチャージを1個獲得する"): (100.0,),
    normalize_stat_text("モンスターはアタックによるヒット時に重傷を付与する"): (100.0,),
    normalize_stat_text("モンスターはヒット時に盲目を付与する"): (100.0,),
    normalize_stat_text(
        "モンスターはヒット時にパワーチャージ、フレンジーチャージおよび"
        "エンデュランスチャージのスタックを盗む"
    ): (100.0,),
    normalize_stat_text("モンスターはスペルによるヒット時に阻害を付与する"): (100.0,),
    normalize_stat_text("モンスターはヒットを受けた時にエンデュランスチャージを1個獲得する"): (100.0,),
    normalize_stat_text("モンスターの投射物は地形と衝突した時に連鎖することができる"): (100.0,),
}
# 公式Tradeに同一文面のStatがないNightmare Map専用Mod。
# 確率付きWitheredとは危険度が異なるため、Map Checkでは別項目として扱う。
_MAP_CHECK_EXACT_STATS = {
    normalize_stat_text("モンスターによるヒット時に衰弱を2秒間付与する"): {
        "stat_id": "nightmare.stat_monsters_inflict_withered_on_hit",
        "ref": "Monsters inflict Withered for 2 seconds on Hit",
    },
}
# 固定文言中にも数値がある場合、検索値に対応する数値の位置を明示する。
# 「敵1体」の1ではなく、その後のMana値を使う。
_DIRECTIONAL_STAT_VALUE_INDEX = {
    normalize_stat_text("倒した敵1体ごとに#のマナを失う"): 1,
}
_SHIELD_STAT_ALIASES = {
    # 公式Tradeの日本語statは他のBlock statとの曖昧さ回避で「(盾)」を
    # 付けるが、ゲーム内の詳細コピーにはこの識別子が表示されない。
    normalize_stat_text("ブロック率 +#%"): "ブロック率 +#% (盾)",
}
_MULTILINE_STAT_TEXT_ALIASES = {
    # 3.29日本語クライアントの詳細コピーではHoly Armamentsが、
    # スキル由来の補足名を含む不規則な表記になる。
    "スケルトン召喚(アニメイトウェポン-ホーリーアーマメント)":
        "ホーリーアーマメント",
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
    # Scarabs share the broad Map Fragments / 「マップフラグメント」
    # item class with unrelated fragments.  Their item-name token is the stable
    # discriminator used by both the Trade and poe.ninja datasets.
    identity_lines = (name.strip().casefold(), base_type.strip().casefold())
    if category == "map" and any(
        re.search(r"\bscarab\b", value) or "スカラベ" in value
        for value in identity_lines
    ):
        return "scarab"
    # Pinnacle boss invitations use the broad "Misc Map Items" /
    # 「その他マップアイテム」class, so the class alone is classified as a map.
    # Their item identity is the reliable discriminator.
    if category == "map" and (
        "invitation" in identity or "招待状" in identity
    ):
        return "invitation"
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


def _values_for_matched_template(
    text: str, japanese_templates: tuple[str, ...],
) -> tuple[float, ...] | None:
    """公式Tradeテンプレートの#に対応する表示値だけを抽出する。"""
    normalized_text = normalize_stat_text(text)
    number = r"[-+]?\d[\d,]*(?:\.\d+)?"
    for template in japanese_templates:
        if normalize_stat_text(template) != normalized_text:
            continue
        parts = template.split("#")
        pattern = re.escape(parts[0])
        for suffix in parts[1:]:
            # 詳細コピーのroll範囲 ``99(85-99)`` は表示値に含めない。
            pattern += rf"({number})(?:\([^)]*\))?" + re.escape(suffix)
        match = re.fullmatch(pattern, text.strip())
        if match:
            return tuple(float(value.replace(",", "")) for value in match.groups())
    return None


def _is_added_damage_range_template(template: str) -> bool:
    """追加ダメージの下限・上限として平均できる文型を判定する。"""
    return "#から#" in template and "ダメージ" in template and "反射する" not in template


def _modifier_values(line: str, metadata) -> tuple[float, ...]:
    """安全に意味が確定している公式テンプレートだけ値解釈へ利用する。"""
    if metadata:
        template_values = _values_for_matched_template(line, metadata.japanese)
        if template_values is not None:
            rule = multi_value_rule(metadata.stat_id)
            if rule:
                operation = rule.get("operation")
                if operation == "blank":
                    return ()
                if operation == "first":
                    return (template_values[0],)
                if operation == "mean":
                    return (sum(template_values) / len(template_values),)
                if operation == "index":
                    return (template_values[int(rule["value_index"])],)
                if operation == "half_second":
                    return (template_values[1] / 2,)
            matching_templates = tuple(
                template for template in metadata.japanese
                if normalize_stat_text(template) == normalize_stat_text(line)
            )
            if any(template.count("#") == 1 for template in matching_templates):
                return template_values
            if len(template_values) == 2 and any(
                _is_added_damage_range_template(template)
                for template in matching_templates
            ):
                return ((template_values[0] + template_values[1]) / 2,)
    # その他の複数可変値は意味のレビューが済むまで従来挙動を維持する。
    return _numbers(line)


def _normalized_modifier_line(line: str, item_category: str | None = None) -> str | None:
    """詳細コピー固有の注釈を除き、検索対象となるMod本文だけを返す。"""
    if item_category == "incubator" and (
        "ハイヴブラッド" in line and "必要" in line
    ):
        # 必要量は母胎ギフトの成長コスト表示であり、検索Modではない。
        return None
    if item_category in _JEWEL_CATEGORIES:
        stripped = line.strip()
        if stripped in _JEWEL_HELP_LINES or (
            stripped.startswith(
                "パッシブツリーで割り当てられたジュエルソケット"
            )
            and "右クリックしてソケットから取り外す" in stripped
        ) or (
            stripped.casefold().startswith("place into an allocated jewel socket")
            and "right click to remove from the socket" in stripped.casefold()
        ):
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


def _combine_multiline_modifiers(
    modifiers: list[ItemModifier],
) -> list[ItemModifier]:
    """同じMod見出しに属する複数行を、公式の改行Stat単位へ戻す。"""
    result: list[ItemModifier] = []
    index = 0
    metadata_index = default_metadata_index()
    while index < len(modifiers):
        first = modifiers[index]
        if first.text.startswith("(") and first.group is not None:
            # 日本語クライアントの用語説明が表示幅により複数行へ折り返されても、
            # 各断片を検索Modや未解決警告として扱わない。
            help_end = index
            found_help_end = False
            while (
                help_end < len(modifiers)
                and modifiers[help_end].group == first.group
            ):
                if modifiers[help_end].text.endswith(")"):
                    index = help_end + 1
                    found_help_end = True
                    break
                help_end += 1
            if found_help_end:
                continue
        if first.kind == "enchant" and first.stat_id is None:
            # Cluster Jewelの基礎効果には、ゲーム内で複数行表示される一方、
            # 公式Tradeでは改行を含む1つのoptionとして定義されたものがある。
            # 未解決Enchantの連続範囲だけを公式メタデータへ照合する。
            group_end = index + 1
            while (
                group_end < len(modifiers)
                and modifiers[group_end].kind == "enchant"
                and modifiers[group_end].stat_id is None
            ):
                group_end += 1
            for size in range(group_end - index, 1, -1):
                group = modifiers[index:index + size]
                text = "\n".join(row.text for row in group)
                metadata, option, confidence = metadata_index.match_with_option(
                    text, first.kind,
                )
                if metadata is None:
                    continue
                result.append(replace(
                    first,
                    text=text,
                    values=tuple(value for row in group for value in row.values),
                    ref=metadata.ref,
                    stat_id=metadata.stat_id,
                    confidence=confidence,
                    option_value=option.value if option else None,
                    option_text=option.japanese if option else None,
                    oils=option.oils if option else (),
                    decimal=metadata.decimal,
                ))
                index += size
                break
            else:
                result.append(first)
                index += 1
            continue
        if first.group is None or first.kind not in {"prefix", "suffix", "explicit"}:
            result.append(first)
            index += 1
            continue
        group_end = index + 1
        while (
            group_end < len(modifiers)
            and modifiers[group_end].group == first.group
        ):
            group_end += 1
        matched = False
        for size in range(group_end - index, 1, -1):
            group = modifiers[index:index + size]
            text = "\n".join(row.text for row in group)
            metadata, option, confidence = metadata_index.match_with_option(
                text, first.kind,
            )
            if metadata is None:
                aliased_text = text
                for source, replacement in _MULTILINE_STAT_TEXT_ALIASES.items():
                    aliased_text = aliased_text.replace(source, replacement)
                if aliased_text != text:
                    metadata, option, confidence = metadata_index.match_with_option(
                        aliased_text, first.kind,
                    )
            if metadata is None:
                continue
            roll_mins = [row.roll_min for row in group if row.roll_min is not None]
            roll_maxes = [row.roll_max for row in group if row.roll_max is not None]
            result.append(replace(
                first,
                text=text,
                values=tuple(value for row in group for value in row.values),
                ref=metadata.ref,
                stat_id=metadata.stat_id,
                confidence=confidence,
                roll_min=min(roll_mins) if roll_mins else None,
                roll_max=max(roll_maxes) if roll_maxes else None,
                better=metadata.better * (-1 if metadata.negated else 1),
                inverted=metadata.inverted ^ metadata.negated,
                option_value=option.value if option else None,
                option_text=option.japanese if option else None,
                oils=option.oils if option else (),
                decimal=metadata.decimal,
            ))
            index += size
            matched = True
            break
        if not matched:
            result.append(first)
            index += 1
    return result


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
        (("vestigial implicit", "痕跡暗黙"), "vestigial"),
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
        (("synthesised", "synthesized", "シンセシス"), "synthesised"),
        (("desecrated", "冒涜"), "desecrated"),
        (("incursion", "インカージョン"), "incursion"),
        (("delve", "デルヴ"), "delve"),
        (("of the essence", "essences", "エッセンス"), "essence"),
        (("of infamy", "infamous", "悪名"), "infamous"),
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


@lru_cache(maxsize=1)
def _japanese_gem_names_to_english() -> dict[str, str]:
    from src.utils.gem_resolver import load_gem_names_ja

    return {
        localized.strip(): english.strip()
        for english, localized in load_gem_names_ja().items()
        if str(localized).strip()
    }


def _vaal_gem_identity(sections: list[list[str]]) -> str | None:
    """Vaalジェム詳細コピー内の独立したVaalスキル名を返す。

    Vaalジェムのヘッダーは通常スキル名（例: Molten Strike）のため、
    後半セクションの `Vaal Molten Strike` を公式Gemメタデータで検証する。
    """
    japanese_to_english = _japanese_gem_names_to_english()
    for section in sections[1:]:
        if len(section) != 1:
            continue
        candidate = section[0].strip()
        english_candidate = candidate
        if candidate.startswith("ヴァール"):
            normal_name = candidate[len("ヴァール"):].strip()
            normal_english = japanese_to_english.get(normal_name)
            english_candidate = f"Vaal {normal_english}" if normal_english else ""
        metadata = gem_metadata(english_candidate)
        if english_candidate.casefold().startswith("vaal ") and metadata.get("vaal"):
            return str(metadata.get("trade_type") or english_candidate)
    return None


def _parse_mercenary_warrant_sections(
    sections: list[list[str]],
) -> tuple[dict[str, str], tuple[ItemModifier, ...]]:
    """傭兵の召喚状のBuildとSkill/Supportを専用構造として読み取る。"""
    properties: dict[str, str] = {}
    modifiers: list[ItemModifier] = []
    build_seen = False
    for section_index, section in enumerate(sections[1:], start=1):
        section_rows: list[tuple[str, int | None]] = []
        for line in section:
            pair = _split_label(line)
            if pair and pair[0] in {"ビルド", "Build"}:
                properties["ビルド"] = pair[1]
                build_seen = True
                continue
            if pair and pair[0] in {"傭兵のレベル", "Mercenary Level"}:
                properties["傭兵のレベル"] = pair[1]
                continue
            if not build_seen:
                properties.setdefault("傭兵名", line)
                continue
            tier_match = _MERCENARY_SUPPORT_TIER.search(line)
            tier = int(tier_match.group(1)) if tier_match else None
            section_rows.append((line.strip(), tier))
        if not build_seen or not section_rows:
            continue
        if any("このアイテムを右クリック" in row[0] for row in section_rows):
            continue
        modifiers.extend(
            ItemModifier(
                text=line, kind="mercenary", tier=tier, group=section_index,
                confidence=1.0, generation="mercenary",
            )
            for line, tier in section_rows
        )
    return properties, tuple(modifiers)


def parse_item_text(text: str) -> ParsedItem:
    """PoEの詳細コピー文を、価格検索に渡せる最小構造へ変換する。"""
    if not text or not text.strip():
        raise ItemParseError("アイテム文章が空です。")
    sections = _sections(text)
    if not sections:
        raise ItemParseError("アイテム文章を読み取れませんでした。")

    header: dict[str, str] = {}
    name_lines: list[str] = []
    usability_warning_seen = False
    for line in sections[0]:
        pair = _split_label(line)
        key = _LABELS.get(pair[0]) if pair else None
        if key:
            header[key] = pair[1]
        elif _ITEM_USABILITY_WARNING.fullmatch(line.strip()):
            usability_warning_seen = True
        else:
            name_lines.append(line)
    if usability_warning_seen and not name_lines and len(sections) > 1:
        # 装備要求を満たさないアイテムは、警告文の直後にも区切り線が入り、
        # 通常はヘッダー内にある固有名／ベース名が次の区画へ押し出される。
        name_lines = [
            line for line in sections[1]
            if not _split_label(line)
            and not _ITEM_USABILITY_WARNING.fullmatch(line.strip())
        ]
        if name_lines:
            sections = [sections[0], *sections[2:]]
    if not header.get("rarity") or not name_lines:
        raise ItemParseError("レアリティまたはアイテム名を取得できませんでした。")

    rarity = header["rarity"]
    # Rare/Uniqueは固有名とベースを分ける。日英併記なら日本語の組を表示に使う。
    name, base_type = _localized_name_lines(name_lines, rarity)
    vestigial_base = (
        _VESTIGIAL_BASE_PREFIX.fullmatch(base_type.strip())
        if rarity.casefold() in {"unique", "ユニーク"} else None
    )
    if vestigial_base:
        # Awakened準拠: Vestigialは固有名ではなくベース名の接頭辞で表される。
        # 通常Unique名・通常ベースで検索し、専用Implicitと状態条件で個体を絞る。
        base_type = vestigial_base.group(1).strip()
    properties: dict[str, str] = {}
    flags: list[str] = ["vestigial"] if vestigial_base else []
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
    if name.strip() in _MERCENARY_WARRANT_NAMES:
        properties, warrant_modifiers = _parse_mercenary_warrant_sections(sections)
        if not properties.get("ビルド") or not warrant_modifiers:
            raise ItemParseError("傭兵の召喚状のビルドまたはスキルを取得できませんでした。")
        return ParsedItem(
            item_class=header.get("item_class", ""), rarity=rarity,
            name=name, base_type=base_type, category="invitation",
            properties=properties, modifiers=warrant_modifiers, raw_text=text,
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
    if item_category == "chart":
        for section in sections[1:]:
            labels = {
                pair[0] for line in section
                if (pair := _split_label(line)) is not None
            }
            if labels & {"エリアレベル", "Area Level"}:
                first = section[0].strip()
                if _split_label(first) is None:
                    properties["マップエリア"] = first
                break
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
            metadata, option, confidence = default_metadata_index().match_for_item_category(
                metadata_text, kind, item_category,
                current_header_generation if from_header else (
                    "foulborn" if is_mutated else None
                ),
            )
            if metadata is None and (
                "盾" in header.get("item_class", "")
                or "shield" in header.get("item_class", "").casefold()
            ):
                shield_alias = _SHIELD_STAT_ALIASES.get(
                    normalize_stat_text(metadata_text)
                )
                if shield_alias:
                    metadata, option, confidence = (
                        default_metadata_index().match_with_option(shield_alias, kind)
                    )
            direction_inverted = False
            direction_alias_key = None
            if metadata is None:
                direction_alias_key = normalize_stat_text(metadata_text)
                metadata, option, confidence = (
                    default_metadata_index().match_directional_inverse(
                        metadata_text, kind, item_category,
                        current_header_generation if from_header else (
                            "foulborn" if is_mutated else kind
                        ),
                    )
                )
                direction_inverted = metadata is not None
                alias = (
                    _DIRECTIONAL_STAT_ALIASES.get(direction_alias_key)
                    if metadata is None else None
                )
                if metadata is None and alias:
                    metadata, option, confidence = default_metadata_index().match_with_option(
                        alias, kind,
                    )
                    direction_inverted = metadata is not None
            stat_alias_key = normalize_stat_text(metadata_text)
            map_check_exact = (
                _MAP_CHECK_EXACT_STATS.get(stat_alias_key)
                if item_category == "map" else None
            )
            if metadata is None and kind == "explicit":
                random_skill = _JAPANESE_RANDOM_SKILL_GEM_LEVEL.fullmatch(
                    metadata_text
                )
                if random_skill:
                    # The Japanese Trade API exposes Dragonfang's per-skill
                    # indexable stats as ``全ての#ジェムのレベル +<skill>``.
                    # Detailed item copy uses the actual, differently ordered
                    # advanced form with a parenthesised skill-family marker.
                    # Awakened matches that advanced form; reshape it to the
                    # API matcher while retaining the selected skill identity.
                    api_matcher = (
                        "全ての#ジェムのレベル +"
                        f"{random_skill.group('skill')}"
                    )
                    metadata, option, confidence = (
                        default_metadata_index().match_with_option(
                            api_matcher, kind,
                        )
                    )
            if metadata is None and kind == "explicit" and name in {
                "禁断のシャコー帽", "禁断のシャコー帽（レプリカ）",
                "Forbidden Shako", "Replica Forbidden Shako",
            }:
                random_support = _JAPANESE_RANDOM_SUPPORT_GEM.fullmatch(
                    metadata_text
                )
                if random_support:
                    # 3.29日本語クライアントの詳細コピーは、選ばれたSupport名の
                    # 後ろへスキル系統の補足括弧を挿入する場合がある。公式Tradeと
                    # AwakenedのRandom Support statは括弧なしの定型文なので、
                    # Shakoの可変Support行に限って補足だけを除いて照合する。
                    api_matcher = (
                        f"{random_support.group('prefix')}"
                        f"{random_support.group('support')}"
                        f"{random_support.group('suffix')}"
                    )
                    metadata, option, confidence = (
                        default_metadata_index().match_with_option(
                            api_matcher, kind,
                        )
                    )
            if metadata is None and stat_alias_key in _STAT_TEXT_ALIASES:
                metadata, option, confidence = default_metadata_index().match_with_option(
                    _STAT_TEXT_ALIASES[stat_alias_key], kind,
                )
            if (
                metadata is None
                and kind == "desecrated"
                and item_category == "map"
            ):
                # Nightmare Mapの高度なModヘッダーはdesecrated生成だが、
                # 公式Trade APIは対応Statをexplicit名前空間で公開している。
                explicit_text = _STAT_TEXT_ALIASES.get(stat_alias_key, metadata_text)
                metadata, option, confidence = default_metadata_index().match_with_option(
                    explicit_text, "explicit",
                )
            if metadata is None and kind == "veiled" and current_header_name:
                metadata, confidence = default_metadata_index().match_ref(
                    current_header_name, kind,
                )
            if (
                metadata is None
                and _PARENTHETICAL_LINE.fullmatch(line)
                and (detailed_copy or item_category == "cluster_jewel")
            ):
                # 詳細コピーやクラスタージュエルに付く用語説明・上限説明は
                # `(enchant)` 表記でも検索条件ではない。
                continue
            roll_min, roll_max = _roll_bounds(line)
            inferred_affix = None
            if metadata and kind == "crafted":
                generations = {tier.generation for tier in metadata.tiers
                               if tier.generation in {"prefix", "suffix"}}
                if len(generations) == 1:
                    inferred_affix = generations.pop()
            values = _modifier_values(line, metadata)
            if stat_alias_key in _STAT_VALUE_OVERRIDES:
                values = _STAT_VALUE_OVERRIDES[stat_alias_key]
            value_index = _DIRECTIONAL_STAT_VALUE_INDEX.get(direction_alias_key)
            if value_index is not None and len(values) > value_index:
                values = (values[value_index],)
            # 公式日本語文（refに対応）のmatcher.negateはAwakenedと同じく
            # better/invertedの両方へ反映する。方向語の別表記を一意照合した場合は、
            # 従来どおり表示値に対する良否を維持し、API符号だけを反転する。
            matcher_negated = bool(metadata and metadata.negated and not direction_inverted)
            modifiers.append(ItemModifier(
                text=line, values=values, kind=kind,
                tier=current_header_tier if from_header else None,
                affix=current_header_affix if from_header else (
                    kind if kind in {"prefix", "suffix"} else inferred_affix
                ),
                group=(current_modifier_group if from_header else
                       section_index if item_category == "expedition_logbook" else None),
                ref=metadata.ref if metadata else (
                    map_check_exact["ref"] if map_check_exact else None
                ),
                stat_id=metadata.stat_id if metadata else (
                    map_check_exact["stat_id"] if map_check_exact else None
                ),
                confidence=confidence if metadata else (1.0 if map_check_exact else confidence),
                roll_min=roll_min,
                roll_max=roll_max,
                better=(metadata.better * (-1 if matcher_negated else 1)) if metadata else None,
                inverted=(metadata.inverted ^ (
                    direction_inverted if direction_inverted else matcher_negated
                )) if metadata else False,
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

    modifiers = _combine_multiline_modifiers(modifiers)
    return ParsedItem(
        item_class=header.get("item_class", ""), rarity=rarity, name=name,
        base_type=base_type, category=item_category,
        item_level=item_level, properties=properties, modifiers=tuple(modifiers),
        flags=tuple(dict.fromkeys(flags + (["veiled"] if any(
            modifier.kind == "veiled" or modifier.generation == "veiled"
            for modifier in modifiers
        ) else []))), raw_text=text,
    )
