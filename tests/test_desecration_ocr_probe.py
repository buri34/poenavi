import json
import re
from pathlib import Path

import pytest

from src.poetore.poe2.desecration_ocr_probe import load_probe_cases, run_probe

FIXTURE_DIR = Path("tests/fixtures/poetore/poe2/desecration")


class ExpectedTextOcr:
    def __init__(self, cases):
        self._responses = [
            [text for text in case.expected_texts for _variant in range(4)]
            for case in cases
        ]
        self.started = False
        self.closed = False

    def start(self):
        self.started = True

    def recognize(self, images):
        assert self.started
        assert len(images) == 12
        return self._responses.pop(0)

    def close(self):
        self.closed = True


class ExpectedNumericOcr(ExpectedTextOcr):
    def __init__(self, cases):
        self._responses = [
            [
                " ".join(re.findall(r"\d+(?:\.\d+)?", text))
                for text in case.expected_texts for _variant in range(4)
            ]
            for case in cases
        ]
        self.started = False
        self.closed = False


def test_reported_images_run_through_full_post_ocr_pipeline(tmp_path):
    cases = load_probe_cases(FIXTURE_DIR, FIXTURE_DIR / "reported-cases.json")
    ocr = ExpectedTextOcr(cases)
    numeric_ocr = ExpectedNumericOcr(cases)

    report = run_probe(
        cases, tmp_path,
        ocr_server=ocr,
        numeric_ocr_server=numeric_ocr,
    )

    assert len(cases) == 7
    assert report["case_count"] == 7
    assert report["passed_cases"] == 7
    assert report["all_expected_passed"] is True
    assert ocr.closed is True
    assert numeric_ocr.closed is True
    assert (tmp_path / "report.html").is_file()
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "アビス冒涜 Windows OCR検証" in html
    assert html.count("OCR候補画像") == 84
    saved = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert saved["cases"][0]["choices"][0]["tier"] == 8
    assert saved["cases"][0]["choices"][0]["numeric_tokens"] == ["3.2"]
    assert saved["cases"][5]["choices"][1]["tier"] == [3, 4]
    assert all(len(choice["prepared_images"]) == 4 for case in saved["cases"] for choice in case["choices"])


def test_prepare_only_saves_all_variants_without_starting_ocr(tmp_path):
    cases = load_probe_cases(FIXTURE_DIR, FIXTURE_DIR / "reported-cases.json")[:1]
    ocr = ExpectedTextOcr(cases)

    report = run_probe(cases, tmp_path, ocr_server=ocr, prepare_only=True)

    assert ocr.started is False
    assert ocr.closed is True
    assert report["cases"][0]["valid_panel"] is True
    assert report["cases"][0]["choices"][0]["status"] == "not_run"


def test_probe_applies_safe_short_numeric_rescue(tmp_path):
    cases = load_probe_cases(FIXTURE_DIR, FIXTURE_DIR / "reported-cases.json")[-1:]
    ocr = ExpectedTextOcr(cases)
    ocr._responses[0][:4] = ["命 中 力 +"] * 4
    numeric_ocr = ExpectedNumericOcr(cases)
    numeric_ocr._responses[0][:4] = ["+64"] * 4

    report = run_probe(
        cases, tmp_path,
        ocr_server=ocr,
        numeric_ocr_server=numeric_ocr,
    )

    assert report["passed_cases"] == 1
    assert report["cases"][0]["choices"][0]["tier"] == 6
    assert report["cases"][0]["choices"][0]["raw_texts"] == ["命 中 力 +"] * 4
    assert report["cases"][0]["choices"][0]["numeric_tokens"] == ["64"]


def test_directory_without_manifest_accepts_only_supported_images(tmp_path):
    (tmp_path / "ignore.txt").write_text("x", encoding="utf-8")
    (tmp_path / "one.PNG").write_bytes(b"not-an-image")

    cases = load_probe_cases(tmp_path)

    assert [case.image.name for case in cases] == ["one.PNG"]


def test_manifest_cannot_escape_the_input_directory(tmp_path):
    outside = tmp_path.parent / "outside.png"
    outside.write_bytes(b"x")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"cases": [{"file": "../outside.png"}]}), encoding="utf-8",
    )

    with pytest.raises(ValueError, match="inside the input directory"):
        load_probe_cases(tmp_path, manifest)


def test_windows_launcher_uses_local_build_output_and_opens_the_report():
    launcher = Path(
        "tools/diagnostics/RUN_DESECRATION_WINDOWS_OCR_TEST.cmd"
    ).read_text(encoding="utf-8")
    script = Path("scripts/run_desecration_windows_ocr.ps1").read_text(encoding="utf-8")

    assert "..\\..\\scripts\\run_desecration_windows_ocr.ps1" in launcher
    assert "$env:LOCALAPPDATA" in script
    assert "poenavi-short-ocr-diagnostic\\helper\\ExpeditionWindowsOcr.exe" in script
    assert "Get-FileHash -LiteralPath $prebuiltHelper -Algorithm SHA256" in script
    assert "if ($trustedPrebuilt)" in script
    assert "Copy-Item -LiteralPath $projectSource" in script
    assert "POENAVI_WINDOWS_OCR_HELPER" in script
    assert 'if ($numericOcrAvailable) { $arguments += @("--numeric-language", "en-US") }' in script
    assert "Start-Process $report" in script
