from datetime import datetime

from src.utils.poe_process import ProcessCandidate, select_process_candidate


def _candidate(pid, path, second=0):
    return ProcessCandidate(
        pid=pid,
        executable_path=path,
        started_at=datetime(2026, 9, 28, 16, 0, second),
        handle=pid + 100,
    )


def test_select_process_matches_client_log_install_directory():
    candidates = [
        _candidate(1, r"C:\Games\Path of Exile\PathOfExileSteam.exe"),
        _candidate(2, r"D:\Games\Path of Exile 2\PathOfExileSteam.exe"),
    ]
    assert select_process_candidate(
        candidates, r"D:\Games\Path of Exile 2\logs\Client.txt"
    ).pid == 2


def test_select_process_accepts_a_single_unambiguous_poe_process():
    candidates = [
        _candidate(1, r"C:\Games\Path of Exile\PathOfExile_x64.exe"),
        _candidate(9, r"C:\Tools\PoENavi.exe"),
    ]
    assert select_process_candidate(candidates, "").pid == 1


def test_select_process_rejects_multiple_unmatched_processes():
    candidates = [
        _candidate(1, r"C:\A\PathOfExile.exe"),
        _candidate(2, r"C:\B\PathOfExileSteam.exe"),
    ]
    assert select_process_candidate(candidates, r"D:\Unknown\logs\Client.txt") is None


def test_select_process_prefers_newest_match_in_same_install_directory():
    candidates = [
        _candidate(1, r"C:\PoE\PathOfExile.exe", 1),
        _candidate(2, r"C:\PoE\PathOfExileSteam.exe", 2),
    ]
    assert select_process_candidate(
        candidates, r"C:\PoE\logs\Client.txt"
    ).pid == 2
