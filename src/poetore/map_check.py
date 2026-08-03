from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from .models import ParsedItem


CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "poetore" / "map_mods.json"
DECISIONS = {"-", "d", "w", "g", "s"}
DEFAULT_DECISIONS_BY_REF = {
    "Players have #% to all maximum Resistances": "w--",
    "Monsters reflect #% of Physical Damage": "d--",
    "Monsters reflect #% of Elemental Damage": "d--",
    "Area contains two Unique Bosses": "g--",
}
MAP_CHECK_CATEGORIES = {
    "map", "invitation", "heist_contract", "heist_blueprint", "expedition_logbook",
}


@dataclass(frozen=True)
class MapModEntry:
    key: str
    ref: str
    japanese: str
    scope: str
    stat_ids: tuple[str, ...]


@lru_cache(maxsize=4)
def load_map_mod_catalog(path: Path = CATALOG_PATH) -> tuple[MapModEntry, ...]:
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(MapModEntry(
        key=str(row["key"]), ref=str(row["ref"]),
        japanese=str(row["japanese"]), scope=str(row["scope"]),
        stat_ids=tuple(str(value) for value in row.get("stat_ids", ())),
    ) for row in payload.get("entries", ()))


def default_map_check_config(catalog: tuple[MapModEntry, ...] | None = None) -> dict:
    catalog = catalog or load_map_mod_catalog()
    decisions = {
        entry.key: DEFAULT_DECISIONS_BY_REF[entry.ref]
        for entry in catalog if entry.ref in DEFAULT_DECISIONS_BY_REF
    }
    known_refs = {entry.ref for entry in catalog}
    decisions.update({
        f"legacy:{ref}": decision
        for ref, decision in DEFAULT_DECISIONS_BY_REF.items()
        if ref not in known_refs
    })
    return {"profile": 1, "show_new_stats": False, "decisions": decisions}


def normalized_map_check_config(config: dict | None) -> dict:
    defaults = default_map_check_config()
    source = config if isinstance(config, dict) else {}
    try:
        profile = int(source.get("profile", 1))
    except (TypeError, ValueError):
        profile = 1
    decisions = dict(defaults["decisions"])
    for key, value in (source.get("decisions") or {}).items():
        value = str(value)
        if len(value) == 3 and all(char in DECISIONS for char in value):
            decisions[str(key)] = value
    return {
        "profile": profile if profile in {1, 2, 3} else 1,
        "show_new_stats": bool(source.get("show_new_stats", False)),
        "decisions": decisions,
    }


def decision_for(config: dict, key: str, profile: int | None = None) -> str:
    profile = profile or int(config.get("profile", 1))
    return str((config.get("decisions") or {}).get(key, "---"))[profile - 1]


def set_decision(config: dict, key: str, value: str, profile: int | None = None) -> None:
    if value not in DECISIONS:
        raise ValueError(value)
    profile = profile or int(config.get("profile", 1))
    decisions = config.setdefault("decisions", {})
    current = list(str(decisions.get(key, "---")))
    current[profile - 1] = value
    updated = "".join(current)
    if updated == "---":
        decisions.pop(key, None)
    else:
        decisions[key] = updated


def next_color_decision(value: str) -> str:
    return {"-": "d", "d": "w", "w": "g", "g": "-", "s": "d"}.get(value, "d")


def is_map_check_item(item: ParsedItem) -> bool:
    if item.category not in MAP_CHECK_CATEGORIES:
        return False
    if item.category == "map" and item.rarity.casefold() in {"unique", "ユニーク"}:
        return False
    return True


def entries_by_stat_id(
    catalog: tuple[MapModEntry, ...] | None = None,
) -> dict[str, MapModEntry]:
    return {
        stat_id: entry
        for entry in (catalog or load_map_mod_catalog())
        for stat_id in entry.stat_ids
    }
