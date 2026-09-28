"""Runtime coordinator for PoETore's opt-in hideout notification mode."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from src.poetore.hideout_notification import (
    HideoutTimerState,
    latest_zone_since_process_start,
    normalize_hideout_notification_settings,
)
from src.poetore.notification_audio import (
    NotificationAudioPlayer,
    bundled_audio_path,
    custom_audio_path,
)
from src.utils.log_path_detector import detect_client_log_paths
from src.utils.log_watcher import LogWatcher
from src.utils.poe_process import find_poe_process


class HideoutNotificationController(QObject):
    display_changed = Signal(str)
    focus_changed = Signal(bool)
    flash_requested = Signal()
    message_requested = Signal(str, str)

    def __init__(
        self,
        config: dict,
        poe_version: str,
        save_config,
        parent=None,
        *,
        process_finder=find_poe_process,
        watcher_factory=LogWatcher,
        audio_player=None,
        monotonic=time.monotonic,
    ):
        super().__init__(parent)
        self.config = config
        self.poe_version = poe_version
        self.save_config = save_config
        self._process_finder = process_finder
        self._watcher_factory = watcher_factory
        self._audio = audio_player or NotificationAudioPlayer(self)
        self._monotonic = monotonic
        self._process = None
        self._watcher = None
        self._last_text = ""
        self.settings = self._read_settings()
        self.state = HideoutTimerState(
            duration_seconds=self.settings["duration_seconds"],
            repeat=self.settings["repeat"],
        )
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._tick)
        self._audio.fallback_used.connect(
            lambda text: self.message_requested.emit("warning", text)
        )
        self._audio.failed.connect(
            lambda text: self.message_requested.emit("warning", text)
        )
        self._emit_display(force=True)

    @property
    def active(self) -> bool:
        return self.state.active

    @property
    def watcher_active(self) -> bool:
        return bool(self._watcher is not None and self._watcher.is_active)

    def _read_settings(self) -> dict:
        poetore = self.config.setdefault("poetore", {})
        settings = normalize_hideout_notification_settings(
            poetore.get("hideout_notification")
        )
        poetore["hideout_notification"] = dict(settings)
        return settings

    def toggle(self) -> None:
        if self.active:
            self.disable()
        else:
            self.enable()

    def enable(self) -> bool:
        if self.active:
            return True
        paths = self.config.setdefault("client_log_paths", {})
        log_path = str(paths.get(self.poe_version, "") or "")
        if not Path(log_path).is_file():
            detected = str(
                detect_client_log_paths().get(self.poe_version, "") or ""
            )
            if Path(detected).is_file():
                paths[self.poe_version] = detected
                self.save_config(self.config)
            log_path = str(paths.get(self.poe_version, "") or "")
        if not Path(log_path).is_file():
            self.message_requested.emit(
                "log_missing", "Client.txtを設定してください。"
            )
            return False
        process = self._process_finder(log_path)
        if process is None or not process.is_alive():
            if process is not None:
                process.close()
            self.message_requested.emit(
                "poe_not_running", "PoEを起動してから集中モードをONにしてください。"
            )
            return False
        current_zone = latest_zone_since_process_start(
            log_path, process.started_at
        )
        watcher = self._watcher_factory(
            log_path=log_path, parent=self, restore_state=False
        )
        watcher.set_poe_version(self.poe_version)
        watcher.zone_entered.connect(self._on_zone_entered)
        if not watcher.start():
            process.close()
            self.message_requested.emit(
                "log_missing",
                "Client.txtを監視できませんでした。設定を確認してください。",
            )
            return False
        self._process = process
        self._watcher = watcher
        self.state.enable(current_zone, self._monotonic())
        self._timer.start()
        self.focus_changed.emit(True)
        self._emit_display(force=True)
        return True

    def disable(self) -> None:
        self._timer.stop()
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher.deleteLater()
            self._watcher = None
        if self._process is not None:
            self._process.close()
            self._process = None
        self._audio.stop()
        self.state.disable()
        self.focus_changed.emit(False)
        self._emit_display(force=True)

    def close(self) -> None:
        self.disable()

    def apply_settings(self, config: dict) -> None:
        previous = self.settings
        self.config = config
        current = self._read_settings()
        now = self._monotonic()
        if current["duration_seconds"] != previous["duration_seconds"]:
            self.state.set_duration(current["duration_seconds"], now)
        if current["repeat"] != previous["repeat"]:
            self.state.set_repeat(current["repeat"])
        self.settings = current
        self._emit_display(force=True)

    def _on_zone_entered(self, zone_name: str) -> None:
        now = self._monotonic()
        process_changed = self._process is None or not self._process.is_alive()
        if process_changed:
            if self._process is not None:
                self._process.close()
            self._process = self._process_finder(self._current_log_path())
            self.state.reset_to_unknown()
            if self._process is None or not self._process.is_alive():
                if self._process is not None:
                    self._process.close()
                    self._process = None
                self._emit_display(force=True)
                return
        self.state.enter_zone(zone_name, now)
        self._emit_display(force=True)

    def _current_log_path(self) -> str:
        return str(
            self.config.get("client_log_paths", {}).get(self.poe_version, "") or ""
        )

    def _tick(self) -> None:
        now = self._monotonic()
        if self.state.consume_due_notification(now) is not None:
            if self._process is None or not self._process.is_alive():
                if self._process is not None:
                    self._process.close()
                    self._process = None
                self.state.reset_to_unknown()
            else:
                primary = bundled_audio_path()
                if self.settings["audio_source"] == "custom":
                    primary = custom_audio_path(self.settings["custom_audio_file"])
                if self._audio.play(
                    primary, bundled_audio_path(), self.settings["volume"]
                ):
                    self.flash_requested.emit()
        self._emit_display()

    def _emit_display(self, *, force: bool = False) -> None:
        text = self.state.button_text(self._monotonic())
        if force or text != self._last_text:
            self._last_text = text
            self.display_changed.emit(text)
