from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QLabel,
    QPushButton,
    QTabWidget,
)

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
        }
    )

    assert "#65FFCA" in dialog.styleSheet()
    assert "#343B3E" in dialog.styleSheet()
    assert not hasattr(dialog, "log_path_edits")
    assert not hasattr(dialog, "timer_size_combo")
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "修道院へ移動（/monastery）:" in labels
    assert all("（仮）修道院" not in label for label in labels)
    assert dialog.app_mode_radios["poetore"].isChecked()
    assert dialog.app_mode_startup_combo.currentData() == "poetore"
    dialog.app_mode_radios["poenavi"].setChecked(True)
    dialog.app_mode_startup_combo.setCurrentIndex(
        dialog.app_mode_startup_combo.findData("ask")
    )
    settings = dialog.get_settings()
    assert settings["startup"]["preferred_mode"] == "poenavi"
    assert settings["hotkeys"]["start_stop"] == "F7"
    assert settings["hotkeys"]["monastery"] == "F12"
    assert settings["hotkeys"]["poetore_capture"] == "alt+d"
    assert settings["hotkeys"]["poetore_auto_hide"] == "ctrl+d"
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
    assert [radio.text() for radio in dialog.app_mode_radios.values()] == [
        "ぽえなび", "ぽえとれ"
    ]
    assert [
        dialog.app_mode_startup_combo.itemText(index)
        for index in range(dialog.app_mode_startup_combo.count())
    ] == ["毎回確認", "ぽえなび固定", "ぽえとれ固定"]
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


def test_poe2_league_selection_uses_same_ui_but_separate_setting():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={
        "poe_version": "poe2",
        "poetore": {"league": "Allflame", "league_poe2": "auto"},
    })
    dialog._show_trade_leagues((
        TradeLeague("Runes of Aldur"), TradeLeague("HC Runes of Aldur", True),
        TradeLeague("Standard"),
    ))
    assert dialog.league_combo.itemText(0) == "自動（現行SC: Runes of Aldur）"
    assert [dialog.league_combo.itemData(i) for i in range(dialog.league_combo.count())] == [
        "auto", "Runes of Aldur", "HC Runes of Aldur", "Standard",
    ]
    dialog.league_combo.setCurrentIndex(1)
    settings = dialog.get_settings()["poetore"]
    assert settings["league"] == "Allflame"
    assert settings["league_poe2"] == "Runes of Aldur"
    dialog.close()


def test_poetore_settings_saves_same_poe_version_controls_as_poenavi():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={
        "poe_version": "poe1",
        "poe_version_mode": "ask",
    })

    assert dialog.poe_version_radios["poe1"].isChecked()
    assert dialog.poe_version_mode_combo.currentData() == "ask"
    dialog.poe_version_radios["poe2"].setChecked(True)
    dialog.poe_version_mode_combo.setCurrentIndex(
        dialog.poe_version_mode_combo.findData("poe2")
    )

    settings = dialog.get_settings()
    assert settings["poe_version"] == "poe2"
    assert settings["poe_version_mode"] == "poe2"
    dialog.close()


def test_poetore_fixed_startup_mode_selects_the_fixed_app():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={
        "startup": {"preferred_mode": "poetore", "show_mode_selector": True}
    })
    dialog.app_mode_startup_combo.setCurrentIndex(
        dialog.app_mode_startup_combo.findData("poenavi")
    )

    assert dialog.get_settings()["startup"] == {
        "preferred_mode": "poenavi",
        "show_mode_selector": False,
    }
    dialog.close()


def test_poetore_poe_version_group_is_visible_and_above_startup_mode():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={"poe_version": "poe2"})
    groups = {
        group.title(): group
        for group in dialog.findChildren(QGroupBox)
        if group.title() in {"PoEバージョン", "起動モード"}
    }
    layout = groups["PoEバージョン"].parentWidget().layout()

    assert layout.indexOf(groups["PoEバージョン"]) < layout.indexOf(groups["起動モード"])
    assert "QRadioButton" in dialog.styleSheet()
    assert all(radio.text() in {"PoE1", "PoE2"} for radio in dialog.poe_version_radios.values())
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
                "exit": "F5",
                "monastery": "F12",
                "poetore_capture": "F5",
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
