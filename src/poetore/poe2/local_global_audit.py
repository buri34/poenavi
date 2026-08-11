from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import quote

import urllib3

from ..models import ParsedItem
from .parser import TRADE_CATEGORY_BY_CATEGORY, parse_item_text
from .trade import API_ROOT, USER_AGENT, trade_stat_value


ROOT = Path(__file__).resolve().parents[3]
STAT_INDEX = ROOT / "data" / "poetore" / "poe2" / "stat_index.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "poe2"
DEFAULT_STATE_DIR = Path.home() / ".openclaw" / "data" / "poenavi-audits" / "poe2-local-global"
MIN_INTERVAL_SECONDS = 30
RATE_LIMIT_SAFETY_SECONDS = 60


@dataclass(frozen=True)
class AuditResponse:
    status: int
    payload: dict
    headers: dict[str, str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _normalized_template(text: str) -> str:
    return re.sub(
        r"\s*\((?:Local|ローカル)\)\s*$", "", text.strip(), flags=re.IGNORECASE,
    ).casefold()


def _stat_pairs() -> dict[str, tuple[str, ...]]:
    payload = json.loads(STAT_INDEX.read_text(encoding="utf-8"))
    groups: dict[tuple[str, str], list[str]] = {}
    local_ids: set[str] = set()
    for entry in payload.get("entries", ()):
        stat_id = str(entry.get("id", ""))
        stat_type = str(entry.get("type", ""))
        english = str((entry.get("text") or {}).get("en", ""))
        if not stat_id or not english or stat_type in {"pseudo", "skill"}:
            continue
        normalized = _normalized_template(english)
        groups.setdefault((stat_type, normalized), []).append(stat_id)
        if normalized != english.strip().casefold():
            local_ids.add(stat_id)
    pairs = {}
    for ids in groups.values():
        unique = tuple(dict.fromkeys(ids))
        if len(unique) < 2 or not any(stat_id in local_ids for stat_id in unique):
            continue
        for stat_id in unique:
            alternatives = tuple(candidate for candidate in unique if candidate != stat_id)
            if alternatives:
                pairs[stat_id] = alternatives
    return pairs


def _fixture_texts() -> tuple[tuple[str, str], ...]:
    rows = []
    for path in sorted(FIXTURE_DIR.glob("*.txt")):
        rows.append((path.name, path.read_text(encoding="utf-8")))
    csv_path = FIXTURE_DIR / "real_copy_bilingual.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            for row_number, row in enumerate(csv.DictReader(handle), start=2):
                for key in ("日本語設定の詳細コピー全文", "英語設定の詳細コピー全文"):
                    text = str(row.get(key, "")).strip()
                    # Referenced files were already included by the *.txt scan above.
                    if text and not text.startswith("@"):
                        rows.append((f"{csv_path.name}:{row_number}:{key}", text))
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))

        def collect(value, location: str) -> None:
            if isinstance(value, str):
                if "Item Class:" in value or "アイテムクラス:" in value:
                    rows.append((f"{path.name}:{location}", value))
                return
            if isinstance(value, list):
                for index, child in enumerate(value):
                    collect(child, f"{location}[{index}]")
                return
            if isinstance(value, dict):
                for key, child in value.items():
                    collect(child, f"{location}.{key}")

        collect(payload, "$")
    return tuple(rows)


def _candidate_id(source: str, item: ParsedItem, selected_id: str, alternatives: tuple[str, ...]) -> str:
    raw = "|".join((source, item.category, item.base_type, selected_id, *alternatives))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_candidates() -> list[dict]:
    pairs = _stat_pairs()
    candidates = []
    seen = set()
    for source, text in _fixture_texts():
        try:
            item = parse_item_text(text)
        except ValueError:
            continue
        trade_category = TRADE_CATEGORY_BY_CATEGORY.get(item.category)
        if trade_category is None:
            continue
        for modifier in item.modifiers:
            selected_id = str(modifier.stat_id or "")
            alternatives = pairs.get(selected_id, ())
            value = trade_stat_value(modifier.values)
            if not alternatives or value is None:
                continue
            identity_name = item.name if item.rarity == "unique" else ""
            dedupe = (item.category, item.base_type, item.rarity, identity_name, selected_id, alternatives, value)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            candidates.append({
                "id": _candidate_id(source, item, selected_id, alternatives),
                "source": source,
                "item": {
                    "category": item.category,
                    "trade_category": trade_category,
                    "base_type": item.base_type,
                    "rarity": item.rarity,
                    "name": item.name,
                },
                "modifier_text": modifier.text,
                "selected_id": selected_id,
                "alternative_ids": list(alternatives),
                "value": value,
                "stage": "selected",
                "results": {},
            })
    return candidates


def _query(candidate: dict, mode: str) -> dict:
    item = candidate["item"]
    type_filters = {"category": {"option": item["trade_category"]}}
    if item["rarity"] == "unique":
        type_filters["rarity"] = {"option": "unique"}
    base_query = {
        "status": {"option": "any"},
        "type": item["base_type"],
        "stats": [],
        "filters": {"type_filters": {"filters": type_filters}},
    }
    if item["rarity"] == "unique" and item["name"]:
        base_query["name"] = item["name"]
    value = {"min": candidate["value"]}
    if mode == "selected":
        groups = [{"type": "and", "filters": [{"id": candidate["selected_id"], "value": value}]}]
    elif mode == "alternative":
        groups = [{"type": "count", "value": {"min": 1}, "filters": [
            {"id": stat_id, "value": value} for stat_id in candidate["alternative_ids"]
        ]}]
    elif mode == "or":
        groups = [{"type": "count", "value": {"min": 1}, "filters": [
            {"id": stat_id, "value": value}
            for stat_id in (candidate["selected_id"], *candidate["alternative_ids"])
        ]}]
    else:
        raise ValueError(f"unknown audit mode: {mode}")
    base_query["stats"] = groups
    return {"query": base_query, "sort": {"price": "asc"}}


_pool = urllib3.PoolManager(num_pools=1, maxsize=1, block=True)


def request_trade(method: str, url: str, payload: dict | None) -> AuditResponse:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    response = _pool.request(
        method, url, body=body, headers=headers,
        timeout=urllib3.Timeout(total=20), retries=False,
    )
    text = response.data.decode("utf-8", errors="replace")
    try:
        response_payload = json.loads(text) if text else {}
    except json.JSONDecodeError:
        response_payload = {"raw": text[:1000]}
    return AuditResponse(
        response.status, response_payload,
        {str(key): str(value) for key, value in response.headers.items()},
    )


def _header(headers: dict[str, str], name: str) -> str:
    lowered = name.casefold()
    return next((value for key, value in headers.items() if key.casefold() == lowered), "")


def _rate_limit_resume_at(headers: dict[str, str], now: datetime) -> datetime | None:
    waits = []
    for name in ("X-Rate-Limit-Ip-State", "X-Rate-Limit-Account-State"):
        for part in _header(headers, name).split(","):
            fields = part.strip().split(":")
            if len(fields) < 3:
                continue
            try:
                used, limit, window = (int(fields[0]), int(fields[1]), int(fields[2]))
            except ValueError:
                continue
            if limit > 0 and used >= max(1, limit - 1):
                waits.append(window + RATE_LIMIT_SAFETY_SECONDS)
    return now + timedelta(seconds=max(waits)) if waits else None


def _retry_resume_at(headers: dict[str, str], now: datetime) -> datetime:
    try:
        retry = max(0, int(float(_header(headers, "Retry-After"))))
    except ValueError:
        retry = 0
    return now + timedelta(seconds=max(MIN_INTERVAL_SECONDS, retry + RATE_LIMIT_SAFETY_SECONDS))


def _initial_state(league: str, now: datetime) -> dict:
    return {
        "schema_version": 1,
        "status": "running",
        "league": league,
        "created_at": _iso(now),
        "updated_at": _iso(now),
        "resume_at": None,
        "candidate_index": 0,
        "candidates": build_candidates(),
        "last_headers": {},
        "api_calls": 0,
    }


def _is_suspicious(candidate: dict) -> bool:
    selected = int(candidate["results"].get("selected", {}).get("total", 0))
    alternative = int(candidate["results"].get("alternative", {}).get("total", 0))
    either = int(candidate["results"].get("or", {}).get("total", 0))
    return (selected == 0 < alternative) or either > max(selected + 10, selected * 2)


def _write_reports(state_dir: Path, state: dict) -> None:
    report = {
        "schema_version": 1,
        "league": state["league"],
        "status": state["status"],
        "updated_at": state["updated_at"],
        "api_calls": state["api_calls"],
        "candidates": state["candidates"],
    }
    _atomic_write_json(state_dir / "report.json", report)
    csv_path = state_dir / "report.csv"
    temporary = csv_path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow((
            "candidate_id", "source", "base_type", "modifier", "selected_id",
            "alternative_ids", "selected_total", "alternative_total", "or_total",
            "suspicious", "representative_item",
        ))
        for candidate in state["candidates"]:
            results = candidate["results"]
            writer.writerow((
                candidate["id"], candidate["source"], candidate["item"]["base_type"],
                candidate["modifier_text"], candidate["selected_id"],
                "|".join(candidate["alternative_ids"]),
                results.get("selected", {}).get("total", ""),
                results.get("alternative", {}).get("total", ""),
                results.get("or", {}).get("total", ""),
                _is_suspicious(candidate) if "or" in results else "",
                results.get("fetch", {}).get("item", ""),
            ))
    temporary.replace(csv_path)


def run_one_step(
    state_dir: Path = DEFAULT_STATE_DIR,
    league: str = "Runes of Aldur",
    requester: Callable[[str, str, dict | None], AuditResponse] = request_trade,
    now: datetime | None = None,
) -> dict:
    now = now or _now()
    state_path = state_dir / "state.json"
    state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.exists() else _initial_state(league, now)
    )
    if state["status"] == "complete":
        return {"status": "complete", "api_call": False, "candidate_count": len(state["candidates"])}
    resume_at = _parse_iso(state.get("resume_at"))
    if resume_at and now < resume_at:
        return {"status": "waiting", "api_call": False, "resume_at": _iso(resume_at)}
    index = int(state["candidate_index"])
    if index >= len(state["candidates"]):
        state["status"] = "complete"
        state["updated_at"] = _iso(now)
        _atomic_write_json(state_path, state)
        _write_reports(state_dir, state)
        return {"status": "complete", "api_call": False, "candidate_count": len(state["candidates"])}
    candidate = state["candidates"][index]
    stage = candidate["stage"]
    if stage == "finalize":
        candidate["suspicious"] = _is_suspicious(candidate)
        candidate["stage"] = "complete"
        state["candidate_index"] = index + 1
        state["resume_at"] = None
        state["updated_at"] = _iso(now)
        _atomic_write_json(state_path, state)
        _write_reports(state_dir, state)
        return {"status": "advanced", "api_call": False, "candidate_id": candidate["id"]}

    if stage in {"selected", "alternative", "or"}:
        url = f"{API_ROOT}/search/{quote(state['league'], safe='')}"
        payload = _query(candidate, stage)
        response = requester("POST", url, payload)
    elif stage == "fetch":
        fetch_plan = candidate.get("fetch_plan") or {}
        url = (
            f"{API_ROOT}/fetch/{quote(str(fetch_plan['item_id']), safe=',')}"
            f"?query={quote(str(fetch_plan['query_id']), safe='')}"
        )
        response = requester("GET", url, None)
    else:
        raise ValueError(f"unknown audit stage: {stage}")

    state["api_calls"] += 1
    state["last_headers"] = response.headers
    state["updated_at"] = _iso(now)
    if response.status == 429:
        state["resume_at"] = _iso(_retry_resume_at(response.headers, now))
        state["status"] = "paused"
        _atomic_write_json(state_path, state)
        return {"status": "paused", "api_call": True, "http_status": 429, "resume_at": state["resume_at"]}
    if response.status >= 400:
        state["resume_at"] = _iso(now + timedelta(minutes=5))
        state["status"] = "paused"
        candidate["last_error"] = {"status": response.status, "payload": response.payload}
        _atomic_write_json(state_path, state)
        return {"status": "paused", "api_call": True, "http_status": response.status, "resume_at": state["resume_at"]}

    state["status"] = "running"
    rate_resume = _rate_limit_resume_at(response.headers, now)
    state["resume_at"] = _iso(rate_resume or (now + timedelta(seconds=MIN_INTERVAL_SECONDS)))
    if stage in {"selected", "alternative", "or"}:
        result_ids = [str(value) for value in response.payload.get("result", ())]
        candidate["results"][stage] = {
            "query_id": str(response.payload.get("id", "")),
            "total": int(response.payload.get("total", len(result_ids))),
            "first_id": result_ids[0] if result_ids else "",
        }
        if stage == "selected":
            candidate["stage"] = "alternative"
        elif stage == "alternative":
            candidate["stage"] = "or"
        elif _is_suspicious(candidate):
            source = next(
                (candidate["results"][name] for name in ("selected", "alternative", "or")
                 if candidate["results"].get(name, {}).get("first_id")),
                None,
            )
            if source:
                candidate["fetch_plan"] = {
                    "item_id": source["first_id"], "query_id": source["query_id"],
                }
                candidate["stage"] = "fetch"
            else:
                candidate["stage"] = "finalize"
        else:
            candidate["stage"] = "finalize"
    else:
        rows = response.payload.get("result", ())
        item = (rows[0].get("item") if rows else {}) or {}
        candidate["results"]["fetch"] = {
            "item": str(item.get("name") or item.get("baseType") or ""),
            "base_type": str(item.get("baseType") or ""),
            "explicit_mods": list(item.get("explicitMods") or ()),
            "rune_mods": list(item.get("runeMods") or ()),
        }
        candidate["stage"] = "finalize"
    _atomic_write_json(state_path, state)
    _write_reports(state_dir, state)
    return {
        "status": state["status"], "api_call": True, "http_status": response.status,
        "candidate_id": candidate["id"], "stage": stage, "next_stage": candidate["stage"],
        "resume_at": state["resume_at"], "candidate_count": len(state["candidates"]),
    }
