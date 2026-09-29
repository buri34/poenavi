import hashlib
import re
import sys
import wave
from array import array
from unittest.mock import MagicMock

import pytest

from src.poetore.notification_audio import (
    NotificationAudioPlayer,
    _decode_audio_file,
    bundled_audio_path,
    copy_custom_audio,
    scale_signed16,
    verify_audio_runtime,
)
from src.utils.config_manager import ConfigManager


def test_volume_50_keeps_original_and_100_amplifies_without_clipping():
    original = array("h", [1000, -2000, 20000, -20000])
    assert scale_signed16(original, 50).tolist() == original.tolist()
    amplified = scale_signed16(original, 100)
    assert max(abs(value) for value in amplified) < 32768
    assert amplified[0] > original[0]
    assert amplified[0] >= 1900
    assert min(amplified) >= -32768


def test_zero_volume_produces_silence():
    assert scale_signed16(array("h", [1, -2, 3]), 0).tolist() == [0, 0, 0]


def test_custom_audio_is_copied_to_user_data(monkeypatch, tmp_path):
    user_data = tmp_path / "user"
    source = tmp_path / "声.wav"
    source.write_bytes(bundled_audio_path().read_bytes())
    monkeypatch.setattr(ConfigManager, "get_user_data_dir", lambda: user_data)
    display_name, stored_name = copy_custom_audio(source)
    assert display_name == "声.wav"
    assert stored_name == "poetore-hideout-notification.wav"
    assert (user_data / stored_name).read_bytes() == source.read_bytes()


def test_audio_decode_supports_japanese_directories_on_windows(tmp_path):
    source = tmp_path / "日本語の共有フォルダ" / "通知音声.wav"
    source.parent.mkdir()
    source.write_bytes(bundled_audio_path().read_bytes())

    decoded = _decode_audio_file(source)

    assert decoded.num_frames > 0
    assert decoded.duration > 3.0


def test_custom_audio_rejects_unsupported_extension(tmp_path):
    source = tmp_path / "notice.ogg"
    source.write_bytes(b"test")
    with pytest.raises(ValueError):
        copy_custom_audio(source)


def test_custom_audio_rejects_broken_supported_file(tmp_path):
    source = tmp_path / "broken.mp3"
    source.write_bytes(b"not an audio file")
    with pytest.raises(ValueError, match="音声ファイルを読み込めませんでした"):
        copy_custom_audio(source)


def test_custom_audio_reports_missing_playback_backend(monkeypatch, tmp_path):
    source = tmp_path / "notice.wav"
    source.write_bytes(bundled_audio_path().read_bytes())
    monkeypatch.setitem(sys.modules, "miniaudio", None)

    with pytest.raises(ValueError, match="音声再生機能を読み込めませんでした"):
        copy_custom_audio(source)


def test_bundled_zundamon_audio_is_the_verified_source_asset():
    path = bundled_audio_path()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "07214ce09a4529be899f46ba2483e8d34c6ae22179c510f0c39b09f33d2a1e3e"
    )
    with wave.open(str(path), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 48000
        assert audio.getnframes() == 189824


def test_windows_release_collects_audio_backend_and_audits_bundled_voice():
    script = (
        bundled_audio_path().parents[2] / "scripts" / "build_release.ps1"
    ).read_text(encoding="utf-8")
    assert '"--hidden-import", "miniaudio"' in script
    assert '"--hidden-import", "_miniaudio"' in script
    assert '"--hidden-import", "_cffi_backend"' in script
    assert '_cffi_backend(?:\\.[^/]+)?\\.pyd$' in script
    assert '"_cffi_backend.pyd"' not in script
    pattern = re.search(
        r'\$_ -match "([^"]*_cffi_backend[^"]+)"', script
    ).group(1)
    assert re.search(pattern, "PoENavi/_internal/_cffi_backend.pyd")
    assert re.search(
        pattern,
        "PoENavi/_internal/_cffi_backend.cp313-win_amd64.pyd",
    )
    assert not re.search(pattern, "PoENavi/_internal/_cffi_backend.py")
    assert '"hideout_focus_notification.wav"' in script
    assert '"--audio-smoke-test"' in script
    assert "POENAVI_AUDIO_SMOKE_RESULT" in script


def test_audio_runtime_smoke_test_imports_backend_and_decodes_bundled_voice():
    decoded = verify_audio_runtime()

    assert decoded.num_frames > 0
    assert decoded.duration > 3.0


def test_custom_playback_failure_falls_back_without_rewriting_settings(qtbot, tmp_path):
    player = NotificationAudioPlayer()
    fallback_messages = []
    failures = []
    player.fallback_used.connect(fallback_messages.append)
    player.failed.connect(failures.append)
    player._play_file = MagicMock(side_effect=[OSError("broken"), None])
    primary = tmp_path / "custom.mp3"
    fallback = tmp_path / "bundled.wav"
    player._playing = True

    player._play_worker(primary, fallback, 50)

    assert player._play_file.call_args_list[0].args == (primary, 50)
    assert player._play_file.call_args_list[1].args == (fallback, 50)
    assert fallback_messages == [
        "設定した音声を再生できなかったため、標準音声を使用しました"
    ]
    assert failures == []
