from unittest.mock import Mock, patch
from dataclasses import replace

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton
import pytest

from src.poetore.ui import PoetoreWindow, show_poetore_window
from src.poetore.window_position import PlacementContext
from src.poetore.trade import PriceListing, PriceResult, TradeLeague, TradeStatFilter
from src.poetore.parser import parse_item_text
from src.poetore.models import ParsedItem
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


def test_poetore_uses_wide_poena_theme_and_hides_debug_parse_area(qapp):
    window = PoetoreWindow()
    try:
        assert window.size().width() == 720
        assert window._panel.objectName() == "poetorePanel"
        assert not window._debug_parse_area.isVisible()
        assert window.mod_filter_tree.isColumnHidden(5)
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
    window._show_price_result(PriceResult("Mirage", "q", 42, (
        PriceListing(4, "chaos", "seller1", "Doom Sever", "Reaver Sword"),
        PriceListing(6, "chaos", "seller2", "Foe Bite", "Reaver Sword"),
    )))
    assert "Mirage" in window.price_status.text()
    assert "候補42件" in window.price_status.text()
    assert "中央値 5 chaos" in window.price_status.text()
    assert window.price_list.topLevelItemCount() == 2
    assert window.price_list.topLevelItem(0).text(1) == "4 chaos"
    assert window.price_list.topLevelItem(0).text(2) == "Doom Sever / Reaver Sword"
    assert window.price_list.topLevelItem(0).text(3) == "seller1"
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
    editor = window.mod_filter_tree.itemWidget(row, 3)
    assert editor.text() == "55"
    row.setCheckState(0, Qt.Checked)
    editor.setText("50")
    assert window._selected_stat_filters() == (
        TradeStatFilter("explicit.stat_1", "命中力 +55", 50, "prefix", True),
    )
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
        detail = row.text(5)
        assert "クラフトベース向けT1 Mod" in detail
        assert "読取 100" in detail
        assert "T1" in detail
        assert "範囲 90–100" in detail
        assert "Fractured" in detail or "fractured" in detail
        assert "一致 100%" in detail

        editor = window.mod_filter_tree.itemWidget(row, 3)
        editor.setText("95")
        selected = window._selected_stat_filters()[0]
        assert selected.min_value == 95
        assert selected.selection_reason == source.selection_reason
        assert selected.tier == 1
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


@pytest.mark.parametrize("toggle_name", [
    "trade_preset_combo", "split_combo",
])
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
        assert window.split_combo.itemText(0) == "非スプリット"
        assert window.split_combo.itemText(1) == "スプリット品含む"
        assert window.split_combo.currentData() is True
        assert not isinstance(window.corrupted_combo, QComboBox)
        assert not isinstance(window.split_combo, QComboBox)

        window.corrupted_combo.setCurrentIndex(2)
        window.split_combo.setCurrentIndex(0)
        window._configure_item_state_filters(item)
        assert window.corrupted_combo.currentData() is True
        assert window.split_combo.currentData() is False
    finally:
        window.close()


def test_item_level_tag_is_leftmost_editable_state_and_replaces_tree_filter(qapp):
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
        assert window.item_level_tag.parentWidget() is window._panel
        assert window.item_level_tag.x() <= window.split_combo.x()

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
