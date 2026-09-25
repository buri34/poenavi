import importlib.util
import io
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

from src.poetore.poe2.ndlocr_lite import NdlOcrResult

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_ndlocr_helper.py"
SPEC = importlib.util.spec_from_file_location("verify_ndlocr_helper", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def test_verify_script_finds_project_modules_without_pythonpath(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_verify_runs_packaged_helper_against_reported_physical_64(monkeypatch):
    fixture = (
        Path(__file__).parent / "fixtures" / "poetore" / "poe2" / "desecration"
        / "reported-spear-physical-read-failed.png"
    )
    server = Mock()
    server.recognize.return_value = [NdlOcrResult("物理ダメージが64%増加する", .874)]
    server.last_metrics = Mock(cold_start=False)
    factory = Mock(return_value=server)
    monkeypatch.setattr(verifier, "NdlOcrLiteServer", factory)

    assert verifier.verify(Path("PoENaviNdlOcr.exe"), fixture) == verifier.EXPECTED
    factory.assert_called_once_with(helper=Path("PoENaviNdlOcr.exe"), timeout=120)
    assert server.recognize.call_count == 2
    assert len(server.recognize.call_args.args[0]) == 1
    server.close.assert_called_once_with()


def test_main_forces_utf8_when_runner_stdout_starts_as_cp1252(monkeypatch):
    output = io.BytesIO()
    stdout = io.TextIOWrapper(output, encoding="cp1252")
    monkeypatch.setattr(verifier.sys, "stdout", stdout)
    monkeypatch.setattr(verifier.sys, "stderr", io.StringIO())
    monkeypatch.setattr(verifier, "verify", Mock(return_value=verifier.EXPECTED))
    monkeypatch.setattr(
        verifier.sys,
        "argv",
        ["verify_ndlocr_helper.py", "--helper", "helper.exe", "--image", "input.png"],
    )

    assert verifier.main() == 0
    stdout.flush()
    assert output.getvalue().decode("utf-8").strip() == verifier.EXPECTED
