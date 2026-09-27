import json

import pytest

from src.poetore.exchange_rate_cache import (
    CACHE_TTL_SECONDS,
    ExchangeRateValueCache,
)
from src.utils.poe_version_data import POE1, POE2

LEFT = "left"
RIGHT = "right"


def test_value_is_restored_only_for_exact_realm_league_and_direction(tmp_path):
    path = tmp_path / "rates.json"
    cache = ExchangeRateValueCache(path, clock=lambda: 1000)
    cache.put(POE1, "League A", LEFT, RIGHT, 12.5, 720)

    restarted = ExchangeRateValueCache(path, clock=lambda: 1001)

    assert restarted.get(POE1, "League A", LEFT, RIGHT).price == 12.5
    assert restarted.get(POE2, "League A", LEFT, RIGHT) is None
    assert restarted.get(POE1, "League B", LEFT, RIGHT) is None
    assert restarted.get(POE1, "League A", RIGHT, LEFT) is None


def test_value_expires_after_24_hours(tmp_path):
    path = tmp_path / "rates.json"
    cache = ExchangeRateValueCache(path)
    cache.put(POE1, "League", LEFT, RIGHT, 2, 720, confirmed_at=1000)

    assert cache.get(
        POE1, "League", LEFT, RIGHT, now=1000 + CACHE_TTL_SECONDS,
    ) is not None
    assert cache.get(
        POE1, "League", LEFT, RIGHT, now=1001 + CACHE_TTL_SECONDS,
    ) is None


def test_put_replaces_only_the_same_directed_key(tmp_path):
    cache = ExchangeRateValueCache(tmp_path / "rates.json", clock=lambda: 1000)
    cache.put(POE1, "League", LEFT, RIGHT, 2, 720)
    cache.put(POE1, "League", RIGHT, LEFT, 0.5, 720)
    cache.put(POE1, "League", LEFT, RIGHT, 3, 720)

    assert cache.get(POE1, "League", LEFT, RIGHT).price == 3
    assert cache.get(POE1, "League", RIGHT, LEFT).price == 0.5
    assert len(json.loads(cache.path.read_text())["entries"]) == 2


@pytest.mark.parametrize("price", (0, -1, float("inf"), float("nan")))
def test_invalid_price_is_rejected_without_writing(tmp_path, price):
    path = tmp_path / "rates.json"
    cache = ExchangeRateValueCache(path)

    with pytest.raises(ValueError):
        cache.put(POE1, "League", LEFT, RIGHT, price, 720)

    assert not path.exists()


def test_broken_rows_are_ignored_without_losing_valid_rows(tmp_path):
    path = tmp_path / "rates.json"
    path.write_text(json.dumps({
        "schema": 1,
        "entries": [
            {"broken": True},
            {
                "poe_version": POE1,
                "league": "League",
                "left_item_id": None,
                "right_item_id": RIGHT,
                "price": 99,
                "source_end_hour": 720,
                "confirmed_at": 1000,
            },
            {
                "poe_version": POE1,
                "league": "League",
                "left_item_id": LEFT,
                "right_item_id": RIGHT,
                "price": 4,
                "source_end_hour": 720,
                "confirmed_at": 1000,
            },
        ],
    }), encoding="utf-8")
    cache = ExchangeRateValueCache(path, clock=lambda: 1001)

    assert cache.get(POE1, "League", LEFT, RIGHT).price == 4


def test_non_list_entries_are_treated_as_an_empty_cache(tmp_path):
    path = tmp_path / "rates.json"
    path.write_text('{"schema": 1, "entries": null}', encoding="utf-8")

    cache = ExchangeRateValueCache(path, clock=lambda: 1001)

    assert cache.get(POE1, "League", LEFT, RIGHT) is None
