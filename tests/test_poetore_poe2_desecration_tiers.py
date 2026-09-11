import hashlib
import json
from pathlib import Path

import pytest

from poetore.poe2.desecration_tiers import resolve_desecration_choice, tier_data

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "poetore" / "poe2" / "desecration"
FIXTURE = json.loads((FIXTURE_DIR / "reveal_cases.json").read_text(encoding="utf-8"))
CHOICES = [
    (choice["text"], case["category"], choice["tier"], choice["mod_id"])
    for case in FIXTURE["cases"]
    for choice in case["choices"]
]


@pytest.mark.parametrize(
    ("text", "category", "tier", "mod_id"),
    CHOICES,
)
def test_user_supplied_reveal_choices_resolve_to_tier(text, category, tier, mod_id):
    result = resolve_desecration_choice(text, category)
    assert result.reason == "matched"
    assert result.tier == tier
    assert result.mod_ids == (mod_id,)


def test_user_supplied_images_are_preserved_exactly():
    for case in FIXTURE["cases"]:
        image = FIXTURE_DIR / case["image"]
        assert hashlib.sha256(image.read_bytes()).hexdigest() == case["image_sha256"]


def test_category_is_required_to_prevent_cross_equipment_guessing():
    result = resolve_desecration_choice("アーマー +27", "spear")
    assert result.tier is None
    assert result.reason == "no_match"


def test_database_keeps_unparsed_template_rows_explicitly_diagnostic():
    payload = tier_data()
    assert len(payload["entries"]) == 1713
    assert payload["diagnostics"]["fully_matchable_rows"] == 1675
    assert len(payload["diagnostics"]["rows_with_unparsed_parts"]) == 38
