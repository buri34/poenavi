import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import validate_locales
from src.utils.zone_data_poe2 import DEFAULT_ZONE_DATA_POE2


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_ZONES = {
    "poe2_act2_area09": ("ケス", "Keth"),
    "poe2_act2_area18": ("ドレッドノート", "Dreadnought"),
    "poe2_act2_area19": ("ドレッドノートの航跡", "The Dreadnought's Wake"),
}

EXPECTED_GUIDE_TERMS = {
    "霧の刃、シオラ": "Siora, Blade of the Mists",
    "蝕まれたタヴァカイ": "Tavakai, the Consumed",
    "族長、タヴァカイ": "Tavakai, the Chieftain",
    "フードをかぶった者": "The Hooded One",
    "カーリバザール": "The Khari Bazaar",
    "アボミネーションのイエティ": "The Abominable Yeti",
    "サンドワーム、アナンドル": "Anundr, the Sandworm",
    "セケマのアサラ": "Sekhema Asala",
    "鍛造場主、メクトゥル": "Mektul, the Forgemaster",
    "古代の戦象、エクバブ": "Ekbab, Ancient Steed",
    "死の王、イクタブ": "Iktab, the Deathlord",
    "太陽の部族の遺物": "Sun Clan Relic",
    "砂漠の地図": "Desert Map",
}


def _zones_by_id(acts):
    return {
        zone["id"]: zone
        for zones in acts.values()
        for zone in zones
    }


def _guide_leaves(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if key in validate_locales.TRANSLATABLE_GUIDE_FIELDS and isinstance(child, str):
                yield child_path, child
            else:
                yield from _guide_leaves(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _guide_leaves(child, f"{path}/{index}")


def test_confirmed_poe2_zone_names_match_current_game_data():
    master = json.loads((ROOT / "data" / "zone_data.json").read_text(encoding="utf-8"))
    runtime_zones = _zones_by_id(master["zone_data_by_version"]["poe2"])
    fallback_zones = _zones_by_id(DEFAULT_ZONE_DATA_POE2)

    for zone_id, (japanese, english) in EXPECTED_ZONES.items():
        assert (runtime_zones[zone_id]["zone"], runtime_zones[zone_id]["zone_en"]) == (
            japanese,
            english,
        )
        assert (fallback_zones[zone_id]["zone"], fallback_zones[zone_id]["zone_en"]) == (
            japanese,
            english,
        )


def test_confirmed_poe2_guide_terms_use_official_english_names():
    japanese = json.loads((ROOT / "guide_data_poe2.json").read_text(encoding="utf-8"))
    english = json.loads((ROOT / "guide_data_poe2_en.json").read_text(encoding="utf-8"))
    english_leaves = dict(_guide_leaves(english))

    matched = set()
    for path, japanese_leaf in _guide_leaves(japanese):
        for japanese_term, english_term in EXPECTED_GUIDE_TERMS.items():
            if japanese_term in japanese_leaf:
                matched.add(japanese_term)
                assert english_term in english_leaves[path], (
                    f"{path} must use {english_term!r} for {japanese_term!r}"
                )

    assert matched == set(EXPECTED_GUIDE_TERMS)


def test_short_risu_name_is_corrected_at_its_known_guide_path():
    english = json.loads((ROOT / "guide_data_poe2_en.json").read_text(encoding="utf-8"))
    step = english["poe2_interlude2_area01"]["default"]

    assert "Risu" in step["objective"]
    assert "Risu" in step["summary"]
    assert "the rat" not in step["objective"].lower()
    assert "the rat" not in step["summary"].lower()


def test_release_validator_includes_shared_authoritative_check():
    validator = getattr(validate_locales, "validate_authoritative_guide_terms", None)

    assert validator is not None
    failures = validator(ROOT)
    assert failures == []


def test_release_validator_rejects_stale_runtime_zone_name():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "data").mkdir()
        (root / "src" / "utils").mkdir(parents=True)
        for relative_path in (
            "data/authoritative_guide_terms.json",
            "data/zone_data.json",
            "src/utils/zone_data_poe2.py",
            "guide_data.json",
            "guide_data_en.json",
            "guide_data_poe2.json",
            "guide_data_poe2_en.json",
        ):
            source = ROOT / relative_path
            destination = root / relative_path
            shutil.copyfile(source, destination)

        zone_path = root / "data" / "zone_data.json"
        zone_master = json.loads(zone_path.read_text(encoding="utf-8"))
        zones = _zones_by_id(zone_master["zone_data_by_version"]["poe2"])
        zones["poe2_act2_area09"]["zone_en"] = "Heart of Keth"
        zone_path.write_text(
            json.dumps(zone_master, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )

        failures = validate_locales.validate_authoritative_guide_terms(root)

    assert any(
        "authoritative PoE2 zone mismatch in data/zone_data.json" in failure
        and "poe2_act2_area09" in failure
        for failure in failures
    )
