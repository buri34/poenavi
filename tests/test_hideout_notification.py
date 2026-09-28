from datetime import datetime

from src.poetore.hideout_notification import (
    HideoutTimerState,
    is_hideout_zone,
    latest_zone_since_process_start,
    normalize_hideout_notification_settings,
    timestamp_from_log_line,
    zone_from_log_line,
)


def test_hideout_settings_are_complete_and_bounded():
    assert normalize_hideout_notification_settings({}) == {
        "duration_seconds": 60,
        "repeat": False,
        "audio_source": "bundled",
        "custom_audio_display_name": "",
        "custom_audio_file": "",
        "volume": 50,
    }
    assert normalize_hideout_notification_settings({
        "duration_seconds": 1,
        "repeat": 1,
        "audio_source": "custom",
        "custom_audio_display_name": "notice.mp3",
        "custom_audio_file": "../custom.mp3",
        "volume": 400,
    }) == {
        "duration_seconds": 10,
        "repeat": True,
        "audio_source": "custom",
        "custom_audio_display_name": "notice.mp3",
        "custom_audio_file": "custom.mp3",
        "volume": 100,
    }


def test_hideout_zone_supports_japanese_and_case_insensitive_english():
    assert is_hideout_zone("夕暮れの隠れ家")
    assert is_hideout_zone("Coastal Hideout")
    assert is_hideout_zone("COASTAL HIDEOUT")
    assert not is_hideout_zone("Kingsmarch")


def test_zone_and_timestamp_parsers_accept_realistic_lines():
    japanese = "2026/09/28 16:20:01 123 [INFO Client] あなたは夕暮れの隠れ家に入場しました。"
    english = "2026/09/28 16:20:02 123 [INFO Client] : You have entered Coastal Hideout."
    scene = "2026/09/28 16:20:03 123 [DEBUG Client] [SCENE] Set Source [ハイゲート]"
    assert zone_from_log_line(japanese) == "夕暮れの隠れ家"
    assert zone_from_log_line(english) == "Coastal Hideout"
    assert zone_from_log_line(scene) == "ハイゲート"
    assert zone_from_log_line("[SCENE] Set Source [(null)]") is None
    assert timestamp_from_log_line(japanese) == datetime(2026, 9, 28, 16, 20, 1)


def test_latest_zone_uses_only_lines_from_current_process(tmp_path):
    log = tmp_path / "Client.txt"
    log.write_text(
        "\n".join((
            "2026/09/28 15:00:00 [INFO Client] あなたは古い隠れ家に入場しました。",
            "2026/09/28 16:00:00 [INFO Client] あなたはハイゲートに入場しました。",
            "2026/09/28 16:05:00 [INFO Client] : You have entered Coastal Hideout.",
        )) + "\n",
        encoding="utf-8",
    )
    assert latest_zone_since_process_start(
        log, datetime(2026, 9, 28, 15, 59, 59, 900000)
    ) == "Coastal Hideout"
    assert latest_zone_since_process_start(
        log, datetime(2026, 9, 28, 16, 6, 0)
    ) is None


def test_latest_zone_rejects_undated_or_old_latest_zone(tmp_path):
    log = tmp_path / "Client.txt"
    log.write_text(
        "2026/09/28 15:59:59 [SCENE] Set Source [Coastal Hideout]\n"
        "[SCENE] Set Source [Another Hideout]\n",
        encoding="utf-8",
    )
    assert latest_zone_since_process_start(
        log, datetime(2026, 9, 28, 16, 0, 0)
    ) is None


def test_timer_starts_at_enable_and_carries_between_hideouts():
    state = HideoutTimerState(duration_seconds=60)
    state.enable("Coastal Hideout", now=100.0)
    assert state.button_text(142.0) == "隠れ家滞在通知\n0:42"
    state.enter_zone("夕暮れの隠れ家", now=150.0)
    assert state.button_text(165.0) == "隠れ家滞在通知\n1:05"
    assert state.consume_due_notification(165.0) == 1
    assert state.button_text(166.0) == "隠れ家滞在通知\n1:06 ✓"


def test_button_text_covers_off_and_repeating_notification_states():
    state = HideoutTimerState(duration_seconds=10, repeat=True)
    assert state.button_text(0.0) == "隠れ家滞在通知\nOFF"
    state.enable("Coastal Hideout", now=0.0)
    assert state.consume_due_notification(10.0) == 1
    assert state.button_text(11.0) == "隠れ家滞在通知\n0:11"


def test_timer_resets_only_after_leaving_hideout():
    state = HideoutTimerState(duration_seconds=10)
    state.enable("Coastal Hideout", now=10.0)
    assert state.consume_due_notification(20.0) == 1
    state.enter_zone("Kingsmarch", now=21.0)
    assert state.button_text(30.0) == "隠れ家滞在通知\nON"
    state.enter_zone("Coastal Hideout", now=40.0)
    assert state.button_text(45.0) == "隠れ家滞在通知\n0:05"
    assert state.consume_due_notification(45.0) is None


def test_repeating_timer_consumes_each_elapsed_slot_once():
    state = HideoutTimerState(duration_seconds=10, repeat=True)
    state.enable("Coastal Hideout", now=0.0)
    assert state.consume_due_notification(9.9) is None
    assert state.consume_due_notification(10.0) == 1
    assert state.consume_due_notification(10.5) is None
    assert state.consume_due_notification(31.0) == 3
    assert state.consume_due_notification(31.5) is None


def test_duration_change_restarts_current_hideout_timer():
    state = HideoutTimerState(duration_seconds=60)
    state.enable("Coastal Hideout", now=0.0)
    state.set_duration(30, now=45.0)
    assert state.button_text(46.0) == "隠れ家滞在通知\n0:01"
    assert state.consume_due_notification(74.9) is None
    assert state.consume_due_notification(75.0) == 1


def test_unknown_zone_waits_without_counting():
    state = HideoutTimerState()
    state.enable(None, now=0.0)
    assert state.button_text(100.0) == "隠れ家滞在通知\nON（エリア待ち）"
    assert state.consume_due_notification(100.0) is None
