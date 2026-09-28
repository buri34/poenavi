from datetime import datetime

from PySide6.QtCore import QObject, Signal

from src.poetore.hideout_notification_controller import (
    HideoutNotificationController,
)


class FakeProcess:
    def __init__(self, alive=True, pid=1):
        self.alive = alive
        self.pid = pid
        self.started_at = datetime(2026, 9, 28, 16, 0, 0)
        self.closed = False

    def is_alive(self):
        return self.alive

    def close(self):
        self.closed = True


class FakeWatcher(QObject):
    zone_entered = Signal(str)

    def __init__(self, **kwargs):
        super().__init__(kwargs.get("parent"))
        self.is_active = False
        self.restore_state = kwargs.get("restore_state")

    def set_poe_version(self, version):
        self.version = version

    def start(self):
        self.is_active = True
        return True

    def stop(self):
        self.is_active = False


class FakeAudio(QObject):
    fallback_used = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.calls = []
        self.stopped = False

    def play(self, primary, fallback, volume):
        self.calls.append((primary, fallback, volume))
        return True

    def stop(self):
        self.stopped = True


def _config(log_path):
    return {
        "client_log_paths": {"poe1": str(log_path)},
        "poetore": {"hideout_notification": {"duration_seconds": 10}},
    }


def test_monitoring_exists_only_while_focus_mode_is_on(qtbot, monkeypatch, tmp_path):
    log = tmp_path / "Client.txt"
    log.write_text(
        "2026/09/28 16:00:01 [SCENE] Set Source [Coastal Hideout]\n",
        encoding="utf-8",
    )
    now = [100.0]
    audio = FakeAudio()
    process = FakeProcess()
    finder_calls = []
    controller = HideoutNotificationController(
        _config(log), "poe1", lambda config: None,
        process_finder=lambda path: finder_calls.append(path) or process,
        watcher_factory=FakeWatcher,
        audio_player=audio,
        monotonic=lambda: now[0],
    )
    assert not controller.active
    assert not controller.watcher_active
    assert controller.enable()
    assert controller.watcher_active
    assert controller._watcher.restore_state is False
    now[0] = 110.0
    controller._tick()
    assert len(audio.calls) == 1
    assert len(finder_calls) == 1
    controller.disable()
    assert not controller.watcher_active
    assert audio.stopped


def test_zone_event_detects_process_restart_and_resets_timer(qtbot, monkeypatch, tmp_path):
    log = tmp_path / "Client.txt"
    log.write_text(
        "2026/09/28 16:00:01 [SCENE] Set Source [Coastal Hideout]\n",
        encoding="utf-8",
    )
    now = [0.0]
    old_process = FakeProcess(pid=1)
    new_process = FakeProcess(pid=2)
    processes = iter((old_process, new_process))
    controller = HideoutNotificationController(
        _config(log), "poe1", lambda config: None,
        process_finder=lambda path: next(processes),
        watcher_factory=FakeWatcher,
        audio_player=FakeAudio(),
        monotonic=lambda: now[0],
    )
    assert controller.enable()
    now[0] = 7.0
    old_process.alive = False
    controller._on_zone_entered("Another Hideout")
    assert controller.state.started_at == 7.0
    assert controller._process.pid == 2


def test_notification_is_suppressed_when_original_process_has_ended(qtbot, tmp_path):
    log = tmp_path / "Client.txt"
    log.write_text(
        "2026/09/28 16:00:01 [SCENE] Set Source [Coastal Hideout]\n",
        encoding="utf-8",
    )
    now = [0.0]
    audio = FakeAudio()
    process = FakeProcess()
    controller = HideoutNotificationController(
        _config(log), "poe1", lambda config: None,
        process_finder=lambda path: process,
        watcher_factory=FakeWatcher,
        audio_player=audio,
        monotonic=lambda: now[0],
    )
    assert controller.enable()
    process.alive = False
    now[0] = 10.0
    controller._tick()
    assert audio.calls == []
    assert not controller.state.zone_known


def test_invalid_saved_log_path_is_replaced_by_auto_detected_path(
    qtbot, monkeypatch, tmp_path
):
    log = tmp_path / "Client.txt"
    log.write_text(
        "2026/09/28 16:00:01 [SCENE] Set Source [Kingsmarch]\n",
        encoding="utf-8",
    )
    config = _config(tmp_path / "missing" / "Client.txt")
    saves = []
    monkeypatch.setattr(
        "src.poetore.hideout_notification_controller.detect_client_log_paths",
        lambda: {"poe1": str(log), "poe2": ""},
    )
    controller = HideoutNotificationController(
        config, "poe1", lambda value: saves.append(value),
        process_finder=lambda path: FakeProcess(),
        watcher_factory=FakeWatcher,
        audio_player=FakeAudio(),
        monotonic=lambda: 0.0,
    )
    assert controller.enable()
    assert config["client_log_paths"]["poe1"] == str(log)
    assert len(saves) == 1
