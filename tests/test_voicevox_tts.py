import json
import queue
import threading
from unittest.mock import Mock

from src.utils.voicevox_tts import VoicevoxTtsService, guide_to_speech_text, split_speech_chunks


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def test_guide_to_speech_text_uses_only_voice_text():
    guide = {"mini_navi": {"text": "表示用", "voice_text": "読み上げ用\n文章"}}
    assert guide_to_speech_text(guide) == "読み上げ用\n文章"


def test_guide_to_speech_text_does_not_fallback_to_display_text():
    assert guide_to_speech_text({"mini_navi": {"text": "表示用"}}) == ""
    assert guide_to_speech_text({"mini_navi": {"text": "表示用", "voice_text": ""}}) == ""


def test_split_speech_chunks_uses_punctuation_and_line_breaks():
    assert split_speech_chunks("右へ進む。ボスを倒す！\n街へ戻る") == [
        "右へ進む。", "ボスを倒す！", "街へ戻る",
    ]


def test_service_posts_query_and_synthesis_with_speed_and_volume():
    requests = []
    played = queue.Queue()

    def opener(request, timeout):
        requests.append((request, timeout))
        if "audio_query" in request.full_url:
            return FakeResponse(b'{}')
        return FakeResponse(b"RIFF-test-wave")

    service = VoicevoxTtsService(
        speed_scale=1.6, volume_scale=1.4, opener=opener,
        player=lambda path: played.put(open(path, "rb").read()), stop_player=Mock(),
    )
    try:
        service.speak_latest("テスト")
        assert played.get(timeout=2) == b"RIFF-test-wave"
    finally:
        service.stop()

    payload = json.loads(requests[1][0].data.decode("utf-8"))
    assert payload == {"speedScale": 1.6, "volumeScale": 1.4}
    assert [item[1] for item in requests] == [10.0, 30.0]


def test_new_request_discards_old_audio_before_playback():
    first_started = threading.Event()
    release_first = threading.Event()
    played = queue.Queue()
    query_count = 0

    def opener(request, timeout):
        nonlocal query_count
        if "audio_query" in request.full_url:
            query_count += 1
            if query_count == 1:
                first_started.set()
                release_first.wait(timeout=2)
            return FakeResponse(b"{}")
        return FakeResponse(f"audio-{query_count}".encode())

    service = VoicevoxTtsService(
        opener=opener,
        player=lambda path: played.put(open(path, "rb").read()),
        stop_player=Mock(),
    )
    try:
        service.speak_latest("古いガイド")
        assert first_started.wait(timeout=2)
        service.speak_latest("新しいガイド")
        release_first.set()
        assert played.get(timeout=2) == b"audio-2"
        assert played.empty()
    finally:
        release_first.set()
        service.stop()


def test_scale_normalization():
    assert VoicevoxTtsService.normalize_speed_scale(9) == 2.0
    assert VoicevoxTtsService.normalize_speed_scale("invalid") == 1.2
    assert VoicevoxTtsService.normalize_volume_scale(-1) == 0.0
    assert VoicevoxTtsService.normalize_volume_scale(9) == 2.0
