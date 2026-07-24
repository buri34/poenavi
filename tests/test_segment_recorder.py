from types import SimpleNamespace
from unittest.mock import Mock

from src.ui.main_window import MainWindow
from src.utils.i18n import EN, get_locale, set_locale
from src.utils.poe_version_data import POE1
from src.utils.segment_recorder import SegmentRecorder


def test_records_elapsed_time_between_distinct_area_entries():
    recorder = SegmentRecorder()

    assert recorder.record_entry("act1_area1", "黄昏の岸辺", 10.0) is None
    completed = recorder.record_entry("act1_area2", "海岸", 42.5)

    assert completed == {
        "zone_id": "act1_area1",
        "zone_name": "黄昏の岸辺",
        "visit": 1,
        "started_at": 10.0,
        "ended_at": 42.5,
        "duration": 32.5,
    }
    assert recorder.segments == [completed]


def test_ignores_duplicate_entry_and_records_reentry_as_a_new_visit():
    recorder = SegmentRecorder()

    recorder.record_entry("act1_area1", "黄昏の岸辺", 0.0)
    assert recorder.record_entry("act1_area1", "黄昏の岸辺", 1.0) is None
    recorder.record_entry("act1_area2", "海岸", 20.0)
    recorder.record_entry("act1_area1", "黄昏の岸辺", 40.0)

    assert [(segment["zone_id"], segment["visit"], segment["duration"]) for segment in recorder.segments] == [
        ("act1_area1", 1, 20.0),
        ("act1_area2", 1, 20.0),
    ]


def test_slowest_segments_returns_at_most_three_longest_completed_segments():
    recorder = SegmentRecorder()
    recorder.segments = [
        {"zone_id": "a", "duration": 10.0},
        {"zone_id": "b", "duration": 40.0},
        {"zone_id": "c", "duration": 30.0},
        {"zone_id": "d", "duration": 20.0},
    ]

    assert [segment["zone_id"] for segment in recorder.slowest_segments()] == ["b", "c", "d"]


def test_summary_returns_latest_and_three_slowest_segments():
    recorder = SegmentRecorder([
        {"zone_id": "a", "zone_name": "海岸", "duration": 10.0},
        {"zone_id": "b", "zone_name": "海底洞窟", "duration": 30.0},
        {"zone_id": "c", "zone_name": "罪人の通路", "duration": 20.0},
        {"zone_id": "d", "zone_name": "牢獄", "duration": 40.0},
    ])

    summary = recorder.summary()

    assert summary["latest"]["zone_id"] == "d"
    assert [segment["zone_id"] for segment in summary["slowest"]] == ["d", "b", "c"]


def test_segment_summary_uses_locale_specific_zone_names():
    original_locale = get_locale()
    set_locale(EN)
    try:
        window = MainWindow.__new__(MainWindow)
        window.zone_data = {
            "Act 1": [
                {
                    "id": "act1_area2",
                    "zone": "海岸",
                    "zone_en": "The Coast",
                }
            ]
        }
        segment = {
            "zone_id": "act1_area2",
            "zone_name": "海岸",
            "duration": 12.5,
        }
        window.segment_recorder = SimpleNamespace(
            summary=lambda: {"latest": segment, "slowest": [segment]}
        )
        window.segment_summary_label = Mock()

        window._update_segment_summary()

        window.segment_summary_label.setText.assert_called_once_with(
            "Latest: The Coast 00:12.50\n"
            "Slowest segments: The Coast 00:12.50"
        )
    finally:
        set_locale(original_locale)


def test_timer_state_restores_active_segment_across_restart():
    original = MainWindow.__new__(MainWindow)
    original.accumulated_time = 42.5
    original.lap_times = [None] * 10
    original.lap_record_order = []
    original.current_act = 1
    original.segment_recorder = SegmentRecorder()
    original.segment_recorder.record_entry(
        "act1_area1", "The Twilight Strand", 10.0
    )

    payload = original._timer_state_payload()

    restored = MainWindow.__new__(MainWindow)
    restored.poe_version = POE1
    restored._load_timer_state_payload = lambda: payload
    restored._migrate_legacy_timer_state_from_config = lambda: None
    restored.update_text = Mock()
    restored.update_lap_display = Mock()
    restored._set_part2 = Mock()
    restored._restore_timer_state()

    completed = restored.segment_recorder.record_entry(
        "act1_area2", "The Coast", 60.0
    )

    assert completed == {
        "zone_id": "act1_area1",
        "zone_name": "The Twilight Strand",
        "visit": 1,
        "started_at": 10.0,
        "ended_at": 60.0,
        "duration": 50.0,
    }

    restored.segment_recorder.record_entry(
        "act1_area1", "The Twilight Strand", 80.0
    )
    assert restored.segment_recorder.to_state()["current"]["visit"] == 2
