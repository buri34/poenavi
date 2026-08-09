from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re


IDENTITY_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "poetore" / "poe2" / "identity_index.json"
)
STAT_PATH = IDENTITY_PATH.with_name("stat_index.json")


@lru_cache(maxsize=1)
def identity_index() -> dict[str, tuple[dict, ...]]:
    payload = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    index = {}
    for entry in payload.get("entries", ()):
        for name in entry.get("names", {}).values():
            index.setdefault(str(name).casefold(), []).append(entry)
    return {key: tuple(value) for key, value in index.items()}


def resolve_identity(name: str, namespace: str | None = None) -> dict | None:
    candidates = identity_index().get(name.strip().casefold(), ())
    if namespace is None:
        return candidates[0] if candidates else None
    return next((row for row in candidates if row.get("namespace") == namespace), None)


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
    resolved = []
    seen_ids = set()
    for entry, pattern in candidate_matchers:
        match = pattern.fullmatch(comparable)
        entry_id = str(entry.get("id", ""))
        if match and entry_id not in seen_ids:
            seen_ids.add(entry_id)
            resolved.append((entry, tuple(float(value) for value in match.groups())))
    if not resolved:
        return ()
    if preferred_type and any(row[0].get("type") == preferred_type for row in resolved):
        resolved = [row for row in resolved if row[0].get("type") == preferred_type]
    else:
        first_type = resolved[0][0].get("type")
        resolved = [row for row in resolved if row[0].get("type") == first_type]
    return tuple(resolved)
