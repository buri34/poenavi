import base64
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

import src.poetore.expedition_ocr_probe as probe
from src.poetore.expedition_ocr_probe import (
    OCR_MAX_IMAGE_DIMENSION,
    OCR_TARGET_TEXT_HEIGHT,
    RowBand,
    WindowsOcrServer,
    analyze_directory,
    detect_reward_cards,
    detect_row_bands,
    expedition_panel_diagnostics,
    load_item_dictionary,
    looks_like_expedition_panel,
    match_item_name,
    normalize_text,
    otsu_threshold,
    parse_quantity_ocr,
    prepare_qimage_rows,
    prepare_retry_row_images,
    reward_text_candidates,
    score_rows,
    strip_quantity,
    write_results_csv,
)


def _black_ink_height(image_bytes: bytes) -> int:
    image = QImage.fromData(image_bytes, "BMP").convertToFormat(
        QImage.Format.Format_Grayscale8
    )
    rows = []
    for y in range(image.height()):
        if any(image.pixelColor(x, y).red() < 128 for x in range(image.width())):
            rows.append(y)
    return rows[-1] - rows[0] + 1 if rows else 0


def test_registered_expedition_region_has_reward_card_structure():
    image = QImage("assets/images/expedition_region_example.png").copy(
        47, 162, 605, 652
    )
    diagnostics = expedition_panel_diagnostics(image)
    assert diagnostics["matched"]
    assert diagnostics["band_count"] >= 1
    assert diagnostics["panel_width"] >= 80
    assert diagnostics["min_band_height"] >= 10
    assert looks_like_expedition_panel(image)


def _solid_panel_with_bright_band(
    *, width: int = 600, height: int = 652, top: int, bottom: int,
) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB888)
    image.fill(QColor(40, 40, 40))
    for y in range(top, bottom):
        for x in range(width):
            image.setPixelColor(x, y, QColor(190, 190, 190))
    return image


def test_expedition_panel_rejects_one_band_taller_than_registered_region_ratio():
    image = _solid_panel_with_bright_band(top=120, bottom=354)

    diagnostics = expedition_panel_diagnostics(image)

    assert diagnostics["band_count"] == 1
    assert diagnostics["max_band_height"] == 117
    assert diagnostics["max_band_height_ratio"] > 0.35
    assert not diagnostics["matched"]
    assert not looks_like_expedition_panel(image)


def test_expedition_panel_keeps_one_tall_reward_below_registered_region_ratio():
    image = _solid_panel_with_bright_band(top=100, bottom=244)

    diagnostics = expedition_panel_diagnostics(image)

    assert diagnostics["band_count"] == 1
    assert diagnostics["max_band_height"] == 72
    assert diagnostics["max_band_height_ratio"] < 0.23
    assert diagnostics["matched"]
    assert looks_like_expedition_panel(image)


@pytest.mark.parametrize("scale", (0.5, 0.7, 1.0, 1.3))
def test_expedition_panel_height_ratio_is_stable_across_image_scales(scale):
    valid = QImage("assets/images/expedition_region_example.png").copy(
        47, 162, 605, 652
    )
    false_positive = _solid_panel_with_bright_band(top=120, bottom=354)

    def scaled(image: QImage) -> QImage:
        return image.scaled(
            round(image.width() * scale),
            round(image.height() * scale),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    assert expedition_panel_diagnostics(scaled(valid))["matched"]
    assert not expedition_panel_diagnostics(scaled(false_positive))["matched"]


def test_load_channels_reads_exact_rgb_values_with_padded_rows(tmp_path):
    image = QImage(3, 2, QImage.Format.Format_RGB888)
    colors = (
        QColor(10, 20, 30), QColor(40, 50, 60), QColor(70, 80, 90),
        QColor(100, 110, 120), QColor(130, 140, 150), QColor(160, 170, 180),
    )
    for index, color in enumerate(colors):
        image.setPixelColor(index % 3, index // 3, color)
    path = tmp_path / "channels.png"
    assert image.save(str(path), "PNG")

    width, height, gray, red, green, blue = probe._load_channels(path)

    assert (width, height) == (3, 2)
    assert list(red) == [10, 40, 70, 100, 130, 160]
    assert list(green) == [20, 50, 80, 110, 140, 170]
    assert list(blue) == [30, 60, 90, 120, 150, 180]
    assert len(gray) == 6


def test_windows_powershell_launcher_is_windows_powershell_compatible_ascii():
    launcher = Path("scripts/run_expedition_windows_ocr.ps1").read_bytes()

    assert launcher.isascii()


def test_windows_ocr_helper_has_persistent_memory_protocol():
    source = Path("tools/ExpeditionWindowsOcr/Program.cs").read_text(encoding="utf-8")

    assert '"--server"' in source
    assert "InMemoryRandomAccessStream" in source
    assert "Convert.FromBase64String" in source


def test_windows_ocr_helper_preserves_recognized_line_boundaries():
    source = Path("tools/ExpeditionWindowsOcr/Program.cs").read_text(encoding="utf-8")

    assert 'string.Join("\\n", result.Lines.Select' in source


def test_normalize_text_preserves_japanese_and_normalizes_quantity_marker():
    assert normalize_text("  3× 高貴なオーブ！ ") == "3x 高貴なオーブ"


def test_otsu_threshold_separates_dark_text_and_light_background():
    threshold = otsu_threshold(([20] * 40) + ([230] * 160))
    assert 20 <= threshold < 230


def test_detect_row_bands_merges_small_vertical_gaps_and_adds_padding():
    width, height = 20, 30
    binary = [0] * (width * height)
    for y in (5, 6, 7, 9, 10, 11, 20, 21, 22, 23, 24):
        for x in range(3, 10):
            binary[y * width + x] = 1
    assert detect_row_bands(binary, width, height, max_blank_gap=2, padding=2) == [
        RowBand(3, 14),
        RowBand(18, 27),
    ]


def test_score_rows_reports_exact_and_similarity_rates():
    score = score_rows(["3x 高貴なオーブ", "混沌のオーブ"], ["3× 高貴なオーブ", "混沌のオ一ブ"])
    assert score["exact_rows"] == 1
    assert score["exact_rate"] == 0.5
    assert 0.9 < score["mean_similarity"] < 1.0


def test_strip_quantity_and_dedicated_quantity_parser():
    assert strip_quantity("| 3× 高貴なオーブ") == (3, "高貴なオーブ")


def test_reward_text_candidates_prioritizes_quantity_suffix_on_same_or_next_line():
    assert reward_text_candidates("記号の誤読 1x 復活のグレーター ルーン")[0] == (
        "復活のグレーター ルーン"
    )
    assert reward_text_candidates("記号の誤読\n1x カトラの陰鬱")[0] == "カトラの陰鬱"
    assert parse_quantity_ocr(" 3x 19 ") == 3
    assert parse_quantity_ocr("19") is None


@pytest.mark.parametrize(
    ("raw", "quantity", "item_text"),
    [
        ("lx 滋 養 の ワ ー ド ル ー ン", 1, "滋 養 の ワ ー ド ル ー ン"),
        ("1 , 勇 気 の ワ ー ド ル ー ン", 1, "勇 気 の ワ ー ド ル ー ン"),
        ("1 = 窮 地 の ワ ー ド ル ー ン", 1, "窮 地 の ワ ー ド ル ー ン"),
        ("、 lx ワ ー ド ル ー ン", 1, "ワ ー ド ル ー ン"),
        ("ⅸ 錬 金 術 の オ ー ブ", 1, "錬 金 術 の オ ー ブ"),
        ("6 = 秘 術 師 の 彫 刻 針", 6, "秘 術 師 の 彫 刻 針"),
    ],
)
def test_windows_quantity_misreads_are_parsed_and_removed(raw, quantity, item_text):
    assert parse_quantity_ocr(raw) == quantity
    assert strip_quantity(raw) == (quantity, item_text)


@pytest.mark.parametrize(
    "raw",
    [
        "ス キ ル レ ベ ル 20 : グ リ ム ピ ラ",
        "ラ ン ダ ム な カ レ ン シ ー 5 個",
        "19",
    ],
)
def test_quantity_parser_does_not_use_non_leading_numbers(raw):
    assert parse_quantity_ocr(raw) is None


def test_dictionary_matching_rejects_ambiguous_neighbour():
    candidates = ["勇気のワードルーン", "補強のワードルーン"]
    exact = match_item_name("勇気のワードルーン", candidates)
    ambiguous = match_item_name("のワードルーン", candidates)
    assert exact[0] == "勇気のワードルーン" and exact[3] is True
    assert ambiguous[3] is False


def test_dictionary_matching_does_not_downgrade_a_missing_variant_suffix():
    candidates = ["カオスオーブ", "カオスオーブ (上級)"]
    assert match_item_name("カオスオーブ om i", candidates)[3] is False
    assert match_item_name("カオスオーブ", candidates)[3] is True


def test_dictionary_matching_corrects_exact_known_exalted_orb_ocr_error():
    candidates = ["高貴なオーブ", "高貴なオーブ (上級)", "高貴なオーブ (完全)"]

    result = match_item_name("高 員 な オ ー ブ", candidates)

    assert result[0] == "高貴なオーブ"
    assert result[3] is True


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    (
        ("1 , サ カ ワ ル の 浸 良 の ル ー ン 一", "サカワルの浸食のルーン"),
        ("lx ス ル ー ド の カ", "スルードの力"),
    ),
)
def test_dictionary_matching_corrects_observed_expedition_ocr_errors(
    raw_text, expected,
):
    candidates = ["サカワルの浸食のルーン", "スルードの力"]
    _quantity, item_text = strip_quantity(raw_text)

    result = match_item_name(item_text, candidates)

    assert result[0] == expected
    assert result[1] == 1.0
    assert result[3] is True


def test_dictionary_matching_uses_an_exact_ocr_level_to_disambiguate_variants():
    loaded = json.loads(
        Path("data/poetore/poe2/expedition_ocr_items.json").read_text(encoding="utf-8")
    )
    candidates = [row["ja"] for row in loaded["items"]]

    result = match_item_name(
        ", マ タ ー ジ ・ フ ラ ッ ク ス ( レ ベ ル 1 8 }",
        candidates,
    )

    assert result[0] == "ソーマタージ・フラックス (レベル18)"
    assert result[3] is True


def test_dictionary_matching_does_not_override_a_different_ocr_level():
    candidates = [
        "ソーマタージ・フラックス (レベル17)",
        "ソーマタージ・フラックス (レベル18)",
    ]

    result = match_item_name("ソーマタージ・フラックス (レベル17)", candidates)

    assert result[0] == "ソーマタージ・フラックス (レベル17)"
    assert result[3] is True


def test_load_dictionary_and_write_flat_csv(tmp_path):
    source = tmp_path / "items.json"
    source.write_text(
        '{"result":[{"entries":[{"type":"高貴なオーブ"},{"name":"固有名"}]}]}',
        encoding="utf-8",
    )
    assert load_item_dictionary(source) == ["固有名", "高貴なオーブ"]
    output = tmp_path / "items.csv"
    write_results_csv(
        [{"rows": [{"matched_item_name": "高貴なオーブ", "trusted": True, "quantity": 3}]}],
        output,
    )
    csv_text = output.read_text(encoding="utf-8-sig")
    assert "image" not in csv_text
    assert "高貴なオーブ" in csv_text


def test_detect_reward_cards_ignores_header_and_partial_card():
    width, height = 100, 180
    gray = [50] * (width * height)
    red = [50] * (width * height)
    green = [50] * (width * height)
    blue = [50] * (width * height)

    def paint(top, bottom, right=55):
        for y in range(top, bottom):
            for x in range(right):
                index = y * width + x
                gray[index] = red[index] = green[index] = blue[index] = 200

    paint(10, 50, 46)  # title/header: narrower and visually less solid than reward cards
    paint(65, 105)
    paint(112, 152)
    paint(159, 175)  # clipped row
    panel_width, bands = detect_reward_cards(gray, red, green, blue, width, height)
    assert panel_width == 100
    assert bands == [RowBand(65, 105), RowBand(112, 152)]


def test_detect_reward_cards_treats_short_wide_image_as_panel_crop():
    width, height = 220, 100
    channels = [[50] * (width * height) for _ in range(4)]
    for top, bottom in ((10, 40), (50, 80)):
        for y in range(top, bottom):
            for x in range(width):
                for channel in channels:
                    channel[y * width + x] = 200
    panel_width, bands = detect_reward_cards(*channels, width, height)
    assert panel_width == width
    assert bands == [RowBand(10, 40), RowBand(50, 80)]


def test_prepare_qimage_rows_keeps_images_in_memory():
    image = QImage(220, 100, QImage.Format.Format_RGB888)
    image.fill(QColor(50, 50, 50))
    for top, bottom in ((10, 40), (50, 80)):
        for y in range(top, bottom):
            for x in range(220):
                image.setPixelColor(x, y, QColor(200, 200, 200))

    prepared = prepare_qimage_rows(image)

    assert prepared.bands == (RowBand(10, 40), RowBand(50, 80))
    assert len(prepared.images) == 2
    assert all(data.startswith(b"BM") for data in prepared.images)


def test_prepare_qimage_rows_normalizes_different_source_text_heights():
    def make_image(card_height: int, text_height: int) -> QImage:
        image = QImage(220, card_height + 20, QImage.Format.Format_RGB888)
        image.fill(QColor(50, 50, 50))
        for y in range(10, card_height + 10):
            for x in range(220):
                image.setPixelColor(x, y, QColor(205, 205, 205))
        text_top = 10 + (card_height - text_height) // 2
        for y in range(text_top, text_top + text_height):
            for x in range(100, 180):
                image.setPixelColor(x, y, QColor(25, 25, 25))
        return image

    small = prepare_qimage_rows(make_image(40, 8))
    large = prepare_qimage_rows(make_image(80, 18))

    assert _black_ink_height(small.images[0]) == pytest.approx(
        OCR_TARGET_TEXT_HEIGHT, abs=2,
    )
    assert _black_ink_height(large.images[0]) == pytest.approx(
        OCR_TARGET_TEXT_HEIGHT, abs=2,
    )
    for image_bytes in (*small.images, *large.images):
        image = QImage.fromData(image_bytes, "BMP")
        assert image.width() <= OCR_MAX_IMAGE_DIMENSION
        assert image.height() <= OCR_MAX_IMAGE_DIMENSION


def test_prepare_retry_row_images_only_builds_requested_rows():
    image = QImage(220, 100, QImage.Format.Format_RGB888)
    image.fill(QColor(50, 50, 50))
    for top, bottom in ((10, 40), (50, 80)):
        for y in range(top, bottom):
            for x in range(220):
                image.setPixelColor(x, y, QColor(200, 200, 200))
        for y in range(top + 8, top + 18):
            for x in range(100, 180):
                image.setPixelColor(x, y, QColor(20, 20, 20))

    prepared = prepare_qimage_rows(image)
    with patch.object(
        probe, "_prepare_row_image", wraps=probe._prepare_row_image,
    ) as prepare_row:
        retries = prepare_retry_row_images(prepared, [1])

    assert tuple(retries) == (1,)
    assert len(retries[1]) == 3
    assert all(data.startswith(b"BM") for data in retries[1])
    assert retries[1][1] != prepared.images[1]
    assert prepare_row.call_args_list[0].kwargs["threshold_mode"] == "adaptive"
    assert (
        prepare_row.call_args_list[1].kwargs["target_text_height"]
        == probe.OCR_RETRY_LARGE_TEXT_HEIGHT
    )
    assert prepare_row.call_args_list[2].kwargs["mask_icons"] is True


def test_rune_icon_mask_removes_large_square_without_erasing_small_text():
    width, height = 120, 60
    binary = [0] * (width * height)
    for x in range(5, 40):
        binary[5 * width + x] = 1
        binary[39 * width + x] = 1
    for y in range(5, 40):
        binary[y * width + 5] = 1
        binary[y * width + 39] = 1
    for y in range(22, 32):
        for x in range(75, 82):
            binary[y * width + x] = 1

    probe._mask_likely_rune_icons(binary, width, height)

    assert not any(binary[y * width + x] for y in range(4, 41) for x in range(4, 41))
    assert any(binary[y * width + x] for y in range(22, 32) for x in range(75, 82))


def test_prepare_qimage_rows_uses_the_supplied_panel_crop_width():
    image = QImage(220, 100, QImage.Format.Format_RGB888)
    image.fill(QColor(50, 50, 50))
    for y in range(20, 60):
        for x in range(60):
            image.setPixelColor(x, y, QColor(200, 200, 200))

    prepared = prepare_qimage_rows(image.copy(0, 0, 60, 100))

    assert prepared.panel_width == 60
    assert prepared.bands == (RowBand(20, 60),)


def test_prepare_qimage_rows_uses_every_card_in_the_user_selected_region():
    image = QImage(220, 180, QImage.Format.Format_RGB888)
    image.fill(QColor(50, 50, 50))
    for top, bottom in ((10, 40), (65, 105), (112, 152)):
        for y in range(top, bottom):
            for x in range(100):
                image.setPixelColor(x, y, QColor(200, 200, 200))

    prepared = prepare_qimage_rows(image.copy(0, 0, 100, 180))

    assert prepared.bands == (
        RowBand(10, 40), RowBand(65, 105), RowBand(112, 152),
    )


def test_detect_reward_cards_drops_background_after_one_tall_reward():
    width, height = 100, 220
    channels = [[50] * (width * height) for _ in range(4)]
    for top, bottom, right in ((50, 100, 100), (104, 144, 50)):
        for y in range(top, bottom):
            for x in range(right):
                for channel in channels:
                    channel[y * width + x] = 200
    _, bands = detect_reward_cards(*channels, width, height)
    assert bands == [RowBand(50, 100)]


def test_detect_reward_cards_merges_one_pixel_split_inside_a_tall_reward():
    width, height = 100, 220
    channels = [[50] * (width * height) for _ in range(4)]
    for top, bottom in ((50, 100), (101, 145)):
        for y in range(top, bottom):
            for x in range(width):
                for channel in channels:
                    channel[y * width + x] = 200

    _, bands = detect_reward_cards(*channels, width, height)

    assert bands == [RowBand(50, 145)]


def test_detect_reward_cards_merges_relative_short_halves_inside_a_tall_reward():
    width, height = 120, 370
    channels = [[45] * (width * height) for _ in range(4)]
    painted = [
        RowBand(10, 90), RowBand(100, 180), RowBand(190, 270),
        RowBand(280, 318), RowBand(324, 360),
    ]
    for band in painted:
        for y in range(band.top, band.bottom):
            for x in range(width):
                for channel in channels:
                    channel[y * width + x] = 195

    _, bands = detect_reward_cards(*channels, width, height)

    assert bands == [
        RowBand(10, 90), RowBand(100, 180), RowBand(190, 270), RowBand(280, 360),
    ]


def test_detect_reward_cards_drops_a_background_band_reaching_image_bottom():
    width, height = 100, 220
    channels = [[50] * (width * height) for _ in range(4)]
    for top, bottom in ((50, 100), (101, 145), (150, height)):
        for y in range(top, bottom):
            for x in range(width):
                for channel in channels:
                    channel[y * width + x] = 200

    _, bands = detect_reward_cards(*channels, width, height)

    assert bands == [RowBand(50, 145)]


def test_detect_reward_cards_keeps_short_reward_after_tall_cards():
    width, height = 100, 300
    channels = [[50] * (width * height) for _ in range(4)]
    for top, bottom in ((50, 100), (110, 160), (170, 200)):
        for y in range(top, bottom):
            for x in range(width):
                for channel in channels:
                    channel[y * width + x] = 200
    _, bands = detect_reward_cards(*channels, width, height)
    assert bands == [RowBand(50, 100), RowBand(110, 160), RowBand(170, 200)]


def test_detect_reward_cards_keeps_three_pixel_gaps_and_mixed_card_heights():
    width, height = 120, 300
    channels = [[45] * (width * height) for _ in range(4)]
    expected = [RowBand(10, 90), RowBand(93, 133), RowBand(136, 216)]
    for band in expected:
        for y in range(band.top, band.bottom):
            for x in range(width):
                for channel in channels:
                    channel[y * width + x] = 195

    _, bands = detect_reward_cards(*channels, width, height)

    assert bands == expected


def test_detect_reward_cards_keeps_all_tall_cards_and_excludes_bottom_partial():
    width, height = 120, 260
    channels = [[45] * (width * height) for _ in range(4)]
    expected = [RowBand(8, 78), RowBand(81, 151), RowBand(154, 224)]
    for band in [*expected, RowBand(227, height)]:
        for y in range(band.top, band.bottom):
            for x in range(width):
                for channel in channels:
                    channel[y * width + x] = 195

    _, bands = detect_reward_cards(*channels, width, height)

    assert bands == expected


def test_detect_reward_cards_scans_past_a_large_blank_area():
    width, height = 120, 300
    channels = [[45] * (width * height) for _ in range(4)]
    expected = [RowBand(10, 50), RowBand(210, 250)]
    for band in expected:
        for y in range(band.top, band.bottom):
            for x in range(width):
                for channel in channels:
                    channel[y * width + x] = 195

    _, bands = detect_reward_cards(*channels, width, height)

    assert bands == expected


def test_analyze_empty_directory_writes_empty_summary(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    assert analyze_directory(input_dir, output_dir, prepare_only=True) == []
    assert (output_dir / "summary.json").read_text(encoding="utf-8") == "[]\n"


def test_windows_ocr_is_explicitly_rejected_outside_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.sys, "platform", "darwin")
    with pytest.raises(RuntimeError, match="Windows上でのみ"):
        probe._run_windows_ocr(tmp_path / "row.png", "ja-JP")


def test_windows_ocr_helper_accepts_external_build_path(tmp_path, monkeypatch):
    helper = tmp_path / "ExpeditionWindowsOcr.dll"
    helper.write_bytes(b"test")
    monkeypatch.setenv("POENAVI_WINDOWS_OCR_HELPER", str(helper))
    assert probe._windows_ocr_helper() == helper


def test_packaged_windows_ocr_exe_does_not_require_dotnet(tmp_path, monkeypatch):
    helper = tmp_path / "ExpeditionWindowsOcr.exe"
    helper.write_bytes(b"test")
    calls = []
    monkeypatch.setattr(probe.sys, "platform", "win32")
    monkeypatch.setattr(probe, "_windows_ocr_helper", lambda: helper)
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command)
        or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    assert probe.windows_ocr_available()
    assert calls == [[str(helper), "--check", "ja-JP"]]


def test_windows_ocr_batch_preserves_input_order(tmp_path, monkeypatch):
    helper = tmp_path / "ExpeditionWindowsOcr.exe"
    images = [tmp_path / "a.png", tmp_path / "b.png"]
    monkeypatch.setattr(probe.sys, "platform", "win32")
    monkeypatch.setattr(probe, "_windows_ocr_helper", lambda: helper)
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout='["一番目", "二番目"]', stderr="",
        ),
    )

    assert probe.run_windows_ocr_batch(images) == ["一番目", "二番目"]


def test_windows_ocr_server_reuses_one_process_for_multiple_batches(monkeypatch):
    server = WindowsOcrServer()
    starts = []

    class FakeStdin:
        def write(self, line):
            request = json.loads(line)
            texts = [
                base64.b64decode(value).decode("ascii")
                for value in request["Images"]
            ]
            server._responses.put(json.dumps({"id": request["Id"], "texts": texts}))

        def flush(self):
            pass

    process = SimpleNamespace(stdin=FakeStdin(), poll=lambda: None)

    def ensure_started():
        if server._process is None:
            starts.append(True)
            server._process = process

    monkeypatch.setattr(server, "_ensure_started", ensure_started)

    assert server.recognize([b"first"]) == ["first"]
    assert server.recognize([b"second"]) == ["second"]
    assert len(starts) == 1


def test_windows_ocr_server_restarts_once_after_failure(monkeypatch):
    server = WindowsOcrServer()
    calls = []
    stops = []

    def recognize_once(_images):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("stopped")
        return ["ok"]

    monkeypatch.setattr(server, "_recognize_once", recognize_once)
    monkeypatch.setattr(server, "_stop_process", lambda **_kwargs: stops.append(True))

    assert server.recognize([b"image"]) == ["ok"]
    assert len(calls) == 2
    assert len(stops) == 1


def test_windows_ocr_server_cleans_up_failed_start(monkeypatch):
    server = WindowsOcrServer()
    stops = []
    monkeypatch.setattr(
        server, "_ensure_started",
        lambda: (_ for _ in ()).throw(RuntimeError("startup failed")),
    )
    monkeypatch.setattr(server, "_stop_process", lambda **_kwargs: stops.append(True))

    with pytest.raises(RuntimeError, match="startup failed"):
        server.start()

    assert stops == [True]


def test_unknown_ocr_engine_is_rejected_before_loading_image(tmp_path):
    with pytest.raises(ValueError, match="未対応のOCRエンジン"):
        probe.analyze_image(tmp_path / "missing.png", tmp_path / "output", ocr_engine="other")
