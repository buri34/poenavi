import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QColor, QImage

import src.poetore.expedition_ocr_probe as probe
from src.poetore.expedition_ocr_probe import (
    RowBand,
    WindowsOcrServer,
    analyze_directory,
    detect_reward_cards,
    detect_row_bands,
    load_item_dictionary,
    match_item_name,
    normalize_text,
    otsu_threshold,
    parse_quantity_ocr,
    prepare_qimage_rows,
    score_rows,
    strip_quantity,
    write_results_csv,
)


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


def test_prepare_qimage_rows_can_limit_panel_scan_width():
    image = QImage(220, 100, QImage.Format.Format_RGB888)
    image.fill(QColor(50, 50, 50))
    for y in range(20, 60):
        for x in range(60):
            image.setPixelColor(x, y, QColor(200, 200, 200))

    prepared = prepare_qimage_rows(image, scan_width=60)

    assert prepared.panel_width == 60
    assert prepared.bands == (RowBand(20, 60),)


def test_prepare_qimage_rows_preserves_full_screen_header_filter_after_crop():
    image = QImage(220, 180, QImage.Format.Format_RGB888)
    image.fill(QColor(50, 50, 50))
    for top, bottom in ((10, 40), (65, 105), (112, 152)):
        for y in range(top, bottom):
            for x in range(100):
                image.setPixelColor(x, y, QColor(200, 200, 200))

    prepared = prepare_qimage_rows(
        image, scan_width=100, full_screen=True,
    )

    assert prepared.bands == (RowBand(65, 105), RowBand(112, 152))


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
