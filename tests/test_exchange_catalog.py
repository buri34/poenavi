import json
import struct
from pathlib import Path

from src.poetore.exchange_catalog import (
    category_labels,
    divination_card_icon_path,
    exchange_catalog_by_id,
    exchange_catalog_items,
)
from src.poetore.official_exchange import CHAOS, DIVINE, EXALTED
from src.utils.poe_version_data import POE1, POE2

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_uses_confirmed_in_game_category_labels_and_order():
    assert category_labels(POE1) == (
        "カレンシー", "エッセンス", "デルブ", "スカラベ", "占いカード",
        "デリリウムオーブ", "リージョン", "フラグメント", "オイル",
        "カタリスト", "お告げ", "タトゥー", "エクスペディション",
        "ハーベスト", "ルーングラフト", "オールフレイム",
    )
    assert category_labels(POE2) == (
        "カレンシー", "エッセンス", "デリリウム", "ブリーチ", "アビス",
        "アッツィリ神殿", "フラグメント", "ルーン", "リチュアル",
        "ソウルコア", "アイドル", "ジェムの原石", "エクスペディション", "ジェム",
    )


def test_catalog_items_have_unique_ids_verified_japanese_and_safe_icons():
    for version in (POE1, POE2):
        items = exchange_catalog_items(version)
        assert len(items) > 600
        assert len({item.item_id for item in items}) == len(items)
        assert all(item.japanese_name.strip() for item in items)
        assert all(item.icon_kind in {"remote", "divination_card", "placeholder"} for item in items)
        assert all(
            item.icon_kind != "remote" or str(item.icon_url).startswith("https://web.poecdn.com/")
            for item in items
        )


def test_golden_currency_ids_resolve_in_both_realms():
    for version in (POE1, POE2):
        catalog = exchange_catalog_by_id(version)
        assert catalog[CHAOS].japanese_name == "カオスオーブ"
        assert catalog[DIVINE].japanese_name == "神のオーブ"
        assert catalog[EXALTED].japanese_name == "高貴なオーブ"


def test_confirmed_exception_categories_are_fixed():
    poe1 = exchange_catalog_by_id(POE1)
    poe2 = exchange_catalog_by_id(POE2)
    assert poe1["Metadata/Items/Deepwater/DeepwaterAbyssCurrency"].category == "allflame"
    assert poe1["Metadata/Items/Currency/LegionCocoonGloves"].category == "legion"
    assert poe1["Metadata/Items/Currency/CurrencyMutatedAddModToRare"].category == "currency"
    assert poe2["Metadata/Items/Currency/CurrencyVerisiumMetal1"].category == "expedition"
    assert poe2["Metadata/Items/Currency/Abyss/AbyssPinnacleKey"].category == "fragments"


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
    payload = json.loads((
        ROOT / "data/poetore/currency_exchange/exchange_item_catalog.json"
    ).read_text(encoding="utf-8"))
    missing = {
        version: {row["en"] for row in payload["realms"][version]["unmapped_observed"]}
        for version in (POE1, POE2)
    }
    assert missing[POE1] == {"Message in a Bottle"}
    assert missing[POE2] == {
        "Raven's Reflection", "The Triskelion Reforged", "Shattered Triskelion",
        "Helbrym's Hide", "Eonyr's Thunder", "Hawk Idol", "Panther Idol", "Stoat Idol",
    }


def test_catalog_sources_are_hash_pinned_official_static_endpoints():
    payload = json.loads((
        ROOT / "data/poetore/currency_exchange/exchange_item_catalog.json"
    ).read_text(encoding="utf-8"))
    for version in (POE1, POE2):
        for language in ("en", "ja"):
            source = payload["sources"][version][language]
            assert source["url"].startswith("https://")
            assert "pathofexile.com/api/trade" in source["url"]
            assert len(source["sha256"]) == 64


def test_distribution_includes_catalog_and_shared_card_icon():
    script = (ROOT / "scripts/build_release.ps1").read_text(encoding="utf-8")
    assert '"--add-data", "data;data"' in script
    assert '"--add-data", "assets;assets"' in script
