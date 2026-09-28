"""Audio storage and playback for hideout-stay notifications."""

from __future__ import annotations

import shutil
import sys
import threading
import time
from array import array
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.utils.config_manager import ConfigManager

BUNDLED_AUDIO_NAME = "hideout_focus_notification.wav"
CUSTOM_AUDIO_STEM = "poetore-hideout-notification"
SUPPORTED_AUDIO_SUFFIXES = {".wav", ".mp3"}


def bundled_audio_path() -> Path:
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
        roots.append(Path(sys.executable).parent)
    roots.append(Path(__file__).resolve().parents[2])
    for root in roots:
        candidate = root / "assets" / "audio" / BUNDLED_AUDIO_NAME
        if candidate.is_file():
            return candidate
    return roots[0] / "assets" / "audio" / BUNDLED_AUDIO_NAME


def custom_audio_path(filename: str) -> Path:
    safe_name = Path(str(filename or "")).name
    if not safe_name:
        return ConfigManager.get_user_data_dir() / f"{CUSTOM_AUDIO_STEM}.wav"
    return ConfigManager.get_user_data_dir() / safe_name


def copy_custom_audio(source: str | Path) -> tuple[str, str]:
    source_path = Path(source)
    suffix = source_path.suffix.casefold()
    if suffix not in SUPPORTED_AUDIO_SUFFIXES:
        raise ValueError("WAVまたはMP3ファイルを選択してください。")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    # Reject corrupt or mislabeled files while the settings dialog can still
    # explain the problem. Playback keeps its own fallback for files that
    # become unreadable after they have been selected.
    try:
        import miniaudio
    except ImportError as error:
        raise ValueError(
            "音声再生機能を読み込めませんでした。アプリを再起動してください。"
        ) from error

    try:
        miniaudio.decode_file(str(source_path))
    except miniaudio.MiniaudioError as error:
        raise ValueError(
            "音声ファイルを読み込めませんでした。別のWAVまたはMP3を選択してください。"
        ) from error
    destination = ConfigManager.get_user_data_dir() / f"{CUSTOM_AUDIO_STEM}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copy2(source_path, temporary)
    temporary.replace(destination)
    return source_path.name, destination.name


def scale_signed16(samples, volume: int) -> array:
    """Scale PCM with a soft limiter. 50 means original amplitude."""
    pcm = array("h", samples)
    volume = max(0, min(100, int(volume)))
    if volume == 50:
        return pcm
    if volume == 0:
        return array("h", [0]) * len(pcm)
    gain = volume / 50.0
    if gain < 1.0:
        return array("h", (round(sample * gain) for sample in pcm))

    # Quiet samples approach the requested gain (up to 2x), while peaks are
    # smoothly compressed instead of being hard-clipped.
    scaled = array("h")
    for sample in pcm:
        normalized = sample / 32768.0
        limited = (gain * normalized) / (
            1.0 + ((gain - 1.0) * abs(normalized))
        )
        scaled.append(max(-32768, min(32767, round(limited * 32768.0))))
    return scaled


class NotificationAudioPlayer(QObject):
    fallback_used = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._playing = False
        self._stop_event = threading.Event()

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._playing

    def play(self, primary: Path, fallback: Path, volume: int) -> bool:
        with self._lock:
            if self._playing:
                return False
            self._playing = True
        self._stop_event.clear()
        threading.Thread(
            target=self._play_worker,
            args=(Path(primary), Path(fallback), int(volume)),
            daemon=True,
            name="PoEToreNotificationAudio",
        ).start()
        return True

    def stop(self) -> None:
        self._stop_event.set()

    def _play_worker(self, primary: Path, fallback: Path, volume: int) -> None:
        try:
            try:
                self._play_file(primary, volume)
            except Exception:  # miniaudio exposes multiple decoder/device errors
                if primary == fallback:
                    raise
                self.fallback_used.emit(
                    "設定した音声を再生できなかったため、標準音声を使用しました"
                )
                self._play_file(fallback, volume)
        except Exception as error:  # keep audio/backend failures outside the UI thread
            self.failed.emit(f"通知音声を再生できませんでした: {error}")
        finally:
            with self._lock:
                self._playing = False
            self.finished.emit()

    def _play_file(self, path: Path, volume: int) -> None:
        import miniaudio

        if not path.is_file():
            raise FileNotFoundError(path)
        decoded = miniaudio.decode_file(
            str(path),
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=2,
            sample_rate=44100,
        )
        samples = scale_signed16(decoded.samples, volume)
        stream = miniaudio.stream_raw_pcm_memory(samples, 2, 2)
        with miniaudio.PlaybackDevice(
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=2,
            sample_rate=44100,
        ) as device:
            device.start(stream)
            deadline = time.monotonic() + float(decoded.duration) + 0.15
            while time.monotonic() < deadline and not self._stop_event.wait(0.02):
                pass
            device.stop()
