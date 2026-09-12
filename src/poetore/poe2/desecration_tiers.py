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
TEMPLATE_NUMBER_RE = re.compile(rf"#|{NUMBER_RE}")
RESCUE_REASONS = {"fixed_number_rescue", "short_text_rescue"}


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


def _stat_identity(entry: dict) -> tuple[str, ...]:
    """Treat prefix/suffix records for the same displayed stat as one effect."""
    return tuple(sorted(str(part.get("stat_id", "")) for part in entry.get("parts", ())))


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
    return re.sub(r"[^#%+\-.0-9a-zぁ-んァ-ヶ一-龯ー]", "", text.casefold())


def _numeric_skeleton(
    template: str, observed: str, ranges: list,
    *, allow_fixed_mismatch: bool = False,
) -> tuple[str, str, int] | None:
    """Pair observed numbers with literal numbers or # slots in the template."""
    template = _visible_template(template)
    template_tokens = list(TEMPLATE_NUMBER_RE.finditer(template))
    observed_tokens = list(re.finditer(NUMBER_RE, observed))
    if len(template_tokens) != len(observed_tokens):
        return None
    if sum(token.group() == "#" for token in template_tokens) != len(ranges):
        return None

    expected_parts: list[str] = []
    actual_parts: list[str] = []
    expected_cursor = actual_cursor = range_index = fixed_mismatches = 0
    for expected_token, actual_token in zip(template_tokens, observed_tokens):
        expected_parts.append(template[expected_cursor:expected_token.start()])
        actual_parts.append(observed[actual_cursor:actual_token.start()])
        expected_raw = expected_token.group()
        actual_raw = actual_token.group()
        if expected_raw == "#":
            value = float(actual_raw)
            low, high = ranges[range_index]
            if not float(low) <= value <= float(high):
                return None
            range_index += 1
            expected_parts.append("#")
            # A leading + is part of the captured numeric value in OCR text,
            # while Trade templates commonly express the same slot as bare #.
            # Numeric range validation above already preserves sign semantics.
            actual_parts.append("#")
        else:
            expected_value = float(expected_raw)
            actual_value = float(actual_raw)
            if expected_value != actual_value:
                fixed_mismatches += 1
                if not allow_fixed_mismatch:
                    return None
            expected_parts.append(expected_raw)
            actual_parts.append(actual_raw)
        expected_cursor = expected_token.end()
        actual_cursor = actual_token.end()
    expected_parts.append(template[expected_cursor:])
    actual_parts.append(observed[actual_cursor:])
    return (
        _score_key("".join(expected_parts)),
        _score_key("".join(actual_parts)),
        fixed_mismatches,
    )


def _part_analysis(
    part: dict, observed: str, *, allow_fixed_mismatch: bool = False,
) -> tuple[float, int] | None:
    ranges = part.get("ranges")
    if ranges is None:
        return None
    skeleton = _numeric_skeleton(
        str(part["text"]["ja"]), observed, ranges,
        allow_fixed_mismatch=allow_fixed_mismatch,
    )
    if skeleton is None:
        return None
    expected, actual, fixed_mismatches = skeleton
    if not expected or not actual:
        return None
    return SequenceMatcher(None, expected, actual).ratio(), fixed_mismatches


def _part_score(part: dict, observed: str) -> float | None:
    analysis = _part_analysis(part, observed)
    return analysis[0] if analysis else None


def _entry_analysis(
    entry: dict, lines: tuple[str, ...], *, allow_fixed_mismatch: bool = False,
) -> tuple[float, int] | None:
    parts = entry.get("parts", ())
    if len(parts) != len(lines):
        return None
    best = None
    for ordered in permutations(lines):
        analyses = [
            _part_analysis(part, line, allow_fixed_mismatch=allow_fixed_mismatch)
            for part, line in zip(parts, ordered)
        ]
        if any(analysis is None for analysis in analyses):
            continue
        score = sum(analysis[0] for analysis in analyses) / len(analyses)
        mismatch_count = sum(analysis[1] for analysis in analyses)
        candidate = (score, mismatch_count)
        best = candidate if best is None or candidate[0] > best[0] else best
    return best


def _entry_score(entry: dict, lines: tuple[str, ...]) -> float | None:
    analysis = _entry_analysis(entry, lines)
    return analysis[0] if analysis else None


def _fixed_number_rescue_score(entry: dict, lines: tuple[str, ...]) -> float | None:
    parts = entry.get("parts", ())
    if len(parts) != len(lines):
        return None
    best = None
    for ordered in permutations(lines):
        scores = []
        mismatch_count = 0
        for part, line in zip(parts, ordered):
            ranges = part.get("ranges")
            if ranges is None:
                break
            skeleton = _numeric_skeleton(
                str(part["text"]["ja"]), line, ranges,
                allow_fixed_mismatch=True,
            )
            if skeleton is None:
                break
            expected, actual, mismatches = skeleton
            # Rescue only a numeric OCR error. Any nonnumeric difference must
            # use the separate short-text path or remain unresolved.
            if re.sub(NUMBER_RE, "#", expected) != re.sub(NUMBER_RE, "#", actual):
                break
            scores.append(SequenceMatcher(None, expected, actual).ratio())
            mismatch_count += mismatches
        else:
            if mismatch_count:
                combined = sum(scores) / len(scores)
                best = combined if best is None else max(best, combined)
    return best


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, 1):
        current = [left_index]
        for right_index, right_char in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def _short_text_score(entry: dict, lines: tuple[str, ...]) -> float | None:
    parts = entry.get("parts", ())
    if len(parts) != 1 or len(lines) != 1:
        return None
    ranges = parts[0].get("ranges")
    if ranges is None:
        return None
    skeleton = _numeric_skeleton(str(parts[0]["text"]["ja"]), lines[0], ranges)
    if skeleton is None:
        return None
    expected, actual, _mismatches = skeleton
    if len(expected) > 12 or _edit_distance(expected, actual) != 1:
        return None
    return 1 - (1 / max(len(expected), len(actual), 1))


def _normalized_lines(lines: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    source = lines.splitlines() if isinstance(lines, str) else lines
    return tuple(str(line).strip() for line in source if str(line).strip())


def _profile_category(profile: dict) -> str:
    """Return the concrete PoE2 equipment category represented by a profile."""
    category = str(profile["category"])
    if category == "staff" and "warstaff" in profile.get("tags", ()):
        return "quarterstaff"
    return category


def available_categories() -> tuple[str, ...]:
    return tuple(sorted({_profile_category(profile) for profile in tier_data()["profiles"]}))


def resolve_desecration_choice(
    lines: str | tuple[str, ...] | list[str], category: str,
) -> TierResolution:
    """Resolve one Reveal choice; ambiguous results are never guessed."""
    normalized_lines = _normalized_lines(lines)
    payload = tier_data()
    profile_ids = {
        profile["id"] for profile in payload["profiles"]
        if _profile_category(profile) == category
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
        if _profile_category(profile) == category
    }
    def candidates_for(mode: str) -> list[tuple[float, dict, str, int]]:
        rows: list[tuple[float, dict, str, int]] = []
        for entry in payload["entries"]:
            if mode == "matched":
                score = _entry_score(entry, normalized_lines)
                if score is None or score < minimum_score:
                    continue
            elif mode == "fixed_number_rescue":
                score = _fixed_number_rescue_score(entry, normalized_lines)
                if score is None:
                    continue
            else:
                score = _short_text_score(entry, normalized_lines)
                if score is None:
                    continue
            for profile_id, tier in entry["profile_tiers"].items():
                if profile_id in profile_ids:
                    rows.append((score, entry, profile_id, int(tier)))
        return rows

    reason = "matched"
    candidates = candidates_for(reason)
    if not candidates:
        reason = "fixed_number_rescue"
        candidates = candidates_for(reason)
    if not candidates:
        reason = "short_text_rescue"
        candidates = candidates_for(reason)
    if not candidates:
        return FuzzyTierResolution(tier=None, reason="no_match", score=None)
    best_score = max(row[0] for row in candidates)
    finalists = [row for row in candidates if best_score - row[0] <= ambiguity_margin]
    tiers = {row[3] for row in finalists}
    mod_ids = tuple(sorted({row[1]["mod_id"] for row in finalists}))
    stat_identities = {_stat_identity(row[1]) for row in finalists}
    profiles = tuple(sorted({row[2] for row in finalists}))
    if len(tiers) != 1 or len(stat_identities) != 1:
        return FuzzyTierResolution(
            tier=None, mod_ids=mod_ids, profile_ids=profiles,
            reason="ambiguous", score=round(best_score, 4),
        )
    return FuzzyTierResolution(
        tier=next(iter(tiers)), mod_ids=mod_ids, profile_ids=profiles,
        range_labels=_shared_range_labels(
            (row[1] for row in finalists), normalized_lines,
        ),
        reason=reason, score=round(best_score, 4),
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
