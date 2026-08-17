from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QTabWidget

from src.ui.poetore_settings_dialog import PoetoreSettingsDialog
from src.poetore.trade import TradeLeague
from src.ui.settings_dialog import AutoHideHotkeyWidget, HotkeyButton


def test_poetore_settings_contains_common_trade_and_window_controls():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={
            "startup": {
                "preferred_mode": "poetore",
                "show_mode_selector": False,
            },
            "hotkeys": {
                "start_stop": "F7",
                "monastery": "F12",
                "poetore_capture": "alt+d",
                "poetore_auto_hide": "ctrl+d",
            },
            "poetore": {"league": "auto"},
            "window_opacity": 80,
            "text_opacity": 70,
            "window_locked": True,
            "always_on_top": False,
            "snap_to_right_edge": True,
            "stash_tab_scroll_enabled": True,
        }
    )

    assert "#65FFCA" in dialog.styleSheet()
    assert "#343B3E" in dialog.styleSheet()
    assert not hasattr(dialog, "log_path_edits")
    assert not hasattr(dialog, "timer_size_combo")
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "修道院へ移動（/monastery）:" in labels
    assert all("（仮）修道院" not in label for label in labels)
    assert dialog.preferred_mode_combo.currentData() == "poetore"
    dialog.preferred_mode_combo.setCurrentIndex(
        dialog.preferred_mode_combo.findData("poenavi")
    )
    settings = dialog.get_settings()
    assert settings["startup"]["preferred_mode"] == "poenavi"
    assert settings["hotkeys"]["start_stop"] == "F7"
    assert settings["hotkeys"]["monastery"] == "F12"
    assert settings["hotkeys"]["poetore_capture"] == "alt+d"
    assert settings["hotkeys"]["poetore_auto_hide"] == "ctrl+d"
    assert settings["stash_tab_scroll_enabled"] is True
    assert "スタッシュ外" in dialog.stash_tab_scroll_cb.text()
    dialog.stash_tab_scroll_cb.setChecked(False)
    assert dialog.get_settings()["stash_tab_scroll_enabled"] is False
    assert isinstance(dialog.capture_hotkey, AutoHideHotkeyWidget)
    assert dialog.capture_hotkey.alt_button.isChecked()
    assert dialog.capture_hotkey.key_button.key_text == "d"
    assert isinstance(dialog.auto_hide_hotkey, AutoHideHotkeyWidget)
    assert dialog.auto_hide_hotkey.ctrl_button.isChecked()
    assert dialog.auto_hide_hotkey.key_button.key_text == "d"
    assert dialog.auto_hide_hotkey.ctrl_button.width() == 48
    assert dialog.auto_hide_hotkey.alt_button.width() == 48
    assert "#65FFCA" in dialog.auto_hide_hotkey.ctrl_button.styleSheet()
    assert settings["window_opacity"] == 80
    assert settings["text_opacity"] == 70
    assert settings["window_locked"] is True
    assert settings["always_on_top"] is False
    assert settings["snap_to_right_edge"] is True
    tabs = dialog.findChild(QTabWidget)
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "基本設定",
        "任意コマンド設定",
        "アプリ情報",
    ]
    assert dialog.windowTitle() == "設定"
    assert "subcontrol-position: top center" in dialog.styleSheet()
    note = dialog.findChild(QLabel, "startupModeSelectorNote")
    layout = dialog.show_mode_selector_cb.parentWidget().layout()
    assert layout.indexOf(note) == layout.indexOf(dialog.show_mode_selector_cb) + 1
    assert "OFFにすると" in note.text()
    private_note = dialog.findChild(QLabel, "privateLeagueNote")
    assert (
        private_note.text()
        == "プライベートリーグで使う場合は、リーグ名を直接手打ちで入力してください。"
    )
    dialog.close()


def test_poetore_hotkey_controls_capture_the_next_pressed_key():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={"hotkeys": {"exit": "F5"}})
    assert isinstance(dialog.exit_hotkey, HotkeyButton)
    dialog.exit_hotkey.setChecked(True)
    assert dialog.exit_hotkey.text() == "Press any key..."
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_H,
        Qt.KeyboardModifier.ControlModifier,
    )
    dialog.exit_hotkey.keyPressEvent(event)
    assert dialog.exit_hotkey.key_text == "Ctrl+H"
    assert dialog.get_settings()["hotkeys"]["exit"] == "Ctrl+H"
    dialog.close()


def test_auto_hide_hotkey_uses_selected_modifier_and_plain_trigger_key():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={"hotkeys": {"poetore_auto_hide": "alt+q"}}
    )
    assert dialog.auto_hide_hotkey.alt_button.isChecked()
    assert dialog.auto_hide_hotkey.key_button.key_text == "q"

    dialog.auto_hide_hotkey.key_button.setChecked(True)
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_R,
        Qt.KeyboardModifier.ControlModifier,
    )
    dialog.auto_hide_hotkey.key_button.keyPressEvent(event)

    assert dialog.auto_hide_hotkey.key_button.key_text == "R"
    assert dialog.get_settings()["hotkeys"]["poetore_auto_hide"] == "alt+R"
    dialog.close()


def test_capture_hotkey_requires_ctrl_or_alt_and_plain_trigger_key():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={"hotkeys": {"poetore_capture": "Ctrl+Shift+P"}}
    )
    assert dialog.capture_hotkey.ctrl_button.isChecked()
    assert dialog.capture_hotkey.key_button.key_text == "P"

    dialog.capture_hotkey.set_modifier("alt")
    dialog.capture_hotkey.set_key("Q")

    assert dialog.get_settings()["hotkeys"]["poetore_capture"] == "alt+Q"
    dialog.close()


def test_poetore_settings_league_choices_match_trade_window_and_allow_manual_input():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={"poetore": {"league": "auto"}}
    )

    dialog._show_trade_leagues((
        TradeLeague("Standard"),
        TradeLeague("Allflame"),
        TradeLeague("Hardcore Allflame", True),
    ))

    assert dialog.league_combo.itemText(0) == "自動（現行SC: Allflame）"
    assert [
        dialog.league_combo.itemData(index)
        for index in range(dialog.league_combo.count())
    ] == ["auto", "Standard", "Allflame", "Hardcore Allflame"]

    dialog.league_combo.setEditText("My Private League")
    assert dialog.get_settings()["poetore"]["league"] == "My Private League"
    dialog.close()


def test_poetore_settings_saves_result_font_size():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={"poetore": {"result_font_size": "medium"}}
    )

    assert dialog.result_font_size_combo.currentData() == "medium"
    assert [
        dialog.result_font_size_combo.itemData(index)
        for index in range(dialog.result_font_size_combo.count())
    ] == ["small", "medium", "large"]
    assert [
        dialog.result_font_size_combo.itemText(index)
        for index in range(dialog.result_font_size_combo.count())
    ] == ["小", "中", "大"]

    dialog.result_font_size_combo.setCurrentIndex(
        dialog.result_font_size_combo.findData("large")
    )

    assert dialog.get_settings()["poetore"]["result_font_size"] == "large"
    note = dialog.findChild(QLabel, "resultFontSizeNote")
    assert "ボタンや入力欄" in note.text()
    dialog.close()


def test_poetore_settings_describes_obs_result_window_behavior():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={"poetore": {}})

    assert dialog.obs_streaming_enabled_cb.text() == (
        "検索結果ウィンドウをOBS配信用にする"
    )
    note = dialog.findChild(QLabel, "obsStreamingNote")
    assert note.text() == (
        "待機中はタイトルバーだけを表示し、検索すると検索結果を当該タイトルバーの下に"
        "展開します。OBSでは「ぽえとれ - 検索結果ウィンドウ」として認識されます。"
    )
    dialog.close()


def test_poetore_settings_defaults_unknown_result_font_size_to_medium():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={"poetore": {"result_font_size": "unknown"}}
    )

    assert dialog.result_font_size_combo.currentData() == "medium"
    dialog.close()


def test_poetore_settings_can_reset_both_saved_result_positions():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={
            "poetore": {
                "result_positions": {
                    "stash": {"x_ratio": 0.2, "y_ratio": 0.3},
                    "inventory": {"x_ratio": 0.8, "y_ratio": 0.4},
                }
            }
        }
    )

    dialog.reset_result_positions_button.click()

    assert "result_positions" not in dialog.get_settings()["poetore"]
    assert dialog.result_positions_reset_note.text() == "保存時にリセットします"
    assert not dialog.reset_result_positions_button.isEnabled()
    dialog.close()


def test_poetore_settings_rejects_duplicate_common_hotkeys():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={
            "hotkeys": {
                "exit": "ctrl+F5",
                "monastery": "F12",
                "poetore_capture": "ctrl+F5",
                "cheat_sheets_toggle": "shift+space",
            }
        }
    )

    with patch(
        "src.ui.poetore_settings_dialog.QMessageBox.warning"
    ) as warning:
        dialog.accept()

    assert dialog.result() != QDialog.Accepted
    warning.assert_called_once()
    assert "f5" in warning.call_args.args[2].casefold()
    dialog.close()


def test_poetore_app_information_update_button_uses_injected_callback():
    QApplication.instance() or QApplication([])
    calls = []
    dialog = PoetoreSettingsDialog(
        current_config={},
        update_check_callback=lambda: calls.append("checked"),
    )

    button = dialog.findChild(QPushButton, "appInfoUpdateButton")
    assert button is not None
    assert button.isEnabled()

    button.click()

    assert calls == ["checked"]
    dialog.close()
