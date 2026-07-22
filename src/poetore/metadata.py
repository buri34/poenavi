from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import re
from typing import Iterable


INDEX_PATH = Path(__file__).resolve().parents[2] / "data" / "poetore" / "mod_metadata.json"
PSEUDO_RELATIONS_PATH = Path(__file__).resolve().parents[2] / "data" / "poetore" / "pseudo_relations.json"


@lru_cache(maxsize=4)
def _load_payload(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def base_armour_bounds(base_type: str, path: Path | None = None) -> dict[str, tuple[float, float]]:
    """固定済み派生データから防具ベースの可変防御値範囲を返す。"""
    path = (path or Path(os.environ.get("POETORE_METADATA_PATH", INDEX_PATH))).resolve()
    if not base_type or not path.exists():
        return {}
    row = _load_payload(str(path)).get("base_armour", {}).get(base_type.strip().casefold(), {})
    return {
        key: (float(bounds[0]), float(bounds[1]))
        for key, bounds in row.items()
        if key in {"ar", "ev", "es", "ward"}
        and isinstance(bounds, list) and len(bounds) == 2
    }


def gem_metadata(name: str, path: Path | None = None) -> dict:
    """固定済みAwakened itemsからGemの最大レベルとTrade識別情報を返す。"""
    path = (path or Path(os.environ.get("POETORE_METADATA_PATH", INDEX_PATH))).resolve()
    if not name or not path.exists():
        return {}
    return dict(_load_payload(str(path)).get("gems", {}).get(name.strip().casefold(), {}))


def pseudo_relations(path: Path | None = None) -> tuple[dict, ...]:
    """Awakened固定commitから機械抽出したpseudo間関係を返す。"""
    path = (path or PSEUDO_RELATIONS_PATH).resolve()
    if not path.exists():
        return ()
    return tuple(dict(row) for row in _load_payload(str(path)).get("relations", ()))


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
class OptionValue:
    value: int | str
    japanese: str
    english: str = ""
    oils: tuple[int, ...] = ()


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
    options: tuple[OptionValue, ...] = ()

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
        self._by_ref: dict[tuple[str, str], list[ModMetadata]] = {}
        self._by_match: dict[tuple[str, str], list[ModMetadata]] = {}
        for record in self.records:
            self._by_ref.setdefault((record.kind, record.ref.strip().casefold()), []).append(record)
            for matcher in record.japanese:
                self._by_match.setdefault((record.kind, normalize_stat_text(matcher)), []).append(record)
        self._by_option: dict[tuple[str, str], list[tuple[ModMetadata, OptionValue]]] = {}
        for record in self.records:
            for option in record.options:
                self._by_option.setdefault(
                    (record.kind, normalize_stat_text(option.japanese)), []
                ).append((record, option))

    def match(self, text: str, kind: str) -> tuple[ModMetadata | None, float]:
        record, _, confidence = self.match_with_option(text, kind)
        return record, confidence

    def match_ref(self, ref: str, kind: str) -> tuple[ModMetadata | None, float]:
        matches = self._by_ref.get((kind, ref.strip().casefold()), ())
        if len(matches) == 1:
            return matches[0], 1.0
        if matches:
            return matches[0], 0.75
        return None, 0.0

    def match_with_option(
        self, text: str, kind: str,
    ) -> tuple[ModMetadata | None, OptionValue | None, float]:
        key = ("explicit" if kind in {"prefix", "suffix"} else kind, normalize_stat_text(text))
        option_matches = self._by_option.get(key, ())
        if len(option_matches) == 1:
            return option_matches[0][0], option_matches[0][1], 1.0
        if option_matches:
            return option_matches[0][0], option_matches[0][1], 0.75
        matches = self._by_match.get(key, ())
        if len(matches) == 1:
            return matches[0], None, 1.0
        if matches:
            return matches[0], None, 0.75
        return None, None, 0.0

    @classmethod
    def load(cls, path: Path = INDEX_PATH) -> "MetadataIndex":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = []
        for row in raw.get("mods", ()):
            tiers = tuple(TierRange(**tier) for tier in row.get("tiers", ()))
            options = tuple(OptionValue(
                value=option["value"], japanese=str(option["japanese"]),
                english=str(option.get("english", "")),
                oils=tuple(int(value) for value in option.get("oils", ())),
            ) for option in row.get("options", ()))
            records.append(ModMetadata(
                ref=row["ref"], stat_id=row["stat_id"], kind=row["kind"],
                japanese=tuple(row.get("japanese", ())), better=int(row.get("better", 1)),
                inverted=bool(row.get("inverted", False)), exact=bool(row.get("exact", False)),
                local=bool(row.get("local", False)), tiers=tiers, options=options,
            ))
        return cls(records)


_DEFAULT_INDEX: MetadataIndex | None = None


def default_metadata_index() -> MetadataIndex:
    global _DEFAULT_INDEX
    if _DEFAULT_INDEX is None:
        override = os.environ.get("POETORE_METADATA_PATH")
        _DEFAULT_INDEX = MetadataIndex.load(Path(override) if override else INDEX_PATH)
    return _DEFAULT_INDEX
