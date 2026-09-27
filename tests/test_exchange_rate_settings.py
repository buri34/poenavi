from copy import deepcopy

import pytest

from src.poetore.exchange_rate_settings import (
    CHAOS_ORB_ID,
    DIVINE_ORB_ID,
    EXALTED_ORB_ID,
    ExchangeRatePairStore,
    RatePair,
    RatePairValidationError,
    default_rate_pairs_config,
    ensure_rate_pair_config,
    normalize_rate_pairs,
)
from src.utils.poe_version_data import POE1, POE2

EXTRA_IDS = tuple(f"test-item-{number}" for number in range(1, 13))
VALID_IDS = {DIVINE_ORB_ID, CHAOS_ORB_ID, EXALTED_ORB_ID, *EXTRA_IDS}


def make_config():
    return {"poetore": {"exchange_rate_pairs": default_rate_pairs_config()}}


def make_store(config=None):
    config = config if config is not None else make_config()
    saved = []
    store = ExchangeRatePairStore(
        config,
        lambda value: saved.append(deepcopy(value)),
        catalog_ids=lambda _poe_version: VALID_IDS,
    )
    return store, config, saved


def test_defaults_are_distinct_for_each_poe_version():
    store, _, _ = make_store()

    assert store.pairs(POE1) == (RatePair(DIVINE_ORB_ID, CHAOS_ORB_ID),)
    assert store.pairs(POE2) == (RatePair(DIVINE_ORB_ID, EXALTED_ORB_ID),)


def test_ensure_defaults_preserves_explicit_empty_lists():
    config = {"poetore": {"exchange_rate_pairs": {POE1: []}}}

    ensure_rate_pair_config(config)

    assert config["poetore"]["exchange_rate_pairs"][POE1] == []
    assert config["poetore"]["exchange_rate_pairs"][POE2] == [
        RatePair(DIVINE_ORB_ID, EXALTED_ORB_ID).to_config()
    ]


def test_empty_state_survives_store_recreation():
    store, config, saved = make_store()
    store.remove(POE1, 0)

    restarted = ExchangeRatePairStore(
        deepcopy(saved[-1]),
        lambda _value: None,
        catalog_ids=lambda _poe_version: VALID_IDS,
    )

    assert config["poetore"]["exchange_rate_pairs"][POE1] == []
    assert restarted.pairs(POE1) == ()


def test_pairs_are_scoped_by_poe_version_not_league():
    store, config, _ = make_store()
    config["poetore"]["league"] = "Standard"
    store.add(POE1, EXTRA_IDS[0], DIVINE_ORB_ID)
    before = store.pairs(POE1)

    config["poetore"]["league"] = "Keepers"

    assert store.pairs(POE1) == before
    assert store.pairs(POE2) == (RatePair(DIVINE_ORB_ID, EXALTED_ORB_ID),)


def test_normalize_drops_invalid_unknown_same_and_duplicate_then_limits_to_ten():
    raw = [
        None,
        {"left_item_id": EXTRA_IDS[0]},
        {"left_item_id": 1, "right_item_id": EXTRA_IDS[1]},
        {"left_item_id": "unknown", "right_item_id": EXTRA_IDS[1]},
        {"left_item_id": EXTRA_IDS[0], "right_item_id": EXTRA_IDS[0]},
        *[
            RatePair(EXTRA_IDS[index], EXTRA_IDS[index + 1]).to_config()
            for index in range(11)
        ],
        {"left_item_id": EXTRA_IDS[0], "right_item_id": EXTRA_IDS[1]},
    ]

    assert normalize_rate_pairs(raw, VALID_IDS) == (
        *(
            RatePair(EXTRA_IDS[index], EXTRA_IDS[index + 1])
            for index in range(10)
        ),
    )
    assert normalize_rate_pairs("broken", VALID_IDS) == ()


def test_add_allows_reverse_pair_and_saves_once():
    store, _, saved = make_store()

    added = store.add(POE1, CHAOS_ORB_ID, DIVINE_ORB_ID)

    assert added == RatePair(CHAOS_ORB_ID, DIVINE_ORB_ID)
    assert store.pairs(POE1)[-1] == added
    assert len(saved) == 1


@pytest.mark.parametrize(
    ("left", "right", "code"),
    [
        (DIVINE_ORB_ID, DIVINE_ORB_ID, "same_item"),
        (DIVINE_ORB_ID, CHAOS_ORB_ID, "duplicate"),
        ("unknown", CHAOS_ORB_ID, "unknown_item"),
    ],
)
def test_add_rejects_invalid_pair_without_saving(left, right, code):
    store, _, saved = make_store()

    with pytest.raises(RatePairValidationError) as error:
        store.add(POE1, left, right)

    assert error.value.code == code
    assert saved == []


def test_add_rejects_eleventh_pair_without_saving():
    config = {"poetore": {"exchange_rate_pairs": {
        POE1: [
            RatePair(EXTRA_IDS[index], EXTRA_IDS[index + 1]).to_config()
            for index in range(10)
        ],
        POE2: [],
    }}}
    store, _, saved = make_store(config)

    with pytest.raises(RatePairValidationError) as error:
        store.add(POE1, EXTRA_IDS[10], EXTRA_IDS[11])

    assert error.value.code == "limit"
    assert saved == []


def test_remove_saves_exactly_once():
    store, _, saved = make_store()

    removed = store.remove(POE1, 0)

    assert removed == RatePair(DIVINE_ORB_ID, CHAOS_ORB_ID)
    assert store.pairs(POE1) == ()
    assert len(saved) == 1


def test_move_saves_once_and_boundary_move_does_not_save():
    store, _, saved = make_store()
    store.add(POE1, EXTRA_IDS[0], EXTRA_IDS[1])
    saved.clear()

    assert store.move_up(POE1, 1) is True
    assert store.pairs(POE1)[0] == RatePair(EXTRA_IDS[0], EXTRA_IDS[1])
    assert len(saved) == 1

    saved.clear()
    assert store.move_down(POE1, 0) is True
    assert store.pairs(POE1)[1] == RatePair(EXTRA_IDS[0], EXTRA_IDS[1])
    assert len(saved) == 1

    saved.clear()
    assert store.move_up(POE1, 0) is False
    assert store.move_down(POE1, 1) is False
    assert saved == []


def test_out_of_range_operation_is_rejected_without_saving():
    store, _, saved = make_store()

    with pytest.raises(RatePairValidationError) as error:
        store.remove(POE1, True)

    assert error.value.code == "index"
    assert saved == []
