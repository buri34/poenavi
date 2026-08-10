from src.poetore.models import ParsedItem
from src.poetore.parser import parse_item_text
from src.poetore.poe_ninja import (
    CACHE_TTL_SECONDS, PoeNinjaPrice, PoeNinjaPriceService, divine_chaos_rate,
    match_poe_ninja_price,
    match_poe_ninja_identity,
)
from src.poetore.trade import english_trade_identity


def test_related_item_identity_matches_unique_variant():
    payload = {
        "currencyOverviews": [{
            "type": "Currency",
            "lines": [{"name": "Divine Orb", "chaos": 200}],
        }],
        "itemOverviews": [{
            "type": "UniqueArmour",
            "lines": [{
                "name": "Skin of the Loyal", "variant": "Simple Robe, 6L",
                "chaos": 320, "graph": [], "sparkLine": {"totalChange": 1},
            }],
        }],
    }
    price = match_poe_ninja_identity(
        payload, "UNIQUE", "Skin of the Loyal", "Simple Robe", "Standard",
    )
    assert price is not None
    assert price.chaos == 320


def test_related_doryani_delusion_identity_uses_awakened_base_variants():
    payload = {
        "itemOverviews": [{
            "type": "UniqueArmour",
            "lines": [
                {"name": "Doryani's Delusion", "variant": "Leviathan Greaves", "chaos": 10},
                {"name": "Doryani's Delusion", "variant": "Warlock Boots", "chaos": 20},
                {"name": "Doryani's Delusion", "variant": "Velour Boots", "chaos": 30},
            ],
        }],
    }

    prices = [
        match_poe_ninja_identity(
            payload, "UNIQUE", "Doryani's Delusion", variant, "Standard",
        )
        for variant in ("Leviathan Greaves", "Warlock Boots", "Velour Boots")
    ]

    assert [price.chaos for price in prices if price is not None] == [10, 20, 30]


def test_related_captured_beast_identity_matches_beast_overview():
    payload = {
        "itemOverviews": [{
            "type": "Beast",
            "lines": [{
                "name": "Wild Hellion Alpha", "chaos": 42,
                "graph": [], "sparkLine": {"totalChange": 3},
            }],
        }],
    }

    price = match_poe_ninja_identity(
        payload, "CAPTURED_BEAST", "Wild Hellion Alpha", None, "Standard",
    )

    assert price is not None
    assert price.chaos == 42
    assert price.source_type == "Beast"
    assert "/beasts/wild-hellion-alpha" in price.url


def _payload():
    return {
        "currencyOverviews": [{
            "type": "Currency", "lines": [
                {"name": "Divine Orb", "chaos": 200, "graph": [0, 1, 2, 3, 4, 5, 6]},
                {"name": "Chaos Orb", "chaos": 1, "graph": [0, -1, -2, -1, 0, 1, 2]},
            ],
        }],
        "itemOverviews": [
            {"type": "UniqueAccessory", "lines": [
                {"name": "Mageblood", "variant": "4 Flasks, Heavy Belt", "chaos": 40000,
                 "graph": [0, 1, 2, 3, 4, 5, 6]},
            ]},
            {"type": "SkillGem", "lines": [
                {"name": "Arc", "variant": "20/20c", "chaos": 60,
                 "graph": [-2, -1, 0, 1, 2, 3, 4]},
            ]},
            {"type": "BlightedMap", "lines": [
                {"name": "Blighted Map (Tier 16)", "variant": "T0, Gen-24", "chaos": 12,
                 "graph": [0, 0, 1, 1, 2, 2, 3]},
            ]},
            {"type": "DivinationCard", "lines": [
                {"name": "The Doctor", "chaos": 1800, "graph": [0, 1, 0, -1, 0, 1, 0]},
            ]},
            {"type": "BaseType", "lines": [
                {"name": "Heavy Belt", "variant": "86+", "chaos": 50, "graph": []},
            ]},
            {"type": "ClusterJewel", "lines": [
                {"name": "12% increased Fire Damage", "variant": "8 passives, 84", "chaos": 80,
                 "graph": []},
            ]},
        ],
    }


def test_unique_price_uses_name_and_formats_divines():
    item = ParsedItem("Belts", "Unique", "Mageblood", "Heavy Belt", "accessory")
    price = match_poe_ninja_price(
        _payload(), item, "Standard", trade_name="Mageblood", trade_base_type="Heavy Belt",
    )
    assert price is not None
    assert price.display_price_parts() == ("200", "divine")
    assert price.display_price() == "200 div"
    assert price.graph_points() == (0, 1, 2, 3, 4, 5, 6)
    assert "/unique-accessories/mageblood-4-flasks-heavy-belt" in price.url
    assert price.source_type == "UniqueAccessory"


def test_mageblood_price_matches_japanese_flask_count_variant():
    payload = _payload()
    payload["itemOverviews"][0]["lines"] = [
        {"name": "Mageblood", "variant": f"{count} Flasks, Heavy Belt", "chaos": chaos}
        for count, chaos in ((2, 2000), (3, 3000), (4, 4000), (5, 5000))
    ]
    item = parse_item_text("""アイテムクラス: ベルト
レアリティ: ユニーク
メイジブラッド
ヘビーベルト
--------
品質 (耐性モッド): +10% (augmented)
幽体化度: 21%
--------
装備要求:
レベル: 44
--------
アイテムレベル: 80
--------
{ 暗黙モッド — 能力値 }
筋力 +35(25-35)
--------
{ ユニークモッド — 能力値 }
器用さ +39(30-50)
{ ユニークモッド — 元素, 火, 耐性 - 10%増加 }
火耐性 +23(15-25)%
{ ユニークモッド — 元素, 冷気, 耐性 - 10%増加 }
冷気耐性 +23(15-25)%
{ ユニークモッド }
マジックのユーティリティフラスコを使用することができない
{ ユニークモッド }
左から4(2-4)個のマジックユーティリティフラスコのフラスコ効果が常にプレイヤーに適用される
{ ユニークモッド }
マジックユーティリティフラスコの効果が取り除かれることがない
--------
お前の血管には力の川が流れている。
""")

    price = match_poe_ninja_price(
        payload, item, "Standard", trade_name="Mageblood", trade_base_type="Heavy Belt",
    )

    assert price is not None
    assert price.variant == "4 Flasks, Heavy Belt"
    assert price.chaos == 4000


def test_mageblood_price_matches_english_flask_count_variant():
    payload = _payload()
    payload["itemOverviews"][0]["lines"] = [
        {"name": "Mageblood", "variant": f"{count} Flasks, Heavy Belt", "chaos": chaos}
        for count, chaos in ((2, 2000), (3, 3000), (4, 4000), (5, 5000))
    ]
    item = ParsedItem(
        "Belts", "Unique", "Mageblood", "Heavy Belt", "accessory",
        raw_text="Leftmost 3 Magic Utility Flasks constantly apply their Flask Effects to you",
    )

    price = match_poe_ninja_price(
        payload, item, "Standard", trade_name="Mageblood", trade_base_type="Heavy Belt",
    )

    assert price is not None
    assert price.variant == "3 Flasks, Heavy Belt"
    assert price.chaos == 3000


def test_mageblood_price_stays_hidden_when_flask_count_is_unknown():
    payload = _payload()
    payload["itemOverviews"][0]["lines"] = [
        {"name": "Mageblood", "variant": f"{count} Flasks, Heavy Belt", "chaos": chaos}
        for count, chaos in ((2, 2000), (3, 3000), (4, 4000), (5, 5000))
    ]
    item = ParsedItem("Belts", "Unique", "Mageblood", "Heavy Belt", "accessory")

    assert match_poe_ninja_price(
        payload, item, "Standard", trade_name="Mageblood", trade_base_type="Heavy Belt",
    ) is None


def test_small_price_uses_chaos_display_parts():
    price = PoeNinjaPrice("Arc", None, 8.5, (), "https://example.com", 200)
    assert price.display_price_parts() == ("8.5", "chaos")
    assert price.display_price() == "8.5 chaos"


def test_divine_chaos_rate_uses_currency_overview_and_rejects_invalid_values():
    assert divine_chaos_rate(_payload()) == 200
    payload = _payload()
    payload["currencyOverviews"][0]["lines"][0]["chaos"] = 29.9
    assert divine_chaos_rate(payload) is None


def test_trend_summary_uses_signed_total_change_instead_of_graph_deviation():
    falling = PoeNinjaPrice(
        "Test", None, 8, (0, 0, 0, 0, 0, 0, -20), "https://example.com",
        total_change=-20,
    )
    rising = PoeNinjaPrice(
        "Test", None, 8, (0, 0, 0, 0, 0, 0, 12), "https://example.com",
        total_change=12,
    )
    assert falling.trend_summary() == ("↘", "-20%")
    assert rising.trend_summary() == ("↗", "+12%")


def test_gem_price_uses_level_quality_and_corruption_variant():
    item = ParsedItem(
        "Skill Gems", "Gem", "Arc", "Arc", "gem",
        properties={"Gem Level": "20", "Quality": "+20%"}, flags=("corrupted",),
    )
    price = match_poe_ninja_price(_payload(), item, "Standard", trade_base_type="Arc")
    assert price is not None and price.name == "Arc" and price.variant == "20/20c"


def test_blighted_map_price_uses_tier_and_state():
    item = ParsedItem(
        "Maps", "Rare", "Map (Tier 16)", "Map (Tier 16)", "map",
        raw_text="Blighted Map (Tier 16)\nArea is infested with Fungal Growth",
    )
    price = match_poe_ninja_price(_payload(), item, "Standard")
    assert price is not None and price.name == "Blighted Map (Tier 16)"


def test_exact_name_item_price_is_supported():
    item = ParsedItem("Divination Cards", "Normal", "The Doctor", "The Doctor", "divination_card")
    price = match_poe_ninja_price(_payload(), item, "Standard", trade_base_type="The Doctor")
    assert price is not None and price.chaos == 1800


def test_scarab_price_uses_only_scarab_overview():
    payload = {
        "itemOverviews": [
            {"type": "Map", "lines": [
                {"name": "Divination Scarab of Plenty", "chaos": 999, "graph": []},
            ]},
            {"type": "Scarab", "lines": [
                {"name": "Divination Scarab of Plenty", "chaos": 14.9,
                 "graph": [], "sparkLine": {"totalChange": 2}},
            ]},
        ],
    }
    item = ParsedItem(
        "マップフラグメント", "ノーマル",
        "豊富な占いのスカラベ", "豊富な占いのスカラベ", "scarab",
    )

    price = match_poe_ninja_price(
        payload, item, "Allflame", trade_base_type="Divination Scarab of Plenty",
    )

    assert price is not None
    assert price.chaos == 14.9
    assert price.source_type == "Scarab"
    assert "/scarabs/divination-scarab-of-plenty" in price.url


def test_reported_japanese_scarab_copy_reaches_poe_ninja_price():
    item = parse_item_text("""アイテムクラス: マップフラグメント
レアリティ: ノーマル
豊富な占いのスカラベ
--------
スタック数: 12/20
個数制限: 5
--------
エリアには占いカードをドロップする確率が1000%増加した
占いに触れられしマジックモンスターパックが6から10パック追加で出現する
--------
全ての行動は一千の未来を作る。
--------
自身のマップデバイスで使用してマップにモッドを追加できる。
""")
    trade_type, trade_name = english_trade_identity(item)
    payload = {"itemOverviews": [{"type": "Scarab", "lines": [{
        "name": "Divination Scarab of Plenty", "chaos": 14.9,
        "graph": [], "sparkLine": {"totalChange": 2},
    }]}]}

    price = match_poe_ninja_price(
        payload, item, "Allflame",
        trade_name=trade_name, trade_base_type=trade_type,
    )

    assert item.category == "scarab"
    assert trade_type == "Divination Scarab of Plenty"
    assert price is not None and price.chaos == 14.9


def test_japanese_finishing_touch_uses_correct_poe_ninja_identity():
    payload = {
        "itemOverviews": [{
            "type": "DivinationCard",
            "lines": [
                {"name": "The Fiend", "chaos": 1000, "graph": []},
                {"name": "The Finishing Touch", "chaos": 7, "graph": []},
            ],
        }],
    }
    item = ParsedItem(
        "占いカード", "ノーマル", "最後の仕上げ", "最後の仕上げ",
        "divination_card",
    )
    trade_type, trade_name = english_trade_identity(item)

    price = match_poe_ninja_price(
        payload, item, "Standard",
        trade_name=trade_name, trade_base_type=trade_type,
    )

    assert trade_type == "The Finishing Touch"
    assert price is not None
    assert price.name == "The Finishing Touch"
    assert price.chaos == 7


def test_duplicate_currency_overviews_are_deduplicated():
    payload = _payload()
    payload["itemOverviews"].append(payload["currencyOverviews"][0])
    item = ParsedItem("Currency", "Currency", "Chaos Orb", "Chaos Orb", "currency")
    price = match_poe_ninja_price(payload, item, "Standard", trade_base_type="Chaos Orb")
    assert price is not None and price.chaos == 1


def test_nonunique_basetype_and_cluster_jewel_are_intentionally_excluded():
    base = ParsedItem("Belts", "Rare", "Test", "Heavy Belt", "accessory", item_level=86)
    cluster = ParsedItem(
        "Cluster Jewels", "Rare", "Test", "Large Cluster Jewel", "cluster_jewel", item_level=84,
    )
    assert match_poe_ninja_price(_payload(), base, "Standard", trade_base_type="Heavy Belt") is None
    assert match_poe_ninja_price(_payload(), cluster, "Standard") is None


def test_service_caches_each_league_for_31_minutes():
    calls = []
    now = [100.0]

    def fetcher(league):
        calls.append(league)
        return _payload()

    service = PoeNinjaPriceService(
        fetcher=fetcher, stash_fetcher=lambda _league, _type: {"lines": []},
        clock=lambda: now[0],
    )
    item = ParsedItem("Divination Cards", "Normal", "The Doctor", "The Doctor", "divination_card")
    assert service.lookup(item, "Standard") is not None
    assert service.lookup(item, "Standard") is not None
    assert calls == ["Standard"]
    now[0] += CACHE_TTL_SECONDS + 1
    assert service.lookup(item, "Standard") is not None
    assert calls == ["Standard", "Standard"]


def test_divine_rate_and_item_lookup_share_the_same_league_cache():
    calls = []

    def fetcher(league):
        calls.append(league)
        return _payload()

    service = PoeNinjaPriceService(
        fetcher=fetcher, stash_fetcher=lambda _league, _type: {"lines": []},
    )
    item = ParsedItem("Divination Cards", "Normal", "The Doctor", "The Doctor", "divination_card")
    assert service.divine_chaos_rate("Standard") == 200
    assert service.lookup(item, "Standard") is not None
    assert calls == ["Standard"]


def test_private_league_is_not_fetched():
    service = PoeNinjaPriceService(fetcher=lambda _league: (_ for _ in ()).throw(AssertionError()))
    item = ParsedItem("Divination Cards", "Normal", "The Doctor", "The Doctor", "divination_card")
    assert service.lookup(item, "My League (PL12345)") is None


def test_service_refreshes_item_price_and_trend_from_current_stash_overview():
    stash_calls = []

    def stash_fetcher(league, type_name):
        stash_calls.append((league, type_name))
        return {"lines": [{
            "detailsId": "mageblood-4-flasks-heavy-belt",
            "chaosValue": 42000,
            "sparkLine": {"totalChange": -20, "data": [0, 0, 0, 0, 0, 0, -20]},
        }]}

    service = PoeNinjaPriceService(fetcher=lambda _league: _payload(), stash_fetcher=stash_fetcher)
    item = ParsedItem("Belts", "Unique", "Mageblood", "Heavy Belt", "accessory")
    price = service.lookup(
        item, "Standard", trade_name="Mageblood", trade_base_type="Heavy Belt",
    )
    assert price is not None
    assert price.chaos == 42000
    assert price.graph_points() == (0, 0, 0, 0, 0, 0, -20)
    assert price.trend_summary() == ("↘", "-20%")
    assert stash_calls == [("Standard", "UniqueAccessory")]
