"""Small, offline OCR benchmark for PoE2 Expedition reward screenshots."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

from PySide6.QtGui import QImage


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


def normalize_text(text: str) -> str:
    text = text.casefold().replace("×", "x")
    text = re.sub(r"[^\w\sぁ-んァ-ヶ一-龯ーx]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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


def _load_grayscale(path: Path) -> tuple[int, int, list[int]]:
    image = QImage(str(path))
    if image.isNull():
        raise ValueError(f"画像を読み込めません: {path}")
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    width, height = image.width(), image.height()
    gray: list[int] = []
    for y in range(height):
        for x in range(width):
            color = image.pixelColor(x, y)
            gray.append(round(0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()))
    return width, height, gray


def _write_pgm(path: Path, width: int, height: int, pixels: Sequence[int]) -> None:
    path.write_bytes(f"P5\n{width} {height}\n255\n".encode("ascii") + bytes(pixels))


def _crop_pixels(pixels: Sequence[int], width: int, band: RowBand) -> list[int]:
    return list(pixels[band.top * width : band.bottom * width])


def _run_tesseract(image: Path, language: str) -> str:
    executable = shutil.which("tesseract")
    if executable is None:
        raise RuntimeError("tesseractが見つかりません。--prepare-onlyで前処理だけ実行できます。")
    command = [executable, str(image), "stdout", "-l", language, "--psm", "7"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"tesseract終了コード: {result.returncode}")
    return result.stdout.strip()


def analyze_image(
    image_path: Path,
    output_dir: Path,
    *,
    language: str = "jpn+eng",
    prepare_only: bool = False,
) -> dict[str, object]:
    width, height, gray = _load_grayscale(image_path)
    threshold = otsu_threshold(gray)
    dark_ink = [1 if value <= threshold else 0 for value in gray]
    bands = detect_row_bands(dark_ink, width, height)
    image_output = output_dir / image_path.stem
    image_output.mkdir(parents=True, exist_ok=True)
    _write_pgm(image_output / "binary.pgm", width, height, [0 if value else 255 for value in dark_ink])

    rows: list[OcrRowResult] = []
    for index, band in enumerate(bands, start=1):
        crop = _crop_pixels(dark_ink, width, band)
        crop_path = image_output / f"row_{index:02d}.pgm"
        _write_pgm(crop_path, width, band.bottom - band.top, [0 if value else 255 for value in crop])
        raw = "" if prepare_only else _run_tesseract(crop_path, language)
        rows.append(OcrRowResult(index, band.top, band.bottom, raw, normalize_text(raw)))

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
        "otsu_threshold": threshold,
        "language": language,
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
    prepare_only: bool = False,
) -> list[dict[str, object]]:
    images = sorted(path for path in input_dir.iterdir() if path.suffix.casefold() in {".png", ".jpg", ".jpeg"})
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [
        analyze_image(path, output_dir, language=language, prepare_only=prepare_only)
        for path in images
    ]
    (output_dir / "summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return results
