from src.poetore.categories import (
    is_armour_category,
    is_equipment_category,
    is_gem_category,
    is_weapon_category,
)


def test_poe1_and_poe2_categories_share_common_groups():
    assert all(is_weapon_category(category) for category in ("weapon", "spear", "crossbow"))
    assert all(is_armour_category(category) for category in ("armour", "body_armour", "focus"))
    assert all(is_equipment_category(category) for category in ("accessory", "ring", "belt"))
    assert all(is_gem_category(category) for category in ("gem", "active_gem", "support_gem", "meta_gem"))
