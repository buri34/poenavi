"""
ジェム取得タイミング解決: PoBインポート結果 + gems.json + クラスから
各ジェムの最初の入手タイミングを特定する。

優先順: quest報酬 > vendor購入 > Act6 Lilly（全ジェム）
図書館ルート/スキップルート分岐にも対応。
"""

import json
import os
import sys


def _get_data_dir():
    """dataディレクトリのパスを返す（exeフォルダ優先 → PyInstaller _MEIPASS）。"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        exe_data_dir = os.path.join(exe_dir, "data")
        if os.path.isdir(exe_data_dir):
            return exe_data_dir
        return os.path.join(getattr(sys, '_MEIPASS', exe_dir), "data")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")


def load_gems_db() -> dict:
    """gems.jsonを読み込む"""
    path = os.path.join(_get_data_dir(), "gems.json")
    if not os.path.exists(path):
        print(f"[GemResolver] gems.json not found: {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_gem_names_ja() -> dict:
    """ジェム名日本語マッピングを読み込む"""
    path = os.path.join(_get_data_dir(), "gem_names_ja.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_quest_names_ja() -> dict:
    """クエスト名日本語マッピングを読み込む"""
    path = os.path.join(_get_data_dir(), "quest_names_ja.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_npc_names_ja() -> dict:
    """NPC名日本語マッピングを読み込む"""
    path = os.path.join(_get_data_dir(), "npc_names_ja.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# クエストの順序（Act→クエスト順）
QUEST_ORDER = [
    "enemy at the gate",
    "mercy mission",
    "breaking some eggs2",
    "breaking some eggs1",
    "the caged brute1",
    "the caged brute2",
    "the siren's cadence",
    "intruders in black",
    "sharp and cruel",
    "the root of the problem",
    "lost in love",
    "sever the right hand",
    "a fixture of fate",       # Act3 Siosa（図書館）
    "breaking the seal",
    "the eternal nightmare",
    "fallen from grace",       # Act6 Lilly
]

# スタータージェム（各クラスの初期ジェム）— gems.jsonには含まれないので除外
STARTER_GEMS = {
    "marauder": ["heavy strike", "ground slam", "ruthless support"],
    "ranger": ["burning arrow", "momentum support"],
    "witch": ["fireball", "freezing pulse", "arcane surge support"],
    "duelist": ["double strike", "chance to bleed support"],
    "templar": ["glacial hammer"],
    "shadow": ["viper strike", "chance to poison support"],
    "scion": ["spectral throw"],
}

# Empower/Enhance/Enlighten はドロップのみなので除外
EXCLUDED_GEMS = {"empower support", "enhance support", "enlighten support"}


def resolve_gem_acquisition(
    gem_names: list[str],
    char_class: str,
    library_route: bool = True,
    gems_db: dict = None,
) -> list[dict]:
    """
    各ジェムについて最初に入手できるタイミングを特定する。
    
    Args:
        gem_names: ジェム名のリスト（英語小文字）
        char_class: キャラクラス名（英語小文字）
        library_route: 図書館ルートを使うかどうか（True=図書館寄り道、False=スキップ）
        gems_db: gems.jsonのデータ（Noneの場合は自動読み込み）
        
    Returns:
        Act/クエスト順にソートされたジェム取得計画のリスト:
        [
            {
                "act": 1,
                "quest": "the caged brute1",
                "quest_ja": "檻の中の獣1",
                "npc": "nessa",
                "npc_ja": "ネッサ",
                "gems": [
                    {
                        "name": "blade vortex",
                        "name_ja": "ブレードヴォーテックス",
                        "type": "quest",  # quest/vendor/lilly
                        "is_support": False,
                        "attribute": 3,  # 1=STR, 2=DEX, 3=INT
                    },
                ]
            },
            ...
        ]
    """
    if gems_db is None:
        gems_db = load_gems_db()
    
    quest_names_ja = load_quest_names_ja()
    gem_names_ja = load_gem_names_ja()
    npc_names_ja = load_npc_names_ja()
    quests_info = gems_db.get("_quests", {})
    
    # スタータージェムを除外
    starter = set(STARTER_GEMS.get(char_class, []))
    
    # 各ジェムの最初の入手タイミングを特定
    gem_acquisitions = {}  # gem_name -> {quest, type, act}
    
    for gem_name in gem_names:
        if gem_name in EXCLUDED_GEMS:
            continue
        if gem_name in starter:
            continue
        
        gem_data = gems_db.get(gem_name)
        if not gem_data:
            # ジェム名に "support" を付加して再検索
            alt_name = gem_name if gem_name.endswith(" support") else gem_name + " support"
            gem_data = gems_db.get(alt_name)
            if gem_data:
                gem_name = alt_name
        
        if not gem_data:
            # gems.jsonに存在しないジェム → NPC入手不可（リストから除外）
            # Exceptional gems, Vaalジェム等
            continue

        # PoBではサポートジェムの末尾 "support" が省略されることがある。
        # 正式名へ補正した後も開始時所持ジェムとして除外する。
        if gem_name in starter:
            continue
        
        quests = gem_data.get("quests", {})
        if not quests:
            # questsが空 → NPC入手不可（Enlighten/Empower/Enhance等）
            continue
        attribute = gem_data.get("attribute", 0)
        
        best = None  # {"quest": ..., "type": ..., "act": ..., "order": ...}
        vendor_acts = set()
        
        for quest_key, quest_data in quests.items():
            quest_info = quests_info.get(quest_key, {})
            quest_act = quest_info.get("act", 99)
            
            # quest_key の順序インデックス
            try:
                order = QUEST_ORDER.index(quest_key)
            except ValueError:
                order = 999
            
            # 図書館スキップルートの場合、Siosa(a fixture of fate)を除外
            if not library_route and quest_key == "a fixture of fate":
                continue
            
            # quest報酬チェック
            quest_classes = quest_data.get("quest", None)
            if quest_classes is not None:
                # 空配列 = 全クラス対象
                if len(quest_classes) == 0 or char_class in quest_classes:
                    candidate = {"quest": quest_key, "type": "quest", "act": quest_act, "order": order}
                    if best is None or order < best["order"]:
                        best = candidate

            # vendor購入チェック
            vendor_classes = quest_data.get("vendor", None)
            if vendor_classes is not None:
                if len(vendor_classes) == 0 or char_class in vendor_classes:
                    vendor_acts.add(6 if not library_route and quest_key == "a fixture of fate" else quest_act)
                    candidate = {"quest": quest_key, "type": "vendor", "act": quest_act, "order": order}
                    if best is None or order < best["order"]:
                        best = candidate
        
        if best:
            # 図書館スキップルートの場合、Siosa のジェムを Lilly に読み替え
            if not library_route and best["quest"] == "a fixture of fate":
                best = {"quest": "fallen from grace", "type": "lilly", "act": 6, "order": QUEST_ORDER.index("fallen from grace")}
            
            gem_acquisitions[gem_name] = {
                "quest": best["quest"],
                "type": best["type"],
                "act": best["act"],
                "attribute": attribute,
                "vendor_acts": sorted(vendor_acts),
            }
        else:
            # どのクエストでも入手できない → Act6 Lilly
            gem_acquisitions[gem_name] = {
                "quest": "fallen from grace",
                "type": "lilly",
                "act": 6,
                "attribute": attribute,
                "vendor_acts": [6],
            }
    
    # クエストごとにジェムをグループ化
    quest_gems = {}  # quest_key -> [gem_info, ...]
    for gem_name, acq in gem_acquisitions.items():
        quest_key = acq["quest"]
        if quest_key not in quest_gems:
            quest_gems[quest_key] = []
        
        is_support = "support" in gem_name
        name_ja = gem_names_ja.get(gem_name, "")
        
        quest_gems[quest_key].append({
            "name": gem_name,
            "name_ja": name_ja,
            "type": acq["type"],
            "is_support": is_support,
            "attribute": acq["attribute"],
            "vendor_acts": acq["vendor_acts"],
        })
    
    # QUEST_ORDER順にソート
    result = []
    for quest_key in QUEST_ORDER:
        if quest_key not in quest_gems:
            continue
        
        quest_info = quests_info.get(quest_key, {})
        quest_act = quest_info.get("act", 0)
        npc = quest_info.get("npc", "")
        quest_ja = quest_names_ja.get(quest_key, quest_key)
        npc_ja = npc_names_ja.get(npc, npc)
        
        # ジェムをソート: quest報酬 > vendor、非サポート > サポート
        gems_sorted = sorted(quest_gems[quest_key], key=lambda g: (
            0 if g["type"] == "quest" else 1,
            0 if not g["is_support"] else 1,
            g["name"],
        ))
        
        result.append({
            "act": quest_act,
            "quest": quest_key,
            "quest_ja": quest_ja,
            "npc": npc,
            "npc_ja": npc_ja,
            "gems": gems_sorted,
        })
    
    return result


def get_gems_for_act(acquisition_plan: list[dict], act: int) -> list[dict]:
    """特定のActのジェム取得リストを返す"""
    return [entry for entry in acquisition_plan if entry["act"] == act]


def get_gems_up_to_act(acquisition_plan: list[dict], act: int) -> list[dict]:
    """指定Act以下の全ジェム取得リストを返す"""
    return [entry for entry in acquisition_plan if entry["act"] <= act]
