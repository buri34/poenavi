import unittest

from src.poetore import ItemParseError, parse_item_text


RARE_JP = """アイテムクラス: 指輪
レアリティ: レア
嵐の 輪
アメジストの指輪
--------
装備条件:
レベル: 60
--------
アイテムレベル: 84
--------
+23% 混沌耐性 (implicit)
--------
+72 最大ライフ
+35% 火耐性
未鑑定
"""


class PoetoreParserTest(unittest.TestCase):
    def test_captured_beast_is_detected_by_class_and_help_text(self):
        by_class = parse_item_text("""Item Class: Captured Beasts
Rarity: Rare
Craicic Chimeral
Craicic Chimeral
--------
Right-click to add this to your bestiary.
""")
        self.assertEqual(by_class.category, "captured_beast")
        by_help = parse_item_text("""アイテムクラス: その他
レアリティ: レア
クライシック・キメラル
クライシック・キメラル
--------
右クリックしてビースト図鑑に追加する。
""")
        self.assertEqual(by_help.category, "captured_beast")

    def test_parses_japanese_rare_item_into_public_model(self):
        item = parse_item_text(RARE_JP)
        self.assertEqual(item.item_class, "指輪")
        self.assertEqual(item.rarity, "レア")
        self.assertEqual(item.name, "嵐の 輪")
        self.assertEqual(item.base_type, "アメジストの指輪")
        self.assertEqual(item.category, "accessory")
        self.assertEqual(item.item_level, 84)
        self.assertEqual(item.flags, ("unidentified",))
        self.assertEqual(len(item.modifiers), 3)
        self.assertEqual(item.modifiers[0].kind, "implicit")
        self.assertEqual(item.modifiers[0].values, (23.0,))

    def test_parses_english_normal_item_and_crlf(self):
        item = parse_item_text(
            "Item Class: Currency\r\nRarity: Normal\r\nChaos Orb\r\n--------\r\nStack Size: 4/20\r\n"
        )
        self.assertEqual(item.name, "Chaos Orb")
        self.assertEqual(item.base_type, "Chaos Orb")
        self.assertEqual(item.category, "currency")
        self.assertEqual(item.properties["Stack Size"], "4/20")

    def test_prefers_japanese_name_and_base_when_both_languages_are_present(self):
        item = parse_item_text("""アイテムクラス: 片手剣
レアリティ: レア
Doom Ruin
Corsair Sword
地獄の破滅
略奪者の剣
--------
アイテムレベル: 82
""")
        self.assertEqual(item.name, "地獄の破滅")
        self.assertEqual(item.base_type, "略奪者の剣")

    def test_keeps_japanese_name_and_base_from_actual_clipboard_text(self):
        item = parse_item_text("""アイテムクラス: 両手剣
レアリティ: レア
地獄の破滅
略奪者の剣
--------
両手剣
物理ダメージ: 108-181 (augmented)
クリティカル率: 5.00%
秒間アタック回数: 1.74 (augmented)
武器攻撃距離：1.3 メートル
--------
装備要求:
レベル: 59
筋力: 82
器用さ: 119
--------
ソケット: G-R-G
--------
アイテムレベル: 67
--------
グローバル命中力が60%増加する (implicit)
--------
物理ダメージが74%増加する
アタックスピードが16%増加する
""")
        self.assertEqual(item.name, "地獄の破滅")
        self.assertEqual(item.base_type, "略奪者の剣")

    def test_rejects_non_item_text(self):
        with self.assertRaises(ItemParseError):
            parse_item_text("ただの文章です")

    def test_weapon_properties_and_requirements_are_not_modifiers(self):
        item = parse_item_text("""Item Class: Bows
Rarity: Rare
Storm Reach
Spine Bow
--------
Bow
Physical Damage: 38-115 (augmented)
Critical Strike Chance: 6.50%
Attacks per Second: 1.50
--------
Requirements:
Level: 64
Dexterity: 212
--------
Sockets: G-G-G-G-G-G
--------
Item Level: 84
--------
+24% to Global Critical Strike Multiplier (implicit)
--------
{ Prefix Modifier "Vicious" (Tier: 3) }
120% increased Physical Damage
{ Suffix Modifier "of the Lynx" (Tier: 2) }
+31 to Dexterity
""")
        self.assertEqual(len(item.modifiers), 3)
        self.assertEqual([mod.kind for mod in item.modifiers], ["implicit", "prefix", "suffix"])
        self.assertEqual([mod.tier for mod in item.modifiers], [None, 3, 2])
        self.assertEqual([mod.affix for mod in item.modifiers], [None, "prefix", "suffix"])
        self.assertEqual([mod.group for mod in item.modifiers], [None, 1, 2])
        self.assertIn("Physical Damage", item.properties)
        self.assertIn("Requirements", item.properties)
        self.assertNotIn("Bow", [mod.text for mod in item.modifiers])

    def test_modifier_header_is_not_counted_as_a_modifier(self):
        item = parse_item_text("""Item Class: Rings
Rarity: Rare
Coil Band
Gold Ring
--------
Requirements:
Level: 40
--------
Item Level: 70
--------
{ Crafted Prefix Modifier }
+45 to maximum Life (crafted)
""")
        self.assertEqual(len(item.modifiers), 1)
        self.assertEqual(item.modifiers[0].kind, "crafted")

    def test_strips_unscalable_value_and_ignores_recently_glossary_in_japanese(self):
        item = parse_item_text("""アイテムクラス: 胴体防具
レアリティ: レア
試作品
ヴァールレガリア
--------
アイテムレベル: 85
--------
{ サフィックスモッド「永続の」 }
直近ヒットを受けていれば毎秒エンデュランスチャージを1個獲得する — スケールできない値
(Recently: 直近とは過去4秒間を指す)
""")
        self.assertEqual(len(item.modifiers), 1)
        self.assertEqual(
            item.modifiers[0].text,
            "直近ヒットを受けていれば毎秒エンデュランスチャージを1個獲得する",
        )
        self.assertNotIn("スケールできない値", item.modifiers[0].text)

    def test_strips_unscalable_value_and_ignores_recently_glossary_in_english(self):
        item = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Shell
Vaal Regalia
--------
Item Level: 85
--------
{ Suffix Modifier }
Gain 1 Endurance Charge every second if you've been Hit Recently — Unscalable Value
(Recently: refers to the past 4 seconds)
""")
        self.assertEqual(len(item.modifiers), 1)
        self.assertEqual(
            item.modifiers[0].text,
            "Gain 1 Endurance Charge every second if you've been Hit Recently",
        )

    def test_ignores_other_parenthesized_glossary_definitions(self):
        item = parse_item_text("""Item Class: Rings
Rarity: Rare
Test Ring
Ruby Ring
--------
Item Level: 85
--------
+30% to Fire Resistance
(Nearby: the distance at which this effect applies depends on the source)
""")
        self.assertEqual([modifier.text for modifier in item.modifiers], [
            "+30% to Fire Resistance",
        ])

    def test_japanese_modifier_headers_are_classified_and_not_counted(self):
        item = parse_item_text("""アイテムクラス: 両手剣
レアリティ: レア
地獄の破滅
略奪者の剣
--------
アイテムレベル: 67
--------
{ プレフィックス モディファイア "残忍な" (ティア: 3) }
物理ダメージが74%増加する
{ サフィックス モディファイア "祝福の" (ティア: 4) }
アタックスピードが16%増加する
{ クラフトされたプレフィックス モディファイア }
命中力 +55 (crafted)
""")
        self.assertEqual(len(item.modifiers), 3)
        self.assertEqual(
            [mod.kind for mod in item.modifiers],
            ["prefix", "suffix", "crafted"],
        )
        self.assertNotIn("モディファイア", [mod.text for mod in item.modifiers])

    def test_multiline_hybrid_prefix_keeps_kind_until_next_header(self):
        item = parse_item_text("""アイテムクラス: 両手剣
レアリティ: レア
地獄の破滅
略奪者の剣
--------
アイテムレベル: 67
--------
{ プレフィックスモッド「引き裂く者」(ティア: 6) }
物理ダメージが30(25-34)%増加する
命中力 +55(47-72)
{ プレフィックスモッド「重い」(ティア: 8) }
物理ダメージが44(40-49)%増加する
{ サフィックスモッド「吸収の」(ティア: 6) }
倒した敵1体ごとに4のマナを獲得する
""")
        self.assertEqual(
            [mod.kind for mod in item.modifiers],
            ["prefix", "prefix", "prefix", "suffix"],
        )
        self.assertEqual(item.modifiers[1].text, "命中力 +55(47-72)")
        self.assertEqual([mod.tier for mod in item.modifiers], [6, 6, 8, 6])
        self.assertEqual([mod.group for mod in item.modifiers], [1, 1, 2, 3])

    def test_parses_synthesised_and_dual_influence_flags_in_both_languages(self):
        english = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Shell
Vaal Regalia
--------
Item Level: 85
--------
Shaper Item
Elder Item
Synthesised Item
""")
        self.assertEqual(
            english.flags,
            ("influence:shaper", "influence:elder", "synthesised"),
        )
        japanese = parse_item_text("""アイテムクラス: 胴体防具
レアリティ: レア
試作品
ヴァールレガリア
--------
アイテムレベル: 85
--------
ハンターアイテム
シンセサイズアイテム
""")
        self.assertEqual(japanese.flags, ("influence:hunter", "synthesised"))

    def test_parses_modifier_generation_for_ui_details(self):
        item = parse_item_text("""アイテムクラス: 鎧
レアリティ: レア
試作品
セイクリッドチェインメイル
--------
アイテムレベル: 94
--------
{ プレフィックスモッド「高位のクルセーダーの」 — ダメージ, 物理 }
効果範囲が11(8-12)%増加する
""")
        modifier = item.modifiers[0]
        self.assertEqual(modifier.affix, "prefix")
        self.assertEqual(modifier.generation, "crusader")


if __name__ == "__main__":
    unittest.main()
