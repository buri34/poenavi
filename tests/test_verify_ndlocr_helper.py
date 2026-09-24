import importlib.util
from pathlib import Path
from unittest.mock import Mock

from src.poetore.poe2.ndlocr_lite import NdlOcrResult

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_ndlocr_helper.py"
SPEC = importlib.util.spec_from_file_location("verify_ndlocr_helper", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def test_verify_runs_packaged_helper_against_reported_physical_64(monkeypatch):
    fixture = (
        Path(__file__).parent / "fixtures" / "poetore" / "poe2" / "desecration"
        / "reported-spear-physical-read-failed.png"
    )
    server = Mock()
    server.recognize.return_value = [NdlOcrResult("物理ダメージが64%増加する", .874)]
    factory = Mock(return_value=server)
    monkeypatch.setattr(verifier, "NdlOcrLiteServer", factory)

    assert verifier.verify(Path("PoENaviNdlOcr.exe"), fixture) == verifier.EXPECTED
    factory.assert_called_once_with(helper=Path("PoENaviNdlOcr.exe"), timeout=120)
    assert len(server.recognize.call_args.args[0]) == 1
