"""Runtime OCR and unit-price helpers for the PoE2 Expedition reward panel."""

from __future__ import annotations

import json
import tempfile
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from src.poetore.expedition_ocr_probe import (
    RowBand,
    analyze_image,
    match_item_name,
    run_windows_ocr_batch,
    strip_quantity,
)
from src.poetore.window_position import path_of_exile_client_rect


@dataclass(frozen=True)
class RewardIdentity:
    top: int
    bottom: int
    japanese_name: str
    english_name: str


@dataclass(frozen=True)
class RewardPriceRow:
    top: int
    bottom: int
    text: str


def load_reward_aliases(path: Path | None = None) -> dict[str, str]:
    source = path or (
        Path(__file__).resolve().parents[2]
        / "data" / "poetore" / "poe2" / "expedition_ocr_items.json"
    )
    loaded = json.loads(source.read_text(encoding="utf-8"))
    return {
        str(row["ja"]): str(row["en"])
        for row in loaded.get("items", ())
        if row.get("ja") and row.get("en")
    }


def stable_reward_identities(
    frames: list[list[RewardIdentity]], *, required_votes: int = 2,
) -> list[RewardIdentity]:
    """Keep only row identities that agree in multiple captured frames."""
    if not frames:
        return []
    max_rows = max((len(frame) for frame in frames), default=0)
    stable: list[RewardIdentity] = []
    for index in range(max_rows):
        rows = [frame[index] for frame in frames if index < len(frame)]
        votes = Counter(row.english_name for row in rows)
        if not votes:
            continue
        name, count = votes.most_common(1)[0]
        if count < required_votes:
            continue
        agreeing = [row for row in rows if row.english_name == name]
        agreeing.sort(key=lambda row: (row.top, row.bottom))
        middle = agreeing[len(agreeing) // 2]
        stable.append(middle)
    return stable


def format_exalted_unit_price(value: float) -> str:
    if value < 0.01:
        amount = "<0.01"
    elif value < 1:
        amount = f"{value:.2f}".rstrip("0").rstrip(".")
    elif value < 10:
        amount = f"{value:.1f}".rstrip("0").rstrip(".")
    else:
        amount = f"{value:.0f}"
    return f"{amount} 高貴/個"


def price_label_x(display_width: int, source_width: int, panel_width: int) -> int:
    """Place price text immediately to the right of the detected reward panel."""
    if display_width <= 0 or source_width <= 0:
        return 8
    scaled_panel_right = round(panel_width * display_width / source_width)
    return max(8, min(display_width - 8, scaled_panel_right + 8))


def reward_cards_still_visible(
    image: QImage, bands: list[RowBand], panel_width: int,
) -> bool:
    """Cheaply verify that the pale cards behind the shown rows still exist."""
    if image.isNull() or not bands or panel_width <= 0:
        return False
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    right = min(image.width(), panel_width)
    for band in bands:
        y = max(0, min(image.height() - 1, (band.top + band.bottom) // 2))
        samples = 0
        pale = 0
        for x in range(0, right, max(2, right // 80)):
            color = image.pixelColor(x, y)
            channels = (color.red(), color.green(), color.blue())
            samples += 1
            if sum(channels) / 3 > 115 and max(channels) - min(channels) < 100:
                pale += 1
        if samples and pale / samples >= 0.35:
            return True
    return False


class ExpeditionPriceOverlay(QWidget):
    def __init__(self):
        super().__init__(None)
        self._rows: list[RewardPriceRow] = []
        self._source_width = 1
        self._source_height = 1
        self._panel_width = 0
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def show_prices(
        self,
        client_rect: QRect,
        source_width: int,
        source_height: int,
        panel_width: int,
        rows: list[RewardPriceRow],
    ) -> None:
        self._source_width = max(1, source_width)
        self._source_height = max(1, source_height)
        self._panel_width = max(0, panel_width)
        self._rows = rows
        self.setGeometry(client_rect)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont("Yu Gothic UI", 13)
        font.setBold(True)
        painter.setFont(font)
        x = price_label_x(self.width(), self._source_width, self._panel_width)
        scale_y = self.height() / self._source_height
        for row in self._rows:
            y = round(((row.top + row.bottom) / 2) * scale_y)
            bounds = painter.fontMetrics().boundingRect(row.text)
            baseline = y + bounds.height() // 3
            painter.setPen(QPen(QColor(0, 0, 0, 220), 4, Qt.SolidLine, Qt.RoundCap))
            painter.drawText(x, baseline, row.text)
            painter.setPen(QColor("#B0FF7B"))
            painter.drawText(x, baseline, row.text)


class ExpeditionRewardController(QObject):
    status = Signal(str)
    failed = Signal(str)
    _ready = Signal(object, object, object, object, object)

    def __init__(self, league_getter, parent=None):
        super().__init__(parent)
        self._league_getter = league_getter
        self._overlay = ExpeditionPriceOverlay()
        self._captures: list[QImage] = []
        self._capture_rect: QRect | None = None
        self._running = False
        self._monitor_misses = 0
        self._bands: list[RowBand] = []
        self._panel_width = 0
        self._monitor = QTimer(self)
        self._monitor.setInterval(650)
        self._monitor.timeout.connect(self._check_panel)
        self._ready.connect(self._show_result)

    @property
    def running(self) -> bool:
        return self._running

    def hide(self) -> None:
        self._overlay.hide()
        self._monitor.stop()

    def request_scan(self) -> bool:
        if self._running:
            return False
        client_rect = path_of_exile_client_rect()
        if client_rect is None:
            self.failed.emit("Path of Exileのゲーム画面が見つかりませんでした。")
            return False
        self._running = True
        self.hide()
        self._capture_rect = QRect(client_rect)
        self._captures = []
        self.status.emit("エクスペディション報酬を読み取っています…")
        self._capture_frame()
        return True

    def _grab_game(self) -> QImage:
        rect = self._capture_rect or path_of_exile_client_rect()
        if rect is None:
            return QImage()
        screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return QImage()
        return screen.grabWindow(
            0, rect.x(), rect.y(), rect.width(), rect.height()
        ).toImage()

    def _capture_frame(self) -> None:
        image = self._grab_game()
        if image.isNull():
            self._finish_error("ゲーム画面をキャプチャできませんでした。")
            return
        self._captures.append(image)
        if len(self._captures) < 3:
            QTimer.singleShot(220, self._capture_frame)
            return
        images = list(self._captures)
        rect = QRect(self._capture_rect)
        threading.Thread(
            target=self._process, args=(images, rect), daemon=True,
        ).start()

    def _process(self, images: list[QImage], client_rect: QRect) -> None:
        try:
            aliases = load_reward_aliases()
            candidates = tuple(aliases)
            prepared: list[tuple[dict, list[Path]]] = []
            with tempfile.TemporaryDirectory(prefix="poenavi-expedition-") as temp:
                root = Path(temp)
                all_crops: list[Path] = []
                for frame_index, image in enumerate(images):
                    source = root / f"frame-{frame_index}.png"
                    if not image.save(str(source), "PNG"):
                        raise RuntimeError("OCR用画像を保存できませんでした。")
                    output = root / f"prepared-{frame_index}"
                    result = analyze_image(
                        source, output, ocr_engine="windows", prepare_only=True,
                    )
                    crops = [
                        output / source.stem / f"row_{index:02d}.png"
                        for index in range(1, len(result["rows"]) + 1)
                    ]
                    prepared.append((result, crops))
                    all_crops.extend(crops)
                raw_texts = run_windows_ocr_batch(all_crops)
                offset = 0
                frames: list[list[RewardIdentity]] = []
                for result, crops in prepared:
                    frame: list[RewardIdentity] = []
                    for row, raw in zip(result["rows"], raw_texts[offset:offset + len(crops)]):
                        _quantity, item_text = strip_quantity(raw)
                        best, _score, _margin, trusted = match_item_name(
                            item_text, candidates,
                        )
                        if trusted:
                            frame.append(RewardIdentity(
                                int(row["top"]), int(row["bottom"]), best, aliases[best]
                            ))
                        else:
                            frame.append(RewardIdentity(
                                int(row["top"]), int(row["bottom"]), "", ""
                            ))
                    frames.append(frame)
                    offset += len(crops)
                stable = [row for row in stable_reward_identities(frames) if row.english_name]
                if not stable:
                    raise RuntimeError("安全に特定できる報酬名がありませんでした。")

                from src.poetore.poe_ninja import default_poe_ninja_service

                league = self._league_getter()
                prices = default_poe_ninja_service.lookup_poe2_expedition_rewards(
                    tuple(row.english_name for row in stable), league,
                )
                exalted_chaos = default_poe_ninja_service.exalted_chaos_rate(league)
                if not exalted_chaos:
                    raise RuntimeError("高貴なオーブの換算レートを取得できませんでした。")
                shown = [
                    RewardPriceRow(
                        row.top, row.bottom,
                        format_exalted_unit_price(prices[row.english_name].chaos / exalted_chaos),
                    )
                    for row in stable
                    if row.english_name in prices and prices[row.english_name].chaos > 0
                ]
                if not shown:
                    raise RuntimeError("特定した報酬のpoe.ninja価格が見つかりませんでした。")
                first = prepared[0][0]
                bands = [RowBand(int(row["top"]), int(row["bottom"])) for row in first["rows"]]
                self._ready.emit(
                    client_rect, shown, (int(first["width"]), int(first["height"])),
                    (int(first["panel_width"]), bands), len(stable),
                )
        except Exception as exc:
            self.failed.emit(str(exc))
            self._running = False

    def _show_result(self, client_rect, rows, source_size, panel_data, stable_count):
        self._running = False
        self._panel_width, self._bands = panel_data
        self._capture_rect = QRect(client_rect)
        self._overlay.show_prices(
            client_rect, source_size[0], source_size[1], self._panel_width, rows,
        )
        self._monitor_misses = 0
        self._monitor.start()
        self.status.emit(f"{len(rows)}/{stable_count}件の単価を表示しました。")

    def _finish_error(self, message: str) -> None:
        self._running = False
        self.failed.emit(message)

    def _check_panel(self) -> None:
        image = self._grab_game()
        if reward_cards_still_visible(image, self._bands, self._panel_width):
            self._monitor_misses = 0
            return
        self._monitor_misses += 1
        if self._monitor_misses >= 2:
            self.hide()
            self.status.emit("エクスペディション報酬画面を閉じたため表示を消しました。")
