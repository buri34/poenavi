from concurrent.futures import Future
from copy import deepcopy
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.poetore.exchange_catalog import exchange_catalog_by_id, exchange_catalog_items
from src.poetore.exchange_icon_cache import IconResult
from src.poetore.exchange_rate_settings import (
    CHAOS_ORB_ID,
    DIVINE_ORB_ID,
    EXALTED_ORB_ID,
    ExchangeRatePairStore,
    default_rate_pairs_config,
)
from src.ui.exchange_rate_management_dialog import ExchangeRateManagementDialog
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
    ][:5]
    dialog, store, *_ = make_dialog(qapp, tmp_path, available_ids=extras)
    try:
        select_candidate(dialog, DIVINE_ORB_ID)
        dialog.currency_buttons[CHAOS_ORB_ID].setChecked(True)
        assert "すでに登録" in dialog.validation_label.text()
        dialog.currency_buttons[DIVINE_ORB_ID].setChecked(True)
        assert "同じ通貨" in dialog.validation_label.text()
        for item_id in extras[:4]:
            store.add(POE1, item_id, DIVINE_ORB_ID)
        dialog._render_registered_pairs()
        assert "上限" in dialog.validation_label.text()
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
        assert not dialog.findChild(type(dialog.add_button), "ratePairMoveUp0").isEnabled()
        assert not dialog.findChild(type(dialog.add_button), "ratePairMoveDown1").isEnabled()
        dialog.findChild(type(dialog.add_button), "ratePairMoveUp1").click()
        assert len(saved) == 1
        changed.assert_called_once_with()
        dialog.findChild(type(dialog.add_button), "ratePairDelete0").click()
        assert len(saved) == 2
        assert changed.call_count == 2
        assert len(store.pairs(POE1)) == 1
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
