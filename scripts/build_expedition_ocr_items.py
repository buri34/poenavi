"""Build the packaged Japanese/English item alias list used by Expedition OCR."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_GROUPS = ("currency", "gem", "map")
EXPEDITION_REWARD_TYPES = (
    "Currency",
    "Expedition",
    "UncutGems",
    "Runes",
    "Verisium",
)
POE2_EXCHANGE_OVERVIEW_URL = (
    "https://poe.ninja/poe2/api/economy/exchange/current/overview"
)


def build_aliases(
    japanese: dict,
    english: dict,
    reward_names: set[str],
) -> list[dict[str, str]]:
    """Pair aligned official Trade item snapshots, dropping ambiguous aliases."""
    en_groups = {group.get("id"): group for group in english.get("result", ())}
    candidates: dict[str, set[str]] = {}
    for ja_group in japanese.get("result", ()):
        group_id = ja_group.get("id")
        if group_id not in DEFAULT_GROUPS or group_id not in en_groups:
            continue
        ja_entries = ja_group.get("entries", ())
        en_entries = en_groups[group_id].get("entries", ())
        if len(ja_entries) != len(en_entries):
            raise ValueError(f"Trade item group is not aligned: {group_id}")
        for ja_entry, en_entry in zip(ja_entries, en_entries, strict=True):
            for field in ("name", "type"):
                ja_name = str(ja_entry.get(field, "")).strip()
                en_name = str(en_entry.get(field, "")).strip()
                if (
                    ja_name
                    and en_name
                    and en_name in reward_names
                    and not ja_name.startswith("[DNT]")
                    and not en_name.startswith("[DNT]")
                ):
                    candidates.setdefault(ja_name, set()).add(en_name)
    return [
        {"ja": ja_name, "en": next(iter(en_names))}
        for ja_name, en_names in sorted(candidates.items())
        if len(en_names) == 1
    ]


def fetch_reward_names(league: str) -> set[str]:
    names: set[str] = set()
    for type_name in EXPEDITION_REWARD_TYPES:
        url = (
            f"{POE2_EXCHANGE_OVERVIEW_URL}?league={quote(league, safe='')}"
            f"&type={quote(type_name, safe='')}"
        )
        request = Request(url, headers={"User-Agent": "PoENavi/poetore"})
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        category_names = {
            str(item.get("name", "")).strip()
            for item in payload.get("items", ())
            if str(item.get("name", "")).strip()
        }
        if not category_names:
            raise ValueError(f"Empty poe.ninja reward category: {type_name}")
        names.update(category_names)
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ja", type=Path, required=True)
    parser.add_argument("--en", type=Path, required=True)
    parser.add_argument("--league", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    japanese = json.loads(args.ja.read_text(encoding="utf-8"))
    english = json.loads(args.en.read_text(encoding="utf-8"))
    reward_names = fetch_reward_names(args.league)
    aliases = build_aliases(japanese, english, reward_names)
    mapped_names = {row["en"] for row in aliases}
    missing_names = sorted(reward_names - mapped_names)
    if missing_names:
        raise ValueError(
            "Trade item snapshots do not contain reward names: "
            + ", ".join(missing_names)
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "source": "poe.ninja PoE2 Currency Exchange categories",
                "league": args.league,
                "categories": list(EXPEDITION_REWARD_TYPES),
                "items": aliases,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
