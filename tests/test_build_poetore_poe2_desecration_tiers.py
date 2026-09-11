import importlib.util
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1] / "scripts" / "build_poetore_poe2_desecration_tiers.py"
)
SPEC = importlib.util.spec_from_file_location("build_poetore_poe2_desecration_tiers", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_spawn_weight_uses_first_matching_base_tag():
    row = {"weights": [("boots", 0), ("str_armour", 1), ("default", 0)]}
    profile = {"tags": ["boots", "str_armour", "armour", "default"]}
    assert MODULE.spawn_weight(row, profile) == 0


def test_value_ranges_accepts_pob_rolls_and_trade_local_suffix():
    assert MODULE.value_ranges(
        "# to Accuracy Rating (Local)", "+(47-72) to Accuracy Rating",
    ) == [[47.0, 72.0]]


def test_value_ranges_accepts_fixed_roll():
    assert MODULE.value_ranges(
        "#% increased Movement Speed", "30% increased Movement Speed",
    ) == [[30.0, 30.0]]


def test_generated_database_has_audited_population_and_fixed_sources():
    payload = __import__("json").loads(MODULE.DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    assert len(payload["entries"]) == 1713
    assert payload["source"]["pob2_revision"] == (
        "ce566eac45ea8a86477f513c7ee65a1ebe60014e"
    )
    assert payload["diagnostics"]["selected_rows"] == 1713
    assert payload["diagnostics"]["fully_matchable_rows"] == 1675
    assert len(payload["source"]["pob2_bases_sha256"]) == 64
