from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import pytest

from src.poetore.ui import PoetoreWindow, show_poetore_window
from src.poetore.trade import PriceListing, PriceResult, TradeStatFilter
from src.poetore.parser import parse_item_text


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
        assert window.trade_status_combo.currentData() == "instant"
        assert window.trade_status_combo.count() == 3
        assert window.trade_currency_combo.currentData() == "any"
        assert window.trade_currency_combo.count() == 4
    finally:
        window.close()


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

        window.trade_preset_combo.setCurrentIndex(1)
        assert "クラフトベース" in window.price_status.text()

        low_level = parse_item_text(high_level.raw_text.replace("Item Level: 85", "Item Level: 70"))
        window._configure_trade_presets(low_level)
        assert window.trade_preset_combo.count() == 1
        assert not window.trade_preset_combo.isEnabled()
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
        assert window.corrupted_combo.itemText(0) == "未コラプトのみ"
        assert window.corrupted_combo.itemText(1) == "コラプト品含む"
        assert window.corrupted_combo.currentData() is False
        assert window.split_combo.itemText(0) == "非スプリットのみ"
        assert window.split_combo.itemText(1) == "スプリット品含む"
        assert window.split_combo.currentData() is True

        window.corrupted_combo.setCurrentIndex(1)
        window.split_combo.setCurrentIndex(0)
        window._configure_item_state_filters(item)
        assert window.corrupted_combo.currentData() is True
        assert window.split_combo.currentData() is False
    finally:
        window.close()
