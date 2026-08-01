from io import BytesIO
from dataclasses import replace
import json
import pytest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from src.poetore.parser import parse_item_text
from src.poetore.metadata import unique_fixed_stats
from src.poetore.models import ItemModifier, ParsedItem
from src.poetore.trade import (
    PRESET_BASE, PRESET_FINISHED, PriceListing, PriceResult, TradeApiError, TradeStatFilter,
    UniqueCandidate,
    active_pc_league, apply_search_range, available_pc_leagues, available_trade_presets, build_search_query,
    default_pc_league, elemental_dps, english_trade_identity,
    japanese_trade_item_label,
    default_trade_currency, physical_dps, physical_dps_at_20_quality,
    resolve_trade_stat_filters, search_prices, unique_candidate_details,
    unique_candidates, unique_variants,
    unresolved_modifier_warnings, uses_dedicated_exact_preset, resolve_official_base_type,
    is_inscribed_ultimatum,
)
from src.poetore.trade import _request_json
from src.poetore.trade import _base_defence_percentile
from src.poetore.trade import _trade_response_cache
from src.poetore.trade import _awakened_tier_tags
from src.poetore.trade import _apply_atzoatl_room_rules
from src.poetore.trade import _group_price_listings
from src.poetore.trade import (
    _english_trade_item_name,
    _english_trade_item_type,
    _japanese_trade_item_name,
    _japanese_trade_item_type,
)


def test_japanese_trade_item_label_uses_unique_name_and_regular_type():
    with (
        patch(
            "src.poetore.trade._japanese_trade_item_name",
            return_value="忠臣の皮膚",
        ) as unique_name,
        patch(
            "src.poetore.trade._japanese_trade_item_type",
            return_value="チャユラの祝福",
        ) as item_type,
    ):
        assert japanese_trade_item_label(
            "UNIQUE", "Skin of the Loyal", "Simple Robe",
        ) == "忠臣の皮膚"
        assert japanese_trade_item_label(
            "ITEM", "Blessing of Chayula",
        ) == "チャユラの祝福"
        unique_name.assert_called_once_with("Skin of the Loyal")
        item_type.assert_called_once_with("Blessing of Chayula")


def test_japanese_trade_item_label_falls_back_to_english_name():
    with (
        patch("src.poetore.trade._japanese_trade_item_name", return_value=None),
        patch("src.poetore.trade._japanese_trade_item_type", return_value=None),
    ):
        assert japanese_trade_item_label("UNIQUE", "Unknown Unique") == "Unknown Unique"
        assert japanese_trade_item_label("ITEM", "Unknown Item") == "Unknown Item"


ITEM = """Item Class: Two Hand Swords
Rarity: Rare
Doom Sever
Reaver Sword
--------
Two Hand Sword
Physical Damage: 108-181 (augmented)
Attacks per Second: 1.74 (augmented)
--------
Item Level: 67
--------
74% increased Physical Damage
"""

MIRRORED_PENUMBRA_RING = """アイテムクラス: 指輪
レアリティ: レア
Pandemonium Loop
Penumbra Ring
--------
装備要求:
レベル: 59
--------
アイテムレベル: 83
--------
{ 暗黙モッド — 呪い }
左の指輪スロット: 受けている呪いの効果が30%減少する
右の指輪スロット: 受けている呪いの効果が30%増加する
--------
{ プレフィックスモッド「凍える」 — ダメージ, 元素, 冷気, アタック }
プレイヤー自身が受けるアタックに16(6-9)から36(13-16)の冷気ダメージを追加する
{ プレフィックスモッド「海賊の」 (ティア: 3) — ドロップ }
見つかるアイテムのレアリティが36(13-18)%増加する
{ サフィックスモッド 「タイタンの」 (ティア: 2) — 能力値 }
筋力 +120(43-50)
{ サフィックスモッド 「拡散の」 (ティア: 3) — マナ }
倒した敵1体ごとに48(-16--25)のマナを失う
{ サフィックスモッド 「迷い子の」 (ティア: 6) — 混沌, 耐性 }
混沌耐性 +14(5-10)%
--------
ミラー状態
"""

WARLORD_SYNDICATES_GARB = """アイテムクラス: 鎧
レアリティ: レア
Honour Jack
Syndicate's Garb
--------
回避力: 1374
--------
装備要求:
レベル: 84
器用さ: 293
--------
ソケット: G G
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「ウォーロードの」 (ティア: 1) — 物理, 元素, 火 }
ヒットによる物理ダメージの15(13-15)%を火ダメージとして受ける
{ サフィックスモッド 「ジャガーの」 (ティア: 3) — 能力値 }
器用さ +40(38-42)
{ サフィックスモッド 「火山の」 (ティア: 3) — 元素, 火, 耐性 }
火耐性 +40(36-41)%
--------
ウォーロードアイテム
"""


def test_japanese_type_mapping_keeps_safe_prefix_of_unequal_item_groups():
    english = (("armour", ({"type": "First Base"}, {"type": "Syndicate's Garb"},
                {"type": "Missing Later"}, {"type": "Unique", "name": "Unique",
                                            "flags": {"unique": True}},
                {"type": "Crusader Gloves", "name": "Repentance",
                 "flags": {"unique": True}})),)
    japanese = (("armour", ({"type": "最初のベース"}, {"type": "シンジケートの服"},
                 {"type": "ユニーク", "name": "ユニーク",
                  "flags": {"unique": True}},
                 {"type": "聖戦士のグローブ", "name": "悔恨",
                  "flags": {"unique": True}})),)
    with patch("src.poetore.trade._trade_item_groups", return_value=english), patch(
        "src.poetore.trade._jp_trade_item_groups", return_value=japanese,
    ):
        assert _japanese_trade_item_type("Syndicate's Garb") == "シンジケートの服"
        # 欠落entry自体を誤った日本語typeへ変換せず、その後のUnique境界で再同期する。
        assert _japanese_trade_item_type("Missing Later") is None
        assert _japanese_trade_item_name("Repentance") == "悔恨"


def test_item_mapping_uses_stable_group_id_instead_of_group_order():
    english = (
        ("accessory", ({"type": "Iron Ring"},)),
        ("armour", ({"type": "Mesh Boots", "name": "Wake of Destruction",
                     "flags": {"unique": True}},)),
    )
    japanese = (
        ("armour", ({"type": "メッシュブーツ", "name": "破滅の軌跡",
                     "flags": {"unique": True}},)),
        ("accessory", ({"type": "鉄の指輪"},)),
    )
    with patch("src.poetore.trade._trade_item_groups", return_value=english), patch(
        "src.poetore.trade._jp_trade_item_groups", return_value=japanese,
    ):
        assert _english_trade_item_type("メッシュブーツ") == "Mesh Boots"
        assert _english_trade_item_name("破滅の軌跡") == "Wake of Destruction"


def test_item_mapping_rejects_ambiguous_localized_identity():
    english = (("weapon", (
        {"type": "Heavy Arrow Quiver"},
        {"type": "Heavy Quiver"},
    )),)
    japanese = (("weapon", (
        {"type": "重い矢筒"},
        {"type": "重い矢筒"},
    )),)
    with patch("src.poetore.trade._trade_item_groups", return_value=english), patch(
        "src.poetore.trade._jp_trade_item_groups", return_value=japanese,
    ):
        assert _english_trade_item_type("重い矢筒") is None


@pytest.mark.parametrize(("localized", "expected"), (
    ("重い矢筒", "Heavy Arrow Quiver"),
    ("原始の矢筒", "Primal Arrow Quiver"),
    ("羽根付きの矢筒", "Feathered Arrow Quiver"),
    ("灼熱の矢筒", "Blazing Arrow Quiver"),
))
def test_confirmed_quiver_overrides_resolve_ambiguous_official_data(
    localized, expected,
):
    assert _english_trade_item_type(localized, "accessory") == expected


def test_confirmed_rabid_rhoa_card_override_is_category_scoped():
    assert _english_trade_item_type(
        "狂犬病のロア", "divination_card",
    ) == "The Rabid Rhoa"
    assert _english_trade_item_type("狂犬病のロア", "captured_beast") is None


def test_329_japanese_copy_resolves_base_type_for_nonunique_items():
    item = ParsedItem("靴", "レア", "破滅の足跡", "メッシュブーツ", "armour")
    with patch(
        "src.poetore.trade._english_trade_item_type", return_value="Mesh Boots",
    ) as item_type, patch(
        "src.poetore.trade._english_trade_item_name",
    ) as item_name:
        assert english_trade_identity(
            item, item.base_type, item.name,
        ) == ("Mesh Boots", "破滅の足跡")
    item_type.assert_called_once_with("メッシュブーツ", "armour")
    item_name.assert_not_called()


def test_329_japanese_copy_resolves_unique_name_and_base_type():
    item = ParsedItem("靴", "ユニーク", "破滅の軌跡", "メッシュブーツ", "armour")
    with patch(
        "src.poetore.trade._english_trade_item_type", return_value="Mesh Boots",
    ), patch(
        "src.poetore.trade._english_trade_item_name", return_value="Wake of Destruction",
    ):
        assert english_trade_identity(
            item, item.base_type, item.name,
        ) == ("Mesh Boots", "Wake of Destruction")


def test_329_japanese_magic_one_line_name_resolves_contained_base_type():
    english = (("flask", ({"type": "Jade Flask"}, {"type": "Blood Sap Tincture"})),)
    japanese = (("flask", ({"type": "翡翠のフラスコ"}, {"type": "血の樹液のチンキ"})),)
    with patch("src.poetore.trade._trade_item_groups", return_value=english), patch(
        "src.poetore.trade._jp_trade_item_groups", return_value=japanese,
    ):
        assert _english_trade_item_type(
            "初学者の 消費の 翡翠のフラスコ",
        ) == "Jade Flask"
        assert _english_trade_item_type(
            "固く握った 殴打の 血の樹液のチンキ",
        ) == "Blood Sap Tincture"


def test_329_unidentified_unique_base_is_not_used_as_unique_name():
    item = ParsedItem("スタッフ", "ユニーク", "ねじれた枝", "ねじれた枝", "weapon")
    with patch(
        "src.poetore.trade._english_trade_item_type", return_value="Gnarled Branch",
    ), patch("src.poetore.trade._english_trade_item_name") as item_name:
        assert english_trade_identity(
            item, item.base_type, item.name,
        ) == ("Gnarled Branch", None)
    item_name.assert_not_called()


def test_warlord_syndicates_garb_web_url_uses_japanese_official_base_type():
    _trade_response_cache.clear()
    item = parse_item_text(WARLORD_SYNDICATES_GARB)
    filters = resolve_trade_stat_filters(item)
    response = ({"id": "qid", "result": [], "total": 0}, {})
    with patch("src.poetore.trade._request_json", return_value=response), patch(
        "src.poetore.trade._japanese_trade_item_type",
        side_effect=lambda value: "シンジケートの服"
        if value == "Syndicate's Garb" else None,
    ):
        result = search_prices(
            item, "Syndicate's Garb", "Standard", filters,
            item_level_min=85,
        )
    payload = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])
    assert payload["query"]["type"] == "シンジケートの服"
    assert payload["query"]["filters"]["misc_filters"]["filters"]["ilvl"] == {
        "min": 85,
    }


def test_awakened_tier_tags_preserve_each_aggregated_mod():
    modifiers = (
        ItemModifier("命中力 +100", (100,), tier=2),
        ItemModifier("命中力 +200", (200,), tier=2),
    )
    assert _awakened_tier_tags(modifiers) == (2, 2)

    mixed = (
        ItemModifier("命中力 +100", (100,), tier=2),
        ItemModifier("命中力 +300", (300,), tier=1),
    )
    assert _awakened_tier_tags(mixed) == (1, 2)


def test_trade_api_surfaces_rate_limit_immediately():
    error = HTTPError(
        "https://example.invalid", 429, "rate limited", {"Retry-After": "580"},
        BytesIO(b'{}'),
    )
    with patch("src.poetore.trade.urlopen", side_effect=error) as urlopen:
        with pytest.raises(Exception) as exc_info:
            _request_json("https://example.invalid", {"query": {}})
    assert str(exc_info.value) == (
        "検索回数が多いため、PoE Trade APIの利用制限に達しました。"
        " 約10分後に、もう一度検索してください。"
    )
    urlopen.assert_called_once()


def test_trade_api_surfaces_rate_limit_without_retry_after():
    error = HTTPError(
        "https://example.invalid", 429, "rate limited", {},
        BytesIO(b'{}'),
    )
    with patch("src.poetore.trade.urlopen", side_effect=error):
        with pytest.raises(Exception) as exc_info:
            _request_json("https://example.invalid", {"query": {}})
    assert str(exc_info.value) == (
        "検索回数が多いため、PoE Trade APIの利用制限に達しました。"
        " しばらく時間を置いてから、もう一度検索してください。"
    )


def test_trade_api_surfaces_official_error_message():
    error = HTTPError(
        "https://example.invalid", 400, "bad request", {},
        BytesIO(b'{"error":{"code":2,"message":"Unknown item base type"}}'),
    )
    with patch("src.poetore.trade.urlopen", side_effect=error):
        with pytest.raises(Exception) as exc_info:
            _request_json("https://example.invalid", {"query": {}})
    assert "HTTP 400" in str(exc_info.value)
    assert "Unknown item base type" in str(exc_info.value)


def test_weapon_search_uses_english_base_rarity_and_comparable_pdps():
    item = parse_item_text(ITEM)
    filters = resolve_trade_stat_filters(item)
    query = build_search_query(item, "Reaver Sword", filters)["query"]
    assert query["type"] == "Reaver Sword"
    assert query["filters"]["type_filters"]["filters"]["rarity"]["option"] == "nonunique"
    assert query["filters"]["weapon_filters"]["filters"]["pdps"]["min"] == 271.0
    assert query["status"]["option"] == "securable"
    assert round(physical_dps(item), 2) == 251.43
    assert round(physical_dps_at_20_quality(item), 2) == 301.72


def test_weapon_search_strips_superior_display_prefix_from_base_type():
    item = parse_item_text(ITEM)
    assert build_search_query(item, "Superior Ezomyte Blade")["query"]["type"] == "Ezomyte Blade"
    assert build_search_query(item, "上質な エゾマイトの刃")["query"]["type"] == "エゾマイトの刃"


def test_nonunique_gear_can_search_all_bases_in_the_same_item_class():
    sword = parse_item_text(ITEM)
    sword_query = build_search_query(
        sword, "Reaver Sword", exact_base_type=False,
    )["query"]
    assert "type" not in sword_query
    assert sword_query["filters"]["type_filters"]["filters"]["category"] == {
        "option": "weapon.twosword"
    }
    assert sword_query["filters"]["type_filters"]["filters"]["rarity"] == {
        "option": "nonunique"
    }

    armour = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Item Level: 94
""")
    armour_query = build_search_query(
        armour, "Sacred Chainmail", exact_base_type=False,
    )["query"]
    assert "type" not in armour_query
    assert armour_query["filters"]["type_filters"]["filters"]["category"] == {
        "option": "armour.chest"
    }


@pytest.mark.parametrize(("item_text", "base_type", "category"), [
    ("""Item Class: Jewels
Rarity: Rare
Test Jewel
Crimson Jewel
--------
Item Level: 84
""", "Crimson Jewel", "jewel.base"),
    ("""Item Class: Abyss Jewels
Rarity: Rare
Test Jewel
Ghastly Eye Jewel
--------
Item Level: 84
""", "Ghastly Eye Jewel", "jewel.abyss"),
])
def test_nonunique_jewels_can_search_their_whole_jewel_category(
    item_text, base_type, category,
):
    item = parse_item_text(item_text)
    query = build_search_query(item, base_type, exact_base_type=False)["query"]
    assert "type" not in query
    assert query["filters"]["type_filters"]["filters"]["category"] == {
        "option": category
    }


def test_magic_single_line_affixed_name_resolves_longest_official_base():
    entries = (
        {"type": "Wand", "flags": {}},
        {"type": "Imbued Wand", "flags": {}},
        {"type": "The Imbued Wand", "flags": {"unique": True}},
    )
    with patch("src.poetore.trade._trade_item_entries", return_value=entries):
        assert resolve_official_base_type("Dissolution Imbued Wand of Torment") == "Imbued Wand"


def test_search_auto_resolves_magic_single_line_detail_name_before_api():
    item = ParsedItem(
        "ワンド", "マジック", "酩薬の 痛憤の 浸潤のワンド",
        "酩薬の 痛憤の 浸潤のワンド", "weapon", item_level=84,
    )
    entries = ({"type": "Imbued Wand", "flags": {}},)
    response = ({"id": "qid", "result": [], "total": 0}, {}, False)
    with patch("src.poetore.trade._trade_item_entries", return_value=entries), patch(
        "src.poetore.trade._cached_request_json", return_value=response,
    ) as request:
        search_prices(item, "Dissolution Imbued Wand of Torment", league="Standard")
    assert request.call_args.args[1]["query"]["type"] == "Imbued Wand"


def test_normal_search_rejects_japanese_identity_before_api_request():
    item = parse_item_text(ITEM)
    with patch(
        "src.poetore.trade._english_trade_item_type", return_value=None,
    ), patch("src.poetore.trade._cached_request_json") as request_json:
        with pytest.raises(TradeApiError, match="英語のアイテム名またはベースタイプ"):
            search_prices(
                item, "上質な エゾマイトの刃", league="Standard",
                stat_filters=(TradeStatFilter(
                    "property.physical_dps", "物理DPS", 139.9, "property", True,
                ),),
            )
    request_json.assert_not_called()


def test_normal_equipment_defaults_to_any_currency():
    item = parse_item_text(ITEM)
    assert default_trade_currency(item) == "any"
    query = build_search_query(item, "Reaver Sword")["query"]
    assert "trade_filters" not in query["filters"]


def test_consumable_craftable_item_defaults_to_chaos_and_divine():
    item = parse_item_text("""Item Class: Expedition Logbooks
Rarity: Rare
Test Logbook
Expedition Logbook
--------
Item Level: 83
""")
    assert item.category == "expedition_logbook"
    assert default_trade_currency(item) == "chaos_divine"
    query = build_search_query(item, trade_currency=default_trade_currency(item))["query"]
    assert query["filters"]["trade_filters"]["filters"]["price"] == {
        "option": "chaos_divine"
    }


def test_unique_item_defaults_to_any_currency_even_when_not_craftable():
    item = parse_item_text("""Item Class: Flasks
Rarity: Unique
Test Flask
Silver Flask
--------
Item Level: 80
""")
    assert default_trade_currency(item) == "any"


def test_all_supported_trade_currency_options_map_to_api_values():
    item = parse_item_text(ITEM)
    expected = {
        "chaos": "chaos", "divine": "divine", "chaos_divine": "chaos_divine",
    }
    for selected, api_value in expected.items():
        query = build_search_query(item, trade_currency=selected)["query"]
        assert query["filters"]["trade_filters"]["filters"]["price"]["option"] == api_value


def test_stat_filter_supports_maximum_exact_and_trade_inversion():
    item = parse_item_text(ITEM)
    filters = (
        TradeStatFilter("explicit.low", "低いほど良い", None, "suffix", True, 12),
        TradeStatFilter("explicit.exact", "完全一致", 3, "suffix", True, 3),
        TradeStatFilter("explicit.inverted", "API符号反転", 10, "suffix", True, 20, None, 1.0, True),
    )
    query = build_search_query(item, "Reaver Sword", filters)["query"]
    assert query["stats"][0]["filters"] == [
        {"id": "explicit.low", "value": {"max": 12}},
        {"id": "explicit.exact", "value": {"min": 3, "max": 3}},
        {"id": "explicit.inverted", "value": {"min": -20, "max": -10}},
    ]


def test_infamous_slower_rage_loss_uses_negative_faster_value():
    item = parse_item_text("""アイテムクラス: 兜
レアリティ: レア
恐ろしい堅塁
征服者のヘルメット
--------
アーマー: 615 (augmented)
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「悪名高い」 (ティア: 1) }
憤怒の固有効果による喪失が20%遅くなる
(この効果は直近にヒット受けていないか憤怒を獲得していない時の憤怒の減少にのみ影響を与える)
""")
    filters = resolve_trade_stat_filters(item)
    infamous = next(
        row for row in filters if row.stat_id == "explicit.stat_3645269560"
    )
    assert infamous.generation == "infamous"
    assert infamous.inverted is True
    assert unresolved_modifier_warnings(item, filters) == ()

    query = build_search_query(
        item, stat_filters=(replace(infamous, enabled=True),),
    )["query"]
    assert query["stats"][0]["filters"] == [{
        "id": "explicit.stat_3645269560",
        "value": {"max": -20.0},
    }]


def test_reduced_curse_effect_flask_uses_awakened_positive_minimum():
    item = parse_item_text("""アイテムクラス: ユーティリティフラスコ
レアリティ: マジック
医者の モッキングバードの 水銀のフラスコ
--------
アイテムレベル: 84
--------
{ サフィックスモッド 「モッキングバードの」 (ティア: 4) }
効果中にプレイヤーに対する呪いの効果が45(47-42)%減少する
""")
    filters = resolve_trade_stat_filters(item)
    curse = next(
        row for row in filters if row.stat_id == "explicit.stat_4265534424"
    )

    assert (curse.min_value, curse.max_value, curse.inverted) == (40.0, None, False)
    query = build_search_query(
        item, stat_filters=(replace(curse, enabled=True),),
    )["query"]
    assert query["stats"][0]["filters"] == [{
        "id": "explicit.stat_4265534424",
        "value": {"min": 40.0},
    }]


def test_high_item_level_unfinished_rare_has_finished_and_base_presets():
    item = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 85"))
    assert available_trade_presets(item) == (PRESET_FINISHED, PRESET_BASE)
    rows = resolve_trade_stat_filters(item, PRESET_BASE)
    by_id = {row.stat_id: row for row in rows}
    assert by_id["property.item_level"] == TradeStatFilter(
        "property.item_level", "アイテムレベル", 85.0, "base", True,
        read_value=85.0,
        selection_reason="クラフト価値のあるアイテムレベル",
    )
    assert not by_id["property.physical_dps"].enabled
    assert not by_id["property.aps"].enabled


def test_base_preset_uses_exact_base_nonunique_ilvl_and_craftable_state():
    item = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 88"))
    filters = resolve_trade_stat_filters(item, PRESET_BASE)
    query = build_search_query(
        item, "Reaver Sword", filters, preset=PRESET_BASE,
    )["query"]
    assert query["type"] == "Reaver Sword"
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "nonunique"}
    misc = query["filters"]["misc_filters"]["filters"]
    assert misc["ilvl"] == {"min": 86.0}
    assert misc["corrupted"] == {"option": "false"}
    assert misc["mirrored"] == {"option": "false"}
    assert query["stats"][0]["filters"] == []


def test_finished_or_low_level_items_do_not_offer_base_preset():
    low_level = parse_item_text(ITEM)
    crafted = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 85").replace(
        "74% increased Physical Damage", "+50 to maximum Life (crafted)",
    ))
    quality_20 = parse_item_text(ITEM.replace(
        "Physical Damage: 108-181 (augmented)",
        "Quality: +20% (augmented)\nPhysical Damage: 108-181 (augmented)",
    ).replace("Item Level: 67", "Item Level: 85"))
    corrupted = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 85").replace(
        "74% increased Physical Damage", "74% increased Physical Damage\nCorrupted",
    ))
    for item in (low_level, crafted, quality_20, corrupted):
        assert available_trade_presets(item) == (PRESET_FINISHED,)


def test_fractured_item_can_offer_base_preset_below_ilvl_82():
    item = parse_item_text(ITEM.replace(
        "74% increased Physical Damage",
        '{ Fractured Prefix Modifier }\n74% increased Physical Damage',
    ))
    entries = ({
        "id": "fractured.phys", "text": "#% increased Physical Damage", "type": "fractured",
    },)
    assert available_trade_presets(item) == (PRESET_FINISHED, PRESET_BASE)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item, PRESET_BASE)
    by_id = {row.stat_id: row for row in filters}
    assert by_id["property.item_level"].enabled
    assert by_id["fractured.phys"].enabled
    assert not by_id["property.physical_dps"].enabled
    assert not by_id["property.aps"].enabled
    query = build_search_query(item, "Reaver Sword", filters, preset=PRESET_BASE)["query"]
    misc = query["filters"]["misc_filters"]["filters"]
    assert misc["fractured_item"] == {"option": "true"}
    assert misc["synthesised_item"] == {"option": "false"}
    assert query["stats"][0]["filters"] == [
        {"id": "fractured.phys", "value": {"min": 74.0}},
    ]


def test_quality_twenty_fractured_armour_still_offers_base_preset():
    item = parse_item_text("""アイテムクラス: 靴
レアリティ: レア
腐敗した足取り
ウォーロックブーツ
--------
品質: +20% (augmented)
エナジーシールド: 194 (augmented)
--------
アイテムレベル: 85
--------
{ フラクチャー プレフィックスモッド「競技者の」 (ティア: 1) — ライフ }
最大ライフ +122(115-129)
--------
フラクチャーアイテム
""")
    entries = ({
        "id": "fractured.stat_3299347043",
        "text": "+# to maximum Life",
        "type": "fractured",
    },)

    assert available_trade_presets(item) == (PRESET_FINISHED, PRESET_BASE)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item, PRESET_BASE)

    fractured = next(
        row for row in filters
        if row.stat_id == "fractured.stat_3299347043"
    )
    assert fractured.enabled
    query = build_search_query(
        item, "Warlock Boots", filters, preset=PRESET_BASE,
    )["query"]
    assert query["filters"]["misc_filters"]["filters"]["fractured_item"] == {
        "option": "true",
    }
    assert query["stats"][0]["filters"] == [{
        "id": "fractured.stat_3299347043",
        "value": {"min": 122.0},
    }]


@pytest.mark.parametrize("blocked_flag", ("corrupted", "mirrored"))
def test_unmodifiable_fractured_item_does_not_offer_base_preset(blocked_flag):
    item = ParsedItem(
        "Body Armours", "Rare", "Test Mantle", "Vaal Regalia", "armour",
        item_level=85, flags=(blocked_flag,),
        modifiers=(
            ItemModifier(
                "+100 to maximum Life", (100,), kind="fractured",
                ref="+# to maximum Life", stat_id="fractured.life",
            ),
        ),
    )

    assert available_trade_presets(item) == (PRESET_FINISHED,)


@pytest.mark.parametrize("strong_flag", ("synthesised", "influence:elder"))
def test_crafted_item_with_strong_crafting_identity_offers_base_preset(
        strong_flag):
    item = ParsedItem(
        "Boots", "Rare", "Test Boots", "Warlock Boots", "armour",
        item_level=85, flags=(strong_flag,),
        modifiers=(
            ItemModifier(
                "+20 to maximum Energy Shield", (20,), kind="crafted",
                ref="+# to maximum Energy Shield", stat_id="crafted.es",
            ),
        ),
    )

    assert available_trade_presets(item) == (PRESET_FINISHED, PRESET_BASE)


def test_japanese_329_fractured_local_mod_uses_stat_id_when_trade_text_has_local_suffix():
    item = parse_item_text("""アイテムクラス: 手袋
レアリティ: レア
巻き込む前脚
賢者のグローブ
--------
エナジーシールド: 110 (augmented)
--------
アイテムレベル: 85
--------
{ フラクチャー プレフィックスモッド「恐れ知らずな」 (ティア: 3) — 防御, エナジーシールド }
エナジーシールドが74(68-79)%増加する
--------
フラクチャーアイテム
""")
    entries = ({
        "id": "fractured.stat_4015621042",
        "text": "エナジーシールドが#%増加する (ローカル)",
        "type": "fractured",
    },)

    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item, PRESET_BASE)

    fractured = next(row for row in filters if row.kind == "fractured")
    assert fractured.stat_id == "fractured.stat_4015621042"
    assert fractured.min_value == 74.0
    assert fractured.enabled is True

    query = build_search_query(
        item, "Sage's Gloves", filters, preset=PRESET_BASE,
    )["query"]
    misc = query["filters"]["misc_filters"]["filters"]
    assert misc["fractured_item"] == {"option": "true"}
    assert query["stats"][0]["filters"] == [{
        "id": "fractured.stat_4015621042",
        "value": {"min": 74.0},
    }]


def test_influenced_and_synthesised_items_add_strict_base_conditions():
    item = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 70").replace(
        "74% increased Physical Damage",
        "74% increased Physical Damage\nShaper Item\nElder Item\nSynthesised Item",
    ))
    assert available_trade_presets(item) == (PRESET_FINISHED, PRESET_BASE)
    filters = resolve_trade_stat_filters(item, PRESET_BASE)
    assert [(row.stat_id, row.enabled) for row in filters if row.enabled] == [
        ("property.item_level", True),
        ("pseudo.pseudo_has_shaper_influence", True),
        ("pseudo.pseudo_has_elder_influence", True),
    ]
    query = build_search_query(item, "Reaver Sword", filters, preset=PRESET_BASE)["query"]
    assert query["filters"]["misc_filters"]["filters"]["synthesised_item"] == {"option": "true"}
    assert query["filters"]["misc_filters"]["filters"]["fractured_item"] == {"option": "false"}
    assert query["stats"][0]["filters"] == [
        {"id": "pseudo.pseudo_has_shaper_influence", "value": {}},
        {"id": "pseudo.pseudo_has_elder_influence", "value": {}},
    ]


def test_rare_base_preset_does_not_keep_replaceable_explicit_mods_or_empty_slots():
    item = parse_item_text("""アイテムクラス: 指輪
レアリティ: レア
試作品
ルビーの指輪
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「健康な」 (ティア: 1) }
最大ライフ +100(90-100)
{ プレフィックスモッド「普通の」 (ティア: 3) }
最大マナ +50(45-55)
{ サフィックスモッド「火炎の」 (ティア: 2) }
火耐性 +40(36-41)%
""")
    entries = (
        {"id": "explicit.life", "text": "最大ライフ +#", "type": "explicit"},
        {"id": "explicit.mana", "text": "最大マナ +#", "type": "explicit"},
        {"id": "explicit.fire", "text": "火耐性 +#%", "type": "explicit"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item, PRESET_BASE)
    enabled = [(row.stat_id, row.min_value) for row in filters if row.enabled]
    assert enabled == [("property.item_level", 85.0)]
    assert not any(row.stat_id.startswith("explicit.") for row in filters)
    assert not any(row.kind == "craft" for row in filters)


def test_magic_base_preset_shows_all_explicit_mods_but_enables_only_t1_t2():
    item = parse_item_text("""Item Class: Rings
Rarity: Magic
Healthy Ruby Ring
Ruby Ring
--------
Item Level: 85
--------
{ Prefix Modifier (Tier: 1) }
+100 to maximum Life
{ Suffix Modifier (Tier: 3) }
+25% to Fire Resistance
""")
    entries = (
        {"id": "explicit.life", "text": "+# to maximum Life", "type": "explicit"},
        {"id": "explicit.fire", "text": "+#% to Fire Resistance", "type": "explicit"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item, PRESET_BASE)
    by_id = {row.stat_id: row for row in filters}
    assert by_id["explicit.life"].enabled is True
    assert by_id["explicit.fire"].enabled is False
    default_query = build_search_query(item, "Ruby Ring", filters, preset=PRESET_BASE)["query"]
    exact_query = build_search_query(
        item, "Ruby Ring", filters, preset=PRESET_BASE, magic_exact=True,
    )["query"]
    assert "type_filters" not in default_query["filters"]
    assert exact_query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "magic"}


def test_dedicated_exact_magic_flask_uses_nonunique_rarity_like_awakened():
    item = ParsedItem(
        "Utility Flasks", "Magic", "Test Flask", "Granite Flask", "flask",
        item_level=85,
    )

    default_query = build_search_query(item, "Granite Flask")["query"]
    magic_query = build_search_query(
        item, "Granite Flask", magic_exact=True,
    )["query"]

    assert default_query["filters"]["type_filters"]["filters"]["rarity"] == {
        "option": "nonunique",
    }
    assert magic_query["filters"]["type_filters"]["filters"]["rarity"] == {
        "option": "nonunique",
    }


@pytest.mark.parametrize("category", [
    "map", "memory_line", "heist_contract", "heist_blueprint",
    "tincture", "sanctum_relic", "charm", "idol",
])
def test_dedicated_exact_magic_items_exclude_uniques_like_awakened(category):
    item = ParsedItem(
        "Test Items", "Magic", "Test Item", "Test Base", category,
        item_level=85,
    )

    query = build_search_query(item, "Test Base")["query"]

    assert query["filters"]["type_filters"]["filters"]["rarity"] == {
        "option": "nonunique",
    }


def test_unique_flask_still_uses_unique_rarity():
    item = ParsedItem(
        "Utility Flasks", "Unique", "Kiara's Determination", "Silver Flask", "flask",
        item_level=85,
    )

    query = build_search_query(
        item, "Silver Flask", trade_name="Kiara's Determination",
    )["query"]

    assert query["filters"]["type_filters"]["filters"]["rarity"] == {
        "option": "unique",
    }


def test_nonexact_accessory_search_uses_item_class_category():
    cases = (
        ("Rings", "Ruby Ring", "accessory.ring"),
        ("指輪", "ルビーの指輪", "accessory.ring"),
        ("Amulets", "Gold Amulet", "accessory.amulet"),
        ("Belts", "Leather Belt", "accessory.belt"),
    )
    for item_class, base_type, expected_category in cases:
        item = ParsedItem(
            item_class=item_class, rarity="Rare", name=base_type,
            base_type=base_type, category="accessory", item_level=80,
        )
        query = build_search_query(
            item, base_type, (), preset=PRESET_FINISHED, exact_base_type=False,
        )["query"]
        assert "type" not in query
        assert query["filters"]["type_filters"]["filters"]["category"] == {
            "option": expected_category,
        }


def test_normal_unidentified_and_magic_abyss_do_not_offer_base_preset():
    normal = parse_item_text(ITEM.replace("Rarity: Rare", "Rarity: Normal").replace(
        "Storm Reach\nReaver Sword", "Reaver Sword",
    ).replace("Item Level: 67", "Item Level: 85"))
    unidentified = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 85").replace(
        "74% increased Physical Damage", "74% increased Physical Damage\nUnidentified",
    ))
    abyss = parse_item_text("""Item Class: Abyss Jewels
Rarity: Magic
Test Jewel
Searching Eye Jewel
--------
Item Level: 84
""")
    for item in (normal, unidentified, abyss):
        assert available_trade_presets(item) == (PRESET_FINISHED,)


@pytest.mark.parametrize(("strands", "expected_enabled"), (
    (59, False),
    (60, True),
    (64, True),
))
def test_base_preset_uses_awakened_memory_strands_threshold(
        strands, expected_enabled):
    item = parse_item_text(f"""Item Class: Two Hand Swords
Rarity: Rare
Test Sword
Reaver Sword
--------
Memory Strands: {strands}
--------
Item Level: 85
--------
+25% to Global Critical Strike Multiplier (implicit)
--------
{{ Enchant Modifier }}
10% increased Attack Speed
""")
    entries = (
        {"id": "implicit.crit", "text": "+#% to Global Critical Strike Multiplier", "type": "implicit"},
        {"id": "enchant.speed", "text": "#% increased Attack Speed", "type": "enchant"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item, PRESET_BASE)
    by_id = {row.stat_id: row for row in filters}
    assert by_id["implicit.crit"].enabled is True
    assert by_id["enchant.speed"].enabled is True
    assert by_id["property.memory_strands"].enabled is expected_enabled


def test_finished_preset_hides_memory_strands_even_above_threshold():
    item = parse_item_text("""Item Class: Rings
Rarity: Rare
Test Ring
Manifold Ring
--------
Memory Strands: 64
--------
Item Level: 86
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    strands = next(row for row in filters if row.stat_id == "property.memory_strands")
    assert strands.enabled is False
    assert strands.hidden_reason


def test_finished_preset_does_not_force_special_base_state():
    item = parse_item_text(ITEM.replace(
        "74% increased Physical Damage", "74% increased Physical Damage\nHunter Item",
    ))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item, PRESET_FINISHED)
    query = build_search_query(item, "Reaver Sword", filters, preset=PRESET_FINISHED)["query"]
    misc = query["filters"].get("misc_filters", {}).get("filters", {})
    assert "synthesised_item" not in misc
    assert "fractured_item" not in misc
    assert not any(
        row.get("id") == "pseudo.pseudo_has_hunter_influence"
        for row in query["stats"][0]["filters"]
    )


def test_mixed_weapon_selects_total_dps_and_dominant_component_only():
    item = parse_item_text(ITEM.replace(
        "Physical Damage: 108-181 (augmented)",
        "Physical Damage: 108-181 (augmented)\nElemental Damage: 10-20, 20-30",
    ))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    enabled = {row.stat_id: row.min_value for row in filters if row.enabled}
    assert "property.total_dps" in enabled
    assert "property.physical_dps" in enabled
    assert "property.elemental_dps" not in enabled
    assert round(elemental_dps(item), 2) == 69.6


def test_attack_weapon_property_order_and_defaults_match_awakened():
    item = parse_item_text(ITEM.replace(
        "Physical Damage: 108-181 (augmented)",
        "Physical Damage: 108-181 (augmented)\nElemental Damage: 10-20, 20-30",
    ).replace(
        "Attacks per Second: 1.74 (augmented)",
        "Attacks per Second: 1.74 (augmented)\nCritical Strike Chance: 6.00%",
    ))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        rows = resolve_trade_stat_filters(item)
    property_rows = [row for row in rows if row.stat_id in {
        "property.total_dps", "property.physical_dps", "property.elemental_dps",
        "property.aps", "property.crit",
    }]
    assert [row.stat_id for row in property_rows] == [
        "property.total_dps", "property.physical_dps", "property.aps", "property.crit",
    ]
    assert [row.enabled for row in property_rows] == [True, True, False, False]


def test_spell_weapon_order_and_gem_level_default_match_recommendation():
    item = parse_item_text("""Item Class: Wands
Rarity: Rare
Test Wand
Imbued Wand
--------
Critical Strike Chance: 7.00%
Attacks per Second: 1.50
--------
Item Level: 86
--------
+1 to Level of all Spell Skill Gems
80% increased Spell Damage
12% increased Cast Speed
20% increased Spell Critical Strike Chance
+60 to maximum Mana
""")
    entries = ({
        "id": "explicit.gem_level", "text": "+# to Level of all Spell Skill Gems",
        "type": "explicit",
    },)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        rows = resolve_trade_stat_filters(item)
    ids = [row.stat_id for row in rows]
    expected = [
        "explicit.gem_level",
        "pseudo.pseudo_increased_spell_damage",
        "pseudo.pseudo_total_cast_speed",
        "pseudo.pseudo_critical_strike_chance_for_spells",
        "pseudo.pseudo_total_mana",
    ]
    assert [stat_id for stat_id in ids if stat_id in expected] == expected
    assert next(row for row in rows if row.stat_id == "explicit.gem_level").enabled
    assert not any(
        row.enabled for row in rows
        if row.stat_id in set(expected) - {"explicit.gem_level"}
    )


def test_weapon_base_preset_shows_performance_properties_but_keeps_them_off():
    item = parse_item_text(ITEM.replace("Item Level: 67", "Item Level: 85"))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        rows = resolve_trade_stat_filters(item, PRESET_BASE)
    properties = [row for row in rows if row.stat_id in {
        "property.total_dps", "property.physical_dps", "property.elemental_dps",
        "property.aps", "property.crit",
    }]
    assert [row.stat_id for row in properties] == ["property.physical_dps", "property.aps"]
    assert not any(row.enabled for row in properties)


def test_non_physical_weapon_does_not_enable_pdps():
    item = parse_item_text(ITEM.replace("Two Hand Swords", "Wands"))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    assert not any(row.stat_id == "property.physical_dps" and row.enabled for row in filters)


def test_single_and_hybrid_armour_enable_every_present_defence():
    single = parse_item_text(ITEM.replace("Two Hand Swords", "Body Armours").replace(
        "Physical Damage: 108-181 (augmented)\nAttacks per Second: 1.74 (augmented)",
        "Armour: 1000",
    ))
    hybrid = parse_item_text(single.raw_text.replace("Armour: 1000", "Armour: 1000\nEvasion Rating: 500"))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        assert [(row.stat_id, row.min_value) for row in resolve_trade_stat_filters(single) if row.enabled] == [
            ("property.armour", 1080.0),
        ]
        assert [(row.stat_id, row.min_value) for row in resolve_trade_stat_filters(hybrid) if row.enabled] == [
            ("property.armour", 1080.0),
            ("property.evasion", 540.0),
        ]


def test_shield_finished_and_base_presets_use_armour_specific_order_and_defaults():
    item = parse_item_text("""アイテムクラス: 盾
レアリティ: レア
Test Guard
Cardinal Round Shield
--------
ブロック率: 25%
アーマー: 400
回避力: 300
エナジーシールド: 100
--------
アイテムレベル: 86
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        finished = resolve_trade_stat_filters(item)
        base = resolve_trade_stat_filters(item, PRESET_BASE)

    property_ids = {
        "property.block", "property.armour", "property.evasion",
        "property.energy_shield", "property.ward",
    }
    assert [row.stat_id for row in finished if row.stat_id in property_ids] == [
        "property.block", "property.armour", "property.evasion",
        "property.energy_shield",
    ]
    assert not next(
        row for row in finished if row.stat_id == "property.block"
    ).enabled
    assert all(
        row.enabled for row in finished
        if row.stat_id in property_ids and row.stat_id != "property.block"
    )
    assert not any(row.stat_id == "property.base_percentile" for row in finished)

    base_properties = [row for row in base if row.stat_id in property_ids]
    assert [row.stat_id for row in base_properties] == [
        "property.block", "property.armour", "property.evasion",
        "property.energy_shield",
    ]
    assert not any(row.enabled for row in base_properties)


def test_normal_armour_dedicated_base_search_uses_awakened_percentile_threshold():
    item = parse_item_text("""アイテムクラス: 盾
レアリティ: ノーマル
Cardinal Round Shield
--------
ブロック率: 25%
アーマー: 220
回避力: 220
--------
アイテムレベル: 86
""")
    filters = resolve_trade_stat_filters(item, trade_base_type="Cardinal Round Shield")
    by_id = {row.stat_id: row for row in filters}
    assert by_id["property.base_percentile"].enabled is False
    assert not by_id["property.block"].enabled
    assert not by_id["property.armour"].enabled
    assert not by_id["property.evasion"].enabled


def test_base_percentile_below_50_starts_off_in_base_preset():
    item = parse_item_text("""アイテムクラス: 盾
レアリティ: レア
Test Guard
Cardinal Round Shield
--------
ブロック率: 25%
アーマー: 220
回避力: 220
--------
アイテムレベル: 86
""")
    with patch("src.poetore.trade._base_defence_percentile", return_value=49.0):
        filters = resolve_trade_stat_filters(
            item, PRESET_BASE, trade_base_type="Cardinal Round Shield",
        )
    percentile = next(
        row for row in filters if row.stat_id == "property.base_percentile"
    )
    assert percentile.enabled is False


def test_quality_above_20_is_not_normalized_down():
    item = parse_item_text(ITEM.replace(
        "Two Hand Sword\nPhysical Damage", "Two Hand Sword\nQuality: +30% (augmented)\nPhysical Damage",
    ))
    assert physical_dps_at_20_quality(item) == physical_dps(item)


def test_quality_below_20_is_normalized_to_20():
    item = parse_item_text(ITEM.replace(
        "Two Hand Sword\nPhysical Damage", "Two Hand Sword\nQuality: +10% (augmented)\nPhysical Damage",
    ))
    expected = physical_dps(item) * 1.2 / 1.1
    assert round(physical_dps_at_20_quality(item), 4) == round(expected, 4)


def test_local_weapon_mods_are_replaced_by_property_filters():
    item = parse_item_text(ITEM.replace(
        "Attacks per Second: 1.74 (augmented)",
        "Attacks per Second: 1.74 (augmented)\nCritical Strike Chance: 5.50% (augmented)",
    ).replace(
        "74% increased Physical Damage",
        "74% increased Physical Damage\n16% increased Attack Speed\n25% increased Critical Strike Chance",
    ))
    entries = (
        {"id": "explicit.stat_1509134228", "text": "#% increased Physical Damage", "type": "explicit"},
        {"id": "explicit.stat_210067635", "text": "#% increased Attack Speed", "type": "explicit"},
        {"id": "explicit.stat_2375316951", "text": "#% increased Critical Strike Chance", "type": "explicit"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    ids = {row.stat_id for row in filters}
    assert "explicit.stat_1509134228" not in ids
    assert "explicit.stat_210067635" not in ids
    assert "explicit.stat_2375316951" not in ids
    assert {"property.physical_dps", "property.aps", "property.crit"} <= ids
    assert not next(row for row in filters if row.stat_id == "property.aps").enabled
    assert not next(row for row in filters if row.stat_id == "property.crit").enabled


def test_local_armour_mod_is_replaced_by_normalized_armour_property():
    item = parse_item_text(ITEM.replace("Two Hand Swords", "Body Armours").replace(
        "Physical Damage: 108-181 (augmented)\nAttacks per Second: 1.74 (augmented)",
        "Quality: +10% (augmented)\nArmour: 1000 (augmented)",
    ).replace("74% increased Physical Damage", "100% increased Armour"))
    entries = ({
        "id": "explicit.stat_1062208444", "text": "#% increased Armour", "type": "explicit",
    },)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert not any(row.stat_id == "explicit.stat_1062208444" for row in filters)
    armour = next(row for row in filters if row.stat_id == "property.armour")
    assert armour.min_value == 981.0


def test_armour_quality_20_recalculation_matches_awakened_with_flat_and_increased_mods():
    item = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Plate
Astral Plate
--------
Quality: +10% (augmented)
Armour: 1320 (augmented)
--------
Item Level: 86
--------
{ Prefix Modifier "Glorious" (Tier: 2) }
+100 to Armour
100% increased Armour
""")
    entries = (
        {"id": "explicit.flat_armour", "text": "+# to Armour", "type": "explicit"},
        {"id": "explicit.increased_armour", "text": "#% increased Armour", "type": "explicit"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        armour = next(
            row for row in resolve_trade_stat_filters(item)
            if row.stat_id == "property.armour"
        )

    # Awakened: base = 1320 / 1.10 / 2.00 - 100 = 500,
    # q20 = (500 + 100) * 2.00 * 1.20 = 1440, then relax by 10%.
    assert armour.min_value == 1296.0


def test_japanese_armour_energy_shield_hybrid_enables_both_properties():
    item = parse_item_text("""アイテムクラス: 鎧
レアリティ: レア
Kraken Pelt
Sacred Chainmail
--------
品質: +30% (augmented)
アーマー: 2940 (augmented)
エナジーシールド: 642 (augmented)
--------
アイテムレベル: 94
--------
{プレフィックスモッド「神々しい」}
アーマー +306(301-375)
最大エナジーシールド +80(73-80)
--------
スプリット
--------
クルセイダーアイテム
ウォーロードアイテム
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        enabled = {row.stat_id: row.min_value for row in resolve_trade_stat_filters(item) if row.enabled}
    assert enabled == {
        "property.armour": 2646.0,
        "property.energy_shield": 577.0,
        "property.quality": 30.0,
    }
    assert item.flags == ("split", "influence:crusader", "influence:warlord")


def test_armour_property_inherits_awakened_t1_t2_tags_from_local_mods():
    item = parse_item_text("""アイテムクラス: 鎧
レアリティ: レア
Test Mantle
Vaal Regalia
--------
エナジーシールド: 642 (augmented)
--------
アイテムレベル: 86
--------
{ プレフィックスモッド「輝く」 (ティア: 2) }
最大エナジーシールド +80(73-80)
{ プレフィックスモッド「聖なる」 (ティア: 1) }
エナジーシールドが120(111-120)%増加する
{ サフィックスモッド「知性の」 (ティア: 3) }
知性 +50(48-51)
""")
    filters = resolve_trade_stat_filters(item)
    energy_shield = next(row for row in filters if row.stat_id == "property.energy_shield")
    assert energy_shield.tier is None
    assert energy_shield.tier_tags == (1, 2)
    assert not any(
        row.stat_id in {"explicit.stat_3489782002", "explicit.stat_4015621042"}
        for row in filters
    )


def test_armour_base_percentile_block_and_memory_strands_build_official_filters(tmp_path, monkeypatch):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({
        "base_armour": {"sacred chainmail": {"ar": [723, 831]}}, "mods": [],
    }), encoding="utf-8")
    monkeypatch.setenv("POETORE_METADATA_PATH", str(metadata_path))
    item = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Plate
Sacred Chainmail
--------
Armour: 777
Chance to Block: 25%
Memory Strands: 70
--------
Item Level: 85
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(
            item, PRESET_BASE, trade_base_type="Sacred Chainmail",
        )
    by_id = {row.stat_id: row for row in filters}
    assert by_id["property.base_percentile"].read_value == 50.0
    assert by_id["property.base_percentile"].min_value == 45.0
    assert by_id["property.base_percentile"].enabled is True
    assert by_id["property.block"].enabled is False
    assert by_id["property.memory_strands"].min_value == 63.0
    assert by_id["property.memory_strands"].enabled is True
    query = build_search_query(item, "Sacred Chainmail", filters)["query"]["filters"]
    assert query["armour_filters"]["filters"]["base_defence_percentile"] == {"min": 45.0}
    assert query["misc_filters"]["filters"]["memory_level"] == {"min": 63.0}
    block_query = build_search_query(item, "Sacred Chainmail", (
        TradeStatFilter("property.block", "ブロック率", 22.5, "property", True),
    ))["query"]["filters"]
    assert block_query["armour_filters"]["filters"]["block"] == {"min": 22.5}


def test_base_percentile_removes_quality_and_local_increase_multiplicatively(tmp_path, monkeypatch):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({
        "base_armour": {"test armour": {"ar": [100, 200]}}, "mods": [],
    }), encoding="utf-8")
    monkeypatch.setenv("POETORE_METADATA_PATH", str(metadata_path))
    item = ParsedItem(
        item_class="Body Armours", rarity="Rare", name="Test", base_type="Test Armour",
        category="armour", properties={"Armour": "270", "Quality": "+20%"},
        modifiers=(ItemModifier(
            "50% increased Armour", values=(50.0,), ref="#% increased Armour",
        ),),
    )
    # 270 / 1.20 / 1.50 = 150。100～200の中央なので50 percentile。
    assert _base_defence_percentile(item, "Test Armour") == 50.0


def test_cluster_jewel_item_level_is_normalized_to_awakened_bracket():
    item = parse_item_text("""Item Class: Cluster Jewels
Rarity: Rare
Test Cluster
Large Cluster Jewel
--------
Item Level: 72
""")
    assert item.category == "cluster_jewel"
    assert available_trade_presets(item) == (PRESET_FINISHED, PRESET_BASE)
    filters = resolve_trade_stat_filters(item, PRESET_BASE)
    level = next(row for row in filters if row.stat_id == "property.item_level")
    assert (level.min_value, level.max_value) == (68.0, 74.0)
    query = build_search_query(item, "Large Cluster Jewel", filters, preset=PRESET_BASE)["query"]
    assert query["filters"]["misc_filters"]["filters"]["ilvl"] == {"min": 68.0, "max": 74.0}


def test_rare_cluster_notables_are_visible_off_for_finished_and_absent_from_base():
    item = parse_item_text("""アイテムクラス: ジュエル
レアリティ: レア
燦爛たる創傷
クラスタージュエル (中)
--------
アイテムレベル: 83
--------
パッシブスキルを4個追加する (enchant)
--------
{ プレフィックスモッド「特殊な」 (ティア: 1) }
パッシブスキルを1個追加: 優位の主張
{ プレフィックスモッド「特殊な」 (ティア: 1) — ライフ }
パッシブスキルを1個追加: 高くそびえる脅威
""")

    finished = resolve_trade_stat_filters(item, PRESET_FINISHED, "Medium Cluster Jewel")
    notables = {
        row.ref: row for row in finished
        if row.ref in {
            "1 Added Passive Skill is Assert Dominance",
            "1 Added Passive Skill is Towering Threat",
        }
    }
    assert set(notables) == {
        "1 Added Passive Skill is Assert Dominance",
        "1 Added Passive Skill is Towering Threat",
    }
    assert all(not row.enabled for row in notables.values())

    base = resolve_trade_stat_filters(item, PRESET_BASE, "Medium Cluster Jewel")
    assert not any(row.ref in notables for row in base)


@pytest.mark.parametrize(("base_type", "trade_base_type", "passive_count"), [
    ("クラスタージュエル (小)", "Small Cluster Jewel", 2),
    ("クラスタージュエル (大)", "Large Cluster Jewel", 8),
])
def test_optimal_cluster_passive_count_does_not_include_next_integer(
    base_type, trade_base_type, passive_count,
):
    item = parse_item_text(f"""アイテムクラス: ジュエル
レアリティ: ノーマル
{base_type}
--------
アイテムレベル: 84
--------
パッシブスキルを{passive_count}個追加する (enchant)
""")
    filters = resolve_trade_stat_filters(item)
    passive = next(row for row in filters if row.ref == "Adds # Passive Skills")
    assert (passive.min_value, passive.max_value, passive.enabled) == (
        None, float(passive_count), True,
    )

    query = build_search_query(item, trade_base_type, filters)["query"]
    sent = query["stats"][0]["filters"][0]
    assert sent == {
        "id": "enchant.stat_3086156145",
        "value": {"max": float(passive_count)},
    }

    ranged = apply_search_range(filters, 2, item)
    passive = next(row for row in ranged if row.ref == "Adds # Passive Skills")
    assert (passive.min_value, passive.max_value) == (
        None, float(passive_count),
    )
    ranged_query = build_search_query(item, trade_base_type, ranged)["query"]
    assert ranged_query["stats"][0]["filters"][0] == {
        "id": "enchant.stat_3086156145",
        "value": {"max": float(passive_count)},
    }


def test_nine_passive_large_cluster_searches_nine_or_more():
    item = parse_item_text("""アイテムクラス: ジュエル
レアリティ: ノーマル
クラスタージュエル (大)
--------
アイテムレベル: 84
--------
パッシブスキルを9個追加する (enchant)
""")
    filters = resolve_trade_stat_filters(item)
    passive = next(row for row in filters if row.ref == "Adds # Passive Skills")
    assert (passive.min_value, passive.max_value, passive.enabled) == (9.0, None, True)

    query = build_search_query(item, "Large Cluster Jewel", filters)["query"]
    assert query["stats"][0]["filters"][0] == {
        "id": "enchant.stat_3086156145",
        "value": {"min": 9.0},
    }

    ranged = apply_search_range(filters, 50, item)
    passive = next(row for row in ranged if row.ref == "Adds # Passive Skills")
    assert (passive.min_value, passive.max_value) == (9.0, None)


@pytest.mark.parametrize(("base_type", "english_base"), [
    ("クラスタージュエル (大)", "Large Cluster Jewel"),
    ("クラスタージュエル (中)", "Medium Cluster Jewel"),
    ("クラスタージュエル (小)", "Small Cluster Jewel"),
])
def test_japanese_cluster_jewel_class_keeps_exact_cluster_base(
    base_type, english_base,
):
    item = parse_item_text(f"""アイテムクラス: ジュエル
レアリティ: レア
試験品
{base_type}
--------
アイテムレベル: 84
""")
    assert item.category == "cluster_jewel"
    query = build_search_query(item, english_base)["query"]
    assert query["type"] == english_base
    assert query.get("filters", {}).get("type_filters", {}).get(
        "filters", {}
    ).get("category") is None


def test_magic_jewel_search_requires_magic_rarity_and_exact_corruption_state():
    item = parse_item_text("""Item Class: Jewels
Rarity: Magic
Healthy Crimson Jewel
Crimson Jewel
--------
Item Level: 84
""")
    assert item.category == "jewel"
    query = build_search_query(item, "Crimson Jewel")["query"]
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "magic"}
    assert query["filters"]["misc_filters"]["filters"]["corrupted"] == {"option": "false"}
    corrupted = parse_item_text(item.raw_text + "--------\nCorrupted\n")
    query = build_search_query(corrupted, "Crimson Jewel")["query"]
    assert query["filters"]["misc_filters"]["filters"]["corrupted"] == {"option": "true"}


def test_quality_sockets_and_item_states_are_added_to_finished_search():
    item = parse_item_text("""アイテムクラス: 鎧
レアリティ: レア
Kraken Pelt
Sacred Chainmail
--------
品質: +21% (augmented)
アーマー: 2940 (augmented)
ソケット: W-W-W-R-B-B
--------
アイテムレベル: 94
--------
コラプト状態
ミラー品
スプリット
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    details = {row.stat_id: (row.min_value, row.enabled) for row in filters}
    assert details["property.quality"] == (21.0, True)
    assert details["property.sockets"] == (6.0, True)
    assert details["property.links"] == (6.0, False)
    assert "property.white_sockets" not in details
    query = build_search_query(item, "Sacred Chainmail", filters)["query"]
    misc = query["filters"]["misc_filters"]["filters"]
    assert misc["quality"] == {"min": 21.0}
    assert "mirrored" not in misc
    assert "corrupted" not in misc
    assert "split" not in misc
    sockets = query["filters"]["socket_filters"]["filters"]
    assert sockets == {"sockets": {"min": 6}}
    assert query["stats"][0]["filters"] == []

    non_mirrored = build_search_query(
        item, "Sacred Chainmail", filters, include_mirrored=False,
    )["query"]
    assert non_mirrored["filters"]["misc_filters"]["filters"]["mirrored"] == {
        "option": "false"
    }


def test_mirrored_penumbra_ring_resolves_negative_direction_stats_like_awakened():
    item = parse_item_text(MIRRORED_PENUMBRA_RING)
    assert item.flags == ("mirrored",)
    filters = resolve_trade_stat_filters(item)
    by_id = {row.stat_id: row for row in filters}

    left_curse = by_id["implicit.stat_496053892"]
    assert (left_curse.min_value, left_curse.inverted) == (27.0, True)
    mana_on_kill = by_id["explicit.stat_1368271171"]
    assert (mana_on_kill.min_value, mana_on_kill.inverted) == (48.0, True)
    assert unresolved_modifier_warnings(item, filters) == ()

    selected = [
        replace(left_curse, enabled=True),
        replace(mana_on_kill, enabled=True),
    ]
    query = build_search_query(item, "Penumbra Ring", selected)["query"]
    assert query["stats"][0]["filters"] == [
        {"id": "implicit.stat_496053892", "value": {"max": -27.0}},
        {"id": "explicit.stat_1368271171", "value": {"max": -48.0}},
    ]
    # Awakenedと同じく、Mirrored品の初期状態は「Mirroredを許可」であり
    # mirrored=trueの完全一致条件は送らない。
    assert "mirrored" not in query["filters"]["misc_filters"]["filters"]
    non_mirrored = build_search_query(
        item, "Penumbra Ring", selected, include_mirrored=False,
    )["query"]
    assert non_mirrored["filters"]["misc_filters"]["filters"]["mirrored"] == {
        "option": "false"
    }


def test_finished_search_state_filters_can_exclude_or_include_items():
    item = parse_item_text(ITEM)
    excluded = build_search_query(
        item, include_corrupted=False, include_split=False,
    )["query"]["filters"]["misc_filters"]["filters"]
    assert excluded["corrupted"] == {"option": "false"}
    assert excluded["split"] == {"option": "false"}

    included = build_search_query(
        item, include_corrupted=True, include_split=True,
    )["query"]["filters"]["misc_filters"]["filters"]
    assert "corrupted" not in included
    assert "split" not in included

    corrupted_only = build_search_query(
        item, include_corrupted="only", include_split=True,
    )["query"]["filters"]["misc_filters"]["filters"]
    assert corrupted_only["corrupted"] == {"option": "true"}


def test_common_item_level_override_replaces_category_specific_range():
    item = parse_item_text(ITEM)
    bracket = TradeStatFilter(
        "property.item_level", "アイテムレベル帯", 84.0, "base", True,
        max_value=100.0,
    )
    query = build_search_query(item, stat_filters=(bracket,), item_level_min=82)["query"]
    assert query["filters"]["misc_filters"]["filters"]["ilvl"] == {"min": 82}


def test_common_item_level_range_override_replaces_category_specific_range():
    item = parse_item_text(ITEM)
    bracket = TradeStatFilter(
        "property.item_level", "アイテムレベル帯", 84.0, "base", True,
        max_value=100.0,
    )
    query = build_search_query(
        item, stat_filters=(bracket,), item_level_min=68, item_level_max=74,
    )["query"]
    assert query["filters"]["misc_filters"]["filters"]["ilvl"] == {
        "min": 68, "max": 74,
    }


@pytest.mark.parametrize("value", [0, 101])
def test_common_item_level_override_rejects_out_of_range_values(value):
    item = parse_item_text(ITEM)
    with pytest.raises(ValueError, match="1～100"):
        build_search_query(item, item_level_min=value)


def test_common_item_level_override_rejects_reversed_range():
    item = parse_item_text(ITEM)
    with pytest.raises(ValueError, match="最小値は最大値以下"):
        build_search_query(item, item_level_min=84, item_level_max=83)


def test_search_rejects_unknown_corruption_mode():
    item = parse_item_text(ITEM)
    with pytest.raises(ValueError, match="未対応のコラプト条件"):
        build_search_query(item, include_corrupted="invalid")


@pytest.mark.parametrize("category", [
    "map", "flask", "tincture", "heist_equipment", "sanctum_relic", "charm", "idol",
])
def test_special_category_explicit_corruption_filter_reaches_trade_query(category):
    item = ParsedItem(
        item_class="Test Items", rarity="Rare", name="Test Item",
        base_type="Test Item", category=category, raw_text=f"special:{category}",
    )
    corrupted = build_search_query(item, include_corrupted="only")["query"]
    uncorrupted = build_search_query(item, include_corrupted=False)["query"]
    both = build_search_query(item, include_corrupted=True)["query"]
    assert corrupted["filters"]["misc_filters"]["filters"]["corrupted"] == {
        "option": "true"
    }
    assert uncorrupted["filters"]["misc_filters"]["filters"]["corrupted"] == {
        "option": "false"
    }
    assert "corrupted" not in both.get("filters", {}).get(
        "misc_filters", {}
    ).get("filters", {})


def test_split_uncorrupted_item_defaults_to_uncorrupted_and_includes_split():
    item = parse_item_text(ITEM + "--------\nSplit\n")
    misc = build_search_query(item)["query"]["filters"]["misc_filters"]["filters"]
    assert misc["corrupted"] == {"option": "false"}
    assert "split" not in misc


def test_quality_20_and_non_six_socket_count_are_visible_but_not_preselected():
    item = parse_item_text(ITEM.replace(
        "Physical Damage: 108-181 (augmented)",
        "Quality: +20% (augmented)\nSockets: R-G B\nPhysical Damage: 108-181 (augmented)",
    ))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    details = {row.stat_id: row for row in filters}
    assert details["property.quality"].enabled is False
    assert details["property.sockets"].min_value == 3.0
    assert details["property.sockets"].enabled is False
    assert details["property.links"].min_value == 2.0
    assert details["property.links"].enabled is False


def test_armour_also_enables_general_life_pseudo():
    item = parse_item_text(ITEM.replace("Two Hand Swords", "Body Armours").replace(
        "Physical Damage: 108-181 (augmented)\nAttacks per Second: 1.74 (augmented)",
        "Armour: 1000",
    ).replace("74% increased Physical Damage", "+80 to maximum Life"))
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        enabled = {row.stat_id: row.min_value for row in resolve_trade_stat_filters(item) if row.enabled}
    assert enabled["property.armour"] == 1080.0
    assert enabled["pseudo.pseudo_total_life"] == 72.0


def test_weapon_strength_without_life_mod_does_not_create_life_pseudo():
    item = parse_item_text("""アイテムクラス: 両手斧
レアリティ: レア
恐怖の分割
ヴァールアックス
--------
物理ダメージ: 765-1316 (augmented)
クリティカル率: 5.00%
秒間アタック回数: 1.38 (augmented)
--------
アイテムレベル: 89
--------
{ サフィックスモッド 「結社の」 (ティア: 1) — アタック, 能力値 }
筋力および器用さ +25(25-28)
    """)
    filters = {row.stat_id: row for row in resolve_trade_stat_filters(item)}
    assert "pseudo.pseudo_total_life" not in filters
    assert filters["property.physical_dps"].enabled is True


def test_accessory_enables_aggregated_life_and_resistance_pseudos():
    item = parse_item_text("""Item Class: Rings
Rarity: Rare
Test Ring
Ruby Ring
--------
Item Level: 85
--------
+70 to maximum Life
+30% to Fire Resistance
+20% to Cold and Lightning Resistances
+10% to Chaos Resistance
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    enabled = {row.stat_id: row.min_value for row in filters if row.enabled}
    assert enabled == {
        "pseudo.pseudo_total_life": 63.0,
        "pseudo.pseudo_total_elemental_resistance": 63.0,
        "pseudo.pseudo_total_chaos_resistance": 9.0,
    }
    details = {row.stat_id: row for row in filters}
    elemental = details["pseudo.pseudo_total_elemental_resistance"]
    assert elemental.source_contributions == (30.0, 40.0)


def test_pseudo_source_contributions_include_attribute_conversion():
    item = parse_item_text("""Item Class: Amulets
Rarity: Rare
Test Amulet
Onyx Amulet
--------
Item Level: 85
--------
+70 to maximum Life
+60 to Strength
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        rows = {row.stat_id: row for row in resolve_trade_stat_filters(item)}
    life = rows["pseudo.pseudo_total_life"]
    assert life.source_texts == ("+70 to maximum Life", "+60 to Strength")
    assert life.source_contributions == (70.0, 30.0)


def test_attributes_alone_do_not_create_life_or_mana_pseudos():
    item = parse_item_text("""Item Class: Amulets
Rarity: Rare
Test Amulet
Onyx Amulet
--------
Item Level: 85
--------
+60 to Strength
+60 to Intelligence
""")

    rows = {row.stat_id: row for row in resolve_trade_stat_filters(item)}
    assert "pseudo.pseudo_total_life" not in rows
    assert "pseudo.pseudo_total_mana" not in rows


def test_accessory_finished_filters_use_requested_awakened_based_order():
    item = parse_item_text("""Item Class: Amulets
Rarity: Rare
Test Amulet
Onyx Amulet
--------
Item Level: 85
--------
+70 to maximum Life
+40 to maximum Energy Shield
+30% to Fire Resistance
+10% to Chaos Resistance
+20 to all Attributes
+60 to maximum Mana
12% increased Cast Speed
""")
    filters = resolve_trade_stat_filters(item)
    ids = [row.stat_id for row in filters]
    expected = [
        "pseudo.pseudo_total_life",
        "pseudo.pseudo_total_energy_shield",
        "pseudo.pseudo_total_elemental_resistance",
        "pseudo.pseudo_total_chaos_resistance",
        "pseudo.pseudo_total_all_attributes",
        "pseudo.pseudo_total_mana",
        "pseudo.pseudo_total_cast_speed",
    ]
    assert [stat_id for stat_id in ids if stat_id in expected] == expected
    enabled = {row.stat_id for row in filters if row.enabled}
    assert enabled & set(expected) == {
        "pseudo.pseudo_total_life",
        "pseudo.pseudo_total_elemental_resistance",
        "pseudo.pseudo_total_chaos_resistance",
    }


def test_quiver_category_search_uses_all_quivers():
    item = ParsedItem(
        item_class="Quivers", rarity="Rare", name="Test Quiver",
        base_type="Broadhead Arrow Quiver", category="accessory", item_level=86,
    )
    query = build_search_query(
        item, item.base_type, (), preset=PRESET_FINISHED, exact_base_type=False,
    )["query"]
    assert query["filters"]["type_filters"]["filters"]["category"] == {
        "option": "accessory.quiver",
    }


def test_pseudo_mods_cover_attributes_resources_speed_damage_crit_and_recovery():
    item = parse_item_text("""アイテムクラス: アミュレット
レアリティ: レア
試作品
ゴールドアミュレット
--------
アイテムレベル: 85
--------
全ての能力値 +20
最大マナ +60
最大エナジーシールド +40
キャストスピードが12%増加する
スペルダメージが30%増加する
火ダメージが25%増加する
グローバルクリティカルダメージ倍率 +35%
移動スピードが10%増加する
毎秒15のライフを自動回復する
マナ自動回復レートが40%増加する
""")
    filters = {row.stat_id: row for row in resolve_trade_stat_filters(item)}
    expected = {
        "pseudo.pseudo_total_all_attributes": 18.0,
        "pseudo.pseudo_total_mana": 63.0,
        "pseudo.pseudo_total_energy_shield": 36.0,
        "pseudo.pseudo_total_cast_speed": 10.0,
        "pseudo.pseudo_increased_spell_damage": 27.0,
        "pseudo.pseudo_increased_fire_damage": 22.0,
        "pseudo.pseudo_global_critical_strike_multiplier": 31.0,
        "pseudo.pseudo_increased_movement_speed": 9.0,
        "pseudo.pseudo_total_life_regen": 13.0,
        "pseudo.pseudo_increased_mana_regen": 36.0,
    }
    assert {stat_id: filters[stat_id].min_value for stat_id in expected} == expected
    assert "pseudo.pseudo_total_life" not in filters
    assert all(not filters[stat_id].enabled for stat_id in expected)
    assert all(row.kind == "pseudo" for row in filters.values())


def _pseudo_test_item(modifiers, category="accessory"):
    return ParsedItem(
        item_class="Rings", rarity="Rare", name="Test", base_type="Ring",
        category=category, item_level=85, modifiers=tuple(modifiers),
    )


def test_pseudo_replaces_more_general_damage_and_crit_groups():
    item = _pseudo_test_item((
        ItemModifier("", (20,), ref="#% increased Elemental Damage"),
        ItemModifier("", (30,), ref="#% increased Fire Damage"),
        ItemModifier("", (40,), ref="#% increased Burning Damage"),
        ItemModifier("", (10,), ref="#% increased Global Critical Strike Chance"),
        ItemModifier("", (25,), ref="#% increased Spell Critical Strike Chance"),
    ))
    rows = {row.stat_id: row for row in resolve_trade_stat_filters(item)}
    assert "pseudo.pseudo_increased_elemental_damage" not in rows
    assert "pseudo.pseudo_increased_fire_damage" not in rows
    assert rows["pseudo.pseudo_increased_burning_damage"].min_value == 81.0
    assert "pseudo.pseudo_global_critical_strike_chance" not in rows
    assert rows["pseudo.pseudo_critical_strike_chance_for_spells"].min_value == 31.0


def test_new_relational_pseudos_parse_from_japanese_detail_copy():
    item = parse_item_text("""アイテムクラス: アミュレット
レアリティ: レア
試作品
ゴールドアミュレット
--------
アイテムレベル: 85
--------
スペルのクリティカル率が25%増加する
アタックスキルの元素ダメージが30%増加する
燃焼ダメージが40%増加する
""")
    rows = {row.stat_id: row for row in resolve_trade_stat_filters(item)}
    assert rows["pseudo.pseudo_critical_strike_chance_for_spells"].min_value == 22.0
    assert rows["pseudo.pseudo_increased_elemental_damage_with_attack_skills"].min_value == 27.0
    assert rows["pseudo.pseudo_increased_burning_damage"].min_value == 36.0


def test_pseudo_group_output_is_independent_of_modifier_input_order():
    modifiers = (
        ItemModifier("", (20,), ref="+#% to Fire Resistance"),
        ItemModifier("", (35,), ref="+#% to Cold Resistance"),
        ItemModifier("", (10,), ref="+#% to Lightning Resistance"),
        ItemModifier("", (12,), ref="+# to Strength"),
        ItemModifier("", (30,), ref="+# to Dexterity"),
        ItemModifier("", (5,), ref="+# to Intelligence"),
    )
    forward = resolve_trade_stat_filters(_pseudo_test_item(modifiers))
    backward = resolve_trade_stat_filters(_pseudo_test_item(reversed(modifiers)))
    signature = lambda rows: tuple((row.stat_id, row.min_value, row.enabled) for row in rows)
    assert signature(forward) == signature(backward)
    ids = {row.stat_id for row in forward}
    assert ids & {
        "pseudo.pseudo_total_fire_resistance",
        "pseudo.pseudo_total_cold_resistance",
        "pseudo.pseudo_total_lightning_resistance",
    } == {"pseudo.pseudo_total_cold_resistance"}
    assert "pseudo.pseudo_total_intelligence" not in ids


def test_equal_elemental_resistances_do_not_leave_an_arbitrary_individual_pseudo():
    item = _pseudo_test_item((
        ItemModifier("", (20,), ref="+#% to Fire Resistance"),
        ItemModifier("", (20,), ref="+#% to Cold Resistance"),
    ))
    ids = {row.stat_id for row in resolve_trade_stat_filters(item)}
    assert not ids & {
        "pseudo.pseudo_total_fire_resistance",
        "pseudo.pseudo_total_cold_resistance",
        "pseudo.pseudo_total_lightning_resistance",
    }
    assert "pseudo.pseudo_total_elemental_resistance" in ids


def test_crafted_chaos_only_is_hidden_but_mixed_sources_are_aggregated():
    crafted = ItemModifier("", (16,), kind="crafted", ref="+#% to Chaos Resistance")
    assert "pseudo.pseudo_total_chaos_resistance" not in {
        row.stat_id for row in resolve_trade_stat_filters(_pseudo_test_item((crafted,)))
    }
    natural = ItemModifier("", (20,), ref="+#% to Fire and Chaos Resistances")
    rows = {row.stat_id: row for row in resolve_trade_stat_filters(
        _pseudo_test_item((crafted, natural))
    )}
    assert rows["pseudo.pseudo_total_chaos_resistance"].min_value == 32.0
    assert rows["pseudo.pseudo_total_chaos_resistance"].enabled is True


def test_unresolved_modifier_does_not_remove_unrelated_pseudos():
    item = _pseudo_test_item((
        ItemModifier("未解決Mod", (999,), ref=None, stat_id=None),
        ItemModifier("", (80,), ref="+# to maximum Life"),
        ItemModifier("", (30,), ref="+#% to Fire Resistance"),
    ))
    ids = {row.stat_id for row in resolve_trade_stat_filters(item)}
    assert "pseudo.pseudo_total_life" in ids
    assert "pseudo.pseudo_total_elemental_resistance" in ids


def test_enabled_stat_filter_is_added_with_editable_minimum():
    item = parse_item_text(ITEM)
    stat = TradeStatFilter("explicit.stat_1", "Physical", 74, "prefix", True)
    query = build_search_query(item, "Reaver Sword", (stat,))["query"]
    assert query["stats"][0]["filters"] == [
        {"id": "explicit.stat_1", "value": {"min": 74}},
    ]


def test_unique_search_uses_exact_english_name_and_hides_fixed_mods():
    item = parse_item_text("""Item Class: Amulets
Rarity: Unique
The Example
Gold Amulet
--------
Item Level: 70
--------
+40(30-50) to maximum Life
+10% to Fire Resistance
""")
    entries = (
        {"id": "explicit.life", "text": "+# to maximum Life", "type": "explicit"},
        {"id": "explicit.fire", "text": "+#% to Fire Resistance", "type": "explicit"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert filters[0] == TradeStatFilter(
        "explicit.life", "+40(30-50) to maximum Life", 38.0, "explicit", True,
        selection_reason="ユニークの可変Modが3個以下のため自動選択",
    )
    assert filters[1].stat_id == "explicit.fire"
    assert filters[1].hidden_reason == "ユニーク固定値のため初期非表示"
    query = build_search_query(item, "Gold Amulet", filters, trade_name="The Example")["query"]
    assert query["name"] == "The Example"
    assert query["type"] == "Gold Amulet"
    assert query["stats"][0]["filters"] == [
        {"id": "explicit.life", "value": {"min": 38.0}},
    ]


def test_unique_weapon_shows_aggregated_performance_properties():
    item = parse_item_text("""アイテムクラス: ルーンの短剣
レアリティ: ユニーク
ビノの包丁
屠殺のナイフ
--------
ルーンの短剣
物理ダメージ: 152-319 (augmented)
クリティカル率: 12.32% (augmented)
秒間アタック回数: 1.40
武器攻撃距離：1 メートル
--------
装備要求:
レベル: 65
器用さ: 81 (unmet)
知性: 117
--------
ソケット: W
--------
アイテムレベル: 84
--------
{ 暗黙モッド — クリティカル }
グローバルクリティカル率が45(40-45)%増加する
--------
{ ユニークモッド — ダメージ, 物理, アタック }
142(140-155)から233(210-235)の物理ダメージを追加する
{ ユニークモッド — 混沌, 耐性 }
混沌耐性 +29(17-29)%
{ ユニークモッド — ダメージ, クリティカル }
グローバルクリティカルダメージ倍率 +15(15-25)%
{ ユニークモッド — アタック, クリティカル }
クリティカル率が45(40-50)%増加する
{ ユニークモッド — ライフ, 混沌, 状態異常 }
毒状態の敵を倒すと3m以内の敵に毒を付与し
3m以内のプレイヤーと味方は毒の持続時間の間毎秒400ライフを自動回復する
--------
それを毒と呼ぶことはそもそもそれが
食べられるものだったということになる。
""")
    filters = resolve_trade_stat_filters(
        item, trade_base_type="Slaughter Knife", trade_name="Bino's Kitchen Knife",
    )
    properties = {
        row.stat_id: row for row in filters if row.kind == "property"
    }

    assert set(properties) >= {
        "property.physical_dps", "property.aps", "property.crit",
    }
    assert properties["property.physical_dps"].enabled is True
    assert properties["property.aps"].enabled is False
    assert properties["property.crit"].enabled is False
    # 品質表示がない武器は既存仕様どおり、比較可能な品質20%時へ正規化する。
    assert properties["property.physical_dps"].read_value == pytest.approx(395.64)
    assert not any(
        row.text == "142(140-155)から233(210-235)の物理ダメージを追加する"
        for row in filters
    )

    query = build_search_query(
        item, "Slaughter Knife", filters, trade_name="Bino's Kitchen Knife",
    )["query"]
    assert query["filters"]["weapon_filters"]["filters"]["pdps"] == {
        "min": properties["property.physical_dps"].min_value,
    }


def test_corrupted_unique_hidden_fixed_mutation_can_be_selected_exactly():
    item = parse_item_text("""アイテムクラス: 盾
レアリティ: ユニーク
ラスピスの球体
チタンスピリットシールド
--------
アイテムレベル: 83
--------
{ ユニークモッド — ダメージ, キャスター }
プレイヤーの最大ライフ100ごとにスペルダメージが4(3)%増加する
--------
コラプト状態
""")
    filters = resolve_trade_stat_filters(
        item, trade_base_type="Titanium Spirit Shield",
        trade_name="Rathpith Globe",
    )
    spell_damage = next(
        row for row in filters
        if row.stat_id == "explicit.stat_3491815140"
    )

    assert spell_damage.hidden_reason == "ユニーク固定値のため初期非表示"
    assert spell_damage.enabled is False
    assert spell_damage.min_value == 4
    assert spell_damage.max_value == 4

    selected = replace(spell_damage, enabled=True)
    query = build_search_query(
        item, "Titanium Spirit Shield", (selected,),
        trade_name="Rathpith Globe",
    )["query"]
    assert query["stats"][0]["filters"] == [{
        "id": "explicit.stat_3491815140",
        "value": {"min": 4, "max": 4},
    }]


def test_unique_with_more_than_three_variable_mods_does_not_preselect_all():
    labels = ("Alpha", "Beta", "Gamma", "Delta")
    body = "\n".join(
        f"+{value}({value - 5}-{value + 5}) to {label}"
        for label, value in zip(labels, (20, 30, 40, 50))
    )
    item = parse_item_text(f"""Item Class: Belts
Rarity: Unique
Many Rolls
Heavy Belt
--------
Item Level: 70
--------
{body}
""")
    entries = tuple(
        {"id": f"explicit.stat_{index}", "text": f"+# to {label}", "type": "explicit"}
        for index, label in enumerate(labels)
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert len(filters) == 4
    assert not any(row.enabled for row in filters)


def test_watchers_eye_uses_awakened_fixed_stats_and_keeps_unscalable_variant():
    item = parse_item_text("""アイテムクラス: ジュエル
レアリティ: ユニーク
Watcher's Eye
Prismatic Jewel
--------
アイテムレベル: 86
--------
{ ユニークモッド — ライフ }
最大ライフが6(4-6)%増加する
{ ユニークモッド — キャスター, 呪い }
ヘイストの影響を受けている時にテンポラルチェーンの影響を受けない — スケールできない値
(Unaffected: 影響を受けない場合でも、デバフがかけられるが、それによる効果は表れない)
""")
    entries = (
        {
            "id": "explicit.stat_983749596",
            "text": "最大ライフが#%増加する",
            "type": "explicit",
        },
        {
            "id": "explicit.stat_2806391472",
            "text": "ヘイストの影響を受けている時にテンポラルチェーンの影響を受けない",
            "type": "explicit",
        },
    )
    fixed = frozenset({"#% increased maximum Life"})
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries), patch(
        "src.poetore.trade.unique_fixed_stats", return_value=fixed
    ):
        filters = resolve_trade_stat_filters(item)
    assert [row.stat_id for row in filters] == [
        "explicit.stat_983749596",
        "explicit.stat_2806391472",
    ]
    assert filters[0].min_value == 6.0
    assert filters[1].min_value is None
    assert all(row.enabled for row in filters if not row.hidden_reason)
    assert all(not row.enabled for row in filters if row.hidden_reason)


def test_unidentified_unique_query_requires_unidentified_state():
    item = parse_item_text("""Item Class: Amulets
Rarity: Unique
Gold Amulet
--------
Item Level: 70
--------
Unidentified
""")
    assert item.name == item.base_type == "Gold Amulet"
    query = build_search_query(item, "Gold Amulet", trade_name="The Example")["query"]
    assert query["name"] == "The Example"
    assert query["filters"]["misc_filters"]["filters"]["identified"] == {"option": "false"}
    relaxed = build_search_query(
        item, "Gold Amulet", trade_name="The Example", include_unidentified=False,
    )["query"]
    assert "identified" not in relaxed.get("filters", {}).get("misc_filters", {}).get("filters", {})


def test_unique_candidates_come_from_official_item_data():
    payload = {"result": [{"entries": [
        {"name": "The Example", "type": "Gold Amulet", "flags": {"unique": True}},
        {"name": "Another Example", "type": "Gold Amulet", "flags": {"unique": True}},
        {"name": "Not Unique", "type": "Gold Amulet", "flags": {}},
    ]}]}
    with patch("src.poetore.trade._item_entries_cache", None), patch(
        "src.poetore.trade._request_json", return_value=(payload, {}),
    ):
        assert unique_candidates("Gold Amulet") == ("Another Example", "The Example")


def test_unique_candidate_details_include_official_icon_urls():
    payload = {"result": [{"entries": [
        {"name": "The Example", "type": "Gold Amulet", "flags": {"unique": True}},
    ]}]}
    with patch("src.poetore.trade._item_entries_cache", None), patch(
        "src.poetore.trade._request_json", return_value=(payload, {}),
    ), patch(
        "src.poetore.trade.unique_icon_url",
        return_value="https://web.poecdn.com/example.png",
    ), patch(
        "src.poetore.trade._japanese_trade_item_name",
        return_value="日本語の例",
    ):
        assert unique_candidate_details("Gold Amulet") == (
            UniqueCandidate(
                "The Example",
                "https://web.poecdn.com/example.png",
                "日本語の例",
            ),
        )


def test_unique_candidate_details_fall_back_to_wiki_icon_and_english_name():
    payload = {"result": [{"entries": [
        {"name": "The Example", "type": "Gold Amulet", "flags": {"unique": True}},
    ]}]}
    with patch("src.poetore.trade._item_entries_cache", None), patch(
        "src.poetore.trade._request_json", return_value=(payload, {}),
    ), patch(
        "src.poetore.trade.unique_icon_url", return_value=None,
    ), patch(
        "src.poetore.trade._japanese_trade_item_name", return_value=None,
    ):
        assert unique_candidate_details("Gold Amulet") == (
            UniqueCandidate(
                "The Example",
                "https://www.poewiki.net/wiki/Special:Redirect/file/"
                "The_Example_inventory_icon.png",
                "The Example",
            ),
        )


def test_unique_variants_preserve_trade_discriminator():
    entries = (
        {"name": "Auxium", "type": "Chain Belt", "text": "Auxium Chain Belt", "flags": {"unique": True}},
        {"name": "Auxium", "type": "Chain Belt", "text": "Auxium Chain Belt (Legacy)", "disc": "legacy", "flags": {"unique": True}},
    )
    with patch("src.poetore.trade._item_entries_cache", entries):
        assert unique_variants("Auxium", "Chain Belt") == (
            ("Auxium Chain Belt", None), ("Auxium Chain Belt (Legacy)", "legacy"),
        )


def test_unique_variant_foil_and_foulborn_conditions_are_sent_exactly():
    foil = parse_item_text("""Item Class: Belts
Rarity: Unique
Auxium
Chain Belt
--------
Item Level: 70
--------
Foil
""")
    query = build_search_query(
        foil, "Chain Belt", trade_name="Auxium", trade_discriminator="legacy",
    )["query"]
    assert query["name"] == {"option": "Auxium", "discriminator": "legacy"}
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "uniquefoil"}

    plain_unique = build_search_query(
        foil, "Chain Belt", trade_name="Auxium", include_foil=False,
    )["query"]
    assert plain_unique["filters"]["type_filters"]["filters"]["rarity"] == {
        "option": "unique"
    }
    assert query["filters"]["misc_filters"]["filters"]["foulborn_item"] == {"option": "false"}

    foulborn = parse_item_text(foil.raw_text.replace("Foil", "Foulborn"))
    misc = build_search_query(foulborn, "Chain Belt", trade_name="Auxium")["query"]["filters"]["misc_filters"]["filters"]
    assert "foulborn_item" not in misc


def test_foulborn_unique_keeps_all_variable_explicit_mods_as_filters():
    item = parse_item_text("""アイテムクラス: 指輪
レアリティ: ユニーク
Foulborn Le Heup of All
Iron Ring
--------
アイテムレベル: 83
--------
{ 暗黙モッド }
1から4の物理ダメージをアタックに追加する
--------
{ ユニークモッド — 能力値 }
全ての能力値 +22(10-30)
{ ユニークモッド — 元素, 耐性 }
全ての元素耐性 +29(10-30)%
{ ユニークモッド — ドロップ }
見つかるアイテムのレアリティが16(10-30)%増加する
{ ファウルボーンユニークモッド — 防御 }
グローバル防御力が16(10-30)%増加する
""")
    filters = resolve_trade_stat_filters(item)
    assert item.name == "Le Heup of All"
    assert {row.stat_id for row in filters} >= {
        "explicit.stat_1379411836",
        "explicit.stat_2901986750",
        "explicit.stat_3917489142",
        "explicit.stat_1389153006",
    }
    assert all(row.enabled for row in filters if not row.hidden_reason)
    assert all(not row.enabled for row in filters if row.hidden_reason)
    query = build_search_query(
        item, "Iron Ring", trade_name=item.name,
        stat_filters=filters,
    )["query"]
    assert query["name"] == "Le Heup of All"
    assert "foulborn_item" not in query["filters"]["misc_filters"]["filters"]


def test_foulborn_unique_keeps_fixed_replacement_mod_as_enabled_filter():
    item = parse_item_text("""アイテムクラス: 鉤爪
レアリティ: ユニーク
ファウルボーン 思考と動作の手
帝国の鉤爪
--------
アイテムレベル: 85
--------
{ ユニークモッド — 能力値 }
知性が12(8-12)%増加する
{ ユニークモッド — 能力値 }
器用さが11(8-12)%増加する
{ ファウルボーンユニークモッド }
知性25ごとに命中力が3%増加する
""")

    filters = resolve_trade_stat_filters(item)
    accuracy = next(
        row for row in filters
        if row.stat_id == "explicit.stat_4106889136"
    )

    assert accuracy.text == "知性25ごとに命中力が3%増加する"
    assert accuracy.min_value == 3
    assert accuracy.read_value == 3
    assert accuracy.generation == "foulborn"
    assert accuracy.enabled

    query = build_search_query(
        item, "Imperial Claw", trade_name="Hand of Thought and Motion",
        stat_filters=filters,
    )["query"]
    query_filter = next(
        row for row in query["stats"][0]["filters"]
        if row["id"] == "explicit.stat_4106889136"
    )
    assert query_filter["value"] == {"min": 3}


def test_foulborn_unique_localizes_name_for_japanese_trade_link():
    _trade_response_cache.clear()
    item = parse_item_text("""アイテムクラス: 指輪
レアリティ: ユニーク
Foulborn Le Heup of All
Iron Ring
--------
アイテムレベル: 83
--------
{ ユニークモッド — 能力値 }
全ての能力値 +22(10-30)
{ ユニークモッド — 元素, 耐性 }
全ての元素耐性 +29(10-30)%
{ ユニークモッド — ドロップ }
見つかるアイテムのレアリティが16(10-30)%増加する
{ ファウルボーンユニークモッド — 防御 }
グローバル防御力が16(10-30)%増加する
""")
    filters = resolve_trade_stat_filters(
        item, trade_base_type="Iron Ring", trade_name=item.name,
    )
    response = ({"id": "foulborn-query", "result": [], "total": 0}, {})
    with patch("src.poetore.trade._request_json", return_value=response), patch(
        "src.poetore.trade._japanese_trade_item_type", return_value="鉄の指輪",
    ), patch(
        "src.poetore.trade._japanese_trade_item_name", return_value="皆を繋ぐもの",
    ):
        result = search_prices(
            item, "Iron Ring", "Standard", stat_filters=filters,
            trade_name=item.name,
        )

    web_query = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])["query"]
    assert web_query["name"] == "皆を繋ぐもの"
    assert web_query["type"] == "鉄の指輪"
    assert len(web_query["stats"][0]["filters"]) == 4


def test_foulborn_repentance_uses_normal_unique_name_in_japanese_trade_link():
    _trade_response_cache.clear()
    item = parse_item_text("""アイテムクラス: 手袋
レアリティ: ユニーク
Foulborn Repentance
Crusader Gloves
--------
品質: +20% (augmented)
アーマー: 920 (augmented)
エナジーシールド: 185 (augmented)
--------
装備要求:
レベル: 66
筋力: 306 (augmented) (unmet)
知性: 306 (augmented)
--------
ソケット: B-B-B B
--------
アイテムレベル: 81
--------
{ ユニークモッド — キャスター }
アイアンウィル — スケールできない値
{ ユニークモッド — 防御, アーマー, エナジーシールド }
アーマーおよびエナジーシールドが472(400-500)%増加する
{ ユニークモッド }
要求能力値が500%増加する
{ ファウルボーンユニークモッド — 能力値 }
知性が16(12-16)%増加する
""")
    assert item.name == "Repentance"
    filters = resolve_trade_stat_filters(
        item, trade_base_type="Crusader Gloves", trade_name=item.name,
    )
    response = ({"id": "foulborn-repentance", "result": [], "total": 0}, {})
    with patch("src.poetore.trade._request_json", return_value=response), patch(
        "src.poetore.trade._japanese_trade_item_type", return_value="聖戦士のグローブ",
    ), patch(
        "src.poetore.trade._japanese_trade_item_name", return_value="悔恨",
    ):
        result = search_prices(
            item, "Crusader Gloves", "Standard", stat_filters=filters,
            trade_name=item.name,
        )

    web_query = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])["query"]
    assert web_query["name"] == "悔恨"
    assert web_query["type"] == "聖戦士のグローブ"
    assert any(
        row["id"] == "explicit.stat_656461285"
        for row in web_query["stats"][0]["filters"]
    )


def test_replica_dragonfang_uses_distinct_reservation_and_requirements_filters():
    item = parse_item_text("""アイテムクラス: アミュレット
レアリティ: ユニーク
Replica Dragonfang's Flight
Onyx Amulet
--------
アイテムレベル: 83
--------
{ 暗黙モッド — 能力値 }
全ての能力値 +15(10-16)
--------
{ ユニークモッド — 元素, 耐性 }
全ての元素耐性 +6(5-10)%
{ ユニークモッド }
スキルのリザーブ効率が6(5-10)%増加する
{ ユニークモッド }
アイテムおよびジェムの要求能力値が8(10-5)%減少する
""")
    filters = resolve_trade_stat_filters(item)
    by_id = {row.stat_id: row for row in filters}
    assert set(by_id) == {
        "implicit.stat_1379411836",
        "explicit.stat_2901986750",
        "explicit.stat_2587176568",
        "explicit.stat_752930724",
    }
    assert by_id["explicit.stat_2587176568"].text.startswith("スキルのリザーブ効率")
    requirements = by_id["explicit.stat_752930724"]
    assert requirements.text.startswith("アイテムおよびジェムの要求能力値")
    assert requirements.min_value == 7.0
    assert requirements.inverted is True

    query = build_search_query(
        item, "Onyx Amulet", trade_name="Replica Dragonfang's Flight",
        stat_filters=tuple(replace(
            row, enabled=row.stat_id in {
                "explicit.stat_2587176568", "explicit.stat_752930724",
            },
        ) for row in filters),
    )["query"]
    stat_filters = [
        row for group in query["stats"] for row in group["filters"]
    ]
    by_query_id = {row["id"]: row["value"] for row in stat_filters}
    assert by_query_id["explicit.stat_2587176568"] == {"min": 5.0}
    assert by_query_id["explicit.stat_752930724"] == {"max": -7.0}


def test_replica_dragonfang_flavour_text_is_not_an_unresolved_modifier():
    item = parse_item_text("""アイテムクラス: アミュレット
レアリティ: ユニーク
Replica Dragonfang's Flight
Onyx Amulet
--------
アイテムレベル: 83
--------
{ ユニークモッド }
全てのブライト(ファイヤーボール-ディバインブラスト)ジェムのレベル +3
{ ユニークモッド }
スキルのリザーブ効率が6(5-10)%増加する
--------
「私たちがこれを作ったのですか？何故記録がないのでしょう？
何かが起こると警告はされていましたが……」
―管理者クォトラ
""")
    assert unresolved_modifier_warnings(item) == (
        "全てのブライト(ファイヤーボール-ディバインブラスト)ジェムのレベル +3",
    )


def test_svalinn_fixed_lucky_block_is_not_an_unresolved_modifier():
    item = parse_item_text("""アイテムクラス: 盾
レアリティ: ユニーク
Svalinn
Girded Tower Shield
--------
品質: +12% (augmented)
ブロック率: 23%
アーマー: 458 (augmented)
ワード: 138 (augmented)
--------
ソケット: R-R-R
--------
アイテムレベル: 86
--------
{ 暗黙モッド — ライフ }
最大ライフ +20(10-20)
--------
{ ユニークモッド }
スペルブロック率が15(10-15)%
{ ユニークモッド — 防御 }
ワード +123(100-150)
{ ユニークモッド }
アタックブロック率の最大値 -10%
{ ユニークモッド }
スペルブロック率の最大値 -10%
{ ユニークモッド }
ブロック確率が幸運になる
(Lucky: 幸運は2度試行し、良いほうの結果を用いる)
{ ユニークモッド — キャスター, ジェム }
ブロック時にソケットされた元素スペルをトリガーする。クールダウンは0.25秒 — スケールできない値
""")
    filters = resolve_trade_stat_filters(item, trade_name="Svalinn")

    assert unique_fixed_stats("Svalinn") is None
    assert unresolved_modifier_warnings(item, filters) == ()


def test_dawnbreaker_shield_block_mod_uses_shield_specific_trade_stat():
    item = parse_item_text("""アイテムクラス: 盾
レアリティ: ユニーク
ドーンブレイカー
巨大なタワーシールド
--------
ブロック率: 45% (augmented)
アーマー: 2003 (augmented)
--------
アイテムレベル: 86
--------
{ 暗黙モッド — ライフ }
最大ライフ +17(10-20)
--------
{ ユニークモッド }
ブロック率 +22(20-25)%
""")
    filters = resolve_trade_stat_filters(item, trade_name="Dawnbreaker")

    block_modifier = next(
        modifier for modifier in item.modifiers
        if modifier.text == "ブロック率 +22(20-25)%"
    )
    assert block_modifier.stat_id == "explicit.stat_4253454700"
    assert any(row.stat_id == "property.block" for row in filters)
    block_filter = next(
        row for row in filters
        if row.stat_id == "explicit.stat_4253454700"
    )
    assert block_filter.text == "ブロック率 +22(20-25)%"
    assert block_filter.min_value == 21
    assert block_filter.hidden_reason == ""
    assert unresolved_modifier_warnings(item, filters) == ()


def test_sparse_item_with_crafted_affix_is_not_a_one_slot_finished_item():
    item = parse_item_text("""アイテムクラス: 指輪
レアリティ: レア
試作品
ルビーの指輪
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「健康な」 (ティア: 1) }
最大ライフ +100(90-100)
{ マスタークラフト サフィックスモッド「製作の」 }
火耐性 +20%
""")
    empty = {row.stat_id: row.text for row in resolve_trade_stat_filters(item) if row.kind == "craft"}
    assert empty == {}


def test_six_mod_item_with_crafted_suffix_offers_empty_suffix_like_awakened():
    item = parse_item_text("""アイテムクラス: 指輪
レアリティ: レア
試作品
ルビーの指輪
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「健康な」 (ティア: 1) }
最大ライフ +100(90-100)
{ プレフィックスモッド「強固な」 (ティア: 1) }
最大エナジーシールド +50(40-50)
{ プレフィックスモッド「頑丈な」 (ティア: 1) }
アーマー +100(90-100)
{ サフィックスモッド 「炎の」 (ティア: 1) }
火耐性 +40(36-40)%
{ サフィックスモッド 「氷の」 (ティア: 1) }
冷気耐性 +40(36-40)%
{ マスタークラフト サフィックスモッド「製作の」 }
雷耐性 +20%
""")
    empty = {row.stat_id: row.text for row in resolve_trade_stat_filters(item) if row.kind == "craft"}
    assert empty == {
        "pseudo.pseudo_number_of_empty_suffix_mods": "空きSuffix枠（現在1枠）",
    }


def test_four_mod_item_without_craft_does_not_offer_empty_affix_like_awakened():
    modifiers = tuple(
        ItemModifier(f"Prefix {index}", kind="prefix", affix="prefix", group=index)
        for index in range(2)
    ) + tuple(
        ItemModifier(f"Suffix {index}", kind="suffix", affix="suffix", group=100 + index)
        for index in range(2)
    )
    item = ParsedItem(
        item_class="Rings", rarity="Rare", name="Test", base_type="Ruby Ring",
        category="accessory", modifiers=modifiers,
    )
    assert not any(row.kind == "craft" for row in resolve_trade_stat_filters(item))


def test_rare_jewel_uses_two_prefix_and_two_suffix_limits():
    item = parse_item_text("""アイテムクラス: ジュエル
レアリティ: レア
Dusk Scar
Crimson Jewel
--------
アイテムレベル: 83
--------
{ プレフィックスモッド「轟く」 (ティア: 1) }
雷スキルのクリティカル率が14%増加する
{ プレフィックスモッド「電流の」 (ティア: 1) }
雷スキルのクリティカルダメージ倍率 +16%
{ サフィックスモッド 「抵抗力の」 (ティア: 1) }
全ての元素耐性 +9%
--------
パッシブツリーで割り当てられたジュエルソケットにはめる。右クリックしてソケットから取り外すことができる。
""")
    empty = {row.stat_id: row.text for row in resolve_trade_stat_filters(item) if row.kind == "craft"}
    assert empty == {
        "pseudo.pseudo_number_of_empty_suffix_mods": "空きSuffix枠（現在1枠）",
    }


@pytest.mark.parametrize(
    ("category", "base_type", "prefixes", "suffixes", "expected_stat"),
    (
        ("accessory", "Cogwork Ring", 1, 4, "pseudo.pseudo_number_of_empty_prefix_mods"),
        ("accessory", "Geodesic Ring", 4, 1, "pseudo.pseudo_number_of_empty_suffix_mods"),
        ("accessory", "Manifold Ring", 3, 1, "pseudo.pseudo_number_of_empty_prefix_mods"),
        ("accessory", "Helical Ring", 1, 3, "pseudo.pseudo_number_of_empty_suffix_mods"),
        ("accessory", "Simplex Amulet", 1, 1, "pseudo.pseudo_number_of_empty_suffix_mods"),
        ("accessory", "Focused Amulet", 1, 1, "pseudo.pseudo_number_of_empty_prefix_mods"),
        ("abyss_jewel", "Ghastly Eye Jewel", 2, 1, "pseudo.pseudo_number_of_empty_suffix_mods"),
        ("cluster_jewel", "Large Cluster Jewel", 1, 2, "pseudo.pseudo_number_of_empty_prefix_mods"),
        ("map", "Strand Map", 3, 2, "pseudo.pseudo_number_of_empty_suffix_mods"),
    ),
)
def test_empty_affixes_use_category_and_special_base_limits(
    category, base_type, prefixes, suffixes, expected_stat,
):
    modifiers = tuple(
        ItemModifier(f"Prefix {index}", kind="prefix", affix="prefix", group=index)
        for index in range(prefixes)
    ) + tuple(
        ItemModifier(f"Suffix {index}", kind="suffix", affix="suffix", group=100 + index)
        for index in range(suffixes)
    )
    item = ParsedItem(
        item_class="Test", rarity="Rare", name="Test", base_type=base_type,
        category=category, modifiers=modifiers,
    )
    empty = {
        row.stat_id: int(row.text.removesuffix("枠）").rsplit("現在", 1)[1])
        for row in resolve_trade_stat_filters(item, trade_base_type=base_type)
        if row.kind == "craft"
    }
    assert empty == {expected_stat: 1}


@pytest.mark.parametrize("flag", ("corrupted", "mirrored"))
def test_uncraftable_rare_items_do_not_offer_empty_affix_filters(flag):
    item = ParsedItem(
        item_class="Rings", rarity="Rare", name="Test", base_type="Ruby Ring",
        category="accessory",
        modifiers=(
            ItemModifier("Prefix", kind="prefix", affix="prefix", group=1),
            ItemModifier("Suffix", kind="suffix", affix="suffix", group=2),
        ),
        flags=(flag,),
    )
    assert not any(
        row.kind == "craft" for row in resolve_trade_stat_filters(item)
    )


def test_magic_flask_does_not_offer_rare_empty_affix_filters():
    item = ParsedItem(
        item_class="Utility Flasks", rarity="Magic", name="Test",
        base_type="Granite Flask", category="flask",
        modifiers=(ItemModifier("Prefix", kind="prefix", affix="prefix", group=1),),
    )
    assert not any(
        row.kind == "craft" for row in resolve_trade_stat_filters(item)
    )


def test_trade_status_modes_map_to_official_api_options():
    item = parse_item_text(ITEM)
    assert build_search_query(item, trade_status="instant")["query"]["status"] == {"option": "securable"}
    assert build_search_query(item, trade_status="available")["query"]["status"] == {"option": "available"}
    assert build_search_query(item, trade_status="online")["query"]["status"] == {"option": "online"}


def test_unknown_trade_status_is_rejected():
    item = parse_item_text(ITEM)
    try:
        build_search_query(item, trade_status="carrier_pigeon")
    except ValueError as exc:
        assert "未対応の取引方式" in str(exc)
    else:
        raise AssertionError("unknown trade status was accepted")


def test_offline_and_listing_age_are_sent_to_trade_api():
    query = build_search_query(
        parse_item_text(ITEM), trade_status="offline", listed_within="1week",
    )["query"]
    assert query["status"] == {"option": "any"}
    assert query["filters"]["trade_filters"]["filters"]["indexed"] == {
        "option": "1week"
    }


def test_captured_beast_uses_exact_english_type_without_rarity_filter():
    item = parse_item_text("""Item Class: Captured Beasts
Rarity: Rare
Craicic Chimeral
Craicic Chimeral
--------
Right-click to add this to your bestiary.
""")
    query = build_search_query(item, "Craicic Chimeral")["query"]
    assert query["type"] == "Craicic Chimeral"
    assert "type_filters" not in query["filters"]


def test_current_japanese_captured_beast_uses_species_only_like_awakened():
    _trade_response_cache.clear()
    item = parse_item_text("""アイテムクラス: スタック可能カレンシー
レアリティ: レア
Bloodmauler the Drooling
Farric Lynx Alpha
--------
ジーナス: ヤマネコ
グループ: ネコ類
ファミリー: 原生林
--------
アイテムレベル: 83
--------
{ プレフィックスモッド「潰滅する」 (ティア: 1) }
ヒット時破砕
{ プレフィックスモッド「軽快な」 (ティア: 1) }
素早い
{ モンスターモッド }
ファルウルの存在感
{ モンスターモッド }
サテュロスの嵐
{ モンスターモッド }
霊体の猛撃
{ モンスターモッド }
血の祭壇で生贄にされた時に20%の確率で消費されない
--------
右クリックしてこのモンスターを怪獣園に追加する。
""")
    assert item.category == "captured_beast"
    assert item.base_type == "Farric Lynx Alpha"
    filters = resolve_trade_stat_filters(item)
    assert filters == ()
    assert unresolved_modifier_warnings(item, filters) == ()

    response = ({"id": "qid", "result": [], "total": 0}, {})
    with patch("src.poetore.trade._request_json", return_value=response), patch(
        "src.poetore.trade._japanese_trade_item_type",
        return_value="ファルウルのリンクス・アルファ",
    ):
        result = search_prices(item, item.base_type, "Standard", stat_filters=filters)

    web_query = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])["query"]
    assert web_query["type"] == "ファルウルのリンクス・アルファ"
    assert web_query["filters"] == {}
    assert web_query["stats"] == [{"type": "and", "filters": []}]


def test_itemised_spectre_corpse_uses_awakened_exact_identity_without_mod_warnings():
    item = parse_item_text("""アイテムクラス: 死体
レアリティ: カレンシー
完全体のドルイド錬金術師
--------
死体レベル: 85
モンスターカテゴリー: 人型
--------
アイテムレベル: 85
--------
ポイゾナスコンコクションを投げる
フラスコの効果が200％増加する
所有者は3秒ごとにライフフラスコのチャージを1得る
--------
このアイテムを右クリックしてこの死体を生成する。
""")

    assert item.category == "corpse"
    assert uses_dedicated_exact_preset(item)
    filters = resolve_trade_stat_filters(item)
    assert [row.stat_id for row in filters] == ["property.item_level"]
    assert unresolved_modifier_warnings(item, filters) == ()

    query = build_search_query(
        item, item.base_type, stat_filters=filters, item_level_min=85,
    )["query"]
    assert query["type"] == "完全体のドルイド錬金術師"
    assert query["stats"] == [{"type": "and", "filters": []}]
    assert query["filters"]["misc_filters"]["filters"]["ilvl"] == {"min": 85}

    query_without_ilvl = build_search_query(
        item, item.base_type, stat_filters=(), item_level_min=None,
    )["query"]
    assert "ilvl" not in query_without_ilvl["filters"]["misc_filters"]["filters"]


def test_japanese_local_physical_modifier_is_not_duplicated_after_pdps_aggregation():
    item = parse_item_text(ITEM.replace("74% increased Physical Damage", "物理ダメージが74%\u5897加する"))
    entries = ({"id": "explicit.stat_1509134228", "text": "物理ダメージが#%増加する", "type": "explicit"},)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert not any(row.stat_id == "explicit.stat_1509134228" for row in filters)
    assert any(row.stat_id == "property.physical_dps" for row in filters)


def test_hybrid_and_duplicate_stats_resolve_with_correct_values_and_sum():
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
倒した敵1体ごとに4(4-6)のマナを獲得する
""")
    entries = (
        {"id": "explicit.phys", "text": "物理ダメージが#%増加する", "type": "explicit"},
        {"id": "explicit.accuracy", "text": "命中力 +# (ローカル)", "type": "explicit"},
        {"id": "explicit.mana", "text": "倒した敵1体ごとに#のマナを獲得する", "type": "explicit"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert [(row.stat_id, row.min_value) for row in filters if row.kind != "craft"] == [
        ("explicit.phys", 74), ("explicit.accuracy", 55), ("explicit.mana", 4),
    ]
    assert filters[0].text.endswith("(2行合計)")


def test_active_pc_league_skips_permanent_and_hard_modes():
    payload = {"result": [
        {"id": "Hardcore Mirage", "realm": "pc"},
        {"id": "Mirage", "realm": "pc"},
        {"id": "Standard", "realm": "pc"},
    ]}
    with patch("src.poetore.trade._request_json", return_value=(payload, {})):
        assert active_pc_league() == "Mirage"


def test_available_pc_leagues_matches_awakened_filters():
    payload = [
        {"id": "Standard", "realm": "pc", "rules": []},
        {"id": "Hardcore", "realm": "pc", "rules": [{"id": "Hardcore"}]},
        {"id": "Mirage", "realm": "pc", "rules": []},
        {"id": "Hardcore Mirage", "realm": "pc", "rules": [{"id": "Hardcore"}]},
        {"id": "SSF Mirage", "realm": "pc", "rules": [{"id": "NoParties"}]},
        {"id": "Ruthless", "realm": "pc", "rules": [{"id": "HardMode"}]},
    ]
    with patch("src.poetore.trade._request_json", return_value=(payload, {})):
        leagues = available_pc_leagues()
    assert [(league.id, league.hardcore) for league in leagues] == [
        ("Standard", False), ("Mirage", False), ("Hardcore Mirage", True),
    ]
    assert default_pc_league(leagues) == "Mirage"


def test_price_result_calculates_median_per_currency():
    result = PriceResult("Mirage", "q", 3, (
        PriceListing(3, "chaos"), PriceListing(7, "chaos"), PriceListing(1, "divine")
    ))
    assert result.median_by_currency() == {"chaos": 5, "divine": 1}


def test_same_seller_same_price_is_grouped_before_median():
    grouped = _group_price_listings([
        PriceListing(1, "chaos", "price-fixer"),
        PriceListing(1, "chaos", "price-fixer"),
        PriceListing(1, "chaos", "price-fixer"),
        PriceListing(8, "chaos", "seller-a"),
        PriceListing(10, "chaos", "seller-b"),
    ])
    assert [(row.amount, row.account, row.listed_times) for row in grouped] == [
        (1, "price-fixer", 3),
        (8, "seller-a", 1),
        (10, "seller-b", 1),
    ]
    assert PriceResult("Mirage", "q", 5, grouped).median_by_currency() == {
        "chaos": 8,
    }


def test_common_search_range_recalculates_from_read_value():
    row = TradeStatFilter(
        "explicit.life", "最大ライフ +100", 90, "explicit", True,
        read_value=100,
    )
    assert apply_search_range((row,), 0)[0].min_value == 100
    assert apply_search_range((row,), 20)[0].min_value == 80


def test_search_range_does_not_reduce_discrete_socket_counts():
    item = parse_item_text("""アイテムクラス: 両手斧
レアリティ: レア
魂の引き裂き
ヴァールアックス
--------
ソケット: R-R-R-W-G W
--------
アイテムレベル: 85
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    adjusted = {
        row.stat_id: row
        for row in apply_search_range(filters, 10, item)
        if row.stat_id.startswith("property.")
    }
    assert adjusted["property.sockets"].min_value == 6
    assert adjusted["property.links"].min_value == 5
    assert "property.white_sockets" not in adjusted


def test_search_prices_keeps_item_and_seller_for_list_display():
    _trade_response_cache.clear()
    search = ({"id": "query1", "result": ["item1"]}, {"X-Rate-Limit-Ip-State": "1:10:0"})
    fetch = ({"result": [{
        "listing": {
            "price": {"amount": 4, "currency": "chaos"},
            "account": {"name": "seller"},
            "indexed": "2026-07-22T09:21:00Z",
        },
        "item": {
            "name": "Doom Sever", "baseType": "Reaver Sword", "ilvl": 86,
            "stackSize": 3,
            "properties": [
                {"name": "Level", "values": [["20", 0]]},
                {"name": "Quality", "values": [["+23%", 1]]},
            ],
        },
    }]}, {})
    with patch(
        "src.poetore.trade._request_json", side_effect=[search, fetch],
    ), patch(
        "src.poetore.trade._japanese_trade_item_type",
        return_value="略奪者の剣",
    ):
        result = search_prices(parse_item_text(ITEM), "Reaver Sword", "Mirage")
    assert result.listings == (
        PriceListing(
            4, "chaos", "seller", "Doom Sever", "Reaver Sword",
            "2026-07-22T09:21:00Z", 86, 20, 23, 3,
        ),
    )


def test_search_prices_classifies_face_to_face_instant_and_unpriced_listings():
    _trade_response_cache.clear()
    search = (
        {"id": "query1", "result": ["face", "instant", "unpriced"]},
        {},
    )
    fetch = ({"result": [
        {
            "listing": {
                "price": {"amount": 4, "currency": "chaos"},
                "account": {"name": "face-seller"},
            },
            "item": {"baseType": "Reaver Sword", "note": "~price 4 chaos"},
        },
        {
            "listing": {
                "price": {"amount": 5, "currency": "chaos"},
                "fee": 1,
                "account": {"name": "instant-seller"},
            },
            "item": {"baseType": "Reaver Sword"},
        },
        {
            "listing": {"account": {"name": "stash-seller"}},
            "item": {"baseType": "Reaver Sword"},
        },
    ]}, {})
    with patch(
        "src.poetore.trade._request_json", side_effect=[search, fetch],
    ), patch(
        "src.poetore.trade._japanese_trade_item_type",
        return_value="略奪者の剣",
    ):
        result = search_prices(parse_item_text(ITEM), "Reaver Sword", "Mirage")

    assert [row.pricing_method for row in result.listings] == [
        "face_to_face", "instant", "unpriced",
    ]
    assert result.median_by_currency() == {"chaos": 4.5}


def test_search_prices_fetches_at_least_twenty_results():
    _trade_response_cache.clear()
    search = ({"id": "query1", "result": [f"item{i}" for i in range(30)]}, {})

    def block(start):
        return ({"result": [{
            "listing": {
                "price": {"amount": start + index + 1, "currency": "chaos"},
                "account": {"name": f"seller-{start + index}"},
            },
            "item": {"baseType": "Reaver Sword"},
        } for index in range(10)]}, {})

    with patch(
        "src.poetore.trade._request_json",
        side_effect=[search, block(0), block(10)],
    ) as request, patch(
        "src.poetore.trade._japanese_trade_item_type",
        return_value="略奪者の剣",
    ):
        result = search_prices(parse_item_text(ITEM), "Reaver Sword", "Mirage")

    assert request.call_count == 3
    assert len(result.listings) == 20


def test_search_prices_logs_request_payload_and_response_summary(capsys):
    _trade_response_cache.clear()
    search = ({"id": "query1", "result": ["item1"]}, {"X-Rate-Limit-Ip-State": "1:10:0"})
    fetch = ({"result": [{
        "listing": {"price": {"amount": 4, "currency": "chaos"}},
        "item": {"baseType": "Reaver Sword"},
    }]}, {})
    with patch("src.poetore.trade._request_json", side_effect=[search, fetch]):
        search_prices(
            parse_item_text(ITEM), "Reaver Sword", "Mirage",
            trade_status="available",
        )

    output = capsys.readouterr().out
    assert "[POETORE TRADE] search: league='Mirage'" in output
    assert "trade_status='available' api_status='available'" in output
    assert '"type": "Reaver Sword"' in output
    assert '"status": {' in output
    assert '"option": "available"' in output
    assert "search response: query_id='query1' candidates=1" in output
    assert "priced_listings=1 rate_limit='1:10:0'" in output


def test_search_result_exposes_japanese_trade_url_and_reuses_cache():
    _trade_response_cache.clear()
    response = ({"id": "qid", "result": [], "total": 0}, {})
    item = replace(parse_item_text(ITEM), name="破滅の切断", base_type="上質な 略奪者の剣")
    with patch("src.poetore.trade._request_json", return_value=response) as request:
        first = search_prices(item, "Reaver Sword", "Standard")
        second = search_prices(item, "Reaver Sword", "Standard")
    assert request.call_count == 1
    assert first.cached is False and second.cached is True
    parsed_url = urlsplit(first.web_url)
    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "jp.pathofexile.com"
    assert parsed_url.path == "/trade/search/Standard"
    web_payload = json.loads(parse_qs(parsed_url.query)["q"][0])
    assert web_payload["query"]["type"] == "略奪者の剣"
    assert "qid" not in first.web_url


@pytest.mark.parametrize(("english_name", "japanese_name"), (
    ("Eternal Damnation", "永遠の破滅"),
    ("Voll's Devotion", "ヴォールの献身"),
))
def test_unidentified_unique_candidate_is_kept_in_japanese_trade_url(
    english_name, japanese_name,
):
    _trade_response_cache.clear()
    item = parse_item_text("""アイテムクラス: アミュレット
レアリティ: ユニーク
瑪瑙のアミュレット
--------
アイテムレベル: 85
--------
未鑑定
""")
    response = ({"id": "qid", "result": [], "total": 0}, {})
    with (
        patch("src.poetore.trade._request_json", return_value=response),
        patch(
            "src.poetore.trade._english_trade_item_type",
            return_value="Agate Amulet",
        ),
        patch(
            "src.poetore.trade._japanese_trade_item_type",
            return_value="瑪瑙のアミュレット",
        ),
        patch(
            "src.poetore.trade._japanese_trade_item_name",
            return_value=japanese_name,
        ) as localize_name,
    ):
        result = search_prices(
            item,
            "Agate Amulet",
            "Standard",
            trade_name=english_name,
            include_unidentified=True,
        )

    web_payload = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])
    assert web_payload["query"]["name"] == japanese_name
    assert web_payload["query"]["type"] == "瑪瑙のアミュレット"
    assert web_payload["query"]["filters"]["misc_filters"]["filters"]["identified"] == {
        "option": "false",
    }
    localize_name.assert_called_with(english_name)


def test_magic_base_jewel_web_url_does_not_add_affixed_name_as_type():
    _trade_response_cache.clear()
    item = parse_item_text("""アイテムクラス: ジュエル
レアリティ: マジック
凶悪な 避難所の ビリジアンジュエル
--------
アイテムレベル: 82
--------
{ プレフィックスモッド「凶悪な」 (ティア: 1) — ダメージ, アタック }
剣によるダメージが14(14-16)%増加する
{ サフィックスモッド 「避難所の」 (ティア: 1) — 元素, 冷気, 雷, 耐性 }
冷気および雷耐性 +12(10-12)%
--------
パッシブツリーで割り当てられたジュエルソケットにはめる。
""")
    filters = (
        TradeStatFilter(
            "explicit.stat_83050999",
            "剣によるダメージが14(14-16)%増加する",
            12.6, "prefix", True,
        ),
        TradeStatFilter(
            "explicit.stat_4277795662",
            "冷気および雷耐性 +12(10-12)%",
            10.8, "suffix", True,
        ),
    )
    response = ({"id": "qid", "result": [], "total": 0}, {})
    with patch("src.poetore.trade._request_json", return_value=response):
        result = search_prices(
            item, "Viridian Jewel", "Standard", stat_filters=filters,
            exact_base_type=False,
        )

    web_payload = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])
    web_query = web_payload["query"]
    assert "type" not in web_query
    assert web_query["filters"]["type_filters"]["filters"] == {
        "rarity": {"option": "magic"},
        "category": {"option": "jewel.base"},
    }
    assert [row["id"] for row in web_query["stats"][0]["filters"]] == [
        "explicit.stat_83050999",
        "explicit.stat_4277795662",
    ]


def test_current_japanese_flask_resolves_reduced_duration_and_opens_localized_trade():
    _trade_response_cache.clear()
    item = parse_item_text("""アイテムクラス: ユーティリティフラスコ
レアリティ: マジック
Abecedarian's Jade Flask of Depletion
--------
3.70 (augmented)秒間持続
使用時に60中30チャージを消費
現在0チャージ
回避力 +1500
--------
装備要求:
レベル: 27
--------
アイテムレベル: 42
--------
{ プレフィックスモッド「初学者の」 (ティア: 3) }
持続時間が38(38-33)%減少する
効果が25%増加する
{ サフィックスモッド 「消費の」 (ティア: 4) — 防御, エナジーシールド, キャスター }
効果中はスペルダメージの0.5%をエナジーシールドとしてリーチする
""")
    filters = resolve_trade_stat_filters(item)
    duration = next(row for row in filters if row.stat_id == "explicit.stat_1256719186")
    assert duration.ref == "#% increased Duration"
    assert duration.inverted is True
    assert unresolved_modifier_warnings(item, filters) == ()
    ilvl = next(row for row in filters if row.stat_id == "property.item_level")
    assert ilvl.enabled is False

    response = ({"id": "qid", "result": [], "total": 0}, {})
    with patch("src.poetore.trade._request_json", return_value=response), patch(
        "src.poetore.trade._trade_item_entries",
        return_value=({"type": "Jade Flask"},),
    ), patch(
        "src.poetore.trade._japanese_trade_item_type",
        return_value="翡翠のフラスコ",
    ) as localize:
        result = search_prices(
            item, item.base_type, "Standard",
            stat_filters=(replace(duration, enabled=True),),
        )

    localize.assert_called_once_with("Jade Flask")
    web_query = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])["query"]
    assert web_query["type"] == "翡翠のフラスコ"
    assert web_query["stats"][0]["filters"] == [{
        "id": "explicit.stat_1256719186",
        "value": {"max": -38.0},
    }]


def test_current_japanese_tincture_opens_localized_trade_without_affixed_type():
    _trade_response_cache.clear()
    item = parse_item_text("""アイテムクラス: チンキ
レアリティ: マジック
Tenacious Blood Sap Tincture of Battering
--------
毎秒0.85 (augmented)のマナ燃焼を付与する
不活性化時のクールダウン 6秒
--------
装備要求:
レベル: 45
--------
アイテムレベル: 47
--------
{ プレフィックスモッド「固く握った」 (ティア: 3) }
マナ燃焼レートが18(20-18)%減少する
{ サフィックスモッド 「殴打の」 (ティア: 3) — ダメージ, 物理, アタック }
近接武器は30(30-39)%の確率で敵物理ダメージ軽減を無視する
""")
    filters = resolve_trade_stat_filters(item)
    mana_burn = next(row for row in filters if row.stat_id == "explicit.stat_116232170")
    assert mana_burn.inverted is False
    assert unresolved_modifier_warnings(item, filters) == ()
    assert next(
        row for row in filters if row.stat_id == "property.item_level"
    ).enabled is False

    response = ({"id": "qid", "result": [], "total": 0}, {})
    with patch("src.poetore.trade._request_json", return_value=response), patch(
        "src.poetore.trade._trade_item_entries",
        return_value=({"type": "Blood Sap Tincture"},),
    ), patch(
        "src.poetore.trade._japanese_trade_item_type",
        return_value="血の樹液のチンキ",
    ) as localize:
        result = search_prices(
            item, item.base_type, "Standard",
            stat_filters=(replace(mana_burn, enabled=True),),
        )

    localize.assert_called_once_with("Blood Sap Tincture")
    web_query = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])["query"]
    assert web_query["type"] == "血の樹液のチンキ"
    assert web_query["stats"][0]["filters"] == [{
        "id": "explicit.stat_116232170",
        "value": {"min": 16.0},
    }]


def test_tincture_effect_uses_tincture_specific_duplicate_trade_stat():
    item = parse_item_text("""アイテムクラス: チンキ
レアリティ: マジック
強い 液状化の 血の樹液のチンキ
--------
毎秒0.43 (augmented)のマナ燃焼を付与する
不活性化時のクールダウン 6秒
--------
装備要求:
レベル: 46
--------
アイテムレベル: 84
--------
{ 暗黙モッド — ダメージ, 物理, アタック, 状態異常 - 35%増加 }
近接武器により20%の確率で出血を付与する
近接武器による出血ダメージが85(60-90)%増加する
--------
{ プレフィックスモッド「強い」 (ティア: 3) - 35%増加 }
効果が35%増加する
マナ燃焼レートが48(47-51)%増加する
{ サフィックスモッド 「液状化の」 (ティア: 3) — ダメージ, アタック - 35%増加 }
近接武器によるアタックの継続ダメージ倍率 +23(19-23)%
""")
    duplicate_entries = (
        {
            "id": "explicit.stat_2448920197",
            "text": "効果が#%増加する",
            "type": "explicit",
        },
        {
            "id": "explicit.stat_3529940209",
            "text": "効果が#%増加する",
            "type": "explicit",
        },
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=duplicate_entries):
        filters = resolve_trade_stat_filters(item)

    effect = next(row for row in filters if row.text == "効果が35%増加する")
    assert effect.stat_id == "explicit.stat_3529940209"
    assert effect.min_value == 35
    assert not any(row.stat_id == "explicit.stat_2448920197" for row in filters)

    query = build_search_query(
        item, "Blood Sap Tincture",
        stat_filters=(replace(effect, enabled=True),),
    )["query"]
    assert query["stats"][0]["filters"] == [{
        "id": "explicit.stat_3529940209",
        "value": {"min": 35},
    }]


def test_transfigured_gem_web_url_uses_localized_base_type_with_discriminator():
    _trade_response_cache.clear()
    item = _gem_item("爆撃するクローンのミラーアロー", level=14, quality=0)
    response = ({"id": "qid", "result": [], "total": 0}, {})
    jp_items = (
        {"type": "ミラーアロー"},
        {
            "type": "ミラーアロー",
            "text": "爆撃するクローンのミラーアロー",
            "disc": "alt_x",
        },
    )
    with patch("src.poetore.trade._request_json", return_value=response), patch(
        "src.poetore.trade._jp_trade_item_entries", return_value=jp_items,
    ):
        result = search_prices(
            item, "Mirror Arrow of Bombarding Clones", "Standard",
        )

    web_payload = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])
    assert web_payload["query"]["type"] == {
        "option": "ミラーアロー",
        "discriminator": "alt_x",
    }


def test_japanese_transfigured_gem_text_resolves_to_english_variant_identity():
    item = _gem_item("動地のグラウンドスラム", level=20, quality=20)
    aligned_items = ((
        {
            "type": "Ground Slam",
            "text": "Ground Slam of Earthshaking",
            "disc": "alt_x",
        },
        {
            "type": "グラウンドスラム",
            "text": "動地のグラウンドスラム",
            "disc": "alt_x",
        },
    ),)
    with patch(
        "src.poetore.trade._aligned_trade_item_pairs",
        return_value=iter(aligned_items),
    ):
        trade_type, trade_name = english_trade_identity(item)

    assert trade_type == "Ground Slam of Earthshaking"
    assert trade_name is None
    query = build_search_query(item, trade_type)["query"]
    assert query["type"] == {
        "option": "Ground Slam",
        "discriminator": "alt_x",
    }


def test_vaal_gem_detailed_copy_searches_the_vaal_item_not_the_normal_gem():
    item = parse_item_text("""Item Class: Skill Gems
Rarity: Gem
Molten Strike
--------
Attack, Projectile, Area, Melee, Strike, Fire, Chaining, Vaal
Level: 1
--------
Vaal Molten Strike
--------
Souls Per Use: 15
Can Store 3 Uses
--------
Corrupted
""")

    query = build_search_query(item, item.base_type)["query"]

    assert item.base_type == "Vaal Molten Strike"
    assert query["type"] == "Vaal Molten Strike"

    response = ({"id": "qid", "result": [], "total": 0}, {})
    jp_items = ({"type": "ヴァールモルテンストライク"},)
    with patch("src.poetore.trade._request_json", return_value=response), patch(
        "src.poetore.trade._jp_trade_item_entries", return_value=jp_items,
    ):
        result = search_prices(item, item.base_type, "Standard")

    web_payload = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])
    assert web_payload["query"]["type"] == "ヴァールモルテンストライク"


@pytest.mark.parametrize(
    ("oils", "expected_visible"),
    [
        ((10, 10, 10), False),  # 黒色のみ
        ((10, 11, 10), True),   # 乳白色
        ((10, 12, 10), True),   # 銀色
        ((10, 13, 10), True),   # 金色
    ],
)
def test_modifiable_amulet_shows_anointments_using_valuable_oils(
    oils, expected_visible,
):
    item = ParsedItem(
        item_class="アミュレット",
        rarity="レア",
        name="試験用",
        base_type="オニキスのアミュレット",
        category="accessory",
        modifiers=(
            ItemModifier(
                "処刑人 を割り当てる",
                kind="enchant",
                ref="Allocates #",
                stat_id="enchant.allocates",
                option_value=10016,
                oils=oils,
            ),
        ),
    )
    entries = ({"id": "enchant.allocates", "type": "enchant", "text": "# を割り当てる"},)

    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)

    assert bool(filters) is expected_visible
    if expected_visible:
        assert filters[0].oils == oils
        assert filters[0].enabled is False


def test_query_supports_option_not_count_and_special_item_states():
    item = parse_item_text(ITEM)
    item = replace(item, flags=item.flags + ("searing_item", "tangled_item", "veiled"))
    filters = (
        TradeStatFilter("enchant.allocates", "処刑人 を割り当てる", None, "enchant", True,
                        option_value=10016),
        TradeStatFilter("explicit.bad", "除外", None, "explicit", True,
                        group_type="not", group_key="exclude"),
        TradeStatFilter("explicit.one", "候補1", None, "explicit", True,
                        group_type="count", group_key="either", group_min=1),
        TradeStatFilter("explicit.two", "候補2", None, "explicit", True,
                        group_type="count", group_key="either", group_min=1),
    )
    query = build_search_query(item, stat_filters=filters)["query"]
    assert query["stats"][0]["filters"][0] == {
        "id": "enchant.allocates", "value": {"option": 10016},
    }
    assert {group["type"] for group in query["stats"]} == {"and", "not", "count"}
    count = next(group for group in query["stats"] if group["type"] == "count")
    assert count["value"] == {"min": 1}
    misc = query["filters"]["misc_filters"]["filters"]
    assert misc["searing_item"] == misc["tangled_item"] == {"option": "true"}
    assert "veiled" not in misc
    without_veiled = build_search_query(
        item, stat_filters=filters, include_veiled=False,
    )["query"]
    assert "veiled" not in without_veiled["filters"]["misc_filters"]["filters"]


def test_eldritch_item_filters_can_be_disabled_independently():
    item = replace(
        parse_item_text(ITEM),
        flags=parse_item_text(ITEM).flags + ("searing_item", "tangled_item"),
    )

    initial = build_search_query(item)["query"]
    initial_misc = initial["filters"]["misc_filters"]["filters"]
    assert initial_misc["searing_item"] == {"option": "true"}
    assert initial_misc["tangled_item"] == {"option": "true"}

    eater_disabled = build_search_query(
        item, include_searing=True, include_tangled=False,
    )["query"]
    eater_disabled_misc = eater_disabled["filters"]["misc_filters"]["filters"]
    assert eater_disabled_misc["searing_item"] == {"option": "true"}
    assert "tangled_item" not in eater_disabled_misc

    both_disabled = build_search_query(
        item, include_searing=False, include_tangled=False,
    )["query"]
    both_disabled_misc = both_disabled["filters"]["misc_filters"]["filters"]
    assert "searing_item" not in both_disabled_misc
    assert "tangled_item" not in both_disabled_misc


def test_option_stat_query_does_not_include_numeric_bounds():
    item = parse_item_text("""アイテムクラス: ジュエル
レアリティ: レア
思案する瞳
クラスタージュエル (小)
--------
アイテムレベル: 83
--------
パッシブスキルを2個追加する (enchant)
追加される通常パッシブスキルは付与: 回避力が15%増加する (enchant)
""")
    filters = resolve_trade_stat_filters(
        item, PRESET_FINISHED, "Small Cluster Jewel",
    )
    base_effect = next(
        row for row in filters
        if row.stat_id.split("|", 1)[0] == "enchant.stat_3948993189"
    )
    assert base_effect.option_value == 43
    assert base_effect.min_value == 15

    query = build_search_query(
        item, stat_filters=(replace(base_effect, enabled=True),),
    )["query"]
    sent = query["stats"][0]["filters"][0]
    assert sent == {
        "id": "enchant.stat_3948993189",
        "value": {"option": 43},
    }


def test_dark_monarch_holy_armaments_variant_is_enabled_and_sent_exactly():
    item = parse_item_text("""アイテムクラス: 兜
レアリティ: ユニーク
闇の王
リッチのサークレット
--------
エナジーシールド: 205 (augmented)
--------
アイテムレベル: 86
--------
{ ユニークモッド — 防御, エナジーシールド }
最大エナジーシールド +76(50-100)
{ ユニークモッド — ミニオン, ジェム }
全てのミニオンスキルジェムのレベル +1
{ ユニークモッド — 混沌, 耐性 }
混沌耐性 +33(27-37)%
{ ユニークモッド }
光半径が50%減少する
{ ユニークモッド }
スケルトン召喚(アニメイトウェポン-ホーリーアーマメント)の最大数が二倍になる
スケルトン召喚(アニメイトウェポン-ホーリーアーマメント)以外のミニオンを召喚できない
""")

    filters = resolve_trade_stat_filters(item, trade_name="The Dark Monarch")
    variant = next(
        row for row in filters
        if row.stat_id == "explicit.stat_56473917|16"
    )
    assert variant.enabled
    assert not variant.hidden_reason

    query = build_search_query(
        item, "Lich's Circlet", filters, trade_name="The Dark Monarch",
    )["query"]
    assert query["stats"][0]["filters"] == [{
        "id": "explicit.stat_56473917|16",
        "value": {},
    }]


def test_forbidden_flame_ascendancy_uses_trade_site_composite_stat_id():
    item = parse_item_text("""アイテムクラス: ジュエル
レアリティ: ユニーク
禁じられた炎
クリムゾンジュエル
--------
アイテムレベル: 86
--------
禁じられた炎に一致するモッドがあれば元素の要塞を割り当てる
""")

    filters = resolve_trade_stat_filters(item, trade_name="Forbidden Flame")
    ascendancy = next(
        row for row in filters
        if row.stat_id == "explicit.stat_2460506030|4917"
    )
    assert ascendancy.enabled
    assert ascendancy.option_value is None

    query = build_search_query(
        item, "Crimson Jewel", (ascendancy,), trade_name="Forbidden Flame",
    )["query"]
    assert query["stats"][0]["filters"] == [{
        "id": "explicit.stat_2460506030|4917",
        "value": {},
    }]


def test_veiled_chip_uses_matching_veiled_stat_ids_like_awakened():
    item = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Mantle
Vaal Regalia
--------
Item Level: 86
--------
{ Prefix Modifier "Catarina's Veiled" }
Veiled Prefix
{ Suffix Modifier "of Aisling's Veil" }
Veiled Suffix
""")
    veiled = [modifier for modifier in item.modifiers if modifier.kind == "veiled"]
    assert [(modifier.ref, modifier.stat_id) for modifier in veiled] == [
        ("Catarina's Veiled", "veiled.mod_63772"),
        ("of Aisling's Veil", "veiled.mod_48007"),
    ]

    enabled = build_search_query(item, include_veiled=True)["query"]
    assert enabled["stats"][0]["filters"] == [
        {"id": "veiled.mod_63772", "value": {}},
        {"id": "veiled.mod_48007", "value": {}},
    ]
    assert "veiled" not in enabled["filters"]["misc_filters"]["filters"]

    disabled = build_search_query(item, include_veiled=False)["query"]
    assert disabled["stats"][0]["filters"] == []


def test_veiled_item_starts_with_only_its_veiled_type_enabled():
    item = ParsedItem(
        "Body Armours", "Rare", "Test Mantle", "Vaal Regalia", "armour",
        item_level=86, flags=("veiled",),
        modifiers=(
            ItemModifier(
                "Catarina's Veiled", kind="veiled",
                ref="Catarina's Veiled", stat_id="veiled.mod_63772",
            ),
            ItemModifier(
                "+100 to maximum Life", (100,), kind="prefix", tier=1,
                ref="+# to maximum Life", stat_id="explicit.life",
            ),
        ),
    )
    entries = ({
        "id": "explicit.life", "text": "+# to maximum Life", "type": "explicit",
    },)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    assert filters
    assert not any(row.enabled for row in filters)

    query = build_search_query(
        item, "Vaal Regalia", filters,
        include_veiled=True, preset=PRESET_FINISHED,
    )["query"]
    assert query["stats"][0]["filters"] == [{
        "id": "veiled.mod_63772",
        "value": {},
    }]


def test_japanese_veiled_header_resolves_its_specific_stat_id():
    item = parse_item_text("""アイテムクラス: 鎧
レアリティ: レア
試験の衣
ヴァールレガリア
--------
アイテムレベル: 86
--------
{ プレフィックスモッド「ヴェールされた」 }
ヴェールされたプレフィックス
""")
    veiled = next(modifier for modifier in item.modifiers if modifier.kind == "veiled")
    assert veiled.ref == "Veiled"
    assert veiled.stat_id == "veiled.mod_65000"


def _gem_item(name="アーク", level=20, quality=20, corrupted=False):
    return parse_item_text(f"""アイテムクラス: スキルジェム
レアリティ: ジェム
{name}
--------
レベル: {level}
品質: +{quality}%
--------
アイテムレベル: 1
--------
{"コラプト状態" if corrupted else ""}
""")


def test_gem_filters_use_awakened_max_level_quality_and_corruption_rules():
    normal = _gem_item(level=20, quality=16)
    filters = {row.stat_id: row for row in resolve_trade_stat_filters(normal, trade_base_type="Arc")}
    assert filters["property.gem_level"].enabled is True
    assert filters["property.quality"].enabled is True
    query = build_search_query(normal, "Arc", tuple(filters.values()))["query"]
    assert query["filters"]["misc_filters"]["filters"] == {
        "corrupted": {"option": "false"}, "gem_level": {"min": 20.0}, "quality": {"min": 16.0},
    }

    corrupted_only = build_search_query(
        normal, "Arc", tuple(filters.values()), include_corrupted="only",
    )["query"]
    assert corrupted_only["filters"]["misc_filters"]["filters"]["corrupted"] == {
        "option": "true"
    }

    both = build_search_query(
        normal, "Arc", tuple(filters.values()), include_corrupted=True,
    )["query"]
    assert "corrupted" not in both["filters"]["misc_filters"]["filters"]

    low = _gem_item(level=19, quality=15)
    assert all(not row.enabled for row in resolve_trade_stat_filters(low, trade_base_type="Arc"))


def test_gem_filter_uses_gem_level_instead_of_requirement_level():
    item = parse_item_text("""アイテムクラス: サポートジェム
レアリティ: ジェム
範囲ダメージ集中サポート
--------
レベル: 3
--------
装備条件:
レベル: 26
知性: 45
--------
次のレベル:
レベル: 29
知性: 49
""")
    level_filter = next(
        row for row in resolve_trade_stat_filters(
            item, trade_base_type="Concentrated Effect Support",
        ) if row.stat_id == "property.gem_level"
    )
    assert level_filter.read_value == 3
    assert level_filter.min_value == 3


def test_explicit_gem_level_minimum_overrides_stat_filter():
    item = _gem_item(level=20, quality=0)
    legacy = TradeStatFilter(
        "property.gem_level", "ジェムレベル", 20.0, "gem", True,
    )
    query = build_search_query(
        item, "Arc", stat_filters=(legacy,), gem_level_min=18,
    )["query"]
    assert query["filters"]["misc_filters"]["filters"]["gem_level"] == {"min": 18}


def test_explicit_gem_quality_minimum_overrides_stat_filter():
    item = _gem_item(level=20, quality=16)
    legacy = TradeStatFilter(
        "property.quality", "品質", 16.0, "gem", True,
    )
    query = build_search_query(
        item, "Arc", stat_filters=(legacy,), quality_min=20,
    )["query"]
    assert query["filters"]["misc_filters"]["filters"]["quality"] == {"min": 20}


def test_explicit_link_minimum_overrides_stat_filter():
    item = parse_item_text(ITEM)
    legacy = TradeStatFilter(
        "property.links", "最大リンク数", 6.0, "socket", True,
    )
    query = build_search_query(
        item, stat_filters=(legacy,), links_min=5,
    )["query"]
    assert query["filters"]["socket_filters"]["filters"]["links"] == {"min": 5}


def test_transfigured_vaal_awakened_and_exceptional_gem_identity():
    transfigured = _gem_item("サージングのアーク", 20, 16)
    filters = resolve_trade_stat_filters(transfigured, trade_base_type="Arc of Surging")
    assert next(row for row in filters if row.stat_id == "property.quality").enabled is False
    query = build_search_query(transfigured, "Arc of Surging", filters)["query"]
    assert query["type"] == {"option": "Arc", "discriminator": "alt_x"}

    empower = _gem_item("エンパワーサポート", 3, 0)
    level = next(row for row in resolve_trade_stat_filters(empower, trade_base_type="Empower Support")
                 if row.stat_id == "property.gem_level")
    assert level.enabled is True
    awakened = _gem_item("覚醒のエンパワーサポート", 3, 0)
    awakened_level = next(row for row in resolve_trade_stat_filters(
        awakened, trade_base_type="Awakened Empower Support"
    ) if row.stat_id == "property.gem_level")
    assert awakened_level.enabled is False
    assert build_search_query(_gem_item("ヴァールアーク", 20, 20, True), "Vaal Arc")["query"]["type"] == "Vaal Arc"


def test_unique_item_level_exceptions_match_awakened():
    watchers = replace(parse_item_text("""Item Class: Jewels
Rarity: Unique
Prismatic Jewel
--------
Item Level: 86
--------
Unidentified
"""), name="Watcher's Eye")
    query = build_search_query(watchers, "Prismatic Jewel", trade_name="Watcher's Eye")["query"]
    assert query["filters"]["misc_filters"]["filters"]["ilvl"] == {"min": 86}

    agnerod = replace(watchers, name="Agnerod West", flags=(), item_level=81)
    filters = resolve_trade_stat_filters(agnerod)
    level = next(row for row in filters if row.stat_id == "property.item_level")
    assert level.min_value == 80
    query = build_search_query(agnerod, "Imperial Staff", filters, trade_name="Agnerod West")["query"]
    assert query["filters"]["misc_filters"]["filters"]["ilvl"] == {"min": 80.0}


def test_map_properties_blight_and_valdo_safety_filters():
    item = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
ブライトに破壊された峡谷マップ
峡谷マップ
--------
マップティア: 16
アイテム数量: +120%
アイテムレアリティ: +75%
モンスターパックサイズ: +42%
追加マップ: +25%
追加スカラベ: +30%
マップ完了報酬: Mageblood
--------
アイテムレベル: 83
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(item)
    enabled = {row.stat_id: row for row in filters if row.enabled}
    assert enabled["property.map_tier"].min_value == 16
    # AwakenedのBlighted Map ExactはMap本体条件だけを使い、rolled map statsは出さない。
    assert "property.map_quantity" not in enabled
    assert "property.map_rarity" not in enabled
    assert "property.map_pack_size" not in enabled
    assert "pseudo.pseudo_map_more_map_drops" not in enabled
    assert "pseudo.pseudo_map_more_scarab_drops" not in enabled
    assert enabled["property.map_uberblighted"].enabled
    assert "explicit.stat_1095765106" not in enabled
    query = build_search_query(item, "Canyon Map", filters)["query"]
    map_filters = query["filters"]["map_filters"]["filters"]
    assert map_filters["map_tier"] == {"min": 16.0}
    assert map_filters["map_uberblighted"] == {"option": "true"}
    assert map_filters["map_completion_reward"] == {"option": "Mageblood"}


def test_blighted_map_ignores_all_map_mods_and_unresolved_warnings():
    item = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Glyph Stone
Blighted Map (Tier 16)
--------
マップエリア: 干上がった海
アイテム数量: +75% (augmented)
アイテムレアリティ: +45% (augmented)
モンスターパックサイズ: +29% (augmented)
--------
アイテムレベル: 83
--------
モンスターレベル：83
--------
{ 暗黙モッド }
エリアは真菌に覆われている
マップのアイテムの数量のモッドはその数値の20%がブライトチェストにも影響する
3回アノイントすることができる — スケールできない値
このエリアに元々生息していた生物はいなくなる — スケールできない値
--------
{ プレフィックスモッド「多様な」 (ティア: 1) }
エリアのモンスターの種類が増える — スケールできない値
{ プレフィックスモッド「装甲付き」 (ティア: 1) — 物理 }
モンスターの物理ダメージ軽減率 +40%
{ プレフィックスモッド「電撃の」 (ティア: 1) — ダメージ, 物理, 元素, 雷 }
モンスターは物理ダメージの97(90-110)%を追加雷ダメージとして与える
{ サフィックスモッド 「耐久力の」 (ティア: 1) }
モンスターはヒット時にエンデュランスチャージを1個獲得する
{ サフィックスモッド 「虐殺の」 (ティア: 1) }
モンスターはアタックによるヒット時に重傷を付与する
{ サフィックスモッド 「干魃の」 (ティア: 1) }
全てのプレイヤーの獲得フラスコチャージが50%減少する
""")
    filters = resolve_trade_stat_filters(item)
    assert {row.stat_id for row in filters} == {
        "property.map_tier", "property.map_blighted",
    }
    assert unresolved_modifier_warnings(item, filters) == ()


def test_valdo_reward_and_multiline_mods_use_official_exact_filters():
    item = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Befuddling Frontier
Valdo Map
--------
報酬: フォイル 魅惑
--------
アイテムレベル: 100
--------
{ ユニークモッド }
ビヨンドからのモンスターは冒涜領域を生成する
ビヨンドボスはスポーンしない
{ ユニークモッド }
モンスターはプレイヤーから2m以内にいる時だけダメージを受ける
プレイヤーの光半径に対するモッドはこの範囲にも適用される
--------
フォイル (天体の翠玉)
""")
    filters = resolve_trade_stat_filters(item)
    by_id = {row.stat_id: row for row in filters}
    assert by_id["property.map_completion_reward"].option_value == "Allure"
    assert by_id["property.map_completion_reward"].option_text == "魅惑"
    assert by_id["explicit.stat_2624514051"].enabled is True
    assert by_id["explicit.stat_3791071930"].enabled is True
    assert by_id["explicit.stat_1095765106"].group_type == "not"
    assert unresolved_modifier_warnings(item, filters) == ()


def test_valdo_reward_uses_english_api_value_and_japanese_web_value():
    item = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Befuddling Frontier
Valdo Map
--------
報酬: フォイル 魅惑
--------
アイテムレベル: 100
--------
フォイル (天体の翠玉)
""")
    response = ({"id": "qid", "result": [], "total": 0}, {})
    with patch(
        "src.poetore.trade._english_trade_item_name", return_value="Allure"
    ), patch(
        "src.poetore.trade._japanese_trade_item_type", return_value="ヴァルドマップ"
    ), patch("src.poetore.trade._request_json", return_value=response) as request:
        filters = resolve_trade_stat_filters(item)
        result = search_prices(
            item, "Valdo Map", "Standard", stat_filters=filters,
            include_foil=True,
        )

    api_payload = request.call_args.args[1]
    assert api_payload["query"]["filters"]["map_filters"]["filters"][
        "map_completion_reward"
    ] == {"option": "Allure"}
    web_payload = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])
    assert web_payload["query"]["type"] == "ヴァルドマップ"
    assert web_payload["query"]["filters"]["map_filters"]["filters"][
        "map_completion_reward"
    ] == {"option": "魅惑"}


def test_detailed_generic_map_type_is_not_sent_as_trade_base_type():
    item = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Insane Intent
Map (Tier 16)
--------
アイテム数量: +65% (augmented)
アイテムレアリティ: +39% (augmented)
モンスターパックサイズ: +25% (augmented)
--------
アイテムレベル: 85
--------
モンスターレベル：83
--------
{ プレフィックスモッド「凍りつく」 (ティア: 1) }
モンスターは物理ダメージの98(90-110)%を追加冷気ダメージとして与える
""")
    filters = resolve_trade_stat_filters(item, trade_base_type=item.base_type)
    query = build_search_query(item, item.base_type, filters)["query"]

    assert "type" not in query
    assert query["filters"]["map_filters"]["filters"]["map_tier"] == {"min": 16.0}


def test_unique_generic_map_matches_awakened_identity_and_ignores_rolls():
    item = parse_item_text("""アイテムクラス: マップ
レアリティ: ユニーク
オバの呪われた財宝
マップ (ティア 16)
--------
アイテム数量: +40% (augmented)
--------
アイテムレベル: 84
--------
モンスターレベル：83
--------
{ ユニークモッド — ライフ }
モンスターのライフが42(40-50)%上昇する
{ ユニークモッド — ダメージ }
モンスターのダメージが35(30-40)%増加する
{ ユニークモッド — ダメージ, 混沌 }
エリアには冒涜領域がまだらに存在する
{ ユニークモッド }
エリアは時間が経つと致命的になる
""")
    filters = resolve_trade_stat_filters(item, trade_base_type="Map")
    assert [
        row.stat_id for row in filters if row.enabled
    ] == ["property.map_tier"]

    tier = next(row for row in filters if row.stat_id == "property.map_tier")
    query = build_search_query(
        item,
        "Map",
        (replace(tier, max_value=tier.min_value),),
        trade_name="Oba's Cursed Trove",
    )["query"]

    exact_map = {"option": "Map", "discriminator": "map"}
    exact_name = {"option": "Oba's Cursed Trove", "discriminator": "map"}
    assert query["type"] == exact_map
    assert query["name"] == exact_name
    assert query["stats"] == [{"type": "and", "filters": []}]
    assert query["filters"]["map_filters"]["filters"]["map_tier"] == {
        "min": 16.0, "max": 16.0,
    }


@pytest.mark.parametrize("text", [
    """アイテムクラス: マップ
レアリティ: ノーマル
Map (Tier 16)
--------
アイテムレベル: 85
--------
モンスターレベル：83
""",
    """Item Class: Maps
Rarity: Unique
The Coward's Trial
Cursed Crypt Map
--------
Map Tier: 16
Item Level: 83
""",
    """アイテムクラス: マップ
レアリティ: レア
ブライトマップ
峡谷マップ
--------
マップティア: 16
アイテムレベル: 83
""",
    """アイテムクラス: マップ
レアリティ: レア
Befuddling Frontier
Valdo Map
--------
報酬: フォイル 魅惑
アイテムレベル: 100
""",
])
def test_all_map_variants_never_send_item_level(text):
    item = parse_item_text(text)
    filters = resolve_trade_stat_filters(item)
    assert all(row.stat_id != "property.item_level" for row in filters)

    stale_filters = filters + (TradeStatFilter(
        "property.item_level", "古いilvl条件", float(item.item_level), "base", True,
    ),)
    query = build_search_query(
        item, item.base_type, stale_filters,
        item_level_min=item.item_level,
    )["query"]
    misc = query.get("filters", {}).get("misc_filters", {}).get("filters", {})
    assert "ilvl" not in misc


def test_dedicated_exact_normal_item_uses_nonunique_ilvl_and_exact_stats_only():
    item = parse_item_text("""Item Class: Two Hand Swords
Rarity: Normal
Reaver Sword
--------
Item Level: 85
--------
Quality: +20%
Sockets: R-R-R-R-R-R
""")
    filters = resolve_trade_stat_filters(item, trade_base_type="Reaver Sword")
    ids = {row.stat_id: row for row in filters}
    assert ids["property.item_level"].enabled and ids["property.item_level"].min_value == 85
    assert "property.total_dps" not in ids
    assert "pseudo.pseudo_number_of_empty_prefix_mods" not in ids
    query = build_search_query(item, "Reaver Sword", filters)["query"]
    assert query["filters"]["type_filters"]["filters"]["rarity"] == {"option": "nonunique"}
    assert query["filters"]["misc_filters"]["filters"]["ilvl"] == {"min": 85.0}


@pytest.mark.parametrize("category,rarity", [
    ("map", "Rare"), ("memory_line", "Rare"), ("invitation", "Normal"),
    ("heist_contract", "Rare"), ("heist_blueprint", "Rare"),
    ("expedition_logbook", "Rare"), ("flask", "Magic"), ("tincture", "Magic"),
    ("sanctum_relic", "Rare"), ("charm", "Rare"), ("idol", "Rare"),
    ("captured_beast", "Rare"),
])
def test_awakened_supported_categories_use_dedicated_exact(category, rarity):
    item = ParsedItem("Test", rarity, "Test", "Test", category)
    assert uses_dedicated_exact_preset(item)


def test_misc_map_boss_invitation_ignores_fixed_reward_quantity_implicit():
    item = parse_item_text("""アイテムクラス: その他マップアイテム
レアリティ: ノーマル
極性の招待状
--------
アイテムレベル: 83
--------
{ 暗黙モッド }
アイテムの数量のモッドはボスからドロップする報酬の量に影響する
--------
一度ブラック・スターに捕まれば、
逃げ場はない。
--------
自身のマップデバイスで使用することで、極性の虚無へのポータルを開く。
""")
    filters = resolve_trade_stat_filters(item)

    assert item.category == "invitation"
    assert all(row.kind != "implicit" for row in filters)
    assert unresolved_modifier_warnings(item, filters) == ()


@pytest.mark.parametrize(("text", "stat_id", "expected_min"), [
    (
        "自身のアクションスピードは最低でも基礎値の90%となる",
        "explicit.stat_179010262",
        None,
    ),
    (
        "プレイヤーにより凍結させられた敵が受けるダメージが20%増加する",
        "explicit.stat_849085925",
        None,
    ),
    (
        "敵の蠢く虫は2秒ごとにスポーンする",
        "explicit.stat_933024928",
        None,
    ),
    (
        "エルダーアイテムを4個装備していれば反射物理ダメージを受けることがない",
        "explicit.stat_609019022",
        None,
    ),
    (
        "クリティカル時に混沌の力を4秒間獲得する",
        "explicit.stat_1183009081",
        4,
    ),
    (
        "120m以内のレアおよびユニークの敵はミニマップアイコンを持つ",
        "explicit.stat_2543266731",
        120,
    ),
    (
        "レアモンスターを倒すとそのモッドの全てを60秒間獲得する",
        "explicit.stat_2913235441",
        60,
    ),
])
def test_only_api_verified_fixed_number_stats_omit_numeric_bounds(
    text, stat_id, expected_min,
):
    item = parse_item_text(f"""アイテムクラス: 指輪
レアリティ: ユニーク
ファウルボーン テスト
鉄の指輪
--------
アイテムレベル: 85
--------
{{ ファウルボーンユニークモッド }}
{text}
""")

    row = next(
        row for row in resolve_trade_stat_filters(item, trade_base_type="Iron Ring")
        if row.stat_id == stat_id
    )
    assert row.min_value == expected_min
    assert row.max_value is None


@pytest.mark.parametrize("category", ["sentinel"])
def test_product_exclusions_do_not_enter_dedicated_exact(category):
    item = ParsedItem("Test", "Rare", "Test", "Test", category)
    assert not uses_dedicated_exact_preset(item)


def test_dedicated_exact_magic_flask_keeps_t1_t2_and_crafted_only():
    item = ParsedItem(
        item_class="Utility Flasks", rarity="Magic", name="Test", base_type="Granite Flask",
        category="flask", item_level=84,
        modifiers=(
            ItemModifier("T1", (35,), kind="prefix", tier=1, stat_id="explicit.t1"),
            ItemModifier("T3", (20,), kind="suffix", tier=3, stat_id="explicit.t3"),
            ItemModifier("Crafted", (10,), kind="crafted", stat_id="crafted.one"),
        ),
    )
    entries = (
        {"id": "explicit.t1", "text": "T1", "type": "explicit"},
        {"id": "explicit.t3", "text": "T3", "type": "explicit"},
        {"id": "crafted.one", "text": "Crafted", "type": "crafted"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    rows = {row.stat_id: row for row in filters}
    assert rows["explicit.t1"].enabled is True
    assert rows["explicit.t3"].enabled is False
    assert rows["crafted.one"].enabled is True
    assert rows["property.item_level"].enabled is False


def test_dedicated_exact_magic_flask_hides_instilling_enchantment():
    item = parse_item_text("""アイテムクラス: ユーティリティフラスコ
レアリティ: マジック
検査者の 虹の シルバーフラスコ
--------
アイテムレベル: 85
--------
チャージがフルになった時に使用される (enchant)
--------
{ プレフィックスモッド「検査者の」 (ティア: 3) }
持続時間が27(26-30)%増加する
{ サフィックスモッド 「虹の」 (ティア: 1) }
効果中は20(18-20)%の元素耐性が追加される
""")

    filters = resolve_trade_stat_filters(item)
    rows = {row.stat_id: row for row in filters}
    enchant = rows["enchant.stat_3287581721"]
    assert enchant.text == "チャージがフルになった時に使用される (enchant)"
    assert enchant.enabled is False
    assert enchant.hidden_reason
    assert enchant.min_value is None

    query = build_search_query(
        item, "Silver Flask", filters, preset=PRESET_FINISHED,
    )["query"]
    assert not any(
        row["id"] == "enchant.stat_3287581721"
        for row in query["stats"][0]["filters"]
    )


def test_dedicated_exact_magic_flask_keeps_enkindling_enchantment():
    item = ParsedItem(
        "Utility Flasks", "Magic", "Test", "Granite Flask", "flask",
        item_level=84,
        modifiers=(
            ItemModifier(
                "70% increased effect\nGains no Charges during Flask Effect",
                (70,), kind="enchant",
                ref="Gains no Charges during Flask Effect",
                stat_id="enchant.enkindling",
            ),
        ),
    )
    entries = ({
        "id": "enchant.enkindling",
        "text": "#% increased effect\\nGains no Charges during Flask Effect",
        "type": "enchant",
    },)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    enchant = next(row for row in filters if row.stat_id == "enchant.enkindling")
    assert enchant.enabled is True
    assert not enchant.hidden_reason


def test_forbidden_tome_below_83_uses_exact_area_level_range():
    item = ParsedItem(
        item_class="Misc Map Items", rarity="Normal", name="Forbidden Tome",
        base_type="Forbidden Tome", category="unknown", item_level=None,
        properties={"Area Level": "78"}, raw_text="Area Level: 78",
    )
    filters = resolve_trade_stat_filters(item)
    area = next(row for row in filters if row.stat_id == "property.area_level")
    assert area.min_value == 78 and area.max_value == 78 and area.enabled


def test_inscribed_ultimatum_uses_name_only_without_detail_filters():
    item = ParsedItem(
        item_class="Misc Map Items", rarity="Currency",
        name="アルティメイタムの刻印", base_type="Inscribed Ultimatum",
        category="currency", properties={
            "クリア条件": "敵のウェーブを倒せ", "エリアレベル": "83",
            "必要な生贄": "消去のオーブ x4", "報酬": "捧げたカレンシーを倍にする",
        }, modifiers=(ItemModifier("モンスターのダメージが20%増加する", (20,)),),
    )

    assert is_inscribed_ultimatum(item)
    assert resolve_trade_stat_filters(item) == ()
    query = build_search_query(item, "Inscribed Ultimatum")["query"]
    assert query["type"] == "Inscribed Ultimatum"
    assert query["stats"] == [{"type": "and", "filters": []}]
    assert query["filters"] == {}


def test_heist_blueprint_contract_and_logbook_rules():
    blueprint = parse_item_text("""アイテムクラス: 設計図
レアリティ: レア
試作品
設計図
--------
エリアレベル: 83
情報を聞いた区画数: 4
--------
アイテムレベル: 83
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(blueprint)
    ids = {row.stat_id: row for row in filters}
    assert ids["property.area_level"].enabled
    assert ids["property.heist_wings"].min_value == 4
    assert ids["pseudo.pseudo_number_of_enchant_mods"].group_type == "not"
    query = build_search_query(blueprint, "Blueprint", filters)["query"]
    assert query["filters"]["heist_filters"]["filters"]["heist_wings"] == {"min": 4.0}

    contract = parse_item_text("""アイテムクラス: 契約書
レアリティ: レア
試作品
契約書
--------
エリアレベル: 81
必要なジョブ: 知覚能力 レベル 3
依頼書目標の価値: プライスレス
--------
アイテムレベル: 81
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(contract)
    ids = {row.stat_id: row for row in filters}
    assert ids["property.heist_perception"].min_value == 3
    assert ids["property.heist_objective_value"].option_value == "priceless"


def test_current_japanese_blueprint_copy_uses_revealed_wings_like_awakened():
    blueprint = parse_item_text("""アイテムクラス: 計画書
レアリティ: マジック
Stoic Blueprint: Underbelly
--------
エリアレベル: 83
情報を聞いた区画: 1/4
情報を聞いた脱出ルート: 1/8
情報を聞いた報酬部屋: 3/28
必要ジョブ 怪力 (レベル 1)
必要ジョブ 敏捷性 (レベル 1)
必要ジョブ 欺瞞 (レベル 5)
アイテム数量: +16% (augmented)
アイテムレアリティ: +9% (augmented)
アラートレベル減少: +6% (augmented)
ロックダウンまでの時間: +6% (augmented)
活動可能な増援の最大数: +6% (augmented)
--------
アイテムレベル: 83
--------
{ プレフィックスモッド「克己する」 (ティア: 1) }
ガードが受けるダメージが29(30-27)%減少する
--------
ローグハーバーにいる特定のNPCに話しかけ、諜報を使って追加の区画や部屋の情報を聞くことができます。
""")

    assert blueprint.properties["情報を聞いた区画"] == "1/4"
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(blueprint)
    ids = {row.stat_id: row for row in filters}
    assert ids["property.area_level"].min_value == 83
    assert ids["property.heist_wings"].min_value == 1
    assert "property.item_level" not in ids
    assert not any(
        row.stat_id.startswith("property.heist_")
        and row.stat_id != "property.heist_wings"
        for row in filters
    )
    assert not any(row.kind in {"prefix", "suffix"} for row in filters)
    assert unresolved_modifier_warnings(blueprint, filters) == ()

    query = build_search_query(blueprint, "Blueprint: Underbelly", filters)["query"]
    assert query["filters"]["heist_filters"]["filters"]["heist_wings"] == {"min": 1.0}
    assert "ilvl" not in query.get("filters", {}).get("misc_filters", {}).get("filters", {})

    _trade_response_cache.clear()
    response = ({"id": "blueprint-query", "result": [], "total": 0}, {})
    with patch("src.poetore.trade._request_json", return_value=response), patch(
        "src.poetore.trade._japanese_trade_item_type",
        return_value="計画書: 無法地帯",
    ):
        result = search_prices(
            blueprint, "Blueprint: Underbelly", "Standard", stat_filters=filters,
        )
    web_payload = json.loads(parse_qs(urlsplit(result.web_url).query)["q"][0])
    assert web_payload["query"]["type"] == "計画書: 無法地帯"
    assert web_payload["query"]["filters"]["heist_filters"]["filters"][
        "heist_wings"
    ] == {"min": 1.0}

    logbook = parse_item_text("""アイテムクラス: ログブック
レアリティ: レア
遠征ログブック
ログブック
--------
エリアレベル: 82
--------
アイテムレベル: 82
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(logbook)
    assert next(row for row in filters if row.stat_id == "property.area_level").min_value == 81


def test_current_japanese_contract_copy_uses_required_job_like_awakened():
    contract = parse_item_text("""アイテムクラス: 依頼書
レアリティ: レア
Vengeance Pact
Contract: Underbelly
--------
依頼人: 真夜中の修理人
ハイスト目標: アリモルの腕 (中程度な価値)
エリアレベル: 49
必要ジョブ 工作 (レベル 1)
アイテム数量: +64% (augmented)
--------
アイテムレベル: 49
--------
{ プレフィックスモッド「燃える」 (ティア: 4) }
モンスターは物理ダメージの31(30-49)%を追加火ダメージとして与える
{ プレフィックスモッド「連鎖する」 (ティア: 2) }
モンスターのスキルは追加で1回連鎖する
{ プレフィックスモッド「敵愾心の」 (ティア: 4) }
報酬部屋のモンスターが受けるダメージが17(18-16)%減少する
{ サフィックスモッド 「悩みの」 (ティア: 4) }
アラートレベル25%ごとにプレイヤーのアーマーが5%低下する
""")

    assert contract.category == "heist_contract"
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(contract)
    ids = {row.stat_id: row for row in filters}
    assert ids["property.area_level"].min_value == 49
    assert ids["property.heist_engineering"].min_value == 1
    assert ids["property.heist_engineering"].enabled
    assert "property.item_level" not in ids
    assert "property.heist_objective_value" not in ids
    assert not any(row.kind in {"prefix", "suffix"} for row in filters)
    assert unresolved_modifier_warnings(contract, filters) == ()

    query = build_search_query(contract, "Contract: Underbelly", filters)["query"]
    assert query["filters"]["heist_filters"]["filters"]["heist_engineering"] == {
        "min": 1.0,
    }
    assert "ilvl" not in query.get("filters", {}).get("misc_filters", {}).get("filters", {})


def test_logbook_factions_are_parsed_and_only_first_area_is_initially_active():
    item = parse_item_text("""Item Class: Expedition Logbooks
Rarity: Rare
Expedition Logbook
--------
Area Level: 83
--------
Black Scythe Mercenaries
Area contains an Expedition Boss (1)
--------
Druids of the Broken Circle
""")
    entries = (
        {"id": "pseudo.pseudo_logbook_faction_mercenaries", "text": "ログブックは次の組織を含む: 黒い鎌の傭兵団", "type": "pseudo"},
        {"id": "pseudo.pseudo_logbook_faction_druids", "text": "ログブックは次の組織を含む: 壊れた環の祭司", "type": "pseudo"},
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        filters = resolve_trade_stat_filters(item)
    factions = [row for row in filters if row.stat_id.startswith("pseudo.pseudo_logbook_faction_")]
    assert [row.stat_id for row in factions] == [
        "pseudo.pseudo_logbook_faction_mercenaries",
        "pseudo.pseudo_logbook_faction_druids",
    ]
    assert [row.enabled for row in factions] == [True, False]


def test_flask_hybrid_cluster_and_special_area_rules():
    flask = ParsedItem(
        item_class="Utility Flasks", rarity="Magic", name="Test", base_type="Granite Flask",
        category="flask", item_level=84,
        modifiers=(ItemModifier(
            "20% increased Charge Recovery", (20,), ref="#% increased Charge Recovery",
            stat_id="explicit.stat_3196823591",
        ),),
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(flask)
    hybrid = next(row for row in filters if row.kind == "flask hybrid")
    assert hybrid.group_type == "not" and hybrid.enabled

    reduced_hybrid = parse_item_text("""アイテムクラス: ユーティリティフラスコ
レアリティ: マジック
割り当てられた ダイヤモンドフラスコ
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「割り当てられた」 (ティア: 2) }
チャージ回復量が60(55-60)%増加する
効果が25%減少する
""")
    reduced_filters = resolve_trade_stat_filters(reduced_hybrid)
    reduced_effect = next(
        row for row in reduced_filters
        if row.stat_id == "explicit.stat_2448920197"
    )
    assert reduced_effect.inverted and reduced_effect.enabled
    assert not any(row.kind == "flask hybrid" for row in reduced_filters)
    assert unresolved_modifier_warnings(reduced_hybrid, reduced_filters) == ()

    cluster = parse_item_text("""Item Class: Cluster Jewels
Rarity: Rare
Test
Large Cluster Jewel
--------
Item Level: 72
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(cluster)
    level = next(row for row in filters if row.stat_id == "property.item_level")
    assert (level.min_value, level.max_value, level.enabled) == (68, 74, True)

    chronicle = parse_item_text("""アイテムクラス: インカージョンアイテム
レアリティ: ノーマル
アトゾアトルの年代記
--------
エリアレベル: 79
--------
アイテムレベル: 1
""")
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        filters = resolve_trade_stat_filters(chronicle)
    assert next(row for row in filters if row.stat_id == "property.area_level").min_value == 78


def test_atzoatl_room_rules_match_awakened_priorities_and_visibility():
    def room(ref, option=1):
        return TradeStatFilter(
            f"pseudo.{ref}", ref, None, "pseudo", True,
            ref=ref, option_value=option,
        )

    area = TradeStatFilter(
        "property.area_level", "エリアレベル", 78, "special", True,
    )
    rows = _apply_atzoatl_room_rules([
        area,
        room("Has Room: Banquet Hall"),
        room("Has Room: Corruption Chamber (Tier 1)"),
        room("Has Room: Locus of Corruption (Tier 3)"),
        room("Has Room: Wealth of the Vaal (Tier 3)"),
        room("Has Room: Treasury (Tier 2)"),
        room("Has Room: Vault (Tier 1)"),
        room("Has Room: Storm of Corruption (Tier 3)"),
    ])
    by_ref = {row.ref: row for row in rows if row.ref}

    assert area in rows
    assert "Has Room: Banquet Hall" not in by_ref
    assert "Has Room: Corruption Chamber (Tier 1)" not in by_ref
    assert by_ref["Has Room: Locus of Corruption (Tier 3)"].enabled
    assert by_ref["Has Room: Wealth of the Vaal (Tier 3)"].enabled
    assert not by_ref["Has Room: Treasury (Tier 2)"].enabled
    assert by_ref["Has Room: Vault (Tier 1)"].hidden_reason
    assert by_ref["Has Room: Storm of Corruption (Tier 3)"].hidden_reason


def test_atzoatl_obstructed_room_requires_open_explosives():
    def room(ref, option):
        return TradeStatFilter(
            f"pseudo.{ref}", ref, None, "pseudo", True,
            ref=ref, option_value=option,
        )

    obstructed = room("Has Room: Treasury (Tier 2)", 2)
    assert _apply_atzoatl_room_rules([obstructed]) == []

    rows = _apply_atzoatl_room_rules([
        room("Has Room: Explosives Room (Tier 1)", 1),
        obstructed,
    ])
    assert len(rows) == 1
    assert rows[0].ref == "Has Room: Treasury (Tier 2)"
    assert rows[0].option_value is None
    assert rows[0].enabled is False


def test_cluster_uses_finished_and_base_presets_and_flask_tincture_ilvl_is_disabled():
    cluster = ParsedItem("Cluster Jewels", "Rare", "Test", "Large Cluster Jewel",
                         "cluster_jewel", item_level=84)
    assert not uses_dedicated_exact_preset(cluster)
    assert available_trade_presets(cluster) == (PRESET_FINISHED, PRESET_BASE)
    for category, item_class, base in (
        ("flask", "Utility Flasks", "Granite Flask"),
        ("tincture", "Tinctures", "Prismatic Tincture"),
    ):
        item = ParsedItem(item_class, "Magic", "Test", base, category, item_level=84)
        with patch("src.poetore.trade._trade_stat_entries", return_value=()):
            rows = resolve_trade_stat_filters(item)
        ilvl = next(row for row in rows if row.stat_id == "property.item_level")
        assert ilvl.enabled is False


def test_rare_jewel_mods_start_off_and_magic_affixes_start_on():
    entries = (
        {"id": "explicit.life", "text": "+# to maximum Life", "type": "explicit"},
    )
    modifier = ItemModifier(
        "+20 to maximum Life", (20,), kind="prefix", ref="+# to maximum Life",
        stat_id="explicit.life",
    )
    for rarity, expected in (("Rare", False), ("Magic", True)):
        item = ParsedItem("Jewels", rarity, "Test", "Crimson Jewel", "jewel",
                          modifiers=(modifier,))
        with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
            rows = resolve_trade_stat_filters(item)
        assert next(row for row in rows if row.stat_id == "explicit.life").enabled is expected


def test_exact_map_starts_with_tier_and_all_explicit_mods_on():
    item = ParsedItem(
        "Maps", "Rare", "Test", "Cemetery Map", "map",
        properties={"Map Tier": "16", "Item Quantity": "+100%"},
        modifiers=(ItemModifier(
            "Monsters deal 100% extra Damage", (100,), kind="explicit",
            stat_id="explicit.map_damage",
        ),),
    )
    entries = ({"id": "explicit.map_damage", "text": "Monsters deal #% extra Damage",
                "type": "explicit"},)
    with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
        rows = resolve_trade_stat_filters(item)
    by_id = {row.stat_id: row for row in rows}
    assert by_id["property.map_tier"].enabled is True
    assert "property.map_quantity" not in by_id
    assert by_id["explicit.map_damage"].enabled is True
    query = build_search_query(
        item, "Cemetery Map", rows, preset=PRESET_FINISHED,
    )["query"]
    assert {
        "id": "explicit.map_damage",
        "value": {"min": 100.0},
    } in query["stats"][0]["filters"]


def test_corrupted_map_value_properties_start_on():
    item = ParsedItem(
        "Maps", "Rare", "Test", "Cemetery Map", "map",
        properties={
            "Map Tier": "16", "Item Quantity": "+100%",
            "Item Rarity": "+55%", "Monster Pack Size": "+32%",
        },
        flags=("corrupted",),
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        rows = resolve_trade_stat_filters(item)
    by_id = {row.stat_id: row for row in rows}
    for stat_id in (
        "property.map_quantity", "property.map_rarity",
        "property.map_pack_size",
    ):
        assert by_id[stat_id].enabled is True


def test_more_drops_map_enables_value_pseudos_but_not_rarity():
    item = ParsedItem(
        "Maps", "Rare", "Test", "Cemetery Map", "map",
        properties={
            "Map Tier": "16", "Item Quantity": "+100%",
            "Item Rarity": "+55%", "Monster Pack Size": "+32%",
            "More Scarabs": "150%",
        },
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        rows = resolve_trade_stat_filters(item)
    by_id = {row.stat_id: row for row in rows}
    assert by_id["property.map_quantity"].enabled is True
    assert by_id["property.map_rarity"].enabled is False
    assert by_id["property.map_pack_size"].enabled is True
    assert by_id["pseudo.pseudo_map_more_scarab_drops"].enabled is True


def test_japanese_nightmare_map_new_more_drop_labels_and_mods_resolve():
    item = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
黒焦げの覚悟
ナイトメアマップ
--------
アイテム数量: +101% (augmented)
アイテムレアリティ: +63% (augmented)
モンスターパックサイズ: +53% (augmented)
マップ量が上昇: +35% (augmented)
スカラベ量が上昇: +88% (augmented)
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「不安定な」 (ティア: 1) }
レアモンスターはボラタイルコアを持つ
{ サフィックスモッド 「ぬかるみの」 (ティア: 1) }
プレイヤーの防御力が30(30-25)%低下する
(アーマー、回避力、エナジーシールドは標準的な防御力である)
{ サフィックスモッド 「耐久力の」 }
モンスターはヒット時にエンデュランスチャージを1個獲得する
{ サフィックスモッド 「ぬかるみの」 — アタック }
全てのプレイヤーはスペルダメージを抑制して防ぐダメージ割合が-20%される
(抑制したヒットによるダメージとそのヒットが付与した
状態異常によるダメージの40%を防ぐ)
--------
コラプト状態
""")
    rows = resolve_trade_stat_filters(item)
    by_id = {row.stat_id: row for row in rows}

    assert by_id["pseudo.pseudo_map_more_map_drops"].min_value == 35
    assert by_id["pseudo.pseudo_map_more_map_drops"].text == "マップ量"
    assert by_id["pseudo.pseudo_map_more_scarab_drops"].min_value == 88
    assert by_id["pseudo.pseudo_map_more_scarab_drops"].text == "スカラベ量"
    assert by_id["property.map_rarity"].enabled is False
    assert by_id["explicit.stat_1706239920"].min_value == 100
    assert by_id["explicit.stat_943960754"].min_value == 30
    assert by_id["explicit.stat_943960754"].inverted is True
    assert by_id["explicit.stat_687813731"].min_value == 100
    assert by_id["explicit.stat_286947568"].min_value == -20
    assert unresolved_modifier_warnings(item, rows) == ()
    query = build_search_query(item, "Nightmare Map", rows)["query"]
    api_rows = {
        row["id"]: row.get("value", {})
        for group in query["stats"] for row in group["filters"]
    }
    assert api_rows["explicit.stat_943960754"] == {"max": -30.0}


def test_japanese_map_new_currency_and_divination_card_drop_labels_resolve():
    item = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
苦悩する中核
マップ (ティア 16)
--------
アイテム数量: +80% (augmented)
アイテムレアリティ: +41% (augmented)
モンスターパックサイズ: +26% (augmented)
カレンシー量が上昇: +139% (augmented)
占いカード増加: +50% (augmented)
品質 (占いカード): +20% (augmented)
--------
アイテムレベル: 85
--------
モンスターレベル：83
--------
{ 暗黙モッド }
エリアはオリジネイターのメモリーインフルエンスを受けている
--------
コラプト状態
""")
    rows = resolve_trade_stat_filters(item)
    by_id = {row.stat_id: row for row in rows}

    currency = by_id["pseudo.pseudo_map_more_currency_drops"]
    assert currency.text == "カレンシー量"
    assert currency.min_value == 139
    assert currency.enabled is True

    cards = by_id["pseudo.pseudo_map_more_card_drops"]
    assert cards.text == "占いカード量"
    assert cards.min_value == 50
    assert cards.enabled is True

    query = build_search_query(item, item.base_type, rows)["query"]
    api_rows = {
        row["id"]: row.get("value", {})
        for group in query["stats"] for row in group["filters"]
    }
    assert api_rows["pseudo.pseudo_map_more_currency_drops"] == {"min": 139.0}
    assert api_rows["pseudo.pseudo_map_more_card_drops"] == {"min": 50.0}


def test_corrupted_eight_mod_map_enables_modifier_count_pseudo():
    modifiers = tuple(
        ItemModifier(
            f"Map modifier {index}", (index,),
            kind="prefix" if index < 4 else "suffix",
        )
        for index in range(8)
    )
    item = ParsedItem(
        "Maps", "Rare", "Test", "Cemetery Map", "map",
        properties={"Map Tier": "16", "Item Quantity": "+100%"},
        modifiers=modifiers, flags=("corrupted",),
    )
    with patch("src.poetore.trade._trade_stat_entries", return_value=()):
        rows = resolve_trade_stat_filters(item)
    count = next(
        row for row in rows
        if row.stat_id == "pseudo.pseudo_number_of_affix_mods"
    )
    assert count.enabled is True
    assert count.min_value == 8
    assert count.max_value == 8
    query = build_search_query(
        item, "Cemetery Map", rows, preset=PRESET_FINISHED,
    )["query"]
    assert {
        "id": "pseudo.pseudo_number_of_affix_mods",
        "value": {"min": 8.0, "max": 8.0},
    } in query["stats"][0]["filters"]
