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


def test_build_realm_excludes_removed_poe1_scarabs_but_not_poe2_items():
    item_id = "Metadata/Items/Scarabs/Example"
    en, ja = _static("Fragments", "example", "Example Scarab", "スカラベ例")

    poe1 = build_realm(POE1, {item_id: "Example Scarab"}, en, ja, {item_id}, {})
    poe2 = build_realm(POE2, {item_id: "Example Scarab"}, en, ja, {item_id}, {})

    assert poe1["items"] == []
    assert poe1["unmapped_observed"] == []
    assert all(category["id"] != "scarabs" for category in poe1["categories"])
    assert [row["id"] for row in poe2["items"]] == [item_id]


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
        "Metadata/Items/Currency/AstrolabeBestiary": "currency",
        "Metadata/Items/Currency/AstrolabeBetrayal": "currency",
        "Metadata/Items/Currency/AstrolabeIncursion": "currency",
        "Metadata/Items/Threads/ThreadExpedition": "threads",
        "Metadata/Items/Threads/ThreadAbyss": "threads",
        "Metadata/Items/Threads/ThreadBreach": "threads",
        "Metadata/Items/Threads/ThreadRitual": "threads",
        "Metadata/Items/Threads/ThreadUltimatum": "threads",
        "Metadata/Items/Threads/ThreadLegion": "threads",
        "Metadata/Items/Threads/ThreadBlight": "threads",
        "Metadata/Items/Threads/ThreadBestiary": "threads",
        "Metadata/Items/Threads/ThreadBetrayal": "threads",
        "Metadata/Items/Threads/ThreadIncursion": "threads",
        "Metadata/Items/MapFragments/CurrencyAfflictionFragment": "delirium",
        "Metadata/Items/Currency/CurrencyAfflictionShard": "delirium",
        "Metadata/Items/Currency/CurrencyDeepwater": "allflame",
        "Metadata/Items/MapFragments/AtlasAllflamePack": "allflame",
        "Metadata/Items/MapFragments/CloisterAllflamePack": "allflame",
        "Metadata/Items/MapFragments/PantheonAllflamePack": "allflame",
    }
    assert {
        item_id: _category(POE1, "Fragments", item_id, "Example")
        for item_id in expected
    } == expected


def test_confirmed_poe1_330_static_ids_bridge_market_ids_to_localized_rows():
    rows = [
        (
            "Fragments",
            "immortal-astrolabe",
            "Immortal Astrolabe",
            "不死のアストロラーベ",
            "Metadata/Items/Currency/AstrolabeBetrayal",
            "currency",
        ),
        (
            "Currency",
            "soul-core-of-intellect",
            "Soul Core of Intellect",
            "知識のソウルコア",
            "Metadata/Items/Currency/CurrencyWishSupportGemBlue",
            "currency",
        ),
        (
            "Fragments",
            "allflame-ember-of-the-divine",
            "Allflame Ember of the Divine",
            "神性のオールフレイムの残り火",
            "Metadata/Items/MapFragments/PantheonAllflamePack",
            "allflame",
        ),
    ]
    en_groups = {}
    ja_groups = {}
    for group, trade_id, english, japanese, _item_id, _expected_category in rows:
        en_groups.setdefault(group, []).append(
            {"id": trade_id, "text": english, "image": "/gen/example.png"}
        )
        ja_groups.setdefault(group, []).append(
            {"id": trade_id, "text": japanese}
        )
    en = {"result": [
        {"id": group, "entries": entries} for group, entries in en_groups.items()
    ]}
    ja = {"result": [
        {"id": group, "entries": entries} for group, entries in ja_groups.items()
    ]}

    result = build_realm(
        POE1,
        {},
        en,
        ja,
        {row[4] for row in rows},
        {},
    )

    by_id = {row["id"]: row for row in result["items"]}
    assert {
        item_id: (by_id[item_id]["en"], by_id[item_id]["ja"], by_id[item_id]["category"])
        for _group, _trade_id, english, japanese, item_id, category in rows
    } == {
        item_id: (english, japanese, category)
        for _group, _trade_id, english, japanese, item_id, category in rows
    }
    assert result["unmapped_observed"] == []


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
    assert result["items"][0]["icon"] == {
        "kind": "bundled",
        "filename": "MessageInABottle.png",
    }
    assert result["unmapped_observed"] == []


def test_official_static_message_in_a_bottle_icon_replaces_bundled_fallback():
    item_id = "Metadata/Items/Deepwater/DeepwaterBottledItem"
    names = {item_id: "Message in a Bottle"}
    static_row = {
        "id": "Currency",
        "entries": [
            {
                "id": item_id,
                "text": "Message in a Bottle",
                "image": "/gen/image/message-in-a-bottle.png",
            }
        ],
    }
    japanese_row = {
        "id": "Currency",
        "entries": [{"id": item_id, "text": "瓶の中の手紙"}],
    }

    result = build_realm(
        POE1,
        names,
        {"result": [static_row]},
        {"result": [japanese_row]},
        {item_id},
        {},
    )

    assert result["items"][0]["icon"] == {
        "kind": "remote",
        "url": "https://web.poecdn.com/gen/image/message-in-a-bottle.png",
    }


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
