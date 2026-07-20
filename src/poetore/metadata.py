from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Iterable


INDEX_PATH = Path(__file__).resolve().parents[2] / "data" / "poetore" / "mod_metadata.json"


def normalize_stat_text(text: str) -> str:
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\([^)]*(?:\d|implicit|crafted|enchant|ローカル)[^)]*\)", "", text, flags=re.I)
    text = re.sub(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", "#", text)
    text = text.replace("+#", "#").replace("-#", "#")
    return re.sub(r"\s+", " ", text).strip().casefold()


@dataclass(frozen=True)
class TierRange:
    tier: int | None
    minimum: float
    maximum: float
    required_level: int | None = None
    generation: str | None = None
    mod_id: str | None = None


@dataclass(frozen=True)
class ModMetadata:
    ref: str
    stat_id: str
    kind: str
    japanese: tuple[str, ...]
    better: int = 1
    inverted: bool = False
    exact: bool = False
    local: bool = False
    tiers: tuple[TierRange, ...] = ()

    def search_bounds(self, value: float | None, roll_min: float | None = None,
                      roll_max: float | None = None, relaxation: float = 0.10
                      ) -> tuple[float | None, float | None]:
        if value is None:
            return None, None
        if self.exact or self.better == 0:
            return value, value
        if roll_min is not None and roll_max is not None:
            perfect = (self.better > 0 and value >= roll_max) or (self.better < 0 and value <= roll_min)
            if perfect:
                relaxation = 0.0
        span = abs(roll_max - roll_min) if roll_min is not None and roll_max is not None else abs(value)
        relaxed = round(span * relaxation, 1)
        if self.better < 0:
            return None, round(value + relaxed, 1)
        return round(value - relaxed, 1), None


class MetadataIndex:
    def __init__(self, records: Iterable[ModMetadata] = ()):
        self.records = tuple(records)
        self._by_match: dict[tuple[str, str], list[ModMetadata]] = {}
        for record in self.records:
            for matcher in record.japanese:
                self._by_match.setdefault((record.kind, normalize_stat_text(matcher)), []).append(record)

    def match(self, text: str, kind: str) -> tuple[ModMetadata | None, float]:
        key = ("explicit" if kind in {"prefix", "suffix"} else kind, normalize_stat_text(text))
        matches = self._by_match.get(key, ())
        if len(matches) == 1:
            return matches[0], 1.0
        if matches:
            return matches[0], 0.75
        return None, 0.0

    @classmethod
    def load(cls, path: Path = INDEX_PATH) -> "MetadataIndex":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = []
        for row in raw.get("mods", ()):
            tiers = tuple(TierRange(**tier) for tier in row.get("tiers", ()))
            records.append(ModMetadata(
                ref=row["ref"], stat_id=row["stat_id"], kind=row["kind"],
                japanese=tuple(row.get("japanese", ())), better=int(row.get("better", 1)),
                inverted=bool(row.get("inverted", False)), exact=bool(row.get("exact", False)),
                local=bool(row.get("local", False)), tiers=tiers,
            ))
        return cls(records)


_DEFAULT_INDEX: MetadataIndex | None = None


def default_metadata_index() -> MetadataIndex:
    global _DEFAULT_INDEX
    if _DEFAULT_INDEX is None:
        override = os.environ.get("POETORE_METADATA_PATH")
        _DEFAULT_INDEX = MetadataIndex.load(Path(override) if override else INDEX_PATH)
    return _DEFAULT_INDEX
