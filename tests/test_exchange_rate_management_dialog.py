from concurrent.futures import Future
from copy import deepcopy
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QToolButton

from src.poetore.exchange_catalog import exchange_catalog_by_id, exchange_catalog_items
from src.poetore.exchange_icon_cache import IconResult
from src.poetore.exchange_rate_settings import (
    CHAOS_ORB_ID,
    DIVINE_ORB_ID,
    EXALTED_ORB_ID,
    ExchangeRatePairStore,
    default_rate_pairs_config,
)
from src.ui.app_theme import POETORE_THEME
from src.ui.exchange_rate_management_dialog import (
    RATE_PAIR_DRAG_MIME,
    ExchangeRateManagementDialog,
)
from src.utils.poe_version_data import POE1


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeIconCache:
    def __init__(self, path):
        self.path = path
        self.requests = []

    def request(self, kind, url=None):
        self.requests.append((kind, url))
        future = Future()
        future.set_result(IconResult(self.path, "placeholder", "svg"))
        return future


def make_dialog(qapp, tmp_path, *, available_ids=None, config=None):
    catalog = exchange_catalog_by_id(POE1)
    ids = list(catalog)
    available_ids = available_ids or ids[:40]
    for required in (DIVINE_ORB_ID, CHAOS_ORB_ID, EXALTED_ORB_ID):
        if required not in available_ids:
            available_ids.append(required)
    config = config or {"poetore": {"exchange_rate_pairs": default_rate_pairs_config()}}
    saved = []
    store = ExchangeRatePairStore(
        config,
        lambda value: saved.append(deepcopy(value)),
    )
    icon_path = tmp_path / "placeholder.svg"
    icon_path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    changed = Mock()
    dialog = ExchangeRateManagementDialog(
        None,
        poe_version=POE1,
        store=store,
        available_item_ids=available_ids,
        icon_cache=FakeIconCache(icon_path),
        on_changed=changed,
    )
    dialog.show()
    qapp.processEvents()
    return dialog, store, saved, changed


def select_candidate(dialog, item_id):
    for row in range(dialog.candidate_list.count()):
        item = dialog.candidate_list.item(row)
        if item.data(Qt.UserRole) == item_id:
            dialog.candidate_list.setCurrentRow(row)
            return
    raise AssertionError(f"candidate not found: {item_id}")


def test_search_is_japanese_only_and_crosses_selected_category(qapp, tmp_path):
    items = exchange_catalog_items(POE1)
    target = next(item for item in items if item.category_order > 0)
    dialog, *_ = make_dialog(qapp, tmp_path, available_ids=[target.item_id])
    try:
        dialog.category_list.setCurrentRow(1)
        dialog.search_edit.setText(target.japanese_name)
        assert dialog.candidate_list.count() == 1
        assert target.japanese_name in dialog.candidate_list.item(0).text()
        assert "·" in dialog.candidate_list.item(0).text()
        dialog.search_edit.setText(target.english_name)
        assert dialog.candidate_list.count() == 0
    finally:
        dialog.close()


def test_changing_category_clears_search_text(qapp, tmp_path):
    items = exchange_catalog_items(POE1)
    target = next(item for item in items if item.category_order > 0)
    dialog, *_ = make_dialog(qapp, tmp_path, available_ids=[target.item_id])
    try:
        dialog.search_edit.setText(target.japanese_name)
        assert dialog.search_edit.text() == target.japanese_name
        assert dialog.candidate_list.count() == 1

        dialog.category_list.setCurrentRow(1)

        assert dialog.search_edit.text() == ""
        assert all(
            "·" not in dialog.candidate_list.item(row).text()
            for row in range(dialog.candidate_list.count())
        )
    finally:
        dialog.close()


def test_search_clear_button_clears_input(qapp, tmp_path):
    dialog, *_ = make_dialog(qapp, tmp_path)
    try:
        dialog.search_edit.setText("神のオーブ")
        qapp.processEvents()
        clear_button = dialog.findChild(QToolButton, "ratePairSearchClear")
        assert clear_button is not None
        assert clear_button.isVisible()
        clear_button.click()
        assert dialog.search_edit.text() == ""
    finally:
        dialog.close()


def test_pair_editor_uses_two_labeled_cards_and_footer(qapp, tmp_path):
    dialog, *_ = make_dialog(qapp, tmp_path)
    try:
        assert dialog.item_card_title.text() == "価格を確認するアイテム"
        assert dialog.currency_card_title.text() == "通貨"
        assert dialog.exchange_symbol.text() == "⇔"
        assert dialog.item_card.isAncestorOf(dialog.search_edit)
        assert all(
            dialog.currency_card.isAncestorOf(button)
            for button in dialog.currency_buttons.values()
        )
        assert dialog.preview_label.objectName() == "ratePairPreview"
        assert dialog.preview_label.geometry().top() > dialog.item_card.geometry().bottom()
        assert dialog.preview_label.text() == "アイテムと通貨を選択してください"
    finally:
        dialog.close()


def test_currency_choices_have_icons_and_preview_uses_bidirectional_symbol(
    qapp, tmp_path
):
    catalog = exchange_catalog_by_id(POE1)
    target = next(
        item_id
        for item_id in catalog
        if item_id not in {DIVINE_ORB_ID, CHAOS_ORB_ID, EXALTED_ORB_ID}
    )
    dialog, *_ = make_dialog(qapp, tmp_path, available_ids=[target])
    try:
        assert all(
            not button.icon().isNull()
            for button in dialog.currency_buttons.values()
        )
        select_candidate(dialog, target)
        dialog.currency_buttons[DIVINE_ORB_ID].setChecked(True)
        assert dialog.preview_label.text() == (
            f"{catalog[target].japanese_name} ⇔ "
            f"{catalog[DIVINE_ORB_ID].japanese_name}"
        )
        assert dialog.validation_label.text() == ""
        assert dialog.add_button.isEnabled()
    finally:
        dialog.close()


def test_add_clears_selection_stays_open_and_saves_once(qapp, tmp_path):
    catalog = exchange_catalog_by_id(POE1)
    target = next(
        item_id for item_id in catalog
        if item_id not in {DIVINE_ORB_ID, CHAOS_ORB_ID, EXALTED_ORB_ID}
    )
    dialog, store, saved, changed = make_dialog(qapp, tmp_path, available_ids=[target])
    try:
        select_candidate(dialog, target)
        dialog.currency_buttons[DIVINE_ORB_ID].setChecked(True)
        assert dialog.add_button.isEnabled()
        dialog.add_button.click()
        assert dialog.isVisible()
        assert len(store.pairs(POE1)) == 2
        assert len(saved) == 1
        changed.assert_called_once_with()
        assert dialog.candidate_list.currentRow() == -1
        assert not any(button.isChecked() for button in dialog.currency_buttons.values())
    finally:
        dialog.close()


def test_same_pair_same_currency_and_limit_have_nearby_reasons(qapp, tmp_path):
    catalog = exchange_catalog_by_id(POE1)
    extras = [
        item_id for item_id in catalog
        if item_id not in {DIVINE_ORB_ID, CHAOS_ORB_ID, EXALTED_ORB_ID}
    ][:9]
    dialog, store, *_ = make_dialog(qapp, tmp_path, available_ids=extras)
    try:
        select_candidate(dialog, DIVINE_ORB_ID)
        dialog.currency_buttons[CHAOS_ORB_ID].setChecked(True)
        assert "すでに登録" in dialog.validation_label.text()
        dialog.currency_buttons[DIVINE_ORB_ID].setChecked(True)
        assert "同じ通貨" in dialog.validation_label.text()
        for item_id in extras[:9]:
            store.add(POE1, item_id, DIVINE_ORB_ID)
        dialog._render_registered_pairs()
        assert "上限" in dialog.validation_label.text()
        assert "10件" in dialog.validation_label.text()
        assert dialog.title_label.text() == "レート表示の管理（10 / 10）"
        assert not dialog.add_button.isEnabled()
    finally:
        dialog.close()


def test_move_and_delete_save_once_and_refresh_main_once(qapp, tmp_path):
    catalog = exchange_catalog_by_id(POE1)
    target = next(
        item_id for item_id in catalog
        if item_id not in {DIVINE_ORB_ID, CHAOS_ORB_ID, EXALTED_ORB_ID}
    )
    dialog, store, saved, changed = make_dialog(qapp, tmp_path, available_ids=[target])
    try:
        store.add(POE1, target, DIVINE_ORB_ID)
        saved.clear()
        dialog._render_registered_pairs()
        first_up = dialog.registered_widget.findChildren(
            QPushButton, "ratePairMoveUp0"
        )[-1]
        first_down = dialog.registered_widget.findChildren(
            QPushButton, "ratePairMoveDown0"
        )[-1]
        last_up = dialog.registered_widget.findChildren(
            QPushButton, "ratePairMoveUp1"
        )[-1]
        last_down = dialog.registered_widget.findChildren(
            QPushButton, "ratePairMoveDown1"
        )[-1]
        assert first_up.text() == "↑"
        assert first_down.text() == "↓"
        assert not first_up.isEnabled()
        assert first_down.isEnabled()
        assert last_up.isEnabled()
        assert not last_down.isEnabled()
        for enabled in (first_down, last_up):
            assert "color: #FFFFFF" in enabled.styleSheet()
        for disabled in (first_up, last_down):
            assert "QPushButton:disabled { color: #000000; }" in disabled.styleSheet()
        last_up.click()
        assert len(saved) == 1
        changed.assert_called_once_with()
        dialog.findChild(type(dialog.add_button), "ratePairDelete0").click()
        assert len(saved) == 2
        assert changed.call_count == 2
        assert len(store.pairs(POE1)) == 1
    finally:
        dialog.close()


def test_dragging_registered_pair_to_bottom_reorders_and_saves_once(qapp, tmp_path):
    catalog = exchange_catalog_by_id(POE1)
    extras = tuple(
        item_id for item_id in catalog
        if item_id not in {DIVINE_ORB_ID, CHAOS_ORB_ID, EXALTED_ORB_ID}
    )[:2]
    dialog, store, saved, changed = make_dialog(
        qapp, tmp_path, available_ids=list(extras)
    )
    try:
        for item_id in extras:
            store.add(POE1, item_id, DIVINE_ORB_ID)
        saved.clear()
        dialog._render_registered_pairs()
        before = store.pairs(POE1)
        rows = dialog.registered_widget._rows
        assert len(rows) == 3
        assert all("ドラッグ" in row.toolTip() for row in rows)

        mime = QMimeData()
        mime.setData(RATE_PAIR_DRAG_MIME, b"0")
        drop = QDropEvent(
            QPointF(5, rows[-1].geometry().bottom() + 5),
            Qt.MoveAction,
            mime,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        dialog.registered_widget.dropEvent(drop)

        assert store.pairs(POE1) == (before[1], before[2], before[0])
        assert len(saved) == 1
        changed.assert_called_once_with()
    finally:
        dialog.close()


def test_dragging_near_registered_list_edge_auto_scrolls(qapp, tmp_path):
    catalog = exchange_catalog_by_id(POE1)
    extras = [
        item_id for item_id in catalog
        if item_id not in {DIVINE_ORB_ID, CHAOS_ORB_ID, EXALTED_ORB_ID}
    ][:9]
    dialog, store, *_ = make_dialog(qapp, tmp_path, available_ids=list(extras))
    try:
        for item_id in extras:
            store.add(POE1, item_id, DIVINE_ORB_ID)
        dialog._render_registered_pairs()
        qapp.processEvents()
        scroll_bar = dialog.registered_scroll.verticalScrollBar()
        assert scroll_bar.maximum() > 0
        scroll_bar.setValue(0)
        content_position = dialog.registered_scroll.viewport().mapTo(
            dialog.registered_widget,
            QPoint(5, dialog.registered_scroll.viewport().height() - 2),
        )

        dialog.registered_widget._auto_scroll(content_position)

        assert scroll_bar.value() > 0
    finally:
        dialog.close()


def test_candidate_refresh_does_not_remove_registered_pair(qapp, tmp_path):
    dialog, store, *_ = make_dialog(qapp, tmp_path)
    before = store.pairs(POE1)
    try:
        dialog.update_available_item_ids([])
        assert dialog.candidate_list.count() == 0
        assert store.pairs(POE1) == before
    finally:
        dialog.close()


def test_only_visible_candidates_request_icons(qapp, tmp_path):
    available = [item.item_id for item in exchange_catalog_items(POE1)[:200]]
    dialog, *_ = make_dialog(qapp, tmp_path, available_ids=available)
    try:
        requested = len(dialog.icon_cache.requests)
        assert 0 < requested < dialog.candidate_list.count()
    finally:
        dialog.close()


def test_registered_area_and_pair_names_use_dark_theme(qapp, tmp_path):
    dialog, *_ = make_dialog(qapp, tmp_path)
    try:
        assert POETORE_THEME.panel in dialog.registered_scroll.viewport().styleSheet()
        assert POETORE_THEME.panel in dialog.registered_widget.styleSheet()
        name = dialog.findChild(QLabel, "ratePairName0")
        assert name is not None
        assert POETORE_THEME.text in name.styleSheet()
    finally:
        dialog.close()
