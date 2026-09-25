import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPIKE = ROOT / "spikes" / "001-ndlocr-resident-memory"
SERVER = SPIKE / "ndlocr_resident_server.py"
SPEC = importlib.util.spec_from_file_location("ndlocr_resident_server", SERVER)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def test_model_paths_cover_detector_and_three_recognizers(tmp_path):
    paths = server.model_paths(tmp_path)
    assert set(paths) == {
        "det_weights", "det_classes", "rec_weights30", "rec_weights50",
        "rec_weights", "rec_classes",
    }
    assert len([path for path in paths.values() if path.suffix == ".onnx"]) == 4


def test_response_reports_physical_64_and_minimum_confidence():
    payload = server.response_payload({
        "text": "物 理 ダ メ ー ジ が 64 % 増 加 す る",
        "json_lines": [{"confidence": 0.91}, {"confidence": 0.87}],
    }, 123.4567)
    assert payload == {
        "ok": True,
        "elapsed_ms": 123.457,
        "text": "物 理 ダ メ ー ジ が 64 % 増 加 す る",
        "expected_text_found": True,
        "minimum_confidence": 0.87,
    }


def test_windows_runner_measures_startup_requests_and_idle_memory():
    script = (SPIKE / "run_probe.ps1").read_text(encoding="utf-8")
    batch = (ROOT / "RUN_NDLOCR_RESIDENT_MEMORY_TEST.cmd").read_text(
        encoding="utf-8",
    )
    for marker in (
        "WorkingSet64", "PrivateMemorySize64", "PeakWorkingSet64",
        "model_startup_ms", "request_", "idle_", "summary.json", "report.html",
    ):
        assert marker in script
    assert "RepeatCount = 5" in script
    assert "IdleSeconds = 300" in script
    assert "e510d3a7b878395ea9de0bdd365711b699e5fd430b5c7e23a40e918e913fd1f2" in script
    assert "run_probe.ps1" in batch


def test_spike_is_not_connected_to_the_production_ocr_path():
    production = (ROOT / "src" / "poetore" / "poe2" / "ndlocr_lite.py").read_text(
        encoding="utf-8",
    )
    assert "NdlOcrResident" not in production
    assert "resident" not in production.lower()
