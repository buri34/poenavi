from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QTabWidget,
)

from src.poetore.trade import TradeLeague
from src.ui.dialog_theme import POETORE_DIALOG_THEME
from src.ui.poetore_settings_dialog import PoetoreSettingsDialog
from src.ui.settings_dialog import AutoHideHotkeyWidget, HotkeyButton
from src.utils.poe_version_data import POE1, POE2


def test_monastery_hotkey_is_visible_only_for_poe1():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={"poe_version": POE2})

    assert not dialog.monastery_label.isVisibleTo(dialog)
    assert not dialog.monastery_hotkey.isVisibleTo(dialog)
    assert not dialog.map_check_label.isVisibleTo(dialog)
    assert not dialog.map_check_hotkey.isVisibleTo(dialog)

    dialog.poe_version_radios[POE1].setChecked(True)
    assert dialog.monastery_label.isVisibleTo(dialog)
    assert dialog.monastery_hotkey.isVisibleTo(dialog)
    assert dialog.map_check_label.isVisibleTo(dialog)
    assert dialog.map_check_hotkey.isVisibleTo(dialog)
    dialog.close()


def test_expedition_settings_are_preserved_without_general_settings_controls():
    QApplication.instance() or QApplication([])
    expedition = {
        "enabled": True,
        "region": {"left": 0.1, "top": 0.2, "right": 0.6, "bottom": 0.9},
    }
    dialog = PoetoreSettingsDialog(current_config={
        "poe_version": POE2,
        "hotkeys": {"expedition_reward_ocr": "alt+r"},
        "poetore": {"expedition_reward_overlay": expedition},
    })

    assert not hasattr(dialog, "expedition_group")
    assert dialog.findChild(QPushButton, "openExpeditionSettingsButton") is None
    settings = dialog.get_settings()
    assert settings["hotkeys"]["expedition_reward_ocr"] == "alt+r"
    assert settings["poetore"]["expedition_reward_overlay"] == expedition
    dialog.close()


def test_poe2_enables_poetore_startup_choices():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={
        "poe_version": POE2,
        "poe_version_mode": POE2,
        "startup": {"preferred_mode": "poetore", "show_mode_selector": False},
    })

    assert dialog.app_mode_radios["poetore"].isEnabled()
    assert dialog.app_mode_radios["poetore"].isChecked()
    assert dialog.skip_startup_selector_checkbox.isChecked()
    assert dialog.get_settings()["startup"] == {
        "preferred_mode": "poetore",
        "show_mode_selector": False,
        "windows_autostart_poetore": False,
    }
    dialog.close()


def test_hideout_notification_controls_load_and_save_seconds_and_volume():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={
        "poe_version": POE1,
        "client_log_paths": {"poe1": r"C:\PoE\logs\Client.txt"},
        "poetore": {
            "hideout_notification": {
                "duration_seconds": 125,
                "repeat": True,
                "audio_source": "custom",
                "custom_audio_display_name": "声.mp3",
                "custom_audio_file": "poetore-hideout-notification.mp3",
                "volume": 75,
            }
        },
    })
    assert dialog.hideout_minutes_spin.value() == 2
    assert dialog.hideout_seconds_spin.value() == 5
    assert dialog.hideout_repeat_cb.isChecked()
    assert dialog.hideout_audio_name.text() == "声.mp3"
    assert dialog.hideout_log_path_edit.text() == r"C:\PoE\logs\Client.txt"
    assert dialog.hideout_volume_label.text() == "75"
    assert dialog.hideout_note.text().splitlines() == [
        "集中モード中、隠れ家に設定時間滞在すると音声でお知らせします。",
        "音声ファイルは、選択ボタンから任意のwavまたはmp3ファイルに変更可能です。",
        "音量50が音声本来の大きさで、50より上は増幅します。",
    ]
    settings = dialog.get_settings()["poetore"]["hideout_notification"]
    assert settings == {
        "duration_seconds": 125,
        "repeat": True,
        "audio_source": "custom",
        "custom_audio_display_name": "声.mp3",
        "custom_audio_file": "poetore-hideout-notification.mp3",
        "volume": 75,
    }
    assert dialog.get_settings()["client_log_paths"]["poe1"] == (
        r"C:\PoE\logs\Client.txt"
    )
    dialog.close()


def test_hideout_notification_duration_is_bounded_to_ten_seconds():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={"poe_version": POE1})
    dialog.hideout_minutes_spin.setValue(0)
    dialog.hideout_seconds_spin.setValue(1)
    assert dialog.hideout_seconds_spin.value() == 10
    settings = dialog.get_settings()["poetore"]["hideout_notification"]
    assert settings["duration_seconds"] == 10
    assert dialog.hideout_volume_label.text() == "50（標準）"
    dialog.close()


def test_hideout_duration_buttons_show_bounds_and_adjust_reliably(qtbot):
    dialog = PoetoreSettingsDialog(current_config={
        "poe_version": POE1,
        "poetore": {"hideout_notification": {"duration_seconds": 10}},
    })
    qtbot.addWidget(dialog)

    assert not dialog.hideout_minutes_down_button.isEnabled()
    assert not dialog.hideout_seconds_down_button.isEnabled()
    for button in (
        dialog.hideout_minutes_up_button,
        dialog.hideout_minutes_down_button,
        dialog.hideout_seconds_up_button,
        dialog.hideout_seconds_down_button,
    ):
        assert button.text() == ""
        assert not button.icon().isNull()

    qtbot.mouseClick(dialog.hideout_seconds_up_button, Qt.LeftButton)
    assert (dialog.hideout_minutes_spin.value(), dialog.hideout_seconds_spin.value()) == (0, 11)
    qtbot.mouseClick(dialog.hideout_seconds_down_button, Qt.LeftButton)
    assert (dialog.hideout_minutes_spin.value(), dialog.hideout_seconds_spin.value()) == (0, 10)

    qtbot.mouseClick(dialog.hideout_minutes_up_button, Qt.LeftButton)
    assert (dialog.hideout_minutes_spin.value(), dialog.hideout_seconds_spin.value()) == (1, 10)
    qtbot.mouseClick(dialog.hideout_minutes_down_button, Qt.LeftButton)
    assert (dialog.hideout_minutes_spin.value(), dialog.hideout_seconds_spin.value()) == (0, 10)
    dialog.close()


def test_hideout_minute_down_can_reach_zero_minutes(qtbot):
    dialog = PoetoreSettingsDialog(current_config={
        "poe_version": POE1,
        "poetore": {"hideout_notification": {"duration_seconds": 61}},
    })
    qtbot.addWidget(dialog)

    assert dialog.hideout_minutes_down_button.isEnabled()
    qtbot.mouseClick(dialog.hideout_minutes_down_button, Qt.LeftButton)
    assert (dialog.hideout_minutes_spin.value(), dialog.hideout_seconds_spin.value()) == (0, 10)
    dialog.close()


def test_hideout_second_buttons_carry_and_borrow_minutes(qtbot):
    dialog = PoetoreSettingsDialog(current_config={
        "poe_version": POE1,
        "poetore": {"hideout_notification": {"duration_seconds": 59}},
    })
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.hideout_seconds_up_button, Qt.LeftButton)
    assert (dialog.hideout_minutes_spin.value(), dialog.hideout_seconds_spin.value()) == (1, 0)
    qtbot.mouseClick(dialog.hideout_seconds_down_button, Qt.LeftButton)
    assert (dialog.hideout_minutes_spin.value(), dialog.hideout_seconds_spin.value()) == (0, 59)
    dialog.close()


def test_hideout_audio_error_message_uses_dark_poetore_theme(monkeypatch):
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={"poe_version": POE1})
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.Ok)

    result = dialog._show_hideout_audio_message(
        QMessageBox.Warning,
        "音声再生機能を読み込めませんでした。",
    )

    messages = dialog.findChildren(QMessageBox)
    assert result == QMessageBox.Ok
    assert len(messages) == 1
    assert messages[0].property("dialogTheme") == "poetore"
    assert POETORE_DIALOG_THEME.background in messages[0].styleSheet()
    assert POETORE_DIALOG_THEME.text in messages[0].styleSheet()
    dialog.close()


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

    assert dialog.theme is POETORE_DIALOG_THEME
    assert dialog.property("dialogTheme") == "poetore"
    assert dialog.property("dialogAccent") == "#65FFCA"
    assert "#65FFCA" in dialog.styleSheet()
    assert "#B0FF7B" not in dialog.styleSheet()
    assert "#E9FFBD" not in dialog.styleSheet()
    assert "#E6ECEA" in dialog.styleSheet()
    assert "#111416" in dialog.styleSheet()
    assert "#171B1D" in dialog.styleSheet()
    assert "Noto Sans JP" in dialog.styleSheet()
    assert "font-size: 13px" in dialog.styleSheet()
    assert not hasattr(dialog, "log_path_edits")
    assert not hasattr(dialog, "timer_size_combo")
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "修道院へ移動（/monastery）:" in labels
    assert all("（仮）修道院" not in label for label in labels)
    assert dialog.app_mode_radios["poetore"].isChecked()
    assert not dialog.skip_startup_selector_checkbox.isChecked()
    dialog.app_mode_radios["poenavi"].setChecked(True)
    dialog.skip_startup_selector_checkbox.setChecked(False)
    settings = dialog.get_settings()
    assert settings["startup"]["preferred_mode"] == "poenavi"
    assert settings["hotkeys"]["start_stop"] == "F7"
    assert settings["hotkeys"]["monastery"] == "F12"
    assert settings["hotkeys"]["poetore_capture"] == "alt+d"
    assert settings["hotkeys"]["poetore_auto_hide"] == "ctrl+d"
    assert settings["stash_tab_scroll_enabled"] is True
    assert dialog.stash_tab_scroll_cb.text() == (
        "Ctrl＋マウスホイールでスタッシュタブを切り替える"
    )
    dialog.stash_tab_scroll_cb.setChecked(False)
    assert dialog.get_settings()["stash_tab_scroll_enabled"] is False
    assert isinstance(dialog.capture_hotkey, AutoHideHotkeyWidget)
    assert dialog.capture_hotkey.alt_button.isChecked()
    assert dialog.capture_hotkey.no_modifier_button is not None
    assert dialog.capture_hotkey.key_button.key_text == "d"
    assert isinstance(dialog.auto_hide_hotkey, AutoHideHotkeyWidget)
    assert dialog.auto_hide_hotkey.ctrl_button.isChecked()
    assert dialog.auto_hide_hotkey.no_modifier_button is None
    assert dialog.auto_hide_hotkey.key_button.key_text == "d"
    assert dialog.auto_hide_hotkey.ctrl_button.width() == 48
    assert dialog.auto_hide_hotkey.alt_button.width() == 48
    assert dialog.auto_hide_hotkey.ctrl_button.styleSheet() == ""
    assert settings["window_opacity"] == 80
    assert settings["text_opacity"] == 70
    assert settings["window_locked"] is True
    assert settings["always_on_top"] is False
    assert settings["snap_to_right_edge"] is True
    assert not dialog.capture_error_notification_cb.isChecked()
    assert dialog.capture_error_notification_cb.text() == (
        "アイテムを取得できなかったときに通知する"
    )
    groups = [group.title() for group in dialog.findChildren(QGroupBox)]
    assert groups.index("検索時のエラー処理") == (
        groups.index("共通・ぽえとれホットキー") + 1
    )
    tabs = dialog.findChild(QTabWidget)
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "基本設定",
        "任意コマンド設定",
        "アプリ情報",
    ]
    assert dialog.windowTitle() == "設定"
    assert "subcontrol-position: top left" in dialog.styleSheet()
    assert [radio.text() for radio in dialog.app_mode_radios.values()] == [
        "ぽえなび", "ぽえとれ"
    ]
    assert dialog.skip_startup_selector_checkbox.text() == "次回からこの設定で直接起動"
    private_note = dialog.findChild(QLabel, "privateLeagueNote")
    assert (
        private_note.text()
        == "プライベートリーグで使う場合は、リーグ名を直接手打ちで入力してください。"
    )
    dialog.close()


def test_poetore_settings_saves_capture_error_notification_preference():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={
            "poetore": {"capture_error_notification_enabled": False}
        }
    )

    assert not dialog.capture_error_notification_cb.isChecked()
    dialog.capture_error_notification_cb.setChecked(True)
    assert dialog.get_settings()["poetore"][
        "capture_error_notification_enabled"
    ] is True
    dialog.close()


def test_poetore_capture_error_notification_is_disabled_by_default():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={})

    assert not dialog.capture_error_notification_cb.isChecked()
    assert dialog.get_settings()["poetore"][
        "capture_error_notification_enabled"
    ] is False
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
    assert dialog.league_refresh_button.text() == "再取得"
    assert dialog.league_refresh_button.toolTip() == "公式サイトからリーグ一覧を再取得"
    assert dialog.league_refresh_button.isEnabled()

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


def test_poe2_settings_refresh_button_forces_a_fresh_league_request(monkeypatch):
    requested = []

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr("src.ui.poetore_settings_dialog.threading.Thread", ImmediateThread)
    monkeypatch.setattr(
        "src.poetore.poe2.trade.available_pc_leagues",
        lambda *, force_refresh=False: (
            requested.append(force_refresh) or (TradeLeague("Fresh League"),)
        ),
    )
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={"poe_version": "poe2"})

    dialog.league_refresh_button.click()

    assert requested == [True]
    assert dialog.league_combo.itemText(0) == "自動（現行SC: Fresh League）"
    assert dialog.league_refresh_button.isEnabled()
    assert dialog.league_refresh_button.text() == "再取得"
    dialog.close()


def test_poetore_settings_saves_same_poe_version_controls_as_poenavi():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={
        "poe_version": "poe1",
        "poe_version_mode": "ask",
    })

    assert dialog.poe_version_radios["poe1"].isChecked()
    assert not dialog.skip_startup_selector_checkbox.isChecked()
    dialog.poe_version_radios["poe2"].setChecked(True)
    dialog.skip_startup_selector_checkbox.setChecked(True)

    settings = dialog.get_settings()
    assert settings["poe_version"] == "poe2"
    assert settings["poe_version_mode"] == "poe2"
    dialog.close()


def test_poetore_fixed_startup_mode_selects_the_fixed_app():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={
        "startup": {"preferred_mode": "poetore", "show_mode_selector": True}
    })
    dialog.app_mode_radios["poenavi"].setChecked(True)
    dialog.skip_startup_selector_checkbox.setChecked(True)

    assert dialog.get_settings()["startup"] == {
        "preferred_mode": "poenavi",
        "show_mode_selector": False,
        "windows_autostart_poetore": False,
    }
    dialog.close()


def test_poetore_poe_version_and_app_mode_are_in_one_startup_group():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={"poe_version": "poe2"})
    groups = [group for group in dialog.findChildren(QGroupBox) if group.title() == "起動設定"]
    labels = [label.text() for label in groups[0].findChildren(QLabel)]
    assert len(groups) == 1
    assert "PoEバージョン" in labels
    assert "起動モード" in labels
    assert "QRadioButton" in dialog.styleSheet()
    assert all(radio.text() in {"PoE1", "PoE2"} for radio in dialog.poe_version_radios.values())
    dialog.close()


def test_poetore_windows_autostart_has_blank_line_and_saves_setting():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={
        "startup": {"windows_autostart_poetore": True}
    })

    checkbox = dialog.windows_autostart_poetore_checkbox
    assert checkbox.text() == "Windowsログイン時にぽえとれを自動起動"
    assert checkbox.isChecked()
    layout = dialog.skip_startup_selector_checkbox.parentWidget().layout()
    direct_index = layout.indexOf(dialog.skip_startup_selector_checkbox)
    assert layout.itemAt(direct_index + 1).widget() is dialog.startup_change_note
    assert dialog.startup_change_note.text() == (
        "PoEバージョン・起動モードの変更は、次回起動時から適用されます。"
    )
    assert layout.itemAt(direct_index + 2).spacerItem().sizeHint().height() == 13
    assert layout.itemAt(direct_index + 3).widget() is checkbox
    assert layout.itemAt(direct_index + 4).widget() is dialog.windows_autostart_note
    assert dialog.windows_autostart_note.text() == (
        "有効にすると、次回のWindowsログイン時からぽえとれを自動起動します。"
    )
    checkbox.setChecked(False)
    assert dialog.get_settings()["startup"]["windows_autostart_poetore"] is False
    dialog.close()


def test_poetore_settings_uses_shared_blue_checkbox_style_everywhere():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={
        "custom_commands": [{
            "enabled": True,
            "name": "hideout",
            "hotkey": "ctrl+h",
            "command": "/hideout",
        }]
    })

    checkboxes = dialog.findChildren(QCheckBox)
    assert checkboxes
    assert all(checkbox.styleSheet() == "" for checkbox in checkboxes)
    assert "#4488FF" in dialog.styleSheet()
    dialog.close()


def test_poetore_settings_uses_shared_control_roles_and_fixed_footer():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={})
    try:
        assert dialog.save_button.property("buttonRole") == "primary"
        assert dialog.cancel_button.property("buttonRole") == "secondary"
        assert dialog.custom_commands_widget.theme is POETORE_DIALOG_THEME
        assert dialog.custom_commands_widget.property("density") == "compact"
        assert (
            dialog.custom_commands_widget.add_button.property("buttonRole")
            == "primary"
        )
        assert (
            dialog.custom_commands_widget.remove_button.property("buttonRole")
            == "danger"
        )
        assert dialog.app_info_widget.update_button.property("buttonRole") == "primary"

        footer_widgets = [
            dialog.footer_layout.itemAt(index).widget()
            for index in range(dialog.footer_layout.count())
            if dialog.footer_layout.itemAt(index).widget() is not None
        ]
        assert footer_widgets[-2:] == [dialog.cancel_button, dialog.save_button]

        for widget_type in (
            QCheckBox,
            QComboBox,
            QGroupBox,
            QPushButton,
            QRadioButton,
            QSlider,
        ):
            assert all(
                widget.styleSheet() == ""
                for widget in dialog.findChildren(widget_type)
            )
    finally:
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
    assert dialog.obs_title_bar_opacity_slider.minimum() == 0
    assert dialog.obs_title_bar_opacity_slider.maximum() == 100
    assert dialog.obs_title_bar_opacity_slider.value() == 100
    note = dialog.findChild(QLabel, "obsStreamingNote")
    assert note.text() == (
        "待機中はタイトルバーだけを表示し、検索すると検索結果を当該タイトルバーの下に"
        "展開します。OBSでは「ぽえとれ - 検索結果ウィンドウ」として認識されます。\n"
        "待機中のタイトルバーは透過率を変更できます。"
    )
    dialog.close()


def test_poetore_settings_saves_obs_title_bar_opacity():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(current_config={
        "poetore": {"obs_streaming": {"enabled": True, "title_bar_opacity": 42}}
    })

    assert dialog.obs_title_bar_opacity_slider.value() == 42
    dialog.obs_title_bar_opacity_slider.setValue(18)
    assert dialog.get_settings()["poetore"]["obs_streaming"] == {
        "enabled": True,
        "title_bar_opacity": 18,
    }
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
