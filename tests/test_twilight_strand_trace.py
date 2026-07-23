from unittest.mock import patch

from src.utils.log_watcher import LogWatcher


def test_twilight_trace_reports_log_and_detection_timestamps(capsys):
    watcher = LogWatcher()
    line = (
        "2026/07/23 20:15:30 123456 abc [INFO Client 1234] "
        ": You have entered The Twilight Strand."
    )

    with patch.dict("os.environ", {"POENAVI_TWILIGHT_TRACE": "1"}):
        watcher._parse_line(line)

    output = capsys.readouterr().out
    assert "[黄昏の海岸・検知テスト]" in output
    assert "入場ログ（英語）" in output
    assert "2026/07/23 20:15:30" in output
    assert "PoENavi検知時刻:" in output
    assert "The Twilight Strand" in output


def test_twilight_trace_reports_set_source_separately(capsys):
    watcher = LogWatcher()
    line = (
        "2026/07/23 20:15:29 123456 abc [DEBUG Client 1234] "
        "[SCENE] Set Source [黄昏の海岸]"
    )

    with patch.dict("os.environ", {"POENAVI_TWILIGHT_TRACE": "1"}):
        watcher._parse_line(line)

    output = capsys.readouterr().out
    assert "[黄昏の海岸・検知テスト]" in output
    assert "検知経路     : Set Source" in output


def test_twilight_trace_is_disabled_without_development_flag(capsys):
    watcher = LogWatcher()
    line = (
        "2026/07/23 20:15:30 123456 abc [INFO Client 1234] "
        ": You have entered The Twilight Strand."
    )

    with patch.dict("os.environ", {}, clear=True):
        watcher._parse_line(line)

    output = capsys.readouterr().out
    assert "[黄昏の海岸・検知テスト]" not in output
