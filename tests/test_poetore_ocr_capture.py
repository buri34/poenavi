from pathlib import Path

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage

from src.poetore.ocr_capture import (
    _enhance_for_ocr,
    _largest_true_run,
    _line_belongs_to_central_panel,
    _ocr_candidate_score,
    detect_item_panel,
    ocr_text_to_item_text,
    save_ocr_debug_artifacts,
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


@pytest.fixture(autouse=True)
def official_base_types(monkeypatch):
    rows = (
        ("多様体の指輪", "アクセサリー"),
        ("クイックスタッフ", "武器"),
        ("暗殺者のミット", "防具"),
        ("王族のバーゴネット", "防具"),
    )
    monkeypatch.setattr(
        "src.poetore.ocr_capture.official_japanese_base_types",
        lambda: rows,
    )


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


def test_background_lines_before_title_do_not_replace_preview_item():
    raw = """最大ライフ +91
クイックスタッフ
グローバルクリティカルダメージ倍率 +2%
螺旋するループ (Loath Loop)
多様体の指輪 (Manifold Ring)
メモリーストランド: 5
幽体化度: 7%
装備条件レベル 65
プレフィックスモッド +1個
サフィックスモッド -2個
暗黙モッドは変化しない
最大マナ +62
最大エナジーシールド +47
最大ライフ +91
グローバルクリティカルダメージ倍率 +21%"""

    item = parse_item_text(ocr_text_to_item_text(raw))

    assert item.name == "螺旋するループ (Loath Loop)"
    assert item.base_type == "多様体の指輪 (Manifold Ring)"
    assert all("クイックスタッフ" not in modifier.text for modifier in item.modifiers)


def test_central_panel_filter_rejects_right_side_background_text():
    assert _line_belongs_to_central_panel(250, 620, 819)
    assert not _line_belongs_to_central_panel(680, 810, 819)


def test_enhanced_ocr_image_is_scaled_and_binary():
    image = QImage(100, 50, QImage.Format.Format_RGB32)
    image.fill(0x202020)
    image.setPixel(10, 10, 0xD0A040)

    enhanced = _enhance_for_ocr(image)

    assert enhanced.width() == 200
    assert enhanced.height() == 100
    assert enhanced.pixel(20, 20) & 0xFFFFFF == 0xFFFFFF


def test_ocr_candidate_with_recognized_base_type_is_preferred():
    failed = "最大ライフ +91\nクイックスタッフ\nグローバルクリティカルダメージ倍率 +2%"
    recovered = "螺旋するループ\n多様体の指輪\n最大ライフ +91"

    assert _ocr_candidate_score(recovered) > _ocr_candidate_score(failed)


@pytest.mark.parametrize(
    ("spaced_base", "expected_base"),
    (
        ("暗 殺 者 の ミ ッ ト", "暗殺者のミット"),
        ("王 族 の バ ー ゴ ネ ッ ト", "王族のバーゴネット"),
    ),
)
def test_official_base_type_dictionary_handles_cjk_ocr_spacing(
    spaced_base, expected_base,
):
    raw = f"""実体化させる
嵐の掌握
{spaced_base}
装備条件レベル 68
最大ライフ +91"""

    item = parse_item_text(ocr_text_to_item_text(raw))

    assert item.name == "嵐の掌握"
    assert item.base_type == expected_base
    assert item.item_class == "防具"
    assert item.category == "armour"


def test_official_base_type_dictionary_tolerates_one_ocr_substitution():
    raw = """実体化させる
嵐の掌握
暗殺者のミツト
装備条件レベル 68
最大ライフ +91"""

    item = parse_item_text(ocr_text_to_item_text(raw))

    assert item.name == "嵐の掌握"
    assert item.base_type == "暗殺者のミット"
    assert item.item_class == "防具"


def test_latest_ocr_debug_artifacts_are_saved_in_user_data(tmp_path, monkeypatch):
    monkeypatch.setenv("POENAVI_USER_DATA_DIR", str(tmp_path))
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    image.fill(0x101010)

    debug_dir = save_ocr_debug_artifacts(
        image=image,
        raw_text="OCR原文",
        item_text="再構成文",
    )

    assert debug_dir == tmp_path / "ocr-debug"
    assert (debug_dir / "latest-panel.png").is_file()
    assert (debug_dir / "latest-raw.txt").read_text(encoding="utf-8") == "OCR原文"
    assert (debug_dir / "latest-item.txt").read_text(encoding="utf-8") == "再構成文"
