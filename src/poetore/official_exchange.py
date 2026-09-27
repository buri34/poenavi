"""GGG Currency Exchange cache and latest-trade price evaluation."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import statistics
import sys
import tempfile
import threading
import time
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from src.utils.config_manager import ConfigManager
from src.utils.poe_version_data import POE1, POE2

HOUR_SECONDS = 3600
WINDOW_HOURS = 24
CACHE_MAX_LAG_HOURS = 2
EXTREME_PRICE_FACTOR = 3.0
PREVIOUS_HOUR_CONFIRMATION_FACTOR = 1.5
REFERENCE_CONFIRMATION_FACTOR = 2.0
ORDER_BOOK_MAX_SPREAD_FACTOR = 3.0
ORDER_BOOK_PRICE_TOLERANCE_FACTOR = 1.2
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 3
SEARCH_LOG_DEDUPE_SECONDS = 2

CHAOS = "Metadata/Items/Currency/CurrencyRerollRare"
DIVINE = "Metadata/Items/Currency/CurrencyModValues"
EXALTED = "Metadata/Items/Currency/CurrencyAddModToRare"


@dataclass(frozen=True)
class RealmProfile:
    poe_version: str
    realm: str
    base_currency: str
    base_label: str
    bridge_currency: str = DIVINE

    @property
    def api_path(self) -> str:
        return "" if self.realm == "poe1" else "/poe2"


PROFILES = {
    POE1: RealmProfile(POE1, "poe1", CHAOS, "chaos"),
    POE2: RealmProfile(POE2, "poe2", EXALTED, "exalted"),
}


@dataclass(frozen=True)
class HourlySample:
    hour: int
    price: float
    item_units: int
    order_book_supported: bool = False


@dataclass(frozen=True)
class RouteDecision:
    valid: bool
    reason: str
    price: float | None
    raw_hours: int
    kept_hours: int
    excluded_hours: int
    latest_hour: int | None
    total_item_units: int
    baseline_price: float | None = None
    extreme_factor: float | None = None
    confirmations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShadowPrice:
    item_id: str
    name: str
    status: str
    selected_route: str | None
    selected_price: float | None
    selected_currency: str | None
    display_amount: float | None
    display_currency: str | None
    base_equivalent: float | None
    divine_rate: float | None
    direct_base: RouteDecision
    direct_divine: RouteDecision
    warnings: tuple[dict, ...]


@dataclass(frozen=True)
class ResolvedReferencePrice:
    """A UI/calculation-ready price with an explicit source."""

    name: str
    base_amount: float
    display_amount: float
    display_currency: str
    source: str
    official: ShadowPrice | None = None
    fallback: object | None = None

    def display_price(self) -> str:
        value = self.display_amount
        if abs(value) < 1:
            amount = f"{value:.2f}".rstrip("0").rstrip(".")
        elif abs(value) < 10:
            amount = f"{value:.1f}".rstrip("0").rstrip(".")
        else:
            amount = str(round(value))
        suffix = "div" if self.display_currency == "divine" else self.display_currency
        return f"{amount} {suffix}"


@dataclass(frozen=True)
class DirectPairPrice:
    """A direct-market-only rate for one left item in right-item units."""

    status: str
    left_item_id: str
    right_item_id: str
    price: float | None
    end_hour: int | None
    decision: RouteDecision | None = None


@dataclass(frozen=True)
class ExchangeSyncState:
    poe_version: str
    league: str
    end_hour: int | None
    latest_hour: int
    lag_hours: int | None
    syncing: bool
    available: bool


@dataclass(frozen=True)
class SyncCheckResult:
    status: str
    poe_version: str
    league: str
    end_hour: int | None
    fetched: int = 0
    error_type: str | None = None


@dataclass(frozen=True)
class _PriceTable:
    profile: RealmProfile
    league: str
    end_hour: int
    names_by_id: dict[str, str]
    ids_by_name: dict[str, str]
    series: dict[str, dict[str, tuple[HourlySample, ...]]]
    direct_pair_series: dict[tuple[str, str], tuple[HourlySample, ...]]
    observed_ids: frozenset[str]
    divine_rate_samples: tuple[HourlySample, ...]
    missing_ids: tuple[str, ...]
    ambiguous_names: tuple[str, ...]


def latest_completed_hour(now: float | None = None) -> int:
    value = time.time() if now is None else now
    return int(value) // HOUR_SECONDS * HOUR_SECONDS - HOUR_SECONDS


def normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _candidate_names(values: Iterable[str | None]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        text
        for value in values
        if value is not None and (text := str(value).strip())
    ))


def _bundled_metadata_root() -> Path:
    """Resolve exchange metadata in source and PyInstaller onedir builds."""
    source_root = Path(__file__).resolve().parents[2]
    executable_root = Path(sys.executable).resolve().parent
    roots = (executable_root, Path(getattr(sys, "_MEIPASS", source_root)), source_root)
    relative = Path("data") / "poetore" / "currency_exchange"
    for root in roots:
        candidate = root / relative
        if candidate.is_dir():
            return candidate
    return source_root / relative


def _safe_league_folder(league: str) -> str:
    readable = re.sub(r"[^a-z0-9]+", "-", normalize_name(league)).strip("-")[:48]
    digest = hashlib.sha256(league.encode("utf-8")).hexdigest()[:10]
    return f"{readable or 'league'}-{digest}"


def _atomic_gzip_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(gzip.compress(encoded, compresslevel=6))
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def _read_gzip_json(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise TypeError(f"Invalid Currency Exchange cache payload: {path}")
    return payload


def _market_index(markets: Iterable[dict]) -> dict[frozenset[str], dict]:
    return {
        frozenset(pair): market
        for market in markets
        if len(pair := tuple(market.get("market_pair") or ())) == 2
    }


def _pair_price(
    indexed: dict[frozenset[str], dict], item_id: str, quote_id: str,
) -> tuple[float, int] | None:
    market = indexed.get(frozenset((item_id, quote_id)))
    if market is None:
        return None
    volumes = market.get("volume_traded") or {}
    item_units = int(volumes.get(item_id, 0) or 0)
    quote_units = int(volumes.get(quote_id, 0) or 0)
    if item_units <= 0 or quote_units <= 0:
        return None
    price = quote_units / item_units
    if not math.isfinite(price) or price <= 0:
        return None
    return price, item_units


def _ratio_price(values: dict, item_id: str, quote_id: str) -> float | None:
    item_units = float(values.get(item_id, 0) or 0)
    quote_units = float(values.get(quote_id, 0) or 0)
    if item_units <= 0 or quote_units <= 0:
        return None
    price = quote_units / item_units
    return price if math.isfinite(price) and price > 0 else None


def _order_book_supports(
    indexed: dict[frozenset[str], dict],
    item_id: str,
    quote_id: str,
    price: float,
) -> bool:
    market = indexed.get(frozenset((item_id, quote_id)))
    if market is None:
        return False
    ratios = [
        _ratio_price(market.get(key) or {}, item_id, quote_id)
        for key in ("lowest_ratio", "highest_ratio")
    ]
    if any(value is None for value in ratios):
        return False
    stocks = [
        float((market.get(key) or {}).get(currency, 0) or 0)
        for key in ("lowest_stock", "highest_stock")
        for currency in (item_id, quote_id)
    ]
    if not stocks or min(stocks) <= 0:
        return False
    lower, upper = min(ratios), max(ratios)
    if upper / lower > ORDER_BOOK_MAX_SPREAD_FACTOR:
        return False
    return (
        lower / ORDER_BOOK_PRICE_TOLERANCE_FACTOR
        <= price
        <= upper * ORDER_BOOK_PRICE_TOLERANCE_FACTOR
    )


def _pair_sample(
    indexed: dict[frozenset[str], dict],
    item_id: str,
    quote_id: str,
    hour: int,
) -> HourlySample | None:
    result = _pair_price(indexed, item_id, quote_id)
    if result is None:
        return None
    price, item_units = result
    return HourlySample(
        hour=hour,
        price=price,
        item_units=item_units,
        order_book_supported=_order_book_supports(
            indexed, item_id, quote_id, price,
        ),
    )


def evaluate_route(
    samples: Iterable[HourlySample], reference_price: float | None = None,
) -> RouteDecision:
    values = sorted(samples, key=lambda sample: sample.hour)
    if not values:
        return RouteDecision(False, "no_trades", None, 0, 0, 0, None, 0)

    latest = values[-1]
    prior = values[:-1]
    candidate = latest.price
    baseline = statistics.median(sample.price for sample in prior) if prior else None
    extreme_factor = (
        max(candidate / baseline, baseline / candidate)
        if baseline is not None and baseline > 0 else None
    )
    confirmations = []
    if (
        prior
        and prior[-1].hour == latest.hour - HOUR_SECONDS
        and max(candidate / prior[-1].price, prior[-1].price / candidate)
        <= PREVIOUS_HOUR_CONFIRMATION_FACTOR
    ):
        confirmations.append("previous_hour")
    if latest.order_book_supported:
        confirmations.append("order_book")
    reference_factor = None
    if reference_price is not None and reference_price > 0:
        reference_factor = max(
            candidate / reference_price, reference_price / candidate,
        )
        if reference_factor <= REFERENCE_CONFIRMATION_FACTOR:
            confirmations.append("poe_ninja")

    is_extreme = (
        len(prior) >= 3
        and extreme_factor is not None
        and extreme_factor > EXTREME_PRICE_FACTOR
    )
    lacks_sparse_confirmation = (
        len(prior) < 3
        and reference_factor is not None
        and reference_factor > REFERENCE_CONFIRMATION_FACTOR
        and not confirmations
    )
    if is_extreme and not confirmations:
        valid = False
        reason = "latest_extreme_unconfirmed"
    elif lacks_sparse_confirmation:
        valid = False
        reason = (
            "single_observation_reference_conflict"
            if len(values) == 1 else "latest_sparse_reference_conflict"
        )
    elif is_extreme:
        valid = True
        reason = "latest_extreme_confirmed"
    elif "previous_hour" in confirmations and reference_factor is not None:
        valid = True
        reason = "latest_observation_previous_confirmed"
    elif len(values) == 1 and "poe_ninja" in confirmations:
        valid = True
        reason = "single_observation_reference_confirmed"
    elif len(values) == 1:
        valid = True
        reason = "single_observation_unchecked"
    else:
        valid = True
        reason = "latest_observation"

    return RouteDecision(
        valid=valid,
        reason=reason,
        price=candidate,
        raw_hours=len(values),
        kept_hours=len(values),
        excluded_hours=0,
        latest_hour=latest.hour,
        total_item_units=sum(sample.item_units for sample in values),
        baseline_price=baseline,
        extreme_factor=extreme_factor,
        confirmations=tuple(confirmations),
    )


def _route_dict(decision: RouteDecision) -> dict:
    return {
        "valid": decision.valid,
        "reason": decision.reason,
        "price": decision.price,
        "raw_hours": decision.raw_hours,
        "kept_hours": decision.kept_hours,
        "excluded_hours": decision.excluded_hours,
        "latest_hour": decision.latest_hour,
        "total_item_units": decision.total_item_units,
        "baseline_price": decision.baseline_price,
        "extreme_factor": decision.extreme_factor,
        "confirmations": decision.confirmations,
    }


def _default_fetcher(profile: RealmProfile, hour: int) -> dict:
    url = f"https://web.poecdn.com/api/currency-exchange{profile.api_path}/{hour}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": "PoENavi/poetore-official-shadow",
        },
    )
    with urlopen(request, timeout=45) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise TypeError("Currency Exchange API returned a non-object payload")
    return payload


class OfficialExchangeShadowService:
    """Maintain bounded official-price state for lookup, audit, and display."""

    def __init__(
        self,
        *,
        cache_root: Path | None = None,
        metadata_root: Path | None = None,
        fetcher: Callable[[RealmProfile, int], dict] = _default_fetcher,
        clock: Callable[[], float] = time.time,
    ):
        self.cache_root = cache_root or ConfigManager.get_user_data_path(
            "poetore-official-exchange"
        )
        self.metadata_root = metadata_root or _bundled_metadata_root()
        self._fetcher = fetcher
        self._clock = clock
        self._tables: dict[tuple[str, str], _PriceTable] = {}
        self._active_syncs: set[tuple[str, str]] = set()
        self._sync_callbacks: dict[tuple[str, str], list[Callable[[dict], None]]] = {}
        self._check_callbacks: dict[
            tuple[str, str], list[Callable[[SyncCheckResult], None]]
        ] = {}
        self._last_search_fingerprint: tuple | None = None
        self._last_search_logged_at = 0.0
        self._lock = threading.RLock()

    @property
    def log_path(self) -> Path:
        return self.cache_root / "shadow.jsonl"

    def queue_sync(
        self,
        poe_version: str,
        league: str | None,
        *,
        on_complete: Callable[[dict], None] | None = None,
        on_checked: Callable[[SyncCheckResult], None] | None = None,
    ) -> bool:
        if poe_version not in PROFILES or not league or re.search(r"\(PL\d+\)$", league):
            if on_checked is not None:
                self._notify_check_callback(on_checked, SyncCheckResult(
                    "failed", poe_version, league or "", None,
                    error_type="invalid_request",
                ))
            return False
        key = (poe_version, league)
        no_new_result = None
        with self._lock:
            if key in self._active_syncs:
                if on_complete is not None:
                    callbacks = self._sync_callbacks.setdefault(key, [])
                    if on_complete not in callbacks:
                        callbacks.append(on_complete)
                if on_checked is not None:
                    callbacks = self._check_callbacks.setdefault(key, [])
                    if on_checked not in callbacks:
                        callbacks.append(on_checked)
                return False
            current = self._tables.get(key)
            if current is not None and current.end_hour >= latest_completed_hour(self._clock()):
                no_new_result = SyncCheckResult(
                    "no_new_data", poe_version, league, current.end_hour,
                )
            if no_new_result is None:
                if on_complete is not None:
                    callbacks = self._sync_callbacks.setdefault(key, [])
                    if on_complete not in callbacks:
                        callbacks.append(on_complete)
                if on_checked is not None:
                    callbacks = self._check_callbacks.setdefault(key, [])
                    if on_checked not in callbacks:
                        callbacks.append(on_checked)
                self._active_syncs.add(key)
                previous_end_hour = current.end_hour if current is not None else None

        if no_new_result is not None:
            if on_checked is not None:
                self._notify_check_callback(on_checked, no_new_result)
            return False

        def run() -> None:
            result = None
            check_result = None
            try:
                result = self.sync(poe_version, league)
            except Exception as exc:  # noqa: BLE001 - daemon boundary must contain failures
                check_result = SyncCheckResult(
                    "failed", poe_version, league, previous_end_hour,
                    error_type=type(exc).__name__,
                )
                self._append_log({
                    "event": "sync_failed",
                    "poe_version": poe_version,
                    "league": league,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                })
            finally:
                with self._lock:
                    self._active_syncs.discard(key)
                    callbacks = tuple(self._sync_callbacks.pop(key, ()))
                    check_callbacks = tuple(self._check_callbacks.pop(key, ()))
            if result is not None:
                check_result = SyncCheckResult(
                    "updated" if previous_end_hour != result["end_hour"] else "no_new_data",
                    poe_version,
                    league,
                    result["end_hour"],
                    fetched=result["fetched"],
                )
                for callback in callbacks:
                    self._notify_completion_callback(callback, result)
            if check_result is not None:
                for callback in check_callbacks:
                    self._notify_check_callback(callback, check_result)

        threading.Thread(target=run, daemon=True).start()
        return True

    @staticmethod
    def _notify_completion_callback(
        callback: Callable[[dict], None], result: dict,
    ) -> None:
        try:
            callback(result)
        except Exception:  # noqa: BLE001, S110 - observers cannot fail sync
            pass

    @staticmethod
    def _notify_check_callback(
        callback: Callable[[SyncCheckResult], None], result: SyncCheckResult,
    ) -> None:
        try:
            callback(result)
        except Exception:  # noqa: BLE001, S110 - observers cannot fail sync
            pass

    def sync(self, poe_version: str, league: str, *, now: float | None = None) -> dict:
        profile = PROFILES[poe_version]
        started = time.perf_counter()
        end_hour = latest_completed_hour(self._clock() if now is None else now)
        required_hours = tuple(
            end_hour - offset * HOUR_SECONDS for offset in reversed(range(WINDOW_HOURS))
        )
        folder = self._snapshot_folder(profile, league)
        missing = []
        for hour in required_hours:
            path = self._snapshot_path(folder, hour)
            if self._valid_snapshot(path, profile, league, hour):
                continue
            if path.exists():
                path.unlink()
            missing.append(hour)
        fetched = 0
        for hour in missing:
            payload = self._fetcher(profile, hour)
            markets = [
                market for market in payload.get("markets", ())
                if market.get("league") == league
            ]
            if not markets:
                raise RuntimeError(
                    f"No Currency Exchange markets for {profile.realm}/{league} at {hour}"
                )
            _atomic_gzip_json(self._snapshot_path(folder, hour), {
                "schema": 1,
                "realm": profile.realm,
                "league": league,
                "hour": hour,
                "markets": markets,
            })
            fetched += 1

        required = set(required_hours)
        pruned = 0
        for path in folder.glob("*.json.gz"):
            try:
                hour = int(path.name.removesuffix(".json.gz"))
            except ValueError:
                continue
            if hour not in required:
                path.unlink()
                pruned += 1

        paths = [self._snapshot_path(folder, hour) for hour in required_hours]
        if not all(path.exists() for path in paths):
            raise RuntimeError("Currency Exchange 24-hour cache is incomplete")
        table = self._build_table(profile, league, end_hour, paths)
        with self._lock:
            self._tables[(poe_version, league)] = table

        result = {
            "event": "sync_completed",
            "poe_version": poe_version,
            "realm": profile.realm,
            "league": league,
            "end_hour": end_hour,
            "window_hours": WINDOW_HOURS,
            "missing_before": len(missing),
            "fetched": fetched,
            "pruned": pruned,
            "items": len(table.series),
            "missing_ids": len(table.missing_ids),
            "ambiguous_names": len(table.ambiguous_names),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        self._append_log(result)
        return result

    def lookup(
        self,
        poe_version: str,
        league: str,
        candidate_names: Iterable[str | None],
        *,
        reference_base_price: float | None = None,
        reference_divine_rate: float | None = None,
        now: float | None = None,
    ) -> ShadowPrice | None:
        profile = PROFILES.get(poe_version)
        if profile is None:
            return None
        table = self._table_for(poe_version, league, now=now)
        if table is None:
            return None
        item_id = next((
            table.ids_by_name.get(normalize_name(name))
            for name in _candidate_names(candidate_names)
        ), None)
        if item_id is None:
            return None

        routes = table.series.get(item_id, {
            "direct_base": (),
            "direct_divine": (),
        })
        divine_reference = (
            reference_base_price / reference_divine_rate
            if reference_base_price and reference_divine_rate and reference_divine_rate > 0
            else None
        )
        direct = evaluate_route(routes["direct_base"], reference_base_price)
        divine = evaluate_route(routes["direct_divine"], divine_reference)
        rate = evaluate_route(table.divine_rate_samples, reference_divine_rate)
        divine_rate = rate.price if rate.valid else None
        warnings: list[dict] = []

        if direct.valid:
            status = "accepted_direct"
            selected_route = "direct_base"
            selected_price = direct.price
            selected_currency = profile.base_currency
            if divine.valid and divine_rate and direct.price and divine.price:
                converted = divine.price * divine_rate
                factor = max(direct.price / converted, converted / direct.price)
                if factor > 1.5:
                    warnings.append({"code": "cross_route_conflict", "factor": factor})
        elif direct.raw_hours == 0 and divine.valid:
            status = "accepted_divine"
            selected_route = "direct_divine"
            selected_price = divine.price
            selected_currency = profile.bridge_currency
        elif reference_base_price is not None and reference_base_price > 0:
            status = "poe_ninja_fallback"
            selected_route = "poe_ninja"
            selected_price = reference_base_price
            selected_currency = profile.base_currency
        else:
            status = "no_accepted_price"
            selected_route = None
            selected_price = None
            selected_currency = None

        display_amount = selected_price
        display_currency = selected_currency
        base_equivalent = None
        if selected_price is not None and selected_currency == profile.bridge_currency:
            base_equivalent = selected_price * divine_rate if divine_rate else None
        elif selected_price is not None and selected_currency == profile.base_currency:
            base_equivalent = selected_price
            if divine_rate and selected_price >= divine_rate:
                display_amount = selected_price / divine_rate
                display_currency = profile.bridge_currency

        return ShadowPrice(
            item_id=item_id,
            name=table.names_by_id[item_id],
            status=status,
            selected_route=selected_route,
            selected_price=selected_price,
            selected_currency=selected_currency,
            display_amount=display_amount,
            display_currency=display_currency,
            base_equivalent=base_equivalent,
            divine_rate=divine_rate,
            direct_base=direct,
            direct_divine=divine,
            warnings=tuple(warnings),
        )

    def direct_pair(
        self,
        poe_version: str,
        league: str,
        left_item_id: str,
        right_item_id: str,
        *,
        now: float | None = None,
    ) -> DirectPairPrice:
        """Resolve only real trades for the requested directed market pair."""
        table = self._table_for(poe_version, league, now=now)
        if table is None or left_item_id == right_item_id:
            return DirectPairPrice(
                "unavailable", left_item_id, right_item_id, None, None,
            )

        decision = evaluate_route(
            table.direct_pair_series.get((left_item_id, right_item_id), ())
        )
        if decision.raw_hours == 0:
            status = "no_trades"
            price = None
        elif not decision.valid:
            status = "unconfirmed"
            price = None
        else:
            status = "available"
            price = decision.price
        return DirectPairPrice(
            status,
            left_item_id,
            right_item_id,
            price,
            table.end_hour,
            decision,
        )

    def exchange_item_ids(
        self, poe_version: str, league: str, *, now: float | None = None,
    ) -> frozenset[str]:
        """Return IDs observed anywhere in the current 24-hour market table."""
        table = self._table_for(poe_version, league, now=now)
        return table.observed_ids if table is not None else frozenset()

    def sync_state(
        self, poe_version: str, league: str, *, now: float | None = None,
    ) -> ExchangeSyncState:
        current_time = self._clock() if now is None else now
        latest = latest_completed_hour(current_time)
        key = (poe_version, league)
        with self._lock:
            table = self._tables.get(key)
            syncing = key in self._active_syncs
        end_hour = table.end_hour if table is not None else None
        lag_hours = (
            (latest - end_hour) // HOUR_SECONDS if end_hour is not None else None
        )
        available = bool(
            table is not None
            and lag_hours is not None
            and 0 <= lag_hours <= CACHE_MAX_LAG_HOURS
        )
        return ExchangeSyncState(
            poe_version,
            league,
            end_hour,
            latest,
            lag_hours,
            syncing,
            available,
        )

    def record_search(
        self,
        poe_version: str,
        league: str,
        candidate_names: Iterable[str | None],
        *,
        reference_base_price: float | None,
        reference_divine_rate: float | None,
    ) -> ShadowPrice | None:
        started = time.perf_counter()
        names = _candidate_names(candidate_names)
        price = self.lookup(
            poe_version,
            league,
            names,
            reference_base_price=reference_base_price,
            reference_divine_rate=reference_divine_rate,
        )
        event = {
            "event": "search_shadow",
            "poe_version": poe_version,
            "league": league,
            "candidate_names": names,
            "reference_base_price": reference_base_price,
            "reference_divine_rate": reference_divine_rate,
            "lookup_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        if price is None:
            event["status"] = "no_official_candidate"
        else:
            event.update({
                "item_id": price.item_id,
                "matched_name": price.name,
                "status": price.status,
                "selected_route": price.selected_route,
                "selected_price": price.selected_price,
                "selected_currency": price.selected_currency,
                "display_amount": price.display_amount,
                "display_currency": price.display_currency,
                "base_equivalent": price.base_equivalent,
                "divine_rate": price.divine_rate,
                "direct_base": _route_dict(price.direct_base),
                "direct_divine": _route_dict(price.direct_divine),
                "warnings": price.warnings,
            })
        fingerprint = (
            poe_version,
            league,
            names,
            reference_base_price,
            reference_divine_rate,
            event.get("status"),
            event.get("item_id"),
            event.get("selected_route"),
            event.get("selected_price"),
        )
        logged_at = self._clock()
        with self._lock:
            is_duplicate = (
                fingerprint == self._last_search_fingerprint
                and 0 <= logged_at - self._last_search_logged_at
                <= SEARCH_LOG_DEDUPE_SECONDS
            )
            if not is_duplicate:
                self._last_search_fingerprint = fingerprint
                self._last_search_logged_at = logged_at
        if not is_duplicate:
            self._append_log(event)
        return price

    def cache_file_count(self, poe_version: str, league: str) -> int:
        return len(tuple(self._snapshot_folder(PROFILES[poe_version], league).glob("*.json.gz")))

    def _table_for(
        self, poe_version: str, league: str, *, now: float | None,
    ) -> _PriceTable | None:
        with self._lock:
            table = self._tables.get((poe_version, league))
        if table is None:
            return None
        latest = latest_completed_hour(self._clock() if now is None else now)
        lag_hours = (latest - table.end_hour) // HOUR_SECONDS
        return table if 0 <= lag_hours <= CACHE_MAX_LAG_HOURS else None

    def _snapshot_folder(self, profile: RealmProfile, league: str) -> Path:
        return self.cache_root / "raw" / profile.realm / _safe_league_folder(league)

    @staticmethod
    def _snapshot_path(folder: Path, hour: int) -> Path:
        return folder / f"{hour}.json.gz"

    @staticmethod
    def _valid_snapshot(
        path: Path, profile: RealmProfile, league: str, hour: int,
    ) -> bool:
        if not path.exists():
            return False
        try:
            payload = _read_gzip_json(path)
            return bool(
                payload.get("schema") == 1
                and payload.get("realm") == profile.realm
                and payload.get("league") == league
                and int(payload.get("hour", -1)) == hour
                and isinstance(payload.get("markets"), list)
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

    def _load_names(self, profile: RealmProfile) -> dict[str, str]:
        path = self.metadata_root / f"{profile.realm}_item_names.json"
        with path.open("r", encoding="utf-8") as source:
            payload = json.load(source)
        if not isinstance(payload, dict):
            raise TypeError(f"Invalid bundled exchange metadata: {path}")
        return {
            str(item_id): str(name).strip()
            for item_id, name in payload.items() if str(name).strip()
        }

    def _build_table(
        self,
        profile: RealmProfile,
        league: str,
        end_hour: int,
        paths: Iterable[Path],
    ) -> _PriceTable:
        names = self._load_names(profile)
        golden = {
            CHAOS: "chaos orb",
            DIVINE: "divine orb",
            EXALTED: "exalted orb",
        }
        for item_id, expected in golden.items():
            if normalize_name(names.get(item_id, "")) != expected:
                raise ValueError(f"Bundled golden Currency Exchange ID mismatch: {item_id}")

        series: dict[str, dict[str, list[HourlySample]]] = defaultdict(
            lambda: {"direct_base": [], "direct_divine": []}
        )
        direct_pairs: dict[tuple[str, str], list[HourlySample]] = defaultdict(list)
        divine_rates: list[HourlySample] = []
        observed_ids: set[str] = set()
        for path in paths:
            snapshot = _read_gzip_json(path)
            if snapshot.get("realm") != profile.realm or snapshot.get("league") != league:
                raise ValueError(f"Cross-realm or cross-league cache entry: {path}")
            hour = int(snapshot["hour"])
            markets = snapshot.get("markets") or []
            indexed = _market_index(markets)
            ids = {
                item_id for market in markets
                for item_id in market.get("market_pair", ())
            }
            observed_ids.update(ids)
            for market_pair in indexed:
                if len(market_pair) != 2:
                    continue
                left_item_id, right_item_id = sorted(market_pair)
                for left_id, right_id in (
                    (left_item_id, right_item_id),
                    (right_item_id, left_item_id),
                ):
                    sample = _pair_sample(indexed, left_id, right_id, hour)
                    if sample is not None:
                        direct_pairs[(left_id, right_id)].append(sample)
            rate_sample = _pair_sample(
                indexed, profile.bridge_currency, profile.base_currency, hour,
            )
            if rate_sample:
                divine_rates.append(rate_sample)
                series[profile.bridge_currency]["direct_base"].append(rate_sample)
            # The base unit is definitionally worth one of itself.  This keeps
            # Chaos/Exalted searches visible in shadow logs without inventing a
            # same-currency market pair.
            series[profile.base_currency]["direct_base"].append(
                HourlySample(hour, 1.0, 1)
            )
            for item_id in ids - {profile.base_currency, profile.bridge_currency}:
                direct = _pair_sample(indexed, item_id, profile.base_currency, hour)
                divine = _pair_sample(indexed, item_id, profile.bridge_currency, hour)
                if direct:
                    series[item_id]["direct_base"].append(direct)
                if divine:
                    series[item_id]["direct_divine"].append(divine)

        missing_ids = tuple(sorted(item_id for item_id in observed_ids if item_id not in names))
        by_name: dict[str, list[str]] = defaultdict(list)
        for item_id in observed_ids - set(missing_ids):
            by_name[normalize_name(names[item_id])].append(item_id)
        ambiguous = tuple(sorted(name for name, ids in by_name.items() if len(ids) != 1))
        ids_by_name = {
            name: ids[0] for name, ids in by_name.items() if len(ids) == 1
        }
        safe_ids = set(ids_by_name.values())
        frozen_series = {
            item_id: {
                route: tuple(samples) for route, samples in routes.items()
            }
            for item_id, routes in series.items() if item_id in safe_ids
        }
        return _PriceTable(
            profile=profile,
            league=league,
            end_hour=end_hour,
            names_by_id={item_id: names[item_id] for item_id in safe_ids},
            ids_by_name=ids_by_name,
            series=frozen_series,
            direct_pair_series={
                pair: tuple(samples) for pair, samples in direct_pairs.items()
            },
            observed_ids=frozenset(observed_ids),
            divine_rate_samples=tuple(divine_rates),
            missing_ids=missing_ids,
            ambiguous_names=ambiguous,
        )

    def _append_log(self, payload: dict) -> None:
        path = self.log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if path.exists() and path.stat().st_size >= LOG_MAX_BYTES:
                oldest = path.with_suffix(f".jsonl.{LOG_BACKUPS}")
                if oldest.exists():
                    oldest.unlink()
                for index in reversed(range(1, LOG_BACKUPS)):
                    source = path.with_suffix(f".jsonl.{index}")
                    if source.exists():
                        source.replace(path.with_suffix(f".jsonl.{index + 1}"))
                path.replace(path.with_suffix(".jsonl.1"))
            event = {"logged_at": int(self._clock()), **payload}
            with path.open("a", encoding="utf-8") as destination:
                destination.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
                destination.write("\n")


def poe_ninja_reference_base(
    poe_version: str,
    price: object | None,
    *,
    divine_rate: float | None,
) -> float | None:
    if price is None:
        return None
    if poe_version == POE1:
        value = float(getattr(price, "chaos", 0) or 0)
        return value if value > 0 else None
    amount = float(getattr(price, "quote_amount", 0) or 0)
    currency = str(getattr(price, "quote_currency", "") or "").casefold()
    if amount <= 0:
        return None
    if currency == "exalted":
        return amount
    if currency == "divine" and divine_rate and divine_rate > 0:
        return amount * divine_rate
    return None


def resolve_reference_prices(
    poe_version: str,
    league: str,
    entries: Iterable[tuple[object, Iterable[str | None], object | None]],
    *,
    reference_divine_rate: float | None,
    service: OfficialExchangeShadowService | None = None,
) -> dict[object, ResolvedReferencePrice | None]:
    """Resolve many prices from the local official table with ninja fallback."""
    active_service = service or default_official_exchange_shadow_service
    resolved: dict[object, ResolvedReferencePrice | None] = {}
    for key, candidate_names, fallback in entries:
        names = _candidate_names(candidate_names)
        reference_base = poe_ninja_reference_base(
            poe_version, fallback, divine_rate=reference_divine_rate,
        )
        official = active_service.lookup(
            poe_version,
            league,
            names,
            reference_base_price=reference_base,
            reference_divine_rate=reference_divine_rate,
        )
        if (
            official is not None
            and official.status in {"accepted_direct", "accepted_divine"}
            and official.selected_price is not None
            and official.display_amount is not None
        ):
            base_amount = official.base_equivalent
            if (
                base_amount is None
                and official.selected_currency == DIVINE
                and reference_divine_rate
                and reference_divine_rate > 0
            ):
                base_amount = official.selected_price * reference_divine_rate
            display_currency = {
                CHAOS: "chaos", DIVINE: "divine", EXALTED: "exalted",
            }.get(official.display_currency)
            if base_amount is not None and base_amount > 0 and display_currency:
                resolved[key] = ResolvedReferencePrice(
                    name=official.name,
                    base_amount=float(base_amount),
                    display_amount=float(official.display_amount),
                    display_currency=display_currency,
                    source="official",
                    official=official,
                    fallback=fallback,
                )
                continue
        if fallback is None or reference_base is None or reference_base <= 0:
            resolved[key] = None
            continue
        display_parts = getattr(fallback, "display_price_parts", None)
        if callable(display_parts):
            amount_text, currency = display_parts()
            try:
                display_amount = float(amount_text)
            except (TypeError, ValueError):
                display_amount = reference_base
                currency = PROFILES[poe_version].base_label
        else:
            display_amount = reference_base
            currency = PROFILES[poe_version].base_label
        resolved[key] = ResolvedReferencePrice(
            name=str(getattr(fallback, "name", None) or next(iter(names), "")),
            base_amount=float(reference_base),
            display_amount=float(display_amount),
            display_currency=str(currency),
            source="poe_ninja",
            fallback=fallback,
        )
    return resolved


def resolve_divine_rate(
    poe_version: str,
    league: str,
    reference_rate: float | None,
    *,
    service: OfficialExchangeShadowService | None = None,
) -> ResolvedReferencePrice | None:
    """Resolve one Divine Orb in the game's base currency."""
    active_service = service or default_official_exchange_shadow_service
    official = active_service.lookup(
        poe_version,
        league,
        ("Divine Orb",),
        reference_base_price=reference_rate,
        reference_divine_rate=reference_rate,
    )
    if (
        official is not None
        and official.status in {"accepted_direct", "accepted_divine"}
        and official.base_equivalent is not None
        and official.base_equivalent > 0
    ):
        return ResolvedReferencePrice(
            name="Divine Orb",
            base_amount=float(official.base_equivalent),
            display_amount=float(official.base_equivalent),
            display_currency=PROFILES[poe_version].base_label,
            source="official",
            official=official,
        )
    if reference_rate is None or reference_rate <= 0:
        return None
    return ResolvedReferencePrice(
        name="Divine Orb",
        base_amount=float(reference_rate),
        display_amount=float(reference_rate),
        display_currency=PROFILES[poe_version].base_label,
        source="poe_ninja",
    )


default_official_exchange_shadow_service = OfficialExchangeShadowService()
