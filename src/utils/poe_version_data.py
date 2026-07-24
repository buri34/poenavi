"""PoEバージョン別の進行定義・表示定義"""

POE1 = "poe1"
POE2 = "poe2"

POE1_TOWN_ZONES = [
    "Lioneye's Watch", "ライオンアイの見張り場",
    "The Forest Encampment", "森の野営地",
    "The Sarn Encampment", "サーンの野営地",
    "Highgate", "ハイゲート",
    "Overseer's Tower", "監督官の塔",
    "The Bridge Encampment", "橋の野営地",
    "Oriath Docks", "オリアスの船着場",
    "Karui Shores", "カルイの海岸",
]

POE2_TOWN_ZONES = [
    "クリアフェルの野営地",
    "Clearfell Encampment",
    "アードゥラのキャラバン", "The Ardura Caravan",
    "ジッグラトの野営地", "Ziggurat Encampment",
    "キングスマーチ", "Kingsmarch",
    "避難所", "The Refuge",
    "カーリバザール", "The Khari Bazaar",
    "森の広場", "The Glade",
]

POE_VERSION_LABELS = {
    POE1: "PoE1",
    POE2: "PoE2",
}

POE_VERSION_ORDER = [POE1, POE2]

POE_VERSION_DEFINITIONS = {
    POE1: {
        "label": "PoE1",
        "acts": [
            "Act 1", "Act 2", "Act 3", "Act 4", "Act 5",
            "Act 6", "Act 7", "Act 8", "Act 9", "Act 10",
        ],
        "lap_labels": [
            "Act 1", "Act 2", "Act 3", "Act 4", "Act 5",
            "Act 6", "Act 7", "Act 8", "Act 9", "Act 10",
        ],
        "guide_file": "guide_data.json",
        "timer_file": "timer_poe1.json",
        "progress_flags_file": "progress_flags_poe1.json",
        "town_zones": POE1_TOWN_ZONES,
    },
    POE2: {
        "label": "PoE2",
        "acts": [
            "Act 1", "Act 2", "Act 3", "Act 4",
            "幕間 1", "幕間 2", "幕間 3", "クリア",
        ],
        "lap_labels": [
            "Act 1", "Act 2", "Act 3", "Act 4",
            "幕間 1", "幕間 2", "幕間 3", "クリア",
        ],
        "guide_file": "guide_data_poe2.json",
        "timer_file": "timer_poe2.json",
        "progress_flags_file": "progress_flags_poe2.json",
        "town_zones": POE2_TOWN_ZONES,
    },
}


def get_poe_definition(poe_version: str) -> dict:
    return POE_VERSION_DEFINITIONS.get(poe_version, POE_VERSION_DEFINITIONS[POE1])


def get_act_list(poe_version: str) -> list[str]:
    return list(get_poe_definition(poe_version)["acts"])


def get_lap_labels(poe_version: str) -> list[str]:
    return list(get_poe_definition(poe_version)["lap_labels"])


def get_guide_filename(poe_version: str, language: str = "ja") -> str:
    filename = get_poe_definition(poe_version)["guide_file"]
    if str(language).lower().replace("_", "-").startswith("en"):
        stem, suffix = filename.rsplit(".", 1)
        return f"{stem}_en.{suffix}"
    return filename


def get_timer_filename(poe_version: str) -> str:
    return get_poe_definition(poe_version)["timer_file"]


def get_progress_flags_filename(poe_version: str) -> str | None:
    return get_poe_definition(poe_version).get("progress_flags_file")


def get_poe_label(poe_version: str) -> str:
    return get_poe_definition(poe_version)["label"]


def get_town_zones(poe_version: str) -> list[str]:
    return list(get_poe_definition(poe_version).get("town_zones", []))
