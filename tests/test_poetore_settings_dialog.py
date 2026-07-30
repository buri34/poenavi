from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QTabWidget

from src.ui.poetore_settings_dialog import PoetoreSettingsDialog
from src.poetore.trade import TradeLeague


def test_poetore_settings_contains_common_trade_and_window_controls():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={
            "startup": {
                "preferred_mode": "poetore",
                "show_mode_selector": False,
            },
            "hotkeys": {"start_stop": "F7", "poetore_capture": "alt+d"},
            "poetore": {"league": "auto"},
            "window_opacity": 80,
            "text_opacity": 70,
            "window_locked": True,
            "always_on_top": False,
            "snap_to_right_edge": True,
        }
    )

    assert "#DB86EF" in dialog.styleSheet()
    assert not hasattr(dialog, "log_path_edits")
    assert not hasattr(dialog, "timer_size_combo")
    assert dialog.preferred_mode_combo.currentData() == "poetore"
    dialog.preferred_mode_combo.setCurrentIndex(
        dialog.preferred_mode_combo.findData("poenavi")
    )
    settings = dialog.get_settings()
    assert settings["startup"]["preferred_mode"] == "poenavi"
    assert settings["hotkeys"]["start_stop"] == "F7"
    assert settings["hotkeys"]["poetore_capture"] == "alt+d"
    assert settings["window_opacity"] == 80
    assert settings["text_opacity"] == 70
    assert settings["window_locked"] is True
    assert settings["always_on_top"] is False
    assert settings["snap_to_right_edge"] is True
    tabs = dialog.findChild(QTabWidget)
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "基本設定",
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


def test_poetore_settings_defaults_unknown_result_font_size_to_small():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={"poetore": {"result_font_size": "unknown"}}
    )

    assert dialog.result_font_size_combo.currentData() == "small"
    dialog.close()


def test_poetore_settings_rejects_duplicate_common_hotkeys():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={
            "hotkeys": {
                "exit": "F5",
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
