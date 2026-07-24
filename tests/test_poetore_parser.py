import unittest

from src.poetore import ItemParseError, parse_item_text
from src.utils.i18n import EN, JA, set_locale


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

    def test_english_item_copy_parsing_is_independent_of_ui_locale(self):
        set_locale(EN)
        try:
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
        finally:
            set_locale(JA)

        self.assertEqual(item.category, "accessory")
        self.assertEqual(item.item_level, 70)
        self.assertEqual(item.base_type, "Gold Ring")
        self.assertEqual(len(item.modifiers), 1)
        self.assertEqual(item.modifiers[0].kind, "crafted")

    def test_parses_quiver_as_accessory(self):
        item = parse_item_text("""Item Class: Quivers
Rarity: Rare
Test Quiver
Broadhead Arrow Quiver
--------
Item Level: 86
""")
        self.assertEqual(item.category, "accessory")

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

    def test_map_tier_is_parsed_from_detailed_copy_name_line(self):
        item = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Pandemonium Solitude
Map (Tier 16)
--------
アイテム数量: +52% (augmented)
--------
アイテムレベル: 85
--------
モンスターレベル：83
""")
        self.assertEqual(item.category, "map")
        self.assertEqual(item.properties["Map Tier"], "16")

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

    def test_ignores_jewel_socket_help_text_in_japanese_and_english(self):
        japanese = parse_item_text("""アイテムクラス: ジュエル
レアリティ: レア
夕暮れの傷跡
クリムゾンジュエル
--------
アイテムレベル: 83
--------
パッシブツリーで割り当てられたジュエルソケットにはめる。右クリックしてソケットから取り外すことができる。
""")
        english = parse_item_text("""Item Class: Jewels
Rarity: Rare
Test Scar
Crimson Jewel
--------
Item Level: 83
--------
Place into an allocated Jewel Socket on the Passive Skill Tree. Right click to remove from the Socket.
""")
        self.assertEqual(japanese.modifiers, ())
        self.assertEqual(english.modifiers, ())

    def test_does_not_hide_jewel_help_text_from_unrelated_categories(self):
        item = parse_item_text("""アイテムクラス: 指輪
レアリティ: レア
試作品
ルビーの指輪
--------
アイテムレベル: 83
--------
パッシブツリーで割り当てられたジュエルソケットにはめる。右クリックしてソケットから取り外すことができる。
""")
        self.assertEqual(
            [modifier.text for modifier in item.modifiers],
            ["パッシブツリーで割り当てられたジュエルソケットにはめる。右クリックしてソケットから取り外すことができる。"],
        )

    def test_gem_level_is_not_overwritten_by_requirements_or_next_level(self):
        item = parse_item_text("""アイテムクラス: サポートジェム
レアリティ: ジェム
範囲ダメージ集中サポート
--------
レベル: 3
コスト・リザーブ倍率: 140%
--------
装備条件:
レベル: 26
知性: 45
--------
経験値: 154553/154553
--------
次のレベル:
レベル: 29
知性: 49
""")
        self.assertEqual(item.category, "gem")
        self.assertEqual(item.properties["ジェムレベル"], "3")
        self.assertEqual(item.properties["レベル"], "29")

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

    def test_foulborn_unique_headers_reset_implicit_kind_and_set_flag(self):
        item = parse_item_text("""アイテムクラス: 指輪
レアリティ: ユニーク
Foulborn Le Heup of All
Iron Ring
--------
アイテムレベル: 83
--------
{ 暗黙モッド — ダメージ, 物理, アタック }
1から4の物理ダメージをアタックに追加する
--------
{ ユニークモッド — 能力値 }
全ての能力値 +22(10-30)
(Attribute: 能力値は筋力、器用さ、知性)
{ ユニークモッド — 元素, 耐性 }
全ての元素耐性 +29(10-30)%
{ ユニークモッド — ドロップ }
見つかるアイテムのレアリティが16(10-30)%増加する
{ ファウルボーンユニークモッド — 防御 }
グローバル防御力が16(10-30)%増加する
(アーマー、回避力、エナジーシールドは標準的な防御力である)
""")
        self.assertIn("foulborn", item.flags)
        self.assertEqual(item.name, "Le Heup of All")
        self.assertEqual(
            [modifier.kind for modifier in item.modifiers],
            ["implicit", "explicit", "explicit", "explicit", "explicit"],
        )
        self.assertEqual(item.modifiers[-1].generation, "foulborn")
        self.assertTrue(all(modifier.stat_id for modifier in item.modifiers))

    def test_replica_dragonfang_reduced_requirements_resolves_signed_stat(self):
        item = parse_item_text("""アイテムクラス: アミュレット
レアリティ: ユニーク
Replica Dragonfang's Flight
Onyx Amulet
--------
アイテムレベル: 83
--------
{ ユニークモッド }
スキルのリザーブ効率が6(5-10)%増加する
{ ユニークモッド }
アイテムおよびジェムの要求能力値が8(10-5)%減少する
""")
        reservation, requirements = item.modifiers
        self.assertEqual(reservation.stat_id, "explicit.stat_2587176568")
        self.assertEqual(requirements.stat_id, "explicit.stat_752930724")
        self.assertTrue(requirements.inverted)
        self.assertEqual((requirements.roll_min, requirements.roll_max), (5.0, 10.0))

    def test_unique_flavour_text_after_separator_is_not_parsed_as_modifiers(self):
        item = parse_item_text("""アイテムクラス: アミュレット
レアリティ: ユニーク
Replica Dragonfang's Flight
Onyx Amulet
--------
装備要求:
レベル: 56
--------
アイテムレベル: 83
--------
{ 暗黙モッド — 能力値 }
全ての能力値 +15(10-16)
(Attribute: 能力値は筋力、器用さ、知性)
--------
{ ユニークモッド }
全てのブライト(ファイヤーボール-ディバインブラスト)ジェムのレベル +3
{ ユニークモッド — 元素, 耐性 }
全ての元素耐性 +6(5-10)%
{ ユニークモッド }
スキルのリザーブ効率が6(5-10)%増加する
{ ユニークモッド }
アイテムおよびジェムの要求能力値が8(10-5)%減少する
(Attribute: 能力値は筋力、器用さ、知性)
--------
「私たちがこれを作ったのですか？何故記録がないのでしょう？
何かが起こると警告はされていましたが……」
―管理者クォトラ
""")
        self.assertEqual(len(item.modifiers), 5)
        self.assertFalse(any("管理者クォトラ" in mod.text for mod in item.modifiers))

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

    def test_ignores_flask_usage_help_text_in_japanese_and_english(self):
        japanese = parse_item_text("""アイテムクラス: ユーティリティフラスコ
レアリティ: ノーマル
Quicksilver Flask
--------
6秒間持続
使用時に60中30チャージを消費
現在0チャージ
移動スピードが40%増加する
--------
装備要求:
レベル: 4
--------
アイテムレベル: 4
--------
右クリックして飲む。腰につけているときだけチャージを貯めることができる。モンスターを倒すことで充填される。
""")
        english = parse_item_text("""Item Class: Utility Flasks
Rarity: Normal
Quicksilver Flask
--------
Item Level: 4
--------
Right click to drink. Can only hold charges while in belt. Refills as you kill monsters.
""")
        self.assertEqual(japanese.modifiers, ())
        self.assertEqual(english.modifiers, ())


VAAL_MOLTEN_STRIKE = """アイテムクラス: スキルジェム
レアリティ: ジェム
Molten Strike
--------
アタック, 投射物, 範囲効果, 近接, ストライク, 火, 連鎖, ヴァール
レベル: 1
コスト: 6 マナ
アタックダメージ: 基本の126.5%
追加ダメージ効率: 126%
--------
装備要求:
レベル: 1
--------
近接武器に高温の溶融エネルギーを注入し物理ダメージと火ダメージで攻撃する。
--------
4個の投射物を放つ
物理ダメージの60%を火ダメージに変換する
--------
Vaal Molten Strike
--------
使用ごとの必要ソウル: 15
3回分保持可能
ソウル獲得不能: 3 秒
アタックスピード: 基本の70%
アタックダメージ: 基本の86.3%
追加ダメージ効率: 87%
--------
9個の投射物を放つ
+8回連鎖する
--------
経験値: 1/70
--------
同じ色のソケットにはめることでスキルを使用できるようになります。
--------
コラプト状態
"""


def test_vaal_gem_uses_the_vaal_skill_section_as_trade_identity():
    item = parse_item_text(VAAL_MOLTEN_STRIKE)

    assert item.category == "gem"
    assert item.name == "Vaal Molten Strike"
    assert item.base_type == "Vaal Molten Strike"
    assert "corrupted" in item.flags


def test_other_vaal_gem_is_detected_without_name_specific_logic():
    text = VAAL_MOLTEN_STRIKE.replace("Molten Strike", "Arc")
    item = parse_item_text(text)

    assert item.name == "Vaal Arc"
    assert item.base_type == "Vaal Arc"


if __name__ == "__main__":
    unittest.main()
