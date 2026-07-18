from src.poetore.merge import merge_normal_and_detailed_copy
from src.poetore.parser import parse_item_text


def test_uses_japanese_name_and_base_with_detailed_mods():
    normal = """アイテムクラス: 両手剣
レアリティ: レア
地獄の破滅
略奪者の剣
--------
アイテムレベル: 67
--------
物理ダメージが74%増加する
"""
    detailed = """Item Class: Two Hand Swords
Rarity: Rare
Pandemonium Bane
Reaver Sword
--------
Item Level: 67
--------
{ Prefix Modifier \"Vicious\" (Tier: 3) }
74% increased Physical Damage
"""

    merged = merge_normal_and_detailed_copy(normal, detailed)
    item = parse_item_text(merged)

    assert item.name == "地獄の破滅"
    assert item.base_type == "略奪者の剣"
    assert "{ Prefix Modifier" in merged
    assert "74% increased Physical Damage" in merged
