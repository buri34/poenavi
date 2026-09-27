from concurrent.futures import Future
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.poetore.exchange_catalog import exchange_catalog_by_id
from src.poetore.exchange_icon_cache import IconResult
from src.poetore.exchange_rate_cache import ExchangeRateValueCache
from src.poetore.exchange_rate_settings import (
    CHAOS_ORB_ID,
    DIVINE_ORB_ID,
    EXALTED_ORB_ID,
    ExchangeRatePairStore,
    default_rate_pairs_config,
)
from src.poetore.official_exchange import DirectPairPrice, ExchangeSyncState
from src.ui.custom_exchange_rate_panel import CustomExchangeRatePanel
from src.ui.exchange_rate_management_dialog import ExchangeRateManagementDialog
from src.utils.poe_version_data import POE1


class _IconCache:
    def __init__(self, path):
        self.path = path

    def request(self, _kind, _url=None):
        future = Future()
        future.set_result(IconResult(self.path, "placeholder", "svg"))
        return future


class _ExchangeService:
    def __init__(self, item_ids):
        self.item_ids = frozenset(item_ids)

    def direct_pair(self, _version, _league, left, right):
        return DirectPairPrice("no_trades", left, right, None, 720)

    def sync_state(self, version, league):
        return ExchangeSyncState(version, league, 720, 720, 0, False, True)

    def exchange_item_ids(self, _version, _league):
        return self.item_ids

    def queue_sync(self, *_args, **_kwargs):
        return False


def _select(dialog, item_id):
    for index in range(dialog.candidate_list.count()):
        row = dialog.candidate_list.item(index)
        if row.data(Qt.UserRole) == item_id:
            dialog.candidate_list.setCurrentRow(index)
            return
    raise AssertionError(item_id)


def test_manage_add_move_delete_and_restart_flow(tmp_path):
    app = QApplication.instance() or QApplication([])
    catalog = exchange_catalog_by_id(POE1)
    target = next(
        item_id for item_id in catalog
        if item_id not in {DIVINE_ORB_ID, CHAOS_ORB_ID, EXALTED_ORB_ID}
    )
    config = {"poetore": {"exchange_rate_pairs": default_rate_pairs_config()}}
    saved = []
    store = ExchangeRatePairStore(
        config, lambda value: saved.append(deepcopy(value))
    )
    icon = tmp_path / "placeholder.svg"
    icon.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    icons = _IconCache(icon)
    service = _ExchangeService({target, DIVINE_ORB_ID, CHAOS_ORB_ID})
    panel = CustomExchangeRatePanel(
        None,
        poe_version=POE1,
        store=store,
        league_getter=lambda: "League",
        service=service,
        value_cache=ExchangeRateValueCache(tmp_path / "values.json"),
        icon_cache=icons,
        on_manage=lambda: None,
    )
    dialog = ExchangeRateManagementDialog(
        None,
        poe_version=POE1,
        store=store,
        available_item_ids=service.item_ids,
        icon_cache=icons,
        on_changed=panel.render_rows,
    )
    try:
        panel.show()
        dialog.show()
        app.processEvents()
        _select(dialog, target)
        dialog.currency_buttons[DIVINE_ORB_ID].setChecked(True)
        dialog.add_button.click()
        assert len(panel.row_widgets) == 2
        assert len(saved) == 1

        dialog._move_up(1)
        assert store.pairs(POE1)[0].left_item_id == target
        assert len(saved) == 2
        dialog._delete(1)
        assert len(panel.row_widgets) == 1
        assert len(saved) == 3

        restarted = ExchangeRatePairStore(
            deepcopy(saved[-1]), lambda _value: None
        )
        assert restarted.pairs(POE1) == store.pairs(POE1)
        assert restarted.pairs(POE1)[0].left_item_id == target
    finally:
        dialog.close()
        panel.stop()
        panel.close()
        app.processEvents()
