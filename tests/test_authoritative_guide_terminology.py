import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import validate_locales


ROOT = Path(__file__).resolve().parents[1]


def _copy_validator_inputs(root: Path) -> None:
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
        shutil.copyfile(ROOT / relative_path, root / relative_path)


def _replace_first_term(root: Path, game: str) -> tuple[str, str]:
    fixture = json.loads(
        (root / "data" / "authoritative_guide_terms.json").read_text(encoding="utf-8")
    )
    term = fixture["games"][game]["guide_terms"][0]
    guide_path = root / ("guide_data_en.json" if game == "poe1" else "guide_data_poe2_en.json")
    text = guide_path.read_text(encoding="utf-8")
    assert term["en"] in text
    guide_path.write_text(text.replace(term["en"], "Incorrect Name", 1), encoding="utf-8")
    return term["en"], guide_path.name


def _append_to_first_string(value, suffix: str) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, str):
                value[key] = f"{child} {suffix}"
                return True
            if _append_to_first_string(child, suffix):
                return True
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, str):
                value[index] = f"{child} {suffix}"
                return True
            if _append_to_first_string(child, suffix):
                return True
    return False


def test_shared_authoritative_fixture_covers_both_games():
    fixture = json.loads(
        (ROOT / "data" / "authoritative_guide_terms.json").read_text(encoding="utf-8")
    )

    assert set(fixture["games"]) == {"poe1", "poe2"}
    assert fixture["games"]["poe1"]["guide_terms"]
    assert fixture["games"]["poe2"]["guide_terms"]


def test_validator_accepts_reviewed_guides():
    assert validate_locales.validate_authoritative_guide_terms(ROOT) == []


def test_validator_reports_wrong_term_for_each_game():
    for game in ("poe1", "poe2"):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _copy_validator_inputs(root)
            expected, guide_name = _replace_first_term(root, game)

            failures = validate_locales.validate_authoritative_guide_terms(root)

        assert any(
            game in failure and guide_name in failure and expected in failure
            for failure in failures
        )


def test_validator_rejects_known_bad_translation_for_each_game():
    for game in ("poe1", "poe2"):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _copy_validator_inputs(root)
            fixture = json.loads(
                (root / "data" / "authoritative_guide_terms.json").read_text(
                    encoding="utf-8"
                )
            )
            forbidden = fixture["games"][game]["forbidden_english"][0]
            guide_path = root / (
                "guide_data_en.json" if game == "poe1" else "guide_data_poe2_en.json"
            )
            guide = json.loads(guide_path.read_text(encoding="utf-8"))
            assert _append_to_first_string(guide, forbidden)
            guide_path.write_text(
                json.dumps(guide, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            failures = validate_locales.validate_authoritative_guide_terms(root)

        assert any(
            game in failure and forbidden in failure
            for failure in failures
        )


def test_validator_rejects_unused_and_duplicate_fixture_entries():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        _copy_validator_inputs(root)
        fixture_path = root / "data" / "authoritative_guide_terms.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        first = dict(fixture["games"]["poe1"]["guide_terms"][0])
        fixture["games"]["poe1"]["guide_terms"].append(first)
        unused = dict(first)
        unused["game_id"] = f"{first['game_id']}-unused"
        unused["ja"] = "存在しない権威用語"
        unused["en"] = "Unused Authoritative Term"
        fixture["games"]["poe1"]["guide_terms"].append(unused)
        fixture_path.write_text(
            json.dumps(fixture, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        failures = validate_locales.validate_authoritative_guide_terms(root)

    assert any("duplicate authoritative identity" in failure for failure in failures)
    assert any("unused" in failure and "poe1" in failure for failure in failures)
