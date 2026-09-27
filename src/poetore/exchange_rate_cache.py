"""Persistent last-confirmed values for custom Currency Exchange rate rows."""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from src.utils.config_manager import ConfigManager
from src.utils.poe_version_data import POE1, POE2

CACHE_SCHEMA = 1
CACHE_TTL_SECONDS = 24 * 60 * 60
MAX_CACHE_ENTRIES = 200


@dataclass(frozen=True)
class CachedRateValue:
    poe_version: str
    league: str
    left_item_id: str
    right_item_id: str
    price: float
    source_end_hour: int
    confirmed_at: int


class ExchangeRateValueCache:
    """Store exact realm, league, and pair-direction values for at most 24 hours."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        clock=time.time,
    ):
        self.path = path or ConfigManager.get_user_data_path(
            "poetore-exchange-rate-values.json"
        )
        self._clock = clock
        self._lock = threading.RLock()

    def get(
        self,
        poe_version: str,
        league: str,
        left_item_id: str,
        right_item_id: str,
        *,
        now: float | None = None,
    ) -> CachedRateValue | None:
        current_time = self._clock() if now is None else now
        key = (poe_version, league, left_item_id, right_item_id)
        with self._lock:
            entries = self._read_entries()
        for entry in entries:
            if self._entry_key(entry) != key:
                continue
            age = current_time - entry.confirmed_at
            return entry if 0 <= age <= CACHE_TTL_SECONDS else None
        return None

    def put(
        self,
        poe_version: str,
        league: str,
        left_item_id: str,
        right_item_id: str,
        price: float,
        source_end_hour: int,
        *,
        confirmed_at: float | None = None,
    ) -> CachedRateValue:
        if poe_version not in {POE1, POE2} or not league:
            raise ValueError("A supported PoE version and league are required")
        if left_item_id == right_item_id:
            raise ValueError("A cached rate pair must contain two different items")
        if not math.isfinite(price) or price <= 0:
            raise ValueError("A cached rate price must be finite and positive")
        timestamp = int(self._clock() if confirmed_at is None else confirmed_at)
        value = CachedRateValue(
            poe_version,
            league,
            left_item_id,
            right_item_id,
            float(price),
            int(source_end_hour),
            timestamp,
        )
        key = self._entry_key(value)
        with self._lock:
            entries = [
                entry for entry in self._read_entries()
                if self._entry_key(entry) != key
                and 0 <= timestamp - entry.confirmed_at <= CACHE_TTL_SECONDS
            ]
            entries.append(value)
            entries = sorted(
                entries, key=lambda entry: entry.confirmed_at, reverse=True,
            )[:MAX_CACHE_ENTRIES]
            self._write_entries(entries)
        return value

    @staticmethod
    def _entry_key(value: CachedRateValue) -> tuple[str, str, str, str]:
        return (
            value.poe_version,
            value.league,
            value.left_item_id,
            value.right_item_id,
        )

    def _read_entries(self) -> list[CachedRateValue]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return []
        if (
            not isinstance(payload, dict)
            or type(payload.get("schema")) is not int
            or payload["schema"] != CACHE_SCHEMA
        ):
            return []
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            return []
        entries = []
        for row in raw_entries:
            if not isinstance(row, dict):
                continue
            if not all(isinstance(row.get(key), str) for key in (
                "poe_version", "league", "left_item_id", "right_item_id",
            )):
                continue
            if type(row.get("source_end_hour")) is not int:
                continue
            if type(row.get("confirmed_at")) is not int:
                continue
            if not isinstance(row.get("price"), (int, float)) or isinstance(
                row.get("price"), bool,
            ):
                continue
            try:
                value = CachedRateValue(
                    poe_version=row["poe_version"],
                    league=row["league"],
                    left_item_id=row["left_item_id"],
                    right_item_id=row["right_item_id"],
                    price=float(row["price"]),
                    source_end_hour=row["source_end_hour"],
                    confirmed_at=row["confirmed_at"],
                )
            except (TypeError, ValueError):
                continue
            if (
                value.poe_version in {POE1, POE2}
                and value.league
                and value.left_item_id != value.right_item_id
                and math.isfinite(value.price)
                and value.price > 0
            ):
                entries.append(value)
        return entries

    def _write_entries(self, entries: list[CachedRateValue]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": CACHE_SCHEMA,
            "entries": [asdict(entry) for entry in entries],
        }
        encoded = json.dumps(
            payload, ensure_ascii=False, indent=2, sort_keys=True,
        ).encode()
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent, delete=False,
            ) as temporary:
                temporary.write(encoded)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
