from datetime import datetime, timedelta, timezone
import json

from src.poetore.poe2.local_global_audit import (
    AuditResponse, _query, build_candidates, run_one_step,
)


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def test_candidates_cover_armour_evasion_and_energy_shield_when_present():
    candidates = build_candidates()
    assert candidates
    texts = "\n".join(candidate["modifier_text"] for candidate in candidates)
    assert "Evasion" in texts or "回避力" in texts
    assert "Armour" in texts or "アーマー" in texts
    assert "Energy Shield" in texts or "エナジーシールド" in texts
    assert all(candidate["selected_id"] not in candidate["alternative_ids"] for candidate in candidates)


def test_query_changes_only_the_local_global_stat_group():
    candidate = build_candidates()[0]
    selected = _query(candidate, "selected")["query"]
    alternative = _query(candidate, "alternative")["query"]
    either = _query(candidate, "or")["query"]
    assert selected["type"] == alternative["type"] == either["type"]
    assert selected["filters"] == alternative["filters"] == either["filters"]
    assert selected["stats"][0]["filters"][0]["id"] == candidate["selected_id"]
    assert {row["id"] for row in either["stats"][0]["filters"]} == {
        candidate["selected_id"], *candidate["alternative_ids"],
    }


def test_one_step_makes_at_most_one_request_and_resumes_atomically(tmp_path):
    calls = []

    def requester(method, url, payload):
        calls.append((method, url, payload))
        return AuditResponse(200, {"id": "query-1", "total": 3, "result": ["item-1"]}, {
            "X-Rate-Limit-Ip-State": "1:20:60",
        })

    first = run_one_step(tmp_path, requester=requester, now=NOW)
    assert first["api_call"] is True
    assert len(calls) == 1
    waiting = run_one_step(tmp_path, requester=requester, now=NOW + timedelta(seconds=10))
    assert waiting["status"] == "waiting"
    assert len(calls) == 1
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["candidates"][0]["stage"] == "alternative"


def test_429_pauses_without_advancing_stage(tmp_path):
    def requester(_method, _url, _payload):
        return AuditResponse(429, {"error": {"message": "rate limit"}}, {"Retry-After": "120"})

    result = run_one_step(tmp_path, requester=requester, now=NOW)
    assert result["status"] == "paused"
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["candidates"][0]["stage"] == "selected"
    assert datetime.fromisoformat(state["resume_at"].replace("Z", "+00:00")) >= NOW + timedelta(seconds=180)


def test_suspicious_difference_adds_fetch_as_separate_next_call(tmp_path):
    responses = iter((
        AuditResponse(200, {"id": "selected", "total": 0, "result": []}, {}),
        AuditResponse(200, {"id": "alternative", "total": 12, "result": ["alt-item"]}, {}),
        AuditResponse(200, {"id": "or", "total": 12, "result": ["or-item"]}, {}),
        AuditResponse(200, {"result": [{"item": {"baseType": "Test Base", "explicitMods": ["mod"]}}]}, {}),
    ))
    calls = []

    def requester(method, url, payload):
        calls.append((method, url, payload))
        return next(responses)

    for offset in (0, 31, 62):
        run_one_step(tmp_path, requester=requester, now=NOW + timedelta(seconds=offset))
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["candidates"][0]["stage"] == "fetch"
    assert len(calls) == 3
    run_one_step(tmp_path, requester=requester, now=NOW + timedelta(seconds=93))
    assert len(calls) == 4
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["candidates"][0]["stage"] == "finalize"
