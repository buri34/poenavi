from pathlib import Path

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage

from src.poetore.ocr_capture import (
    _largest_true_run,
    detect_item_panel,
    ocr_text_to_item_text,
)
from src.poetore.parser import parse_item_text


SAMPLE_OCR = """実体化させる
災いのナックル
多様体の指輪
メモリーストランド: 47
幽体化度: 5%
装備条件レベル 68
プレフィックスモッド +1個
サフィックスモッド -2個
暗黙モッドは変化しない
プレフィックスモッドの強さが50%増加する
10から16の物理ダメージをアタックに追加する
グローバルクリティカルダメージ倍率 +24%
最大エナジーシールド +61
最大ライフ +132
最大マナ +111"""


def test_ocr_preview_is_converted_to_parseable_item_text():
    item_text = ocr_text_to_item_text(SAMPLE_OCR)
    item = parse_item_text(item_text)

    assert item.name == "災いのナックル"
    assert item.base_type == "多様体の指輪"
    assert item.properties["レベル"] == "68"
    assert "メモリーストランド: 47" in item_text
    assert "最大ライフ +132" in item_text
    assert len(item.modifiers) >= 7
    assert all(modifier.stat_id for modifier in item.modifiers)


def test_largest_true_run_selects_longest_sequence():
    assert _largest_true_run([False, True, True, False, True, True, True]) == (4, 6)


def test_panel_detector_never_returns_invalid_rectangle():
    image = QImage(320, 240, QImage.Format.Format_RGB32)
    image.fill(0x101010)
    rect = detect_item_panel(image)
    assert rect.isValid()
    assert QRect(0, 0, 320, 240).contains(rect)


def test_panel_detector_accepts_real_sample_when_available():
    sample = Path(
        "/Users/thiroki34/.openclaw/workspace/media/inbound/"
        "openclaw-staged-17d4b5ff-0d21-4156-93a1-d069c033d200/"
        "image---7df5d5a2-63d2-4e77-8f3d-b5da1c42ef6c.png"
    )
    if not sample.exists():
        pytest.skip("conversation sample is unavailable")
    image = QImage(str(sample))
    rect = detect_item_panel(image)
    assert rect.width() >= image.width() * 0.45
    assert rect.height() >= 180
    assert rect.top() <= 70
