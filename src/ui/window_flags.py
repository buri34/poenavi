from PySide6.QtCore import Qt

from src.utils.config_manager import ConfigManager


def _is_always_on_top_enabled(parent=None):
    """設定に応じて最前面表示を有効にするか返す。"""
    if parent is not None and hasattr(parent, "config"):
        return parent.config.get("always_on_top", True)
    return ConfigManager.load_config().get("always_on_top", True)


def _with_optional_always_on_top(flags, parent=None):
    if _is_always_on_top_enabled(parent):
        return flags | Qt.WindowStaysOnTopHint
    return flags & ~Qt.WindowStaysOnTopHint


def _is_mini_always_on_top_enabled(parent=None):
    """みになび専用の最前面表示設定。未設定時はON。"""
    if parent is not None and hasattr(parent, "config"):
        config = parent.config
    else:
        config = ConfigManager.load_config()
    mini_config = config.get("mini_guide_overlay", {}) if isinstance(config, dict) else {}
    if isinstance(mini_config, dict):
        return mini_config.get("always_on_top", True)
    return True


def _with_optional_mini_always_on_top(flags, parent=None):
    if _is_mini_always_on_top_enabled(parent):
        return flags | Qt.WindowStaysOnTopHint
    return flags & ~Qt.WindowStaysOnTopHint
