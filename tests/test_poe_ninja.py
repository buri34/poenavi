import pytest

from src.poetore.models import ParsedItem
from src.poetore.parser import parse_item_text
from src.poetore.poe_ninja import (
    CACHE_TTL_SECONDS, PoeNinjaPrice, PoeNinjaPriceService, divine_chaos_rate,
    match_poe_ninja_price,
    match_poe_ninja_identity,
    match_poe2_exchange_price,
    match_poe2_unique_price,
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


def test_new_awakened_currency_categories_are_supported():
    payload = {
        "itemOverviews": [
            {"type": "Ducat", "lines": [{
                "name": "Merrick's Ducat", "chaos": 14.43,
                "graph": [], "sparkLine": {"totalChange": 2},
            }]},
            {"type": "EnshroudingCrystal", "lines": [{
                "name": "Imperial Enshrouding Crystal", "chaos": 1.12,
                "graph": [], "sparkLine": {"totalChange": -1},
            }]},
        ],
    }

    cases = (
        ("Merrick's Ducat", "Ducat", 14.43, "/ducats/merricks-ducat"),
        (
            "Imperial Enshrouding Crystal", "EnshroudingCrystal", 1.12,
            "/enshrouding-crystals/imperial-enshrouding-crystal",
        ),
    )
    for name, source_type, chaos, url_path in cases:
        item = ParsedItem("Stackable Currency", "Currency", name, name, "currency")
        price = match_poe_ninja_price(
            payload, item, "Allflame", trade_base_type=name,
        )
        assert price is not None
        assert price.source_type == source_type
        assert price.chaos == chaos
        assert url_path in price.url


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


def _poe2_unique_payload():
    return {
        "core": {
            "items": [{"id": "divine", "name": "Divine Orb"}],
            "rates": {"chaos": 7.73},
            "primary": "divine",
            "secondary": "chaos",
        },
        "lines": [{
            "name": "Mageblood",
            "baseType": "Utility Belt",
            "detailsId": "mageblood-utility-belt",
            "primaryValue": 350.0,
            "listingCount": 5993,
            "corrupted": False,
            "sparkLine": {"totalChange": -7.89, "data": [0, None, -2.63, None, -7.89]},
        }],
    }


def test_poe2_unique_overview_matches_name_base_and_divine_value():
    item = ParsedItem("Belts", "Unique", "Mageblood", "Utility Belt", "belt")
    price = match_poe2_unique_price(
        _poe2_unique_payload(), item, "Runes of Aldur",
        trade_name="Mageblood", trade_base_type="Utility Belt",
    )
    assert price is not None
    assert price.display_price() == "350 div"
    assert price.trend_summary() == ("↘", "-8%")
    assert price.url == (
        "https://poe.ninja/poe2/economy/runesofaldur/"
        "unique-accessories/mageblood-utility-belt"
    )


def test_poe2_unique_hc_overview_uses_poe_ninja_suffix_slug():
    item = ParsedItem("Belts", "Unique", "Mageblood", "Utility Belt", "belt")
    price = match_poe2_unique_price(
        _poe2_unique_payload(), item, "HC Runes of Aldur",
        trade_name="Mageblood", trade_base_type="Utility Belt",
    )
    assert price is not None
    assert price.url == (
        "https://poe.ninja/poe2/economy/runesofaldurhc/"
        "unique-accessories/mageblood-utility-belt"
    )


def test_poe2_unique_service_uses_plural_overview_type_and_cache():
    calls = []

    def poe2_fetcher(league, type_name):
        calls.append((league, type_name))
        return _poe2_unique_payload()

    service = PoeNinjaPriceService(poe2_fetcher=poe2_fetcher)
    item = ParsedItem("Belts", "Unique", "Mageblood", "Utility Belt", "belt")
    assert service.lookup_poe2_unique(item, "Runes of Aldur") is not None
    assert service.lookup_poe2_unique(item, "Runes of Aldur") is not None
    assert calls == [("Runes of Aldur", "UniqueAccessories")]


def _poe2_exchange_payload():
    return {
        "core": {
            "primary": "divine",
            "secondary": "chaos",
            "rates": {"exalted": 364.9, "chaos": 7.74},
        },
        "items": [{
            "id": "uncut-skill-gem-18",
            "name": "Uncut Skill Gem (Level 18)",
            "detailsId": "uncut-skill-gem-level-18",
        }],
        "lines": [{
            "id": "uncut-skill-gem-18",
            "primaryValue": 0.001535,
            "maxVolumeCurrency": "exalted",
            "maxVolumeRate": 1.79,
            "sparkline": {"totalChange": 12.4, "data": [1, 3, 12.4]},
        }],
    }


def test_poe2_divine_exalted_rate_uses_currency_exchange_core_and_cache():
    calls = []

    def fetcher(league, type_name):
        calls.append((league, type_name))
        return _poe2_exchange_payload()

    service = PoeNinjaPriceService(poe2_exchange_fetcher=fetcher)
    assert service.divine_exalted_rate("Runes of Aldur") == 364.9
    assert service.divine_exalted_rate("Runes of Aldur") == 364.9
    assert calls == [("Runes of Aldur", "Currency")]


def test_poe2_exchange_matches_uncut_gem_and_uses_most_traded_quote_currency():
    item = ParsedItem(
        "Uncut Skill Gems", "currency", "Uncut Skill Gem (Level 18)",
        "Uncut Skill Gem (Level 18)", "uncut_gem",
    )
    price = match_poe2_exchange_price(
        _poe2_exchange_payload(), item, "Runes of Aldur", source_type="UncutGems",
    )
    assert price is not None
    assert price.display_price_parts() == ("0.56", "exalted")
    assert price.url == (
        "https://poe.ninja/poe2/economy/runesofaldur/"
        "uncut-gems/uncut-skill-gem-level-18"
    )


def test_poe2_exchange_hc_overview_uses_poe_ninja_suffix_slug():
    item = ParsedItem(
        "Uncut Skill Gems", "currency", "Uncut Skill Gem (Level 18)",
        "Uncut Skill Gem (Level 18)", "uncut_gem",
    )
    price = match_poe2_exchange_price(
        _poe2_exchange_payload(), item, "HC Runes of Aldur", source_type="UncutGems",
    )
    assert price is not None
    assert price.url == (
        "https://poe.ninja/poe2/economy/runesofaldurhc/"
        "uncut-gems/uncut-skill-gem-level-18"
    )


def test_poe2_exchange_service_uses_exchange_category_and_cache():
    calls = []

    def fetcher(league, type_name):
        calls.append((league, type_name))
        return _poe2_exchange_payload()

    service = PoeNinjaPriceService(poe2_exchange_fetcher=fetcher)
    item = ParsedItem(
        "Uncut Skill Gems", "currency", "Uncut Skill Gem (Level 18)",
        "Uncut Skill Gem (Level 18)", "uncut_gem",
    )
    assert service.lookup_poe2_exchange(item, "Runes of Aldur") is not None
    assert service.lookup_poe2_exchange(item, "Runes of Aldur") is not None
    assert calls == [("Runes of Aldur", "UncutGems")]


@pytest.mark.parametrize(
    ("category", "name", "source_type", "slug"),
    [
        ("soul_core", "Soul Core of Topotante", "SoulCores", "soul-cores"),
        ("rune", "Greater Iron Rune", "Runes", "runes"),
    ],
)
def test_poe2_augments_use_their_exchange_overviews(
    category, name, source_type, slug,
):
    calls = []

    def fetcher(league, type_name):
        calls.append((league, type_name))
        return {
            "core": {
                "primary": "divine", "rates": {"chaos": 7.74, "exalted": 366.6},
            },
            "items": [{"id": "augment", "name": name, "detailsId": "augment"}],
            "lines": [{
                "id": "augment", "primaryValue": 0.0126,
                "maxVolumeCurrency": "exalted", "maxVolumeRate": 1 / 4.62,
                "sparkline": {"data": [], "totalChange": 0},
            }],
        }

    service = PoeNinjaPriceService(poe2_exchange_fetcher=fetcher)
    item = ParsedItem(category, "currency", name, name, category)
    price = service.lookup_poe2_exchange(item, "Runes of Aldur")

    assert price is not None
    assert price.source_type == source_type
    assert price.display_price_parts() == ("4.6", "exalted")
    assert price.url.endswith(f"/{slug}/augment")
    assert calls == [("Runes of Aldur", source_type)]


@pytest.mark.parametrize(
    ("category", "name", "source_type"),
    [
        ("currency", "Greater Essence of Enhancement", "Essences"),
        ("currency", "Simulacrum Splinter", "Delirium"),
        ("currency", "Adaptive Catalyst", "Breach"),
        ("currency", "Adaptive Alloy", "Verisium"),
        ("rune", "Bear Idol", "Idols"),
        ("rune", "Ancient Jawbone", "Abyss"),
    ],
)
def test_poe2_dedicated_exchange_categories_are_discovered(
    category, name, source_type,
):
    calls = []

    def fetcher(league, type_name):
        calls.append((league, type_name))
        items = []
        lines = []
        if type_name == source_type:
            items = [{"id": "item", "name": name, "detailsId": "item"}]
            lines = [{
                "id": "item", "primaryValue": 0.01,
                "maxVolumeCurrency": "exalted", "maxVolumeRate": 0.25,
                "sparkline": {"data": [], "totalChange": 0},
            }]
        return {
            "core": {
                "primary": "divine", "rates": {"chaos": 7.74, "exalted": 366.6},
            },
            "items": items,
            "lines": lines,
        }

    service = PoeNinjaPriceService(poe2_exchange_fetcher=fetcher)
    item = ParsedItem("Currency", "currency", name, name, category)
    price = service.lookup_poe2_exchange(item, "Runes of Aldur")

    assert price is not None
    assert price.source_type == source_type
    assert calls[-1] == ("Runes of Aldur", source_type)


def test_poe2_related_identities_use_pinned_categories_and_share_cache():
    exchange_calls = []
    unique_calls = []

    def exchange_fetcher(league, type_name):
        exchange_calls.append((league, type_name))
        payload = _poe2_exchange_payload()
        payload["items"] = [{"id": "fragment", "name": "Primary Calamity Fragment",
                             "detailsId": "primary-calamity-fragment"}]
        payload["lines"] = [{"id": "fragment", "primaryValue": 1.0,
                             "maxVolumeCurrency": "divine", "maxVolumeRate": 1.0,
                             "sparkline": {"data": [], "totalChange": 0}}]
        return payload

    def unique_fetcher(league, type_name):
        unique_calls.append((league, type_name))
        payload = _poe2_unique_payload()
        payload["lines"][0].update({"name": "Prism of Belief", "baseType": "Diamond"})
        return payload

    service = PoeNinjaPriceService(
        poe2_fetcher=unique_fetcher, poe2_exchange_fetcher=exchange_fetcher,
    )
    identities = (
        ("ITEM", "Primary Calamity Fragment", None, "Fragments"),
        ("ITEM", "Primary Calamity Fragment", None, "Fragments"),
        ("UNIQUE", "Prism of Belief", "Diamond", "UniqueJewels"),
        ("GEM", "Unavailable Reward", None, None),
    )
    prices = service.lookup_poe2_identities(identities, "Runes of Aldur")
    assert [price is not None for price in prices] == [True, True, True, False]
    assert exchange_calls == [("Runes of Aldur", "Fragments")]
    assert unique_calls == [("Runes of Aldur", "UniqueJewels")]


def test_poe2_exchange_matches_regular_currency():
    payload = _poe2_exchange_payload()
    payload["items"] = [{"id": "chaos", "name": "Chaos Orb", "detailsId": "chaos-orb"}]
    payload["lines"] = [{
        "id": "chaos", "primaryValue": 0.1293,
        "maxVolumeCurrency": "divine", "maxVolumeRate": 7.74,
        "sparkline": {"totalChange": 5.19, "data": [1.54, 5.19]},
    }]
    item = ParsedItem("Currency", "currency", "Chaos Orb", "Chaos Orb", "currency")
    price = match_poe2_exchange_price(payload, item, "Runes of Aldur")
    assert price is not None
    assert price.display_price_parts() == ("0.13", "divine")
    assert price.url.endswith("/currency/chaos-orb")


def test_poe2_fragment_exchange_uses_allowlist_and_fragments_overview():
    calls = []

    def fetcher(league, type_name):
        calls.append((league, type_name))
        payload = _poe2_exchange_payload()
        payload["items"] = [{
            "id": "simulacrum", "name": "Simulacrum", "detailsId": "simulacrum",
        }]
        payload["lines"] = [{
            "id": "simulacrum", "primaryValue": 3.33,
            "maxVolumeCurrency": "divine", "maxVolumeRate": 0.3,
            "sparkline": {"totalChange": 1.0, "data": [1.0]},
        }]
        return payload

    service = PoeNinjaPriceService(poe2_exchange_fetcher=fetcher)
    item = ParsedItem("Map Fragments", "normal", "", "Simulacrum", "map_fragment")
    price = service.lookup_poe2_exchange(item, "Runes of Aldur")
    assert price is not None
    assert price.source_type == "Fragments"
    assert price.url.endswith("/fragments/simulacrum")
    assert calls == [("Runes of Aldur", "Fragments")]


@pytest.mark.parametrize(
    "base_type",
    [
        "Primary Calamity Fragment", "Secondary Calamity Fragment",
        "Tertiary Calamity Fragment", "Zarokh's Reliquary Key: Temporalis",
        "An Audience with the King", "Head of the King", "Idol of Estazunti",
        "Breachstone",
    ],
)
def test_poe2_fragment_exchange_excludes_pending_and_trade2_items(base_type):
    service = PoeNinjaPriceService(
        poe2_exchange_fetcher=lambda *_args: pytest.fail("exchange fetch must not run")
    )
    item = ParsedItem("Special", "normal", "", base_type, "map_fragment")
    assert service.lookup_poe2_exchange(item, "Runes of Aldur") is None


def test_poe2_expedition_logbook_uses_expedition_exchange_overview():
    calls = []

    def fetcher(league, type_name):
        calls.append((league, type_name))
        return {
            "core": {"primary": "divine", "rates": {"chaos": 100}},
            "items": [{
                "id": "expedition-logbook", "name": "Expedition Logbook",
                "detailsId": "expedition-logbook",
            }],
            "lines": [{
                "id": "expedition-logbook", "primaryValue": 1.43,
                "maxVolumeCurrency": "divine", "maxVolumeRate": 0.7,
                "sparkline": {"data": [], "totalChange": 0},
            }],
        }

    service = PoeNinjaPriceService(poe2_exchange_fetcher=fetcher)
    item = ParsedItem(
        "Expedition Logbooks", "normal", "", "Expedition Logbook",
        "expedition_logbook",
    )
    price = service.lookup_poe2_exchange(item, "Runes of Aldur")

    assert price is not None
    assert price.source_type == "Expedition"
    assert price.url.endswith("/expedition/expedition-logbook")
    assert calls == [("Runes of Aldur", "Expedition")]


@pytest.mark.parametrize(
    "name",
    [
        "Aldur's Saga", "Medved's Saga", "Olroth's Saga", "Uhtred's Saga",
        "Vorana's Saga",
    ],
)
def test_poe2_expedition_sagas_use_expedition_exchange_overview(name):
    calls = []

    def fetcher(league, type_name):
        calls.append((league, type_name))
        return {
            "core": {"primary": "divine", "rates": {"chaos": 7.74}},
            "items": [{"id": "saga", "name": name, "detailsId": "saga"}],
            "lines": [{
                "id": "saga", "primaryValue": 0.01,
                "maxVolumeCurrency": "exalted", "maxVolumeRate": 0.5,
                "sparkline": {"data": [], "totalChange": 0},
            }],
        }

    service = PoeNinjaPriceService(poe2_exchange_fetcher=fetcher)
    item = ParsedItem("Omens", "currency", name, name, "currency")
    price = service.lookup_poe2_exchange(item, "Runes of Aldur")

    assert price is not None
    assert price.name == name
    assert price.source_type == "Expedition"
    assert price.display_price_parts() == ("2", "exalted")
    assert price.url.endswith("/expedition/saga")
    assert calls == [("Runes of Aldur", "Expedition")]


@pytest.mark.parametrize("item_class", ["Omens", "Omen", "お告げ"])
def test_poe2_regular_omens_use_ritual_exchange_overview(item_class):
    calls = []

    def fetcher(league, type_name):
        calls.append((league, type_name))
        return {
            "core": {"primary": "divine", "rates": {"chaos": 7.74}},
            "items": [{
                "id": "omen-of-sanctification",
                "name": "Omen of Sanctification",
                "detailsId": "omen-of-sanctification",
            }],
            "lines": [{
                "id": "omen-of-sanctification", "primaryValue": 0.77,
                "maxVolumeCurrency": "divine", "maxVolumeRate": 1.3,
                "sparkline": {"data": [], "totalChange": 0},
            }],
        }

    service = PoeNinjaPriceService(poe2_exchange_fetcher=fetcher)
    item = ParsedItem(
        item_class, "currency", "Omen of Sanctification",
        "Omen of Sanctification", "currency",
    )
    price = service.lookup_poe2_exchange(item, "Runes of Aldur")

    assert price is not None
    assert price.name == "Omen of Sanctification"
    assert price.source_type == "Ritual"
    assert price.display_price_parts() == ("0.77", "divine")
    assert price.url.endswith("/omens/omen-of-sanctification")
    assert calls == [("Runes of Aldur", "Ritual")]
