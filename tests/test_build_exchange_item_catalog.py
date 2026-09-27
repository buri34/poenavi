from scripts.build_exchange_item_catalog import _category, build_realm
from src.utils.poe_version_data import POE1, POE2


def _static(group, entry_id, english, japanese, image="/gen/example.png"):
    return (
        {"result": [{"id": group, "entries": [
            {"id": entry_id, "text": english, "image": image},
        ]}]},
        {"result": [{"id": group, "entries": [
            {"id": entry_id, "text": japanese, "image": image},
        ]}]},
    )


def test_build_realm_uses_observed_id_to_resolve_duplicate_english_names():
    en, ja = _static("Fragments", "example", "Example Fragment", "フラグメント例")
    active = "Metadata/Items/MapFragments/CurrencyExample"
    result = build_realm(
        POE1,
        {active: "Example Fragment", "Metadata/Items/QuestItems/Example": "Example Fragment"},
        en,
        ja,
        {active},
        {},
    )
    assert [row["id"] for row in result["items"]] == [active]


def test_build_realm_never_falls_back_to_english_when_japanese_is_missing():
    en, ja = _static("Currency", "example", "Example Orb", "")
    item_id = "Metadata/Items/Currency/ExampleOrb"
    result = build_realm(POE1, {item_id: "Example Orb"}, en, ja, {item_id}, {})
    assert result["items"] == []
    assert result["unmapped_observed"] == [{"id": item_id, "en": "Example Orb"}]


def test_confirmed_path_based_subcategories_are_deterministic():
    assert _category(
        POE1, "Currency", "Metadata/Items/Currency/HarvestSeedRed", "Wild Lifeforce",
    ) == "harvest"
    assert _category(
        POE1, "Fragments", "Metadata/Items/Scarabs/Example", "Example Scarab",
    ) == "scarabs"
    assert _category(
        POE1, "Ancestor", "Metadata/Items/Currency/OmenExample", "Omen of Testing",
    ) == "omens"
    assert _category(
        POE2, "Vaal", "Metadata/Items/SoulCores/Example", "Example Soul Core",
    ) == "soul_cores"
    assert _category(
        POE2, "Ritual", "Metadata/Items/SoulCores/IdolExample", "Example Idol",
    ) == "idols"
