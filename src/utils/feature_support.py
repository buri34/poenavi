"""Central registry for features that support only specific PoE versions."""

from src.utils.poe_version_data import POE1, POE2


MINI_NAVI = "mini_navi"
POETORE = "poetore"

FEATURE_SUPPORTED_VERSIONS = {
    MINI_NAVI: frozenset({POE1, POE2}),
    POETORE: frozenset({POE1, POE2}),
}

FEATURE_HOTKEY_ACTIONS = {
    POETORE: frozenset({"poetore_capture", "poetore_auto_hide"}),
}


def is_feature_supported(feature: str, poe_version: str) -> bool:
    """Return whether *feature* explicitly supports *poe_version*."""
    return poe_version in FEATURE_SUPPORTED_VERSIONS.get(feature, frozenset())


def is_feature_hotkey_supported(action: str, poe_version: str) -> bool:
    """Apply feature support to a hotkey action; common actions remain allowed."""
    for feature, actions in FEATURE_HOTKEY_ACTIONS.items():
        if action in actions:
            return is_feature_supported(feature, poe_version)
    return True


def supported_versions(feature: str) -> frozenset[str]:
    """Expose the immutable supported-version set for UI and diagnostics."""
    return FEATURE_SUPPORTED_VERSIONS.get(feature, frozenset())
