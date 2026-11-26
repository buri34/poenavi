import hashlib
import json
import struct
from pathlib import Path

from src.poetore.exchange_catalog import (
    bundled_exchange_icon_path,
    category_labels,
    divination_card_icon_path,
    exchange_catalog_by_id,
    exchange_catalog_items,
    placeholder_icon_path,
)
from src.poetore.official_exchange import CHAOS, DIVINE, EXALTED
from src.utils.poe_version_data import POE1, POE2

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_uses_confirmed_in_game_category_labels_and_order():
    assert category_labels(POE1) == (
        "カレンシー",
        "エッセンス",
        "デルブ",
        "スレッド",
        "占いカード",
        "デリリウムオーブ",
        "リージョン",
        "フラグメント",
        "オイル",
        "カタリスト",
        "お告げ",
        "タトゥー",
        "エクスペディション",
        "ハーベスト",
        "ルーングラフト",
        "オールフレイム",
    )
    assert category_labels(POE2) == (
        "カレンシー",
        "エッセンス",
        "デリリウム",
        "ブリーチ",
        "アビス",
        "アッツィリ神殿",
        "フラグメント",
        "ルーン",
        "リチュアル",
        "ソウルコア",
        "アイドル",
        "ジェムの原石",
        "エクスペディション",
        "ジェム",
    )


def test_catalog_items_have_unique_ids_verified_japanese_and_safe_icons():
    for version in (POE1, POE2):
        items = exchange_catalog_items(version)
        assert len(items) > 600
        assert len({item.item_id for item in items}) == len(items)
        assert all(item.japanese_name.strip() for item in items)
        assert all(
            item.icon_kind
            in {
                "remote",
                "divination_card",
                "bundled",
                "placeholder",
            }
            for item in items
        )
        assert all(
            item.icon_kind != "remote"
            or str(item.icon_url).startswith("https://web.poecdn.com/")
            for item in items
        )


def test_golden_currency_ids_resolve_in_both_realms():
    for version in (POE1, POE2):
        catalog = exchange_catalog_by_id(version)
        assert catalog[CHAOS].japanese_name == "カオスオーブ"
        assert catalog[DIVINE].japanese_name == "神のオーブ"
        assert catalog[EXALTED].japanese_name == "高貴なオーブ"


def test_poe1_330_exchange_items_are_pinned_and_scarabs_are_absent():
    catalog = exchange_catalog_by_id(POE1)
    expected = {
        "Metadata/Items/MapFragments/CurrencyFaridunBossKey": (
            "The Black Barya",
            "黒きバリャ",
            "fragments",
        ),
        "Metadata/Items/Currency/CurrencyJewelleryQualitySuffix": (
            "Dextral Catalyst",
            "右側のカタリスト",
            "catalysts",
        ),
        "Metadata/Items/Currency/CurrencyEssenceFaridun1": (
            "Essence of Desolation",
            "荒廃のエッセンス",
            "essences",
        ),
        "Metadata/Items/Currency/CurrencyAfflictionRerollClusterEnchant": (
            "Refracting Fog",
            "屈折する霧",
            "currency",
        ),
        "Metadata/Items/Currency/CurrencyJewelleryQualityPrefix": (
            "Sinistral Catalyst",
            "左側のカタリスト",
            "catalysts",
        ),
    }

    assert {
        item_id: (
            catalog[item_id].english_name,
            catalog[item_id].japanese_name,
            catalog[item_id].category,
        )
        for item_id in expected
    } == expected
    assert all(item.category != "scarabs" for item in catalog.values())
    assert all("/Scarabs/" not in item_id for item_id in catalog)


def test_poe1_330_removed_rows_are_absent_and_replacements_are_pinned():
    catalog = exchange_catalog_by_id(POE1)
    removed = {
        "Metadata/Items/Currency/CurrencyStackedScarab",
        "Metadata/Items/Currency/AstrolabeGeneric",
        "Metadata/Items/Currency/AstrolabeHarvest",
        "Metadata/Items/Currency/AstrolabeDelirium",
        *(f"Metadata/Items/MapFragments/CurrencyVaalFragment1_{index}" for index in range(1, 5)),
        *(f"Metadata/Items/MapFragments/CurrencyVaalFragment2_{index}" for index in range(1, 5)),
        "Metadata/Items/MapFragments/CurrencyVaalFragments1Complete",
        "Metadata/Items/MapFragments/CurrencyVaalFragments2Complete",
        "Metadata/Items/DivinationCards/DivinationCardHerMask",
        "Metadata/Items/DivinationCards/DivinationCardLastHope",
        "Metadata/Items/DivinationCards/DivinationCardSambodhisVow",
        "Metadata/Items/DivinationCards/DivinationCardBuriedTreasure",
        "Metadata/Items/DivinationCards/DivinationCardCameriasCut",
        "Metadata/Items/DivinationCards/DivinationCardManWithBear",
        "Metadata/Items/DivinationCards/DivinationCardMoreIsNeverEnough",
        "Metadata/Items/DivinationCards/DivinationCardTheCardSharp",
        "Metadata/Items/DivinationCards/DivinationCardTheDeal",
        "Metadata/Items/DivinationCards/DivinationCardTheRabbitsFoot",
        "Metadata/Items/DivinationCards/DivinationCardTheSillyBoy",
    }
    expected = {
        "Metadata/Items/Currency/CurrencyStackedThread": (
            "Frayed Thread",
            "謎のスレッド",
            "currency",
        ),
        "Metadata/Items/Currency/StackedAstrolabe": (
            "Cryptic Astrolabe",
            "謎のアストロラーベ",
            "currency",
        ),
        "Metadata/Items/Currency/CurrencyMapQualityScarabs": (
            "Maven's Chisel of Threads",
            "メイヴェンのスレッドのチゼル",
            "currency",
        ),
        "Metadata/Items/Currency/CurrencyAfflictionOrbScarabs": (
            "Threaded Delirium Orb",
            "スレッドのデリリウムオーブ",
            "delirium",
        ),
    }

    assert removed.isdisjoint(catalog)
    assert {
        item_id: (
            catalog[item_id].english_name,
            catalog[item_id].japanese_name,
            catalog[item_id].category,
        )
        for item_id in expected
    } == expected


def test_poe1_threads_follow_the_confirmed_in_game_order():
    threads = [
        item for item in exchange_catalog_items(POE1) if item.category == "threads"
    ]
    assert [
        (item.item_id, item.english_name, item.japanese_name)
        for item in threads
    ] == [
        (
            "Metadata/Items/Threads/ThreadExpedition",
            "Expedition Thread",
            "エクスペディションスレッド",
        ),
        (
            "Metadata/Items/Threads/ThreadAbyss",
            "Abyss Thread",
            "アビススレッド",
        ),
        (
            "Metadata/Items/Threads/ThreadBreach",
            "Breach Thread",
            "ブリーチスレッド",
        ),
        (
            "Metadata/Items/Threads/ThreadRitual",
            "Ritual Thread",
            "リチュアルスレッド",
        ),
        (
            "Metadata/Items/Threads/ThreadUltimatum",
            "Ultimatum Thread",
            "アルティメイタムスレッド",
        ),
        (
            "Metadata/Items/Threads/ThreadLegion",
            "Legion Thread",
            "リージョンスレッド",
        ),
        (
            "Metadata/Items/Threads/ThreadBlight",
            "Blight Thread",
            "ブライトスレッド",
        ),
        (
            "Metadata/Items/Threads/ThreadBestiary",
            "Bestiary Thread",
            "ベスティアリースレッド",
        ),
        (
            "Metadata/Items/Threads/ThreadBetrayal",
            "Betrayal Thread",
            "ビトレイアルスレッド",
        ),
        (
            "Metadata/Items/Threads/ThreadIncursion",
            "Incursion Thread",
            "インカージョンスレッド",
        ),
    ]
    assert [item.item_order for item in threads] == sorted(
        item.item_order for item in threads
    )
    assert all(item.icon_kind == "remote" for item in threads)


def test_poe1_late_330_exchange_additions_are_pinned():
    catalog = exchange_catalog_by_id(POE1)
    expected = {
        "Metadata/Items/Currency/AstrolabeBestiary": (
            "Feral Astrolabe", "野生のアストロラーベ", "currency"
        ),
        "Metadata/Items/Currency/AstrolabeBetrayal": (
            "Immortal Astrolabe", "不死のアストロラーベ", "currency"
        ),
        "Metadata/Items/Currency/AstrolabeIncursion": (
            "Royal Astrolabe", "王家のアストロラーベ", "currency"
        ),
        "Metadata/Items/Currency/CurrencyEssenceUber1": (
            "Essence of Trickery", "欺瞞のエッセンス", "essences"
        ),
        "Metadata/Items/Currency/CurrencyWishSupportGem": (
            "Soul Core of Instability", "不安定のソウルコア", "currency"
        ),
        "Metadata/Items/Currency/CurrencyWishSupportGemBlue": (
            "Soul Core of Intellect", "知識のソウルコア", "currency"
        ),
        "Metadata/Items/Currency/CurrencyWishSupportGemGreen": (
            "Soul Core of Finesse", "技のソウルコア", "currency"
        ),
        "Metadata/Items/Currency/CurrencyWishSupportGemRed": (
            "Soul Core of Might", "力のソウルコア", "currency"
        ),
        "Metadata/Items/Currency/LegionCocoonQuiver": (
            "Afarud Enshrouding Crystal",
            "アファルドのエンシュラウドクリスタル",
            "legion",
        ),
        "Metadata/Items/MapFragments/AtlasAllflamePack": (
            "Allflame Ember of the Multitude",
            "群衆のオールフレイムの残り火",
            "allflame",
        ),
        "Metadata/Items/MapFragments/CloisterAllflamePack": (
            "Allflame Ember of the Cloister",
            "学園のオールフレイムの残り火",
            "allflame",
        ),
        "Metadata/Items/MapFragments/CurrencyAuguryBossKey": (
            "Cursed Poppet", "呪いの人形", "fragments"
        ),
        "Metadata/Items/MapFragments/CurrencyIncursionUberFragment": (
            "Royal Visage", "王家の仮面", "fragments"
        ),
        "Metadata/Items/MapFragments/PantheonAllflamePack": (
            "Allflame Ember of the Divine",
            "神性のオールフレイムの残り火",
            "allflame",
        ),
    }

    assert {
        item_id: (
            catalog[item_id].english_name,
            catalog[item_id].japanese_name,
            catalog[item_id].category,
        )
        for item_id in expected
    } == expected
    assert all(catalog[item_id].icon_kind == "remote" for item_id in expected)


def test_poe1_new_exalted_orbs_are_pinned_to_market_ids():
    catalog = exchange_catalog_by_id(POE1)
    expected = {
        "Metadata/Items/Currency/CurrencyStackedExalt": (
            "Primordial Exalted Orb", "原初の高貴なオーブ", "currency",
        ),
        "Metadata/Items/Currency/CurrencyAddModToRareOriginator": (
            "Originator's Exalted Orb",
            "オリジネーターの高貴なオーブ",
            "currency",
        ),
    }

    assert {
        item_id: (
            catalog[item_id].english_name,
            catalog[item_id].japanese_name,
            catalog[item_id].category,
        )
        for item_id in expected
    } == expected
    assert all(catalog[item_id].icon_kind == "remote" for item_id in expected)


def test_confirmed_exception_categories_are_fixed():
    poe1 = exchange_catalog_by_id(POE1)
    poe2 = exchange_catalog_by_id(POE2)
    assert (
        poe1["Metadata/Items/Deepwater/DeepwaterAbyssCurrency"].category == "allflame"
    )
    assert poe1["Metadata/Items/Currency/LegionCocoonGloves"].category == "legion"
    assert (
        poe1["Metadata/Items/Currency/CurrencyMutatedAddModToRare"].category
        == "currency"
    )
    expected_poe1_categories = {
        "Metadata/Items/MapFragments/CurrencyFragmentPantheonFlask": "currency",
        "Metadata/Items/MapFragments/VoidbornVaultKey": "currency",
        "Metadata/Items/Currency/FearMemoryThread": "currency",
        "Metadata/Items/Currency/BenevolenceMemoryThread": "currency",
        "Metadata/Items/Currency/IgnoranceMemoryThread": "currency",
        "Metadata/Items/Currency/StackedAstrolabe": "currency",
        "Metadata/Items/Currency/AstrolabeAbyss": "currency",
        "Metadata/Items/Currency/AstrolabeBreach": "currency",
        "Metadata/Items/Currency/AstrolabeRitual": "currency",
        "Metadata/Items/Currency/AstrolabeBlight": "currency",
        "Metadata/Items/Currency/AstrolabeUltimatum": "currency",
        "Metadata/Items/Currency/AstrolabeLegion": "currency",
        "Metadata/Items/Currency/AstrolabeExpedition": "currency",
        "Metadata/Items/MapFragments/CurrencyAfflictionFragment": "delirium",
        "Metadata/Items/Currency/CurrencyAfflictionShard": "delirium",
        "Metadata/Items/Currency/CurrencyDeepwater": "allflame",
        "Metadata/Items/Deepwater/DeepwaterBottledItem": "allflame",
    }
    assert {
        item_id: poe1[item_id].category for item_id in expected_poe1_categories
    } == expected_poe1_categories
    assert (
        poe1["Metadata/Items/Deepwater/DeepwaterBottledItem"].japanese_name
        == "瓶の中の手紙"
    )
    bottled = poe1["Metadata/Items/Deepwater/DeepwaterBottledItem"]
    assert (bottled.icon_kind, bottled.icon_filename) == (
        "bundled",
        "MessageInABottle.png",
    )
    icon = bundled_exchange_icon_path(bottled.icon_filename)
    assert icon is not None
    content = icon.read_bytes()
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", content[16:24]) == (553, 547)
    assert hashlib.sha256(content).hexdigest() == (
        "bb501629aa70996180d4d058fa5510c49d18b83f7e9237724b5f4be5aecf0864"
    )
    assert (
        poe2["Metadata/Items/Currency/CurrencyVerisiumMetal1"].category == "expedition"
    )
    expected_poe2_categories = {
        "Metadata/Items/Currency/Abyss/AbyssPinnacleKey": "abyss",
        "Metadata/Items/Currency/Breach/BreachPinnacleKey": "breach",
        "Metadata/Items/Pinnacle/RitualPinnacleEffigyPiece": "fragments",
        "Metadata/Items/Currency/OmenOnAbyssRerollOptions": "abyss",
        "Metadata/Items/Currency/OmenOnAbyssGuarenteeLichTypeMod1": "abyss",
        "Metadata/Items/Currency/OmenOnAbyssGuarenteeLichTypeMod2": "abyss",
        "Metadata/Items/Currency/OmenOnAbyssGuarenteeLichTypeMod3": "abyss",
        "Metadata/Items/Currency/OmenOnAbyssVeilAllAndCorrupt": "abyss",
        "Metadata/Items/Currency/OmenOnAnnulRemoveAbyssMod": "abyss",
        "Metadata/Items/Currency/OmenOnAbyssAddPrefixes": "abyss",
        "Metadata/Items/Currency/OmenOnAbyssAddSuffixes": "abyss",
        "Metadata/Items/SoulCores/CarvedCunning": "idols",
        "Metadata/Items/SoulCores/CarvedMajesty": "idols",
        "Metadata/Items/SoulCores/CarvedMischief": "idols",
        "Metadata/Items/SoulCores/CarvedTenacity": "idols",
    }
    assert {
        item_id: poe2[item_id].category for item_id in expected_poe2_categories
    } == expected_poe2_categories


def test_confirmed_triskelions_are_available_in_poe2_expedition():
    poe2 = exchange_catalog_by_id(POE2)
    expected = {
        "Metadata/Items/Currency/Expedition/ExpeditionPinnacleKeyShard": "砕けたトリスケリオン",
        "Metadata/Items/Currency/Expedition/ExpeditionPinnacleKey": "再鍛造されたトリスケリオン",
    }
    assert {item_id: poe2[item_id].japanese_name for item_id in expected} == expected
    assert {poe2[item_id].category for item_id in expected} == {"expedition"}
    expected_icons = {
        "Metadata/Items/Currency/Expedition/ExpeditionPinnacleKeyShard": "TriskelionShattered.png",
        "Metadata/Items/Currency/Expedition/ExpeditionPinnacleKey": "TriskelionReforged.png",
    }
    assert {
        item_id: (poe2[item_id].icon_kind, poe2[item_id].icon_filename)
        for item_id in expected
    } == {
        item_id: ("bundled", filename) for item_id, filename in expected_icons.items()
    }
    for filename in expected_icons.values():
        icon = bundled_exchange_icon_path(filename)
        assert icon is not None
        content = icon.read_bytes()
        assert content.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack(">II", content[16:24]) == (518, 524)


def test_poe1_divination_cards_use_one_bundled_icon():
    cards = [item for item in exchange_catalog_items(POE1) if item.category == "cards"]
    assert len(cards) > 400
    assert {item.icon_kind for item in cards} == {"divination_card"}
    icon = divination_card_icon_path()
    assert icon.is_file()
    content = icon.read_bytes()
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", content[16:24]) == (16, 16)


def test_current_unmapped_observed_items_are_explicit_and_not_catalog_items():
    payload = json.loads(
        (ROOT / "data/poetore/currency_exchange/exchange_item_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    missing = {
        version: {row["en"] for row in payload["realms"][version]["unmapped_observed"]}
        for version in (POE1, POE2)
    }
    assert missing[POE1] == set()
    assert missing[POE2] == {
        "Raven's Reflection",
        "Helbrym's Hide",
        "Eonyr's Thunder",
        "Hawk Idol",
        "Panther Idol",
        "Stoat Idol",
    }


def test_catalog_sources_are_hash_pinned_official_static_endpoints():
    payload = json.loads(
        (ROOT / "data/poetore/currency_exchange/exchange_item_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    for version in (POE1, POE2):
        for language in ("en", "ja"):
            source = payload["sources"][version][language]
            assert source["url"].startswith("https://")
            assert "pathofexile.com/api/trade" in source["url"]
            assert len(source["sha256"]) == 64


def test_distribution_includes_catalog_and_bundled_icons():
    script = (ROOT / "scripts/build_release.ps1").read_text(encoding="utf-8")
    assert '"--add-data", "data;data"' in script
    assert '"--add-data", "assets;assets"' in script
    placeholder = placeholder_icon_path()
    assert placeholder.is_file()
    assert "<svg" in placeholder.read_text(encoding="utf-8")
    for filename in (
        "TriskelionShattered.png",
        "TriskelionReforged.png",
        "MessageInABottle.png",
    ):
        assert filename in script
