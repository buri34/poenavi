from unittest.mock import MagicMock, call, patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QSystemTrayIcon

from src.ui.poetore_mode_window import PoetoreModeWindow


def test_poetore_mode_starts_only_common_and_poetore_services():
    app = QApplication.instance() or QApplication([])
    config = {
        "hotkeys": {
            "exit": "F5",
            "monastery": "F12",
            "poetore_capture": "alt+d",
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
    ) as hotkey_class:
        hotkey_service = MagicMock()
        hotkey_service.command.connect = MagicMock()
        hotkey_class.return_value = hotkey_service
        with patch.object(PoetoreModeWindow, "refresh_currency_rate"):
            window = PoetoreModeWindow()

    supplied_hotkeys = hotkey_class.call_args.args[0]
    assert supplied_hotkeys == {
        "exit": "F5",
        "monastery": "F12",
        "poetore_capture": "alt+d",
        "map_check": "alt+f",
        "cheat_sheets_toggle": "shift+space",
    }
    assert not hasattr(window, "log_watcher")
    assert not hasattr(window, "mini_navi_overlay")
    assert not hasattr(window, "timer")
    assert "currency_rate_refresh" in window.active_service_names
    assert window.memo_button.text() == "📝"
    assert window.cheat_sheets_button.text() == "🖼"
    assert window.map_mods_button.text() == "🗺"
    assert window.settings_button.text() == "⚙"
    assert window.memo_button.size().width() == 35
    assert window.memo_button.size().height() == 35
    assert window.divine_rate_value.text() == "取得中…"
    assert window.width() == 558
    assert window.windowFlags() & Qt.FramelessWindowHint
    assert window.capture_hint.text() == (
        "アイテムにマウスオーバーしながらAlt + Dで価格チェック"
    )
    assert window.findChild(QPushButton, "poetoreMinimizeButton").text() == "─"
    assert window.findChild(QPushButton, "poetoreCloseButton").text() == "✕"
    assert window.tray_icon.toolTip() == "ぽえとれ"
    assert [
        action.text() for action in window.tray_icon.contextMenu().actions()
        if not action.isSeparator()
    ] == ["ぽえとれを表示", "設定", "終了"]
    hotkey_service.start.assert_called_once()
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


def test_poetore_mode_capture_hint_uses_configured_hotkey():
    app = QApplication.instance() or QApplication([])
    config = {"hotkeys": {"poetore_capture": "Ctrl+Shift+P"}}

    with patch(
        "src.ui.poetore_mode_window.ConfigManager.load_config",
        return_value=config,
    ), patch(
        "src.ui.poetore_mode_window.GlobalHotkeyService"
    ), patch.object(PoetoreModeWindow, "refresh_currency_rate"):
        window = PoetoreModeWindow()

    assert window.capture_hint.text() == (
        "アイテムにマウスオーバーしながらCtrl + Shift + Pで価格チェック"
    )
    window.config["hotkeys"]["poetore_capture"] = "none"
    window._update_capture_hint()
    assert window.capture_hint.text() == "価格チェックのホットキーが設定されていません。"
    window.close()
    app.processEvents()


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
    assert "#DB86EF" in window.centralWidget().styleSheet()
    window.close()
    app.processEvents()
