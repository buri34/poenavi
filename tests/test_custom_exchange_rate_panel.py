from concurrent.futures import Future
from copy import deepcopy

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from src.poetore.exchange_catalog import (
    divination_card_icon_path,
    exchange_catalog_by_id,
)
from src.poetore.exchange_icon_cache import IconResult
from src.poetore.exchange_rate_cache import ExchangeRateValueCache
from src.poetore.exchange_rate_settings import (
    CHAOS_ORB_ID,
    DIVINE_ORB_ID,
    EXALTED_ORB_ID,
    ExchangeRatePairStore,
    RatePair,
)
from src.poetore.official_exchange import (
    DirectPairPrice,
    ExchangeSyncState,
    SyncCheckResult,
)
from src.ui.app_theme import POETORE_THEME
from src.ui.custom_exchange_rate_panel import (
    OFFICIAL_DATA_TOOLTIP,
    RATE_CHECK_INTERVAL_MSEC,
    CustomExchangeRatePanel,
    format_significant_rate,
)
from src.utils.poe_version_data import POE1, POE2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeIconCache:
    def __init__(self, path):
        self.path = path

    def request(self, _kind, _url=None):
        future = Future()
        future.set_result(IconResult(self.path, "placeholder", "svg"))
        return future


class FakeService:
    def __init__(self, results=None, ids=()):
        self.results = results or {}
        self.ids = frozenset(ids)
        self.state = ExchangeSyncState(POE1, "League", None, 0, None, False, False)
        self.queued = []

    def direct_pair(self, _version, _league, left, right):
        return self.results.get(
            (left, right), DirectPairPrice("unavailable", left, right, None, None)
        )

    def sync_state(self, *_args):
        return self.state

    def exchange_item_ids(self, *_args):
        return self.ids

    def queue_sync(self, version, league, *, on_complete, on_checked):
        self.queued.append((version, league, on_complete, on_checked))
        return True


def make_panel(qapp, tmp_path, *, pairs=None, service=None, version=POE1):
    default_right = EXALTED_ORB_ID if version == POE2 else CHAOS_ORB_ID
    pairs = pairs if pairs is not None else [RatePair(DIVINE_ORB_ID, default_right)]
    config = {"poetore": {"exchange_rate_pairs": {
        POE1: [pair.to_config() for pair in pairs] if version == POE1 else [],
        POE2: [pair.to_config() for pair in pairs] if version == POE2 else [],
    }}}
    saved = []
    store = ExchangeRatePairStore(config, lambda value: saved.append(deepcopy(value)))
    icon = divination_card_icon_path()
    panel = CustomExchangeRatePanel(
        None,
        poe_version=version,
        store=store,
        league_getter=lambda: "League",
        service=service or FakeService(),
        value_cache=ExchangeRateValueCache(tmp_path / "rates.json", clock=lambda: 1000),
        icon_cache=FakeIconCache(icon),
        on_manage=lambda: None,
    )
    panel.show()
    qapp.processEvents()
    return panel, store, saved


@pytest.mark.parametrize(("value", "expected"), [
    (174.36, "174.4"),
    (12.345, "12.35"),
    (1.2345, "1.235"),
    (0.005735260, "0.005735"),
    (12345, "12,350"),
    (1.5000, "1.5"),
    (372.5, "372.5"),
    (372.8, "372.8"),
])
def test_four_significant_digits_and_trailing_zeroes(value, expected):
    assert format_significant_rate(value) == expected


@pytest.mark.parametrize("count", (0, 1, 9, 10))
def test_zero_through_ten_rows_have_no_scroll_and_plus_until_limit(
    qapp, tmp_path, count,
):
    ids = list(exchange_catalog_by_id(POE1))
    pairs = [RatePair(ids[index], ids[index + 10]) for index in range(count)]
    panel, *_ = make_panel(qapp, tmp_path, pairs=pairs)
    try:
        assert len(panel.row_widgets) == count
        assert panel.add_button is not None if count < 10 else panel.add_button is None
        assert panel.findChildren(type(panel)) == []
    finally:
        panel.stop()
        panel.close()


def test_available_no_trade_unconfirmed_and_unavailable_are_distinct(qapp, tmp_path):
    ids = list(exchange_catalog_by_id(POE1))[:8]
    pairs = [RatePair(ids[index], ids[index + 4]) for index in range(4)]
    statuses = ("available", "no_trades", "unconfirmed", "unavailable")
    results = {
        (pair.left_item_id, pair.right_item_id): DirectPairPrice(
            status,
            pair.left_item_id,
            pair.right_item_id,
            2.5 if status == "available" else None,
            720,
        )
        for pair, status in zip(pairs, statuses, strict=True)
    }
    panel, *_ = make_panel(qapp, tmp_path, pairs=pairs, service=FakeService(results))
    try:
        values = [
            panel.findChild(QLabel, f"customRateValue{index}").text()
            for index in range(4)
        ]
        assert values == [
            "1 ＝ 2.5", "取引データなし", "価格未確定",
            "最新データを取得できません",
        ]
        assert all(
            panel.findChild(QLabel, f"customRateValue{index}").alignment()
            == Qt.AlignCenter
            for index in range(4)
        )
    finally:
        panel.stop()
        panel.close()


def test_base_currency_quote_keeps_fractional_direct_rate(qapp, tmp_path):
    pair = RatePair(DIVINE_ORB_ID, CHAOS_ORB_ID)
    result = DirectPairPrice(
        "available", DIVINE_ORB_ID, CHAOS_ORB_ID, 372.5, 720
    )
    panel, *_ = make_panel(
        qapp,
        tmp_path,
        pairs=[pair],
        service=FakeService({(DIVINE_ORB_ID, CHAOS_ORB_ID): result}),
    )
    try:
        assert panel.findChild(QLabel, "customRateValue0").text() == "1 ＝ 372.5"
    finally:
        panel.stop()
        panel.close()


def test_delete_including_default_is_immediate_and_confirmation_free(qapp, tmp_path):
    panel, store, saved = make_panel(qapp, tmp_path)
    try:
        panel.findChild(QPushButton, "customRateDelete0").click()
        assert store.pairs(POE1) == ()
        assert len(saved) == 1
        assert panel.add_button is not None
    finally:
        panel.stop()
        panel.close()


def test_refresh_is_nonblocking_and_manual_result_text_is_specific(qapp, tmp_path):
    service = FakeService()
    panel, *_ = make_panel(qapp, tmp_path, service=service)
    try:
        previous_row = panel.row_widgets[0]
        panel.refresh(manual=True)
        assert not previous_row.isVisible()
        assert panel.status_label.text() == "最新データを確認中…"
        loading_value = panel.row_widgets[0].findChild(QLabel, "customRateValue0")
        assert loading_value.text() == "最新データ取得中…"
        assert loading_value.toolTip() == "最新データ取得中…"
        assert "font-size: 12px" in loading_value.styleSheet()
        assert loading_value.sizeHint().width() <= loading_value.width()
        assert not panel.refresh_button.isEnabled()
        callback = service.queued[-1][3]
        callback(SyncCheckResult("no_new_data", POE1, "League", 720))
        qapp.processEvents()
        assert panel.status_label.text() == "新しい公式データはまだありません"
        failed_value = panel.row_widgets[0].findChild(QLabel, "customRateValue0")
        assert failed_value.text() == "最新データを取得できません"
        assert failed_value.toolTip() == "最新データを取得できません"
        assert panel.refresh_button.isEnabled()
        assert panel.check_timer.interval() == RATE_CHECK_INTERVAL_MSEC
    finally:
        panel.stop()
        panel.close()


def test_official_hourly_explanation_is_exact(qapp, tmp_path):
    panel, *_ = make_panel(qapp, tmp_path)
    try:
        assert panel.title_label.toolTip() == OFFICIAL_DATA_TOOLTIP
        assert panel.refresh_button.text() == "最新データ確認"
    finally:
        panel.stop()
        panel.close()


def test_tooltips_use_high_contrast_dark_theme(qapp, tmp_path):
    panel, *_ = make_panel(qapp, tmp_path)
    try:
        style = panel.styleSheet()
        assert "QToolTip" in style
        assert f"color: {POETORE_THEME.text}" in style
        assert f"background-color: {POETORE_THEME.background}" in style
        assert "border: 1px solid" in style
    finally:
        panel.stop()
        panel.close()


def test_long_names_keep_full_tooltip(qapp, tmp_path):
    panel, *_ = make_panel(qapp, tmp_path)
    try:
        label = panel.findChild(QLabel, "customRateLeftName0")
        assert label.toolTip() == label.text()
        assert label.width() == 125
    finally:
        panel.stop()
        panel.close()


def test_names_use_heading_accent_and_cached_icons_render(qapp, tmp_path):
    panel, *_ = make_panel(qapp, tmp_path)
    try:
        qapp.processEvents()
        for side in ("Left", "Right"):
            name = panel.findChild(QLabel, f"customRate{side}Name0")
            assert POETORE_THEME.accent in name.styleSheet()
        icon_labels = [
            label
            for label in panel.findChildren(QLabel)
            if label.objectName().startswith("customRateIcon-")
        ]
        assert len(icon_labels) == 2
        assert all(label.pixmap() is not None and not label.pixmap().isNull()
                   for label in icon_labels)
    finally:
        panel.stop()
        panel.close()
