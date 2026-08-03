from src.poetore.performance import SearchPerformanceTrace


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
