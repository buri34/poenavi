from src.poetore.expedition_ocr_probe import (
    RowBand,
    analyze_directory,
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


def test_analyze_empty_directory_writes_empty_summary(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    assert analyze_directory(input_dir, output_dir, prepare_only=True) == []
    assert (output_dir / "summary.json").read_text(encoding="utf-8") == "[]\n"
