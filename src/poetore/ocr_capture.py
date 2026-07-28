from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QRect
from PySide6.QtGui import QGuiApplication, QImage


CAPTURE_WIDTH = 1200
CAPTURE_HEIGHT = 1400


class OcrCaptureError(RuntimeError):
    pass


@dataclass(frozen=True)
class OcrCapture:
    image: QImage
    screen_rect: QRect
    panel_rect: QRect


def capture_around_cursor(
    cursor: QPoint,
    width: int = CAPTURE_WIDTH,
    height: int = CAPTURE_HEIGHT,
) -> OcrCapture:
    """Capture a cursor-centred region, clamped to the containing display."""
    screen = QGuiApplication.screenAt(cursor)
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:
        raise OcrCaptureError("画面を取得できませんでした。")

    bounds = screen.geometry()
    capture_width = min(width, bounds.width())
    capture_height = min(height, bounds.height())
    left = max(bounds.left(), min(cursor.x() - capture_width // 2, bounds.right() - capture_width + 1))
    top = max(bounds.top(), min(cursor.y() - capture_height // 2, bounds.bottom() - capture_height + 1))
    screen_rect = QRect(left, top, capture_width, capture_height)
    pixmap = screen.grabWindow(
        0,
        screen_rect.x() - bounds.x(),
        screen_rect.y() - bounds.y(),
        screen_rect.width(),
        screen_rect.height(),
    )
    if pixmap.isNull():
        raise OcrCaptureError("スクリーンショットの取得に失敗しました。")

    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32)
    panel_rect = detect_item_panel(image)
    return OcrCapture(image.copy(panel_rect), screen_rect, panel_rect)


def detect_item_panel(image: QImage) -> QRect:
    """Find the broad dark PoE item panel; safely fall back to the full capture."""
    if image.isNull() or image.width() < 80 or image.height() < 80:
        return QRect(0, 0, image.width(), image.height())

    # PoE preview panels have a wide dark body. Locate rows/columns dominated by
    # low-luminance pixels, then retain the largest run around the image centre.
    stride = max(1, min(image.width(), image.height()) // 500)

    def dark(pixel: int) -> bool:
        red = (pixel >> 16) & 0xFF
        green = (pixel >> 8) & 0xFF
        blue = pixel & 0xFF
        return (red * 3 + green * 6 + blue) < 360

    row_dark = []
    for y in range(0, image.height(), stride):
        samples = [dark(image.pixel(x, y)) for x in range(0, image.width(), stride)]
        row_dark.append(sum(samples) / max(1, len(samples)) >= 0.42)
    col_dark = []
    for x in range(0, image.width(), stride):
        samples = [dark(image.pixel(x, y)) for y in range(0, image.height(), stride)]
        col_dark.append(sum(samples) / max(1, len(samples)) >= 0.35)

    y_run = _largest_true_run(row_dark)
    x_run = _largest_true_run(col_dark)
    if y_run is None or x_run is None:
        return QRect(0, 0, image.width(), image.height())

    left = max(0, x_run[0] * stride - 12)
    right = min(image.width(), (x_run[1] + 1) * stride + 12)
    # The gold name banner is brighter than the body and can sit just above
    # the detected dark run. Keep enough headroom to retain both title lines.
    top = max(0, y_run[0] * stride - 90)
    bottom = min(image.height(), (y_run[1] + 1) * stride + 12)
    candidate = QRect(left, top, right - left, bottom - top)
    if candidate.width() < image.width() * 0.45 or candidate.height() < 180:
        return QRect(0, 0, image.width(), image.height())
    return candidate


def _largest_true_run(values: list[bool]) -> tuple[int, int] | None:
    best = None
    start = None
    for index, value in enumerate(values + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            run = (start, index - 1)
            if best is None or run[1] - run[0] > best[1] - best[0]:
                best = run
            start = None
    return best


def image_to_png(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(buffer, "PNG"):
        raise OcrCaptureError("OCR用画像を作成できませんでした。")
    return bytes(data)


def recognize_japanese(image: QImage) -> str:
    """Run Windows' installed Japanese OCR engine without an external service."""
    if sys.platform != "win32":
        raise OcrCaptureError("スクリーンショットOCRはWindows版で利用できます。")
    try:
        return asyncio.run(_recognize_windows_png(image_to_png(image)))
    except OcrCaptureError:
        raise
    except ImportError as exc:
        raise OcrCaptureError(
            "OCRコンポーネントがありません。requirements.txtからWinRT OCRを導入してください。"
        ) from exc
    except Exception as exc:
        raise OcrCaptureError(f"Windows OCRに失敗しました: {exc}") from exc


async def _recognize_windows_png(png: bytes) -> str:
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    engine = OcrEngine.try_create_from_language(Language("ja-JP"))
    if engine is None:
        raise OcrCaptureError(
            "Windowsの日本語OCR言語が利用できません。日本語言語機能を追加してください。"
        )
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    result = await engine.recognize_async(bitmap)
    return "\n".join(
        " ".join(word.text for word in line.words).strip()
        for line in result.lines
        if line.words
    )


_CLASS_BY_BASE_SUFFIX = (
    ("指輪", "指輪"),
    ("アミュレット", "アミュレット"),
    ("ベルト", "ベルト"),
    ("ジュエル", "ジュエル"),
    ("フラスコ", "フラスコ"),
    ("盾", "盾"),
    ("シールド", "盾"),
)


def ocr_text_to_item_text(raw_text: str) -> str:
    """Convert OCR lines from a recombination/preview panel into parser input."""
    lines = [_clean_ocr_line(line) for line in raw_text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        raise OcrCaptureError("アイテムの文字を認識できませんでした。")

    while lines and ("実体化" in lines[0] or lines[0] in {"検索", "閉じる"}):
        lines.pop(0)
    if len(lines) < 3:
        raise OcrCaptureError("アイテム名とベースタイプを認識できませんでした。")

    name, base_type = lines[0], lines[1]
    item_class = next((value for suffix, value in _CLASS_BY_BASE_SUFFIX if suffix in base_type), "")
    if not item_class:
        raise OcrCaptureError(f"アイテムクラスを判定できませんでした: {base_type}")

    body = lines[2:]
    required_level = None
    property_lines: list[str] = []
    searchable_lines: list[str] = []
    flags: list[str] = []
    for line in body:
        level_match = re.search(r"装備条件レベル\s*[:：]?\s*(\d+)", line)
        if level_match:
            required_level = level_match.group(1)
            continue
        if line in {"未鑑定", "コラプト状態", "シンセシスアイテム"}:
            flags.append(line)
            continue
        if re.match(r"^(メモリー?ストランド|記憶の糸|幽体化度)\s*[:：]", line):
            property_lines.append(line)
            continue
        if _looks_like_modifier(line):
            searchable_lines.append(line)

    if not searchable_lines:
        raise OcrCaptureError("検索可能なModを認識できませんでした。")

    result = [
        f"アイテムクラス: {item_class}",
        "レアリティ: レア",
        name,
        base_type,
        "--------",
    ]
    if property_lines:
        result.extend([*property_lines, "--------"])
    if required_level:
        result.extend(["装備要求:", f"レベル: {required_level}", "--------"])
    # Screenshot previews do not expose item level. This internal marker moves
    # the normal parser into its Mod section without inventing an ilvl value.
    result.extend(["OCR検索Mod:", "--------"])
    for line in searchable_lines:
        result.extend(["{ 暗黙モッド }", line])
    result.extend(["--------", *flags])
    return "\n".join(result)


def _clean_ocr_line(line: str) -> str:
    line = line.strip().replace("：", ":")
    line = re.sub(r"\s+", " ", line)
    line = re.sub(r"\s*([+-])(?=\d)", r" \1", line)
    line = re.sub(r"\s*%\s*", "%", line)
    return line


def _looks_like_modifier(line: str) -> bool:
    if line in {"暗黙モッドは変化しない", "Implicit Modifiers are unchanged"}:
        return True
    return bool(
        re.search(r"\d", line)
        and any(
            token in line
            for token in (
                "モッド", "ダメージ", "クリティカル", "ライフ", "マナ",
                "耐性", "能力値", "スピード", "付与", "増加", "減少",
                "追加", "暗黙", "プレフィックス", "サフィックス",
            )
        )
    )
