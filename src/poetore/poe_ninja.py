from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import ParsedItem


API_URL = "https://poe.ninja/poe1/api/economy/current/dense/overviews"
STASH_OVERVIEW_URL = "https://poe.ninja/poe1/api/economy/stash/current/item/overview"
CACHE_TTL_SECONDS = 31 * 60

_UNIQUE_TYPES = {
    "UniqueJewel", "ForbiddenJewel", "UniqueFlask", "UniqueWeapon", "UniqueArmour",
    "UniqueAccessory", "UniqueMap", "UniqueRelic", "UniqueIdol", "UniqueTincture",
}
_EXACT_TYPES_BY_CATEGORY = {
    "currency": {"Currency", "Fragment", "Essence", "Fossil", "Resonator", "Scarab", "Oil",
                 "DeliriumOrb", "Artifact", "Tattoo", "Omen", "Vial", "Incubator", "Runegraft",
                 "DjinnCoin", "Astrolabe", "AllflameEmber"},
    "divination_card": {"DivinationCard"},
    "captured_beast": {"Beast"},
    "invitation": {"Invitation"},
    "incursion_item": {"IncursionTemple"},
}
_MAP_TYPES = {"Map", "BlightedMap", "BlightRavagedMap", "ValdoMap"}


@dataclass(frozen=True)
class PoeNinjaPrice:
    name: str
    variant: str | None
    chaos: float
    graph: tuple[float | None, ...]
    url: str
    divine_chaos: float | None = None
    total_change: float | None = None
    source_type: str | None = None

    def display_price(self) -> str:
        if self.divine_chaos and self.chaos >= self.divine_chaos * 0.94:
            value = self.chaos / self.divine_chaos
            return f"{_display_number(value)} div"
        return f"{_display_number(self.chaos)} chaos"

    def graph_points(self) -> tuple[float, ...]:
        return tuple(float(value) for value in self.graph if value is not None)

    def trend_summary(self) -> tuple[str, str] | None:
        change = self.total_change
        if change is None:
            points = self.graph_points()
            change = points[-1] if points else None
        if change is None:
            return None
        rounded = round(change)
        if rounded > 0:
            return "↗", f"+{rounded}%"
        if rounded < 0:
            return "↘", f"{rounded}%"
        return "→", "0%"


def _display_number(value: float) -> str:
    if abs(value) < 10:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return str(round(value))


def _default_fetcher(league: str) -> dict:
    url = f"{API_URL}?league={quote(league, safe='')}&language=en"
    request = Request(url, headers={"User-Agent": "PoENavi/poetore"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _default_stash_fetcher(league: str, type_name: str) -> dict:
    url = (
        f"{STASH_OVERVIEW_URL}?league={quote(league, safe='')}"
        f"&type={quote(type_name, safe='')}"
    )
    request = Request(url, headers={"User-Agent": "PoENavi/poetore"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = re.sub(r"[^a-zA-Z0-9:\- ]", "", normalized).lower()
    return normalized.replace(" ", "-")


def _league_slug(league: str) -> str:
    if league == "Standard":
        return "standard"
    if league == "Hardcore":
        return "hardcore"
    hardcore = league.startswith("Hardcore ")
    value = league.removeprefix("Hardcore ").lower().replace(" ", "")
    return f"{value}hc" if hardcore else value


def _line_url(league: str, overview_url: str, line: dict) -> str:
    details = str(line.get("name", ""))
    if line.get("variant"):
        details += f", {line['variant']}"
    return f"https://poe.ninja/poe1/economy/{_league_slug(league)}/{overview_url}/{_slug(details)}"


_URL_BY_TYPE = {
    "Currency": "currency", "Fragment": "fragments", "DivinationCard": "divination-cards",
    "Essence": "essences", "Fossil": "fossils", "Resonator": "resonators",
    "Scarab": "scarabs", "Oil": "oils", "DeliriumOrb": "delirium-orbs",
    "Artifact": "artifacts", "Tattoo": "tattoos", "Omen": "omens", "Vial": "vials",
    "Incubator": "incubators", "Runegraft": "runegrafts", "DjinnCoin": "djinn-coins",
    "Astrolabe": "astrolabes", "AllflameEmber": "allflame-embers", "Beast": "beasts",
    "Invitation": "invitations", "Map": "maps", "BlightedMap": "blighted-maps",
    "BlightRavagedMap": "blight-ravaged-maps", "ValdoMap": "valdo-maps",
    "IncursionTemple": "incursion-temples", "UniqueJewel": "unique-jewels",
    "ForbiddenJewel": "unique-jewels", "UniqueFlask": "unique-flasks",
    "UniqueWeapon": "unique-weapons", "UniqueArmour": "unique-armours",
    "UniqueAccessory": "unique-accessories", "UniqueMap": "unique-maps",
    "UniqueRelic": "unique-relics", "UniqueIdol": "unique-idols",
    "UniqueTincture": "unique-tinctures", "SkillGem": "skill-gems", "ImbuedGem": "skill-gems",
}


class PoeNinjaPriceService:
    """poe.ninja価格一覧の取得・キャッシュ・高信頼度照合をUIから分離する。"""

    def __init__(
        self,
        fetcher: Callable[[str], dict] = _default_fetcher,
        stash_fetcher: Callable[[str, str], dict] = _default_stash_fetcher,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetcher = fetcher
        self._stash_fetcher = stash_fetcher
        self._clock = clock
        self._cache: dict[str, tuple[float, dict]] = {}
        self._stash_cache: dict[tuple[str, str], tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._stash_cache.clear()

    def lookup(
        self,
        item: ParsedItem,
        league: str,
        *,
        trade_name: str | None = None,
        trade_base_type: str | None = None,
    ) -> PoeNinjaPrice | None:
        if not league or re.search(r"\(PL\d+\)$", league):
            return None
        payload = self._payload(league)
        price = match_poe_ninja_price(
            payload, item, league, trade_name=trade_name, trade_base_type=trade_base_type,
        )
        if price is None or not price.source_type or price.source_type in {"Currency", "Fragment"}:
            return price
        try:
            current = self._stash_payload(league, price.source_type)
            return _refresh_from_stash_overview(price, current)
        except Exception:
            # 参考価格の補助取得失敗で通常検索を妨げず、dense API値へフォールバックする。
            return price

    def _payload(self, league: str) -> dict:
        with self._lock:
            cached = self._cache.get(league)
            now = self._clock()
            if cached and now - cached[0] < CACHE_TTL_SECONDS:
                return cached[1]
            payload = self._fetcher(league)
            if not isinstance(payload, dict):
                raise ValueError("poe.ninjaの応答形式を認識できませんでした。")
            self._cache[league] = (now, payload)
            return payload

    def _stash_payload(self, league: str, type_name: str) -> dict:
        key = (league, type_name)
        with self._lock:
            cached = self._stash_cache.get(key)
            now = self._clock()
            if cached and now - cached[0] < CACHE_TTL_SECONDS:
                return cached[1]
            payload = self._stash_fetcher(league, type_name)
            if not isinstance(payload, dict):
                raise ValueError("poe.ninjaの現行価格応答を認識できませんでした。")
            self._stash_cache[key] = (now, payload)
            return payload


def _refresh_from_stash_overview(price: PoeNinjaPrice, payload: dict) -> PoeNinjaPrice:
    details = price.name
    if price.variant:
        details += f", {price.variant}"
    details_id = _slug(details)
    lines = payload.get("lines", ())
    line = next((row for row in lines if str(row.get("detailsId", "")) == details_id), None)
    if line is None:
        return price
    chaos = float(line.get("chaosValue", 0))
    if chaos <= 0:
        return price
    sparkline = line.get("sparkLine") or {}
    graph = tuple(sparkline.get("data", ()))
    total_change = sparkline.get("totalChange")
    return PoeNinjaPrice(
        price.name, price.variant, chaos, graph, price.url, price.divine_chaos,
        float(total_change) if total_change is not None else None, price.source_type,
    )


def _overview_lines(payload: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    seen: dict[str, set[tuple[str, str, float]]] = {}
    for group in ("currencyOverviews", "itemOverviews"):
        for overview in payload.get(group, ()):
            type_name = str(overview.get("type", ""))
            if type_name in _URL_BY_TYPE:
                target = result.setdefault(type_name, [])
                type_seen = seen.setdefault(type_name, set())
                for line in overview.get("lines", ()):
                    key = (
                        str(line.get("name", "")), str(line.get("variant", "")),
                        float(line.get("chaos", 0)),
                    )
                    if key not in type_seen:
                        type_seen.add(key)
                        target.append(line)
    return result


def _english_candidates(item: ParsedItem, trade_name: str | None, trade_base_type: str | None) -> tuple[str, ...]:
    values = (trade_name, trade_base_type, item.name, item.base_type)
    return tuple(dict.fromkeys(str(value).strip() for value in values if value and str(value).strip()))


def _gem_variant(item: ParsedItem) -> str:
    level_text = item.properties.get("ジェムレベル") or item.properties.get("Gem Level") \
        or item.properties.get("レベル") or item.properties.get("Level") or "1"
    level_match = re.search(r"\d+", level_text)
    level = int(level_match.group()) if level_match else 1
    quality_text = item.properties.get("品質") or item.properties.get("Quality") or ""
    quality_match = re.search(r"\d+", quality_text)
    quality = int(quality_match.group()) if quality_match else 0
    variant = str(level if level >= 20 else 1)
    if quality:
        variant += f"/{20 if 16 <= quality <= 20 else quality}"
    if "corrupted" in item.flags:
        variant += "c"
    return variant


def _map_tier(item: ParsedItem) -> int | None:
    value = item.properties.get("マップティア") or item.properties.get("Map Tier")
    if not value:
        match = re.search(r"(?:Tier|ティア)\s*(\d+)", f"{item.name} {item.base_type}", re.I)
        return int(match.group(1)) if match else None
    match = re.search(r"\d+", value)
    return int(match.group()) if match else None


def _best_unique_line(lines: list[dict], name: str, item: ParsedItem, base_type: str | None) -> dict | None:
    matches = [line for line in lines if str(line.get("name", "")).casefold() == name.casefold()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return None
    base = (base_type or item.base_type or "").casefold()
    links = "6L" if re.search(r"(?:^|\s)(?:[RGBWAB]-){5}[RGBWAB](?:\s|$)", item.properties.get("ソケット", "") or item.properties.get("Sockets", "")) else ""
    scored = []
    for line in matches:
        variant = str(line.get("variant", ""))
        score = int(bool(base and base in variant.casefold())) + int(bool(links and links in variant))
        scored.append((score, line))
    best_score = max(score for score, _line in scored)
    best = [line for score, line in scored if score == best_score]
    return best[0] if best_score > 0 and len(best) == 1 else None


def _current_map_generation(overviews: dict[str, list[dict]]) -> int | None:
    generations = []
    for type_name in _MAP_TYPES:
        for line in overviews.get(type_name, ()):
            match = re.search(r"\bGen-(\d+)\b", str(line.get("variant", "")))
            if match:
                generations.append(int(match.group(1)))
    return max(generations) if generations else None


def match_poe_ninja_price(
    payload: dict,
    item: ParsedItem,
    league: str,
    *,
    trade_name: str | None = None,
    trade_base_type: str | None = None,
) -> PoeNinjaPrice | None:
    overviews = _overview_lines(payload)
    candidates = _english_candidates(item, trade_name, trade_base_type)
    rarity = item.rarity.casefold()
    selected: tuple[str, dict] | None = None

    if rarity in {"unique", "ユニーク"}:
        if "unidentified" in item.flags or "foil" in item.flags or "foulborn" in item.flags:
            return None
        unique_name = trade_name or item.name
        for type_name in _UNIQUE_TYPES:
            line = _best_unique_line(overviews.get(type_name, []), unique_name, item, trade_base_type)
            if line is not None:
                selected = (type_name, line)
                break
    elif item.category == "gem":
        variant = _gem_variant(item)
        for type_name in ("SkillGem", "ImbuedGem"):
            for name in candidates:
                line = next((row for row in overviews.get(type_name, ())
                             if str(row.get("name", "")).casefold() == name.casefold()
                             and str(row.get("variant", "")) == variant), None)
                if line is not None:
                    selected = (type_name, line)
                    break
            if selected:
                break
    elif item.category == "map":
        tier = _map_tier(item)
        map_identity = f"{item.name}\n{item.base_type}\n{item.raw_text}".casefold()
        is_ravaged = "blight-ravaged" in map_identity or "ブライトに破壊" in map_identity
        is_blighted = (
            is_ravaged or "blighted map" in map_identity or "エリアは真菌に覆われている" in item.raw_text
        )
        type_names = ("BlightRavagedMap",) if is_ravaged else \
            (("BlightedMap",) if is_blighted else ("ValdoMap", "Map"))
        map_names = list(candidates)
        if tier is not None:
            if is_ravaged:
                map_names.insert(0, f"Blight-ravaged Map (Tier {tier})")
            elif is_blighted:
                map_names.insert(0, f"Blighted Map (Tier {tier})")
        for type_name in type_names:
            lines = [row for row in overviews.get(type_name, ())
                     if str(row.get("name", "")).casefold() in {name.casefold() for name in map_names}]
            current_generation = _current_map_generation(overviews)
            current_lines = [
                row for row in lines
                if current_generation is not None
                and f"Gen-{current_generation}" in str(row.get("variant", ""))
            ]
            if len(current_lines) == 1:
                selected = (type_name, current_lines[0])
                break
            if len(lines) == 1:
                selected = (type_name, lines[0])
                break
            # Atlas世代違いで複数行ある場合は誤価格防止のため表示しない。
    else:
        allowed_types = _EXACT_TYPES_BY_CATEGORY.get(item.category, set())
        matches = []
        for type_name in allowed_types:
            for line in overviews.get(type_name, ()):
                if str(line.get("name", "")).casefold() in {name.casefold() for name in candidates}:
                    matches.append((type_name, line))
        if len(matches) == 1:
            selected = matches[0]

    if selected is None:
        return None
    type_name, line = selected
    chaos = float(line.get("chaos", 0))
    if chaos <= 0:
        return None
    divine_line = next((row for row in overviews.get("Currency", ()) if row.get("name") == "Divine Orb"), None)
    divine_chaos = float(divine_line["chaos"]) if divine_line and float(divine_line.get("chaos", 0)) >= 30 else None
    return PoeNinjaPrice(
        str(line.get("name", "")), str(line["variant"]) if line.get("variant") else None,
        chaos, tuple(line.get("graph", ())),
        _line_url(league, _URL_BY_TYPE[type_name], line), divine_chaos,
        float(line["sparkLine"]["totalChange"])
        if isinstance(line.get("sparkLine"), dict) and line["sparkLine"].get("totalChange") is not None
        else None,
        type_name,
    )


default_poe_ninja_service = PoeNinjaPriceService()
