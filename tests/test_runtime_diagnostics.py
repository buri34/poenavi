from unittest.mock import patch

from src.utils.runtime_diagnostics import (
    capture_runtime_snapshot,
    print_runtime_snapshot,
)


class Window:
    active_service_names = {"currency_rate_refresh", "global_hotkeys"}


def test_runtime_snapshot_records_mode_threads_modules_and_services(capsys):
    with patch(
        "src.utils.runtime_diagnostics.perf_counter",
        return_value=1.25,
    ), patch(
        "src.utils.runtime_diagnostics._process_memory_mib",
        return_value=42.5,
    ), patch.dict(
        "os.environ",
        {"POENAVI_PROFILE": "1"},
    ):
        snapshot = capture_runtime_snapshot("poetore", 1.0, Window())
        print_runtime_snapshot(snapshot)

    assert snapshot.startup_ms == 250
    assert snapshot.memory_mib == 42.5
    assert snapshot.services == ("currency_rate_refresh", "global_hotkeys")
    output = capsys.readouterr().out
    assert "mode=poetore" in output
    assert "memory=42.5 MiB" in output
