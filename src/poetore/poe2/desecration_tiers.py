"""Pure matching logic for PoE2 Desecration Reveal modifier tiers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
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
    reason: str = "unknown"


@lru_cache(maxsize=1)
def tier_data() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _visible_template(template: str) -> str:
    return re.sub(r"\s*\((?:Local|ローカル)\)\s*$", "", template, flags=re.IGNORECASE)


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


def resolve_desecration_choice(
    lines: str | tuple[str, ...] | list[str], category: str,
) -> TierResolution:
    """Resolve one Reveal choice; ambiguous results are never guessed."""
    if isinstance(lines, str):
        normalized_lines = tuple(line.strip() for line in lines.splitlines() if line.strip())
    else:
        normalized_lines = tuple(str(line).strip() for line in lines if str(line).strip())
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
        profile_ids=matched_profiles, reason="matched",
    )
