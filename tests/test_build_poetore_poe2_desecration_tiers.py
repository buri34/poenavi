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


def test_warstaff_base_is_emitted_as_quarterstaff():
    assert MODULE.concrete_base_category("staff", ("staff",)) == "staff"
    assert MODULE.concrete_base_category("staff", ("warstaff",)) == "quarterstaff"


def test_value_ranges_accepts_pob_rolls_and_trade_local_suffix():
    assert MODULE.value_ranges(
        "# to Accuracy Rating (Local)", "+(47-72) to Accuracy Rating",
    ) == [[47.0, 72.0]]


def test_value_ranges_accepts_fixed_roll():
    assert MODULE.value_ranges(
        "#% increased Movement Speed", "30% increased Movement Speed",
    ) == [[30.0, 30.0]]


def test_directional_part_uses_pob2_polarity_for_text_and_range():
    resolved = MODULE.resolve_directional_part(
        "#% increased Attribute Requirements",
        "要求能力値が#%増加する",
        "25% reduced Attribute Requirements",
    )
    assert resolved == {
        "en": "#% reduced Attribute Requirements",
        "ja": "要求能力値が#%減少する",
        "ranges": [[25.0, 25.0]],
        "direction": "decrease",
    }


def test_directional_part_does_not_guess_when_more_than_direction_differs():
    assert MODULE.resolve_directional_part(
        "#% increased Attribute Requirements",
        "要求能力値が#%増加する",
        "25% reduced Mana Requirements",
    ) is None


def test_generated_database_has_audited_population_and_fixed_sources():
    payload = __import__("json").loads(MODULE.DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    assert len(payload["entries"]) == 1713
    assert payload["source"]["pob2_revision"] == (
        "ce566eac45ea8a86477f513c7ee65a1ebe60014e"
    )
    assert payload["diagnostics"]["selected_rows"] == 1713
    assert payload["diagnostics"]["fully_matchable_rows"] == 1698
    assert len(payload["diagnostics"]["rows_with_unparsed_parts"]) == 15
    assert len(payload["diagnostics"]["polarity_adjusted_rows"]) == 23
    assert payload["diagnostics"]["mixed_fixed_dynamic_parts"] == 61
    assert payload["diagnostics"]["mixed_fixed_dynamic_templates"] == 25
    assert payload["diagnostics"]["numeric_skeleton_collisions"] == []
    assert len(payload["source"]["pob2_bases_sha256"]) == 64

    requirements = next(
        row for row in payload["entries"]
        if row["mod_id"] == "ReducedLocalAttributeRequirements3"
    )
    assert requirements["parts"][0]["text"]["ja"] == "要求能力値が#%減少する"
    assert requirements["parts"][0]["ranges"] == [[25.0, 25.0]]
    assert requirements["parts"][0]["direction"] == "decrease"
