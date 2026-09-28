"""State and log helpers for PoETore hideout-stay notifications."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_HIDEOUT_NOTIFICATION_SETTINGS = {
    "duration_seconds": 60,
    "repeat": False,
    "audio_source": "bundled",
    "custom_audio_display_name": "",
    "custom_audio_file": "",
    "volume": 50,
}

MIN_DURATION_SECONDS = 10
MAX_DURATION_SECONDS = 60 * 60
MAX_LOG_SCAN_BYTES = 128 * 1024 * 1024
BUTTON_LABEL = "隠れ家滞在通知"

_LOG_TIMESTAMP = re.compile(
    r"(?P<date>\d{4}/\d{2}/\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2})"
)
_ZONE_JA = re.compile(r"あなたは(.+?)に入場しました。")
_ZONE_EN = re.compile(r": You have entered (.+?)\.")
_SET_SOURCE = re.compile(r"\[SCENE\] Set Source \[(.+?)\]")
_CHAPTER_ONLY = re.compile(r"(?:アクト\d+|Act\s*\d+)", re.IGNORECASE)


def normalize_hideout_notification_settings(value) -> dict:
    """Return a complete, bounded settings dictionary."""
    source = value if isinstance(value, dict) else {}
    normalized = dict(DEFAULT_HIDEOUT_NOTIFICATION_SETTINGS)
    try:
        duration = int(source.get("duration_seconds", 60))
    except (TypeError, ValueError):
        duration = 60
    normalized["duration_seconds"] = max(
        MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, duration)
    )
    normalized["repeat"] = bool(source.get("repeat", False))
    normalized["audio_source"] = (
        "custom" if source.get("audio_source") == "custom" else "bundled"
    )
    normalized["custom_audio_display_name"] = str(
        source.get("custom_audio_display_name", "") or ""
    )
    custom_file = Path(str(source.get("custom_audio_file", "") or "")).name
    normalized["custom_audio_file"] = custom_file
    try:
        volume = int(source.get("volume", 50))
    except (TypeError, ValueError):
        volume = 50
    normalized["volume"] = max(0, min(100, volume))
    if not custom_file:
        normalized["audio_source"] = "bundled"
    return normalized


def is_hideout_zone(zone_name: str | None) -> bool:
    value = str(zone_name or "")
    return "隠れ家" in value or "hideout" in value.casefold()


def zone_from_log_line(line: str) -> str | None:
    """Extract a usable zone from a Client.txt line."""
    for pattern in (_ZONE_JA, _ZONE_EN, _SET_SOURCE):
        match = pattern.search(line)
        if not match:
            continue
        zone = match.group(1).strip()
        if zone in {"(null)", "(unknown)", "幕間", "Interlude"}:
            return None
        if _CHAPTER_ONLY.fullmatch(zone):
            return None
        return zone
    return None


def timestamp_from_log_line(line: str) -> datetime | None:
    match = _LOG_TIMESTAMP.search(line)
    if not match:
        return None
    try:
        return datetime.strptime(
            f"{match.group('date')} {match.group('time')}", "%Y/%m/%d %H:%M:%S"
        )
    except ValueError:
        return None


def _reverse_log_lines(path: Path, max_bytes: int = MAX_LOG_SCAN_BYTES):
    """Yield UTF-8 log lines from newest to oldest without loading the file."""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        end = handle.tell()
        lower_bound = max(0, end - max(0, int(max_bytes)))
        position = end
        prefix = b""
        while position > lower_bound:
            read_size = min(64 * 1024, position - lower_bound)
            position -= read_size
            handle.seek(position)
            data = handle.read(read_size) + prefix
            parts = data.split(b"\n")
            prefix = parts.pop(0)
            for raw_line in reversed(parts):
                yield raw_line.rstrip(b"\r").decode("utf-8", errors="ignore")
        if prefix:
            yield prefix.rstrip(b"\r").decode("utf-8", errors="ignore")


def latest_zone_since_process_start(
    log_path: str | Path,
    process_started_at: datetime,
    *,
    max_bytes: int = MAX_LOG_SCAN_BYTES,
) -> str | None:
    """Return the newest zone logged during the current PoE process."""
    path = Path(log_path)
    if not path.is_file() or not isinstance(process_started_at, datetime):
        return None
    # Client.txt timestamps have second precision. Compare at that precision so a
    # first line emitted within the process-start second is not discarded.
    threshold = process_started_at.replace(tzinfo=None, microsecond=0)
    try:
        for line in _reverse_log_lines(path, max_bytes=max_bytes):
            zone = zone_from_log_line(line)
            if zone is None:
                continue
            timestamp = timestamp_from_log_line(line)
            if timestamp is None:
                continue
            if timestamp < threshold:
                return None
            return zone
    except OSError:
        return None
    return None


@dataclass
class HideoutTimerState:
    duration_seconds: int = 60
    repeat: bool = False
    active: bool = False
    zone_known: bool = False
    in_hideout: bool = False
    started_at: float | None = None
    notified: bool = False
    last_due_slot: int = 0

    def enable(self, current_zone: str | None, now: float) -> None:
        self.active = True
        self.zone_known = current_zone is not None
        self.in_hideout = is_hideout_zone(current_zone)
        self.started_at = now if self.in_hideout else None
        self.notified = False
        self.last_due_slot = 0

    def disable(self) -> None:
        self.active = False
        self.reset_to_unknown()

    def reset_to_unknown(self) -> None:
        self.zone_known = False
        self.in_hideout = False
        self.started_at = None
        self.notified = False
        self.last_due_slot = 0

    def enter_zone(self, zone_name: str, now: float) -> None:
        hideout = is_hideout_zone(zone_name)
        was_hideout = self.zone_known and self.in_hideout
        self.zone_known = True
        self.in_hideout = hideout
        if hideout:
            if not was_hideout or self.started_at is None:
                self.started_at = now
                self.notified = False
                self.last_due_slot = 0
            return
        self.started_at = None
        self.notified = False
        self.last_due_slot = 0

    def elapsed_seconds(self, now: float) -> int:
        if not self.active or not self.in_hideout or self.started_at is None:
            return 0
        return max(0, int(now - self.started_at))

    def consume_due_notification(self, now: float) -> int | None:
        if not self.active or not self.in_hideout or self.started_at is None:
            return None
        slot = self.elapsed_seconds(now) // max(1, int(self.duration_seconds))
        if slot < 1:
            return None
        if self.repeat:
            if slot <= self.last_due_slot:
                return None
            self.last_due_slot = slot
            return slot
        if self.notified:
            return None
        self.notified = True
        self.last_due_slot = max(1, slot)
        return self.last_due_slot

    def set_duration(self, duration_seconds: int, now: float) -> None:
        self.duration_seconds = max(
            MIN_DURATION_SECONDS,
            min(MAX_DURATION_SECONDS, int(duration_seconds)),
        )
        if self.active and self.in_hideout:
            self.started_at = now
        self.notified = False
        self.last_due_slot = 0

    def set_repeat(self, repeat: bool) -> None:
        self.repeat = bool(repeat)
        if not self.repeat and self.last_due_slot:
            self.notified = True

    def button_text(self, now: float) -> str:
        if not self.active:
            return f"{BUTTON_LABEL}\nOFF"
        if not self.zone_known:
            return f"{BUTTON_LABEL}\nON（エリア待ち）"
        if not self.in_hideout:
            return f"{BUTTON_LABEL}\nON"
        elapsed = self.elapsed_seconds(now)
        minutes, seconds = divmod(elapsed, 60)
        suffix = " ✓" if self.notified and not self.repeat else ""
        return f"{BUTTON_LABEL}\n{minutes}:{seconds:02d}{suffix}"
