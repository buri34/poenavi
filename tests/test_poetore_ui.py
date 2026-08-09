from unittest.mock import Mock, patch
from dataclasses import replace
from datetime import datetime, timezone
import csv
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QPalette, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QMessageBox, QPushButton
import pytest

from src.poetore.ui import (
    PoetoreWindow, _MOD_COLUMN_CHECK, _MOD_COLUMN_MAX, _MOD_COLUMN_MIN, _MOD_COLUMN_TEXT,
    _UniqueRollSlider, _auto_mod_layout_sizes, _replace_filters_with_special_chips, prepare_poetore_window,
    show_poetore_window, _price_currency_icon_filename,
)
from src.poetore.window_position import PlacementContext
from src.poetore.trade import (
    PRESET_BASE, PRESET_FINISHED, PriceListing, PriceResult, TradeLeague, TradeStatFilter,
    build_search_query, resolve_trade_stat_filters,
)
from src.poetore.parser import parse_item_text
from src.poetore.models import ItemModifier, ParsedItem
from src.poetore.poe_ninja import PoeNinjaPrice
from src.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def deterministic_global_cursor(monkeypatch):
    """Keep listener-coordinate tests independent from the real CI cursor."""
    monkeypatch.setattr(
        PoetoreWindow,
        "_global_cursor_point",
        lambda _self, x, y: QPoint(x, y),
    )


def test_poetore_window_always_accepts_mouse_input(qapp):
    window = PoetoreWindow()
    try:
        assert window.isEnabled()
        assert not window.testAttribute(Qt.WA_TransparentForMouseEvents)
        assert window.testAttribute(Qt.WA_ShowWithoutActivating)
        assert not bool(window.windowFlags() & Qt.WindowTransparentForInput)
        assert bool(window.windowFlags() & Qt.FramelessWindowHint)
        assert bool(window.windowFlags() & Qt.WindowStaysOnTopHint)
        assert window.trade_status_combo.currentData() == "instant"
        assert window.trade_status_combo.count() == 4
        assert window.trade_status_combo.itemData(3) == "offline"
        assert window.listed_within_combo.currentData() == "any"
        assert window.listed_within_combo.count() == 7
        assert not window.trade_url_button.isEnabled()
        assert window.trade_currency_combo.currentData() == "any"
        assert window.trade_currency_combo.count() == 4
        assert [
            window.trade_currency_combo.itemText(index)
            for index in range(window.trade_currency_combo.count())
        ] == [
            "すべての通貨",
            "カオスオーブのみ",
            "神のオーブのみ",
            "カオスまたは神のオーブ",
        ]
        assert not hasattr(window, "disclaimer_label")
        assert window.trade_league_combo.currentData() == "auto"
        assert window._selected_trade_league() is None
        assert window.width() == 840
        assert window.minimumWidth() == 760
        assert window.height() == 1039
        assert window.price_list.minimumHeight() == 434
        assert window.trade_url_button.text() == "公式トレード  ↗"
        assert window.trade_url_button.toolTip() == "日本語公式Tradeをブラウザで開く"
        assert all(button.text() != "貼り付け" for button in window.findChildren(QPushButton))
    finally:
        window.close()


@pytest.mark.parametrize(
    ("setting", "font_px", "width", "height", "minimum_width"),
    (
        ("small", 12, 720, 1039, 680),
        ("medium", 14, 840, 1039, 760),
        ("large", 16, 960, 1039, 840),
    ),
)
def test_poetore_result_display_size_scales_window_and_controls(
    qapp, setting, font_px, width, height, minimum_width,
):
    window = PoetoreWindow(
        app_config={"poetore": {"result_font_size": setting}}
    )
    try:
        assert window._result_font_size == setting
        assert window.width() == width
        assert window.height() == height
        assert window.minimumWidth() == minimum_width
        assert f"font-size: {font_px}px" in window.styleSheet()
        assert window.trade_league_combo.width() == round(290 * font_px / 12)
        assert window.mod_filter_tree.minimumHeight() > 0
        assert window.price_list.minimumHeight() > 0
    finally:
        window.close()


def test_poetore_result_display_size_can_change_on_existing_window(qapp):
    config = {"poetore": {"result_font_size": "small"}}
    window = PoetoreWindow(app_config=config)
    try:
        config["poetore"]["result_font_size"] = "large"
        window.apply_result_display_size()

        assert window._result_font_size == "large"
        assert window.width() == 960
        assert window.height() == 1039
        assert "font-size: 16px" in window.styleSheet()
    finally:
        window.close()


def test_capture_error_dialog_uses_readable_dark_theme(qapp):
    window = PoetoreWindow()
    try:
        dialog = window._build_capture_error_dialog()
        style = dialog.styleSheet()

        assert dialog.icon() == QMessageBox.Icon.Warning
        assert dialog.text() == (
            "アイテムを取得できませんでした。\n"
            "PoEがアクティブでない可能性があります。\n"
            "PoEを前面にしてアイテムへカーソルを合わせ、\n"
            "もう一度 Alt+D を押してください。"
        )
        assert "background-color: #111111" in style
        assert "color: #f2e7f5" in style
        assert "color: #db86ef" in style
        assert "min-width: 290px" not in style
        assert dialog.standardButtons() == QMessageBox.StandardButton.Ok
        dialog.ensurePolished()
        dialog.adjustSize()
        assert dialog.sizeHint().width() < 450
    finally:
        window.close()


def test_capture_failure_opens_the_dark_error_dialog(qapp):
    window = PoetoreWindow()
    dialog = Mock()
    try:
        with patch(
            "src.poetore.ui.read_item_clipboard",
            return_value="",
        ), patch.object(
            window,
            "_build_capture_error_dialog",
            return_value=dialog,
        ) as build:
            window._capture_item_copy()

        build.assert_called_once()
        assert build.call_args.args == ()
        dialog.exec.assert_called_once_with()
    finally:
        window.close()


def test_capture_from_poe_remembers_the_verified_game_window(qapp):
    window = PoetoreWindow()
    try:
        with patch("src.poetore.ui.get_foreground_window", return_value=1234), patch(
            "src.poetore.ui.is_path_of_exile_window", return_value=True,
        ) as verify, patch("pynput.keyboard.Controller"), patch.object(
            QTimer, "singleShot",
        ):
            window.capture_from_poe()

        verify.assert_called_once_with(1234)
        assert window._poe_window_hwnd == 1234
    finally:
        window.close()


def test_auto_hide_capture_remembers_mode_and_cursor_origin(qapp):
    window = PoetoreWindow()
    context = PlacementContext(QRect(0, 0, 1920, 1080), QPoint(500, 400))
    try:
        controller = Mock()
        with patch("src.poetore.ui.capture_placement_context", return_value=context), patch(
            "pynput.keyboard.Controller", return_value=controller,
        ), patch.object(QTimer, "singleShot") as single_shot:
            window.capture_from_poe(
                auto_hide=True, capture_hotkey="ctrl+d",
            )

        assert window._capture_auto_hide is True
        assert window._auto_hide_hotkey_released is False
        assert window._auto_hide_origin == QPoint(500, 400)
        assert window._capture_copy_keys == ("c",)
        controller.release.assert_called_once_with("d")
        assert [call.args[0] for call in single_shot.call_args_list] == [30, 250]
    finally:
        window.close()


def test_alt_auto_hide_copy_uses_ctrl_c_without_changing_the_alt_hold_key(qapp):
    window = PoetoreWindow()
    try:
        with patch("pynput.keyboard.Controller"), patch.object(QTimer, "singleShot"):
            window.capture_from_poe(auto_hide=True, capture_hotkey="alt+q")

        assert window._capture_copy_keys[1] == "c"
        assert len(window._capture_copy_keys) == 2
    finally:
        window.close()


def test_capture_copy_starts_as_soon_as_hotkey_is_fully_released(qapp):
    window = PoetoreWindow()
    try:
        with patch("pynput.keyboard.Controller"), patch.object(
            QTimer, "singleShot",
        ) as single_shot, patch.object(window, "_send_copy") as send_copy:
            window.capture_from_poe()
            window.capture_hotkey_released()

        assert single_shot.call_args.args[0] == 250
        send_copy.assert_called_once_with(window._capture_copy_keys, window._capture_item_copy)
    finally:
        window.close()


def test_capture_copy_timeout_preserves_previous_250ms_fallback(qapp):
    window = PoetoreWindow()
    scheduled = []
    try:
        with patch("pynput.keyboard.Controller"), patch.object(
            QTimer, "singleShot", side_effect=lambda delay, fn: scheduled.append((delay, fn)),
        ), patch.object(window, "_send_copy") as send_copy:
            window.capture_from_poe()
            assert scheduled[0][0] == 250
            scheduled[0][1]()
            window.capture_hotkey_released()

        send_copy.assert_called_once_with(window._capture_copy_keys, window._capture_item_copy)
    finally:
        window.close()


def test_copy_continues_immediately_when_clipboard_generation_changes(qapp):
    window = PoetoreWindow()
    window._capture_keyboard = Mock()
    callback = Mock()
    try:
        with patch(
            "src.poetore.ui.clipboard_change_token",
            side_effect=[("windows", 10), ("windows", 11)],
        ), patch.object(QTimer, "singleShot") as single_shot:
            window._send_copy(("ctrl", "c"), callback)

        callback.assert_called_once_with()
        single_shot.assert_not_called()
    finally:
        window.close()


def test_copy_polls_until_clipboard_generation_changes(qapp):
    window = PoetoreWindow()
    window._clipboard_wait_generation = 1
    callback = Mock()
    scheduled = []
    try:
        with patch(
            "src.poetore.ui.clipboard_change_token",
            side_effect=[("windows", 10), ("windows", 11)],
        ), patch.object(
            QTimer, "singleShot", side_effect=lambda delay, fn: scheduled.append((delay, fn)),
        ):
            window._wait_for_clipboard_update(("windows", 10), callback, 1, 0)
            callback.assert_not_called()
            assert scheduled[0][0] == 10
            scheduled.pop(0)[1]()

        callback.assert_called_once_with()
    finally:
        window.close()


def test_copy_uses_existing_capture_after_clipboard_timeout(qapp):
    window = PoetoreWindow()
    window._clipboard_wait_generation = 1
    callback = Mock()
    try:
        with patch(
            "src.poetore.ui.clipboard_change_token", return_value=("windows", 10),
        ), patch.object(QTimer, "singleShot") as single_shot:
            window._wait_for_clipboard_update(("windows", 10), callback, 1, 300)

        callback.assert_called_once_with()
        single_shot.assert_not_called()
    finally:
        window.close()


def test_poetore_disclaimer_is_in_app_information(qapp):
    dialog = SettingsDialog(current_config={})
    try:
        text = dialog.app_disclaimer_label.text()
        assert text.startswith("ぽえなびは無料の非公式ツール")
        assert "提携・承認関係はありません" in text
        assert dialog.app_disclaimer_label.wordWrap()
        assert all(label.text() != "ぽえとれについて" for label in dialog.findChildren(QLabel))
    finally:
        dialog.close()


def test_show_poetore_window_is_independent_from_owner(qapp):
    owner = Mock()
    owner._poetore_window = None

    with patch.object(PoetoreWindow, "show"), patch.object(PoetoreWindow, "raise_"), patch.object(
        PoetoreWindow, "activateWindow"
    ):
        window = show_poetore_window(owner)

    try:
        assert window.parent() is None
        assert owner._poetore_window is window
    finally:
        window.close()


def test_prepare_poetore_window_has_no_trade_api_side_effect(qapp):
    owner = Mock()
    owner._poetore_window = None
    owner.config = {}
    with patch.object(PoetoreWindow, "refresh_trade_leagues") as refresh, patch(
        "src.poetore.trade._request_json",
    ) as request_json:
        window = prepare_poetore_window(owner)
    try:
        assert owner._poetore_window is window
        assert not window.isVisible()
        refresh.assert_not_called()
        request_json.assert_not_called()
    finally:
        window.close()


def test_329_single_copy_is_parsed_without_normal_and_detailed_merge(qapp):
    copied = """アイテムクラス: 靴
レアリティ: ユニーク
破滅の軌跡
メッシュブーツ
--------
アイテムレベル: 41
--------
{ ユニークモッド — スピード }
移動スピードが15%増加する
"""
    window = PoetoreWindow()
    qapp.clipboard().setText(copied)
    window._placement_context = PlacementContext(
        QRect(0, 0, 1920, 1080), QPoint(100, 100),
    )
    parsed = ParsedItem("Boots", "Unique", "破滅の軌跡", "メッシュブーツ", "armour", raw_text=copied)
    try:
        with patch(
            "src.poetore.ui.read_item_clipboard",
            return_value=copied,
        ), patch(
            "src.poetore.ui.parse_item_text",
            return_value=parsed,
        ), patch(
            "src.poetore.ui.english_trade_identity",
            return_value=("Mesh Boots", "Wake of Destruction"),
        ), patch.object(window, "parse_current_text") as parse, patch.object(
            window, "show_at_context",
        ) as show, patch.object(window, "search_current_item") as search:
            window._capture_item_copy()

        assert window.input_edit.toPlainText() == copied
        assert window._trade_base_type == "Mesh Boots"
        assert window._trade_item_name == "Wake of Destruction"
        parse.assert_called_once_with()
        show.assert_called_once_with(window._placement_context, activate=True)
        search.assert_called_once_with()
        assert not hasattr(window, "_normal_copy_text")
    finally:
        window.close()


def test_show_at_context_places_window_inward_from_cursor_side(qapp):
    window = PoetoreWindow()
    try:
        context = PlacementContext(QRect(100, 50, 1920, 1080), QPoint(1700, 400))
        with patch.object(window, "show"), patch.object(window, "raise_"), patch.object(
            window, "activateWindow"
        ):
            window.show_at_context(context)
        assert window.pos() == QPoint(514, 50)
    finally:
        window.close()


def test_show_at_context_does_not_focus_editable_league_field(qapp):
    window = PoetoreWindow()
    try:
        window.show_at_context(PlacementContext(QRect(0, 0, 1920, 1080), QPoint(500, 400)))
        qapp.processEvents()

        assert window.focusWidget() is window
        assert not window.trade_league_combo.hasFocus()
        assert not window.trade_league_combo.lineEdit().hasFocus()

        QTest.mouseClick(window.trade_league_combo.lineEdit(), Qt.LeftButton)
        assert window.trade_league_combo.lineEdit().hasFocus()
    finally:
        window.close()


def test_show_at_context_can_display_without_activating(qapp):
    window = PoetoreWindow()
    try:
        context = PlacementContext(QRect(0, 0, 1920, 1080), QPoint(500, 400))
        with patch.object(window, "show"), patch.object(window, "raise_"), patch.object(
            window, "activateWindow"
        ) as activate, patch.object(window, "setFocus") as set_focus:
            window.show_at_context(context, activate=False)

        activate.assert_not_called()
        set_focus.assert_not_called()
    finally:
        window.close()


def test_passive_hotkey_display_closes_only_for_outside_click(qapp, deterministic_global_cursor):
    window = PoetoreWindow()
    try:
        window.setGeometry(100, 100, 720, 1039)
        window.show()
        window._passive_hotkey_display = True
        qapp.processEvents()

        window._handle_global_mouse_press(200, 200)
        assert window.isVisible()

        window._handle_global_mouse_press(50, 50)
        assert not window.isVisible()
    finally:
        window.close()


def test_auto_hide_closes_only_after_release_and_mouse_threshold(qapp, deterministic_global_cursor):
    window = PoetoreWindow()
    try:
        window.setGeometry(1000, 100, 720, 1039)
        window.show()
        window._passive_hotkey_display = True
        window._capture_auto_hide = True
        window._auto_hide_origin = QPoint(500, 400)
        qapp.processEvents()

        window._handle_global_mouse_move(550, 400)
        assert window.isVisible()

        window.capture_hotkey_released()
        window._handle_global_mouse_move(520, 400)
        assert window.isVisible()
        window._handle_global_mouse_move(541, 400)
        assert not window.isVisible()
    finally:
        window.close()


def test_auto_hide_can_become_interactive_while_hotkey_is_held(qapp, deterministic_global_cursor):
    window = PoetoreWindow()
    try:
        window.setGeometry(100, 100, 720, 1039)
        window.show()
        window._passive_hotkey_display = True
        window._capture_auto_hide = True
        window._auto_hide_hotkey_released = False
        qapp.processEvents()

        with patch.object(window, "_stop_outside_click_listener") as stop, patch.object(
            window, "activateWindow"
        ) as activate:
            window._handle_global_mouse_move(200, 200)

        assert window._passive_hotkey_display is False
        assert window._auto_hide_interactive is True
        stop.assert_not_called()
        activate.assert_called_once_with()
    finally:
        window.close()


def test_auto_hide_interactive_returns_to_poe_after_pointer_leaves(qapp, deterministic_global_cursor):
    window = PoetoreWindow()
    try:
        window.setGeometry(100, 100, 720, 1039)
        window.show()
        window._capture_auto_hide = True
        window._auto_hide_interactive = True
        window._poe_window_hwnd = 1234
        qapp.processEvents()

        with patch.object(window, "_stop_outside_click_listener") as stop, patch.object(
            window, "_close_and_return_to_poe"
        ) as close_and_return:
            window._handle_global_mouse_move(200, 200)
            close_and_return.assert_not_called()
            window._handle_global_mouse_move(50, 50)

        stop.assert_called_once_with()
        close_and_return.assert_called_once_with()
    finally:
        window.close()


def test_auto_hide_click_inside_enters_interactive_mode(qapp, deterministic_global_cursor):
    window = PoetoreWindow()
    try:
        window.setGeometry(100, 100, 720, 1039)
        window.show()
        window._passive_hotkey_display = True
        window._capture_auto_hide = True
        qapp.processEvents()

        with patch.object(window, "activateWindow") as activate:
            window._handle_global_mouse_press(200, 200)

        assert window.isVisible()
        assert window._passive_hotkey_display is False
        assert window._auto_hide_interactive is True
        activate.assert_called_once_with()
    finally:
        window.close()


def test_auto_hide_treats_combo_popup_as_interactive_area(qapp):
    window = PoetoreWindow()
    try:
        window.show()
        window.trade_league_combo.showPopup()
        qapp.processEvents()
        popup = qapp.activePopupWidget()

        assert popup is not None
        assert window._widget_belongs_to_panel(popup)
        assert window._auto_hide_area_contains(
            popup.window().frameGeometry().center()
        )
    finally:
        window.trade_league_combo.hidePopup()
        window.close()


def test_auto_hide_uses_qt_cursor_coordinates_on_windows(qapp):
    window = PoetoreWindow()
    try:
        with patch("src.poetore.ui.sys.platform", "win32"), patch(
            "src.poetore.ui.QCursor.pos", return_value=QPoint(321, 654)
        ):
            assert window._global_cursor_point(999, 888) == QPoint(321, 654)
    finally:
        window.close()


@pytest.mark.parametrize("key,modifiers", [
    (Qt.Key_Escape, Qt.NoModifier),
    (Qt.Key_W, Qt.AltModifier),
])
def test_poetore_close_shortcuts_apply_to_child_widgets(qapp, key, modifiers):
    window = PoetoreWindow()
    try:
        window.show()
        window.input_edit.setFocus()
        QTest.keyClick(window.input_edit, key, modifiers)
        qapp.processEvents()
        assert not window.isVisible()
    finally:
        window.close()


def test_poetore_close_shortcut_returns_focus_to_captured_poe(qapp):
    window = PoetoreWindow()
    try:
        window._poe_window_hwnd = 1234
        window.show()
        window.input_edit.setFocus()
        with patch("src.poetore.ui.focus_window") as focus:
            QTest.keyClick(window.input_edit, Qt.Key_Escape)
            qapp.processEvents()

        assert not window.isVisible()
        assert window._poe_window_hwnd is None
        focus.assert_called_once_with(1234)
    finally:
        window.close()


def test_poetore_closes_when_window_loses_focus(qapp):
    window = PoetoreWindow()
    outside = QPushButton()
    try:
        window.show()
        window._close_when_focus_leaves_panel(window.input_edit, outside)
        qapp.processEvents()
        assert not window.isVisible()
    finally:
        window.close()
        outside.close()


@pytest.mark.parametrize("combo_name", [
    "trade_league_combo",
    "trade_status_combo",
    "trade_currency_combo",
    "listed_within_combo",
])
def test_poetore_combo_popups_are_treated_as_inside_panel(qapp, combo_name):
    window = PoetoreWindow()
    try:
        window.show()
        combo = getattr(window, combo_name)
        popup_view = combo.view()
        assert popup_view.window().windowType() == Qt.Popup
        assert window._widget_belongs_to_panel(popup_view)

        window._close_when_focus_leaves_panel(combo, popup_view)
        assert window.isVisible()
        window._close_when_focus_leaves_panel(popup_view, None)
        qapp.processEvents()
        assert window.isVisible()
    finally:
        window.close()


def test_poetore_title_bar_keeps_close_button(qapp):
    window = PoetoreWindow()
    try:
        assert window.trade_league_combo.parentWidget().objectName() == "poetoreTitleBar"
        assert window.trade_league_combo.width() == 338
        assert window.league_popup_button.text() == "▼"
        assert window.league_popup_button.toolTip() == "リーグ一覧を開く"
        close_buttons = [
            button for button in window.findChildren(QPushButton)
            if button.toolTip() == "閉じる" and button.text() == "×"
        ]
        assert len(close_buttons) == 1
        window.show()
        close_buttons[0].click()
        assert not window.isVisible()
    finally:
        window.close()


def test_search_condition_change_clears_stale_results_and_waits(qapp):
    window = PoetoreWindow()
    try:
        window._parsed_item = ParsedItem(
            "Rings", "Rare", "Test Ring", "Ruby Ring", "accessory", raw_text="test-ring",
        )
        window._has_searched_current_item = True
        window._show_price_result(PriceResult(
            "Mirage", "q", 1, (PriceListing(5, "chaos"),),
            web_url="https://example.invalid/trade",
        ))
        window._populate_stat_filters((
            TradeStatFilter("explicit.stat_1", "+# to maximum Life", 70, "explicit"),
        ))
        checkbox = window.mod_filter_tree.itemWidget(
            window.mod_filter_tree.topLevelItem(0), 0,
        ).findChild(QCheckBox, "modFilterCheckbox")

        checkbox.click()

        assert window._search_dirty is True
        assert window.price_list.topLevelItemCount() == 0
        assert window.price_status.text() == ""
        assert not window.trade_url_button.isEnabled()
        assert window.price_button.isEnabled()
    finally:
        window.close()


def test_search_error_replaces_searching_status_and_reenables_button(qapp):
    window = PoetoreWindow()
    try:
        window._search_generation = 3
        window.price_button.setEnabled(False)
        window.price_status.setText("検索中…")

        message = (
            "検索回数が多いため、PoE Trade APIの利用制限に達しました。"
            " 約10分後に、もう一度検索してください。"
        )
        window._show_price_error(message, 3)

        assert window.price_status.text() == message
        assert window.price_button.isEnabled()
    finally:
        window.close()


def test_enter_in_changed_mod_value_researches(qapp):
    window = PoetoreWindow()
    try:
        window.show()
        window._parsed_item = ParsedItem(
            "Rings", "Rare", "Test Ring", "Ruby Ring", "accessory", raw_text="test-ring",
        )
        window._has_searched_current_item = True
        window._populate_stat_filters((
            TradeStatFilter("explicit.stat_1", "+# to maximum Life", 70, "explicit"),
        ))
        editor = window.mod_filter_tree.itemWidget(
            window.mod_filter_tree.topLevelItem(0), 4,
        )
        editor.setFocus()
        QTest.keyClicks(editor, "8")
        assert window._search_dirty is True

        with patch.object(window, "search_current_item") as search:
            QTest.keyClick(editor, Qt.Key_Return)

        search.assert_called_once_with()
    finally:
        window.close()


def test_hovering_search_button_researches_when_conditions_changed(qapp):
    window = PoetoreWindow()
    try:
        window._parsed_item = ParsedItem(
            "Rings", "Rare", "Test Ring", "Ruby Ring", "accessory", raw_text="test-ring",
        )
        window._has_searched_current_item = True
        window._search_dirty = True

        with patch.object(window, "search_current_item") as search:
            QApplication.sendEvent(window.price_button, QEvent(QEvent.Enter))

        search.assert_called_once_with()
    finally:
        window.close()


@pytest.mark.parametrize("combo_name", [
    "trade_status_combo", "trade_currency_combo", "listed_within_combo",
])
def test_trade_option_change_researches_immediately(qapp, combo_name):
    window = PoetoreWindow()
    try:
        window._parsed_item = ParsedItem(
            "Rings", "Rare", "Test Ring", "Ruby Ring", "accessory", raw_text="test-ring",
        )
        window._has_searched_current_item = True
        combo = getattr(window, combo_name)

        with patch.object(window, "search_current_item") as search:
            combo.setCurrentIndex(1)
            qapp.processEvents()

        search.assert_called_once_with()
    finally:
        window.close()


def test_filter_kind_column_is_japanese_and_marks_foulborn_generation(qapp):
    window = PoetoreWindow()
    try:
        window._populate_stat_filters((
            TradeStatFilter("explicit.stat_1", "通常Mod", 10, "explicit"),
            TradeStatFilter(
                "explicit.stat_2", "Foulborn Mod", 10, "explicit",
                generation="foulborn",
            ),
            TradeStatFilter("pseudo.test", "疑似Mod", 10, "pseudo"),
            TradeStatFilter("pseudo.map", "マップ量", 35, "map pseudo"),
        ))
        assert [
            window.mod_filter_tree.topLevelItem(index).text(1)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ] == ["明示", "ファウルボーン", "疑似", "マップ"]
    finally:
        window.close()


def test_filter_kind_column_marks_essence_and_infamous_generations(qapp):
    window = PoetoreWindow()
    try:
        window._populate_stat_filters((
            TradeStatFilter(
                "explicit.stat_1", "Essence Mod", 10, "explicit",
                generation="essence",
            ),
            TradeStatFilter(
                "explicit.stat_2", "Infamous Mod", 10, "explicit",
                generation="infamous",
            ),
        ))
        assert [
            window.mod_filter_tree.topLevelItem(index).text(1)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ] == ["エッセンス", "悪名高い"]
    finally:
        window.close()


def test_filter_kind_column_marks_awakened_source_generations(qapp):
    window = PoetoreWindow()
    try:
        generations = (
            ("corrupted", "コラプト"),
            ("eldritch", "エルドリッチ"),
            ("synthesised", "シンセシス"),
            ("delve", "デルブ"),
            ("incursion", "インカージョン"),
            ("shaper", "シェイパー"),
        )
        window._populate_stat_filters(tuple(
            TradeStatFilter(
                f"explicit.stat_{index}", generation, 10, "explicit",
                generation=generation,
            )
            for index, (generation, _) in enumerate(generations)
        ))

        assert [
            window.mod_filter_tree.topLevelItem(index).text(1)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ] == [label for _, label in generations]
    finally:
        window.close()


def test_reported_infamous_helmet_resolves_and_is_labelled_in_real_panel(qapp):
    text = """アイテムクラス: 兜
レアリティ: レア
恐ろしい堅塁
征服者のヘルメット
--------
アーマー: 615 (augmented)
--------
装備要求:
レベル: 78
筋力: 194
--------
ソケット: W-W-W-W
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「悪名高い」 (ティア: 1) }
憤怒の固有効果による喪失が20%遅くなる
(この効果は直近にヒット受けていないか憤怒を獲得していない時の憤怒の減少にのみ影響を与える)
{ プレフィックスモッド「雲丹の」 (ティア: 2) — ライフ, 防御, アーマー }
アーマー +46(33-48)
最大ライフ +28(24-28)
{ プレフィックスモッド「頑健な」 (ティア: 5) — ライフ }
最大ライフ +72(70-84)
{ サフィックスモッド 「碩学の」 (ティア: 4) — 能力値 }
知性 +39(38-42)
--------
メモ: ~b/o 1 chaos
"""
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText(text)
        window.parse_current_text()

        rows = [
            window.mod_filter_tree.topLevelItem(index)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        infamous = next(
            row for row in rows
            if row.text(3) == "憤怒の固有効果による喪失が20%遅くなる"
        )
        assert infamous.text(1) == "悪名高い"
        assert window.mod_warning.isHidden()
    finally:
        window.close()


def test_foulborn_unique_uses_normal_name_and_enables_variable_mods_in_real_panel(qapp):
    window = PoetoreWindow()
    try:
        window._trade_base_type = "Iron Ring"
        window._trade_item_name = "Le Heup of All"
        window.input_edit.setPlainText("""アイテムクラス: 指輪
レアリティ: ユニーク
ファウルボーン 皆を繋ぐもの
鉄の指輪
--------
アイテムレベル: 83
--------
{ ユニークモッド — 能力値 }
全ての能力値 +22(10-30)
{ ユニークモッド — 元素, 耐性 }
全ての元素耐性 +29(10-30)%
{ ユニークモッド — ドロップ }
見つかるアイテムのレアリティが16(10-30)%増加する
{ ファウルボーンユニークモッド — 防御 }
グローバル防御力が16(10-30)%増加する
""")
        window.parse_current_text()

        assert window._parsed_item.name == "皆を繋ぐもの"
        assert window.item_name_label.text() == "皆を繋ぐもの"
        assert window.mod_filter_tree.topLevelItemCount() == 4
        assert all(
            window.mod_filter_tree.itemWidget(
                window.mod_filter_tree.topLevelItem(index), 0
            ).findChild(QCheckBox, "modFilterCheckbox").isChecked()
            for index in range(4)
        )
        assert "foulborn" not in {name for name, _chip in window._filter_chips}
    finally:
        window.close()


def test_japanese_vestigial_unique_shows_enabled_implicit_in_real_panel(qapp):
    window = PoetoreWindow()
    try:
        window._trade_base_type = "Riveted Boots"
        window._trade_item_name = "Ralakesh's Impatience"
        window.input_edit.setPlainText("""アイテムクラス: 靴
レアリティ: ユニーク
ララケシュの短気
痕跡 リベットブーツ
--------
アーマー: 65
エナジーシールド: 14
--------
装備要求:
レベル: 40
筋力: 35
知性: 35
--------
ソケット: B
--------
アイテムレベル: 86
--------
{ 痕跡暗黙モッド — 元素, 火, 状態異常 }
近くの敵は焦げ状態になる
(Scorch: 焦げた敵は元素耐性が-10%される)
--------
{ ユニークモッド — 元素, 冷気, 耐性 }
冷気耐性 +21(15-25)%
{ ユニークモッド — 混沌, 耐性 }
混沌耐性 +20(15-25)%
{ ユニークモッド — スピード }
移動スピードが18(15-25)%増加する
{ ユニークモッド — 物理, 状態異常 }
穢れた血を付与されることがない
{ ユニークモッド }
パワーチャージを最大数持っているとして見なされる
--------
不死者にとって、
時代と瞬間に違いはあるのか？
--------
メモ: ~b/o 10 mirror
""")
        window.parse_current_text()

        assert window._parsed_item.base_type == "リベットブーツ"
        rows = [
            window.mod_filter_tree.topLevelItem(index)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        scorch = next(row for row in rows if row.text(3) == "近くの敵は焦げ状態になる")
        checkbox = window.mod_filter_tree.itemWidget(
            scorch, 0,
        ).findChild(QCheckBox, "modFilterCheckbox")
        assert scorch.text(1) == "痕跡"
        assert checkbox.isChecked()
        assert not window.mod_warning.isVisible()
    finally:
        window.close()


def test_foulborn_fixed_replacement_mod_is_enabled_in_real_panel(qapp):
    window = PoetoreWindow()
    try:
        window._trade_base_type = "Imperial Claw"
        window._trade_item_name = "Hand of Thought and Motion"
        window.input_edit.setPlainText("""アイテムクラス: 鉤爪
レアリティ: ユニーク
ファウルボーン 思考と動作の手
帝国の鉤爪
--------
アイテムレベル: 85
--------
{ ユニークモッド — 能力値 }
知性が12(8-12)%増加する
{ ユニークモッド — 能力値 }
器用さが11(8-12)%増加する
{ ファウルボーンユニークモッド }
知性25ごとに命中力が3%増加する
""")
        window.parse_current_text()

        rows = [
            window.mod_filter_tree.topLevelItem(index)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        accuracy = next(
            row for row in rows
            if row.text(3) == "知性25ごとに命中力が3%増加する"
        )
        checkbox = window.mod_filter_tree.itemWidget(
            accuracy, 0
        ).findChild(QCheckBox, "modFilterCheckbox")

        assert accuracy.text(1) == "ファウルボーン"
        assert checkbox.isChecked()
        selected = window._selected_stat_filters()
        assert selected[rows.index(accuracy)].min_value == 3
        assert not window.mod_warning.isVisible()
    finally:
        window.close()


def test_foulborn_tulborn_fixed_number_mod_builds_valueless_trade_filter(qapp):
    window = PoetoreWindow()
    try:
        window._trade_base_type = "Opal Wand"
        window._trade_item_name = "Tulborn"
        window.input_edit.setPlainText("""アイテムクラス: ワンド
レアリティ: ユニーク
ファウルボーン トゥルボーン
オパールのワンド
--------
ワンド
物理ダメージ: 30-56
クリティカル率: 8.00%
秒間アタック回数: 1.45
--------
装備要求:
レベル: 62
知性: 212
--------
ソケット: W-W-W
--------
アイテムレベル: 85
--------
{ 暗黙モッド — ダメージ, キャスター }
スペルダメージが35(31-35)%増加する
--------
{ ユニークモッド }
付与した冷気の曝露は冷気耐性を追加で-12%させる
{ ユニークモッド — ダメージ, 元素, 冷気, キャスター }
122(120-140)から168(150-170)の冷気ダメージをスペルに追加する
{ ユニークモッド — マナ }
凍結状態の敵を倒した時に+25(20-25)のマナを獲得する
{ ファウルボーンユニークモッド }
マナを合計200消費した後にパワーチャージを1個獲得する
""")
        window.parse_current_text()

        selected = next(
            row for row in window._selected_stat_filters()
            if row.stat_id == "explicit.stat_3269060224"
        )
        assert selected.enabled
        assert selected.min_value is None
        assert selected.max_value is None

        query = build_search_query(
            window._parsed_item,
            window._trade_base_type,
            (selected,),
            trade_status="offline",
            trade_name=window._trade_item_name,
        )["query"]
        assert query["stats"][0]["filters"] == [{
            "id": "explicit.stat_3269060224",
            "value": {},
        }]
    finally:
        window.close()


def test_foulborn_xoph_uses_mutated_unique_returning_projectiles_stat(qapp):
    window = PoetoreWindow()
    try:
        window._trade_base_type = "Citadel Bow"
        window._trade_item_name = "Xoph's Inception"
        window.input_edit.setPlainText("""アイテムクラス: 弓
レアリティ: ユニーク
ファウルボーン ゾフの発端
シタデルボウ
--------
弓
物理ダメージ: 97-389 (augmented)
クリティカル率: 6.00%
秒間アタック回数: 1.25
--------
装備要求:
レベル: 58
器用さ: 185 (unmet)
--------
ソケット: W-W
--------
アイテムレベル: 85
--------
{ ユニークモッド — ダメージ, 物理, アタック }
物理ダメージが170(160-190)%増加する
{ ユニークモッド — ダメージ, 物理, 元素, 火 }
物理ダメージの20%を追加火ダメージとして獲得する
{ ユニークモッド — 元素, 火, 状態異常 }
10%の確率で敵を発火させる
(Ignite: 発火は、スキルの基礎火ダメージに基づいて火継続ダメージを与える。持続時間は4秒)
{ ユニークモッド — ライフ }
発火状態の敵を倒した時に298(200-300)のライフを獲得する
{ ユニークモッド }
矢は貫通した回数1回ごとに30から50の火ダメージを追加する
{ ファウルボーンユニークモッド }
ソケットされたジェムはレベル20投射物回帰によりサポートされる
--------
赤き火葬壇の上に我らは生まれる。

このアイテムはゾフの祝福によって変化させることができる
""")
        returning_projectiles = (
            {
                "id": "explicit.indexable_support_149", "type": "explicit",
                "text": "ソケットされたジェムはレベル#投射物回帰によりサポートされる",
            },
            {
                "id": "explicit.stat_1549219417", "type": "explicit",
                "text": "ソケットされたジェムはレベル#投射物回帰によりサポートされる",
            },
            {
                "id": "explicit.stat_52197415", "type": "explicit",
                "text": "ソケットされたジェムはレベル#投射物回帰によりサポートされる",
            },
        )
        with patch(
            "src.poetore.trade._trade_stat_entries",
            return_value=returning_projectiles,
        ):
            window.parse_current_text()

        parsed = next(
            modifier for modifier in window._parsed_item.modifiers
            if "投射物回帰" in modifier.text
        )
        assert parsed.stat_id == "explicit.stat_1549219417"
        selected = [
            row for row in window._selected_stat_filters()
            if "投射物回帰" in row.text
        ]
        assert len(selected) == 1
        assert selected[0].stat_id == "explicit.stat_1549219417"
        assert selected[0].min_value == 20

        query = build_search_query(
            window._parsed_item,
            window._trade_base_type,
            selected,
            trade_status="offline",
            trade_name=window._trade_item_name,
        )["query"]
        assert query["stats"][0]["filters"] == [{
            "id": "explicit.stat_1549219417",
            "value": {"min": 20},
        }]
    finally:
        window.close()


def test_poetore_uses_wide_poena_theme_and_hides_debug_parse_area(qapp):
    window = PoetoreWindow()
    try:
        assert window.size().width() == 840
        assert window._panel.objectName() == "poetorePanel"
        assert not window._debug_parse_area.isVisible()
        assert window.mod_filter_tree.columnCount() == 6
        assert window.mod_filter_tree.header().isHidden()
        assert window.mod_filter_tree.headerItem().text(2) == "ティア"
        assert "論理" not in [
            window.mod_filter_tree.headerItem().text(index)
            for index in range(window.mod_filter_tree.columnCount())
        ]
        assert "rgba(14, 14, 14, 246)" in window.styleSheet()
        assert "#db86ef" in window.styleSheet()
        assert "#b0ff7b" not in window.styleSheet()
    finally:
        window.close()


def test_weapon_parse_updates_awakened_style_item_header_and_filters(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""Item Class: Bows
Rarity: Rare
Storm Branch
Spine Bow
--------
Physical Damage: 38-115 (augmented)
Critical Strike Chance: 6.50%
Attacks per Second: 1.50
--------
Item Level: 83
""")
        window.parse_current_text()
        assert window.item_name_label.text() == "Spine Bow"
        assert window.item_name_label.isHidden()
        assert window.base_scope_toggle.itemText(0) == "Spine Bow"
        assert window.base_scope_toggle.itemText(1) == "すべての弓"
        assert window.weapon_property_label.text() == "武器性能・検索Mod"
        assert window.weapon_dps_label.text() == "pDPS：137.7（品質20%換算）"
        assert not window.weapon_dps_label.isHidden()
        filter_ids = {
            window.mod_filter_tree.topLevelItem(index).data(0, Qt.UserRole)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        }
        assert "property.physical_dps" in filter_ids
        assert "property.aps" in filter_ids
        assert "property.crit" in filter_ids
    finally:
        window.close()


def test_weapon_header_shows_total_pdps_and_edps_but_hides_summary_for_non_weapon(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: 両手剣
レアリティ: レア
混沌の刃
略奪者の剣
--------
品質: +20% (augmented)
物理ダメージ: 100-200 (augmented)
元素ダメージ: 20-40 (augmented)
秒間アタック回数: 1.50 (augmented)
--------
アイテムレベル: 84
""")
        window.parse_current_text()
        assert window.weapon_dps_label.text() == (
            "合計DPS：270.0（pDPS 225.0 / eDPS 45.0、pDPSは品質20%換算）"
        )
        assert not window.weapon_dps_label.isHidden()

        elemental = parse_item_text("""Item Class: Wands
Rarity: Rare
Elemental Wand
Imbued Wand
--------
Elemental Damage: 20-40, 30-60, 10-20
Attacks per Second: 1.50
--------
Item Level: 84
""")
        window._update_item_header(elemental)
        assert window.weapon_dps_label.text() == "eDPS：135.0"
        assert not window.weapon_dps_label.isHidden()

        armour = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Armour: 1000
--------
Item Level: 84
""")
        window._update_item_header(armour)
        assert window.weapon_dps_label.text() == ""
        assert window.weapon_dps_label.isHidden()
    finally:
        window.close()


def test_poetore_league_choices_include_sc_hc_and_persist(qapp):
    config = {"poetore": {"league": "Hardcore Mirage"}}
    saved = Mock()
    window = PoetoreWindow(app_config=config, save_config=saved)
    try:
        window._show_trade_leagues((
            TradeLeague("Standard"),
            TradeLeague("Mirage"),
            TradeLeague("Hardcore Mirage", hardcore=True),
        ))
        assert window.trade_league_combo.itemText(0) == "自動（現行SC: Mirage）"
        assert window.trade_league_combo.currentData() == "Hardcore Mirage"
        assert "（HC）" in window.trade_league_combo.currentText()

        window.trade_league_combo.setCurrentIndex(0)
        assert config["poetore"]["league"] == "auto"
        assert window._selected_trade_league() == "Mirage"
        assert saved.called

        window.trade_league_combo.setEditText("My League (PL99999)")
        window._persist_trade_league()
        assert config["poetore"]["league"] == "My League (PL99999)"
        assert window._selected_trade_league() == "My League (PL99999)"
    finally:
        window.close()


def test_poe2_window_starts_with_four_leagues_and_reported_mageblood_is_resolved(qapp):
    config = {"poe_version": "poe2", "poetore": {"league_poe2": "auto"}}
    window = PoetoreWindow(app_config=config)
    try:
        assert window.trade_league_combo.itemText(0) == "自動（現行SC: Runes of Aldur）"
        assert [
            window.trade_league_combo.itemData(index)
            for index in range(window.trade_league_combo.count())
        ] == ["auto", "Runes of Aldur", "HC Runes of Aldur", "Standard", "Hardcore"]

        text = (Path(__file__).parent / "fixtures" / "poe2" / "mageblood_ja.txt").read_text(
            encoding="utf-8"
        )
        window.input_edit.setPlainText(text)
        window.parse_current_text()

        assert window._parsed_item.name == "Mageblood"
        assert window.mod_filter_tree.topLevelItemCount() == 7
        assert window.mod_warning.isHidden()
        selected = window._selected_stat_filters()
        assert len(selected) == 7
        assert [row.stat_id for row in selected if "264262054" in row.stat_id] == [
            "explicit.stat_264262054|3", "explicit.stat_264262054|11",
            "explicit.stat_264262054|4", "explicit.stat_264262054|8",
        ]
    finally:
        window.close()


def test_reported_poe2_rare_gloves_show_chaos_resistance_without_warning(qapp):
    window = PoetoreWindow(app_config={"poe_version": "poe2"})
    try:
        text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_gloves_ja.txt").read_text(
            encoding="utf-8"
        )
        window.input_edit.setPlainText(text)
        window.parse_current_text()

        assert window.mod_filter_tree.topLevelItemCount() == 7
        assert window.mod_warning.isHidden()
        selected = window._selected_stat_filters()
        chaos = next(row for row in selected if row.stat_id == "explicit.stat_2923486259")
        assert chaos.text == "混沌耐性 +15(12-15)%"
        assert chaos.min_value == 15
    finally:
        window.close()


def test_reported_poe2_rare_body_armour_shows_local_evasion_filter(qapp):
    window = PoetoreWindow(app_config={"poe_version": "poe2"})
    try:
        text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_body_armour_ja.txt").read_text(
            encoding="utf-8"
        )
        window.input_edit.setPlainText(text)
        window.parse_current_text()

        selected = window._selected_stat_filters()
        evasion = [row for row in selected if row.text.startswith("回避力が")]
        assert [(row.stat_id, row.min_value) for row in evasion] == [
            ("explicit.stat_124859000", 105),
            ("explicit.stat_124859000", 40),
        ]
        assert all(not row.alternative_stat_ids for row in evasion)
        assert window.mod_warning.isHidden()
    finally:
        window.close()


def test_poetore_search_range_is_persisted(qapp):
    config = {"poetore": {"search_stat_range": 20}}
    saved = Mock()
    window = PoetoreWindow(app_config=config, save_config=saved)
    try:
        assert window.search_range_combo.currentData() == 20
        assert window.search_range_combo.currentText() == "Mod数値：-20%まで許容"
        assert "読取値100・-10%まで許容 → 最小値90で検索" in (
            window.search_range_combo.toolTip()
        )
        window.search_range_combo.setCurrentIndex(
            window.search_range_combo.findData(5)
        )
        assert config["poetore"]["search_stat_range"] == 5
        assert saved.called
    finally:
        window.close()


def test_search_range_change_keeps_checkboxes_but_recalculates_edited_values(qapp):
    window = PoetoreWindow(
        app_config={"poetore": {"search_stat_range": 0}}
    )
    try:
        original = TradeStatFilter(
            "explicit.stat_fire_resistance", "+40% to Fire Resistance", 40,
            "explicit", enabled=True, read_value=40,
            ref="+#% to Fire Resistance",
        )
        window._populate_stat_filters((original,))
        checkbox = window.mod_filter_tree.itemWidget(
            window.mod_filter_tree.topLevelItem(0), _MOD_COLUMN_CHECK
        ).findChild(QCheckBox, "modFilterCheckbox")
        minimum = window.mod_filter_tree.itemWidget(
            window.mod_filter_tree.topLevelItem(0), _MOD_COLUMN_MIN
        )
        checkbox.setChecked(False)
        minimum.setText("30")

        window._parsed_item = ParsedItem(
            "Rings", "Rare", "Test Ring", "Ruby Ring", "accessory.ring"
        )
        window._resolved_trade_filters = Mock(return_value=(
            replace(original, min_value=36),
        ))
        window.search_range_combo.setCurrentIndex(
            window.search_range_combo.findData(10)
        )

        selected = window._selected_stat_filters()[0]
        assert not selected.enabled
        assert selected.min_value == 36
        window._resolved_trade_filters.assert_called_once_with(
            window._parsed_item, PRESET_FINISHED
        )
    finally:
        window.close()


def test_hidden_candidates_and_pseudo_sources_can_be_toggled(qapp):
    window = PoetoreWindow()
    try:
        assert "価格比較に影響しないため" in window.hidden_mods_toggle.toolTip()
        assert "影響しにくい" not in window.hidden_mods_toggle.toolTip()
        assert "Pseudo" not in window.mod_sources_toggle.toolTip()
        assert "複数の数値をまとめた検索条件" in (
            window.mod_sources_toggle.toolTip()
        )
        assert "計算に使われた元のMod文章" in (
            window.mod_sources_toggle.toolTip()
        )
        window._populate_stat_filters((
            TradeStatFilter(
                "pseudo.life", "最大ライフ合計", 90, "pseudo", True,
                read_value=100,
                source_texts=("最大ライフ +70", "筋力 +60"),
                source_contributions=(70, 30),
                source_headings=("プレフィックス (T1)", "サフィックス (T2)"),
            ),
            TradeStatFilter(
                "explicit.fixed", "固定Mod", 10, "explicit", False,
                hidden_reason="ユニーク固定値のため初期非表示",
            ),
        ))
        normal = window.mod_filter_tree.topLevelItem(0)
        hidden = window.mod_filter_tree.topLevelItem(1)
        assert not normal.isHidden()
        assert hidden.isHidden()
        assert normal.childCount() == 1
        source_row = normal.child(0)
        source_widget = window.mod_filter_tree.itemWidget(source_row, 0)
        labels = [label.text() for label in source_widget.findChildren(QLabel)]
        assert "プレフィックス (T1)" in labels
        assert "最大ライフ +70" in labels
        assert "サフィックス (T2)" in labels
        assert "筋力 +60" in labels
        assert "+70" not in labels
        assert "+30" not in labels
        assert not any("pseudo" in text.casefold() for text in labels)
        assert not any("主要" in text for text in labels)
        assert not normal.isExpanded()

        window.hidden_mods_toggle.setChecked(True)
        assert normal.isHidden()
        assert not hidden.isHidden()

        window.mod_sources_toggle.setChecked(True)
        assert normal.isExpanded()
        window.mod_sources_toggle.setChecked(False)
        assert not normal.isExpanded()
    finally:
        window.close()


def test_auto_mod_layout_expands_until_available_height():
    assert _auto_mod_layout_sizes(
        profile_height=900,
        profile_mod_height=250,
        profile_price_height=300,
        minimum_price_height=120,
        content_height=430,
        available_height=1200,
        minimum_height=620,
    ) == (430, 300, 1080)
    assert _auto_mod_layout_sizes(
        profile_height=900,
        profile_mod_height=250,
        profile_price_height=300,
        minimum_price_height=120,
        content_height=600,
        available_height=1000,
        minimum_height=620,
    ) == (514, 120, 984)


def test_auto_mod_layout_borrows_height_from_price_results_on_fhd():
    assert _auto_mod_layout_sizes(
        profile_height=1039,
        profile_mod_height=250,
        profile_price_height=434,
        minimum_price_height=120,
        content_height=330,
        available_height=1040,
        minimum_height=620,
    ) == (330, 339, 1024)


def test_auto_mod_layout_keeps_related_items_budget_on_fhd():
    assert _auto_mod_layout_sizes(
        profile_height=1039,
        profile_mod_height=250,
        profile_price_height=254,
        minimum_price_height=120,
        content_height=330,
        available_height=1040,
        minimum_height=620,
    ) == (330, 159, 1024)

def test_checked_hidden_unique_mutation_is_sent_as_exact_filter(qapp):
    window = PoetoreWindow()
    try:
        window._trade_base_type = "Titanium Spirit Shield"
        window._trade_item_name = "Rathpith Globe"
        window.input_edit.setPlainText("""アイテムクラス: 盾
レアリティ: ユニーク
ラスピスの球体
チタンスピリットシールド
--------
アイテムレベル: 83
--------
{ ユニークモッド — ダメージ, キャスター }
プレイヤーの最大ライフ100ごとにスペルダメージが4(3)%増加する
--------
コラプト状態
""")
        window.parse_current_text()
        window.hidden_mods_toggle.setChecked(True)

        target = next(
            window.mod_filter_tree.topLevelItem(index)
            for index in range(window.mod_filter_tree.topLevelItemCount())
            if window.mod_filter_tree.topLevelItem(index).data(
                0, Qt.UserRole + 4
            ).stat_id == "explicit.stat_3491815140"
        )
        checkbox = window.mod_filter_tree.itemWidget(
            target, 0
        ).findChild(QCheckBox, "modFilterCheckbox")
        checkbox.setChecked(True)

        selected = tuple(
            row for row in window._selected_stat_filters() if row.enabled
        )
        spell_damage = next(
            row for row in selected
            if row.stat_id == "explicit.stat_3491815140"
        )
        assert spell_damage.min_value == 4
        assert spell_damage.max_value == 4

        query = build_search_query(
            window._parsed_item, "Titanium Spirit Shield", selected,
            trade_name="Rathpith Globe",
        )["query"]
        assert query["stats"][0]["filters"] == [{
            "id": "explicit.stat_3491815140",
            "value": {"min": 4, "max": 4},
        }]
    finally:
        window.close()

def test_search_keeps_checked_hidden_unique_mutation_visible(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: 鎧
レアリティ: ユニーク
カオムの心臓
栄光のプレート
--------
品質: +20% (augmented)
アーマー: 944 (augmented)
--------
装備要求:
レベル: 68
筋力: 191
--------
アイテムレベル: 80
--------
{ ユニークモッド — ライフ }
最大ライフ +1080(1000)
{ ユニークモッド }
ソケットを持たない
--------
コラプト状態
""")
        window.parse_current_text()
        window._populate_stat_filters((
            TradeStatFilter(
                "explicit.normal", "通常候補", 10, "explicit", False,
            ),
            TradeStatFilter(
                "explicit.hidden", "最大ライフ +1080(1000)", 1080,
                "explicit", False, max_value=1080,
                hidden_reason="ユニーク固定値のため初期非表示",
            ),
        ))
        window.hidden_mods_toggle.setChecked(True)
        hidden = window.mod_filter_tree.topLevelItem(1)
        checkbox = window.mod_filter_tree.itemWidget(
            hidden, 0
        ).findChild(QCheckBox, "modFilterCheckbox")
        checkbox.setChecked(True)

        result = PriceResult("Standard", "qid", 0, ())
        with patch("src.poetore.ui.search_prices", return_value=result) as search:
            window.search_current_item()
            for _ in range(50):
                qapp.processEvents()
                if search.called:
                    break
                QTest.qWait(10)

        assert search.called
        assert not window.hidden_mods_toggle.isChecked()
        assert window.hidden_mods_toggle.text() == "隠し候補を表示"
        assert not window.mod_filter_tree.topLevelItem(0).isHidden()
        assert not window.mod_filter_tree.topLevelItem(1).isHidden()
        sent = search.call_args.kwargs["stat_filters"]
        assert any(
            row.stat_id == "explicit.hidden"
            and row.enabled
            and row.min_value == 1080
            and row.max_value == 1080
            for row in sent
        )
        checkbox.setChecked(False)
        assert window.mod_filter_tree.topLevelItem(1).isHidden()
    finally:
        window.close()


def test_poetore_private_league_is_kept_and_ended_public_league_falls_back(qapp):
    private = PoetoreWindow(app_config={"poetore": {"league": "My League (PL12345)"}})
    ended = PoetoreWindow(app_config={"poetore": {"league": "Old Challenge"}})
    leagues = (TradeLeague("Standard"), TradeLeague("Mirage"))
    try:
        private._show_trade_leagues(leagues)
        assert private._selected_trade_league() == "My League (PL12345)"

        ended._show_trade_leagues(leagues)
        assert ended.trade_league_combo.currentData() == "auto"
        assert ended._selected_trade_league() == "Mirage"
    finally:
        private.close()
        ended.close()


def test_price_result_is_rendered_in_japanese(qapp):
    window = PoetoreWindow()
    window._parsed_item = ParsedItem(
        "剣", "レア", "Doom Sever", "Reaver Sword", "weapon", item_level=86,
    )
    window.item_level_tag.show()
    window._set_item_level_filter_enabled(True)
    window.item_level_edit.setText("86")
    window._show_price_result(PriceResult("Mirage", "q", 42, (
        PriceListing(4, "chaos", "seller1", "Doom Sever", "Reaver Sword",
                     "2026-07-22T09:21:00Z", 86),
        PriceListing(6, "chaos", "seller2", "Foe Bite", "Reaver Sword",
                     "2026-07-22T09:22:00Z", 87),
    )))
    assert "Mirage" in window.price_status.text()
    assert "候補42件" in window.price_status.text()
    assert "中央値 5 chaos" in window.price_status.text()
    assert window.price_list.topLevelItemCount() == 2
    assert [window.price_list.headerItem().text(i) for i in range(4)] == [
        "価格", "ilvl", "出品日時", "取引方式",
    ]
    assert window.price_list.topLevelItem(0).text(0) == "4 chaos"
    assert window.price_list.topLevelItem(0).text(1) == "86"
    assert window.price_list.topLevelItem(0).text(2).endswith("前")
    assert window.price_list.topLevelItem(0).text(3) == "対面"
    window.close()


def test_partial_price_result_is_shown_without_finishing_search(qapp):
    window = PoetoreWindow()
    window._search_generation = 7
    window.price_button.setEnabled(False)
    window.trade_url_button.setEnabled(False)
    result = PriceResult("Mirage", "q", 42, (
        PriceListing(4, "chaos", "seller1", "", "Reaver Sword", ""),
    ))
    try:
        window._search_partially_completed(result, 7)

        assert "取得中" in window.price_status.text()
        assert window.price_list.topLevelItemCount() == 1
        assert not window.price_button.isEnabled()
        assert not window.trade_url_button.isEnabled()
    finally:
        window.close()


def test_relative_listing_time_is_shown_without_online_status(qapp):
    now = datetime(2026, 7, 22, 9, 24, tzinfo=timezone.utc)
    assert PoetoreWindow._relative_listing_time("2026-07-22T09:21:00Z", now) == "3分前"
    assert PoetoreWindow._relative_listing_time("2026-07-22T07:24:00+00:00", now) == "2時間前"
    assert PoetoreWindow._relative_listing_time("", now) == "-"


def test_price_result_shows_pricing_method_in_rightmost_column(qapp):
    window = PoetoreWindow()
    try:
        window._show_price_result(PriceResult("Mirage", "q", 3, (
            PriceListing(4, "chaos", pricing_method="face_to_face"),
            PriceListing(5, "chaos", pricing_method="instant"),
            PriceListing(0, "", pricing_method="unpriced"),
        )))
        last_column = window.price_list.columnCount() - 1
        assert window.price_list.headerItem().text(last_column) == "取引方式"
        assert [
            window.price_list.topLevelItem(index).text(last_column)
            for index in range(3)
        ] == ["対面", "インスタント", "値段なし"]
        assert window.price_list.topLevelItem(2).text(0) == "値段なし"
        assert "中央値 4.5 chaos" in window.price_status.text()
    finally:
        window.close()


def test_gem_result_adds_gem_level_and_quality_columns(qapp):
    window = PoetoreWindow()
    window._parsed_item = ParsedItem("ジェム", "ジェム", "Arc", "Arc", "gem")
    try:
        window._show_price_result(PriceResult("Mirage", "q", 1, (
            PriceListing(2, "chaos", indexed="2026-07-22T09:21:00Z", gem_level=20, quality=23),
        )))
        assert [window.price_list.headerItem().text(i) for i in range(5)] == [
            "価格", "ジェムLv", "品質", "出品日時", "取引方式",
        ]
        assert window.price_list.topLevelItem(0).text(1) == "20"
        assert window.price_list.topLevelItem(0).text(2) == "23"
    finally:
        window.close()


def test_japanese_trade_url_button_opens_result_url(qapp):
    window = PoetoreWindow()
    url = "https://jp.pathofexile.com/trade/search/Standard?q=test"
    try:
        window._show_price_result(PriceResult(
            "Standard", "q", 0, (), web_url=url, cached=True,
        ))
        assert window.trade_url_button.isEnabled()
        assert "キャッシュ" in window.price_status.text()
        with patch("src.poetore.ui.QDesktopServices.openUrl") as opened:
            window._open_trade_url()
        assert opened.call_args.args[0].toString() == url
    finally:
        window.close()


def test_price_result_columns_reset_when_switching_from_gem_to_weapon(qapp):
    window = PoetoreWindow()
    try:
        gem = parse_item_text("""アイテムクラス: スキルジェム
レアリティ: ジェム
Arc
--------
レベル: 20
品質: +20%
""")
        window._parsed_item = gem
        gem_listing = PriceListing(
            1, "chaos", "", "Arc", "Arc",
            "2026-07-23T12:00:00Z", 1, 20, 20, None,
        )
        window._show_price_result(PriceResult(
            "Standard", "gem", 1, (gem_listing,),
        ))
        assert [
            window.price_list.headerItem().text(index)
            for index in range(window.price_list.columnCount())
        ] == ["価格", "ジェムLv", "品質", "出品日時", "取引方式"]

        weapon = parse_item_text("""アイテムクラス: ワンド
レアリティ: レア
Test Wand
Imbued Wand
--------
アイテムレベル: 84
        """)
        window._parsed_item = weapon
        window._configure_item_level(weapon)
        weapon_listing = PriceListing(
            3, "chaos", "", "Test Wand", "Imbued Wand",
            "2026-07-23T12:00:00Z", 84, None, None, None,
        )
        window._show_price_result(PriceResult(
            "Standard", "weapon", 1, (weapon_listing,),
        ))
        assert window.price_list.columnCount() == 4
        assert [
            window.price_list.headerItem().text(index)
            for index in range(window.price_list.columnCount())
        ] == ["価格", "ilvl", "出品日時", "取引方式"]
    finally:
        window.close()


def test_mod_filters_are_checkable_and_minimum_is_editable(qapp):
    window = PoetoreWindow()
    window._populate_stat_filters((TradeStatFilter(
        "explicit.stat_1", "命中力 +55", 55, "prefix", False,
    ),))
    row = window.mod_filter_tree.topLevelItem(0)
    checkbox = window.mod_filter_tree.itemWidget(row, 0).findChild(
        QCheckBox, "modFilterCheckbox"
    )
    assert checkbox is not None
    assert not checkbox.isChecked()
    assert "#4488ff" in checkbox.styleSheet()
    editor = window.mod_filter_tree.itemWidget(row, 4)
    assert editor.text() == "55"
    checkbox.click()
    editor.setText("50")
    assert window._selected_stat_filters() == (
        TradeStatFilter("explicit.stat_1", "命中力 +55", 50, "prefix", True),
    )
    window.close()


def test_mod_filter_check_and_condition_columns_fit_without_clipping(qapp):
    window = PoetoreWindow()
    try:
        assert window.mod_filter_tree.columnWidth(0) == 47
        assert window.mod_filter_tree.columnWidth(3) == 404
    finally:
        window.close()


def test_mod_filter_minimum_and_maximum_editors_use_narrow_width(qapp):
    window = PoetoreWindow()
    window._populate_stat_filters((TradeStatFilter(
        "explicit.stat_1", "命中力 +55", 55, "prefix", False, max_value=100,
    ),))
    try:
        row = window.mod_filter_tree.topLevelItem(0)
        assert window.mod_filter_tree.itemWidget(row, 4).width() == 84
        assert window.mod_filter_tree.itemWidget(row, 5).width() == 84
    finally:
        window.close()


def test_mod_text_click_toggles_without_selecting_or_moving_value_editors(qapp):
    window = PoetoreWindow()
    window._populate_stat_filters((TradeStatFilter(
        "explicit.stat_1", "命中力 +55", 55, "prefix", False, max_value=100,
    ),))
    try:
        window.show()
        qapp.processEvents()
        row = window.mod_filter_tree.topLevelItem(0)
        checkbox = window.mod_filter_tree.itemWidget(row, 0).findChild(
            QCheckBox, "modFilterCheckbox"
        )
        minimum_editor = window.mod_filter_tree.itemWidget(row, 4)
        maximum_editor = window.mod_filter_tree.itemWidget(row, 5)
        before = (minimum_editor.geometry(), maximum_editor.geometry())

        window._toggle_mod_condition_from_text(row, 3)
        qapp.processEvents()

        assert checkbox.isChecked()
        assert not row.isSelected()
        assert (minimum_editor.geometry(), maximum_editor.geometry()) == before
        row_rect = window.mod_filter_tree.visualItemRect(row)
        assert row_rect.height() > minimum_editor.height()
        assert minimum_editor.geometry().top() > 0
        assert minimum_editor.geometry().bottom() < row_rect.height() - 1
        assert maximum_editor.geometry().top() > 0
        assert maximum_editor.geometry().bottom() < row_rect.height() - 1
    finally:
        window.close()


def test_watchers_eye_shows_all_three_variable_aura_mods_in_actual_ui(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: ジュエル
レアリティ: ユニーク
ウォッチャーズアイ
プリズマティックジュエル
--------
個数制限: 1
--------
アイテムレベル: 86
--------
{ ユニークモッド — ライフ }
最大ライフが6(4-6)%増加する
{ ユニークモッド — 防御, エナジーシールド }
最大エナジーシールドが4(4-6)%増加する
{ ユニークモッド — マナ }
最大マナが6(4-6)%増加する
{ ユニークモッド — キャスター, 呪い }
ヘイストの影響を受けている時にテンポラルチェーンの影響を受けない — スケールできない値
(Unaffected: 影響を受けない場合でも、デバフがかけられるが、それによる効果は表れない)
{ ユニークモッド — アタック, スピード }
プレシジョンの影響を受けている時にアタックスピードが15(10-15)%増加する
{ ユニークモッド }
デターミネーションの影響を受けている時にアタックブロック率 +7(5-8)%
--------
一人ずつ、彼らは理解することも、
ましてや倒すことも期待できぬ生き物の前に立ちふさがり、
そして一人ずつ、彼らはそれの一部となった。
--------
パッシブツリーで割り当てられたジュエルソケットにはめる。右クリックしてソケットから取り外すことができる。""")
        # 実機のAlt+Dでは表示名は通常コピーの日本語へ戻し、Trade検索名は
        # 詳細コピーから得た英語名を別途保持する。
        window._trade_item_name = "Watcher's Eye"
        window._trade_base_type = "Prismatic Jewel"
        window.parse_current_text()

        rows = [
            window.mod_filter_tree.topLevelItem(index)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        assert len(rows) == 6
        by_stat_id = {row.data(0, Qt.UserRole): row for row in rows}
        haste = by_stat_id["explicit.stat_2806391472"]
        assert haste.text(3) == (
            "ヘイストの影響を受けている時にテンポラルチェーンの影響を受けない"
        )
        haste_checkbox = window.mod_filter_tree.itemWidget(
            haste, 0
        ).findChild(QCheckBox, "modFilterCheckbox")
        assert haste_checkbox is not None
    finally:
        window.close()


@pytest.mark.parametrize(("group_type", "group_key", "group_min"), [
    ("and", None, None),
    ("not", "valdo-lethal", None),
    ("count", "either", 1),
])
def test_mod_filter_ui_preserves_internal_logic_without_user_logic_column(
    qapp, group_type, group_key, group_min,
):
    window = PoetoreWindow()
    try:
        source = TradeStatFilter(
            "explicit.stat_1", "内部論理Mod", 10, "explicit", True,
            group_type=group_type, group_key=group_key, group_min=group_min,
        )
        window._populate_stat_filters((source,))
        row = window.mod_filter_tree.topLevelItem(0)
        assert window.mod_filter_tree.itemWidget(row, 7) is None
        selected = window._selected_stat_filters()[0]
        assert selected.group_type == group_type
        assert selected.group_key == group_key
        assert selected.group_min == group_min
    finally:
        window.close()


def test_mod_filter_ui_shows_reason_tier_range_generation_and_matching(qapp):
    window = PoetoreWindow()
    try:
        source = TradeStatFilter(
            "explicit.stat_1", "最大ライフ +100", 90, "prefix", True,
            ref="+# to maximum Life", confidence=1.0, read_value=100,
            tier=1, roll_min=90, roll_max=100, affix="prefix",
            generation="fractured", selection_reason="ベースアイテム向けT1 Mod",
        )
        window._populate_stat_filters((source,))
        row = window.mod_filter_tree.topLevelItem(0)
        assert row.text(2) == "T1"
        detail = row.toolTip(3)
        assert "ベースアイテム向けT1 Mod" in detail
        assert "読取 100" in detail
        assert "T1" in detail
        assert "範囲 90–100" in detail
        assert "プレフィックス" in detail
        assert "フラクチャー" in detail
        assert "一致 100%" in detail

        editor = window.mod_filter_tree.itemWidget(row, 4)
        editor.setText("95")
        selected = window._selected_stat_filters()[0]
        assert selected.min_value == 95
        assert selected.selection_reason == source.selection_reason
        assert selected.tier == 1
    finally:
        window.close()


def test_unique_variable_roll_slider_drag_updates_minimum_and_enables_filter(qapp):
    window = PoetoreWindow()
    try:
        window._parsed_item = ParsedItem(
            "Amulets", "Unique", "The Example", "Gold Amulet", "accessory",
        )
        source = TradeStatFilter(
            "explicit.life", "+40(30-50) to maximum Life", 38, "explicit", False,
            read_value=40, roll_min=30, roll_max=50, better=1,
        )
        window._populate_stat_filters((source,))
        window.show()
        qapp.processEvents()
        row = window.mod_filter_tree.topLevelItem(0)
        slider = window.mod_filter_tree.itemWidget(row, 3).findChild(
            _UniqueRollSlider, "uniqueRollSlider"
        )
        assert slider is not None
        text_widget = window.mod_filter_tree.itemWidget(row, 3)
        assert row.text(3) == source.text
        assert text_widget.palette().color(QPalette.Window).name() == "#121212"
        assert "QWidget#uniqueRollCell" in text_widget.styleSheet()
        labels = text_widget.findChildren(QLabel)
        assert len(labels) == 1
        assert row.sizeHint(3).height() == 72
        rendered_cell = text_widget.grab().toImage()
        assert {
            rendered_cell.pixelColor(x, y).name()
            for x, y in (
                (0, 0),
                (rendered_cell.width() - 1, 0),
                (0, rendered_cell.height() - 1),
                (rendered_cell.width() - 1, rendered_cell.height() - 1),
            )
        } == {"#121212"}

        drag_x = slider.width() * 3 // 4
        expected = slider._value_at(drag_x)
        QTest.mousePress(slider, Qt.LeftButton, pos=QPoint(drag_x, 12))
        assert slider._preview == expected
        QTest.mouseMove(slider, QPoint(drag_x, 12))
        QTest.mouseRelease(slider, Qt.LeftButton, pos=QPoint(drag_x, 12))
        assert slider._preview is None

        minimum_editor = window.mod_filter_tree.itemWidget(row, 4)
        maximum_editor = window.mod_filter_tree.itemWidget(row, 5)
        checkbox = window.mod_filter_tree.itemWidget(row, 0).findChild(
            QCheckBox, "modFilterCheckbox"
        )
        assert minimum_editor.text() == f"{expected:g}"
        assert maximum_editor.text() == ""
        assert checkbox.isChecked()
        selected = window._selected_stat_filters()[0]
        assert selected.enabled is True
        assert selected.min_value == expected
        assert selected.max_value is None
        query = build_search_query(
            window._parsed_item, "Gold Amulet", (selected,),
            trade_name="The Example",
        )["query"]
        assert query["stats"][0]["filters"] == [{
            "id": "explicit.life", "value": {"min": expected},
        }]
    finally:
        window.close()


def test_unique_roll_slider_tracks_numeric_input_and_awakened_decimal_precision(qapp):
    slider = _UniqueRollSlider((1.0, 2.0), 1.5, 1, True)
    slider.resize(300, 24)
    assert slider._value_at(100) == 1.33

    window = PoetoreWindow()
    try:
        window._parsed_item = ParsedItem(
            "Jewels", "Unique", "Decimal Example", "Jewel", "jewel",
        )
        source = TradeStatFilter(
            "explicit.speed", "Speed", 1.4, "explicit", True,
            read_value=1.5, roll_min=1.0, roll_max=2.0, better=1,
            decimal=True,
        )
        window._populate_stat_filters((source,))
        row = window.mod_filter_tree.topLevelItem(0)
        roll_slider = window.mod_filter_tree.itemWidget(row, 3).findChild(
            _UniqueRollSlider, "uniqueRollSlider"
        )
        window.mod_filter_tree.itemWidget(row, 4).setText("1.75")
        assert roll_slider.searchValues() == (1.75, None)
    finally:
        window.close()


def test_unique_lower_is_better_slider_updates_maximum(qapp):
    window = PoetoreWindow()
    try:
        window._parsed_item = ParsedItem(
            "Rings", "Unique", "Lower Example", "Gold Ring", "accessory",
        )
        source = TradeStatFilter(
            "explicit.penalty", "Penalty", None, "explicit", False,
            max_value=18, read_value=15, roll_min=10, roll_max=20, better=-1,
        )
        window._populate_stat_filters((source,))
        window.show()
        qapp.processEvents()
        row = window.mod_filter_tree.topLevelItem(0)
        slider = window.mod_filter_tree.itemWidget(row, 3).findChild(
            _UniqueRollSlider, "uniqueRollSlider"
        )
        drag_x = slider.width() // 4
        expected = slider._value_at(drag_x)
        QTest.mouseClick(slider, Qt.LeftButton, pos=QPoint(drag_x, 12))

        assert window.mod_filter_tree.itemWidget(row, 4).text() == ""
        assert window.mod_filter_tree.itemWidget(row, 5).text() == f"{expected:g}"
        selected = window._selected_stat_filters()[0]
        assert selected.enabled is True
        assert selected.min_value is None
        assert selected.max_value == expected
    finally:
        window.close()


def test_mod_text_click_toggles_condition_but_value_editor_does_not(qapp):
    window = PoetoreWindow()
    try:
        source = TradeStatFilter(
            "explicit.stat_1", "+50 to maximum Life", 45,
            "explicit", False,
        )
        window._populate_stat_filters((source,))
        window.show()
        qapp.processEvents()

        row = window.mod_filter_tree.topLevelItem(0)
        checkbox = window.mod_filter_tree.itemWidget(
            row, 0
        ).findChild(QCheckBox, "modFilterCheckbox")
        row_rect = window.mod_filter_tree.visualItemRect(row)
        text_x = (
            window.mod_filter_tree.header().sectionViewportPosition(
                _MOD_COLUMN_TEXT
            ) + 12
        )

        QTest.mouseClick(
            window.mod_filter_tree.viewport(), Qt.LeftButton,
            pos=QPoint(text_x, row_rect.center().y()),
        )
        assert checkbox.isChecked()

        minimum_editor = window.mod_filter_tree.itemWidget(
            row, _MOD_COLUMN_MIN
        )
        QTest.mouseClick(minimum_editor, Qt.LeftButton)
        assert checkbox.isChecked()
    finally:
        window.close()


def test_unique_roll_mod_text_click_toggles_condition_without_touching_slider(qapp):
    window = PoetoreWindow()
    try:
        window._parsed_item = ParsedItem(
            "Amulets", "Unique", "The Example", "Gold Amulet", "accessory",
        )
        source = TradeStatFilter(
            "explicit.life", "+40(30-50) to maximum Life", 38,
            "explicit", True, read_value=40, roll_min=30, roll_max=50,
            better=1,
        )
        window._populate_stat_filters((source,))
        window.show()
        qapp.processEvents()

        row = window.mod_filter_tree.topLevelItem(0)
        text_widget = window.mod_filter_tree.itemWidget(row, _MOD_COLUMN_TEXT)
        text_label = text_widget.findChild(QLabel)
        checkbox = window.mod_filter_tree.itemWidget(
            row, _MOD_COLUMN_CHECK
        ).findChild(QCheckBox, "modFilterCheckbox")
        slider = text_widget.findChild(
            _UniqueRollSlider, "uniqueRollSlider"
        )
        before_values = slider.searchValues()

        QTest.mouseClick(text_label, Qt.LeftButton)

        assert not checkbox.isChecked()
        assert slider.searchValues() == before_values
    finally:
        window.close()


@pytest.mark.parametrize("changes", [
    {"roll_min": 10, "roll_max": 10},
    {"better": 0},
    {"option_value": 1},
])
def test_unique_roll_slider_is_hidden_for_unsupported_mods(qapp, changes):
    window = PoetoreWindow()
    try:
        window._parsed_item = ParsedItem(
            "Rings", "Unique", "Fixed Example", "Gold Ring", "accessory",
        )
        values = {
            "roll_min": 10, "roll_max": 20, "better": 1, "option_value": None,
        }
        values.update(changes)
        source = TradeStatFilter(
            "explicit.stat_1", "Example", 10, "explicit", True,
            read_value=15, **values,
        )
        window._populate_stat_filters((source,))
        row = window.mod_filter_tree.topLevelItem(0)
        text_widget = window.mod_filter_tree.itemWidget(row, 3)
        assert text_widget is None or text_widget.findChild(
            _UniqueRollSlider, "uniqueRollSlider"
        ) is None
    finally:
        window.close()


def test_mod_filter_ui_shows_multiple_awakened_tier_tags_on_property(qapp):
    window = PoetoreWindow()
    try:
        source = TradeStatFilter(
            "property.energy_shield", "エナジーシールド", 577.0,
            "property", True, tier_tags=(1, 2),
        )
        window._populate_stat_filters((source,))
        row = window.mod_filter_tree.topLevelItem(0)
        assert row.text(1) == "アイテム特性"
        assert row.text(2) == ""
        tier_widget = window.mod_filter_tree.itemWidget(row, 2)
        assert tier_widget is not None
        assert [label.text() for label in tier_widget.findChildren(QLabel)] == ["T1", "T2"]
        selected = window._selected_stat_filters()[0]
        assert selected.tier_tags == (1, 2)
    finally:
        window.close()


def test_weapon_compound_accuracy_tier_badge_has_double_width_column(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: ワンド
レアリティ: レア
Corruption Call
Imbued Wand
--------
ワンド
品質: +26% (augmented)
物理ダメージ: 59-108 (augmented)
クリティカル率: 8.00%
秒間アタック回数: 1.73 (augmented)
--------
装備要求:
レベル: 60
知性: 188
--------
ソケット: B
--------
アイテムレベル: 83
--------
{ 暗黙モッド — ダメージ, キャスター }
スペルダメージが35(33-37)%増加する
--------
{ プレフィックスモッド「皇帝の」 (ティア: 2) — ダメージ, 物理, アタック }
物理ダメージが72(65-74)%増加する
命中力 +155(150-174)
{ サフィックスモッド 「容易さの」 (ティア: 4) — アタック, スピード }
アタックスピードが8(8-10)%増加する
{ サフィックスモッド 「消し炭の」 (ティア: 4) — ダメージ, 元素, 火 }
火ダメージが17(16-18)%増加する
{ サフィックスモッド 「レンジャーの」 (ティア: 2) — アタック }
命中力 +554(456-624)""")
        window.parse_current_text()
        window.show()
        qapp.processEvents()

        accuracy_row = next(
            window.mod_filter_tree.topLevelItem(index)
            for index in range(window.mod_filter_tree.topLevelItemCount())
            if "命中力 +155" in window.mod_filter_tree.topLevelItem(index).text(3)
        )
        tier_widget = window.mod_filter_tree.itemWidget(accuracy_row, 2)

        assert window.mod_filter_tree.columnWidth(2) == 88
        assert accuracy_row.text(2) == ""
        assert tier_widget is not None
        assert [label.text() for label in tier_widget.findChildren(QLabel)] == ["T2", "T2"]
        assert tier_widget.sizeHint().width() <= window.mod_filter_tree.columnWidth(2)
    finally:
        window.close()


def test_mod_conditions_can_be_collapsed_without_losing_values(qapp):
    window = PoetoreWindow()
    try:
        source = TradeStatFilter(
            "explicit.stat_1", "最大ライフ +100", 90, "prefix", True, tier=2,
        )
        window._populate_stat_filters((source,))
        row = window.mod_filter_tree.topLevelItem(0)
        editor = window.mod_filter_tree.itemWidget(row, 4)
        editor.setText("95")

        window.show()
        assert window.mod_conditions_toggle.text() == "mod条件をたたむ∧"
        window.mod_conditions_toggle.click()
        assert window.mod_filter_tree.isHidden()
        assert window.mod_conditions_toggle.text() == "mod条件をひらく∨"
        assert window._selected_stat_filters()[0].min_value == 95

        window.mod_conditions_toggle.click()
        assert not window.mod_filter_tree.isHidden()
        assert window.mod_conditions_toggle.text() == "mod条件をたたむ∧"
    finally:
        window.close()


def test_mod_conditions_default_is_reset_for_each_new_item(qapp):
    window = PoetoreWindow()
    try:
        fragment = """アイテムクラス: その他マップアイテム
レアリティ: ノーマル
覚醒のフラグメント
--------
スタックサイズ: 1/10
"""
        window.input_edit.setPlainText(fragment)
        window.parse_current_text()

        assert window.mod_filter_tree.topLevelItemCount() == 0
        assert window.mod_filter_tree.isHidden()
        assert window.mod_conditions_toggle.text() == "mod条件をひらく∨"

        window.mod_conditions_toggle.click()
        assert not window.mod_filter_tree.isHidden()
        window.parse_current_text()
        assert not window.mod_filter_tree.isHidden()

        window.mod_filter_tree.clear()
        window.input_edit.setPlainText("""アイテムクラス: 兜
レアリティ: レア
堅牢な冠
鉄の帽子
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「頑健な」 (ティア: 5) — ライフ }
最大ライフ +72(70-84)
""")
        window.parse_current_text()

        assert window.mod_filter_tree.topLevelItemCount() > 0
        assert not window.mod_filter_tree.isHidden()
        assert window.mod_conditions_toggle.text() == "mod条件をたたむ∧"
    finally:
        window.close()


def test_mod_condition_checks_can_all_be_cleared_without_changing_item_level(qapp):
    window = PoetoreWindow()
    try:
        filters = (
            TradeStatFilter("explicit.stat_1", "最大ライフ +100", 90, "prefix", True),
            TradeStatFilter("explicit.stat_2", "火耐性 +40%", 35, "suffix", True),
        )
        window._populate_stat_filters(filters)
        window.item_level_tag.show()
        window.item_level_edit.setText("84")
        window._set_item_level_filter_enabled(True)

        assert window.clear_mod_conditions_button.text() == "一覧のチェックを全解除"
        assert window.clear_mod_conditions_button.toolTip() == (
            "上の条件一覧のみ。ilvlなどの基本条件は変更しません"
        )
        window.show()
        qapp.processEvents()
        assert (
            window.clear_mod_conditions_button.parentWidget()
            is window.mod_conditions_toggle.parentWidget()
        )
        assert (
            window.clear_mod_conditions_button.geometry().left()
            > window.mod_conditions_toggle.geometry().right()
        )
        assert (
            window.clear_mod_conditions_button.geometry().center().y()
            == window.mod_conditions_toggle.geometry().center().y()
        )
        window.clear_mod_conditions_button.click()

        assert [row.enabled for row in window._selected_stat_filters()] == [False, False]
        assert window._selected_item_level() == 84
        assert window._item_level_filter_enabled
    finally:
        window.close()


def test_unresolved_modifiers_are_shown_as_warning(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""Item Class: Rings
Rarity: Rare
Test Ring
Ruby Ring
--------
Item Level: 85
--------
Unknown Experimental Modifier 123
""")
        window.parse_current_text()
        assert not window.mod_warning.isHidden()
        assert "メタデータ未解決 1件" in window.mod_warning.text()
        assert "Unknown Experimental Modifier 123" in window.mod_warning.text()
    finally:
        window.close()


def test_dawnbreaker_shield_block_mod_does_not_show_unresolved_warning(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: 盾
レアリティ: ユニーク
ドーンブレイカー
巨大なタワーシールド
--------
ブロック率: 45% (augmented)
アーマー: 2003 (augmented)
--------
アイテムレベル: 86
--------
{ 暗黙モッド — ライフ }
最大ライフ +17(10-20)
--------
{ ユニークモッド }
ブロック率 +22(20-25)%
{ ユニークモッド }
直近ヒットにより受けた火ダメージ200ごとにアタックブロック率 -1%
(Recently: 直近とは過去4秒間を指す)
{ ユニークモッド }
冷気ダメージの10(10-20)%を火ダメージとして受ける
{ ユニークモッド }
雷ダメージの12(10-20)%を火ダメージとして受ける
{ ユニークモッド }
物理ダメージの20(10-20)%を火ダメージとして受ける
{ ユニークモッド }
ブロック時に近距離にいる敵に焦げを付与する
(Scorch: 焦げた敵は元素耐性が-10%される)
(近距離は最大2メートル)
""")
        window.parse_current_text()

        assert window.mod_warning.isHidden()
        assert window.mod_warning.text() == ""
        visible_filters = [
            window.mod_filter_tree.topLevelItem(index).data(0, Qt.UserRole + 4)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        block_filter = next(
            row for row in visible_filters
            if row.stat_id == "explicit.stat_4253454700"
        )
        assert block_filter.text == "ブロック率 +22(20-25)%"
        assert block_filter.min_value == 21
    finally:
        window.close()


def test_itemised_spectre_corpse_hides_fixed_ability_mod_warning(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: 死体
レアリティ: カレンシー
完全体のドルイド錬金術師
--------
死体レベル: 85
モンスターカテゴリー: 人型
--------
アイテムレベル: 85
--------
ポイゾナスコンコクションを投げる
フラスコの効果が200％増加する
所有者は3秒ごとにライフフラスコのチャージを1得る
--------
このアイテムを右クリックしてこの死体を生成する。
""")
        window.parse_current_text()

        assert window._parsed_item.category == "corpse"
        assert window.mod_warning.isHidden()
        assert window._selected_stat_filters() == ()
        assert not window.item_level_tag.isHidden()
        assert window._selected_item_level() == 85

        window.item_level_toggle.click()
        assert window._selected_item_level() is None

        window.item_level_edit.setFocus()
        window.item_level_edit.selectAll()
        QTest.keyClicks(window.item_level_edit, "83")
        assert window._selected_item_level() == 83
    finally:
        window.close()


def test_embryonic_gift_full_copy_has_no_unresolved_metadata_warning(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: 母胎ギフト
レアリティ: カレンシー
古代の母胎ギフト
--------
アイテムレベル: 83
1790のハイヴブラッドが必要
--------
創生の樹でユニークアイテムに成長させられる
--------
このアイテムを創生の樹の割り当て済みのユニークアイテムの母胎に配置する。右クリックで創生の樹から取り除ける。
""")
        window.parse_current_text()

        assert window._parsed_item.category == "incubator"
        assert window._parsed_item.modifiers == ()
        assert window.mod_warning.isHidden()
        assert window.mod_warning.text() == ""
        assert window._selected_stat_filters() == ()
    finally:
        window.close()


def test_replica_dragonfang_full_copy_shows_selected_skill_mod(qapp):
    window = PoetoreWindow()
    try:
        window._trade_base_type = "Onyx Amulet"
        window._trade_item_name = "Replica Dragonfang's Flight"
        window.input_edit.setPlainText("""アイテムクラス: アミュレット
レアリティ: ユニーク
竜の牙の飛翔（レプリカ）
オニキスのアミュレット
--------
装備要求:
レベル: 56
--------
アイテムレベル: 85
--------
山の如し を割り当てる (enchant)
--------
{ 暗黙モッド — 能力値 }
全ての能力値 +16(10-16)
--------
{ ユニークモッド }
全てのブレードブラスト(ファイヤーボール-マナインフューズスタッフ)ジェムのレベル +3
{ ユニークモッド — 元素, 耐性 }
全ての元素耐性 +5(5-10)%
{ ユニークモッド }
スキルのリザーブ効率が10(5-10)%増加する
{ ユニークモッド }
アイテムおよびジェムの要求能力値が10(10-5)%減少する
""")
        window.parse_current_text()

        visible_filters = [
            window.mod_filter_tree.topLevelItem(index).data(0, Qt.UserRole + 4)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        skill = next(
            row for row in visible_filters
            if row.stat_id == "explicit.indexable_skill_217"
        )
        assert skill.text.startswith("全てのブレードブラスト")
        assert skill.enabled is True
        assert skill.hidden_reason == ""
        assert window.mod_warning.isHidden()
    finally:
        window.close()


def test_forbidden_shako_full_copy_shows_both_random_support_mods(qapp):
    window = PoetoreWindow()
    try:
        window._trade_base_type = "Great Crown"
        window._trade_item_name = "Forbidden Shako"
        window.input_edit.setPlainText("""アイテムクラス: 兜
レアリティ: ユニーク
禁断のシャコー帽
グレートクラウン
--------
装備要求:
レベル: 68
--------
アイテムレベル: 85
--------
{ ユニークモッド }
ソケットされたジェムはレベル8(1-10)クリティカルダメージ増加によりサポートされる
{ ユニークモッド }
ソケットされたジェムはレベル29(25-35)ミニオンスピードによりサポートされる
{ ユニークモッド — 能力値 }
全ての能力値 +29(25-30)
""")
        window.parse_current_text()

        visible_filters = [
            window.mod_filter_tree.topLevelItem(index).data(0, Qt.UserRole + 4)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        by_id = {row.stat_id: row for row in visible_filters}
        assert by_id["explicit.indexable_support_67"].enabled is True
        assert by_id["explicit.indexable_support_62"].enabled is True
        assert by_id["explicit.indexable_support_67"].read_value == 8
        assert by_id["explicit.indexable_support_62"].read_value == 29
        assert window.mod_warning.isHidden()
    finally:
        window.close()


def test_forbidden_shako_reported_advanced_copy_shows_both_support_mods(qapp):
    window = PoetoreWindow()
    try:
        window._trade_base_type = "Great Crown"
        window._trade_item_name = "Forbidden Shako"
        window.input_edit.setPlainText("""アイテムクラス: 兜
レアリティ: ユニーク
禁断のシャコー帽
グレートクラウン
--------
アイテムレベル: 85
--------
{ ユニークモッド — ジェム }
ソケットされたジェムはレベル10(1-10)投射物追加(グレーター投射物追加-聖別)によりサポートされる
{ ユニークモッド — ジェム }
ソケットされたジェムはレベル25(25-35)元素伝染(グレーター投射物追加-聖別)によりサポートされる
{ ユニークモッド — 能力値 }
全ての能力値 +29(25-30)
""")
        window.parse_current_text()

        visible_filters = [
            window.mod_filter_tree.topLevelItem(index).data(0, Qt.UserRole + 4)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        by_id = {row.stat_id: row for row in visible_filters}
        assert by_id["explicit.indexable_support_55"].enabled is True
        assert by_id["explicit.indexable_support_89"].enabled is True
        assert by_id["explicit.indexable_support_55"].read_value == 10
        assert by_id["explicit.indexable_support_89"].read_value == 25
        assert window.mod_warning.isHidden()
    finally:
        window.close()


def test_itemised_spectre_corpse_item_level_toggle_controls_final_search(qapp):
    from src.poetore.trade import PriceResult

    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: 死体
レアリティ: カレンシー
完全体のドルイド錬金術師
--------
死体レベル: 85
モンスターカテゴリー: 人型
--------
アイテムレベル: 85
--------
ポイゾナスコンコクションを投げる
フラスコの効果が200％増加する
所有者は3秒ごとにライフフラスコのチャージを1得る
--------
このアイテムを右クリックしてこの死体を生成する。
""")
        window.parse_current_text()
        window.item_level_toggle.click()

        result = PriceResult("Standard", "qid", 0, ())
        with patch("src.poetore.ui.search_prices", return_value=result) as search:
            window.search_current_item()
            for _ in range(50):
                qapp.processEvents()
                if search.called:
                    break
                QTest.qWait(10)

        assert search.called
        kwargs = search.call_args.kwargs
        assert kwargs["item_level_min"] is None
        assert all(
            row.stat_id != "property.item_level"
            for row in kwargs["stat_filters"]
        )
    finally:
        window.close()


def test_current_japanese_blueprint_shows_revealed_wings_without_rolled_mod_warning(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: 計画書
レアリティ: マジック
Stoic Blueprint: Underbelly
--------
エリアレベル: 83
情報を聞いた区画: 1/4
情報を聞いた脱出ルート: 1/8
情報を聞いた報酬部屋: 3/28
必要ジョブ 怪力 (レベル 1)
必要ジョブ 敏捷性 (レベル 1)
必要ジョブ 欺瞞 (レベル 5)
--------
アイテムレベル: 83
--------
{ プレフィックスモッド「克己する」 (ティア: 1) }
ガードが受けるダメージが29(30-27)%減少する
""")
        window.parse_current_text()

        assert not window.heist_wings_chip.isHidden()
        assert window.heist_wings_chip.values() == (1.0, None)
        assert window.heist_wings_chip.isActive()
        assert window.heist_job_chip.isHidden()
        assert window.mod_warning.isHidden()
        assert window.mod_filter_tree.topLevelItemCount() == 1
        only_row = window.mod_filter_tree.topLevelItem(0).data(0, Qt.UserRole + 4)
        assert only_row.stat_id == "pseudo.pseudo_number_of_enchant_mods"
    finally:
        window.close()


def test_current_japanese_contract_shows_required_job_without_rolled_mod_warning(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: 依頼書
レアリティ: レア
Vengeance Pact
Contract: Underbelly
--------
依頼人: 真夜中の修理人
ハイスト目標: アリモルの腕 (中程度な価値)
エリアレベル: 49
必要ジョブ 工作 (レベル 1)
--------
アイテムレベル: 49
--------
{ プレフィックスモッド「燃える」 (ティア: 4) }
モンスターは物理ダメージの31(30-49)%を追加火ダメージとして与える
{ プレフィックスモッド「連鎖する」 (ティア: 2) }
モンスターのスキルは追加で1回連鎖する
{ プレフィックスモッド「敵愾心の」 (ティア: 4) }
報酬部屋のモンスターが受けるダメージが17(18-16)%減少する
{ サフィックスモッド 「悩みの」 (ティア: 4) }
アラートレベル25%ごとにプレイヤーのアーマーが5%低下する
""")
        window.parse_current_text()

        assert window._parsed_item.category == "heist_contract"
        assert not window.heist_job_chip.isHidden()
        assert window.heist_job_chip.values() == (1.0, None)
        assert window.heist_job_chip.isActive()
        assert window.area_level_chip.values() == (49.0, None)
        assert window.mod_warning.isHidden()
        rows = [
            window.mod_filter_tree.topLevelItem(index).data(0, Qt.UserRole + 4)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        assert rows == []
    finally:
        window.close()


def test_blighted_map_does_not_warn_about_ignored_map_mods(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: マップ
レアリティ: レア
Glyph Stone
Blighted Map (Tier 16)
--------
アイテムレベル: 83
--------
{ 暗黙モッド }
エリアは真菌に覆われている
マップのアイテムの数量のモッドはその数値の20%がブライトチェストにも影響する
3回アノイントすることができる — スケールできない値
このエリアに元々生息していた生物はいなくなる — スケールできない値
--------
{ プレフィックスモッド「多様な」 (ティア: 1) }
エリアのモンスターの種類が増える — スケールできない値
""")
        window.parse_current_text()
        assert window.mod_warning.isHidden()
        assert window.mod_filter_tree.topLevelItemCount() == 0
        assert window.map_tier_chip.values() == (16.0, None)
        assert window.blighted_chip.text() == "ブライトマップ"
    finally:
        window.close()


def test_inscribed_ultimatum_shows_unsupported_condition_notice(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: その他マップアイテム
レアリティ: カレンシー
アルティメイタムの刻印
--------
クリア条件: 敵のウェーブを倒せ
エリアレベル: 83
必要な生贄: 消去のオーブ x4
報酬: 捧げたカレンシーを倍にする
--------
モンスターのダメージが20%増加する
""")
        window.parse_current_text()
        assert not window.search_scope_notice.isHidden()
        assert window.search_scope_notice.text() == (
            "⚠ チャレンジタイプ・報酬種類・必要なアイテム・報酬などの条件を使った検索には対応しておりません。"
        )
        assert window.mod_filter_tree.topLevelItemCount() == 0

        window.input_edit.setPlainText("""Item Class: Currency
Rarity: Currency
Chaos Orb
""")
        window.parse_current_text()
        assert window.search_scope_notice.isHidden()
    finally:
        window.close()


def test_misc_map_boss_invitation_has_no_unresolved_modifier_warning(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: その他マップアイテム
レアリティ: ノーマル
極性の招待状
--------
アイテムレベル: 83
--------
{ 暗黙モッド }
アイテムの数量のモッドはボスからドロップする報酬の量に影響する
--------
一度ブラック・スターに捕まれば、
逃げ場はない。
--------
自身のマップデバイスで使用することで、極性の虚無へのポータルを開く。
""")
        window.parse_current_text()

        assert window._parsed_item.category == "invitation"
        assert window.mod_warning.isHidden()
        assert window.mod_filter_tree.topLevelItemCount() == 0
    finally:
        window.close()


def test_unidentified_unique_candidates_can_be_selected(qapp):
    window = PoetoreWindow()
    try:
        window._show_unique_candidates(("The First", "The Second"))
        buttons = window.unique_name_group.buttons()
        assert not window.unique_name_container.isHidden()
        assert [button.property("uniqueName") for button in buttons] == [
            "The First", "The Second",
        ]
        assert buttons[0].isChecked()
        buttons[1].click()
        assert buttons[1].isChecked()
        assert not buttons[0].isChecked()
        assert "2種類" in window.price_status.text()
    finally:
        window.close()


def test_unidentified_unique_candidates_keep_icon_urls(qapp):
    from src.poetore.trade import UniqueCandidate

    window = PoetoreWindow()
    try:
        icon = "https://web.poecdn.com/gen/image/example.png"
        window._show_unique_candidates((UniqueCandidate("The Example", icon),))
        button = window.unique_name_group.buttons()[0]
        assert button.property("uniqueName") == "The Example"
        assert button.property("iconUrl") == icon
        assert button.iconSize() == QSize(48, 48)
    finally:
        window.close()


def test_unidentified_unique_candidates_show_japanese_but_search_in_english(qapp):
    from src.poetore.trade import UniqueCandidate

    window = PoetoreWindow()
    try:
        window._show_unique_candidates((
            UniqueCandidate(
                "Eternal Damnation",
                "https://web.poecdn.com/example.png",
                "永遠の破滅",
            ),
        ))
        button = window.unique_name_group.buttons()[0]
        assert button.text() == "永遠の破滅"
        assert button.property("uniqueName") == "Eternal Damnation"
        assert button.toolTip() == "永遠の破滅\nEternal Damnation"
    finally:
        window.close()


def test_unidentified_agate_amulet_shows_all_five_candidates(qapp):
    from src.poetore.trade import UniqueCandidate

    window = PoetoreWindow()
    try:
        names = (
            "Eternal Damnation",
            "Extractor Mentis",
            "Shaper's Seed",
            "The Aylardex",
            "Voll's Devotion",
        )
        candidates = tuple(
            UniqueCandidate(name, f"https://web.poecdn.com/{index}.png")
            for index, name in enumerate(names)
        )
        window._show_unique_candidates(candidates)

        buttons = window.unique_name_group.buttons()
        assert [button.property("uniqueName") for button in buttons] == list(names)
        assert all(button.property("iconUrl") for button in buttons)
        assert all(not button.isHidden() for button in buttons)
    finally:
        window.close()


def test_many_unidentified_unique_candidates_are_scrollable(qapp):
    from src.poetore.trade import UniqueCandidate

    window = PoetoreWindow()
    try:
        candidates = tuple(
            UniqueCandidate(f"Candidate {index}", f"https://example.test/{index}.png")
            for index in range(55)
        )
        window._show_unique_candidates(candidates)
        window.show()
        qapp.processEvents()

        assert len(window.unique_name_group.buttons()) == 55
        assert not window.unique_name_scroll.isHidden()
        assert window.unique_name_scroll.minimumHeight() == 204
        assert window.unique_name_scroll.maximumHeight() == 204
        assert window.unique_name_scroll.verticalScrollBar().maximum() > 0
        assert window.unique_name_scroll.viewport().palette().color(
            window.unique_name_scroll.viewport().backgroundRole()
        ).name() == "#121212"
    finally:
        window.close()


def test_unique_variant_discriminator_can_be_selected(qapp):
    window = PoetoreWindow()
    try:
        window._show_unique_variants((("通常版", None), ("Legacy版", "legacy")))
        assert window.unique_variant_combo.isVisible() or not window.unique_variant_combo.isHidden()
        assert window.unique_variant_combo.count() == 2
        assert window.unique_variant_combo.itemData(1) == "legacy"
        assert "2種類" in window.price_status.text()
    finally:
        window.close()


def test_unique_variant_selector_is_cleared_when_item_text_changes(qapp):
    window = PoetoreWindow()
    try:
        window._show_unique_variants((("通常版", None), ("Legacy版", "legacy")))
        window.input_edit.setPlainText("""Item Class: Belts
Rarity: Unique
Another Item
Heavy Belt
--------
Item Level: 70
""")
        window.parse_current_text()
        assert window.unique_variant_combo.isHidden()
        assert window.unique_variant_combo.count() == 0
    finally:
        window.close()


@pytest.mark.parametrize("toggle_name", ["trade_preset_combo"])
def test_binary_filters_are_two_segment_toggles_without_popups(qapp, toggle_name):
    window = PoetoreWindow()
    try:
        toggle = getattr(window, toggle_name)
        assert not isinstance(toggle, QComboBox)
        assert toggle.currentData() == toggle.itemData(0)
        toggle._buttons[1].click()
        assert toggle.currentData() == toggle.itemData(1)
        assert toggle._buttons[1].isChecked()
        assert not toggle._buttons[0].isChecked()
    finally:
        window.close()


def test_split_filter_is_an_awakened_style_cycle_button(qapp):
    window = PoetoreWindow()
    try:
        toggle = window.split_combo
        assert toggle.property("active") is True
        assert toggle.currentText() == "スプリット品含む"
        assert toggle.currentData() is True
        toggle.click()
        assert toggle.currentText() == "非スプリット"
        assert toggle.currentData() is False
        assert toggle.property("active") is True
        toggle.click()
        assert toggle.currentText() == "スプリット品含む"
    finally:
        window.close()


def test_corruption_filter_is_a_three_state_cycle_button(qapp):
    window = PoetoreWindow()
    try:
        toggle = window.corrupted_combo
        assert toggle.count() == 3
        assert toggle.currentText() == "非コラプトのみ"
        assert toggle.currentData() is False
        toggle.click()
        assert toggle.currentText() == "コラプト品含む"
        assert toggle.currentData() is True
        toggle.click()
        assert toggle.currentText() == "コラプトのみ"
        assert toggle.currentData() == "only"
        assert toggle.property("alert") is True
        toggle.click()
        assert toggle.currentText() == "非コラプトのみ"
        assert toggle.property("alert") is False
    finally:
        window.close()


def test_trade_preset_selector_only_offers_base_for_crafting_candidate(qapp):
    window = PoetoreWindow()
    try:
        high_level = parse_item_text("""Item Class: Rings
Rarity: Rare
Test Ring
Ruby Ring
--------
Item Level: 85
--------
+70 to maximum Life
""")
        window._configure_trade_presets(high_level)
        assert window.trade_preset_combo.count() == 2
        assert window.trade_preset_combo.itemData(0) == "finished"
        assert window.trade_preset_combo.itemData(1) == "base"
        assert window.trade_preset_combo.isEnabled()
        assert not isinstance(window.trade_preset_combo, QComboBox)

        window.trade_preset_combo.setCurrentIndex(1)
        assert "ベースアイテム" in window.price_status.text()

        low_level = parse_item_text(high_level.raw_text.replace("Item Level: 85", "Item Level: 70"))
        window._configure_trade_presets(low_level)
        assert window.trade_preset_combo.count() == 1
        assert not window.trade_preset_combo.isEnabled()
        window.resize(720, window.height())
        window.show()
        qapp.processEvents()
        assert window.trade_preset_combo.width() <= window._panel.width() / 2
        single_width = window.trade_preset_combo._buttons[0].width()
        assert window.trade_preset_combo._empty_segment.isVisible()

        window._configure_trade_presets(high_level)
        qapp.processEvents()
        assert not window.trade_preset_combo._empty_segment.isVisible()
        assert abs(window.trade_preset_combo._buttons[0].width() - single_width) <= 1
    finally:
        window.close()


def test_dedicated_exact_preset_is_labeled_as_dedicated_search_and_restores_finished(qapp):
    window = PoetoreWindow()
    try:
        exact_item = ParsedItem(
            item_class="Maps", rarity="Rare", name="Test Map",
            base_type="Test Map", category="map", raw_text="exact-map",
        )
        window._parsed_item = exact_item
        window._configure_trade_presets(exact_item)
        assert window.trade_preset_combo.count() == 1
        assert window.trade_preset_combo.currentData() == "finished"
        assert window.trade_preset_combo.currentText() == "専用検索"
        assert window.trade_preset_combo._buttons[0].text() == "専用検索"
        window._trade_preset_changed()
        assert "専用条件" in window.price_status.text()

        craftable_item = parse_item_text("""Item Class: Rings
Rarity: Rare
Test Ring
Ruby Ring
--------
Item Level: 85
--------
+70 to maximum Life
""")
        window._parsed_item = craftable_item
        window._configure_trade_presets(craftable_item)
        assert window.trade_preset_combo.currentText() == "完成品"
        assert window.trade_preset_combo.itemText(1) == "ベースアイテム"
        assert window.trade_preset_combo.count() == 2
    finally:
        window.close()


def test_normal_item_dedicated_exact_is_labeled_as_base_item(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""アイテムクラス: ワンド
レアリティ: ノーマル
Superior Imbued Wand
--------
ワンド
品質: +25% (augmented)
--------
アイテムレベル: 83
--------
{ 暗黙モッド — ダメージ, キャスター }
スペルダメージが35(33-37)%増加する""")
        window._parsed_item = item
        window._configure_trade_presets(item)

        assert window.trade_preset_combo.count() == 1
        assert window.trade_preset_combo.currentData() == "finished"
        assert window.trade_preset_combo.currentText() == "ベースアイテム"
        assert window.trade_preset_combo._buttons[0].text() == "ベースアイテム"
    finally:
        window.close()


def test_magic_base_rarity_toggle_is_only_shown_for_magic_base_search(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""Item Class: Rings
Rarity: Magic
Healthy Ruby Ring
Ruby Ring
--------
Item Level: 85
""")
        window._parsed_item = item
        window._configure_trade_presets(item)
        assert window.magic_rarity_toggle.isHidden()
        window.trade_preset_combo.setCurrentIndex(1)
        assert not window.magic_rarity_toggle.isHidden()
        assert window.magic_rarity_toggle.currentData() is False
        window.magic_rarity_toggle.setCurrentIndex(1)
        assert window.magic_rarity_toggle.currentData() is True
        window.trade_preset_combo.setCurrentIndex(0)
        assert window.magic_rarity_toggle.isHidden()
    finally:
        window.close()


def test_magic_jewel_base_search_defaults_to_magic_exact_like_awakened(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""Item Class: Jewels
Rarity: Magic
Vicious Viridian Jewel of Shelter
Viridian Jewel
--------
Item Level: 82
""")
        assert item.category == "jewel"
        window._parsed_item = item
        window._configure_trade_presets(item)
        window.trade_preset_combo.setCurrentIndex(1)
        assert not window.magic_rarity_toggle.isHidden()
        assert window.magic_rarity_toggle.currentData() is True
    finally:
        window.close()


def test_currency_selection_uses_recommended_default_and_is_kept_for_same_item(qapp):
    window = PoetoreWindow()
    try:
        sword = parse_item_text("""Item Class: Two Hand Swords
Rarity: Rare
Test Sword
Reaver Sword
--------
Item Level: 70
""")
        window._trade_base_type = "Reaver Sword"
        window._configure_trade_currency(sword)
        assert window.trade_currency_combo.currentData() == "any"

        window.trade_currency_combo.setCurrentIndex(
            window.trade_currency_combo.findData("divine")
        )
        window._configure_trade_currency(sword)
        assert window.trade_currency_combo.currentData() == "divine"

        logbook = parse_item_text("""Item Class: Expedition Logbooks
Rarity: Rare
Test Logbook
Expedition Logbook
--------
Item Level: 83
""")
        window._trade_base_type = "Expedition Logbook"
        window._configure_trade_currency(logbook)
        assert window.trade_currency_combo.currentData() == "chaos_divine"
    finally:
        window.close()


def test_item_state_filters_use_clear_labels_defaults_and_keep_selection(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Item Level: 94
--------
Split
""")
        window._configure_item_state_filters(item)
        assert window.corrupted_combo.itemText(0) == "コラプトのみ"
        assert window.corrupted_combo.itemText(1) == "非コラプトのみ"
        assert window.corrupted_combo.itemText(2) == "コラプト品含む"
        assert window.corrupted_combo.currentData() is False
        assert window.split_combo.itemText(0) == "スプリット品含む"
        assert window.split_combo.itemText(1) == "非スプリット"
        assert window.split_combo.currentData() is True
        assert not window.split_combo.isHidden()
        assert not isinstance(window.corrupted_combo, QComboBox)
        assert not isinstance(window.split_combo, QComboBox)

        window.corrupted_combo.setCurrentIndex(2)
        window.split_combo.setCurrentIndex(1)
        window._configure_item_state_filters(item)
        assert window.corrupted_combo.currentData() is True
        assert window.split_combo.currentData() is False
    finally:
        window.close()


@pytest.mark.parametrize(("extra", "expected_include_split"), [
    ("", False),
    ("Corrupted", True),
    ("Mirrored", True),
    ("Synthesised Item", True),
    ("Shaper Item", True),
])
def test_hidden_split_filter_matches_awakened_special_state_rules(
    qapp, extra, expected_include_split,
):
    window = PoetoreWindow()
    try:
        item = parse_item_text(f"""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Item Level: 94
--------
{extra}
""")
        window._configure_item_state_filters(item)
        assert window.split_combo.isHidden()
        assert window._hidden_include_split is expected_include_split
    finally:
        window.close()


def test_hidden_split_filter_does_not_auto_exclude_fractured_item(qapp):
    window = PoetoreWindow()
    try:
        item = ParsedItem(
            item_class="Body Armours", rarity="Rare", name="Test Armour",
            base_type="Sacred Chainmail", category="armour", item_level=94,
            modifiers=(ItemModifier("10% increased Armour", kind="fractured"),),
            raw_text="fractured armour",
        )
        window._configure_item_state_filters(item)
        assert window.split_combo.isHidden()
        assert window._hidden_include_split is True
    finally:
        window.close()


def test_standard_finished_search_includes_split_but_base_search_excludes_it(qapp):
    window = PoetoreWindow(app_config={"poetore": {"league": "Standard"}})
    try:
        item = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Item Level: 94
""")
        window._parsed_item = item
        window._configure_item_state_filters(item)
        assert window.trade_preset_combo.currentData() == PRESET_FINISHED
        assert window._hidden_include_split is True

        window.trade_preset_combo.setCurrentIndex(1)
        assert window._hidden_include_split is False
    finally:
        window.close()


def test_temporary_league_finished_search_excludes_split(qapp):
    window = PoetoreWindow(app_config={"poetore": {"league": "Mirage"}})
    try:
        item = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Item Level: 94
""")
        window._configure_item_state_filters(item)

        assert window._hidden_include_split is False
    finally:
        window.close()


def test_mirrored_chip_matches_awakened_visible_and_hidden_states(qapp):
    window = PoetoreWindow()
    try:
        mirrored = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Item Level: 94
--------
Mirrored
""")
        window._configure_item_state_filters(mirrored)
        assert not window.mirrored_combo.isHidden()
        assert window.mirrored_combo.currentText() == "ミラー化"
        assert window.mirrored_combo.currentData() is True
        window.mirrored_combo.click()
        assert window.mirrored_combo.currentText() == "非ミラー化"
        assert window.mirrored_combo.currentData() is False

        plain = replace(mirrored, raw_text="plain", flags=())
        window._configure_item_state_filters(plain)
        assert window.mirrored_combo.isHidden()
        assert window._hidden_include_mirrored is False

        corrupted = replace(mirrored, raw_text="corrupted", flags=("corrupted",))
        window._configure_item_state_filters(corrupted)
        assert window.mirrored_combo.isHidden()
        assert window._hidden_include_mirrored is True
    finally:
        window.close()


def test_mirrored_penumbra_ring_resolves_all_visible_mods_without_warning(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: 指輪
レアリティ: レア
Pandemonium Loop
Penumbra Ring
--------
アイテムレベル: 83
--------
{ 暗黙モッド — 呪い }
左の指輪スロット: 受けている呪いの効果が30%減少する
右の指輪スロット: 受けている呪いの効果が30%増加する
--------
{ サフィックスモッド 「拡散の」 (ティア: 3) — マナ }
倒した敵1体ごとに48(-16--25)のマナを失う
--------
ミラー状態
""")
        window.parse_current_text()

        rows = [
            window.mod_filter_tree.topLevelItem(index).data(0, Qt.UserRole + 4)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        by_id = {row.stat_id: row for row in rows}
        assert by_id["implicit.stat_496053892"].inverted is True
        assert by_id["explicit.stat_1368271171"].inverted is True
        assert by_id["explicit.stat_1368271171"].min_value == 48.0
        assert window.mod_warning.isHidden()
        assert not window.mirrored_combo.isHidden()
        assert window.mirrored_combo.currentText() == "ミラー化"
    finally:
        window.close()


def test_reduced_curse_effect_flask_shows_awakened_positive_minimum(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: ユーティリティフラスコ
レアリティ: マジック
医者の モッキングバードの 水銀のフラスコ
--------
アイテムレベル: 84
--------
{ サフィックスモッド 「モッキングバードの」 (ティア: 4) }
効果中にプレイヤーに対する呪いの効果が45(47-42)%減少する
""")
        window.parse_current_text()

        target = None
        for index in range(window.mod_filter_tree.topLevelItemCount()):
            row = window.mod_filter_tree.topLevelItem(index)
            stat_filter = row.data(0, Qt.UserRole + 4)
            if stat_filter.stat_id == "explicit.stat_4265534424":
                target = row
                break
        assert target is not None
        minimum = window.mod_filter_tree.itemWidget(target, _MOD_COLUMN_MIN)
        maximum = window.mod_filter_tree.itemWidget(target, _MOD_COLUMN_MAX)
        assert minimum.text() == "44"
        assert maximum.text() == ""
    finally:
        window.close()


def test_reduced_effect_flask_hybrid_is_resolved_without_exclusion_warning(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: ユーティリティフラスコ
レアリティ: マジック
割り当てられた クリスタルの ダイヤモンドフラスコ
--------
アイテムレベル: 85
--------
{ プレフィックスモッド「割り当てられた」 (ティア: 2) }
チャージ回復量が60(55-60)%増加する
効果が25%減少する
{ サフィックスモッド 「クリスタルの」 (ティア: 3) — 元素, 耐性 }
効果中は13(12-14)%の元素耐性が追加される
""")
        window.parse_current_text()

        rows = [
            window.mod_filter_tree.topLevelItem(index).data(0, Qt.UserRole + 4)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        effect = next(
            row for row in rows if row.stat_id == "explicit.stat_2448920197"
        )
        assert effect.text == "効果が25%減少する"
        assert effect.inverted is True
        assert effect.enabled is True
        assert not any(row.kind == "flask hybrid" for row in rows)
        assert window.mod_warning.isHidden()
    finally:
        window.close()


def test_special_state_chips_for_unidentified_veiled_and_foil(qapp):
    window = PoetoreWindow()
    try:
        base = ParsedItem(
            item_class="Belts", rarity="Unique", name="Auxium", base_type="Chain Belt",
            category="accessory", flags=("unidentified", "veiled", "foil"), raw_text="special",
        )
        window._configure_special_filter_chips(base)
        assert not window.unidentified_chip.isHidden()
        assert window.unidentified_chip.currentData() is True
        assert not window.veiled_chip.isHidden() and window.veiled_chip.currentData() is True
        assert not window.foil_chip.isHidden() and window.foil_chip.currentData() is True

        normal = replace(base, rarity="Rare", raw_text="normal unidentified", flags=("unidentified",))
        window._configure_special_filter_chips(normal)
        assert window.unidentified_chip.currentData() is False
        assert window.veiled_chip.isHidden()
        assert window.foil_chip.isHidden()
    finally:
        window.close()


def test_map_and_heist_special_filter_chips(qapp):
    window = PoetoreWindow()
    try:
        map_item = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
ブライトに破壊された峡谷マップ
峡谷マップ
--------
マップティア: 16
マップ完了報酬: Mageblood
--------
アイテムレベル: 83
""")
        window._configure_special_filter_chips(map_item)
        assert not window.map_tier_chip.isHidden()
        assert window.map_tier_chip.width() == 116
        assert window.map_tier_chip.values() == (16.0, None)
        assert window.map_tier_chip.maximum_edit.isHidden()
        assert window.blighted_chip.text() == "ブライトに破壊されたマップ"
        assert window.completion_reward_chip.text() == "完了報酬: Mageblood"
        ids = {row.stat_id: row for row in window._selected_special_chip_filters()}
        assert ids["property.map_tier"].max_value == 16.0
        assert ids["property.map_uberblighted"].enabled
        assert ids["property.map_completion_reward"].option_value == "Mageblood"

        detailed_copy_map = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Pandemonium Solitude
Map (Tier 16)
--------
アイテム数量: +52% (augmented)
--------
アイテムレベル: 85
--------
モンスターレベル：83
""")
        window._configure_special_filter_chips(detailed_copy_map)
        assert not window.map_tier_chip.isHidden()
        assert window.map_tier_chip.values() == (16.0, None)
        assert window.map_tier_chip.maximum_edit.isHidden()
        detailed_ids = {
            row.stat_id: row for row in window._selected_special_chip_filters()
        }
        assert detailed_ids["property.map_tier"].min_value == 16.0
        assert detailed_ids["property.map_tier"].max_value == 16.0

        nightmare_map = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
勝利の航海
ナイトメアマップ
--------
アイテム数量: +96% (augmented)
--------
アイテムレベル: 85
--------
モンスターレベル：83
""")
        window._trade_base_type = "Nightmare Map"
        window._configure_special_filter_chips(nightmare_map)
        assert not window.nightmare_map_chip.isHidden()
        assert window.nightmare_map_chip.text() == "ナイトメア"
        assert not window.nightmare_map_chip.isEnabled()
        assert window.map_tier_chip.isHidden()
        assert "property.map_tier" not in {
            row.stat_id for row in window._selected_special_chip_filters()
        }

        detailed_blighted_map = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Glyph Stone
Blighted Map (Tier 16)
--------
マップエリア: 干上がった海
アイテム数量: +75% (augmented)
アイテムレアリティ: +45% (augmented)
モンスターパックサイズ: +29% (augmented)
--------
アイテムレベル: 83
--------
モンスターレベル：83
--------
{ 暗黙モッド }
エリアは真菌に覆われている
マップのアイテムの数量のモッドはその数値の20%がブライトチェストにも影響する
3回アノイントすることができる — スケールできない値
このエリアに元々生息していた生物はいなくなる — スケールできない値
""")
        window._configure_special_filter_chips(detailed_blighted_map)
        assert not window.blighted_chip.isHidden()
        assert window.blighted_chip.text() == "ブライトマップ"
        blighted_ids = {
            row.stat_id: row for row in window._selected_special_chip_filters()
        }
        assert blighted_ids["property.map_blighted"].enabled

        blueprint = parse_item_text("""アイテムクラス: 設計図
レアリティ: レア
試作品
設計図
--------
エリアレベル: 83
情報を聞いた区画数: 4
--------
アイテムレベル: 83
""")
        window._configure_special_filter_chips(blueprint)
        assert window.area_level_chip.values() == (83.0, None)
        assert window.heist_wings_chip.values() == (4.0, None)
    finally:
        window.close()


def test_full_valdo_copy_hides_reward_filter_and_shows_unsupported_notice(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: マップ
レアリティ: レア
Befuddling Frontier
Valdo Map
--------
マップエリア: 岸辺
報酬: フォイル 魅惑
アイテム数量: +58% (augmented)
モンスターパックサイズ: +64% (augmented)
--------
アイテムレベル: 100
--------
モンスターレベル：84
--------
{ ユニークモッド }
エリアにはサルファイトゴーレムが追加で10(6-10)パック出現する
{ ユニークモッド }
エリアには安息の訪れない死者の追加のパックが出現する
{ ユニークモッド }
ビヨンドからのモンスターは冒涜領域を生成する
ビヨンドボスはスポーンしない
敵どうしが近くにいる状態で同時に倒すとこの世界の外からのビヨンドからモンスターを呼び寄せる — スケールできない値
{ ユニークモッド }
プレイヤーはブロックできない
{ ユニークモッド }
レアモンスターは死亡時に20%の確率でマップボスの複製をスポーンさせる
{ ユニークモッド }
モンスターはプレイヤーから2m以内にいる時だけダメージを受ける
プレイヤーの光半径に対するモッドはこの範囲にも適用される
--------
変更不可
--------
フォイル (天体の翠玉)
""")
        window.parse_current_text()

        assert window.mod_warning.isHidden()
        assert window.completion_reward_chip.isHidden()
        assert not window.search_scope_notice.isHidden()
        assert window.search_scope_notice.text() == (
            "⚠ Valdo Mapの報酬条件を使った検索は初版では対応していません。"
            "報酬を除く条件で検索します。"
        )
        assert "property.map_completion_reward" not in {
            row.stat_id for row in window._selected_special_chip_filters()
        }
        filters = tuple(window._special_chip_rows.values())
        assert len([row for row in filters if row.stat_id.startswith("explicit.")]) == 8
    finally:
        window.close()


def test_unidentified_unique_can_open_candidate_selector(qapp):
    from src.poetore.trade import UniqueCandidate

    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: スタッフ
レアリティ: ユニーク
Judgement Staff
--------
アイテムレベル: 83
--------
未鑑定
""")
        window.parse_current_text()

        assert window.search_scope_notice.isHidden()
        assert window.price_button.isEnabled()
        assert not window.trade_url_button.isEnabled()
        assert window.unique_name_container.isHidden()

        candidates = (
            UniqueCandidate("The First", "https://web.poecdn.com/first.png"),
            UniqueCandidate("The Second", "https://web.poecdn.com/second.png"),
        )
        with patch("src.poetore.ui.unique_candidate_details", return_value=candidates):
            window.search_current_item()
            for _ in range(50):
                qapp.processEvents()
                if not window.unique_name_container.isHidden():
                    break
                QTest.qWait(10)

        assert not window.unique_name_container.isHidden()
        assert [
            button.property("uniqueName")
            for button in window.unique_name_group.buttons()
        ] == ["The First", "The Second"]
        assert window.price_button.isEnabled()
        assert "候補を選んで" in window.price_status.text()
    finally:
        window.close()


def test_cluster_special_chips_do_not_duplicate_passive_or_enchant_filters(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""アイテムクラス: ジュエル
レアリティ: レア
Loath Eye
Medium Cluster Jewel
--------
アイテムレベル: 84
--------
パッシブスキルを4個追加する (enchant)
ジュエルソケット1個がパッシブスキルに追加される (enchant)
追加される通常パッシブスキルは付与: 範囲ダメージが10%増加する (enchant)
--------
{ プレフィックスモッド「特殊な」 (ティア: 1) — ライフ }
パッシブスキルを1個追加: 高くそびえる脅威 — スケールできない値
{ プレフィックスモッド「特殊な」 (ティア: 1) — ダメージ }
パッシブスキルを1個追加: 強力な暴行 — スケールできない値
""")
        window._parsed_item = item
        window._trade_base_type = "Medium Cluster Jewel"
        window._configure_special_filter_chips(item)

        assert "パッシブスキルを4個追加する" not in window.cluster_enchant_chip.text()
        assert "範囲ダメージが10%増加する" in window.cluster_enchant_chip.text()

        special = window._selected_special_chip_filters()
        stat_ids = [row.stat_id for row in special]
        assert stat_ids.count("enchant.stat_3086156145") == 1
        assert sum(
            stat_id.split("|", 1)[0] == "enchant.stat_3948993189"
            for stat_id in stat_ids
        ) == 1

        initial = resolve_trade_stat_filters(
            item, PRESET_FINISHED, "Medium Cluster Jewel",
        )
        effective = _replace_filters_with_special_chips(initial, (), special)
        effective_ids = [row.stat_id for row in effective if row.enabled]
        assert effective_ids.count("enchant.stat_3086156145") == 1
        assert sum(
            stat_id.split("|", 1)[0] == "enchant.stat_3948993189"
            for stat_id in effective_ids
        ) == 1
    finally:
        window.close()


def test_large_cluster_eight_passives_stays_at_eight_in_ui_with_search_range(qapp):
    window = PoetoreWindow(app_config={"poetore": {"search_stat_range": 10}})
    try:
        item = parse_item_text("""アイテムクラス: ジュエル
レアリティ: ノーマル
クラスタージュエル (大)
--------
アイテムレベル: 84
--------
パッシブスキルを8個追加する (enchant)
ジュエルソケット2個がパッシブスキルに追加される (enchant)
追加される通常パッシブスキルは付与: 物理ダメージが12%増加する (enchant)
""")
        window._trade_base_type = "Large Cluster Jewel"
        filters = window._resolved_trade_filters(item, PRESET_FINISHED)
        window._configure_special_filter_chips(item)
        window._populate_stat_filters(filters)

        assert window.cluster_passives_chip.values() == (None, 8.0)
        selected = window._selected_special_chip_filters()
        passive = next(row for row in selected if row.ref == "Adds # Passive Skills")
        assert (passive.min_value, passive.max_value) == (None, 8.0)
    finally:
        window.close()


def test_item_level_tag_is_editable_state_and_replaces_tree_filter(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Item Level: 86
""")
        window._configure_item_level(item)
        assert not window.item_level_tag.isHidden()
        assert window.item_level_edit.text() == "86"
        assert window.item_level_edit.validator().bottom() == 1
        assert window.item_level_edit.validator().top() == 100
        assert window.item_level_tag.parentWidget() is window.filter_chip_container
        assert window._selected_item_level() is None
        assert window.item_level_toggle.text() == "☐ ilvl："

        window.item_level_edit.setText("84")
        window.item_level_toggle.click()
        assert window._selected_item_level() == 84
        window.item_level_toggle.click()
        assert window._selected_item_level_range() == (None, None)
        assert window.item_level_tag.property("active") is False
        assert window.item_level_toggle.text() == "☐ ilvl："
        assert window.item_level_edit.font().strikeOut()
        window.item_level_toggle.click()
        assert window._selected_item_level_range() == (84, None)
        assert window.item_level_tag.property("active") is True
        assert window.item_level_toggle.text() == "☑ ilvl："
        assert not window.item_level_edit.font().strikeOut()

        window.item_level_toggle.click()
        window.item_level_edit.setFocus()
        window.item_level_edit.selectAll()
        QTest.keyClicks(window.item_level_edit, "82")
        assert window._selected_item_level_range() == (82, None)
        assert window.item_level_tag.property("active") is True
        window._configure_item_level(item)
        assert window.item_level_edit.text() == "82"

        window._populate_stat_filters((TradeStatFilter(
            "property.item_level", "アイテムレベル", 86.0, "base", True,
        ),))
        assert window.mod_filter_tree.topLevelItemCount() == 0
    finally:
        window.close()


@pytest.mark.parametrize(("item_class", "base_type"), [
    ("Two Hand Axes", "Vaal Axe"),
    ("Body Armours", "Sacred Chainmail"),
    ("Rings", "Ruby Ring"),
])
def test_rare_gear_item_level_is_off_for_finished_and_on_for_base(
    qapp, item_class, base_type,
):
    window = PoetoreWindow()
    try:
        item = parse_item_text(f"""Item Class: {item_class}
Rarity: Rare
Test Item
{base_type}
--------
Item Level: 89
--------
Fractured Item
""")
        window._parsed_item = item
        window._trade_base_type = base_type
        window._configure_trade_presets(item)
        window._configure_item_level(item, force=True)

        assert window.trade_preset_combo.currentData() == PRESET_FINISHED
        assert not window.item_level_tag.isHidden()
        assert window.item_level_edit.text() == "89"
        assert window._selected_item_level_range() == (None, None)

        window.trade_preset_combo.setCurrentIndex(1)
        assert window.trade_preset_combo.currentData() == PRESET_BASE
        assert window.item_level_edit.text() == "86"
        assert window._selected_item_level_range() == (86, None)

        window.trade_preset_combo.setCurrentIndex(0)
        assert window.item_level_edit.text() == "89"
        assert window._selected_item_level_range() == (None, None)
    finally:
        window.close()


@pytest.mark.parametrize("text", [
    """アイテムクラス: マップ
レアリティ: ノーマル
Map (Tier 16)
--------
アイテムレベル: 85
--------
モンスターレベル：83
""",
    """Item Class: Maps
Rarity: Unique
The Coward's Trial
Cursed Crypt Map
--------
Map Tier: 16
Item Level: 83
""",
    """アイテムクラス: マップ
レアリティ: レア
ブライトマップ
峡谷マップ
--------
マップティア: 16
アイテムレベル: 83
""",
    """アイテムクラス: マップ
レアリティ: レア
Befuddling Frontier
Valdo Map
--------
報酬: フォイル 魅惑
アイテムレベル: 100
""",
])
def test_all_map_variants_hide_item_level_chip(qapp, text):
    window = PoetoreWindow()
    try:
        item = parse_item_text(text)
        assert item.category == "map"
        window._configure_item_level(item)
        assert window.item_level_tag.isHidden()
        assert window._selected_item_level_range() == (None, None)
    finally:
        window.close()


def test_filter_chips_follow_awakened_order_in_shared_flow_layout(qapp):
    window = PoetoreWindow()
    try:
        assert tuple(name for name, _widget in window._filter_chips) == (
            "links", "nightmare_map", "map_tier", "completion_reward", "area_level", "heist_wings",
            "heist_job", "heist_target", "cluster_enchant",
            "cluster_passives", "cluster_sockets", "blighted", "item_level",
            "base_percentile", "gem_variant", "gem_level", "quality",
            "influence_shaper", "influence_elder", "influence_crusader",
            "influence_hunter", "influence_redeemer", "influence_warlord",
            "influence_eater", "influence_exarch",
            "magic_rarity", "unidentified", "veiled", "foil", "mirrored", "split",
        )
        assert window.filter_chip_layout.ordered_widgets() == tuple(
            widget for _name, widget in window._filter_chips
        )
    finally:
        window.close()


def test_cross_category_transitions_clear_chips_notice_and_restore_preset(qapp):
    window = PoetoreWindow()
    try:
        samples = (
            ("""Item Class: Skill Gems\nRarity: Gem\nArc\n--------\nLevel: 20\nQuality: +20%\n""", "専用検索"),
            ("""アイテムクラス: マップ\nレアリティ: レア\nTest\nMap (Tier 16)\n--------\nアイテムレベル: 85\n""", "専用検索"),
            ("""Item Class: Two Hand Swords\nRarity: Rare\nTest\nReaver Sword\n--------\nItem Level: 85\n""", "完成品"),
            ("""アイテムクラス: その他マップアイテム\nレアリティ: カレンシー\nアルティメイタムの刻印\n""", "専用検索"),
        )
        with patch("src.poetore.ui.resolve_trade_stat_filters", return_value=()):
            for text, preset_label in samples:
                window.input_edit.setPlainText(text)
                window.parse_current_text()
                assert window.trade_preset_combo.currentText() == preset_label
        assert window.gem_level_tag.isHidden()
        assert window.gem_quality_tag.isHidden()
        assert window.map_tier_chip.isHidden()
        assert not window.search_scope_notice.isHidden()

        window.input_edit.setPlainText(samples[2][0])
        with patch("src.poetore.ui.resolve_trade_stat_filters", return_value=()):
            window.parse_current_text()
        assert window.search_scope_notice.isHidden()
        assert window.trade_preset_combo.currentText() == "完成品"
        assert window.map_tier_chip.isHidden()
    finally:
        window.close()


def test_windows_acceptance_csv_has_complete_ordered_cases():
    path = Path("docs/poetore-windows-acceptance-tests.csv")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 42
    assert len({row["ID"] for row in rows}) == len(rows)
    assert rows[-1]["ID"] == "WIN-047"
    required = {"ID", "区分", "優先度", "前提条件", "テストデータ", "手順", "期待結果", "結果", "証跡", "備考"}
    assert set(rows[0]) == required
    assert all(row["手順"] and row["期待結果"] for row in rows)


def test_filter_chip_flow_wraps_visible_chips(qapp):
    window = PoetoreWindow()
    try:
        for _name, chip in window._filter_chips[:9]:
            chip.show()
        window.filter_chip_layout.setGeometry(QRect(0, 0, 320, 200))
        rows = {chip.geometry().y() for _name, chip in window._filter_chips[:9]}
        assert len(rows) >= 2
        assert window.filter_chip_layout.heightForWidth(320) > max(
            chip.sizeHint().height() for _name, chip in window._filter_chips[:9]
        )
    finally:
        window.close()


def test_poe_ninja_placeholder_sits_between_header_and_filter_chips(qapp):
    window = PoetoreWindow()
    try:
        panel_layout = window._panel.layout()
        header_index = panel_layout.indexOf(window.item_header)
        ninja_index = panel_layout.indexOf(window.poe_ninja_price_panel)
        chips_index = panel_layout.indexOf(window.filter_chip_container)
        assert header_index < ninja_index < chips_index
        assert window.poe_ninja_price_panel.isHidden()
        assert window.poe_ninja_price_value.text() == "—"
        assert window.poe_ninja_trend_placeholder.size() == QSize(116, 24)
    finally:
        window.close()


def test_poe_ninja_price_panel_renders_price_trend_and_link(qapp):
    window = PoetoreWindow()
    try:
        key = ("item", "Standard", "Mageblood", "Heavy Belt")
        window._poe_ninja_item_key = key
        price = PoeNinjaPrice(
            "Mageblood", "Heavy Belt", 40000, (0, 1, 2, 3, 4, 5, 6),
            "https://poe.ninja/example", 200,
        )
        window._show_poe_ninja_price(key, price)
        assert not window.poe_ninja_price_panel.isHidden()
        assert window.poe_ninja_price_value.text() == "200"
        assert not window.poe_ninja_currency_icon.pixmap().isNull()
        assert window.poe_ninja_currency_icon.toolTip() == "Divine Orb"
        assert window.poe_ninja_price_multiplier.text() == "×"
        assert "7日推移" in window.poe_ninja_trend_label.text()
        assert window.poe_ninja_trend_chart._points == (0, 1, 2, 3, 4, 5, 6)
        assert window._last_poe_ninja_url == "https://poe.ninja/example"

        window._hide_poe_ninja_price(key)
        assert window.poe_ninja_price_panel.isHidden()
    finally:
        window.close()


def test_poe_ninja_price_panel_uses_chaos_icon_for_small_price(qapp):
    window = PoetoreWindow()
    try:
        key = ("item", "Standard", "Arc", "Arc")
        window._poe_ninja_item_key = key
        window._show_poe_ninja_price(
            key,
            PoeNinjaPrice("Arc", None, 10, (), "https://poe.ninja/example", 200),
        )
        assert window.poe_ninja_price_value.text() == "10"
        assert not window.poe_ninja_currency_icon.pixmap().isNull()
        assert window.poe_ninja_currency_icon.toolTip() == "Chaos Orb"
    finally:
        window.close()


def test_poe2_currency_icon_names_use_supplied_assets():
    assert _price_currency_icon_filename("divine", "poe2") == "DivineOrb2.png"
    assert _price_currency_icon_filename("chaos", "poe2") == "ChaosOrb2.png"
    assert _price_currency_icon_filename("exalted", "poe2") == "ExaltedOrb2.png"
    assert _price_currency_icon_filename("divine", "poe1") == "DivineOrb.png"


def test_poe2_poe_ninja_panel_renders_supplied_divine_icon(qapp):
    window = PoetoreWindow(app_config={"poe_version": "poe2"})
    try:
        key = ("item", "Runes of Aldur", "Mageblood", "Utility Belt")
        window._poe_ninja_item_key = key
        window._show_poe_ninja_price(
            key,
            PoeNinjaPrice("Mageblood", "Utility Belt", 35000, (), "https://poe.ninja/example", 100),
        )
        icon_path = Path(__file__).parents[1] / "assets" / "icons" / "DivineOrb2.png"
        expected = QPixmap(str(icon_path)).scaled(
            26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        assert window.poe_ninja_currency_icon.pixmap().toImage() == expected.toImage()
    finally:
        window.close()


def test_related_items_panel_renders_materials_and_rewards(qapp):
    window = PoetoreWindow()
    try:
        key = ("item", "Standard", "", "")
        window._poe_ninja_item_key = key
        price = PoeNinjaPrice(
            "Blessing of Chayula", None, 12, (), "https://poe.ninja/example", 200,
        )
        window._show_related_items(key, {
            "current": ("ITEM", "chayula's breachstone"),
            "query": (({
                "namespace": "ITEM", "name": "Chayula's Breachstone",
                "display_name": "チャユラのブリーチストーン",
            }, None),),
            "items": (({
                "namespace": "ITEM", "name": "Blessing of Chayula",
                "display_name": "チャユラの祝福",
            }, price),),
        })
        assert not window.related_items_panel.isHidden()
        assert window.related_items_tree.topLevelItemCount() == 2
        assert (
            window.related_items_tree.topLevelItem(0).child(0).text(0)
            == "● チャユラのブリーチストーン"
        )
        assert (
            window.related_items_tree.topLevelItem(1).child(0).text(0)
            == "チャユラの祝福"
        )
        assert window.related_items_tree.topLevelItem(1).child(0).text(1) == "12 chaos"
        assert window.related_items_tree.minimumHeight() == 210
        assert window.related_items_tree.maximumHeight() == 210
        assert window.price_list.minimumHeight() == 224
        window.show()
        qapp.processEvents()
        assert window.related_items_tree.height() == 210
        assert window.related_items_panel.height() >= 200

        window._hide_related_items(key)
        assert window.related_items_tree.minimumHeight() == 0
        assert window.price_list.minimumHeight() == 434
    finally:
        window.close()


def test_related_items_panel_uses_specific_beastcraft_label(qapp):
    window = PoetoreWindow()
    try:
        key = ("item", "Standard", "Watcher's Eye", "Prismatic Jewel")
        window._poe_ninja_item_key = key
        window._show_related_items(key, {
            "current": ("UNIQUE", "watcher's eye"),
            "query_label": "ビーストクラフト素材：Modをリロール",
            "query": (({
                "namespace": "CAPTURED_BEAST", "name": "Wild Hellion Alpha",
                "display_name": "ワイルド・ヘリオン・アルファ",
            }, PoeNinjaPrice(
                "Wild Hellion Alpha", None, 42, (),
                "https://poe.ninja/example", 200,
            )),),
            "items": (),
        })

        parent = window.related_items_tree.topLevelItem(0)
        assert parent.text(0) == "ビーストクラフト素材：Modをリロール"
        assert parent.child(0).text(0) == "ワイルド・ヘリオン・アルファ"
        assert parent.child(0).text(1) == "42 chaos"
    finally:
        window.close()


def test_divine_rate_button_builds_awakened_style_conversion_menu(qapp):
    window = PoetoreWindow()
    try:
        window._divine_rate_key = "Standard"
        window._show_divine_rate("Standard", 174.4)

        assert not window.divine_rate_button.isHidden()
        assert window.divine_rate_button.text() == "⇄ 174"
        labels = [action.text() for action in window.divine_rate_menu.actions()]
        assert labels == [
            "0.1 div  →  17 c",
            "0.2 div  →  35 c",
            "0.3 div  →  52 c",
            "0.4 div  →  70 c",
            "0.5 div  →  87 c",
            "0.6 div  →  105 c",
            "0.7 div  →  122 c",
            "0.8 div  →  140 c",
            "0.9 div  →  157 c",
        ]
        for action in window.divine_rate_menu.actions():
            row = action.defaultWidget()
            icons = [
                label for label in row.findChildren(QLabel)
                if not label.pixmap().isNull()
            ]
            assert len(icons) == 2
    finally:
        window.close()


def test_logbook_area_switch_uses_custom_checkboxes_without_native_indicators(qapp):
    window = PoetoreWindow()
    try:
        filters = (
            TradeStatFilter(
                "pseudo.pseudo_logbook_faction_1", "エリア1", None, "pseudo",
                True, selection_reason="logbook-area:1",
            ),
            TradeStatFilter(
                "pseudo.pseudo_logbook_faction_2", "エリア2", None, "pseudo",
                False, selection_reason="logbook-area:2",
            ),
        )
        window._populate_stat_filters(filters)
        window._logbook_area_groups = ((1, "エリア1"), (2, "エリア2"))

        window._logbook_area_changed(1)

        rows = [
            window.mod_filter_tree.topLevelItem(index)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        checkboxes = [
            window.mod_filter_tree.itemWidget(
                row, 0,
            ).findChild(QCheckBox, "modFilterCheckbox")
            for row in rows
        ]
        assert [checkbox.isChecked() for checkbox in checkboxes] == [False, True]
        assert [row.checkState(0) for row in rows] == [Qt.Unchecked, Qt.Unchecked]
        assert [row.data(0, Qt.UserRole + 5) for row in rows] == [False, True]
    finally:
        window.close()


def test_logbook_area_switch_has_dedicated_row_and_fits_long_labels(qapp):
    window = PoetoreWindow()
    try:
        groups = (
            (1, "断たれた円環のドルイド"),
            (2, "太陽の騎士団"),
        )
        window._logbook_area_groups = groups
        window.logbook_area_selector.setLabels(
            tuple(f"エリア{index + 1}：{label}" for index, (_group, label)
                  in enumerate(groups))
        )
        window.logbook_area_container.show()

        panel_layout = window._panel.layout()
        chip_index = panel_layout.indexOf(window.filter_chip_container)
        area_index = panel_layout.indexOf(window.logbook_area_container)
        assert area_index == chip_index + 2
        assert panel_layout.itemAt(area_index - 1).layout() is not None
        assert window.logbook_area_selector.parentWidget() is window.logbook_area_container
        assert window.logbook_area_selector not in window.filter_chip_layout.ordered_widgets()
        for button in window.logbook_area_selector._buttons:
            required = button.fontMetrics().horizontalAdvance(button.text()) + 24
            assert button.minimumWidth() >= required
    finally:
        window.close()


def test_stale_divine_rate_result_does_not_replace_current_league(qapp):
    window = PoetoreWindow()
    try:
        window._divine_rate_key = "Current"
        window._show_divine_rate("Old", 200)
        assert window.divine_rate_button.text() != "⇄ 200"
    finally:
        window.close()


@pytest.mark.parametrize(("item_level", "minimum", "maximum"), [
    (49, "1", "49"),
    (50, "50", "67"),
    (72, "68", "74"),
    (80, "75", ""),
    (84, "84", ""),
])
def test_cluster_item_level_tag_uses_awakened_bracket(qapp, item_level, minimum, maximum):
    window = PoetoreWindow()
    try:
        item = parse_item_text(f"""Item Class: Cluster Jewels
Rarity: Rare
Test Cluster
Large Cluster Jewel
--------
Item Level: {item_level}
""")
        window._parsed_item = item
        window._trade_base_type = "Large Cluster Jewel"
        window._configure_trade_presets(item)
        window._configure_item_level(item)

        assert window.item_level_edit.text() == minimum
        assert not window.item_level_max_edit.isHidden()
        assert window.item_level_max_edit.text() == maximum
        assert window._selected_item_level_range() == (None, None)

        window.trade_preset_combo.setCurrentIndex(1)
        assert window._selected_item_level_range() == (
            int(minimum), int(maximum) if maximum else None,
        )
    finally:
        window.close()


def test_gem_level_chip_uses_read_level_and_can_be_toggled_and_edited(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""アイテムクラス: サポートジェム
レアリティ: ジェム
範囲ダメージ集中サポート
--------
レベル: 3
""")
        window._configure_gem_level(item)

        assert not window.gem_level_tag.isHidden()
        assert window.gem_level_edit.text() == "3"
        assert window._selected_gem_level() == 3
        assert window.gem_level_toggle.text() == "☑ ジェムLv："

        window.gem_level_toggle.click()
        assert window._selected_gem_level() is None
        assert window.gem_level_edit.font().strikeOut()

        window.gem_level_edit.setFocus()
        window.gem_level_edit.selectAll()
        QTest.keyClicks(window.gem_level_edit, "5")
        assert window._selected_gem_level() == 5
        assert not window.gem_level_edit.font().strikeOut()
    finally:
        window.close()


def test_gem_quality_chip_uses_read_quality_and_can_be_toggled_and_edited(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""アイテムクラス: スキルジェム
レアリティ: ジェム
アーク
--------
レベル: 20
品質: +16%
""")
        window._parsed_item = item
        window._configure_quality(item)

        assert not window.gem_quality_tag.isHidden()
        assert window.gem_quality_edit.text() == "16"
        assert window._selected_quality() == 16
        assert window.gem_quality_toggle.text() == "☑ 品質："

        window.gem_quality_toggle.click()
        assert window._selected_quality() is None
        assert window.gem_quality_edit.font().strikeOut()

        window.gem_quality_edit.setFocus()
        window.gem_quality_edit.selectAll()
        QTest.keyClicks(window.gem_quality_edit, "20")
        assert window._selected_quality() == 20
        assert not window.gem_quality_edit.font().strikeOut()

        window._populate_stat_filters((TradeStatFilter(
            "property.quality", "品質", 20.0, "gem", True,
        ),))
        assert window.mod_filter_tree.topLevelItemCount() == 0
    finally:
        window.close()


@pytest.mark.parametrize(("quality", "metadata", "visible", "enabled"), [
    (0, {"max_level": 20}, False, False),
    (15, {"max_level": 20}, True, False),
    (16, {"max_level": 20}, True, True),
    (19, {"max_level": 20, "transfigured": True}, True, False),
    (20, {"max_level": 20, "transfigured": True}, True, True),
    (1, {"max_level": 1}, True, True),
])
def test_gem_quality_chip_initial_state_matches_awakened(
    qapp, quality, metadata, visible, enabled,
):
    window = PoetoreWindow()
    try:
        item = parse_item_text(f"""アイテムクラス: スキルジェム
レアリティ: ジェム
テストジェム
--------
レベル: 1
品質: +{quality}%
""")
        with patch("src.poetore.ui.gem_metadata", return_value=metadata):
            window._configure_quality(item)

        assert window.gem_quality_tag.isHidden() is (not visible)
        assert window._selected_quality() == (quality if enabled else None)
        assert window.gem_quality_tag.property("active") is enabled
    finally:
        window.close()


def test_non_gem_quality_chip_keeps_exceptional_quality_in_finished_search(qapp):
    window = PoetoreWindow()
    try:
        armour = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Quality: +21%
Item Level: 86
""")
        window._parsed_item = armour
        window._configure_trade_presets(armour)
        window._configure_quality(armour)
        assert not window.gem_quality_tag.isHidden()
        assert window._selected_quality() == 21

        window.trade_preset_combo.setCurrentIndex(1)
        assert not window.gem_quality_tag.isHidden()
        assert window._selected_quality() == 21

        accessory = parse_item_text("""Item Class: Rings
Rarity: Rare
Test Ring
Ruby Ring
--------
Quality: +20%
Item Level: 86
""")
        window._parsed_item = accessory
        window._configure_trade_presets(accessory)
        window._configure_quality(accessory)
        assert window.gem_quality_tag.isHidden()
        window.trade_preset_combo.setCurrentIndex(1)
        assert not window.gem_quality_tag.isHidden()
        assert window._selected_quality() is None

        accessory25 = replace(
            accessory,
            raw_text=accessory.raw_text + "\n25",
            properties={**accessory.properties, "Quality": "+25%"},
        )
        window._parsed_item = accessory25
        window._configure_trade_presets(accessory25)
        window._configure_quality(accessory25)
        assert not window.gem_quality_tag.isHidden()
        assert window.gem_quality_edit.text() == "25"
        assert window._selected_quality() == 25

        flask20 = parse_item_text("""Item Class: Utility Flasks
Rarity: Magic
Test Flask
Granite Flask
--------
Quality: +20%
Item Level: 84
""")
        window._parsed_item = flask20
        window._configure_quality(flask20)
        assert not window.gem_quality_tag.isHidden()
        assert window.gem_quality_edit.text() == "20"
        assert window._selected_quality() is None

        flask21 = replace(flask20, raw_text=flask20.raw_text + "\n21", properties={
            **flask20.properties, "品質": "+21%",
        })
        window._parsed_item = flask21
        window._configure_quality(flask21)
        assert window._selected_quality() == 21
    finally:
        window.close()


def test_poe2_weapon_quality_20_is_visible_but_initially_disabled(qapp):
    window = PoetoreWindow(app_config={"poe_version": "poe2"})
    try:
        from src.poetore.poe2.parser import parse_item_text as parse_poe2_item_text

        text = (Path(__file__).parent / "fixtures" / "poe2" / "rare_spear_ja.txt").read_text(
            encoding="utf-8"
        )
        item = parse_poe2_item_text(text)
        window._configure_quality(item)
        filters = window._resolved_trade_filters(item, "finished")
        flat = next(row for row in filters if "物理ダメージを追加" in row.text)

        assert not window.gem_quality_tag.isHidden()
        assert window.gem_quality_edit.text() == "20"
        assert window._selected_quality() is None
        assert window.gem_quality_toggle.text() == "☐ 品質："
        assert flat.min_value == 32.0
        assert flat.read_value == 32.0

        window.gem_quality_toggle.click()
        assert window._selected_quality() == 20
    finally:
        window.close()


def test_armour_base_percentile_is_an_editable_base_only_chip(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""アイテムクラス: 盾
レアリティ: レア
Test Guard
Cardinal Round Shield
--------
ブロック率: 25%
アーマー: 220
回避力: 220
--------
アイテムレベル: 86
""")
        window._parsed_item = item
        window._trade_base_type = "Cardinal Round Shield"
        window._configure_trade_presets(item)
        window._configure_special_filter_chips(item)
        assert window.base_percentile_chip.isHidden()

        window.trade_preset_combo.setCurrentIndex(1)
        assert not window.base_percentile_chip.isHidden()
        assert not window.base_percentile_chip.isActive()
        assert window.base_percentile_chip.suffix_label.text() == "%"
        minimum, maximum = window.base_percentile_chip.values()
        assert minimum is not None
        assert maximum is None

        window.base_percentile_chip.toggle.click()
        assert window.base_percentile_chip.isActive()
        assert any(
            row.stat_id == "property.base_percentile"
            for row in window._selected_special_chip_filters()
        )

        window.base_percentile_chip.minimum_edit.setFocus()
        window.base_percentile_chip.minimum_edit.selectAll()
        QTest.keyClicks(window.base_percentile_chip.minimum_edit, "80")
        selected = window._selected_special_chip_filters()
        percentile = next(row for row in selected if row.stat_id == "property.base_percentile")
        assert percentile.min_value == 80
    finally:
        window.close()


@pytest.mark.parametrize(("item_class", "base_type"), [
    ("鎧", "Sacred Chainmail"),
    ("弓", "Spine Bow"),
    ("両手剣", "Exquisite Blade"),
    ("スタッフ", "Gnarled Branch"),
    ("ワンド", "Imbued Wand"),
])
def test_link_chip_is_shown_for_socketed_weapons_and_armour(
    qapp, item_class, base_type,
):
    window = PoetoreWindow()
    try:
        item = parse_item_text(f"""アイテムクラス: {item_class}
レアリティ: レア
Test Item
{base_type}
--------
ソケット: R-R-R-G-B-B
--------
アイテムレベル: 86
""")
        window._parsed_item = item
        window._configure_links(item)

        assert not window.links_tag.isHidden()
        assert window._selected_links() == 6
        window.links_toggle.click()
        assert window._selected_links() is None
        window.links_edit.setFocus()
        window.links_edit.selectAll()
        QTest.keyClicks(window.links_edit, "5")
        assert window._selected_links() == 5
    finally:
        window.close()


def test_link_chip_always_replaces_link_and_socket_rows_for_equipment(qapp):
    window = PoetoreWindow()
    try:
        six_link_armour = parse_item_text("""アイテムクラス: 鎧
レアリティ: レア
Test Item
Sacred Chainmail
--------
ソケット: R-R-R-G-B-B
--------
アイテムレベル: 86
""")
        window._parsed_item = six_link_armour
        window._configure_links(six_link_armour)
        window._populate_stat_filters((
            TradeStatFilter("property.sockets", "ソケット数", 6.0, "socket", True),
            TradeStatFilter("property.links", "最大リンク数", 6.0, "socket", False),
        ))
        assert not window.links_tag.isHidden()
        assert window.mod_filter_tree.topLevelItemCount() == 0

        three_socket_armour = parse_item_text("""アイテムクラス: 鎧
レアリティ: レア
Test Item
Sacred Chainmail
--------
ソケット: R-G B
--------
アイテムレベル: 86
""")
        window._parsed_item = three_socket_armour
        window._configure_links(three_socket_armour)
        window._populate_stat_filters((
            TradeStatFilter("property.sockets", "ソケット数", 3.0, "socket", False),
            TradeStatFilter("property.links", "最大リンク数", 2.0, "socket", False),
        ))
        assert not window.links_tag.isHidden()
        assert window.links_edit.text() == "2"
        assert window._selected_links() is None
        stat_ids = [
            window.mod_filter_tree.topLevelItem(index).data(0, Qt.UserRole)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        assert "property.sockets" not in stat_ids
        assert "property.links" not in stat_ids
    finally:
        window.close()


@pytest.mark.parametrize(("socket_text", "value", "enabled"), [
    ("R-R-R-R-R", 5, True),
    ("R-R-R-R-R-R", 6, True),
    ("R-R-R-R G", 4, False),
    ("R-G B", 2, False),
])
def test_link_chip_defaults_only_five_and_six_links_on(
    qapp, socket_text, value, enabled,
):
    window = PoetoreWindow()
    try:
        item = parse_item_text(f"""Item Class: Body Armours
Rarity: Rare
Test Item
Sacred Chainmail
--------
Sockets: {socket_text}
--------
Item Level: 86
""")
        window._configure_links(item)
        assert not window.links_tag.isHidden()
        assert window.links_edit.text() == str(value)
        assert window._selected_links() == (value if enabled else None)
    finally:
        window.close()


def test_influence_chips_match_awakened_finished_and_exact_states(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Shell
Vaal Regalia
--------
Item Level: 85
--------
Shaper Item
Elder Item
""")
        window._parsed_item = item
        window._configure_trade_presets(item)
        window._configure_influence_chips(item)

        assert not window.influence_chips["shaper"].isHidden()
        assert not window.influence_chips["elder"].isHidden()
        assert not window.influence_chips["shaper"].icon().isNull()
        assert window.influence_chips["shaper"].iconSize().width() == 38
        assert window.influence_chips["shaper"].text() == "Shaper"
        assert not window.influence_chips["elder"].icon().isNull()
        assert window._selected_influence_filters() == ()

        window.trade_preset_combo.setCurrentIndex(1)
        selected = window._selected_influence_filters()
        assert {row.stat_id for row in selected} == {
            "pseudo.pseudo_has_shaper_influence",
            "pseudo.pseudo_has_elder_influence",
        }

        window.influence_chips["elder"].click()
        selected = window._selected_influence_filters()
        assert [row.stat_id for row in selected] == [
            "pseudo.pseudo_has_shaper_influence",
        ]

        three = replace(item, raw_text=item.raw_text + "\nthree", flags=(
            "influence:shaper", "influence:elder", "influence:hunter",
        ))
        window._configure_influence_chips(three)
        assert all(button.isHidden() for button in window.influence_chips.values())
    finally:
        window.close()


def test_eldritch_influence_chips_are_visible_enabled_and_independent(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""アイテムクラス: 靴
レアリティ: レア
勝利の拍車
賢者の履物
--------
アイテムレベル: 83
--------
シアリング・エグザークのアイテム
イーター・オブ・ワールズのアイテム
""")
        window._parsed_item = item
        window._configure_trade_presets(item)
        window._configure_influence_chips(item)

        eater = window.influence_chips["eater"]
        exarch = window.influence_chips["exarch"]
        assert not eater.isHidden()
        assert not exarch.isHidden()
        assert not eater.icon().isNull()
        assert not exarch.icon().isNull()
        assert eater.text() == "Eater"
        assert exarch.text() == "Exarch"
        assert window._selected_eldritch_influences() == (True, True)

        eater.click()
        assert window._selected_eldritch_influences() == (True, False)
        exarch.click()
        assert window._selected_eldritch_influences() == (False, False)
    finally:
        window.close()


def test_corrupted_item_defaults_to_corrupted_only(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text("""Item Class: Rings
Rarity: Rare
Test Ring
Amethyst Ring
--------
Item Level: 84
--------
Corrupted
""")
        window._configure_item_state_filters(item)
        assert window.corrupted_combo.currentText() == "コラプトのみ"
        assert window.corrupted_combo.currentData() == "only"
        assert window.corrupted_combo.property("alert") is True
    finally:
        window.close()


def test_gem_allows_three_state_corruption_filter(qapp):
    window = PoetoreWindow()
    try:
        gem = parse_item_text("""Item Class: Support Gems
Rarity: Gem
Volatility Support
--------
Level: 20
Quality: +20% (augmented)
--------
Supports attack skills.
""")
        window._configure_item_state_filters(gem)
        assert gem.category == "gem"
        assert window.corrupted_combo.isEnabled()
        assert window.corrupted_combo.currentData() is False

        window.corrupted_combo.click()
        assert window.corrupted_combo.currentData() is True
        window.corrupted_combo.click()
        assert window.corrupted_combo.currentData() == "only"
    finally:
        window.close()


@pytest.mark.parametrize("category", [
    "map", "flask", "tincture", "heist_equipment", "sanctum_relic", "charm", "idol",
])
def test_requested_special_categories_show_corruption_filter(qapp, category):
    window = PoetoreWindow()
    try:
        item = ParsedItem(
            item_class="Test Items", rarity="Rare", name="Test Item",
            base_type="Test Item", category=category, raw_text=f"special:{category}",
        )
        window._configure_item_state_filters(item)
        assert not window.corrupted_combo.isHidden()
        assert window.corrupted_combo.isEnabled()
    finally:
        window.close()


@pytest.mark.parametrize("category", [
    "invitation", "heist_contract", "heist_blueprint", "memory_line",
    "expedition_logbook", "incursion_item", "graft", "captured_beast",
    "currency", "divination_card", "unknown",
])
def test_unsupported_categories_hide_corruption_filter(qapp, category):
    window = PoetoreWindow()
    try:
        item = ParsedItem(
            item_class="Test Items", rarity="Rare", name="Test Item",
            base_type="Test Item", category=category, raw_text=f"unsupported:{category}",
        )
        window._configure_item_state_filters(item)
        assert window.corrupted_combo.isHidden()
    finally:
        window.close()


def test_current_japanese_captured_beast_shows_species_only_without_extra_filters(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: スタック可能カレンシー
レアリティ: レア
Bloodmauler the Drooling
Farric Lynx Alpha
--------
ジーナス: ヤマネコ
グループ: ネコ類
ファミリー: 原生林
--------
アイテムレベル: 83
--------
{ プレフィックスモッド「潰滅する」 (ティア: 1) }
ヒット時破砕
{ プレフィックスモッド「軽快な」 (ティア: 1) }
素早い
{ モンスターモッド }
ファルウルの存在感
{ モンスターモッド }
サテュロスの嵐
{ モンスターモッド }
霊体の猛撃
{ モンスターモッド }
血の祭壇で生贄にされた時に20%の確率で消費されない
--------
右クリックしてこのモンスターを怪獣園に追加する。
""")
        window.parse_current_text()

        assert window._parsed_item.category == "captured_beast"
        assert window.item_name_label.text() == "Farric Lynx Alpha"
        assert window.item_level_tag.isHidden()
        assert window.mod_filter_tree.topLevelItemCount() == 0
        assert window.mod_warning.isHidden()
    finally:
        window.close()


def test_header_shows_scope_toggle_for_nonunique_weapon_armour_and_accessory(qapp):
    window = PoetoreWindow()
    try:
        armour = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Item Level: 94
""")
        window._update_item_header(armour)
        assert window.item_name_label.isHidden()
        assert not window.base_scope_toggle.isHidden()
        assert window.base_scope_toggle.itemText(0) == "Sacred Chainmail"
        assert window.base_scope_toggle.itemText(1) == "すべての鎧"
        assert window.base_scope_toggle.currentData() is True

        window.base_scope_toggle.setCurrentIndex(1)
        assert window.base_scope_toggle.currentData() is False

        unique = replace(armour, rarity="Unique", name="Test Unique")
        window._update_item_header(unique)
        assert not window.item_name_label.isHidden()
        assert window.item_name_label.text() == "Test Unique"
        assert window.base_scope_toggle.isHidden()
        assert not hasattr(window, "item_base_label")
    finally:
        window.close()


def test_header_removes_affixes_only_for_nonunique_equipment(qapp):
    window = PoetoreWindow()
    try:
        wand = parse_item_text("""アイテムクラス: ワンド
レアリティ: マジック
酹薬の 痛憤の 浸潤のワンド
--------
アイテムレベル: 84
""")
        window._trade_base_type = "Imbued Wand"
        window._update_item_header(wand)
        assert window.base_scope_toggle.itemText(0) == "浸潤のワンド"

        ring = parse_item_text("""アイテムクラス: 指輪
レアリティ: マジック
火炎の アメジストの指輪
--------
アイテムレベル: 84
""")
        window._update_item_header(ring)
        assert window.item_name_label.isHidden()
        assert not window.base_scope_toggle.isHidden()
        assert window.base_scope_toggle.itemText(0) == "アメジストの指輪"
        assert window.base_scope_toggle.itemText(1) == "すべての指輪"

        for item_class, base_type, expected in (
            ("Amulets", "Gold Amulet", "すべてのアミュレット"),
            ("Belts", "Leather Belt", "すべてのベルト"),
        ):
            accessory = replace(
                ring, item_class=item_class, name=base_type, base_type=base_type,
                raw_text=f"{item_class}:{base_type}",
            )
            window._trade_base_type = base_type
            window._update_item_header(accessory)
            assert window.base_scope_toggle.itemText(1) == expected

        flask = replace(ring, category="flask", item_class="Utility Flasks")
        window._update_item_header(flask)
        assert window.item_name_label.text() == "火炎の アメジストの指輪"

        unique = replace(wand, rarity="ユニーク")
        window._update_item_header(unique)
        assert window.item_name_label.text() == "酹薬の 痛憤の 浸潤のワンド"
    finally:
        window.close()


def test_nonunique_jewels_use_category_search_but_cluster_and_unique_stay_exact(qapp):
    window = PoetoreWindow()
    try:
        jewel = ParsedItem(
            item_class="Jewels", rarity="Rare", name="Test Jewel",
            base_type="Crimson Jewel", category="jewel", raw_text="jewel",
        )
        abyss = replace(
            jewel, item_class="Abyss Jewels", base_type="Ghastly Eye Jewel",
            category="abyss_jewel", raw_text="abyss",
        )
        cluster = replace(
            jewel, item_class="Cluster Jewels", base_type="Large Cluster Jewel",
            category="cluster_jewel", raw_text="cluster",
        )
        unique = replace(jewel, rarity="Unique", raw_text="unique")
        assert window._searches_exact_base_type(jewel) is False
        assert window._searches_exact_base_type(abyss) is False
        assert window._searches_exact_base_type(cluster) is True
        assert window._searches_exact_base_type(unique) is True
    finally:
        window.close()


@pytest.mark.parametrize(("text", "expected_stat_id"), [
    ("""アイテムクラス: ユーティリティフラスコ
レアリティ: マジック
Abecedarian's Jade Flask of Depletion
--------
アイテムレベル: 42
--------
{ プレフィックスモッド「初学者の」 (ティア: 3) }
持続時間が38(38-33)%減少する
効果が25%増加する
{ サフィックスモッド 「消費の」 (ティア: 4) }
効果中はスペルダメージの0.5%をエナジーシールドとしてリーチする
""", "explicit.stat_1256719186"),
    ("""アイテムクラス: チンキ
レアリティ: マジック
Tenacious Blood Sap Tincture of Battering
--------
アイテムレベル: 47
--------
{ プレフィックスモッド「固く握った」 (ティア: 3) }
マナ燃焼レートが18(20-18)%減少する
{ サフィックスモッド 「殴打の」 (ティア: 3) }
近接武器は30(30-39)%の確率で敵物理ダメージ軽減を無視する
""", "explicit.stat_116232170"),
    ("""アイテムクラス: チンキ
レアリティ: マジック
Tenacious Blood Sap Tincture
--------
アイテムレベル: 84
--------
{ プレフィックスモッド }
マナ燃焼レートが45(42-46)%増加する
""", "explicit.stat_116232170"),
    ("""アイテムクラス: チンキ
レアリティ: マジック
強い 液状化の 血の樹液のチンキ
--------
アイテムレベル: 84
--------
{ プレフィックスモッド「強い」 (ティア: 3) }
効果が35%増加する
マナ燃焼レートが48(47-51)%増加する
{ サフィックスモッド 「液状化の」 (ティア: 3) }
近接武器によるアタックの継続ダメージ倍率 +23(19-23)%
""", "explicit.stat_3529940209"),
    ("""アイテムクラス: ユーティリティフラスコ
レアリティ: ユニーク
オロスの決意
ルビーフラスコ
--------
アイテムレベル: 84
--------
{ ユニークモッド }
持続時間が36(39-35)%低下する
""", "explicit.stat_1256719186"),
])
def test_current_japanese_flask_and_tincture_have_no_unresolved_warning(
    qapp, text, expected_stat_id,
):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText(text)
        window.parse_current_text()

        rows = [
            window.mod_filter_tree.topLevelItem(index).data(0, Qt.UserRole + 4)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        assert expected_stat_id in {row.stat_id for row in rows}
        assert window.mod_warning.isHidden()
        assert window.item_level_tag.property("active") is False
    finally:
        window.close()


def test_flask_instilling_enchantment_is_hidden_from_search_conditions(qapp):
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText("""アイテムクラス: ユーティリティフラスコ
レアリティ: マジック
検査者の 虹の シルバーフラスコ
--------
品質: +17% (augmented)
8.90 (augmented)秒間持続
使用時に60中40チャージを消費
現在0チャージ
猛攻
--------
装備要求:
レベル: 64
--------
アイテムレベル: 85
--------
チャージがフルになった時に使用される (enchant)
--------
{ プレフィックスモッド「検査者の」 (ティア: 3) }
持続時間が27(26-30)%増加する
{ サフィックスモッド 「虹の」 (ティア: 1) }
効果中は20(18-20)%の元素耐性が追加される
--------
右クリックして飲む。腰につけているときだけチャージを貯めることができる。
""")
        window.parse_current_text()

        enchant_item = next(
            window.mod_filter_tree.topLevelItem(index)
            for index in range(window.mod_filter_tree.topLevelItemCount())
            if window.mod_filter_tree.topLevelItem(index).data(
                0, Qt.UserRole + 4,
            ).stat_id == "enchant.stat_3287581721"
        )
        enchant = enchant_item.data(0, Qt.UserRole + 4)
        assert enchant.text == "チャージがフルになった時に使用される (enchant)"
        assert enchant.enabled is False
        assert enchant_item.isHidden()
        assert window.mod_warning.isHidden()
    finally:
        window.close()


@pytest.mark.parametrize("metadata,name,expected", [
    ({}, "Fireball", "Variant：通常ジェム"),
    ({"vaal": True}, "Vaal Fireball", "Variant：ヴァールジェム"),
    ({}, "Awakened Added Fire Damage Support", "Variant：覚醒ジェム"),
    ({"transfigured": True}, "Fireball of Pelting", "Variant：変容ジェム"),
])
def test_gem_variant_is_shown_as_japanese_readonly_chip(qapp, metadata, name, expected):
    window = PoetoreWindow()
    try:
        item = ParsedItem("Skill Gems", "Gem", name, name, "gem", raw_text=name)
        window._trade_base_type = name
        with patch("src.poetore.ui.gem_metadata", return_value=metadata), \
             patch("src.poetore.ui.resolve_trade_stat_filters", return_value=()):
            window._configure_special_filter_chips(item)
        assert window.gem_variant_chip.text() == expected
        assert window.gem_variant_chip.isEnabled() is False
    finally:
        window.close()


def test_vaal_gem_detailed_copy_is_shown_as_vaal_variant_in_the_real_panel(qapp):
    text = """アイテムクラス: スキルジェム
レアリティ: ジェム
Molten Strike
--------
アタック, 投射物, 範囲効果, 近接, ストライク, 火, 連鎖, ヴァール
レベル: 1
--------
Vaal Molten Strike
--------
使用ごとの必要ソウル: 15
3回分保持可能
--------
コラプト状態
"""
    window = PoetoreWindow()
    try:
        detailed_item = parse_item_text(text)
        window._trade_base_type = detailed_item.base_type
        window.input_edit.setPlainText(text)
        window.parse_current_text()

        assert window._parsed_item.base_type == "Vaal Molten Strike"
        assert window.item_name_label.text() == "ヴァールモルテンストライク"
        assert window.gem_variant_chip.text() == "Variant：ヴァールジェム"
    finally:
        window.close()


def test_japanese_vaal_gem_copy_is_parsed_and_shown_as_vaal_grace(qapp):
    text = """アイテムクラス: スキルジェム
レアリティ: ジェム
グレース
--------
オーラ, スペル, 範囲効果, 持続時間, ヴァール
レベル: 1
リザーブ: 50% マナ
--------
使用者とその仲間に回避力を付与するオーラを纏う。
--------
ヴァールグレース
--------
クールダウン時間: 0.50秒
使用ごとの必要ソウル: 50
1回分保持可能
--------
基礎持続時間は6.00秒
--------
経験値: 1/118,383
--------
コラプト状態
"""
    window = PoetoreWindow()
    try:
        detailed_item = parse_item_text(text)
        window._trade_base_type = detailed_item.base_type
        window.input_edit.setPlainText(text)
        window.parse_current_text()

        assert window._parsed_item.base_type == "Vaal Grace"
        assert window.item_name_label.text() == "ヴァールグレース"
        assert window.gem_variant_chip.text() == "Variant：ヴァールジェム"
    finally:
        window.close()


def test_scrying_orb_header_includes_the_searched_map_area(qapp):
    text = """アイテムクラス: スタック可能カレンシー
レアリティ: カレンシー
透視のオーブ
--------
マップエリア: 岸辺
--------
アトラス上のマップを透視する
"""
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText(text)
        window.parse_current_text()
        assert window.item_name_label.text() == "透視のオーブ (岸辺)"
    finally:
        window.close()
