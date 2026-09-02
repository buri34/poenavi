from unittest.mock import MagicMock, call, patch
import pytest

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QSystemTrayIcon

from src.ui.poetore_mode_window import PoetoreModeWindow, _currency_icon_filename
from src.utils.poe_version_data import POE2


def test_poetore_mode_starts_only_common_and_poetore_services():
    app = QApplication.instance() or QApplication([])
    config = {
        "hotkeys": {
            "exit": "F5",
            "monastery": "F12",
            "poetore_capture": "alt+d",
            "poetore_auto_hide": "ctrl+d",
            "map_check": "alt+f",
            "cheat_sheets_toggle": "shift+space",
            "start_stop": "F7",
        },
    }

    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value=config,
    ), patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ) as hotkey_class, patch(
        "src.ui.poetore_mode_window.StashTabScrollController"
    ) as stash_class, patch(
        "src.ui.poetore_mode_window.ForegroundSuppressedHotkeyService"
    ) as suppressed_class, patch(
        "src.ui.poetore_mode_window.suppressed_hotkeys_supported",
        return_value=True,
    ):
        hotkey_service = MagicMock()
        hotkey_service.command.connect = MagicMock()
        hotkey_class.return_value = hotkey_service
        with patch.object(PoetoreModeWindow, "refresh_currency_rate"):
            window = PoetoreModeWindow()

    supplied_hotkeys = hotkey_class.call_args.args[0]
    assert hotkey_class.call_args.kwargs["action_filter"] is not None
    assert supplied_hotkeys == {
        "exit": "F5",
        "monastery": "F12",
        "poetore_auto_hide": "ctrl+d",
        "map_check": "alt+f",
        "cheat_sheets_toggle": "shift+space",
    }
    suppressed_class.assert_called_once()
    args = suppressed_class.call_args.args
    kwargs = suppressed_class.call_args.kwargs
    assert args == ("poetore_capture", "alt+d")
    assert kwargs["parent"] is window
    assert callable(kwargs["result_window_checker"])
    assert callable(kwargs["poe_target_getter"])
    suppressed_class.return_value.start.assert_called_once_with()
    stash_class.assert_called_once_with(enabled=True)
    stash_class.return_value.start.assert_called_once_with()
    assert not hasattr(window, "log_watcher")
    assert not hasattr(window, "mini_navi_overlay")
    assert not hasattr(window, "timer")
    assert "currency_rate_refresh" in window.active_service_names
    assert "stash_tab_scroll" in window.active_service_names
    header_buttons = (
        window.memo_button,
        window.map_mods_button,
        window.cheat_sheets_button,
        window.settings_button,
    )
    assert all(button.text() == "" for button in header_buttons)
    assert all(not button.icon().isNull() for button in header_buttons)
    assert all(button.iconSize() == QSize(24, 24) for button in header_buttons)
    assert all(button.focusPolicy() == Qt.NoFocus for button in header_buttons)
    icon_images = [
        button.icon().pixmap(QSize(24, 24)).toImage() for button in header_buttons
    ]
    assert all(image != icon_images[0] for image in icon_images[1:])
    assert window.memo_button.size().width() == 35
    assert window.memo_button.size().height() == 35
    assert window.divine_rate_value.text() == "取得中…"
    assert window.width() == 558
    assert window.windowFlags() & Qt.FramelessWindowHint
    assert window.capture_hint.text() == (
        "アイテムにマウスオーバーして Alt + D 操作モード / "
        "Ctrl + D AUTO-HIDE"
    )
    minimize_button = window.findChild(QPushButton, "poetoreMinimizeButton")
    close_button = window.findChild(QPushButton, "poetoreCloseButton")
    assert minimize_button.text() == "─"
    assert close_button.text() == "✕"
    assert minimize_button.focusPolicy() == Qt.NoFocus
    assert close_button.focusPolicy() == Qt.NoFocus
    assert window.rate_refresh_button.text() == "更新"
    assert window.rate_refresh_button.focusPolicy() == Qt.NoFocus
    assert window.tray_icon.toolTip() == "ぽえとれ"
    assert [
        action.text() for action in window.tray_icon.contextMenu().actions()
        if not action.isSeparator()
    ] == ["ぽえとれを表示", "設定", "終了"]
    hotkey_service.start.assert_called_once()
    window.close()
    app.processEvents()
    stash_class.return_value.stop.assert_called_once_with()


def test_poetore_mode_starts_capture_and_stash_scroll_services_for_poe2():
    app = QApplication.instance() or QApplication([])
    config = {
        "poe_version": POE2,
        "hotkeys": {
            "poetore_capture": "alt+d",
            "poetore_auto_hide": "ctrl+d",
            "map_check": "alt+f",
        },
    }

    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value=config,
    ), patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ) as hotkey_class, patch(
        "src.ui.poetore_mode_window.StashTabScrollController"
    ) as stash_class, patch.object(
        PoetoreModeWindow, "refresh_currency_rate"
    ), patch(
        "src.poetore.ui.prepare_poetore_window"
    ) as prepare_window, patch(
        "src.ui.poetore_mode_window.is_feature_supported", return_value=True,
    ), patch(
        "src.ui.poetore_mode_window.is_feature_hotkey_supported", return_value=True,
    ), patch(
        "src.ui.poetore_mode_window.suppressed_hotkeys_supported", return_value=False,
    ):
        window = PoetoreModeWindow()

    supplied_hotkeys = hotkey_class.call_args.args[0]
    assert "poetore_capture" in supplied_hotkeys
    assert "poetore_auto_hide" in supplied_hotkeys
    assert supplied_hotkeys["map_check"] == "alt+f"
    stash_class.assert_called_once_with(enabled=True)
    prepare_window.assert_called_once_with(window)
    for object_name, filename, size in (
        ("divineCurrencyIcon", "DivineOrb2.png", 52),
        ("exaltedCurrencyIcon", "ExaltedOrb2.png", 46),
    ):
        label = window.findChild(QLabel, object_name)
        expected = QPixmap(str(window._asset_path(filename))).scaled(
            QSize(size, size), Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        assert label.pixmap().toImage() == expected.toImage()
    window.close()
    app.processEvents()


def test_poetore_mode_uses_version_specific_currency_icon_names():
    assert _currency_icon_filename("divine", "poe2") == "DivineOrb2.png"
    assert _currency_icon_filename("chaos", "poe2") == "ChaosOrb2.png"
    assert _currency_icon_filename("exalted", "poe2") == "ExaltedOrb2.png"
    assert _currency_icon_filename("chaos", "poe1") == "ChaosOrb.png"


def test_poetore_mode_respects_disabled_stash_scroll_for_poe2():
    app = QApplication.instance() or QApplication([])
    config = {
        "poe_version": POE2,
        "stash_tab_scroll_enabled": False,
        "hotkeys": {},
    }

    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value=config,
    ), patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ), patch(
        "src.ui.poetore_mode_window.StashTabScrollController"
    ) as stash_class, patch.object(
        PoetoreModeWindow, "refresh_currency_rate"
    ), patch(
        "src.ui.poetore_mode_window.is_feature_supported", return_value=True,
    ):
        window = PoetoreModeWindow()

    stash_class.assert_called_once_with(enabled=False)
    window.close()
    app.processEvents()


def test_poetore_mode_starts_obs_window_collapsed_when_enabled():
    app = QApplication.instance() or QApplication([])
    config = {
        "poe_version": "poe1",
        "hotkeys": {},
        "poetore": {"obs_streaming": {"enabled": True, "geometry": {}}},
    }
    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value=config,
    ), patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ), patch.object(PoetoreModeWindow, "refresh_currency_rate"):
        window = PoetoreModeWindow()
        app.processEvents()

    result = window._poetore_window
    assert result.isVisible()
    assert result._obs_collapsed
    assert result.windowTitle() == "ぽえとれ - 検索結果ウィンドウ"
    window.close()
    app.processEvents()


def test_poetore_mode_minimize_hides_to_tray_and_notifies_once():
    app = QApplication.instance() or QApplication([])
    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value={"hotkeys": {}},
    ), patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ), patch.object(
        PoetoreModeWindow, "refresh_currency_rate"
    ), patch.object(
        QSystemTrayIcon, "isSystemTrayAvailable", return_value=True
    ):
        window = PoetoreModeWindow()
        window.show()
        app.processEvents()
        with patch.object(window.tray_icon, "show") as show_tray, patch.object(
            window.tray_icon, "showMessage"
        ) as show_message:
            window.title_bar.minimize_button.click()
            window.minimize_to_tray()

    assert not window.isVisible()
    assert show_tray.call_count == 2
    show_message.assert_called_once()
    window.close()
    app.processEvents()


def test_poetore_mode_minimize_falls_back_when_tray_is_unavailable():
    window = MagicMock()
    with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=False):
        PoetoreModeWindow.minimize_to_tray(window)

    window.showMinimized.assert_called_once_with()
    window.hide.assert_not_called()


def test_poetore_mode_tray_settings_restores_before_opening_dialog():
    window = MagicMock()
    with patch.object(QTimer, "singleShot", side_effect=lambda _delay, callback: callback()):
        PoetoreModeWindow.open_settings_from_tray(window)

    assert window.method_calls[:2] == [
        call.restore_from_tray(),
        call.open_settings(),
    ]


def test_poetore_mode_tray_activation_restores_on_click_and_double_click():
    window = MagicMock()

    PoetoreModeWindow._handle_tray_activation(window, QSystemTrayIcon.Trigger)
    PoetoreModeWindow._handle_tray_activation(window, QSystemTrayIcon.DoubleClick)
    PoetoreModeWindow._handle_tray_activation(window, QSystemTrayIcon.Context)

    assert window.restore_from_tray.call_count == 2


def test_poetore_mode_tray_exit_closes_window_and_quits_application():
    window = MagicMock()
    app = MagicMock()
    with patch.object(QApplication, "instance", return_value=app):
        PoetoreModeWindow.quit_from_tray(window)

    window.close.assert_called_once_with()
    app.quit.assert_called_once_with()


def test_poetore_mode_monastery_hotkey_sends_chat_command():
    app = QApplication.instance() or QApplication([])
    config = {"hotkeys": {"monastery": "F12"}}

    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value=config,
    ), patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ), patch.object(PoetoreModeWindow, "refresh_currency_rate"), patch(
        "src.ui.poetore_mode_window.send_chat_command"
    ) as send_command:
        window = PoetoreModeWindow()
        window.handle_hotkey("monastery")

    send_command.assert_called_once_with("/monastery")
    window.close()
    app.processEvents()


def test_poetore_mode_forwards_capture_hotkey_release():
    window = MagicMock()
    window._poetore_window = MagicMock()

    PoetoreModeWindow.handle_hotkey(window, "poetore_capture_released")

    window._poetore_window.capture_hotkey_released.assert_called_once_with()


def test_poetore_mode_starts_auto_hide_capture_and_forwards_release():
    window = MagicMock()
    window._poetore_window = MagicMock()

    PoetoreModeWindow.handle_hotkey(window, "poetore_auto_hide")
    PoetoreModeWindow.handle_hotkey(window, "poetore_auto_hide_released")

    window.capture_poetore_item.assert_called_once_with(auto_hide=True)
    window._poetore_window.capture_hotkey_released.assert_called_once_with()


def test_poetore_mode_capture_hint_uses_configured_hotkey():
    app = QApplication.instance() or QApplication([])
    config = {"hotkeys": {
        "poetore_capture": "Ctrl+Shift+P",
        "poetore_auto_hide": "Alt+Q",
    }}

    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value=config,
    ), patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ), patch.object(PoetoreModeWindow, "refresh_currency_rate"):
        window = PoetoreModeWindow()

    assert window.capture_hint.text() == (
        "アイテムにマウスオーバーして Ctrl + Shift + P 操作モード / "
        "Alt + Q AUTO-HIDE"
    )
    window.config["hotkeys"]["poetore_capture"] = "none"
    window.config["hotkeys"]["poetore_auto_hide"] = "none"
    window._update_capture_hint()
    assert window.capture_hint.text() == "価格チェックのホットキーが設定されていません。"
    window.close()
    app.processEvents()


def test_poetore_mode_passes_configured_interactive_hotkey_to_capture():
    owner = MagicMock()
    owner.config = {
        "poe_version": POE2,
        "hotkeys": {"poetore_capture": "Ctrl+Shift+P"},
    }
    poetore_window = MagicMock()
    trace = MagicMock()

    with patch(
        "src.poetore.performance.start_search_trace", return_value=trace,
    ), patch(
        "src.poetore.ui.show_poetore_window", return_value=poetore_window,
    ), patch(
        "src.ui.poetore_mode_window.is_feature_supported", return_value=True,
    ):
        PoetoreModeWindow.capture_poetore_item(owner)

    poetore_window.capture_from_poe.assert_called_once_with(
        trace, capture_hotkey="Ctrl+Shift+P",
    )


def test_poetore_mode_renders_divine_chaos_rate():
    app = QApplication.instance() or QApplication([])
    config = {"hotkeys": {}}

    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value=config,
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
    style = window.centralWidget().styleSheet()
    assert "#65FFCA" in style
    assert "#343B3E" in style
    assert "#DB86EF" not in style.upper()
    window.close()
    app.processEvents()


def test_poe2_poetore_mode_renders_divine_exalted_rate():
    app = QApplication.instance() or QApplication([])
    config = {"poe_version": POE2, "hotkeys": {}}

    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value=config,
    ), patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ), patch.object(PoetoreModeWindow, "refresh_currency_rate"):
        with patch(
            "src.ui.poetore_mode_window.is_feature_supported", return_value=True,
        ):
            window = PoetoreModeWindow()

    window._show_rate("Runes of Aldur", 364.9)
    assert window.divine_rate_value.text() == "1 = 364.9 Exalted"
    assert window.findChild(QLabel, "exaltedCurrencyIcon") is not None
    assert window.findChild(QLabel, "chaosCurrencyIcon") is None
    window.close()
    app.processEvents()


def test_poe2_currency_rate_auto_league_does_not_call_trade2_api():
    app = QApplication.instance() or QApplication([])
    config = {"poe_version": POE2, "hotkeys": {}, "poetore": {"league_poe2": "auto"}}

    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config", return_value=config,
    ), patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ), patch.object(PoetoreModeWindow, "refresh_currency_rate"), patch(
        "src.ui.poetore_mode_window.is_feature_supported", return_value=True,
    ), patch(
        "src.poetore.poe2.trade.available_pc_leagues",
        side_effect=AssertionError("Trade2 API must not be used"),
    ):
        window = PoetoreModeWindow()

    assert window._currency_rate_league() == "Runes of Aldur"
    window.close()
    app.processEvents()
