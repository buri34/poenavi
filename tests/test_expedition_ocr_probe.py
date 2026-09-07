from src.poetore.expedition_ocr_probe import (
    RowBand,
    analyze_directory,
    detect_reward_cards,
    detect_row_bands,
    normalize_text,
    otsu_threshold,
    score_rows,
)


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


def test_analyze_empty_directory_writes_empty_summary(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    assert analyze_directory(input_dir, output_dir, prepare_only=True) == []
    assert (output_dir / "summary.json").read_text(encoding="utf-8") == "[]\n"
