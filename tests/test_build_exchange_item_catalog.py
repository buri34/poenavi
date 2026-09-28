from scripts.build_exchange_item_catalog import _category, build_realm
from src.utils.poe_version_data import POE1, POE2


def _static(group, entry_id, english, japanese, image="/gen/example.png"):
    return (
        {
            "result": [
                {
                    "id": group,
                    "entries": [
                        {"id": entry_id, "text": english, "image": image},
                    ],
                }
            ]
        },
        {
            "result": [
                {
                    "id": group,
                    "entries": [
                        {"id": entry_id, "text": japanese, "image": image},
                    ],
                }
            ]
        },
    )


def test_build_realm_uses_observed_id_to_resolve_duplicate_english_names():
    en, ja = _static("Fragments", "example", "Example Fragment", "フラグメント例")
    active = "Metadata/Items/MapFragments/CurrencyExample"
    result = build_realm(
        POE1,
        {
            active: "Example Fragment",
            "Metadata/Items/QuestItems/Example": "Example Fragment",
        },
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
    assert (
        _category(
            POE1,
            "Currency",
            "Metadata/Items/Currency/HarvestSeedRed",
            "Wild Lifeforce",
        )
        == "harvest"
    )
    assert (
        _category(
            POE1,
            "Fragments",
            "Metadata/Items/Scarabs/Example",
            "Example Scarab",
        )
        == "scarabs"
    )
    assert (
        _category(
            POE1,
            "Ancestor",
            "Metadata/Items/Currency/OmenExample",
            "Omen of Testing",
        )
        == "omens"
    )
    assert (
        _category(
            POE2,
            "Vaal",
            "Metadata/Items/SoulCores/Example",
            "Example Soul Core",
        )
        == "soul_cores"
    )
    assert (
        _category(
            POE2,
            "Ritual",
            "Metadata/Items/SoulCores/IdolExample",
            "Example Idol",
        )
        == "idols"
    )


def test_confirmed_poe2_in_game_category_overrides_are_deterministic():
    assert (
        _category(
            POE2,
            "Fragments",
            "Metadata/Items/Currency/Abyss/AbyssPinnacleKey",
            "Kulemak's Invitation",
        )
        == "abyss"
    )
    assert (
        _category(
            POE2,
            "Fragments",
            "Metadata/Items/Currency/Breach/BreachPinnacleKey",
            "Breachlord Sac",
        )
        == "breach"
    )
    assert (
        _category(
            POE2,
            "Ritual",
            "Metadata/Items/Pinnacle/RitualPinnacleEffigyPiece",
            "Call of the Shadows",
        )
        == "fragments"
    )
    assert (
        _category(
            POE2,
            "Ritual",
            "Metadata/Items/Currency/OmenOnAnnulRemoveAbyssMod",
            "Omen of Light",
        )
        == "abyss"
    )
    assert (
        _category(
            POE2,
            "Expedition",
            "Metadata/Items/SoulCores/CarvedCunning",
            "Carved Cunning",
        )
        == "idols"
    )


def test_confirmed_poe1_in_game_category_overrides_are_deterministic():
    expected = {
        "Metadata/Items/MapFragments/CurrencyFragmentPantheonFlask": "currency",
        "Metadata/Items/MapFragments/VoidbornVaultKey": "currency",
        "Metadata/Items/Currency/FearMemoryThread": "currency",
        "Metadata/Items/Currency/BenevolenceMemoryThread": "currency",
        "Metadata/Items/Currency/IgnoranceMemoryThread": "currency",
        "Metadata/Items/Currency/AstrolabeGeneric": "currency",
        "Metadata/Items/Currency/AstrolabeHarvest": "currency",
        "Metadata/Items/Currency/AstrolabeAbyss": "currency",
        "Metadata/Items/Currency/AstrolabeBreach": "currency",
        "Metadata/Items/Currency/AstrolabeRitual": "currency",
        "Metadata/Items/Currency/AstrolabeBlight": "currency",
        "Metadata/Items/Currency/AstrolabeUltimatum": "currency",
        "Metadata/Items/Currency/AstrolabeDelirium": "currency",
        "Metadata/Items/Currency/AstrolabeLegion": "currency",
        "Metadata/Items/Currency/AstrolabeExpedition": "currency",
        "Metadata/Items/MapFragments/CurrencyAfflictionFragment": "delirium",
        "Metadata/Items/Currency/CurrencyAfflictionShard": "delirium",
        "Metadata/Items/Currency/CurrencyDeepwater": "allflame",
    }
    assert {
        item_id: _category(POE1, "Fragments", item_id, "Example")
        for item_id in expected
    } == expected


def test_confirmed_observed_message_in_a_bottle_is_added_without_static_row():
    item_id = "Metadata/Items/Deepwater/DeepwaterBottledItem"
    result = build_realm(
        POE1,
        {item_id: "Message in a Bottle"},
        {"result": []},
        {"result": []},
        {item_id},
        {},
    )

    assert [
        (row["id"], row["en"], row["ja"], row["category"]) for row in result["items"]
    ] == [(item_id, "Message in a Bottle", "瓶の中の手紙", "allflame")]
    assert result["items"][0]["icon"] == {"kind": "placeholder"}
    assert result["unmapped_observed"] == []


def test_confirmed_observed_triskelions_are_added_without_static_rows():
    item_ids = {
        "Metadata/Items/Currency/Expedition/ExpeditionPinnacleKeyShard",
        "Metadata/Items/Currency/Expedition/ExpeditionPinnacleKey",
    }
    names = {
        "Metadata/Items/Currency/Expedition/ExpeditionPinnacleKeyShard": "Shattered Triskelion",
        "Metadata/Items/Currency/Expedition/ExpeditionPinnacleKey": "The Triskelion Reforged",
    }
    result = build_realm(POE2, names, {"result": []}, {"result": []}, item_ids, {})
    assert [(row["en"], row["ja"], row["category"]) for row in result["items"]] == [
        ("Shattered Triskelion", "砕けたトリスケリオン", "expedition"),
        ("The Triskelion Reforged", "再鍛造されたトリスケリオン", "expedition"),
    ]
    assert [row["icon"] for row in result["items"]] == [
        {"kind": "bundled", "filename": "TriskelionShattered.png"},
        {"kind": "bundled", "filename": "TriskelionReforged.png"},
    ]
    assert result["unmapped_observed"] == []


def test_official_static_triskelion_icon_replaces_bundled_fallback():
    item_id = "Metadata/Items/Currency/Expedition/ExpeditionPinnacleKey"
    names = {item_id: "The Triskelion Reforged"}
    static_row = {
        "id": "Expedition",
        "entries": [
            {
                "id": item_id,
                "text": "The Triskelion Reforged",
                "image": "/gen/image/triskelion.png",
            }
        ],
    }
    japanese_row = {
        "id": "Expedition",
        "entries": [
            {
                "id": item_id,
                "text": "再鍛造されたトリスケリオン",
            }
        ],
    }

    result = build_realm(
        POE2,
        names,
        {"result": [static_row]},
        {"result": [japanese_row]},
        {item_id},
        {},
    )

    assert result["items"][0]["icon"] == {
        "kind": "remote",
        "url": "https://web.poecdn.com/gen/image/triskelion.png",
    }
