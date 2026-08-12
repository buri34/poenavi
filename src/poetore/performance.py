"""Low-overhead, per-search timing diagnostics for poetore."""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import count
import json
from pathlib import Path
from queue import SimpleQueue
import threading
import time
from typing import Callable

from src.utils.config_manager import ConfigManager


PERFORMANCE_LOG_FILENAME = "poetore-performance.jsonl"
PERFORMANCE_LOG_MAX_BYTES = 2 * 1024 * 1024

_trace_counter = count(1)
_write_queue: SimpleQueue[dict] = SimpleQueue()
_writer_lock = threading.Lock()
_writer_started = False


def performance_log_path() -> Path:
    return ConfigManager.get_user_data_path(PERFORMANCE_LOG_FILENAME)


def _rotate_log(path: Path) -> None:
    try:
        if path.stat().st_size < PERFORMANCE_LOG_MAX_BYTES:
            return
    except FileNotFoundError:
        return
    rotated = path.with_suffix(path.suffix + ".1")
    try:
        rotated.unlink(missing_ok=True)
        path.replace(rotated)
    except OSError:
        # 計測ログの保守失敗で価格検索を妨げない。
        return


def _write_records() -> None:
    while True:
        record = _write_queue.get()
        try:
            path = performance_log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            _rotate_log(path)
            with path.open("a", encoding="utf-8", newline="\n") as output:
                output.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                output.write("\n")
        except OSError:
            # 読み取り専用フォルダー等でも本体機能は継続する。
            pass


def _ensure_writer() -> None:
    global _writer_started
    if _writer_started:
        return
    with _writer_lock:
        if _writer_started:
            return
        threading.Thread(
            target=_write_records,
            name="poetore-performance-log",
            daemon=True,
        ).start()
        _writer_started = True


def _queue_record(record: dict) -> None:
    _ensure_writer()
    _write_queue.put(record)


def record_hotkey_event(event: str, **details) -> None:
    """Write suppressed-hotkey diagnostics without blocking the hook thread."""
    _queue_record({
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "source": "suppressed_hotkey",
        "event": event,
        **details,
    })


class SearchPerformanceTrace:
    """Record elapsed and inter-stage time without blocking the UI on file I/O."""

    def __init__(
        self,
        source: str,
        *,
        clock: Callable[[], float] = time.perf_counter,
        emit: Callable[[dict], None] = _queue_record,
        trace_id: str | None = None,
        started_at: float | None = None,
    ):
        self.trace_id = trace_id or f"{int(time.time() * 1000):x}-{next(_trace_counter)}"
        self.source = source
        self._clock = clock
        self._emit = emit
        self._started_at = clock() if started_at is None else started_at
        self._last_at = self._started_at
        self._lock = threading.Lock()
        self.mark("started")

    def mark(self, event: str, **details) -> None:
        now = self._clock()
        with self._lock:
            elapsed_ms = (now - self._started_at) * 1000
            delta_ms = (now - self._last_at) * 1000
            self._last_at = now
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "trace_id": self.trace_id,
            "source": self.source,
            "event": str(event),
            "elapsed_ms": round(elapsed_ms, 3),
            "delta_ms": round(delta_ms, 3),
            "thread": threading.current_thread().name,
        }
        record.update({key: value for key, value in details.items() if value is not None})
        self._emit(record)


def start_search_trace(
    source: str, *, started_at: float | None = None,
) -> SearchPerformanceTrace:
    return SearchPerformanceTrace(source, started_at=started_at)
