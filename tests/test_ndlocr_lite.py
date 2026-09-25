import json
import queue
from pathlib import Path
from typing import ClassVar

import pytest

from src.poetore.poe2.ndlocr_lite import (
    NdlOcrLiteServer,
    _payload_result,
)


class FakeTimer:
    created: ClassVar[list] = []

    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.cancelled = False
        self.started = False
        self.daemon = False
        self.__class__.created.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.callback()


class QueueReader:
    def __init__(self):
        self.lines = queue.Queue()

    def readline(self):
        return self.lines.get()

    def feed(self, payload):
        self.lines.put(json.dumps(payload, ensure_ascii=False) + "\n")

    def close(self):
        self.lines.put("")


class FakePersistentProcess:
    _pid = 1200

    def __init__(self, command, **_kwargs):
        self.command = command
        self.stdout = QueueReader()
        self.stderr = QueueReader()
        self.stdin = self
        self.returncode = None
        self.requests = []
        self.writes = []
        self.pid = self.__class__._pid
        self.__class__._pid += 1
        self.stdout.feed({"event": "ready", "pid": self.pid, "startup_ms": 9876.5})

    def write(self, line):
        self.writes.append(line)
        payload = json.loads(line)
        if payload["command"] == "recognize":
            self.requests.append(payload)
            self.stdout.feed({
                "event": "result",
                "request_id": payload["request_id"],
                "ok": True,
                "inference_ms": 742.5,
                "results": [{
                    "text": "物理ダメージが64%増加する",
                    "confidence": .874,
                } for _path in payload["images"]],
            })
        elif payload["command"] == "shutdown":
            self.returncode = 0
            self.stdout.close()
            self.stderr.close()

    def flush(self):
        pass

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def terminate(self):
        self.returncode = -15
        self.stdout.close()
        self.stderr.close()

    def kill(self):
        self.returncode = -9
        self.stdout.close()
        self.stderr.close()


def test_payload_result_orders_lines_and_uses_lowest_detection_confidence():
    payload = {"contents": [[
        {"text": "増加する", "confidence": .91, "boundingBox": [[0, 30], [1, 30]]},
        {"text": "物理ダメージが64%", "confidence": .874, "boundingBox": [[0, 10], [1, 10]]},
    ]]}
    result = _payload_result(payload)
    assert result.text == "物理ダメージが64%\n増加する"
    assert result.confidence == .874


def test_server_runs_bundled_helper_in_temporary_directory(tmp_path):
    helper = tmp_path / "PoENaviNdlOcr.exe"
    helper.write_bytes(b"placeholder")
    observed = []

    class RecordingProcess(FakePersistentProcess):
        def write(self, line):
            payload = json.loads(line)
            if payload["command"] == "recognize":
                paths = [Path(value) for value in payload["images"]]
                observed.append([(path.name, path.read_bytes()) for path in paths])
            super().write(line)

    process = RecordingProcess([str(helper)])
    server = NdlOcrLiteServer(
        helper=helper,
        process_factory=lambda *_args, **_kwargs: process,
        timer_factory=FakeTimer,
    )
    results = server.recognize([b"first", b"second"])

    assert [result.text for result in results] == [
        "物理ダメージが64%増加する",
        "物理ダメージが64%増加する",
    ]
    assert observed == [[
        ("choice-000.bmp", b"first"),
        ("choice-001.bmp", b"second"),
    ]]
    server.close()


def test_server_reuses_loaded_process_and_records_cold_then_warm_metrics(tmp_path):
    FakeTimer.created = []
    helper = tmp_path / "PoENaviNdlOcr.exe"
    helper.write_bytes(b"placeholder")
    processes = []
    process_options = []

    def factory(command, **kwargs):
        process = FakePersistentProcess(command, **kwargs)
        processes.append(process)
        process_options.append(kwargs)
        return process

    events = []
    server = NdlOcrLiteServer(
        helper=helper,
        timeout=1,
        idle_timeout=180,
        process_factory=factory,
        timer_factory=FakeTimer,
        event_callback=lambda event, **details: events.append((event, details)),
    )
    first = server.recognize([b"first"])
    first_metrics = server.last_metrics
    second = server.recognize([b"second"])
    second_metrics = server.last_metrics

    assert len(processes) == 1
    assert len(processes[0].requests) == 2
    assert process_options[0]["env"]["PYTHONUTF8"] == "1"
    assert process_options[0]["env"]["PYTHONIOENCODING"] == "utf-8"
    assert first[0].text == second[0].text == "物理ダメージが64%増加する"
    assert first_metrics is not None and first_metrics.cold_start is True
    assert first_metrics.startup_ms == 9876.5
    assert second_metrics is not None and second_metrics.cold_start is False
    assert second_metrics.inference_ms == 742.5
    assert server.is_ready
    assert [event for event, _details in events].count("ndl_resident_ready") == 1
    server.close()


def test_server_idle_timer_is_refreshed_by_touch_and_stops_after_180_seconds(tmp_path):
    FakeTimer.created = []
    helper = tmp_path / "PoENaviNdlOcr.exe"
    helper.write_bytes(b"placeholder")
    process = FakePersistentProcess([str(helper)])
    events = []
    server = NdlOcrLiteServer(
        helper=helper,
        timeout=1,
        idle_timeout=180,
        process_factory=lambda *_args, **_kwargs: process,
        timer_factory=FakeTimer,
        event_callback=lambda event, **details: events.append((event, details)),
    )
    server.recognize([b"image"])
    first_timer = FakeTimer.created[-1]

    assert first_timer.interval == 180
    assert server.touch_if_running() is True
    second_timer = FakeTimer.created[-1]
    assert first_timer.cancelled is True
    assert second_timer is not first_timer

    first_timer.fire()
    assert server.is_ready
    second_timer.fire()
    assert not server.is_ready
    assert process.returncode == 0
    assert ("ndl_resident_stopped", {"reason": "idle_timeout"}) in events


def test_server_touch_does_not_start_a_stopped_helper(tmp_path):
    FakeTimer.created = []
    helper = tmp_path / "PoENaviNdlOcr.exe"
    helper.write_bytes(b"placeholder")
    factory_called = False

    def factory(*_args, **_kwargs):
        nonlocal factory_called
        factory_called = True
        return FakePersistentProcess([str(helper)])

    server = NdlOcrLiteServer(
        helper=helper,
        process_factory=factory,
        timer_factory=FakeTimer,
    )
    assert server.touch_if_running() is False
    assert factory_called is False
    assert FakeTimer.created == []


def test_server_close_stops_the_resident_process_and_removes_session_files(tmp_path):
    FakeTimer.created = []
    helper = tmp_path / "PoENaviNdlOcr.exe"
    helper.write_bytes(b"placeholder")
    process = FakePersistentProcess([str(helper)])
    server = NdlOcrLiteServer(
        helper=helper,
        timeout=1,
        process_factory=lambda *_args, **_kwargs: process,
        timer_factory=FakeTimer,
    )
    server.recognize([b"image"])
    session_dir = server.session_dir
    assert session_dir is not None and session_dir.is_dir()

    server.close()

    assert process.returncode == 0
    assert not server.is_ready
    assert not session_dir.exists()


def test_server_restarts_after_unexpected_helper_exit(tmp_path):
    FakeTimer.created = []
    helper = tmp_path / "PoENaviNdlOcr.exe"
    helper.write_bytes(b"placeholder")
    processes = []

    def factory(command, **kwargs):
        process = FakePersistentProcess(command, **kwargs)
        processes.append(process)
        return process

    server = NdlOcrLiteServer(
        helper=helper,
        timeout=1,
        process_factory=factory,
        timer_factory=FakeTimer,
    )
    server.recognize([b"first"])
    first_session = server.session_dir
    processes[0].returncode = 3
    processes[0].stdout.close()

    second = server.recognize([b"second"])

    assert second[0].text == "物理ダメージが64%増加する"
    assert len(processes) == 2
    assert first_session is not None and not first_session.exists()
    assert server.last_metrics is not None and server.last_metrics.cold_start
    server.close()


def test_server_forces_exit_and_cleans_session_after_response_timeout(tmp_path):
    FakeTimer.created = []
    helper = tmp_path / "PoENaviNdlOcr.exe"
    helper.write_bytes(b"placeholder")

    class NoResponseProcess(FakePersistentProcess):
        def write(self, line):
            payload = json.loads(line)
            self.writes.append(line)
            if payload["command"] == "shutdown":
                self.returncode = 0
                self.stdout.close()
                self.stderr.close()

    process = NoResponseProcess([str(helper)])
    server = NdlOcrLiteServer(
        helper=helper,
        timeout=.01,
        process_factory=lambda *_args, **_kwargs: process,
        timer_factory=FakeTimer,
    )

    with pytest.raises(TimeoutError):
        server.recognize([b"image"])

    assert process.returncode == 0
    assert not server.is_ready
    assert server.session_dir is None
