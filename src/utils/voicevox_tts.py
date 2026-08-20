"""VOICEVOX Engineを使った、ガイド読み上げ用の軽量バックグラウンド処理。"""

from __future__ import annotations

import json
import os
import queue
import re
import tempfile
import threading
import urllib.parse
import urllib.request
from collections.abc import Callable


VOICEVOX_BASE_URL = "http://127.0.0.1:50021"
MINI_NAVI_ICON_COMMANDS = frozenset({
    "wp", "portal", "quest", "boss", "town", "move", "logout", "note", "star", "trial", "craft",
})


def guide_to_speech_text(guide: dict | None) -> str:
    """PoE2みになびのvoice_textから読み上げテキストを取得する。"""
    if not isinstance(guide, dict):
        return ""

    mini_navi = guide.get("mini_navi")
    if not isinstance(mini_navi, dict):
        return ""
    value = mini_navi.get("voice_text")
    if not isinstance(value, str) or not value.strip():
        return ""

    return value.strip()


def split_speech_chunks(text: str) -> list[str]:
    """読み上げ本文を、意味の切れ目を保った短い合成単位へ分割する。"""
    chunks = re.split(r"(?<=[。！？!?])|[\r\n]+", text or "")
    return [chunk.strip() for chunk in chunks if chunk.strip()]


class VoicevoxTtsService:
    """最新の読み上げ要求だけを残し、UIを止めずにVOICEVOXへ接続する。"""

    def __init__(
        self,
        speaker_id: int = 3,
        speed_scale: float = 1.2,
        pause_length_scale: float = 1.0,
        post_phoneme_length: float = 0.1,
        volume_scale: float = 1.0,
        base_url: str = VOICEVOX_BASE_URL,
        query_timeout_seconds: float = 10.0,
        synthesis_timeout_seconds: float = 30.0,
        player: Callable[[str], None] | None = None,
        stop_player: Callable[[], None] | None = None,
        opener=None,
    ):
        self.speaker_id = int(speaker_id)
        self.speed_scale = self.normalize_speed_scale(speed_scale)
        self.pause_length_scale = self.normalize_pause_length_scale(pause_length_scale)
        self.post_phoneme_length = self.normalize_post_phoneme_length(post_phoneme_length)
        self.volume_scale = self.normalize_volume_scale(volume_scale)
        self.base_url = base_url.rstrip("/")
        self.query_timeout_seconds = float(query_timeout_seconds)
        self.synthesis_timeout_seconds = float(synthesis_timeout_seconds)
        self._opener = opener or urllib.request.urlopen
        self._player = player or self._play_wav
        self._stop_player = stop_player or self._stop_wav
        self._requests: queue.Queue[tuple[int, str] | None] = queue.Queue(maxsize=1)
        self._audio_queue: queue.Queue[tuple[int, bytes] | None] = queue.Queue()
        self._generation = 0
        self._stopped = threading.Event()
        self._last_error = None
        self._request_thread = threading.Thread(
            target=self._run_requests, name="voicevox-tts-requests", daemon=True
        )
        self._playback_thread = threading.Thread(
            target=self._run_playback, name="voicevox-tts-playback", daemon=True
        )
        self._request_thread.start()
        self._playback_thread.start()

    def speak_latest(self, text: str):
        text = (text or "").strip()
        if not text or self._stopped.is_set():
            return
        self._generation += 1
        generation = self._generation
        self._stop_player()
        self._clear_queue(self._requests)
        self._clear_queue(self._audio_queue)
        self._requests.put_nowait((generation, text))

    def stop(self):
        if self._stopped.is_set():
            return
        self._stopped.set()
        self._generation += 1
        self._stop_player()
        self._clear_queue(self._requests)
        self._clear_queue(self._audio_queue)
        self._requests.put_nowait(None)
        self._audio_queue.put_nowait(None)
        self._request_thread.join(timeout=0.3)
        self._playback_thread.join(timeout=0.3)

    @staticmethod
    def _clear_queue(target_queue: queue.Queue):
        while True:
            try:
                target_queue.get_nowait()
            except queue.Empty:
                return

    def _run_requests(self):
        while not self._stopped.is_set():
            request = self._requests.get()
            if request is None:
                return
            generation, text = request
            threading.Thread(
                target=self._synthesize_chunks,
                args=(generation, text),
                name=f"voicevox-tts-synthesis-{generation}",
                daemon=True,
            ).start()

    def _synthesize_chunks(self, generation: int, text: str):
        for chunk in split_speech_chunks(text):
            if generation != self._generation or self._stopped.is_set():
                return
            try:
                audio = self._synthesize(chunk)
            except Exception as exc:
                self._report_error(exc)
                return
            if generation != self._generation or self._stopped.is_set():
                return
            self._last_error = None
            self._audio_queue.put((generation, audio))

    def _run_playback(self):
        while not self._stopped.is_set():
            audio_item = self._audio_queue.get()
            if audio_item is None:
                return
            generation, audio = audio_item
            if generation != self._generation:
                continue
            wav_path = None
            try:
                with tempfile.NamedTemporaryFile(prefix="poenavi-voicevox-", suffix=".wav", delete=False) as wav:
                    wav.write(audio)
                    wav_path = wav.name
                if generation != self._generation or self._stopped.is_set():
                    continue
                self._player(wav_path)
            except Exception as exc:
                self._report_error(exc)
            finally:
                if wav_path:
                    try:
                        os.unlink(wav_path)
                    except OSError:
                        pass

    def _report_error(self, exc: Exception):
        message = f"{type(exc).__name__}: {exc}"
        if message != self._last_error:
            print(f"[VOICEVOX] 読み上げをスキップしました ({message})")
            self._last_error = message

    def _synthesize(self, text: str) -> bytes:
        params = urllib.parse.urlencode({"text": text, "speaker": self.speaker_id})
        query_request = urllib.request.Request(
            f"{self.base_url}/audio_query?{params}", data=b"", method="POST"
        )
        # audio_queryもVOICEVOXの初回起動直後や高負荷時には1秒を超えることがある。
        # localhost未接続は即座にConnectionRefusedとなるため、正常処理用の余裕を持たせる。
        with self._opener(query_request, timeout=self.query_timeout_seconds) as response:
            query = json.loads(response.read().decode("utf-8"))
        query["speedScale"] = self.normalize_speed_scale(self.speed_scale)
        query["pauseLengthScale"] = self.normalize_pause_length_scale(self.pause_length_scale)
        query["postPhonemeLength"] = self.normalize_post_phoneme_length(
            self.post_phoneme_length
        )
        query["volumeScale"] = self.normalize_volume_scale(self.volume_scale)

        synthesis_params = urllib.parse.urlencode({"speaker": self.speaker_id})
        synthesis_request = urllib.request.Request(
            f"{self.base_url}/synthesis?{synthesis_params}",
            data=json.dumps(query, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # ガイド本文は長くなりやすく、VOICEVOXの音声合成には数秒以上かかる。
        # 接続確認用の短いタイムアウトを流用すると正常起動中でも失敗するため分ける。
        with self._opener(synthesis_request, timeout=self.synthesis_timeout_seconds) as response:
            return response.read()

    @staticmethod
    def normalize_speed_scale(value) -> float:
        try:
            return max(0.5, min(2.0, float(value)))
        except (TypeError, ValueError):
            return 1.2

    @staticmethod
    def normalize_volume_scale(value) -> float:
        try:
            return max(0.0, min(2.0, float(value)))
        except (TypeError, ValueError):
            return 1.0

    @staticmethod
    def normalize_pause_length_scale(value) -> float:
        try:
            return max(0.0, min(2.0, float(value)))
        except (TypeError, ValueError):
            return 1.0

    @staticmethod
    def normalize_post_phoneme_length(value) -> float:
        try:
            return max(0.0, min(1.5, float(value)))
        except (TypeError, ValueError):
            return 0.1

    @staticmethod
    def _play_wav(path: str):
        if os.name != "nt":
            return
        import winsound

        winsound.PlaySound(path, winsound.SND_FILENAME)

    @staticmethod
    def _stop_wav():
        if os.name != "nt":
            return
        import winsound

        winsound.PlaySound(None, 0)
