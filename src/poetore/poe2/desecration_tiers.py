"""Pure matching logic for PoE2 Desecration Reveal modifier tiers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from itertools import permutations
from pathlib import Path

DATA_PATH = (
    Path(__file__).resolve().parents[3]
    / "data" / "poetore" / "poe2" / "desecration_tiers.json"
)
NUMBER_RE = r"[+-]?\d+(?:\.\d+)?"


@dataclass(frozen=True)
class TierResolution:
    tier: int | None
    mod_ids: tuple[str, ...] = ()
    profile_ids: tuple[str, ...] = ()
    range_labels: tuple[str, ...] = ()
    reason: str = "unknown"


@dataclass(frozen=True)
class FuzzyTierResolution(TierResolution):
    score: float | None = None


@dataclass(frozen=True)
class RevealResolution:
    categories: tuple[str, ...]
    tiers_by_category: dict[str, tuple[int | None, ...]]
    observed_texts: tuple[str, ...]

    @property
    def needs_category_choice(self) -> bool:
        return len(set(self.tiers_by_category.values())) > 1

    @property
    def tiers(self) -> tuple[int | None, ...] | None:
        unique = set(self.tiers_by_category.values())
        return next(iter(unique)) if len(unique) == 1 else None


@lru_cache(maxsize=1)
def tier_data() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _visible_template(template: str) -> str:
    return re.sub(r"\s*\((?:Local|ローカル)\)\s*$", "", template, flags=re.IGNORECASE)


def _display_number(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _entry_range_labels(
    entry: dict, observed_lines: tuple[str, ...] = (),
) -> tuple[str, ...]:
    labels: list[str] = []
    parts = tuple(entry.get("parts", ()))
    if observed_lines and len(parts) == len(observed_lines):
        ranked = []
        for ordered in permutations(parts):
            scores = [_part_score(part, line) for part, line in zip(ordered, observed_lines)]
            if all(score is not None for score in scores):
                ranked.append((sum(scores), ordered))
        if ranked:
            parts = max(ranked, key=lambda item: item[0])[1]
    for part in parts:
        ranges = part.get("ranges")
        if ranges is None:
            return ()
        template = _visible_template(str(part["text"]["ja"]))
        suffixes = [
            "%" if tail.lstrip().startswith("%") else ""
            for tail in template.split("#")[1:]
        ]
        if len(suffixes) != len(ranges):
            return ()
        for (low, high), suffix in zip(ranges, suffixes):
            low_text = _display_number(low)
            high_text = _display_number(high)
            value = low_text if low_text == high_text else f"{low_text}–{high_text}"
            labels.append(f"{value}{suffix}")
    return tuple(labels)


def _shared_range_labels(
    entries, observed_lines: tuple[str, ...] = (),
) -> tuple[str, ...]:
    unique = {entry["mod_id"]: entry for entry in entries}
    labels = {
        _entry_range_labels(entry, observed_lines) for entry in unique.values()
    }
    return next(iter(labels)) if len(labels) == 1 else ()


@lru_cache(maxsize=4096)
def _line_pattern(template: str) -> re.Pattern:
    template = _visible_template(template).strip()
    pieces = re.split(r"(\#)", template)
    pattern = ""
    for piece in pieces:
        if piece == "#":
            pattern += f"({NUMBER_RE})"
        else:
            escaped = re.escape(piece)
            escaped = escaped.replace(r"\ ", r"\s*")
            pattern += escaped
    return re.compile(rf"^{pattern}$", re.IGNORECASE)


def _match_part(part: dict, line: str) -> bool:
    ranges = part.get("ranges")
    if ranges is None:
        return False
    match = _line_pattern(str(part["text"]["ja"])).fullmatch(line.strip())
    if not match or len(match.groups()) != len(ranges):
        return False
    values = [float(value) for value in match.groups()]
    return all(float(low) <= value <= float(high) for value, (low, high) in zip(values, ranges))


def _entry_matches(entry: dict, lines: tuple[str, ...]) -> bool:
    parts = entry.get("parts", ())
    if len(parts) != len(lines):
        return False
    used: set[int] = set()

    def assign(part_index: int) -> bool:
        if part_index == len(parts):
            return True
        for line_index, line in enumerate(lines):
            if line_index in used or not _match_part(parts[part_index], line):
                continue
            used.add(line_index)
            if assign(part_index + 1):
                return True
            used.remove(line_index)
        return False

    return assign(0)


def _score_key(text: str) -> str:
    text = _visible_template(text)
    text = re.sub(NUMBER_RE, "#", text.casefold())
    return re.sub(r"[^#a-zぁ-んァ-ヶ一-龯ー]", "", text)


def _part_score(part: dict, observed: str) -> float | None:
    ranges = part.get("ranges")
    if ranges is None:
        return None
    values = [float(value) for value in re.findall(NUMBER_RE, observed)]
    if len(values) != len(ranges):
        return None
    if not all(
        float(low) <= value <= float(high)
        for value, (low, high) in zip(values, ranges)
    ):
        return None
    expected = _score_key(str(part["text"]["ja"]))
    actual = _score_key(observed)
    if not expected or not actual:
        return None
    return SequenceMatcher(None, expected, actual).ratio()


def _entry_score(entry: dict, lines: tuple[str, ...]) -> float | None:
    parts = entry.get("parts", ())
    if len(parts) != len(lines):
        return None
    best = None
    for ordered in permutations(lines):
        scores = [_part_score(part, line) for part, line in zip(parts, ordered)]
        if any(score is None for score in scores):
            continue
        combined = sum(scores) / len(scores)
        best = combined if best is None else max(best, combined)
    return best


def _normalized_lines(lines: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    source = lines.splitlines() if isinstance(lines, str) else lines
    return tuple(str(line).strip() for line in source if str(line).strip())


def available_categories() -> tuple[str, ...]:
    return tuple(sorted({profile["category"] for profile in tier_data()["profiles"]}))


def resolve_desecration_choice(
    lines: str | tuple[str, ...] | list[str], category: str,
) -> TierResolution:
    """Resolve one Reveal choice; ambiguous results are never guessed."""
    normalized_lines = _normalized_lines(lines)
    payload = tier_data()
    profile_ids = {
        profile["id"] for profile in payload["profiles"]
        if profile["category"] == category
    }
    matches: list[tuple[dict, str, int]] = []
    for entry in payload["entries"]:
        if not _entry_matches(entry, normalized_lines):
            continue
        for profile_id, tier in entry["profile_tiers"].items():
            if profile_id in profile_ids:
                matches.append((entry, profile_id, int(tier)))
    if not matches:
        return TierResolution(tier=None, reason="no_match")
    tiers = {tier for _entry, _profile, tier in matches}
    mod_ids = tuple(sorted({entry["mod_id"] for entry, _profile, _tier in matches}))
    matched_profiles = tuple(sorted({profile for _entry, profile, _tier in matches}))
    if len(tiers) != 1:
        return TierResolution(
            tier=None, mod_ids=mod_ids, profile_ids=matched_profiles,
            reason="category_dependent",
        )
    return TierResolution(
        tier=next(iter(tiers)), mod_ids=mod_ids,
        profile_ids=matched_profiles,
        range_labels=_shared_range_labels(
            (entry for entry, _profile, _tier in matches), normalized_lines,
        ),
        reason="matched",
    )


def resolve_desecration_choice_fuzzy(
    lines: str | tuple[str, ...] | list[str], category: str,
    *, minimum_score: float = 0.78, ambiguity_margin: float = 0.035,
) -> FuzzyTierResolution:
    """Resolve OCR text while keeping numeric values strict and never guessing."""
    normalized_lines = _normalized_lines(lines)
    payload = tier_data()
    profile_ids = {
        profile["id"] for profile in payload["profiles"]
        if profile["category"] == category
    }
    candidates: list[tuple[float, dict, str, int]] = []
    for entry in payload["entries"]:
        score = _entry_score(entry, normalized_lines)
        if score is None or score < minimum_score:
            continue
        for profile_id, tier in entry["profile_tiers"].items():
            if profile_id in profile_ids:
                candidates.append((score, entry, profile_id, int(tier)))
    if not candidates:
        return FuzzyTierResolution(tier=None, reason="no_match", score=None)
    best_score = max(row[0] for row in candidates)
    finalists = [row for row in candidates if best_score - row[0] <= ambiguity_margin]
    tiers = {row[3] for row in finalists}
    mod_ids = tuple(sorted({row[1]["mod_id"] for row in finalists}))
    profiles = tuple(sorted({row[2] for row in finalists}))
    if len(tiers) != 1:
        return FuzzyTierResolution(
            tier=None, mod_ids=mod_ids, profile_ids=profiles,
            reason="ambiguous", score=round(best_score, 4),
        )
    return FuzzyTierResolution(
        tier=next(iter(tiers)), mod_ids=mod_ids, profile_ids=profiles,
        range_labels=_shared_range_labels(
            (row[1] for row in finalists), normalized_lines,
        ),
        reason="matched", score=round(best_score, 4),
    )


def resolve_desecration_reveal(
    observed_texts: tuple[str, ...] | list[str],
    categories: tuple[str, ...] | list[str] | None = None,
) -> RevealResolution:
    """Find categories that can explain all three choices and their tier tuples."""
    texts = tuple(str(text).strip() for text in observed_texts)
    candidates = tuple(categories) if categories is not None else available_categories()
    tiers_by_category: dict[str, tuple[int | None, ...]] = {}
    for category in candidates:
        resolutions = tuple(resolve_desecration_choice_fuzzy(text, category) for text in texts)
        if all(result.tier is not None for result in resolutions):
            tiers_by_category[category] = tuple(result.tier for result in resolutions)
    return RevealResolution(
        categories=tuple(tiers_by_category), tiers_by_category=tiers_by_category,
        observed_texts=texts,
    )
