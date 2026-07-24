from unittest.mock import Mock, patch
from dataclasses import replace
from datetime import datetime, timezone
import csv
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QPushButton
import pytest

from src.poetore.ui import (
    PoetoreWindow, _UniqueRollSlider, _replace_filters_with_special_chips,
    show_poetore_window,
)
from src.poetore.window_position import PlacementContext
from src.poetore.trade import (
    PRESET_FINISHED, PriceListing, PriceResult, TradeLeague, TradeStatFilter,
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
        assert window.width() == 720
        assert window.minimumWidth() == 680
        assert window.height() == 1039
        assert window.price_list.minimumHeight() == 434
        assert window.trade_url_button.text() == "公式トレード  ↗"
        assert window.trade_url_button.toolTip() == "日本語公式Tradeをブラウザで開く"
        assert all(button.text() != "貼り付け" for button in window.findChildren(QPushButton))
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


def test_show_at_context_places_window_inward_from_cursor_side(qapp):
    window = PoetoreWindow()
    try:
        context = PlacementContext(QRect(100, 50, 1920, 1080), QPoint(1700, 400))
        with patch.object(window, "show"), patch.object(window, "raise_"), patch.object(
            window, "activateWindow"
        ):
            window.show_at_context(context)
        assert window.pos() == QPoint(634, 50)
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


def test_passive_hotkey_display_closes_only_for_outside_click(qapp):
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
        assert window.trade_league_combo.width() == 290
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
        ))
        assert [
            window.mod_filter_tree.topLevelItem(index).text(1)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ] == ["明示", "ファウルボーン", "疑似"]
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


def test_poetore_uses_wide_poena_theme_and_hides_debug_parse_area(qapp):
    window = PoetoreWindow()
    try:
        assert window.size().width() == 720
        assert window._panel.objectName() == "poetorePanel"
        assert not window._debug_parse_area.isVisible()
        assert window.mod_filter_tree.isColumnHidden(6)
        assert window.mod_filter_tree.columnCount() == 7
        assert window.mod_filter_tree.header().isHidden()
        assert window.mod_filter_tree.headerItem().text(2) == "ティア"
        assert window.mod_filter_tree.headerItem().text(6) == "詳細"
        assert "論理" not in [
            window.mod_filter_tree.headerItem().text(index)
            for index in range(window.mod_filter_tree.columnCount())
        ]
        assert "rgba(14, 14, 14, 246)" in window.styleSheet()
        assert "#b0ff7b" in window.styleSheet()
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
        filter_ids = {
            window.mod_filter_tree.topLevelItem(index).data(0, Qt.UserRole)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        }
        assert "property.physical_dps" in filter_ids
        assert "property.aps" in filter_ids
        assert "property.crit" in filter_ids
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
    assert [window.price_list.headerItem().text(i) for i in range(3)] == ["価格", "ilvl", "出品日時"]
    assert window.price_list.topLevelItem(0).text(0) == "4 chaos"
    assert window.price_list.topLevelItem(0).text(1) == "86"
    assert window.price_list.topLevelItem(0).text(2).endswith("前")
    window.close()


def test_relative_listing_time_is_shown_without_online_status(qapp):
    now = datetime(2026, 7, 22, 9, 24, tzinfo=timezone.utc)
    assert PoetoreWindow._relative_listing_time("2026-07-22T09:21:00Z", now) == "3分前"
    assert PoetoreWindow._relative_listing_time("2026-07-22T07:24:00+00:00", now) == "2時間前"
    assert PoetoreWindow._relative_listing_time("", now) == "-"


def test_gem_result_adds_gem_level_and_quality_columns(qapp):
    window = PoetoreWindow()
    window._parsed_item = ParsedItem("ジェム", "ジェム", "Arc", "Arc", "gem")
    try:
        window._show_price_result(PriceResult("Mirage", "q", 1, (
            PriceListing(2, "chaos", indexed="2026-07-22T09:21:00Z", gem_level=20, quality=23),
        )))
        assert [window.price_list.headerItem().text(i) for i in range(4)] == [
            "価格", "ジェムLv", "品質", "出品日時",
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
        ] == ["価格", "ジェムLv", "品質", "出品日時"]

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
        assert window.price_list.columnCount() == 3
        assert [
            window.price_list.headerItem().text(index)
            for index in range(window.price_list.columnCount())
        ] == ["価格", "ilvl", "出品日時"]
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
        assert window.mod_filter_tree.columnWidth(0) == 40
        assert window.mod_filter_tree.columnWidth(3) == 346
    finally:
        window.close()


def test_mod_filter_minimum_and_maximum_editors_use_narrow_width(qapp):
    window = PoetoreWindow()
    window._populate_stat_filters((TradeStatFilter(
        "explicit.stat_1", "命中力 +55", 55, "prefix", False, max_value=100,
    ),))
    try:
        row = window.mod_filter_tree.topLevelItem(0)
        assert window.mod_filter_tree.itemWidget(row, 4).width() == 72
        assert window.mod_filter_tree.itemWidget(row, 5).width() == 72
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
        detail = row.text(6)
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
        assert row.sizeHint(3).height() == 62
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

        assert window.mod_filter_tree.columnWidth(2) == 75
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
        assert rows
        assert all(row.kind == "craft" for row in rows)
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


def test_unidentified_unique_candidates_can_be_selected(qapp):
    window = PoetoreWindow()
    try:
        window._show_unique_candidates(("The First", "The Second"))
        assert not window.unique_name_combo.isHidden()
        assert window.unique_name_combo.count() == 2
        assert window.unique_name_combo.itemData(1) == "The Second"
        assert "2種類" in window.price_status.text()
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
        assert toggle.currentText() == "スプリット"
        assert toggle.currentData() is True
        toggle.click()
        assert toggle.currentText() == "非スプリット"
        assert toggle.currentData() is False
        assert toggle.property("active") is True
        toggle.click()
        assert toggle.currentText() == "スプリット"
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
        assert window.split_combo.itemText(0) == "スプリット"
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


def test_unidentified_unique_is_explicitly_unsupported_in_initial_release(qapp):
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

        assert not window.search_scope_notice.isHidden()
        assert window.search_scope_notice.text() == (
            "⚠ 未鑑定ユニークの候補選択は初版では対応していません。"
            "鑑定後に検索してください。"
        )
        assert not window.price_button.isEnabled()
        assert not window.trade_url_button.isEnabled()
        assert window.unique_name_combo.isHidden()
    finally:
        window.close()


def test_cluster_special_chips_do_not_duplicate_passive_or_enchant_filters(qapp):
    window = PoetoreWindow()
    try:
        entries = (
            {
                "id": "enchant.stat_3086156145",
                "text": "パッシブスキルを#個追加する",
                "type": "enchant",
            },
            {
                "id": "enchant.stat_3948993189",
                "text": "追加される通常パッシブスキルは付与: 範囲ダメージが#%増加する",
                "type": "enchant",
            },
        )
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
        with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
            window._configure_special_filter_chips(item)

            assert "パッシブスキルを4個追加する" not in window.cluster_enchant_chip.text()
            assert "範囲ダメージが10%増加する" in window.cluster_enchant_chip.text()

            special = window._selected_special_chip_filters()
            stat_ids = [row.stat_id for row in special]
            assert stat_ids.count("enchant.stat_3086156145") == 1
            assert stat_ids.count("enchant.stat_3948993189") == 1

            initial = resolve_trade_stat_filters(
                item, PRESET_FINISHED, "Medium Cluster Jewel",
            )
            effective = _replace_filters_with_special_chips(initial, (), special)
            effective_ids = [row.stat_id for row in effective if row.enabled]
            assert effective_ids.count("enchant.stat_3086156145") == 1
            assert effective_ids.count("enchant.stat_3948993189") == 1
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

        window.item_level_edit.setText("84")
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
            "links", "map_tier", "completion_reward", "area_level", "heist_wings",
            "heist_job", "heist_target", "cluster_enchant",
            "cluster_passives", "cluster_sockets", "blighted", "item_level",
            "base_percentile", "gem_variant", "gem_level", "quality",
            "influence_shaper", "influence_elder", "influence_crusader",
            "influence_hunter", "influence_redeemer", "influence_warlord",
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
        assert window.poe_ninja_currency_icon.toolTip() == "神のオーブ"
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
        assert window.poe_ninja_currency_icon.toolTip() == "カオスオーブ"
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
        window._configure_item_level(item)

        assert window.item_level_edit.text() == minimum
        assert not window.item_level_max_edit.isHidden()
        assert window.item_level_max_edit.text() == maximum
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


def test_non_gem_quality_chip_matches_awakened_exact_rules(qapp):
    window = PoetoreWindow()
    try:
        armour = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Quality: +30%
Item Level: 86
""")
        window._parsed_item = armour
        window._configure_trade_presets(armour)
        window._configure_quality(armour)
        assert window.gem_quality_tag.isHidden()

        window.trade_preset_combo.setCurrentIndex(1)
        assert not window.gem_quality_tag.isHidden()
        assert window._selected_quality() == 30

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
        assert window.base_percentile_chip.isActive()
        assert window.base_percentile_chip.suffix_label.text() == "%"
        minimum, maximum = window.base_percentile_chip.values()
        assert minimum is not None
        assert maximum is None

        window.base_percentile_chip.toggle.click()
        assert not window.base_percentile_chip.isActive()
        assert not any(
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


@pytest.mark.parametrize(("item_class", "base_type", "visible"), [
    ("鎧", "Sacred Chainmail", True),
    ("弓", "Spine Bow", True),
    ("両手剣", "Exquisite Blade", True),
    ("スタッフ", "Gnarled Branch", False),
    ("ワンド", "Imbued Wand", False),
])
def test_six_link_chip_is_limited_to_body_armour_and_normal_two_handers(
    qapp, item_class, base_type, visible,
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

        assert window.links_tag.isHidden() is (not visible)
        assert window._selected_links() == (6 if visible else None)
        if visible:
            window.links_toggle.click()
            assert window._selected_links() is None
            window.links_edit.setFocus()
            window.links_edit.selectAll()
            QTest.keyClicks(window.links_edit, "5")
            assert window._selected_links() == 5
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
        assert window.gem_variant_chip.text() == "Variant：ヴァールジェム"
    finally:
        window.close()
