"""Small, offline OCR benchmark for PoE2 Expedition reward screenshots."""

from __future__ import annotations

import base64
import csv
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage

OCR_ENGINES = ("tesseract", "windows")
OCR_MAX_IMAGE_DIMENSION = 2400
OCR_TARGET_TEXT_HEIGHT = 96
OCR_RETRY_LARGE_TEXT_HEIGHT = 120
_EXACT_OCR_KEY_CORRECTIONS = {
    "高員なオーブ": "高貴なオーブ",
    "サカワルの浸良のルーン一": "サカワルの浸食のルーン",
    "スルードのカ": "スルードの力",
}


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


@dataclass(frozen=True)
class PreparedOcrFrame:
    width: int
    height: int
    panel_width: int
    bands: tuple[RowBand, ...]
    images: tuple[bytes, ...]
    gray: bytes = b""


def normalize_text(text: str) -> str:
    text = text.casefold().replace("×", "x")
    text = re.sub(r"[^\w\sぁ-んァ-ヶ一-龯ーx]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_quantity(text: str) -> tuple[int | None, str]:
    """Split the first Expedition stack marker from a noisy OCR string."""
    normalized = normalize_text(text)
    marker = _quantity_marker(text)
    if marker is None:
        return None, normalized
    quantity, end = marker
    return quantity, normalize_text(text[end:])


def reward_text_candidates(text: str) -> tuple[str, ...]:
    """Return quantity-anchored and per-line reward-name candidates in priority order."""
    lines = [line for line in re.split(r"[\r\n]+", text) if line.strip()]
    sources = [*lines, text]
    candidates: list[str] = []
    for source in sources:
        marker = _quantity_marker(source)
        if marker is not None:
            candidate = normalize_text(source[marker[1]:])
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    for source in lines:
        candidate = normalize_text(source)
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    normalized = normalize_text(text)
    if normalized and normalized not in candidates:
        candidates.append(normalized)
    return tuple(candidates)


def _quantity_marker(text: str) -> tuple[int, int] | None:
    pattern = re.compile(
        r"(?:^|\s|[|、。'\"′・])"
        r"(?:(?P<count>\d{1,3})\s*(?:[xX×,=，＝])|(?P<one>[lI|]\s*[xX×]|ⅸ))\s*",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match is None:
        return None
    return (int(match.group("count")) if match.group("count") else 1, match.end())


def _candidate_key(text: str) -> str:
    text = normalize_text(text)
    text = re.sub(r"^(?:スキルレベル\s*\d+|スキル|サポート)\s*[:：]\s*", "", text)
    text = re.sub(r"\s*\(レベル\s*\d+\)\s*$", "", text)
    return text.replace(" ", "")


def _level_number(text: str) -> int | None:
    match = re.search(r"レベル(\d+)", normalize_text(text).replace(" ", ""))
    return int(match.group(1)) if match else None


def match_item_name(
    text: str,
    candidates: Sequence[str],
    *,
    minimum_score: float = 0.72,
    minimum_margin: float = 0.06,
) -> tuple[str, float | None, float | None, bool]:
    """Return the best dictionary candidate and a conservative trust decision."""
    key = _candidate_key(text)
    key = _EXACT_OCR_KEY_CORRECTIONS.get(key, key)
    if not key or not candidates:
        return "", None, None, False
    observed_level = _level_number(text)
    level_candidates = [
        candidate for candidate in candidates
        if _level_number(candidate) == observed_level
    ]
    if observed_level is not None:
        candidates = level_candidates
        if not candidates:
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
    best_level = _level_number(best)
    if (
        observed_level is not None
        and observed_level == best_level
        and best_score >= max(minimum_score, 0.85)
    ):
        trusted = True
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
    has_level_variant = any(
        candidate != best
        and _candidate_key(candidate) == best_key
        and _level_number(candidate) is not None
        for candidate in candidates
    )
    if observed_level is None and (best_level is not None or has_level_variant):
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
) -> tuple[int, list[RowBand]]:
    """Detect reward-card bands inside a user-selected panel-inner rectangle."""
    if width <= 0 or height <= 0 or any(
        len(channel) != width * height for channel in (gray, red, green, blue)
    ):
        return 0, []
    scan_width = width
    row_scores: list[int] = []
    for y in range(height):
        offset = y * width
        values = sorted(gray[offset : offset + scan_width])
        row_scores.append(values[(len(values) - 1) // 2])
    threshold = otsu_threshold(row_scores)
    active = [value > threshold for value in row_scores]

    candidates: list[RowBand] = []
    start: int | None = None
    for y, is_active in enumerate(active + [False]):
        if is_active and start is None:
            start = y
        elif not is_active and start is not None:
            if y > start:
                candidates.append(RowBand(start, y))
            start = None
    if not candidates:
        return scan_width, []
    candidates = [band for band in candidates if band.bottom < height]
    if not candidates:
        return scan_width, []

    merge_gap = max(1, round(scan_width * 0.002))
    merged_candidates: list[RowBand] = []
    for band in candidates:
        if merged_candidates and band.top - merged_candidates[-1].bottom <= merge_gap:
            merged_candidates[-1] = RowBand(merged_candidates[-1].top, band.bottom)
        else:
            merged_candidates.append(band)
    candidates = merged_candidates
    heights = sorted(band.bottom - band.top for band in candidates)
    typical_height = heights[len(heights) // 2]
    candidates = [
        band for band in candidates
        if band.bottom - band.top >= max(1, typical_height * 0.10)
    ]
    joined_candidates: list[RowBand] = []
    index = 0
    while index < len(candidates):
        current = candidates[index]
        if index + 1 < len(candidates):
            following = candidates[index + 1]
            gap = following.top - current.bottom
            current_height = current.bottom - current.top
            following_height = following.bottom - following.top
            if (
                current_height < typical_height * 0.60
                and following_height < typical_height * 0.60
                and gap <= typical_height * 0.08
            ):
                joined_candidates.append(RowBand(current.top, following.bottom))
                index += 2
                continue
        joined_candidates.append(current)
        index += 1
    candidates = joined_candidates
    heights = sorted(band.bottom - band.top for band in candidates)
    typical_height = heights[len(heights) // 2]
    minimum_height = max(2, round(typical_height * 0.45))
    return scan_width, [
        band for band in candidates if band.bottom - band.top >= minimum_height
    ]


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


def _packed_image_bytes(image: QImage, bytes_per_pixel: int) -> bytes:
    """Return tightly packed image bytes without per-pixel Qt calls."""
    width = image.width()
    height = image.height()
    packed_stride = width * bytes_per_pixel
    source_stride = image.bytesPerLine()
    source = bytes(image.constBits())
    if source_stride == packed_stride:
        return source
    return b"".join(
        source[offset : offset + packed_stride]
        for offset in range(0, source_stride * height, source_stride)
    )


def _image_channels(image: QImage) -> tuple[int, int, bytes, bytes, bytes, bytes]:
    if image.isNull():
        raise ValueError("画像を読み込めません。")
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    width, height = image.width(), image.height()
    rgb = _packed_image_bytes(image, 3)
    red = rgb[0::3]
    green = rgb[1::3]
    blue = rgb[2::3]
    # Preserve the benchmarked detector's original luminance values exactly.
    # The Qt Grayscale8 conversion uses different weights and can create false
    # reward-card bands near the threshold.
    gray = bytes(
        round(0.299 * red_value + 0.587 * green_value + 0.114 * blue_value)
        for red_value, green_value, blue_value in zip(red, green, blue)
    )
    return width, height, gray, red, green, blue


def detect_qimage_reward_cards(image: QImage) -> tuple[int, list[RowBand]]:
    """Detect card bands from an already-cropped panel-inner image."""
    if image.isNull():
        return 0, []
    width, height, gray, red, green, blue = _image_channels(image)
    return detect_reward_cards(gray, red, green, blue, width, height)


def expedition_panel_diagnostics(image: QImage) -> dict[str, object]:
    """Return sanitized structural metrics used by the shared OCR router."""
    result: dict[str, object] = {
        "image_width": image.width(),
        "image_height": image.height(),
        "probe_width": 0,
        "probe_height": 0,
        "panel_width": 0,
        "band_count": 0,
        "min_band_height": 0,
        "matched": False,
    }
    if image.isNull() or image.width() < 160 or image.height() < 100:
        return result
    probe = (
        image.scaledToWidth(300, Qt.FastTransformation)
        if image.width() > 300 else image
    )
    panel_width, bands = detect_qimage_reward_cards(probe)
    heights = [band.bottom - band.top for band in bands]
    result.update({
        "probe_width": probe.width(),
        "probe_height": probe.height(),
        "panel_width": panel_width,
        "band_count": len(bands),
        "min_band_height": min(heights, default=0),
        "matched": (
            1 <= len(bands) <= 12
            and panel_width >= max(80, round(probe.width() * 0.45))
            and min(heights, default=0) >= 10
        ),
    })
    return result


def looks_like_expedition_panel(image: QImage) -> bool:
    """Return whether a registered crop contains plausible reward-card rows."""
    return bool(expedition_panel_diagnostics(image)["matched"])


def _load_channels(path: Path) -> tuple[int, int, bytes, bytes, bytes, bytes]:
    image = QImage(str(path))
    if image.isNull():
        raise ValueError(f"画像を読み込めません: {path}")
    return _image_channels(image)


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


def _adaptive_dark_foreground(
    gray: Sequence[int], width: int, height: int, *, radius: int = 8, offset: int = 10,
) -> list[int]:
    """Return dark text using each pixel's local background brightness."""
    stride = width + 1
    integral = [0] * (stride * (height + 1))
    for y in range(height):
        row_total = 0
        source_offset = y * width
        integral_offset = (y + 1) * stride
        previous_offset = y * stride
        for x in range(width):
            row_total += gray[source_offset + x]
            integral[integral_offset + x + 1] = (
                integral[previous_offset + x + 1] + row_total
            )

    binary = [0] * (width * height)
    for y in range(height):
        top = max(0, y - radius)
        bottom = min(height, y + radius + 1)
        for x in range(width):
            left = max(0, x - radius)
            right = min(width, x + radius + 1)
            total = (
                integral[bottom * stride + right]
                - integral[top * stride + right]
                - integral[bottom * stride + left]
                + integral[top * stride + left]
            )
            local_mean = total / ((right - left) * (bottom - top))
            if gray[y * width + x] <= local_mean - offset:
                binary[y * width + x] = 1
    return binary


def _clear_row_image_border(binary: list[int], width: int, height: int) -> None:
    border = max(2, round(height * 0.12))
    for y in range(height):
        for x in range(width):
            if y < border or y >= height - border or x >= width - border:
                binary[y * width + x] = 0


def _mask_likely_rune_icons(binary: list[int], width: int, height: int) -> None:
    """Remove square icon components while preserving smaller text glyphs."""
    if width <= 0 or height <= 0:
        return
    tall_card = height > width * 0.12
    minimum_side = max(4, round(height * (0.25 if tall_card else 0.55)))
    maximum_side = max(minimum_side, round(height * 0.95))
    visited = bytearray(width * height)
    components: list[tuple[int, int, int, int]] = []
    for start in range(width * height):
        if not binary[start] or visited[start]:
            continue
        visited[start] = 1
        pending = deque([start])
        min_x = max_x = start % width
        min_y = max_y = start // width
        pixels = 0
        while pending:
            index = pending.popleft()
            pixels += 1
            x = index % width
            y = index // width
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            for neighbor in (index - 1, index + 1, index - width, index + width):
                if neighbor < 0 or neighbor >= width * height or visited[neighbor]:
                    continue
                neighbor_x = neighbor % width
                if abs(neighbor_x - x) > 1 or not binary[neighbor]:
                    continue
                visited[neighbor] = 1
                pending.append(neighbor)
        component_width = max_x - min_x + 1
        component_height = max_y - min_y + 1
        if not (
            minimum_side <= component_width <= maximum_side
            and minimum_side <= component_height <= maximum_side
            and 0.70 <= component_width / component_height <= 1.30
            and min_y < height * 0.65
            and pixels >= (component_width + component_height) * 0.6
        ):
            continue
        components.append((min_x, min_y, max_x, max_y))
    padding = max(1, round(height * 0.03))
    for min_x, min_y, max_x, max_y in components:
        for y in range(max(0, min_y - padding), min(height, max_y + padding + 1)):
            for x in range(max(0, min_x - padding), min(width, max_x + padding + 1)):
                binary[y * width + x] = 0


def _main_text_height(binary: Sequence[int], width: int, height: int) -> int:
    bands = detect_row_bands(
        binary,
        width,
        height,
        min_ink_ratio=0.01,
        max_blank_gap=1,
        min_height=3,
        padding=0,
    )
    return max((band.bottom - band.top for band in bands), default=max(1, height))


def _normalized_binary_image(
    binary: Sequence[int],
    width: int,
    height: int,
    *,
    target_text_height: int,
) -> QImage:
    text_height = _main_text_height(binary, width, height)
    margin = 12
    maximum_content_size = OCR_MAX_IMAGE_DIMENSION - margin * 2
    scale = max(0.1, min(
        12.0,
        target_text_height / max(1, text_height),
        maximum_content_size / max(1, width),
        maximum_content_size / max(1, height),
    ))
    source = QImage(
        bytes(0 if value else 255 for value in binary),
        width,
        height,
        width,
        QImage.Format.Format_Grayscale8,
    ).copy()
    output_width = max(1, round(width * scale))
    output_height = max(1, round(height * scale))
    scaled = source.scaled(
        output_width,
        output_height,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    packed = _packed_image_bytes(scaled, 1)
    final_width = output_width + margin * 2
    final_height = output_height + margin * 2
    output = bytearray([255]) * (final_width * final_height)
    for y in range(output_height):
        source_offset = y * output_width
        target_offset = (y + margin) * final_width + margin
        output[target_offset : target_offset + output_width] = packed[
            source_offset : source_offset + output_width
        ]
    return QImage(
        bytes(output),
        final_width,
        final_height,
        final_width,
        QImage.Format.Format_Grayscale8,
    ).copy()


def _prepare_row_image(
    gray: Sequence[int],
    width: int,
    band: RowBand,
    text_left: int,
    text_right: int,
    *,
    threshold_mode: str = "otsu",
    target_text_height: int = OCR_TARGET_TEXT_HEIGHT,
    mask_icons: bool = False,
) -> QImage:
    crop_gray = _crop_pixels(gray, width, band, text_left, text_right)
    crop_width = text_right - text_left
    crop_height = band.bottom - band.top
    if threshold_mode == "otsu":
        threshold = otsu_threshold(crop_gray)
        crop = [1 if value <= threshold else 0 for value in crop_gray]
    elif threshold_mode == "adaptive":
        crop = _adaptive_dark_foreground(crop_gray, crop_width, crop_height)
    else:
        raise ValueError(f"未対応のOCR二値化方式です: {threshold_mode}")
    _clear_row_image_border(crop, crop_width, crop_height)
    if mask_icons:
        _mask_likely_rune_icons(crop, crop_width, crop_height)
    active_columns = [
        x for x in range(crop_width)
        if any(crop[y * crop_width + x] for y in range(crop_height))
    ]
    if active_columns:
        margin = max(2, round(crop_height * 0.12))
        trim_left = max(0, active_columns[0] - margin)
        trim_right = min(crop_width, active_columns[-1] + margin + 1)
        crop = _crop_pixels(
            crop, crop_width, RowBand(0, crop_height), trim_left, trim_right,
        )
        crop_width = trim_right - trim_left
    return _normalized_binary_image(
        crop,
        crop_width,
        crop_height,
        target_text_height=target_text_height,
    )


def _image_bytes(image: QImage, image_format: str = "BMP") -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("OCR画像用メモリを開けませんでした。")
    try:
        if not image.save(buffer, image_format):
            raise RuntimeError("OCR画像をメモリへ変換できませんでした。")
    finally:
        buffer.close()
    return bytes(data)


def prepare_qimage_rows(image: QImage) -> PreparedOcrFrame:
    """Prepare Windows OCR row images without writing temporary files."""
    width, height, gray, red, green, blue = _image_channels(image)
    panel_width, bands = detect_reward_cards(
        gray, red, green, blue, width, height,
    )
    images = tuple(
        _image_bytes(_prepare_row_image(gray, width, band, 0, panel_width))
        for band in bands
    )
    return PreparedOcrFrame(
        width, height, panel_width, tuple(bands), images, gray,
    )


def prepare_retry_row_images(
    frame: PreparedOcrFrame,
    row_indices: Sequence[int],
) -> dict[int, tuple[bytes, bytes, bytes]]:
    """Build alternate OCR inputs only for rows unresolved by the primary pass."""
    if not frame.gray:
        raise ValueError("再OCR用の元画像データがありません。")
    retries: dict[int, tuple[bytes, bytes, bytes]] = {}
    for index in dict.fromkeys(row_indices):
        if index < 0 or index >= len(frame.bands):
            raise IndexError(f"報酬行番号が範囲外です: {index}")
        band = frame.bands[index]
        adaptive = _prepare_row_image(
            frame.gray,
            frame.width,
            band,
            0,
            frame.panel_width,
            threshold_mode="adaptive",
        )
        larger = _prepare_row_image(
            frame.gray,
            frame.width,
            band,
            0,
            frame.panel_width,
            target_text_height=OCR_RETRY_LARGE_TEXT_HEIGHT,
        )
        masked = _prepare_row_image(
            frame.gray,
            frame.width,
            band,
            0,
            frame.panel_width,
            threshold_mode="adaptive",
            mask_icons=True,
        )
        retries[index] = (
            _image_bytes(adaptive), _image_bytes(larger), _image_bytes(masked),
        )
    return retries


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


class WindowsOcrServer:
    """Long-lived Windows OCR helper using an in-memory request protocol."""

    def __init__(
        self,
        language: str = "ja-JP",
        *,
        startup_timeout: float = 15.0,
        request_timeout: float = 45.0,
    ):
        self.language = language
        self.startup_timeout = startup_timeout
        self.request_timeout = request_timeout
        self._lock = threading.Lock()
        self._process = None
        self._responses: queue.Queue[str | None] = queue.Queue()
        self._stderr: list[str] = []
        self._next_id = 0

    def start(self) -> None:
        with self._lock:
            try:
                self._ensure_started()
            except Exception:
                self._stop_process()
                raise

    def recognize(self, images: Sequence[bytes]) -> list[str]:
        if not images:
            return []
        with self._lock:
            last_error: Exception | None = None
            for attempt in range(2):
                try:
                    return self._recognize_once(images)
                except Exception as exc:  # noqa: BLE001 - restart owned helper once
                    last_error = exc
                    self._stop_process()
                    if attempt:
                        break
            raise RuntimeError(str(last_error) if last_error else "Windows OCRに失敗しました。")

    def close(self) -> None:
        with self._lock:
            self._stop_process(graceful=True)

    def _ensure_started(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Windows標準OCRはWindows上でのみ実行できます。")
        if self._process is not None and self._process.poll() is None:
            return
        if self._process is not None:
            self._stop_process()
        helper = _windows_ocr_helper()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._responses = queue.Queue()
        self._stderr = []
        self._process = subprocess.Popen(
            [*_windows_ocr_command(helper), "--server", self.language],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=creationflags,
        )
        process = self._process
        responses = self._responses
        stderr = self._stderr
        threading.Thread(
            target=self._read_stdout, args=(process, responses), daemon=True,
        ).start()
        threading.Thread(
            target=self._read_stderr, args=(process, stderr), daemon=True,
        ).start()
        ready_line = self._wait_response(self.startup_timeout)
        try:
            ready = json.loads(ready_line)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Windows OCRヘルパーの起動応答が不正です。") from exc
        if not isinstance(ready, dict) or ready.get("ready") is not True:
            raise RuntimeError(str(ready.get("error") or "Windows OCRヘルパーを起動できません。"))

    def _recognize_once(self, images: Sequence[bytes]) -> list[str]:
        self._ensure_started()
        process = self._process
        if process is None or process.stdin is None:
            raise RuntimeError("Windows OCRヘルパーへ接続できません。")
        self._next_id += 1
        request_id = self._next_id
        request = {
            "Id": request_id,
            "Images": [base64.b64encode(image).decode("ascii") for image in images],
        }
        process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        process.stdin.flush()
        response_line = self._wait_response(self.request_timeout)
        try:
            response = json.loads(response_line)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Windows OCRヘルパーの処理応答が不正です。") from exc
        if not isinstance(response, dict):
            raise RuntimeError(  # noqa: TRY004 - malformed process protocol
                "Windows OCRヘルパーの処理応答が不正です。"
            )
        if response.get("error"):
            raise RuntimeError(str(response["error"]))
        texts = response.get("texts")
        if response.get("id") != request_id or not isinstance(texts, list):
            raise RuntimeError("Windows OCRヘルパーの処理順序が一致しません。")
        if len(texts) != len(images):
            raise RuntimeError("Windows OCRの一括処理結果が不正です。")
        return [str(value) for value in texts]

    def _wait_response(self, timeout: float) -> str:
        try:
            line = self._responses.get(timeout=timeout)
        except queue.Empty as exc:
            raise RuntimeError("Windows OCRヘルパーが時間内に応答しませんでした。") from exc
        if line is None:
            details = " ".join(self._stderr).strip()
            if self._process is not None and getattr(self._process, "returncode", None) == 3:
                raise RuntimeError(
                    "Windowsの日本語OCRがありません。Windows設定の「言語と地域」で"
                    "日本語のOCRを追加してください。"
                )
            raise RuntimeError(details or "Windows OCRヘルパーが終了しました。")
        return line

    @staticmethod
    def _read_stdout(process, responses: queue.Queue[str | None]) -> None:
        if process.stdout is not None:
            for line in process.stdout:
                responses.put(line.strip())
        responses.put(None)

    @staticmethod
    def _read_stderr(process, stderr: list[str]) -> None:
        if process.stderr is not None:
            for line in process.stderr:
                stderr.append(line.strip())

    def _stop_process(self, *, graceful: bool = False) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.poll() is None and graceful and process.stdin is not None:
            try:
                process.stdin.write('{"Command":"shutdown"}\n')
                process.stdin.flush()
                process.wait(timeout=2)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


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
    text_left = 0
    text_right = panel_width

    rows: list[OcrRowResult] = []
    for index, band in enumerate(bands, start=1):
        crop_height = band.bottom - band.top
        prepared_image = _prepare_row_image(
            gray, width, band, text_left, text_right,
        )
        crop_path = image_output / f"row_{index:02d}.png"
        if not prepared_image.save(str(crop_path), "PNG"):
            raise RuntimeError(f"OCR用PNGを保存できません: {crop_path}")
        psm = 11 if crop_height > 70 else 7
        if prepare_only:
            raw = ""
        elif ocr_engine == "windows":
            raw = _run_windows_ocr(crop_path, language)
        else:
            raw = _run_tesseract(crop_path, language, page_segmentation=psm)
        inline_quantity, item_text = strip_quantity(raw)
        match_inputs = reward_text_candidates(raw)
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
        matches = [match_item_name(value, item_dictionary) for value in match_inputs]
        trusted_matches = [value for value in matches if value[3]]
        exact_matches = [value for value in trusted_matches if value[1] == 1.0]
        selected = exact_matches[0] if len({value[0] for value in exact_matches}) == 1 else None
        if selected is None and not exact_matches and len({value[0] for value in trusted_matches}) == 1:
            selected = trusted_matches[0]
        best, match_score, match_margin, trusted = selected or ("", None, None, False)
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
