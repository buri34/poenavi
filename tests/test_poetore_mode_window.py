from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from src.ui.poetore_mode_window import PoetoreModeWindow


def test_poetore_mode_starts_only_common_and_poetore_services():
    app = QApplication.instance() or QApplication([])
    config = {
        "hotkeys": {
            "exit": "F5",
            "poetore_capture": "alt+d",
            "cheat_sheets_toggle": "shift+space",
            "start_stop": "F7",
        },
        "stash_tab_scroll_enabled": True,
    }

    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value=config,
    ), patch(
        "src.ui.poetore_mode_window.StashTabScrollController"
    ) as stash_class, patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ) as hotkey_class:
        hotkey_service = MagicMock()
        hotkey_service.command.connect = MagicMock()
        hotkey_class.return_value = hotkey_service
        window = PoetoreModeWindow()

    supplied_hotkeys = hotkey_class.call_args.args[0]
    assert supplied_hotkeys == {
        "exit": "F5",
        "poetore_capture": "alt+d",
        "cheat_sheets_toggle": "shift+space",
    }
    assert not hasattr(window, "log_watcher")
    assert not hasattr(window, "mini_navi_overlay")
    assert not hasattr(window, "timer")
    stash_class.return_value.start.assert_called_once()
    hotkey_service.start.assert_called_once()
    window.close()
    app.processEvents()
