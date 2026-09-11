from unittest.mock import patch

from src.poetore.performance import (
    SearchPerformanceTrace,
    record_mini_navi_topmost_event,
    record_trade_api_event,
)


def test_search_performance_trace_records_elapsed_and_delta_with_one_id():
    times = iter((10.0, 10.0, 10.125, 10.5))
    records = []
    trace = SearchPerformanceTrace(
        "alt_d", clock=lambda: next(times), emit=records.append, trace_id="trace-1",
    )

    trace.mark("clipboard_read", characters=321)
    trace.mark("trade_search_response", candidates=42)

    assert [row["event"] for row in records] == [
        "started", "clipboard_read", "trade_search_response",
    ]
    assert {row["trace_id"] for row in records} == {"trace-1"}
    assert records[1]["elapsed_ms"] == 125.0
    assert records[1]["delta_ms"] == 125.0
    assert records[2]["elapsed_ms"] == 500.0
    assert records[2]["delta_ms"] == 375.0
    assert records[1]["characters"] == 321


def test_trade_api_diagnostic_record_contains_only_sanitized_fields():
    with patch("src.poetore.performance._queue_record") as queue_record:
        record_trade_api_event(
            "request_completed",
            stage="search_post",
            method="POST",
            mod_filters=6,
            attempt=2,
            elapsed_ms=20000.0,
            status=None,
            outcome="failed",
            error_type="ReadTimeoutError",
        )

    record = queue_record.call_args.args[0]
    assert record["source"] == "trade_api"
    assert record["event"] == "request_completed"
    assert record["stage"] == "search_post"
    assert record["mod_filters"] == 6
    assert record["attempt"] == 2
    assert record["elapsed_ms"] == 20000.0
    assert record["status"] is None
    assert record["outcome"] == "failed"
    assert record["error_type"] == "ReadTimeoutError"
    assert "url" not in record
    assert "payload" not in record
    assert "cookie" not in record


def test_mini_navi_topmost_record_contains_only_timing_and_z_order_state():
    with patch("src.poetore.performance._queue_record") as queue_record:
        record_mini_navi_topmost_event(
            "transition",
            desired=False,
            tick_gap_ms=3012.5,
            foreground_kind="other",
            overlay_topmost_after=False,
            foreground_above_overlay=False,
        )

    record = queue_record.call_args.args[0]
    assert record["source"] == "mini_navi_topmost"
    assert record["event"] == "transition"
    assert record["desired"] is False
    assert record["tick_gap_ms"] == 3012.5
    assert record["foreground_kind"] == "other"
    assert record["overlay_topmost_after"] is False
    assert record["foreground_above_overlay"] is False
    assert "window_title" not in record
    assert "process_path" not in record
    assert "hwnd" not in record
