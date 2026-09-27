import json
import sys
import threading
import time

import pytest

from src.poetore.official_exchange import (
    CHAOS,
    DIVINE,
    EXALTED,
    HOUR_SECONDS,
    WINDOW_HOURS,
    HourlySample,
    OfficialExchangeShadowService,
    evaluate_route,
    latest_completed_hour,
    poe_ninja_reference_base,
    resolve_divine_rate,
    resolve_reference_prices,
)
from src.poetore.poe_ninja import PoeNinjaPrice
from src.utils.poe_version_data import POE1, POE2

ITEM = "Metadata/Items/Test/TestItem"
DIVINE_ONLY = "Metadata/Items/Test/DivineOnly"


def market(league, left, right, left_units, right_units):
    return {
        "league": league,
        "market_pair": [left, right],
        "volume_traded": {left: left_units, right: right_units},
    }


def metadata_root(tmp_path, *, swapped=False, missing_item=False):
    root = tmp_path / "metadata"
    root.mkdir()
    common = {
        CHAOS: "Divine Orb" if swapped else "Chaos Orb",
        DIVINE: "Chaos Orb" if swapped else "Divine Orb",
        EXALTED: "Exalted Orb",
        DIVINE_ONLY: "Divine Only",
    }
    if not missing_item:
        common[ITEM] = "Test Item"
    for realm in ("poe1", "poe2"):
        (root / f"{realm}_item_names.json").write_text(
            json.dumps(common), encoding="utf-8",
        )
    return root


def payload(league, profile, hour):
    direct_price = 7 if profile.realm == "poe1" else 70
    return {
        "markets": [
            market(league, ITEM, profile.base_currency, 2, direct_price * 2),
            market(league, DIVINE_ONLY, DIVINE, 2, 1),
            market(league, DIVINE, profile.base_currency, 1, 200),
            # A different league must never enter the selected league's cache.
            market("Other League", ITEM, profile.base_currency, 1, 999999),
        ],
        "next_change_id": f"change-{hour}",
    }


def make_service(tmp_path, league="Test League", **kwargs):
    calls = []
    metadata = kwargs.pop("metadata", None)
    if metadata is None:
        metadata = metadata_root(tmp_path)

    def fetcher(profile, hour):
        calls.append((profile.realm, hour))
        return payload(league, profile, hour)

    service = OfficialExchangeShadowService(
        cache_root=tmp_path / "cache",
        metadata_root=metadata,
        fetcher=kwargs.pop("fetcher", fetcher),
        clock=kwargs.pop("clock", lambda: 100 * HOUR_SECONDS + 1),
        **kwargs,
    )
    return service, calls


def test_latest_completed_hour_never_uses_the_open_hour():
    assert latest_completed_hour(7201) == 3600


def test_default_metadata_root_uses_pyinstaller_bundle(tmp_path, monkeypatch):
    executable = tmp_path / "PoENavi" / "PoENavi.exe"
    bundle_root = executable.parent / "_internal"
    expected = bundle_root / "data" / "poetore" / "currency_exchange"
    expected.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_root), raising=False)

    service = OfficialExchangeShadowService(cache_root=tmp_path / "cache")

    assert service.metadata_root == expected


def test_single_real_trade_uses_reference_only_as_anomaly_detection():
    confirmed = evaluate_route([HourlySample(1, 80, 1)], 75)
    conflict = evaluate_route([HourlySample(1, 80, 1)], 2)
    assert confirmed.valid
    assert confirmed.reason == "single_observation_reference_confirmed"
    assert not conflict.valid
    assert conflict.reason == "single_observation_reference_conflict"


def test_repeated_new_price_overrides_stale_reference():
    result = evaluate_route(
        [
            HourlySample(HOUR_SECONDS, 78, 1),
            HourlySample(2 * HOUR_SECONDS, 82, 1),
        ],
        2,
    )
    assert result.valid
    assert result.price == 82
    assert result.reason == "latest_observation_previous_confirmed"


def test_latest_non_extreme_trade_is_used_instead_of_the_24_hour_median():
    result = evaluate_route([
        HourlySample(1, 7, 100),
        HourlySample(2, 7.2, 100),
        HourlySample(3, 7.4, 100),
        HourlySample(4, 12.71, 146),
    ])
    assert result.valid
    assert result.price == 12.71
    assert result.reason == "latest_observation"
    assert result.baseline_price == 7.2
    assert result.extreme_factor < 3


def test_unconfirmed_single_extreme_hour_is_rejected():
    result = evaluate_route([
        HourlySample(1, 7, 1),
        HourlySample(2, 7, 1),
        HourlySample(3, 7, 1),
        HourlySample(4, 388.5, 1),
    ])
    assert not result.valid
    assert result.price == 388.5
    assert result.reason == "latest_extreme_unconfirmed"
    assert result.extreme_factor == 55.5


def test_extreme_latest_trade_is_accepted_when_previous_hour_confirms_it():
    result = evaluate_route([
        HourlySample(HOUR_SECONDS, 7, 1),
        HourlySample(2 * HOUR_SECONDS, 7, 1),
        HourlySample(3 * HOUR_SECONDS, 80, 1),
        HourlySample(4 * HOUR_SECONDS, 100, 1),
    ])
    assert result.valid
    assert result.price == 100
    assert result.reason == "latest_extreme_confirmed"
    assert result.confirmations == ("previous_hour",)


def test_extreme_latest_trade_is_accepted_when_order_book_confirms_it():
    result = evaluate_route([
        HourlySample(1, 7, 1),
        HourlySample(2, 7, 1),
        HourlySample(3, 7, 1),
        HourlySample(4, 100, 1, order_book_supported=True),
    ])
    assert result.valid
    assert result.price == 100
    assert result.confirmations == ("order_book",)


def test_extreme_latest_trade_is_accepted_when_poe_ninja_confirms_it():
    result = evaluate_route([
        HourlySample(1, 7, 1),
        HourlySample(2, 7, 1),
        HourlySample(3, 7, 1),
        HourlySample(4, 100, 1),
    ], reference_price=80)
    assert result.valid
    assert result.price == 100
    assert result.confirmations == ("poe_ninja",)


def test_exactly_threefold_latest_trade_does_not_require_confirmation():
    result = evaluate_route([
        HourlySample(1, 7, 1),
        HourlySample(2, 7, 1),
        HourlySample(3, 7, 1),
        HourlySample(4, 21, 1),
    ])
    assert result.valid
    assert result.price == 21
    assert result.reason == "latest_observation"


def test_unconfirmed_extreme_direct_trade_falls_back_to_poe_ninja_not_divine(tmp_path):
    league = "Extreme Direct"

    def fetcher(profile, hour):
        direct_price = 100 if hour == 99 * HOUR_SECONDS else 7
        return {"markets": [
            market(league, ITEM, profile.base_currency, 1, direct_price),
            market(league, ITEM, DIVINE, 2, 1),
            market(league, DIVINE, profile.base_currency, 1, 200),
        ]}

    service = OfficialExchangeShadowService(
        cache_root=tmp_path / "cache",
        metadata_root=metadata_root(tmp_path),
        fetcher=fetcher,
        clock=lambda: 100 * HOUR_SECONDS + 1,
    )
    service.sync(POE1, league)
    price = service.lookup(
        POE1,
        league,
        ("Test Item",),
        reference_base_price=7,
        reference_divine_rate=200,
    )
    assert price is not None
    assert price.status == "poe_ninja_fallback"
    assert price.selected_route == "poe_ninja"
    assert price.selected_price == 7


def test_tight_order_book_from_api_confirms_latest_extreme_trade(tmp_path):
    league = "Book Confirmed"

    def fetcher(profile, hour):
        direct_price = 100 if hour == 99 * HOUR_SECONDS else 7
        direct = market(league, ITEM, profile.base_currency, 1, direct_price)
        if direct_price == 100:
            direct.update({
                "lowest_ratio": {ITEM: 1, profile.base_currency: 120},
                "highest_ratio": {ITEM: 1, profile.base_currency: 80},
                "lowest_stock": {ITEM: 10, profile.base_currency: 1000},
                "highest_stock": {ITEM: 20, profile.base_currency: 2000},
            })
        return {"markets": [
            direct,
            market(league, DIVINE, profile.base_currency, 1, 200),
        ]}

    service = OfficialExchangeShadowService(
        cache_root=tmp_path / "cache",
        metadata_root=metadata_root(tmp_path),
        fetcher=fetcher,
        clock=lambda: 100 * HOUR_SECONDS + 1,
    )
    service.sync(POE1, league)
    price = service.lookup(
        POE1,
        league,
        ("Test Item",),
        reference_base_price=7,
        reference_divine_rate=200,
    )
    assert price is not None
    assert price.status == "accepted_direct"
    assert price.selected_price == 100
    assert price.direct_base.confirmations == ("order_book",)


@pytest.mark.parametrize(
    "book_fields",
    (
        {
            "lowest_ratio": {ITEM: 1, CHAOS: 400},
            "highest_ratio": {ITEM: 1, CHAOS: 80},
            "lowest_stock": {ITEM: 10, CHAOS: 1000},
            "highest_stock": {ITEM: 20, CHAOS: 2000},
        },
        {
            "lowest_ratio": {ITEM: 1, CHAOS: 17},
            "highest_ratio": {ITEM: 1, CHAOS: 10},
            "lowest_stock": {ITEM: 10, CHAOS: 1000},
            "highest_stock": {ITEM: 20, CHAOS: 2000},
        },
        {
            "lowest_ratio": {ITEM: 1, CHAOS: 120},
            "highest_ratio": {ITEM: 1, CHAOS: 80},
            "lowest_stock": {ITEM: 0, CHAOS: 1000},
            "highest_stock": {ITEM: 20, CHAOS: 2000},
        },
    ),
)
def test_wide_distant_or_empty_order_book_does_not_confirm_extreme_trade(
    tmp_path, book_fields,
):
    league = "Book Rejected"

    def fetcher(profile, hour):
        direct_price = 100 if hour == 99 * HOUR_SECONDS else 7
        direct = market(league, ITEM, profile.base_currency, 1, direct_price)
        if direct_price == 100:
            direct.update(book_fields)
        return {"markets": [
            direct,
            market(league, DIVINE, profile.base_currency, 1, 200),
        ]}

    service = OfficialExchangeShadowService(
        cache_root=tmp_path / "cache",
        metadata_root=metadata_root(tmp_path),
        fetcher=fetcher,
        clock=lambda: 100 * HOUR_SECONDS + 1,
    )
    service.sync(POE1, league)
    price = service.lookup(
        POE1,
        league,
        ("Test Item",),
        reference_base_price=7,
        reference_divine_rate=200,
    )
    assert price is not None
    assert price.status == "poe_ninja_fallback"
    assert "order_book" not in price.direct_base.confirmations


@pytest.mark.parametrize(
    ("poe_version", "expected_price", "expected_currency"),
    ((POE1, 7, CHAOS), (POE2, 70, EXALTED)),
)
def test_sync_builds_one_shared_engine_with_mode_specific_base_currency(
    tmp_path, poe_version, expected_price, expected_currency,
):
    service, calls = make_service(tmp_path)
    summary = service.sync(poe_version, "Test League")
    price = service.lookup(
        poe_version,
        "Test League",
        ("Test Item",),
        reference_base_price=expected_price,
        reference_divine_rate=200,
    )
    assert summary["fetched"] == WINDOW_HOURS
    assert len(calls) == WINDOW_HOURS
    assert service.cache_file_count(poe_version, "Test League") == WINDOW_HOURS
    assert price is not None
    assert price.selected_route == "direct_base"
    assert price.selected_price == expected_price
    assert price.selected_currency == expected_currency


def test_divine_only_real_trades_are_retained_as_divine_candidates(tmp_path):
    service, _calls = make_service(tmp_path)
    service.sync(POE2, "Test League")
    price = service.lookup(
        POE2,
        "Test League",
        ("Divine Only",),
        reference_divine_rate=200,
    )
    assert price is not None
    assert price.status == "accepted_divine"
    assert price.selected_price == 0.5
    assert price.display_currency == DIVINE
    assert price.base_equivalent == 100


@pytest.mark.parametrize(("poe_version", "name"), ((POE1, "Chaos Orb"), (POE2, "Exalted Orb")))
def test_each_games_base_currency_is_available_at_one_base_unit(tmp_path, poe_version, name):
    service, _calls = make_service(tmp_path)
    service.sync(poe_version, "Test League")
    price = service.lookup(poe_version, "Test League", (name,), reference_base_price=1)
    assert price is not None
    assert price.status == "accepted_direct"
    assert price.selected_price == 1


@pytest.mark.parametrize("poe_version", (POE1, POE2))
def test_divine_orb_uses_the_observed_game_specific_base_rate(tmp_path, poe_version):
    service, _calls = make_service(tmp_path)
    service.sync(poe_version, "Test League")
    price = service.lookup(
        poe_version,
        "Test League",
        ("Divine Orb",),
        reference_base_price=200,
        reference_divine_rate=200,
    )
    assert price is not None
    assert price.selected_route == "direct_base"
    assert price.selected_price == 200
    assert price.display_amount == 1
    assert price.display_currency == DIVINE


def test_base_price_at_one_divine_or_more_uses_divine_only_for_display(tmp_path):
    league = "High Value"

    def fetcher(profile, hour):
        return {"markets": [
            market(league, ITEM, profile.base_currency, 1, 1000),
            market(league, DIVINE, profile.base_currency, 1, 200),
        ]}

    service = OfficialExchangeShadowService(
        cache_root=tmp_path / "cache",
        metadata_root=metadata_root(tmp_path),
        fetcher=fetcher,
        clock=lambda: 100 * HOUR_SECONDS + 1,
    )
    service.sync(POE2, league)
    price = service.lookup(POE2, league, ("Test Item",), reference_divine_rate=200)
    assert price is not None
    assert price.selected_route == "direct_base"
    assert price.selected_price == 1000
    assert price.display_amount == 5
    assert price.display_currency == DIVINE
    assert price.base_equivalent == 1000


def test_next_hour_fetches_only_delta_and_keeps_cache_bounded(tmp_path):
    now = [100 * HOUR_SECONDS + 1]
    service, calls = make_service(tmp_path, clock=lambda: now[0])
    service.sync(POE1, "Test League")
    calls.clear()
    now[0] += HOUR_SECONDS
    summary = service.sync(POE1, "Test League")
    assert summary["fetched"] == 1
    assert summary["pruned"] == 1
    assert len(calls) == 1
    assert service.cache_file_count(POE1, "Test League") == WINDOW_HOURS


def test_one_week_gap_rebuilds_only_current_window_and_discards_stale_hours(tmp_path):
    now = [100 * HOUR_SECONDS + 1]
    service, calls = make_service(tmp_path, clock=lambda: now[0])
    service.sync(POE1, "Test League")
    calls.clear()
    now[0] += 7 * 24 * HOUR_SECONDS
    assert service.lookup(POE1, "Test League", ("Test Item",)) is None
    summary = service.sync(POE1, "Test League")
    assert summary["fetched"] == WINDOW_HOURS
    assert summary["pruned"] == WINDOW_HOURS
    assert len(calls) == WINDOW_HOURS
    assert service.cache_file_count(POE1, "Test League") == WINDOW_HOURS
    assert service.lookup(POE1, "Test League", ("Test Item",)) is not None


def test_corrupt_cache_hour_is_refetched_before_table_build(tmp_path):
    service, calls = make_service(tmp_path)
    service.sync(POE1, "Test League")
    calls.clear()
    corrupt = next((tmp_path / "cache" / "raw" / "poe1").glob("*/*.json.gz"))
    corrupt.write_bytes(b"broken")
    summary = service.sync(POE1, "Test League")
    assert summary["fetched"] == 1
    assert len(calls) == 1
    assert service.cache_file_count(POE1, "Test League") == WINDOW_HOURS


def test_failed_delta_fetch_keeps_previous_table_and_recovers_on_retry(tmp_path):
    now = [100 * HOUR_SECONDS + 1]
    fail = [False]

    def fetcher(profile, hour):
        if fail[0]:
            raise OSError("temporary network failure")
        return payload("Test League", profile, hour)

    service = OfficialExchangeShadowService(
        cache_root=tmp_path / "cache",
        metadata_root=metadata_root(tmp_path),
        fetcher=fetcher,
        clock=lambda: now[0],
    )
    service.sync(POE1, "Test League")
    now[0] += HOUR_SECONDS
    fail[0] = True
    with pytest.raises(OSError, match="temporary network failure"):
        service.sync(POE1, "Test League")
    assert service.lookup(POE1, "Test League", ("Test Item",)) is not None
    fail[0] = False
    summary = service.sync(POE1, "Test League")
    assert summary["fetched"] == 1
    assert summary["pruned"] == 1
    assert service.cache_file_count(POE1, "Test League") == WINDOW_HOURS


def test_stale_table_is_never_returned_as_current_price(tmp_path):
    service, _calls = make_service(tmp_path)
    service.sync(POE1, "Test League")
    stale_now = (100 + 4) * HOUR_SECONDS + 1
    assert service.lookup(POE1, "Test League", ("Test Item",), now=stale_now) is None


def test_unmapped_id_is_isolated_without_breaking_other_prices(tmp_path):
    service, _calls = make_service(tmp_path, metadata=metadata_root(tmp_path, missing_item=True))
    summary = service.sync(POE1, "Test League")
    assert summary["missing_ids"] == 1
    assert service.lookup(POE1, "Test League", ("Test Item",)) is None
    assert service.lookup(POE1, "Test League", ("Divine Only",)) is not None


def test_item_seen_only_in_unpriced_market_falls_back_without_key_error(tmp_path):
    league = "Unsupported Quote"
    other_quote = "Metadata/Items/Test/OtherQuote"
    metadata = metadata_root(tmp_path)
    for realm in ("poe1", "poe2"):
        path = metadata / f"{realm}_item_names.json"
        names = json.loads(path.read_text(encoding="utf-8"))
        names[other_quote] = "Other Quote"
        path.write_text(json.dumps(names), encoding="utf-8")

    def fetcher(profile, hour):
        return {"markets": [
            market(league, ITEM, other_quote, 1, 3),
            market(league, DIVINE, profile.base_currency, 1, 200),
        ]}

    service = OfficialExchangeShadowService(
        cache_root=tmp_path / "cache",
        metadata_root=metadata,
        fetcher=fetcher,
        clock=lambda: 100 * HOUR_SECONDS + 1,
    )
    service.sync(POE1, league)
    price = service.lookup(
        POE1,
        league,
        ("Test Item",),
        reference_base_price=7,
        reference_divine_rate=200,
    )
    assert price is not None
    assert price.status == "poe_ninja_fallback"
    assert price.direct_base.reason == "no_trades"
    assert price.direct_divine.reason == "no_trades"


def test_swapped_golden_currency_ids_stop_table_creation(tmp_path):
    service, _calls = make_service(tmp_path, metadata=metadata_root(tmp_path, swapped=True))
    with pytest.raises(ValueError, match="golden Currency Exchange ID mismatch"):
        service.sync(POE1, "Test League")


def test_normalized_name_collision_is_isolated(tmp_path):
    metadata = metadata_root(tmp_path)
    for realm in ("poe1", "poe2"):
        path = metadata / f"{realm}_item_names.json"
        names = json.loads(path.read_text(encoding="utf-8"))
        names[ITEM] = "Same  Name"
        names[DIVINE_ONLY] = "Ｓａｍｅ Name"
        path.write_text(json.dumps(names), encoding="utf-8")
    service, _calls = make_service(tmp_path, metadata=metadata)
    summary = service.sync(POE1, "Test League")
    assert summary["ambiguous_names"] == 1
    assert service.lookup(POE1, "Test League", ("Same Name",)) is None


def test_league_cache_and_tables_never_mix(tmp_path):
    prices = {"League A": 7, "League B": 70}

    def fetcher(profile, hour):
        return {"markets": [
            market(league, ITEM, profile.base_currency, 1, price)
            for league, price in prices.items()
        ] + [
            market(league, DIVINE, profile.base_currency, 1, 200)
            for league in prices
        ]}

    service = OfficialExchangeShadowService(
        cache_root=tmp_path / "cache",
        metadata_root=metadata_root(tmp_path),
        fetcher=fetcher,
        clock=lambda: 100 * HOUR_SECONDS + 1,
    )
    service.sync(POE1, "League A")
    service.sync(POE1, "League B")
    price_a = service.lookup(POE1, "League A", ("Test Item",))
    price_b = service.lookup(POE1, "League B", ("Test Item",))
    assert price_a is not None and price_a.selected_price == 7
    assert price_b is not None and price_b.selected_price == 70
    assert service.cache_file_count(POE1, "League A") == WINDOW_HOURS
    assert service.cache_file_count(POE1, "League B") == WINDOW_HOURS


def test_queue_sync_returns_before_slow_network_work_finishes(tmp_path):
    gate = threading.Event()

    def fetcher(profile, hour):
        gate.wait(timeout=2)
        return payload("Test League", profile, hour)

    service = OfficialExchangeShadowService(
        cache_root=tmp_path / "cache",
        metadata_root=metadata_root(tmp_path),
        fetcher=fetcher,
        clock=lambda: 100 * HOUR_SECONDS + 1,
    )
    started = time.perf_counter()
    assert service.queue_sync(POE1, "Test League")
    assert time.perf_counter() - started < 0.1
    gate.set()
    deadline = time.monotonic() + 2
    while service.cache_file_count(POE1, "Test League") < WINDOW_HOURS:
        assert time.monotonic() < deadline
        time.sleep(0.01)


def test_queue_sync_notifies_all_waiters_once_after_table_is_ready(tmp_path):
    gate = threading.Event()
    completed = []

    def fetcher(profile, hour):
        gate.wait(timeout=2)
        return payload("Test League", profile, hour)

    service = OfficialExchangeShadowService(
        cache_root=tmp_path / "cache",
        metadata_root=metadata_root(tmp_path),
        fetcher=fetcher,
        clock=lambda: 100 * HOUR_SECONDS + 1,
    )

    def on_complete(summary):
        completed.append(summary)

    assert service.queue_sync(POE1, "Test League", on_complete=on_complete)
    assert not service.queue_sync(POE1, "Test League", on_complete=on_complete)
    gate.set()
    deadline = time.monotonic() + 2
    while not completed:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert len(completed) == 1
    assert completed[0]["event"] == "sync_completed"
    assert service.lookup(POE1, "Test League", ("Test Item",)) is not None


def test_search_lookup_does_not_call_network(tmp_path):
    service, calls = make_service(tmp_path)
    service.sync(POE1, "Test League")
    calls.clear()
    service.record_search(
        POE1,
        "Test League",
        ("Test Item",),
        reference_base_price=7,
        reference_divine_rate=200,
    )
    assert calls == []
    event = json.loads(service.log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert event["event"] == "search_shadow"
    assert event["status"] == "accepted_direct"


def test_search_log_drops_none_names_and_suppresses_immediate_duplicates(tmp_path):
    service, _calls = make_service(tmp_path)
    service.sync(POE1, "Test League")

    for _ in range(2):
        service.record_search(
            POE1,
            "Test League",
            (None, "Test Item", "Test Item"),
            reference_base_price=7,
            reference_divine_rate=200,
        )

    events = [
        json.loads(line)
        for line in service.log_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["event"] == "search_shadow"
    ]
    assert len(events) == 1
    assert events[0]["candidate_names"] == ["Test Item"]


def test_poe_ninja_reference_conversion_respects_each_game_base_currency():
    poe1 = PoeNinjaPrice("Item", None, 7, (), "https://example.invalid", 200)
    poe2 = PoeNinjaPrice(
        "Item", None, 0, (), "https://example.invalid",
        quote_amount=0.5, quote_currency="divine",
    )
    assert poe_ninja_reference_base(POE1, poe1, divine_rate=200) == 7
    assert poe_ninja_reference_base(POE2, poe2, divine_rate=200) == 100


def test_resolve_reference_prices_prefers_official_and_keeps_ninja_fallback(tmp_path):
    service, _calls = make_service(tmp_path)
    service.sync(POE1, "Test League")
    ninja = PoeNinjaPrice(
        "Test Item", None, 9, (), "https://example.invalid", 200,
    )

    prices = resolve_reference_prices(
        POE1,
        "Test League",
        (
            ("official", ("Test Item",), ninja),
            ("fallback", ("Unknown Item",), ninja),
        ),
        reference_divine_rate=200,
        service=service,
    )

    assert prices["official"].source == "official"
    assert prices["official"].base_amount == 7
    assert prices["official"].display_price() == "7 chaos"
    assert prices["fallback"].source == "poe_ninja"
    assert prices["fallback"].base_amount == 9


def test_resolve_reference_prices_converts_official_divine_to_base(tmp_path):
    service, _calls = make_service(tmp_path)
    service.sync(POE2, "Test League")
    ninja = PoeNinjaPrice(
        "Divine Only", None, 0, (), "https://example.invalid",
        quote_amount=100, quote_currency="exalted",
    )

    price = resolve_reference_prices(
        POE2,
        "Test League",
        (("item", ("Divine Only",), ninja),),
        reference_divine_rate=200,
        service=service,
    )["item"]

    assert price.source == "official"
    assert price.display_price() == "0.5 div"
    assert price.base_amount == 100


def test_resolve_divine_rate_prefers_latest_official_rate(tmp_path):
    service, _calls = make_service(tmp_path)
    service.sync(POE2, "Test League")

    rate = resolve_divine_rate(
        POE2, "Test League", 180, service=service,
    )

    assert rate.source == "official"
    assert rate.base_amount == 200


def test_resolve_divine_rate_works_without_ninja_reference(tmp_path):
    service, _calls = make_service(tmp_path)
    service.sync(POE1, "Test League")

    rate = resolve_divine_rate(
        POE1, "Test League", None, service=service,
    )

    assert rate.source == "official"
    assert rate.base_amount == 200
