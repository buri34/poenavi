from src.utils.feature_support import (
    MINI_NAVI,
    POETORE,
    is_feature_hotkey_supported,
    is_feature_supported,
    supported_versions,
)
from src.utils.poe_version_data import POE1, POE2


def test_poe1_only_features_are_declared_in_one_registry():
    assert supported_versions(MINI_NAVI) == {POE1}
    assert supported_versions(POETORE) == {POE1}
    assert is_feature_supported(MINI_NAVI, POE1)
    assert not is_feature_supported(MINI_NAVI, POE2)
    assert is_feature_supported(POETORE, POE1)
    assert not is_feature_supported(POETORE, POE2)


def test_poetore_hotkeys_follow_feature_support():
    for action in ("poetore_capture", "poetore_auto_hide"):
        assert is_feature_hotkey_supported(action, POE1)
        assert not is_feature_hotkey_supported(action, POE2)
    assert is_feature_hotkey_supported("start_stop", POE2)


def test_unknown_features_fail_closed():
    assert not is_feature_supported("unknown", POE1)
    assert supported_versions("unknown") == frozenset()
