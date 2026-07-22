from unittest.mock import Mock, patch
from dataclasses import replace
from datetime import datetime, timezone

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton
import pytest

from src.poetore.ui import PoetoreWindow, show_poetore_window
from src.poetore.window_position import PlacementContext
from src.poetore.trade import PriceListing, PriceResult, TradeLeague, TradeStatFilter
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
        assert not hasattr(window, "disclaimer_label")
        assert window.trade_league_combo.currentData() == "auto"
        assert window._selected_trade_league() is None
        assert window.width() == 720
        assert window.minimumWidth() == 680
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


def test_poetore_uses_wide_poena_theme_and_hides_debug_parse_area(qapp):
    window = PoetoreWindow()
    try:
        assert window.size().width() == 720
        assert window._panel.objectName() == "poetorePanel"
        assert not window._debug_parse_area.isVisible()
        assert window.mod_filter_tree.isColumnHidden(6)
        assert window.mod_filter_tree.columnCount() == 7
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


def test_mod_filters_are_checkable_and_minimum_is_editable(qapp):
    window = PoetoreWindow()
    window._populate_stat_filters((TradeStatFilter(
        "explicit.stat_1", "命中力 +55", 55, "prefix", False,
    ),))
    row = window.mod_filter_tree.topLevelItem(0)
    assert row.checkState(0) == Qt.Unchecked
    editor = window.mod_filter_tree.itemWidget(row, 4)
    assert editor.text() == "55"
    row.setCheckState(0, Qt.Checked)
    editor.setText("50")
    assert window._selected_stat_filters() == (
        TradeStatFilter("explicit.stat_1", "命中力 +55", 50, "prefix", True),
    )
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
            generation="fractured", selection_reason="クラフトベース向けT1 Mod",
        )
        window._populate_stat_filters((source,))
        row = window.mod_filter_tree.topLevelItem(0)
        assert row.text(2) == "T1"
        detail = row.text(6)
        assert "クラフトベース向けT1 Mod" in detail
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


def test_mod_filter_ui_shows_multiple_awakened_tier_tags_on_property(qapp):
    window = PoetoreWindow()
    try:
        source = TradeStatFilter(
            "property.energy_shield", "エナジーシールド", 577.8,
            "property", True, tier_tags=(1, 2),
        )
        window._populate_stat_filters((source,))
        row = window.mod_filter_tree.topLevelItem(0)
        assert row.text(1) == "アイテム特性"
        assert row.text(2) == "T1 / T2"
        tier_widget = window.mod_filter_tree.itemWidget(row, 2)
        assert tier_widget is not None
        assert [label.text() for label in tier_widget.findChildren(QLabel)] == ["T1", "T2"]
        selected = window._selected_stat_filters()[0]
        assert selected.tier_tags == (1, 2)
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
        assert "クラフトベース" in window.price_status.text()

        low_level = parse_item_text(high_level.raw_text.replace("Item Level: 85", "Item Level: 70"))
        window._configure_trade_presets(low_level)
        assert window.trade_preset_combo.count() == 1
        assert not window.trade_preset_combo.isEnabled()
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
        assert window.trade_preset_combo.itemText(1) == "クラフトベース"
        assert window.trade_preset_combo.count() == 2
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


def test_filter_chips_follow_awakened_order_in_shared_flow_layout(qapp):
    window = PoetoreWindow()
    try:
        assert tuple(name for name, _widget in window._filter_chips) == (
            "links", "map_tier", "completion_reward", "area_level", "heist_wings",
            "blighted", "item_level", "gem_level", "quality",
            "influence_shaper", "influence_elder", "influence_crusader",
            "influence_hunter", "influence_redeemer", "influence_warlord",
            "magic_rarity", "unidentified", "veiled", "foil", "mirrored", "split",
        )
        assert window.filter_chip_layout.ordered_widgets() == tuple(
            widget for _name, widget in window._filter_chips
        )
    finally:
        window.close()


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
        assert window.poe_ninja_price_value.text() == "200 div"
        assert "7日推移" in window.poe_ninja_trend_label.text()
        assert window.poe_ninja_trend_chart._points == (0, 1, 2, 3, 4, 5, 6)
        assert window._last_poe_ninja_url == "https://poe.ninja/example"

        window._hide_poe_ninja_price(key)
        assert window.poe_ninja_price_panel.isHidden()
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
