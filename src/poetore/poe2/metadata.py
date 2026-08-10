from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re


IDENTITY_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "poetore" / "poe2" / "identity_index.json"
)
STAT_PATH = IDENTITY_PATH.with_name("stat_index.json")
AUGMENT_PATH = IDENTITY_PATH.with_name("augment_index.json")


@lru_cache(maxsize=1)
def identity_index() -> dict[str, tuple[dict, ...]]:
    payload = identity_entries()
    index = {}
    for entry in payload:
        for name in entry.get("names", {}).values():
            index.setdefault(str(name).casefold(), []).append(entry)
    return {key: tuple(value) for key, value in index.items()}


@lru_cache(maxsize=1)
def identity_entries() -> tuple[dict, ...]:
    payload = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    return tuple(payload.get("entries", ()))


def resolve_identity_candidates(
    name: str, namespace: str | None = None,
) -> tuple[dict, ...]:
    candidates = identity_index().get(name.strip().casefold(), ())
    if namespace is None:
        return candidates
    return tuple(row for row in candidates if row.get("namespace") == namespace)


def resolve_identity(name: str, namespace: str | None = None) -> dict | None:
    candidates = resolve_identity_candidates(name, namespace)
    return candidates[0] if candidates else None


@lru_cache(maxsize=1)
def augment_entries() -> tuple[dict, ...]:
    payload = json.loads(AUGMENT_PATH.read_text(encoding="utf-8"))
    return tuple(payload.get("entries", ()))


@lru_cache(maxsize=256)
def resolve_identity_fragments(name: str, namespace: str = "ITEM") -> tuple[dict, ...]:
    """Return identities contained in an affixed display name, longest first.

    PoE2 Magic items combine prefix/base/suffix into one header line.  EE2
    resolves that line by testing every contiguous name fragment against its
    item database.  Our compact identity index already contains every
    localized base name, so scanning those names is equivalent and also works
    for Japanese text where word boundaries are not reliable.
    """
    comparable = name.strip().casefold()
    matches: list[tuple[int, dict]] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in identity_entries():
        if entry.get("namespace") != namespace:
            continue
        matched_length = max(
            (
                len(str(localized))
                for localized in (entry.get("names") or {}).values()
                if str(localized).strip().casefold() in comparable
            ),
            default=0,
        )
        if not matched_length:
            continue
        key = (
            str(entry.get("namespace", "")),
            str(entry.get("ref_name", "")),
            str(entry.get("category", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        matches.append((matched_length, entry))
    matches.sort(key=lambda row: row[0], reverse=True)
    return tuple(entry for _length, entry in matches)


def _template_pattern(template: str) -> re.Pattern:
    escaped = re.escape(template)
    escaped = escaped.replace(r"\#", r"\+?(-?\d+(?:\.\d+)?)")
    # A template that explicitly contains +# still requires the plus sign;
    # templates containing only # accept the positive-sign form used by JP copy text.
    escaped = escaped.replace(r"\+\+?(", r"\+(")
    return re.compile(rf"^{escaped}$", re.IGNORECASE)


@lru_cache(maxsize=1)
def stat_matchers() -> tuple[tuple[dict, re.Pattern], ...]:
    payload = json.loads(STAT_PATH.read_text(encoding="utf-8"))
    rows = []
    for entry in payload.get("entries", ()):
        if entry.get("type") == "pseudo":
            continue
        for text in (entry.get("text") or {}).values():
            if text:
                rows.append((entry, _template_pattern(str(text))))
    return tuple(rows)


@lru_cache(maxsize=1)
def stat_ids() -> frozenset[str]:
    payload = json.loads(STAT_PATH.read_text(encoding="utf-8"))
    return frozenset(str(entry.get("id", "")) for entry in payload.get("entries", ()))


def explicit_variant_id(stat_id: str | None) -> str | None:
    """Return the Trade2 explicit counterpart used by EE2's finished preset."""
    if not stat_id or "." not in stat_id:
        return None
    prefix, suffix = stat_id.split(".", 1)
    if prefix not in {"crafted", "fractured", "desecrated"}:
        return None
    candidate = f"explicit.{suffix}"
    return candidate if candidate in stat_ids() else None


@lru_cache(maxsize=1)
def local_stat_matchers() -> tuple[tuple[dict, re.Pattern], ...]:
    rows = []
    for entry, _pattern in stat_matchers():
        for template in (entry.get("text") or {}).values():
            template = str(template)
            local_template = re.sub(
                r"\s*\((?:Local|ローカル)\)\s*$", "", template,
                flags=re.IGNORECASE,
            )
            if local_template != template:
                rows.append((entry, _template_pattern(local_template)))
    return tuple(rows)


def resolve_stat_line(
    text: str, preferred_type: str | None = None, *, prefer_local: bool = False,
) -> tuple[dict, tuple[float, ...]] | None:
    candidates = resolve_stat_line_candidates(
        text, preferred_type, include_local_variants=prefer_local,
    )
    return candidates[0] if candidates else None


def resolve_stat_line_candidates(
    text: str,
    preferred_type: str | None = None,
    *,
    include_local_variants: bool = False,
) -> tuple[tuple[dict, tuple[float, ...]], ...]:
    comparable = re.sub(
        r"\s*\((?:implicit|explicit|enchant|rune|sanctified|desecrated|fractured|crafted)[^)]*\)\s*$",
        "", text.strip(), flags=re.IGNORECASE,
    )
    comparable = re.sub(r"\((?:[^()]*)-[^()]*\)", "", comparable)
    comparable = re.sub(r"\s*[—-]\s*スケールできない値\s*$", "", comparable)
    comparable = re.sub(r"\s*[—-]\s*Unscalable Value\s*$", "", comparable, flags=re.IGNORECASE)
    matchers = stat_matchers()
    if preferred_type:
        matchers = tuple(
            row for row in matchers if row[0].get("type") == preferred_type
        ) + tuple(
            row for row in matchers if row[0].get("type") != preferred_type
        )
    candidate_matchers = []
    if include_local_variants:
        local_matchers = local_stat_matchers()
        if preferred_type:
            local_matchers = tuple(
                row for row in local_matchers if row[0].get("type") == preferred_type
            ) + tuple(
                row for row in local_matchers if row[0].get("type") != preferred_type
            )
        candidate_matchers.extend(local_matchers)
    candidate_matchers.extend(matchers)
    def collect(candidate: str, value_multiplier: float = 1.0):
        matches = []
        seen_ids = set()
        for entry, pattern in candidate_matchers:
            match = pattern.fullmatch(candidate)
            entry_id = str(entry.get("id", ""))
            if match and entry_id not in seen_ids:
                seen_ids.add(entry_id)
                matches.append((
                    entry,
                    tuple(float(value) * value_multiplier for value in match.groups()),
                ))
        return matches

    resolved = collect(comparable)
    if not resolved:
        # EE2 stores these Trade stats in their `increased` direction and
        # registers reduced copy text as a negated matcher.  Our compact index
        # keeps only the canonical template, so reproduce that rule here.
        inverted = re.sub(r"\breduced\b", "increased", comparable, flags=re.IGNORECASE)
        inverted = inverted.replace("減少する", "増加する")
        if inverted != comparable:
            resolved = collect(inverted, -1.0)
    if not resolved:
        return ()
    if preferred_type and any(row[0].get("type") == preferred_type for row in resolved):
        resolved = [row for row in resolved if row[0].get("type") == preferred_type]
    else:
        first_type = resolved[0][0].get("type")
        resolved = [row for row in resolved if row[0].get("type") == first_type]
    return tuple(resolved)
