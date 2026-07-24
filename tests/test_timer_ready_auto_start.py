from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.ui.main_window import MainWindow
from src.utils.i18n import tr_ui
from src.utils.log_watcher import LogWatcher
from src.utils.poe_version_data import POE1, POE2


class FakeLogWatcher:
    def __init__(self, active=True):
        self._active = active
        self.poll_interval_ms = 500
        self.intervals = []

    def set_poll_interval(self, interval_ms):
        self.poll_interval_ms = interval_ms
        self.intervals.append(interval_ms)

    @property
    def is_active(self):
        return self._active


def make_window(poe_version=POE1, watcher_active=True):
    window = MainWindow.__new__(MainWindow)
    window.poe_version = poe_version
    window.is_running = False
    window.accumulated_time = 0.0
    window.lap_times = [None] * 10
    window.lap_record_order = []
    window.segment_recorder = SimpleNamespace(segments=[])
    window.current_zone = ""
    window.timer_ready = False
    window._restoring = False
    window.log_watcher = FakeLogWatcher(watcher_active)
    window._normal_log_poll_interval_ms = 500
    return window


def test_ready_uses_fast_polling_and_can_be_cancelled():
    window = make_window()

    window.toggle_timer_ready()
    assert window.timer_ready is True
    assert window.log_watcher.intervals == [100]

    window.toggle_timer_ready()
    assert window.timer_ready is False
    assert window.log_watcher.intervals == [100, 500]


def test_ready_is_rejected_with_existing_record_running_timer_or_poe2():
    window = make_window()
    window.accumulated_time = 0.01
    with patch("src.ui.main_window.QMessageBox.warning") as warning:
        window.toggle_timer_ready()
    assert window.timer_ready is False
    warning.assert_called_once_with(
        window,
        tr_ui("Readyにできません"),
        tr_ui(
            "タイマーの記録が残っています。\n"
            "問題ないか確認のうえ、リセットしてからReadyしてください。"
        ),
    )

    window = make_window()
    window.is_running = True
    window.toggle_timer_ready()
    assert window.timer_ready is False

    window = make_window(POE2)
    window.toggle_timer_ready()
    assert window.timer_ready is False


def test_ready_is_rejected_when_client_log_is_not_being_watched():
    window = make_window(watcher_active=False)
    window.toggle_timer_ready()
    assert window.timer_ready is False


def test_ready_button_stays_enabled_with_existing_record_for_warning():
    window = make_window()
    window.accumulated_time = 0.01

    assert window._can_set_timer_ready() is False
    assert window._can_use_ready_button() is True


def test_actual_twilight_strand_entry_starts_once_and_clears_ready():
    window = make_window()
    window.toggle_timer_ready()

    def start():
        window._set_timer_ready(False)
        window.is_running = True

    window.start_timer = Mock(side_effect=start)
    window._on_actual_zone_entered_for_auto_start("The Coast")
    window.start_timer.assert_not_called()
    assert window.timer_ready is True

    window._on_actual_zone_entered_for_auto_start("黄昏の岸辺")
    window.start_timer.assert_called_once_with()
    assert window.timer_ready is False
    assert window.current_zone == "黄昏の岸辺"
    assert window.log_watcher.poll_interval_ms == 500

    window._on_actual_zone_entered_for_auto_start("The Twilight Strand")
    window.start_timer.assert_called_once_with()


def test_manual_start_still_works_and_clears_ready():
    window = make_window()
    window.timer = Mock()
    window.current_zone = ""
    window.start_time = 0.0
    window.toggle_timer_ready()

    window.start_timer()

    assert window.is_running is True
    assert window.timer_ready is False
    assert window.log_watcher.poll_interval_ms == 500
    window.timer.start.assert_called_once_with(10)


def test_restore_guard_cancels_ready_without_starting():
    window = make_window()
    window.toggle_timer_ready()
    window._restoring = True
    window.start_timer = Mock()

    window._on_actual_zone_entered_for_auto_start("The Twilight Strand")

    window.start_timer.assert_not_called()
    assert window.timer_ready is False


def test_log_watcher_marks_only_explicit_entry_as_actual():
    watcher = LogWatcher()
    actual = []
    normal = []
    watcher.actual_zone_entered.connect(actual.append)
    watcher.zone_entered.connect(normal.append)

    watcher._parse_line(
        "2026/07/23 20:15:29 123456 abc [DEBUG Client 1234] "
        "[SCENE] Set Source [The Twilight Strand]"
    )
    assert actual == []
    assert normal == ["The Twilight Strand"]

    watcher._parse_line(
        "2026/07/23 20:15:30 123456 abc [INFO Client 1234] "
        ": You have entered The Twilight Strand."
    )
    assert actual == ["The Twilight Strand"]
    assert normal == ["The Twilight Strand", "The Twilight Strand"]


def test_restoring_latest_zone_does_not_emit_actual_entry(tmp_path):
    log_path = tmp_path / "Client.txt"
    log_path.write_text(
        "2026/07/23 20:15:30 123456 abc [INFO Client 1234] "
        ": You have entered The Twilight Strand.\n",
        encoding="utf-8",
    )
    watcher = LogWatcher(str(log_path))
    actual = []
    normal = []
    watcher.actual_zone_entered.connect(actual.append)
    watcher.zone_entered.connect(normal.append)

    watcher._restore_latest_state()

    assert actual == []
    assert normal == ["The Twilight Strand"]


def test_changing_poll_interval_updates_running_qtimer():
    watcher = LogWatcher(poll_interval_ms=500)
    watcher._active = True
    watcher._timer.start = Mock()

    watcher.set_poll_interval(100)

    assert watcher.poll_interval_ms == 100
    watcher._timer.start.assert_called_once_with(100)
