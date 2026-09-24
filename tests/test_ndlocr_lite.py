import json
from pathlib import Path
from unittest.mock import patch

from src.poetore.poe2.ndlocr_lite import NdlOcrLiteServer, _payload_result


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

    def fake_run(command, **_kwargs):
        input_dir = Path(command[command.index("--sourcedir") + 1])
        output_dir = Path(command[command.index("--output") + 1])
        assert sorted(path.name for path in input_dir.iterdir()) == [
            "choice-000.bmp", "choice-001.bmp",
        ]
        payload = {"contents": [[{
            "text": "物理ダメージが64%増加する",
            "confidence": .874,
            "boundingBox": [[0, 0], [1, 0]],
        }]]}
        for index in range(2):
            (output_dir / f"choice-{index:03d}.json").write_text(
                json.dumps(payload), encoding="utf-8",
            )
        return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    with patch(
        "src.poetore.poe2.ndlocr_lite._helper_path", return_value=helper,
    ), patch("src.poetore.poe2.ndlocr_lite.subprocess.run", side_effect=fake_run):
        results = NdlOcrLiteServer(helper=helper).recognize([b"first", b"second"])

    assert [result.text for result in results] == [
        "物理ダメージが64%増加する",
        "物理ダメージが64%増加する",
    ]
