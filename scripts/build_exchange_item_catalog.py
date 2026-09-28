"""Build the runtime custom-rate catalog from verified official sources."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.poetore.official_exchange import normalize_name
from src.utils.poe_version_data import POE1, POE2

STATIC_URLS = {
    POE1: {
        "en": "https://www.pathofexile.com/api/trade/data/static",
        "ja": "https://jp.pathofexile.com/api/trade/data/static",
    },
    POE2: {
        "en": "https://www.pathofexile.com/api/trade2/data/static",
        "ja": "https://jp.pathofexile.com/api/trade2/data/static",
    },
}
GROUP_CATEGORIES = {
    POE1: {
        "Currency": "currency",
        "Fragments": "fragments",
        "Ducats": "allflame",
        "EnshroudingCrystals": "legion",
        "Keepers": "currency",
        "AllflameEmbers": "allflame",
        "Runegrafts": "runegrafts",
        "Ancestor": "ancestor",
        "Expedition": "expedition",
        "DeliriumOrbs": "delirium",
        "Catalysts": "catalysts",
        "Oils": "oils",
        "Delve": "delve",
        "Essences": "essences",
        "Cards": "cards",
    },
    POE2: {
        "Currency": "currency",
        "Fragments": "fragments",
        "Verisium": "expedition",
        "Runes": "runes",
        "Expedition": "expedition",
        "Vaal": "vaal",
        "Delirium": "delirium",
        "Breach": "breach",
        "Ritual": "ritual",
        "Abyss": "abyss",
        "Essences": "essences",
        "UncutGems": "uncut_gems",
        "LineageSupportGems": "gems",
    },
}
CATEGORIES = {
    POE1: (
        ("currency", "カレンシー"),
        ("essences", "エッセンス"),
        ("delve", "デルブ"),
        ("scarabs", "スカラベ"),
        ("cards", "占いカード"),
        ("delirium", "デリリウムオーブ"),
        ("legion", "リージョン"),
        ("fragments", "フラグメント"),
        ("oils", "オイル"),
        ("catalysts", "カタリスト"),
        ("omens", "お告げ"),
        ("tattoos", "タトゥー"),
        ("expedition", "エクスペディション"),
        ("harvest", "ハーベスト"),
        ("runegrafts", "ルーングラフト"),
        ("allflame", "オールフレイム"),
    ),
    POE2: (
        ("currency", "カレンシー"),
        ("essences", "エッセンス"),
        ("delirium", "デリリウム"),
        ("breach", "ブリーチ"),
        ("abyss", "アビス"),
        ("vaal", "アッツィリ神殿"),
        ("fragments", "フラグメント"),
        ("runes", "ルーン"),
        ("ritual", "リチュアル"),
        ("soul_cores", "ソウルコア"),
        ("idols", "アイドル"),
        ("uncut_gems", "ジェムの原石"),
        ("expedition", "エクスペディション"),
        ("gems", "ジェム"),
    ),
}

# The Trade static endpoint groups these by data origin, while the in-game
# Currency Exchange uses the categories below. Keep corrections keyed by the
# stable metadata ID so similarly named items are not moved accidentally.
POE1_CONFIRMED_CATEGORY_OVERRIDES = {
    "Metadata/Items/MapFragments/CurrencyFragmentPantheonFlask": "currency",
    "Metadata/Items/MapFragments/VoidbornVaultKey": "currency",
    "Metadata/Items/Currency/FearMemoryThread": "currency",
    "Metadata/Items/Currency/BenevolenceMemoryThread": "currency",
    "Metadata/Items/Currency/IgnoranceMemoryThread": "currency",
    "Metadata/Items/Currency/AstrolabeGeneric": "currency",
    "Metadata/Items/Currency/AstrolabeHarvest": "currency",
    "Metadata/Items/Currency/AstrolabeAbyss": "currency",
    "Metadata/Items/Currency/AstrolabeBreach": "currency",
    "Metadata/Items/Currency/AstrolabeRitual": "currency",
    "Metadata/Items/Currency/AstrolabeBlight": "currency",
    "Metadata/Items/Currency/AstrolabeUltimatum": "currency",
    "Metadata/Items/Currency/AstrolabeDelirium": "currency",
    "Metadata/Items/Currency/AstrolabeLegion": "currency",
    "Metadata/Items/Currency/AstrolabeExpedition": "currency",
    "Metadata/Items/MapFragments/CurrencyAfflictionFragment": "delirium",
    "Metadata/Items/Currency/CurrencyAfflictionShard": "delirium",
    "Metadata/Items/Currency/CurrencyDeepwater": "allflame",
}

POE2_CONFIRMED_CATEGORY_OVERRIDES = {
    "Metadata/Items/Currency/Abyss/AbyssPinnacleKey": "abyss",
    "Metadata/Items/Currency/Breach/BreachPinnacleKey": "breach",
    "Metadata/Items/Pinnacle/RitualPinnacleEffigyPiece": "fragments",
    "Metadata/Items/Currency/OmenOnAbyssRerollOptions": "abyss",
    "Metadata/Items/Currency/OmenOnAbyssGuarenteeLichTypeMod1": "abyss",
    "Metadata/Items/Currency/OmenOnAbyssGuarenteeLichTypeMod2": "abyss",
    "Metadata/Items/Currency/OmenOnAbyssGuarenteeLichTypeMod3": "abyss",
    "Metadata/Items/Currency/OmenOnAbyssVeilAllAndCorrupt": "abyss",
    "Metadata/Items/Currency/OmenOnAnnulRemoveAbyssMod": "abyss",
    "Metadata/Items/Currency/OmenOnAbyssAddPrefixes": "abyss",
    "Metadata/Items/Currency/OmenOnAbyssAddSuffixes": "abyss",
    "Metadata/Items/SoulCores/CarvedCunning": "idols",
    "Metadata/Items/SoulCores/CarvedMajesty": "idols",
    "Metadata/Items/SoulCores/CarvedMischief": "idols",
    "Metadata/Items/SoulCores/CarvedTenacity": "idols",
}

# This observed market ID is present in game and the official item-name data,
# but is still absent from the Trade static endpoint.
POE1_CONFIRMED_OBSERVED_ITEMS = {
    "Metadata/Items/Deepwater/DeepwaterBottledItem": {
        "en": "Message in a Bottle",
        "ja": "瓶の中の手紙",
        "category": "allflame",
        "item_order": 40_000,
        "icon_filename": "MessageInABottle.png",
    },
}

# These two observed market IDs are present in the official Trade2 item list
# and in game, but are still absent from the Trade2 static endpoint.  Their
# independently verified game icons are bundled until the endpoint exposes a
# verified CDN image.
POE2_CONFIRMED_OBSERVED_ITEMS = {
    "Metadata/Items/Currency/Expedition/ExpeditionPinnacleKeyShard": {
        "en": "Shattered Triskelion",
        "ja": "砕けたトリスケリオン",
        "category": "expedition",
        "item_order": 40_006,
        "icon_filename": "TriskelionShattered.png",
    },
    "Metadata/Items/Currency/Expedition/ExpeditionPinnacleKey": {
        "en": "The Triskelion Reforged",
        "ja": "再鍛造されたトリスケリオン",
        "category": "expedition",
        "item_order": 40_007,
        "icon_filename": "TriskelionReforged.png",
    },
}


def _fetch_json(url: str) -> tuple[dict, str]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "PoENavi/catalog-builder"}
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def observed_ids(folder: Path) -> set[str]:
    result: set[str] = set()
    for path in folder.glob("*.json.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as source:
            payload = json.load(source)
        for market in payload.get("markets", ()):
            result.update(str(value) for value in market.get("market_pair", ()))
    return result


def _card_names(path: Path) -> dict[str, str]:
    payload = _load_json(path)
    return {
        normalize_name(row["english"]): row["japanese"].strip()
        for row in payload.get("cards", ())
        if row.get("japanese", "").strip()
    }


def _category(poe_version: str, group: str, item_id: str, english: str) -> str:
    if poe_version == POE1 and item_id in POE1_CONFIRMED_CATEGORY_OVERRIDES:
        return POE1_CONFIRMED_CATEGORY_OVERRIDES[item_id]
    if poe_version == POE2 and item_id in POE2_CONFIRMED_CATEGORY_OVERRIDES:
        return POE2_CONFIRMED_CATEGORY_OVERRIDES[item_id]
    category = GROUP_CATEGORIES[poe_version][group]
    if poe_version == POE1:
        if group == "Currency" and "HarvestSeed" in item_id:
            return "harvest"
        if group == "Fragments" and "/Scarabs/" in item_id:
            return "scarabs"
        if group == "Fragments" and "Legion" in item_id:
            return "legion"
        if group == "Ancestor":
            return "omens" if english.startswith("Omen of ") else "tattoos"
    else:
        if group == "Vaal" and "/SoulCores/" in item_id:
            return "soul_cores"
        if group == "Ritual" and "/SoulCores/" in item_id:
            return "idols"
    return category


def _static_rows(
    en_payload: dict, ja_payload: dict
) -> list[tuple[str, int, dict, dict]]:
    ja_groups = {group["id"]: group for group in ja_payload.get("result", ())}
    rows = []
    for group_order, group in enumerate(en_payload.get("result", ())):
        ja_entries = {
            entry["id"]: entry
            for entry in ja_groups.get(group["id"], {}).get("entries", ())
        }
        for item_order, entry in enumerate(group.get("entries", ())):
            rows.append(
                (
                    group["id"],
                    group_order * 10_000 + item_order,
                    entry,
                    ja_entries.get(entry["id"], {}),
                )
            )
    return rows


def build_realm(
    poe_version: str,
    names: dict[str, str],
    en_payload: dict,
    ja_payload: dict,
    active_ids: set[str],
    card_names: dict[str, str],
) -> dict:
    ids_by_name: dict[str, list[str]] = defaultdict(list)
    for item_id, name in names.items():
        ids_by_name[normalize_name(name)].append(item_id)
    category_order = {
        key: index for index, (key, _) in enumerate(CATEGORIES[poe_version])
    }
    items: dict[str, dict] = {}
    unresolved: list[dict] = []
    for group, item_order, en, ja in _static_rows(en_payload, ja_payload):
        if group not in GROUP_CATEGORIES[poe_version]:
            continue
        english = str(en.get("text", "")).strip()
        if not english:
            continue
        candidates = ids_by_name.get(normalize_name(english), [])
        active = [item_id for item_id in candidates if item_id in active_ids]
        selected = active if len(active) == 1 else candidates
        if len(selected) != 1:
            unresolved.append({"group": group, "english": english, "ids": selected})
            continue
        item_id = selected[0]
        japanese = str(ja.get("text", "")).strip()
        if group == "Cards":
            japanese = japanese or card_names.get(normalize_name(english), "")
        if not japanese:
            unresolved.append({"group": group, "english": english, "ids": [item_id]})
            continue
        category = _category(poe_version, group, item_id, english)
        image = str(en.get("image", "")).strip()
        if group == "Cards":
            icon = {"kind": "divination_card"}
        elif image:
            icon = {"kind": "remote", "url": "https://web.poecdn.com" + image}
        else:
            icon = {"kind": "placeholder"}
        items[item_id] = {
            "id": item_id,
            "en": english,
            "ja": japanese,
            "category": category,
            "category_order": category_order[category],
            "item_order": item_order,
            "icon": icon,
        }
    # A newly released card can appear in Currency Exchange before the static
    # endpoint gains its entry.  The bundled, independently verified Japanese
    # card list is sufficient because all PoE 1 cards use one common icon here.
    if poe_version == POE1:
        next_card_order = 999_999
        for item_id in sorted(active_ids - set(items)):
            english = names.get(item_id, "").strip()
            japanese = card_names.get(normalize_name(english), "")
            if "/DivinationCards/" not in item_id or not japanese:
                continue
            items[item_id] = {
                "id": item_id,
                "en": english,
                "ja": japanese,
                "category": "cards",
                "category_order": category_order["cards"],
                "item_order": next_card_order,
                "icon": {"kind": "divination_card"},
            }
            next_card_order += 1
        for item_id, confirmed in POE1_CONFIRMED_OBSERVED_ITEMS.items():
            if item_id in items:
                continue
            if item_id not in active_ids:
                continue
            if normalize_name(names.get(item_id, "")) != normalize_name(
                confirmed["en"]
            ):
                continue
            category = confirmed["category"]
            items[item_id] = {
                "id": item_id,
                "en": confirmed["en"],
                "ja": confirmed["ja"],
                "category": category,
                "category_order": category_order[category],
                "item_order": confirmed["item_order"],
                "icon": {
                    "kind": "bundled",
                    "filename": confirmed["icon_filename"],
                },
            }
    elif poe_version == POE2:
        for item_id, confirmed in POE2_CONFIRMED_OBSERVED_ITEMS.items():
            if item_id in items:
                continue
            if item_id not in active_ids:
                continue
            if normalize_name(names.get(item_id, "")) != normalize_name(
                confirmed["en"]
            ):
                continue
            category = confirmed["category"]
            items[item_id] = {
                "id": item_id,
                "en": confirmed["en"],
                "ja": confirmed["ja"],
                "category": category,
                "category_order": category_order[category],
                "item_order": confirmed["item_order"],
                "icon": {
                    "kind": "bundled",
                    "filename": confirmed["icon_filename"],
                },
            }
    known = set(items)
    unmapped_observed = [
        {"id": item_id, "en": names.get(item_id, "")}
        for item_id in sorted(active_ids - known)
    ]
    return {
        "categories": [
            {"id": key, "label": label, "order": order}
            for order, (key, label) in enumerate(CATEGORIES[poe_version])
        ],
        "items": sorted(
            items.values(),
            key=lambda row: (
                row["category_order"],
                row["item_order"],
                row["ja"],
                row["id"],
            ),
        ),
        "unmapped_observed": unmapped_observed,
        "unresolved_static": unresolved,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poe1-names", type=Path, required=True)
    parser.add_argument("--poe2-names", type=Path, required=True)
    parser.add_argument("--poe1-observed", type=Path, required=True)
    parser.add_argument("--poe2-observed", type=Path, required=True)
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cards = _card_names(args.cards)
    realms = {}
    sources = {}
    for version, names_path, observed_path in (
        (POE1, args.poe1_names, args.poe1_observed),
        (POE2, args.poe2_names, args.poe2_observed),
    ):
        en, en_sha = _fetch_json(STATIC_URLS[version]["en"])
        ja, ja_sha = _fetch_json(STATIC_URLS[version]["ja"])
        realms[version] = build_realm(
            version,
            _load_json(names_path),
            en,
            ja,
            observed_ids(observed_path),
            cards,
        )
        sources[version] = {
            "en": {"url": STATIC_URLS[version]["en"], "sha256": en_sha},
            "ja": {"url": STATIC_URLS[version]["ja"], "sha256": ja_sha},
        }
    payload = {"schema_version": 1, "sources": sources, "realms": realms}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    for version in (POE1, POE2):
        realm = realms[version]
        print(
            version,
            "items",
            len(realm["items"]),
            "unmapped_observed",
            len(realm["unmapped_observed"]),
        )


if __name__ == "__main__":
    main()
