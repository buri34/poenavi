"""Grand Heist Curio OCR for the PoE1 Japanese client."""

from __future__ import annotations

import json
import re
import sys
import threading
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QDialog, QMessageBox

from src.poetore.expedition_ocr_probe import WindowsOcrServer
from src.poetore.poe2.ndlocr_lite import NdlOcrLiteServer
from src.poetore.window_position import PlacementContext, path_of_exile_client_rect

CURIO_MIN_SCORE = 0.90
CURIO_MIN_MARGIN = 0.15
CURIO_OCR_SCALE = 3


@dataclass(frozen=True)
class CurioItem:
    stable_id: str
    category: str
    name_en: str
    name_ja: str
    base_type_en: str | None
    base_type_ja: str | None
    ocr_aliases_ja: tuple[str, ...]
    search: dict[str, object]


@dataclass(frozen=True)
class CurioMatch:
    item: CurioItem
    score: float
    margin: float
    name_score: float
    base_score: float

    @property
    def trusted(self) -> bool:
        return self.score >= CURIO_MIN_SCORE and self.margin >= CURIO_MIN_MARGIN


@dataclass(frozen=True)
class CurioUniqueModTemplate:
    stable_id: str
    status: str
    source_mod_count: int
    filters: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class OrangeLine:
    left: int
    right: int
    y: int


@dataclass(frozen=True)
class CurioHeaderBand:
    left: int
    right: int
    top: int
    bottom: int
    line_count: int

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2


def _runtime_roots() -> tuple[Path, ...]:
    source_root = Path(__file__).resolve().parents[2]
    executable_root = Path(sys.executable).resolve().parent
    return tuple(
        dict.fromkeys(
            (
                executable_root,
                Path(getattr(sys, "_MEIPASS", source_root)),
                source_root,
            )
        )
    )


def curio_dictionary_path() -> Path:
    relative = Path("data") / "poetore" / "poe1" / "heist_curio_ja_dictionary.json"
    for root in _runtime_roots():
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return _runtime_roots()[-1] / relative


def curio_unique_mod_templates_path() -> Path:
    relative = (
        Path("data") / "poetore" / "poe1" / "heist_unique_mod_templates.json"
    )
    for root in _runtime_roots():
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return _runtime_roots()[-1] / relative


@lru_cache(maxsize=1)
def load_curio_items(path: Path | None = None) -> tuple[CurioItem, ...]:
    source = path or curio_dictionary_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("未対応のハイスト報酬辞書です。")
    items = tuple(
        CurioItem(
            stable_id=str(row["stable_id"]),
            category=str(row["category"]),
            name_en=str(row["name_en"]),
            name_ja=str(row["name_ja"]),
            base_type_en=(
                str(row["base_type_en"]) if row.get("base_type_en") else None
            ),
            base_type_ja=(
                str(row["base_type_ja"]) if row.get("base_type_ja") else None
            ),
            ocr_aliases_ja=tuple(str(value) for value in row.get("ocr_aliases_ja", ())),
            search=dict(row["search"]),
        )
        for row in payload.get("items", ())
    )
    if not items or len({item.stable_id for item in items}) != len(items):
        raise ValueError("ハイスト報酬辞書が空か、安定IDが重複しています。")
    return items


@lru_cache(maxsize=1)
def load_curio_unique_mod_templates(
    path: Path | None = None,
) -> dict[str, CurioUniqueModTemplate]:
    source = path or curio_unique_mod_templates_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("未対応のハイストユニークMod辞書です。")
    templates = {
        str(row["stable_id"]): CurioUniqueModTemplate(
            stable_id=str(row["stable_id"]),
            status=str(row["status"]),
            source_mod_count=int(row.get("source_mod_count", 0)),
            filters=tuple(dict(value) for value in row.get("filters", ())),
        )
        for row in payload.get("items", ())
    }
    if len(templates) != 101:
        raise ValueError("ハイストユニークMod辞書は101件である必要があります。")
    return templates


def curio_unique_mod_filters(stable_id: str):
    """Return blank, disabled Trade filters for one identified Curio unique."""
    from src.poetore.trade import TradeStatFilter

    template = load_curio_unique_mod_templates().get(str(stable_id))
    if template is None or template.status == "random_veiled":
        return ()
    return tuple(
        TradeStatFilter(
            stat_id=str(row["stat_id"]),
            text=str(row["text_ja"]),
            min_value=None,
            kind="explicit",
            enabled=False,
            max_value=None,
            ref=str(row.get("ref") or "") or None,
            inverted=bool(row.get("inverted", False)),
            better=(int(row["better"]) if row.get("better") is not None else None),
            decimal=bool(row.get("decimal", False)),
            selection_reason="ハイストユニーク固定Mod候補",
        )
        for row in template.filters
    )


def normalize_curio_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龠々ー]+", "", normalized)


def _ocr_values(raw_text: str) -> tuple[str, ...]:
    lines = tuple(
        normalized
        for line in str(raw_text or "").splitlines()
        if (normalized := normalize_curio_text(line))
    )
    joined = normalize_curio_text(" ".join(str(raw_text or "").splitlines()))
    return tuple(dict.fromkeys((*lines, joined))) if joined else lines


def _text_score(values: Sequence[str], targets: Sequence[str | None]) -> float:
    normalized_targets = tuple(
        value
        for target in targets
        if target and (value := normalize_curio_text(target))
    )
    return max(
        (
            SequenceMatcher(None, value, target).ratio()
            for value in values
            for target in normalized_targets
            if value and target
        ),
        default=0.0,
    )


def rank_curio_matches(
    raw_text: str,
    items: Sequence[CurioItem] | None = None,
) -> tuple[CurioMatch, ...]:
    values = _ocr_values(raw_text)
    if not values:
        return ()
    ranked: list[tuple[CurioItem, float, float, float]] = []
    for item in items or load_curio_items():
        name_score = _text_score(values, (item.name_ja, *item.ocr_aliases_ja))
        base_score = _text_score(values, (item.base_type_ja,))
        if item.category in {"currency", "scarab"}:
            score = name_score
        elif item.category == "experimental_base":
            score = max(name_score, base_score)
        else:
            score = name_score * 0.65 + base_score * 0.35
        ranked.append((item, score, name_score, base_score))
    ranked.sort(key=lambda row: row[1], reverse=True)
    matches = []
    for index, (item, score, name_score, base_score) in enumerate(ranked):
        runner_up = ranked[index + 1][1] if index + 1 < len(ranked) else 0.0
        matches.append(
            CurioMatch(
                item=item,
                score=score,
                margin=score - runner_up,
                name_score=name_score,
                base_score=base_score,
            )
        )
    return tuple(matches)


def trusted_curio_match(
    raw_text: str,
    items: Sequence[CurioItem] | None = None,
) -> CurioMatch | None:
    ranked = rank_curio_matches(raw_text, items)
    return ranked[0] if ranked and ranked[0].trusted else None


def _is_orange(r: int, g: int, b: int) -> bool:
    highest = max(r, g, b)
    lowest = min(r, g, b)
    delta = highest - lowest
    return highest >= 65 and r == highest and g >= b and delta * 255 >= 45 * highest


def _overlap(left_a: int, right_a: int, left_b: int, right_b: int) -> int:
    return max(0, min(right_a, right_b) - max(left_a, left_b))


def detect_orange_lines(image: QImage) -> tuple[OrangeLine, ...]:
    """Detect the long gold separators used by Curio item headers."""
    if image.isNull() or image.width() < 100 or image.height() < 80:
        return ()
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    data = bytes(converted.constBits())
    stride = converted.bytesPerLine()
    width, height = converted.width(), converted.height()
    step = 2
    minimum = max(40, round(width * 0.14))
    rows: list[OrangeLine] = []
    for y in range(height):
        row = y * stride
        run_start = None
        last_orange = None
        misses = 0
        orange_samples = 0
        for x in range(0, width, step):
            offset = row + x * 4
            orange = _is_orange(data[offset], data[offset + 1], data[offset + 2])
            if orange:
                if run_start is None:
                    run_start = x
                last_orange = x
                misses = 0
                orange_samples += 1
            elif run_start is not None:
                misses += 1
                if misses <= 15:
                    continue
                sample_count = max(1, (last_orange - run_start) // step + 1)
                if (
                    last_orange is not None
                    and last_orange - run_start >= minimum
                    and orange_samples / sample_count >= 0.55
                ):
                    rows.append(
                        OrangeLine(run_start, min(width - 1, last_orange + step), y)
                    )
                run_start = None
                last_orange = None
                misses = 0
                orange_samples = 0
        sample_count = (
            max(1, (last_orange - run_start) // step + 1)
            if run_start is not None and last_orange is not None
            else 1
        )
        if (
            run_start is not None
            and last_orange is not None
            and last_orange - run_start >= minimum
            and orange_samples / sample_count >= 0.55
        ):
            rows.append(OrangeLine(run_start, min(width - 1, last_orange + step), y))

    clusters: list[list[OrangeLine]] = []
    for line in rows:
        for cluster in reversed(clusters[-12:]):
            previous = cluster[-1]
            overlap = _overlap(line.left, line.right, previous.left, previous.right)
            if line.y - previous.y <= 3 and overlap >= 0.65 * min(
                line.right - line.left,
                previous.right - previous.left,
            ):
                cluster.append(line)
                break
        else:
            clusters.append([line])
    # Text glyphs can form orange runs on many adjacent rows. A separator is
    # the widest member of such a cluster, so retain that row instead of the
    # vertical mean (which can drift into the item name itself).
    return tuple(
        max(cluster, key=lambda line: (line.right - line.left, -line.y))
        for cluster in clusters
    )


def detect_header_bands(image: QImage) -> tuple[CurioHeaderBand, ...]:
    lines = detect_orange_lines(image)
    candidates: list[CurioHeaderBand] = []
    for index, first in enumerate(lines):
        aligned = [first]
        for following in lines[index + 1 :]:
            gap = following.y - aligned[-1].y
            if gap > 90:
                break
            overlap = _overlap(
                first.left,
                first.right,
                following.left,
                following.right,
            )
            if 15 <= gap <= 65 and overlap >= 0.70 * min(
                first.right - first.left,
                following.right - following.left,
            ):
                aligned.append(following)
                if len(aligned) == 4:
                    break
        if len(aligned) < 2:
            continue
        left = max(line.left for line in aligned)
        right = min(line.right for line in aligned)
        if right - left < image.width() * 0.14:
            continue
        candidates.append(
            CurioHeaderBand(
                left=left,
                right=right,
                top=aligned[0].y,
                bottom=aligned[-1].y,
                line_count=len(aligned),
            )
        )

    unique: list[CurioHeaderBand] = []
    for candidate in sorted(candidates, key=lambda band: (-band.line_count, band.top)):
        if any(
            abs(candidate.left - known.left) < 20
            and abs(candidate.right - known.right) < 20
            and (
                abs(candidate.top - known.top) < 12
                or (known.top <= candidate.top and candidate.bottom <= known.bottom)
            )
            for known in unique
        ):
            continue
        unique.append(candidate)
    return tuple(sorted(unique, key=lambda band: (band.left, band.top)))


def select_header_band(
    bands: Sequence[CurioHeaderBand],
    cursor: QPoint,
) -> CurioHeaderBand | None:
    matches = [band for band in bands if band.left <= cursor.x() <= band.right]
    if not matches:
        return None
    matches.sort(key=lambda band: (abs(band.center_y - cursor.y()), -band.line_count))
    best = matches[0]
    if len(matches) > 1:
        first_distance = abs(best.center_y - cursor.y())
        second_distance = abs(matches[1].center_y - cursor.y())
        if (
            best.line_count == matches[1].line_count
            and first_distance == second_distance
        ):
            return None
    return best


def image_point_for_capture(
    global_point: QPoint,
    capture_rect: QRect,
    image: QImage,
) -> QPoint:
    """Map a Qt logical screen point into the captured image's pixel grid."""
    if capture_rect.isEmpty() or image.isNull():
        return QPoint()
    local = global_point - capture_rect.topLeft()
    scale_x = image.width() / capture_rect.width()
    scale_y = image.height() / capture_rect.height()
    return QPoint(
        max(0, min(image.width() - 1, round(local.x() * scale_x))),
        max(0, min(image.height() - 1, round(local.y() * scale_y))),
    )


def crop_header(image: QImage, band: CurioHeaderBand) -> QImage:
    margin_y = max(6, round(image.height() * 0.005))
    rect = QRect(
        band.left,
        max(0, band.top - margin_y),
        band.right - band.left + 1,
        min(image.height() - 1, band.bottom + margin_y)
        - max(0, band.top - margin_y)
        + 1,
    )
    return image.copy(rect)


def image_bytes(image: QImage, image_format: str = "BMP") -> bytes:
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


def prepare_curio_ocr_image(image: QImage) -> bytes:
    if image.isNull():
        raise ValueError("読取画像が空です。")
    scaled = image.scaled(
        image.width() * CURIO_OCR_SCALE,
        image.height() * CURIO_OCR_SCALE,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return image_bytes(scaled)


def curio_item_text(item: CurioItem) -> str:
    item_group = str(item.search.get("item_group") or "")
    item_class = {
        "weapon": "武器",
        "armour": "防具",
        "accessory": "アクセサリー",
    }.get(item_group, "アイテム")
    if item.category == "currency":
        return f"アイテムクラス: スタック可能カレンシー\nレアリティ: カレンシー\n{item.name_ja}\n--------"
    if item.category == "scarab":
        return f"アイテムクラス: マップフラグメント\nレアリティ: ノーマル\n{item.name_ja}\n--------"
    if item.category == "experimental_base":
        return f"アイテムクラス: {item_class}\nレアリティ: ノーマル\n{item.name_ja}\n--------"
    return (
        f"アイテムクラス: {item_class}\nレアリティ: ユニーク\n"
        f"{item.name_ja}\n{item.base_type_ja or item.name_ja}\n--------"
    )


class CurioRegionSelector(QDialog):
    """One-shot drag selector for manual Curio OCR."""

    def __init__(self, client_rect: QRect, parent=None):
        super().__init__(parent)
        self.client_rect = QRect(client_rect)
        self._origin: QPoint | None = None
        self._selection = QRect()
        self.setWindowTitle("ハイスト報酬の読取範囲を指定")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(client_rect)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    @property
    def selected_rect(self) -> QRect | None:
        if self._selection.width() < 80 or self._selection.height() < 24:
            return None
        selected = QRect(self._selection)
        selected.translate(self.client_rect.topLeft())
        return selected

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._selection = QRect(self._origin, QSize())
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._origin is None:
            return
        point = event.position().toPoint()
        point.setX(max(0, min(self.width() - 1, point.x())))
        point.setY(max(0, min(self.height() - 1, point.y())))
        self._selection = QRect(self._origin, point).normalized()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouseMoveEvent(event)
            self._origin = None

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.selected_rect is None:
                QMessageBox.warning(
                    self,
                    "範囲を確認してください",
                    "報酬名を含む範囲を選択してください。",
                )
                return
            self.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 92))
        if not self._selection.isNull():
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(self._selection, Qt.GlobalColor.transparent)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )
            painter.setPen(QPen(QColor("#65FFCA"), 3))
            painter.drawRect(self._selection)
        painter.setPen(QColor("white"))
        painter.drawText(
            self.rect().adjusted(20, 20, -20, -20),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
            "報酬名とベースタイプを囲んでください\nEnter: 確定 / Esc: キャンセル",
        )


class HeistCurioController(QObject):
    status = Signal(str)
    failed = Signal(str)
    resolved = Signal(object, object)
    high_accuracy_started = Signal(bool, object, object)
    high_accuracy_finished = Signal()

    def __init__(
        self,
        parent=None,
        *,
        ocr_server=None,
        ndl_ocr_server=None,
        scan_coordinator=None,
        items: Sequence[CurioItem] | None = None,
    ):
        super().__init__(parent)
        self._ocr = ocr_server or WindowsOcrServer()
        self._owns_ocr = ocr_server is None
        self._ndl_ocr = ndl_ocr_server or NdlOcrLiteServer()
        self._owns_ndl_ocr = ndl_ocr_server is None
        self._scan_coordinator = scan_coordinator
        self._items = tuple(items or load_curio_items())
        self._running = False
        self._generation = 0
        self._high_accuracy_overlay = None
        self.high_accuracy_started.connect(self._show_high_accuracy_status)
        self.high_accuracy_finished.connect(self._hide_high_accuracy_status)

    @property
    def running(self) -> bool:
        return self._running

    def close(self) -> None:
        self._generation += 1
        self._running = False
        self._hide_high_accuracy_status()
        if self._scan_coordinator is not None:
            self._scan_coordinator.finish("heist_curio")
        if self._owns_ocr:
            self._ocr.close()
        if self._owns_ndl_ocr:
            self._ndl_ocr.close()

    def warm_up(self) -> None:
        threading.Thread(
            target=self._safe_start, name="heist-curio-warmup", daemon=True
        ).start()

    def _safe_start(self) -> None:
        try:
            self._ocr.start()
        except Exception:  # noqa: BLE001 - a real scan retries and reports the error
            return

    def request_scan(self) -> bool:
        if self._running:
            return False
        if self._scan_coordinator is not None and not self._scan_coordinator.try_begin(
            "heist_curio"
        ):
            self.failed.emit("別の画面読み取り処理中です。")
            return False
        client_rect = path_of_exile_client_rect()
        if client_rect is None:
            self._finish_error("Path of Exileのゲーム画面が見つかりませんでした。")
            return False
        self._running = True
        self._generation += 1
        generation = self._generation
        selector = CurioRegionSelector(client_rect)
        if not selector.exec() or selector.selected_rect is None:
            self._finish_cancelled()
            return False
        capture_rect = selector.selected_rect
        placement = PlacementContext(QRect(client_rect), capture_rect.center())
        selector.hide()
        QGuiApplication.processEvents()
        image = self._grab(capture_rect)
        if image.isNull():
            self._finish_error("ゲーム画面をキャプチャできませんでした。")
            return False
        try:
            payload = prepare_curio_ocr_image(image)
        except Exception as exc:  # noqa: BLE001 - image conversion errors are user-facing
            self._finish_error(str(exc))
            return False
        self.status.emit("ハイスト報酬を読み取っています…")
        threading.Thread(
            target=self._process,
            args=(payload, placement, capture_rect, generation),
            name="heist-curio-ocr",
            daemon=True,
        ).start()
        return True

    @staticmethod
    def _grab(rect: QRect) -> QImage:
        screen = (
            QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        )
        if screen is None:
            return QImage()
        return screen.grabWindow(
            0, rect.x(), rect.y(), rect.width(), rect.height()
        ).toImage()

    def _process(
        self,
        payload: bytes,
        placement: PlacementContext,
        capture_rect: QRect,
        generation: int,
    ) -> None:
        try:
            self._ocr.start()
            raw_text = self._ocr.recognize([payload])[0]
            match = trusted_curio_match(raw_text, self._items)
            if match is None and getattr(self._ndl_ocr, "is_available", False):
                cold_start = getattr(self._ndl_ocr, "is_ready", False) is not True
                self.high_accuracy_started.emit(
                    cold_start,
                    QRect(placement.target_rect),
                    QRect(capture_rect),
                )
                try:
                    results = self._ndl_ocr.recognize([payload])
                    ndl_text = results[0].text if results else ""
                    match = trusted_curio_match(ndl_text, self._items)
                finally:
                    self.high_accuracy_finished.emit()
            if match is None:
                raise RuntimeError(
                    "報酬名を安全に特定できませんでした。"
                    "範囲を変えてもう一度お試しください。"
                )
            if generation == self._generation:
                self.resolved.emit(match, placement)
        except Exception as exc:  # noqa: BLE001 - worker boundary reports to UI
            if generation == self._generation:
                self.failed.emit(str(exc))
        finally:
            if generation == self._generation:
                self._running = False
                if self._scan_coordinator is not None:
                    self._scan_coordinator.finish("heist_curio")

    def _finish_error(self, message: str) -> None:
        self._running = False
        if self._scan_coordinator is not None:
            self._scan_coordinator.finish("heist_curio")
        self.failed.emit(message)

    def _finish_cancelled(self) -> None:
        self._running = False
        if self._scan_coordinator is not None:
            self._scan_coordinator.finish("heist_curio")

    def _show_high_accuracy_status(
        self, cold_start: bool, client_rect: QRect, capture_rect: QRect
    ) -> None:
        if self._high_accuracy_overlay is None:
            from src.poetore.poe2.desecration_overlay import (
                HighAccuracyOcrStatusOverlay,
            )

            self._high_accuracy_overlay = HighAccuracyOcrStatusOverlay()
        lines = [
            "通常の読み取りで報酬名を確認できませんでした",
            (
                "高精度OCRを準備しています…"
                if cold_start
                else "高精度OCRで再確認しています…"
            ),
        ]
        if cold_start:
            lines.append("初回のみ10～15秒ほどかかります")
        self._high_accuracy_overlay.show_status(client_rect, capture_rect, lines)

    def _hide_high_accuracy_status(self) -> None:
        if self._high_accuracy_overlay is not None:
            self._high_accuracy_overlay.hide()
