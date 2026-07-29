from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication, QLabel

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
        with patch.object(PoetoreModeWindow, "refresh_currency_rate"):
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
    assert "currency_rate_refresh" in window.active_service_names
    assert window.memo_button.text() == "📝"
    assert window.cheat_sheets_button.text() == "🖼"
    assert window.settings_button.text() == "⚙"
    assert window.memo_button.size().width() == 35
    assert window.memo_button.size().height() == 35
    assert window.divine_rate_value.text() == "取得中…"
    stash_class.return_value.start.assert_called_once()
    hotkey_service.start.assert_called_once()
    window.close()
    app.processEvents()


def test_poetore_mode_renders_divine_chaos_rate():
    app = QApplication.instance() or QApplication([])
    config = {"hotkeys": {}, "stash_tab_scroll_enabled": False}

    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value=config,
    ), patch(
        "src.ui.poetore_mode_window.StashTabScrollController"
    ), patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ), patch.object(PoetoreModeWindow, "refresh_currency_rate"):
        window = PoetoreModeWindow()

    window._show_rate("Mirage", 200)
    assert window.divine_rate_value.text() == "1 = 200.0 Chaos"
    assert not hasattr(window, "chaos_rate_value")
    divine_icon = window.findChild(QLabel, "divineCurrencyIcon")
    chaos_icon = window.findChild(QLabel, "chaosCurrencyIcon")
    assert divine_icon is not None and not divine_icon.pixmap().isNull()
    assert chaos_icon is not None and not chaos_icon.pixmap().isNull()
    rate_layout = window.divine_rate_value.parentWidget().layout()
    assert rate_layout.itemAt(1).widget() is window.divine_rate_value
    assert rate_layout.stretch(1) == 0
    assert rate_layout.itemAt(2).widget() is chaos_icon
    assert rate_layout.itemAt(3).spacerItem() is not None
    assert window.rate_status.text() == "Mirage ・ poe.ninja ・ 31分ごとに自動更新"
    assert "#DB86EF" in window.centralWidget().styleSheet()
    window.close()
    app.processEvents()
