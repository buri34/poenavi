WEAPON_CATEGORIES = frozenset({
    "weapon",
    "bow", "crossbow", "spear", "flail", "staff", "quarterstaff", "wand",
    "sceptre", "one_mace", "two_mace", "one_sword", "two_sword", "one_axe",
    "two_axe", "dagger", "talisman",
})
ARMOUR_CATEGORIES = frozenset({
    "armour",
    "focus", "buckler", "shield", "body_armour", "helmet", "gloves", "boots",
    "quiver",
})
ACCESSORY_CATEGORIES = frozenset({
    "accessory", "ring", "amulet", "belt",
})
GEM_CATEGORIES = frozenset({
    "gem", "active_gem", "support_gem", "meta_gem",
})
EQUIPMENT_CATEGORIES = WEAPON_CATEGORIES | ARMOUR_CATEGORIES | ACCESSORY_CATEGORIES


def is_weapon_category(category: str) -> bool:
    return category in WEAPON_CATEGORIES


def is_armour_category(category: str) -> bool:
    return category in ARMOUR_CATEGORIES


def is_accessory_category(category: str) -> bool:
    return category in ACCESSORY_CATEGORIES


def is_equipment_category(category: str) -> bool:
    return category in EQUIPMENT_CATEGORIES


def is_gem_category(category: str) -> bool:
    return category in GEM_CATEGORIES
