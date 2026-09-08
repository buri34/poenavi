"""Small, offline OCR benchmark for PoE2 Expedition reward screenshots."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

from PySide6.QtGui import QImage

OCR_ENGINES = ("tesseract", "windows")


@dataclass(frozen=True)
class RowBand:
    top: int
    bottom: int


@dataclass(frozen=True)
class OcrRowResult:
    row: int
    top: int
    bottom: int
    raw_text: str
    normalized_text: str
    quantity_text: str = ""
    quantity: int | None = None
    item_ocr_text: str = ""
    matched_item_name: str = ""
    match_score: float | None = None
    match_margin: float | None = None
    trusted: bool = False


def normalize_text(text: str) -> str:
    text = text.casefold().replace("×", "x")
    text = re.sub(r"[^\w\sぁ-んァ-ヶ一-龯ーx]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_quantity(text: str) -> tuple[int | None, str]:
    """Split a leading Expedition stack count from an OCR string."""
    normalized = normalize_text(text)
    quantity = parse_quantity_ocr(text)
    if quantity is None:
        return None, normalized

    # Windows OCR recognizes the narrow multiplication glyph reliably as a
    # separator position, but often calls it comma or equals.  The count itself
    # remains a leading number.  It also commonly reads "1x" as "lx".
    without_prefix = re.sub(
        r"^\s*[|\u3001\u3002'\"′・]*\s*(?:\d{1,3}\s*(?:[xX×,=，＝])|[lI|]\s*[xX×]|ⅸ)\s*",
        "",
        text,
        count=1,
    )
    return quantity, normalize_text(without_prefix)


def _candidate_key(text: str) -> str:
    text = normalize_text(text)
    text = re.sub(r"^(?:スキルレベル\s*\d+|スキル|サポート)\s*[:：]\s*", "", text)
    text = re.sub(r"\s*\(レベル\s*\d+\)\s*$", "", text)
    return text.replace(" ", "")


def match_item_name(
    text: str,
    candidates: Sequence[str],
    *,
    minimum_score: float = 0.72,
    minimum_margin: float = 0.06,
) -> tuple[str, float | None, float | None, bool]:
    """Return the best dictionary candidate and a conservative trust decision."""
    key = _candidate_key(text)
    if not key or not candidates:
        return "", None, None, False
    scored = sorted(
        (
            (SequenceMatcher(None, key, _candidate_key(candidate)).ratio(), candidate)
            for candidate in candidates
            if _candidate_key(candidate)
        ),
        reverse=True,
    )
    best_score, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = best_score - second_score
    trusted = best_score >= minimum_score and (best_score == 1.0 or margin >= minimum_margin)
    # A noisy read of e.g. "カオスオーブ (上級)" must not silently become the
    # unqualified base currency.  Require a nearly exact read when the chosen
    # base has parenthesized variants in the dictionary.
    best_key = _candidate_key(best)
    has_qualified_variant = any(
        candidate != best
        and _candidate_key(candidate).startswith(best_key)
        and "(" in candidate
        for candidate in candidates
    )
    if has_qualified_variant and "(" not in text and best_score < 0.95:
        trusted = False
    return best, best_score, margin, trusted


def load_item_dictionary(path: Path) -> list[str]:
    """Load Japanese item names from a Trade API items response."""
    loaded = json.loads(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for group in loaded.get("result", []):
        for entry in group.get("entries", []):
            for field in ("type", "name"):
                value = entry.get(field)
                if isinstance(value, str) and value.strip():
                    names.add(value.strip())
    return sorted(names)


def write_results_csv(results: Sequence[dict[str, object]], path: Path) -> None:
    """Write a flat row list without source-image identifiers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "row",
        "item_name",
        "trusted",
        "quantity",
        "ocr_item_text",
        "ocr_raw_text",
        "match_score",
        "match_margin",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        flat_index = 0
        for result in results:
            for row in result.get("rows", []):
                flat_index += 1
                writer.writerow(
                    {
                        "row": flat_index,
                        "item_name": row.get("matched_item_name", "") if row.get("trusted") else "",
                        "trusted": "yes" if row.get("trusted") else "no",
                        "quantity": row.get("quantity") or "",
                        "ocr_item_text": row.get("item_ocr_text", ""),
                        "ocr_raw_text": row.get("raw_text", ""),
                        "match_score": row.get("match_score") if row.get("match_score") is not None else "",
                        "match_margin": row.get("match_margin") if row.get("match_margin") is not None else "",
                    }
                )


def otsu_threshold(gray: Sequence[int]) -> int:
    if not gray:
        return 127
    histogram = [0] * 256
    for value in gray:
        histogram[max(0, min(255, int(value)))] += 1
    total = len(gray)
    total_sum = sum(index * count for index, count in enumerate(histogram))
    background_weight = 0
    background_sum = 0
    best_variance = -1.0
    best_threshold = 127
    for threshold, count in enumerate(histogram):
        background_weight += count
        if background_weight == 0:
            continue
        foreground_weight = total - background_weight
        if foreground_weight == 0:
            break
        background_sum += threshold * count
        background_mean = background_sum / background_weight
        foreground_mean = (total_sum - background_sum) / foreground_weight
        variance = background_weight * foreground_weight * (background_mean - foreground_mean) ** 2
        if variance > best_variance:
            best_variance = variance
            best_threshold = threshold
    return best_threshold


def detect_row_bands(
    binary: Sequence[int],
    width: int,
    height: int,
    *,
    min_ink_ratio: float = 0.012,
    max_blank_gap: int = 4,
    min_height: int = 5,
    padding: int = 4,
) -> list[RowBand]:
    if width <= 0 or height <= 0 or len(binary) != width * height:
        return []
    minimum_ink = max(2, round(width * min_ink_ratio))
    active = [
        sum(binary[y * width : (y + 1) * width]) >= minimum_ink
        for y in range(height)
    ]
    raw: list[tuple[int, int]] = []
    start: int | None = None
    last_active = -1
    for y, is_active in enumerate(active):
        if is_active:
            if start is None:
                start = y
            last_active = y
        elif start is not None and y - last_active > max_blank_gap:
            if last_active - start + 1 >= min_height:
                raw.append((start, last_active))
            start = None
    if start is not None and last_active - start + 1 >= min_height:
        raw.append((start, last_active))
    return [RowBand(max(0, top - padding), min(height, bottom + padding + 1)) for top, bottom in raw]


def detect_reward_cards(
    gray: Sequence[int],
    red: Sequence[int],
    green: Sequence[int],
    blue: Sequence[int],
    width: int,
    height: int,
    *,
    minimum_row_fill: float = 0.45,
) -> tuple[int, list[RowBand]]:
    """Detect the pale reward cards before looking for dark text.

    The Expedition panel is anchored at the left edge.  Limiting the scan width
    prevents a full-screen capture's game world from affecting row detection.
    """
    if width <= 0 or height <= 0 or any(
        len(channel) != width * height for channel in (gray, red, green, blue)
    ):
        return 0, []
    # Narrow panel crops can also be very wide when only a few rewards exist.
    # Actual game captures are substantially larger than the panel itself.
    is_full_screen = width >= 1000 and width / height > 1.5
    scan_width = round(height * 0.55) if is_full_screen else width
    row_fill: list[float] = []
    for y in range(height):
        pale = 0
        offset = y * width
        for x in range(scan_width):
            index = offset + x
            spread = max(red[index], green[index], blue[index]) - min(
                red[index], green[index], blue[index]
            )
            if gray[index] > 115 and spread < 100:
                pale += 1
        row_fill.append(pale / scan_width)
    active = [value > minimum_row_fill for value in row_fill]

    candidates: list[RowBand] = []
    start: int | None = None
    for y, is_active in enumerate(active + [False]):
        if is_active and start is None:
            start = y
        elif not is_active and start is not None:
            if y - start >= 8:
                candidates.append(RowBand(start, y))
            start = None
    if not candidates:
        return scan_width, []

    tall_heights = sorted(band.bottom - band.top for band in candidates if band.bottom - band.top >= 30)
    if not tall_heights:
        return scan_width, []
    typical_height = tall_heights[len(tall_heights) // 2]
    cards = [
        band
        for band in candidates
        if max(30, typical_height * 0.50)
        <= band.bottom - band.top
        <= typical_height * 2.10
    ]
    if is_full_screen:
        cards = [band for band in cards if band.top >= height * 0.12]
    elif (
        len(cards) >= 2
        and cards[0].top < height * 0.12
        and cards[1].top - cards[0].bottom < 7
    ):
        cards.pop(0)
    if len(cards) >= 2:
        fill_rates = [
            sum(row_fill[band.top : band.bottom]) / (band.bottom - band.top)
            for band in cards
        ]
        typical_fill = sorted(fill_rates[1:])[len(fill_rates[1:]) // 2]
        first_gap = cards[1].top - cards[0].bottom
        later_gaps = sorted(
            cards[index + 1].top - cards[index].bottom for index in range(1, len(cards) - 1)
        )
        typical_gap = later_gaps[len(later_gaps) // 2] if later_gaps else first_gap
        if (
            first_gap > max(typical_gap * 1.5, typical_gap + 5)
            or fill_rates[0] < typical_fill * 0.8
        ):
            cards.pop(0)
    if len(cards) >= 3:
        gaps = [cards[index + 1].top - cards[index].bottom for index in range(len(cards) - 1)]
        positive_gaps = sorted(gap for gap in gaps if gap > 0)
        typical_gap = positive_gaps[len(positive_gaps) // 2] if positive_gaps else 0
        for index, gap in enumerate(gaps, start=1):
            if index >= 2 and (
                gap < max(5, typical_gap * 0.6)
                or gap > max(typical_gap * 3, typical_height * 1.5)
            ):
                cards = cards[:index]
                break
        typical_height = sorted(band.bottom - band.top for band in cards)[len(cards) // 2]
        cards = [
            band
            for index, band in enumerate(cards)
            if index < 2 or band.bottom - band.top <= typical_height * 1.5
        ]
    if (
        len(cards) == 2
        and cards[1].top - cards[0].bottom < 7
        and cards[0].bottom - cards[0].top > cards[1].bottom - cards[1].top
    ):
        cards.pop()
    return scan_width, cards


def score_rows(expected: Sequence[str], actual: Sequence[str]) -> dict[str, object]:
    expected_norm = [normalize_text(value) for value in expected]
    actual_norm = [normalize_text(value) for value in actual]
    pair_count = min(len(expected_norm), len(actual_norm))
    exact = sum(expected_norm[index] == actual_norm[index] for index in range(pair_count))
    similarities = [
        SequenceMatcher(None, expected_norm[index], actual_norm[index]).ratio()
        for index in range(pair_count)
    ]
    return {
        "expected_rows": len(expected_norm),
        "detected_rows": len(actual_norm),
        "exact_rows": exact,
        "exact_rate": exact / len(expected_norm) if expected_norm else None,
        "mean_similarity": sum(similarities) / len(similarities) if similarities else None,
    }


def _load_channels(path: Path) -> tuple[int, int, list[int], list[int], list[int], list[int]]:
    image = QImage(str(path))
    if image.isNull():
        raise ValueError(f"画像を読み込めません: {path}")
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    width, height = image.width(), image.height()
    gray: list[int] = []
    red: list[int] = []
    green: list[int] = []
    blue: list[int] = []
    for y in range(height):
        for x in range(width):
            color = image.pixelColor(x, y)
            red.append(color.red())
            green.append(color.green())
            blue.append(color.blue())
            gray.append(round(0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()))
    return width, height, gray, red, green, blue


def _write_pgm(path: Path, width: int, height: int, pixels: Sequence[int]) -> None:
    path.write_bytes(f"P5\n{width} {height}\n255\n".encode("ascii") + bytes(pixels))


def _write_grayscale_png(path: Path, width: int, height: int, pixels: Sequence[int]) -> None:
    image = QImage(bytes(pixels), width, height, width, QImage.Format.Format_Grayscale8).copy()
    if not image.save(str(path), "PNG"):
        raise RuntimeError(f"OCR用PNGを保存できません: {path}")


def _crop_pixels(
    pixels: Sequence[int], width: int, band: RowBand, left: int, right: int
) -> list[int]:
    cropped: list[int] = []
    for y in range(band.top, band.bottom):
        cropped.extend(pixels[y * width + left : y * width + right])
    return cropped


def _scale_pixels(pixels: Sequence[int], width: int, height: int, factor: int) -> list[int]:
    scaled: list[int] = []
    for y in range(height):
        row: list[int] = []
        for value in pixels[y * width : (y + 1) * width]:
            row.extend([value] * factor)
        for _ in range(factor):
            scaled.extend(row)
    return scaled


def _add_margin(pixels: Sequence[int], width: int, height: int, margin: int) -> list[int]:
    output = [0] * ((width + margin * 2) * margin)
    for y in range(height):
        output.extend([0] * margin)
        output.extend(pixels[y * width : (y + 1) * width])
        output.extend([0] * margin)
    output.extend([0] * ((width + margin * 2) * margin))
    return output


def _run_tesseract(
    image: Path,
    language: str,
    *,
    page_segmentation: int = 7,
    whitelist: str | None = None,
) -> str:
    executable = shutil.which("tesseract")
    if executable is None:
        raise RuntimeError("tesseractが見つかりません。--prepare-onlyで前処理だけ実行できます。")
    command = [
        executable,
        str(image),
        "stdout",
        "-l",
        language,
        "--psm",
        str(page_segmentation),
    ]
    if whitelist:
        command.extend(["-c", f"tessedit_char_whitelist={whitelist}"])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"tesseract終了コード: {result.returncode}")
    return result.stdout.strip()


def _windows_ocr_helper() -> Path:
    configured = os.environ.get("POENAVI_WINDOWS_OCR_HELPER")
    if configured:
        helper = Path(configured)
        if helper.is_file():
            return helper
        raise RuntimeError(f"Windows OCRヘルパーが見つかりません: {helper}")
    packaged = (
        Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
        / "tools"
        / "ExpeditionWindowsOcr"
        / "ExpeditionWindowsOcr.exe"
    )
    if packaged.exists():
        return packaged
    helper = (
        Path(__file__).resolve().parents[2]
        / "tools"
        / "ExpeditionWindowsOcr"
        / "bin"
        / "Release"
        / "net8.0-windows10.0.19041.0"
        / "ExpeditionWindowsOcr.dll"
    )
    if helper.exists():
        return helper
    raise RuntimeError(
        "Windows OCRヘルパーが未ビルドです。"
        "scripts\\run_expedition_windows_ocr.ps1を使って実行してください。"
    )


def _windows_ocr_command(helper: Path) -> list[str]:
    if helper.suffix.casefold() == ".exe":
        return [str(helper)]
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise RuntimeError("dotnetが見つかりません。.NET 8 SDKをインストールしてください。")
    return [dotnet, str(helper)]


def windows_ocr_available(language: str = "ja-JP") -> bool:
    if sys.platform != "win32":
        return False
    helper = _windows_ocr_helper()
    result = subprocess.run(
        [*_windows_ocr_command(helper), "--check", language],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result.returncode == 0


def run_windows_ocr_batch(images: Sequence[Path], language: str = "ja-JP") -> list[str]:
    if sys.platform != "win32":
        raise RuntimeError("Windows標準OCRはWindows上でのみ実行できます。")
    if not images:
        return []
    helper = _windows_ocr_helper()
    result = subprocess.run(
        [
            *_windows_ocr_command(helper), "--batch", language,
            *(str(image.resolve()) for image in images),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        if result.returncode == 3:
            raise RuntimeError(
                "Windowsの日本語OCRがありません。Windows設定の「言語と地域」で日本語のOCRを追加してください。"
            )
        raise RuntimeError(result.stderr.strip() or f"Windows OCR終了コード: {result.returncode}")
    loaded = json.loads(result.stdout)
    if not isinstance(loaded, list) or len(loaded) != len(images):
        raise RuntimeError("Windows OCRの一括処理結果が不正です。")
    return [str(value) for value in loaded]


def _run_windows_ocr(image: Path, language: str) -> str:
    if sys.platform != "win32":
        raise RuntimeError("Windows標準OCRはWindows上でのみ実行できます。")
    helper = _windows_ocr_helper()
    result = subprocess.run(
        [*_windows_ocr_command(helper), str(image.resolve()), language],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Windows OCR終了コード: {result.returncode}")
    return result.stdout.strip()


def parse_quantity_ocr(text: str) -> int | None:
    """Read only a leading Expedition stack marker from noisy Windows OCR.

    Observed Windows.Media.Ocr output turns the visual multiplication sign into
    ``x``, comma, or equals, and turns ``1x`` into ``lx`` or ``IX``.  Requiring
    the marker at the beginning avoids treating gem levels and item names as a
    stack count.
    """
    compact = re.sub(r"\s+", "", text).replace("×", "x").replace("X", "x")
    compact = re.sub(r"^[|、。'\"′・]+", "", compact)
    match = re.match(r"(\d{1,3})(?:x|,|=|，|＝)", compact)
    if match:
        return int(match.group(1))
    if re.match(r"(?:[lI|]x|ⅸ)", compact, re.IGNORECASE):
        return 1
    return None


def analyze_image(
    image_path: Path,
    output_dir: Path,
    *,
    language: str = "jpn+eng",
    ocr_engine: str = "tesseract",
    prepare_only: bool = False,
    item_dictionary: Sequence[str] = (),
) -> dict[str, object]:
    if ocr_engine not in OCR_ENGINES:
        raise ValueError(f"未対応のOCRエンジンです: {ocr_engine}")
    width, height, gray, red, green, blue = _load_channels(image_path)
    panel_width, bands = detect_reward_cards(gray, red, green, blue, width, height)
    image_output = output_dir / image_path.stem
    image_output.mkdir(parents=True, exist_ok=True)
    # Rune icons occupy roughly the left 40%; excluding them markedly improves
    # single-line OCR and still retains the longest right-aligned reward name.
    text_left = round(panel_width * 0.40)
    text_right = panel_width

    rows: list[OcrRowResult] = []
    for index, band in enumerate(bands, start=1):
        crop_gray = _crop_pixels(gray, width, band, text_left, text_right)
        threshold = otsu_threshold(crop_gray)
        crop = [1 if value <= threshold else 0 for value in crop_gray]
        crop_width = text_right - text_left
        crop_height = band.bottom - band.top
        border = max(2, round(crop_height * 0.12))
        for y in range(crop_height):
            for x in range(crop_width):
                if y < border or y >= crop_height - border or x >= crop_width - border:
                    crop[y * crop_width + x] = 0
        scale = 3
        crop = _scale_pixels(crop, crop_width, crop_height, scale)
        margin = 12
        crop = _add_margin(crop, crop_width * scale, crop_height * scale, margin)
        crop_path = image_output / f"row_{index:02d}.png"
        _write_grayscale_png(
            crop_path,
            crop_width * scale + margin * 2,
            crop_height * scale + margin * 2,
            [0 if value else 255 for value in crop],
        )
        psm = 11 if crop_height > 70 else 7
        if prepare_only:
            raw = ""
        elif ocr_engine == "windows":
            raw = _run_windows_ocr(crop_path, language)
        else:
            raw = _run_tesseract(crop_path, language, page_segmentation=psm)
        inline_quantity, item_text = strip_quantity(raw)
        if prepare_only:
            quantity_raw = ""
        elif ocr_engine == "windows":
            quantity_raw = raw
        else:
            quantity_raw = _run_tesseract(
                crop_path,
                "eng",
                page_segmentation=7,
                whitelist="0123456789xX",
            )
        quantity = parse_quantity_ocr(quantity_raw) or inline_quantity
        best, match_score, match_margin, trusted = match_item_name(item_text, item_dictionary)
        rows.append(
            OcrRowResult(
                index,
                band.top,
                band.bottom,
                raw,
                normalize_text(raw),
                quantity_text=quantity_raw,
                quantity=quantity,
                item_ocr_text=item_text,
                matched_item_name=best,
                match_score=match_score,
                match_margin=match_margin,
                trusted=trusted,
            )
        )

    truth_path = image_path.with_suffix(".truth.json")
    expected: list[str] | None = None
    score: dict[str, object] | None = None
    if truth_path.exists():
        loaded = json.loads(truth_path.read_text(encoding="utf-8"))
        expected = loaded["rows"] if isinstance(loaded, dict) else loaded
        score = score_rows(expected, [row.raw_text for row in rows])

    result: dict[str, object] = {
        "image": image_path.name,
        "width": width,
        "height": height,
        "panel_width": panel_width,
        "language": language,
        "ocr_engine": ocr_engine,
        "prepare_only": prepare_only,
        "rows": [asdict(row) for row in rows],
        "expected": expected,
        "score": score,
    }
    (image_output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def analyze_directory(
    input_dir: Path,
    output_dir: Path,
    *,
    language: str = "jpn+eng",
    ocr_engine: str = "tesseract",
    prepare_only: bool = False,
    item_dictionary: Sequence[str] = (),
    csv_path: Path | None = None,
) -> list[dict[str, object]]:
    images = sorted(path for path in input_dir.iterdir() if path.suffix.casefold() in {".png", ".jpg", ".jpeg"})
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [
        analyze_image(
            path,
            output_dir,
            language=language,
            ocr_engine=ocr_engine,
            prepare_only=prepare_only,
            item_dictionary=item_dictionary,
        )
        for path in images
    ]
    (output_dir / "summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_results_csv(results, csv_path or output_dir / "items.csv")
    return results
