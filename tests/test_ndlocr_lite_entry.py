import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import Mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ndlocr_lite_entry.py"
SPEC = importlib.util.spec_from_file_location("ndlocr_lite_entry", SCRIPT)
assert SPEC is not None and SPEC.loader is not None


class FakeEngine:
    def recognize(self, image_path):
        return {
            "text": f"物理ダメージが64%増加する:{Path(image_path).name}",
            "confidence": .874,
        }


def test_frozen_entry_explicitly_forces_utf8_stdio(monkeypatch):
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    stdin = Mock()
    stdout = Mock()
    stderr = Mock()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    module._configure_stdio_utf8()

    stdin.reconfigure.assert_called_once_with(encoding="utf-8", errors="strict")
    stdout.reconfigure.assert_called_once_with(encoding="utf-8", errors="strict")
    stderr.reconfigure.assert_called_once_with(
        encoding="utf-8", errors="backslashreplace",
    )


def test_utf8_configuration_overrides_windows_cp932_protocol_stream(monkeypatch):
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    raw_stdout = io.BytesIO()
    stdout = io.TextIOWrapper(raw_stdout, encoding="cp932")
    monkeypatch.setattr(sys, "stdout", stdout)

    module._configure_stdio_utf8()
    stdout.write(json.dumps({"text": "物理ダメージが64%増加する"}, ensure_ascii=False))
    stdout.flush()

    decoded = raw_stdout.getvalue().decode("utf-8")
    assert "物理ダメージが64%増加する" in decoded


def test_server_protocol_loads_once_and_handles_repeated_requests():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    loads = []
    requests = [
        {"command": "recognize", "request_id": "one", "images": ["one.bmp"]},
        {"command": "recognize", "request_id": "two", "images": ["two.bmp"]},
        {"command": "shutdown"},
    ]
    reader = io.StringIO("".join(json.dumps(row) + "\n" for row in requests))
    writer = io.StringIO()

    assert module.serve(
        reader,
        writer,
        engine_factory=lambda: loads.append("loaded") or FakeEngine(),
    ) == 0

    messages = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert loads == ["loaded"]
    assert messages[0]["event"] == "ready"
    assert [message.get("request_id") for message in messages[1:3]] == ["one", "two"]
    assert messages[1]["results"][0]["confidence"] == .874
    assert messages[2]["results"][0]["text"].endswith("two.bmp")
    assert messages[3]["event"] == "stopped"


def test_server_protocol_reports_request_errors_without_exiting():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)

    class BrokenEngine:
        def recognize(self, _image_path):
            raise RuntimeError("broken")

    reader = io.StringIO(
        json.dumps({"command": "recognize", "request_id": "bad", "images": ["x"]})
        + "\n"
        + json.dumps({"command": "shutdown"})
        + "\n"
    )
    writer = io.StringIO()
    module.serve(reader, writer, engine_factory=BrokenEngine)
    messages = [json.loads(line) for line in writer.getvalue().splitlines()]

    assert messages[1] == {
        "event": "result",
        "request_id": "bad",
        "ok": False,
        "error_type": "RuntimeError",
    }
    assert messages[-1]["event"] == "stopped"


def test_server_protocol_stops_on_parent_stdin_eof():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    writer = io.StringIO()

    assert module.serve(io.StringIO(""), writer, engine_factory=FakeEngine) == 0

    messages = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert [message["event"] for message in messages] == ["ready", "stopped"]
