"""Runtime controller and overlays for PoE2 Desecration Reveal tiers."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.poetore.expedition_ocr_probe import WindowsOcrServer
from src.poetore.poe2.desecration_ocr import (
    ChoiceBand,
    image_bytes,
    prepare_desecration_frame,
    resolve_ocr_variants,
)
from src.poetore.window_position import path_of_exile_client_rect

CATEGORY_LABELS = {
    "amulet": "アミュレット", "belt": "ベルト", "body_armour": "胴体防具",
    "boots": "靴", "bow": "弓", "claw": "クロー", "crossbow": "クロスボウ",
    "dagger": "ダガー", "flail": "フレイル", "focus": "フォーカス",
    "gloves": "手袋", "helmet": "兜", "jewel": "ジュエル",
    "one_hand_axe": "片手斧", "one_hand_mace": "片手メイス",
    "one_hand_sword": "片手剣", "quiver": "矢筒", "ring": "指輪",
    "sceptre": "セプター", "shield": "盾", "spear": "スピア",
    "staff": "スタッフ", "talisman": "タリスマン", "two_hand_axe": "両手斧",
    "two_hand_mace": "両手メイス", "two_hand_sword": "両手剣", "wand": "ワンド",
}


def normalized_capture_rect(client_rect: QRect, value) -> QRect | None:
    if not isinstance(value, dict):
        return None
    try:
        left, top, right, bottom = (float(value[key]) for key in ("left", "top", "right", "bottom"))
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        return None
    x = client_rect.x() + round(client_rect.width() * left)
    y = client_rect.y() + round(client_rect.height() * top)
    return QRect(x, y, max(1, round(client_rect.width() * (right - left))), max(1, round(client_rect.height() * (bottom - top))))


class DesecrationTierOverlay(QWidget):
    def __init__(self):
        super().__init__(None)
        self._capture_offset = QPoint()
        self._capture_size = (1, 1)
        self._bands: tuple[ChoiceBand, ...] = ()
        self._tiers: tuple[int | None, ...] = ()
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def show_tiers(self, client_rect: QRect, capture_rect: QRect, source_size, bands, tiers):
        self.setGeometry(client_rect)
        self._capture_offset = capture_rect.topLeft() - client_rect.topLeft()
        self._capture_size = source_size
        self._bands = tuple(bands)
        self._tiers = tuple(tiers)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _event):
        if not self._bands:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale_y = 1.0
        x = self._capture_offset.x() + self._capture_size[0] - 58
        for band, tier in zip(self._bands, self._tiers):
            y = self._capture_offset.y() + round(((band.top + band.bottom) / 2) * scale_y)
            label = f"T{tier}" if tier is not None else "不明"
            rect = QRectF(x, y - 15, 50, 30)
            font = QFont(self.font())
            font.setBold(True)
            font.setPixelSize(16)
            painter.setFont(font)
            if tier == 1:
                painter.setBrush(QColor("#C9A227")); painter.setPen(QPen(QColor("#F4D76A"), 2))
                text_color = QColor("#111111")
            elif tier == 2:
                painter.setBrush(QColor(10, 13, 12, 220)); painter.setPen(QPen(QColor("#C9A227"), 2))
                text_color = QColor("white")
            elif tier is None:
                painter.setBrush(QColor(10, 13, 12, 220)); painter.setPen(QPen(QColor("#FF9F43"), 2))
                text_color = QColor("#FFCC80")
            else:
                painter.setBrush(QColor(10, 13, 12, 220)); painter.setPen(QPen(QColor("#DDE7E3"), 1))
                text_color = QColor("white")
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(text_color)
            painter.drawText(rect, Qt.AlignCenter, label)


class CategoryChoiceOverlay(QWidget):
    selected = Signal(str)
    cancelled = Signal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet("QWidget { background:#111715; color:#E8F1EE; } QPushButton { padding:6px 10px; border:1px solid #63E6C5; border-radius:5px; color:#E8F1EE; } QPushButton:hover { background:#25463E; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.addWidget(QLabel("装備の種類を選択してください"))
        self._buttons = QGridLayout()
        root.addLayout(self._buttons)

    def show_categories(self, categories, anchor: QPoint):
        while self._buttons.count():
            item = self._buttons.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for index, category in enumerate(categories):
            button = QPushButton(CATEGORY_LABELS.get(category, category))
            button.clicked.connect(lambda _checked=False, value=category: self._choose(value))
            self._buttons.addWidget(button, index // 4, index % 4)
        cancel = QPushButton("閉じる")
        cancel.clicked.connect(self._cancel)
        final_index = len(categories)
        self._buttons.addWidget(cancel, final_index // 4, final_index % 4)
        self.adjustSize()
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            anchor.setX(min(max(available.left(), anchor.x()), available.right() - self.width() + 1))
            anchor.setY(min(max(available.top(), anchor.y()), available.bottom() - self.height() + 1))
        self.move(anchor)
        self.show()
        self.raise_()

    def _choose(self, category):
        self.hide()
        self.selected.emit(category)

    def _cancel(self):
        self.hide()
        self.cancelled.emit()


class DesecrationTierController(QObject):
    status = Signal(str)
    failed = Signal(str)
    _ready = Signal(object, object, object, object, int)

    def __init__(self, parent=None, *, regions_getter=None, ocr_server=None, scan_coordinator=None):
        super().__init__(parent)
        self._regions_getter = regions_getter or dict
        self._ocr = ocr_server or WindowsOcrServer()
        self._owns_ocr = ocr_server is None
        self._scan_coordinator = scan_coordinator
        self._overlay = DesecrationTierOverlay()
        self._category_overlay = CategoryChoiceOverlay()
        self._category_overlay.selected.connect(self._category_selected)
        self._running = False
        self._scan_generation = 0
        self._pending = None
        self._monitor = QTimer(self)
        self._monitor.setInterval(650)
        self._monitor.timeout.connect(self._check_panel)
        self._monitor_misses = 0
        self._expiry = QTimer(self)
        self._expiry.setSingleShot(True)
        self._expiry.setInterval(15000)
        self._expiry.timeout.connect(self.hide)
        self._client_rect = None
        self._capture_rect = None
        self._bands = ()
        self._ready.connect(self._show_result)

    @property
    def running(self):
        return self._running

    def warm_up(self):
        threading.Thread(target=self._safe_start, daemon=True).start()

    def _safe_start(self):
        try:
            self._ocr.start()
        except Exception:  # noqa: BLE001, S110 - the scan retries and reports errors
            pass

    def request_scan(self):
        if self._running:
            return False
        if self._scan_coordinator is not None and not self._scan_coordinator.try_begin("desecration"):
            self.failed.emit("別の画面読み取り処理中です。")
            return False
        client_rect = path_of_exile_client_rect()
        if client_rect is None:
            self._finish_error("Path of Exileのゲーム画面が見つかりませんでした。")
            return False
        regions = self._regions_getter() or {}
        open_rect = normalized_capture_rect(client_rect, regions.get("inventory_open_region"))
        if open_rect is None:
            self._finish_error("インベントリを開いた状態の読取範囲が未設定です。")
            return False
        self._running = True
        self._scan_generation += 1
        generation = self._scan_generation
        self.hide()
        self._client_rect = QRect(client_rect)
        image = self._grab(open_rect)
        prepared = prepare_desecration_frame(image)
        capture_rect = open_rect
        if not prepared.valid_panel:
            closed_rect = normalized_capture_rect(client_rect, regions.get("inventory_closed_region"))
            if closed_rect is not None:
                closed_image = self._grab(closed_rect)
                closed_prepared = prepare_desecration_frame(closed_image)
                if closed_prepared.valid_panel:
                    image, prepared, capture_rect = closed_image, closed_prepared, closed_rect
        if not prepared.valid_panel:
            self._finish_error("冒涜Modの3択を検出できませんでした。")
            return False
        self._capture_rect = QRect(capture_rect)
        self._bands = prepared.bands
        self.status.emit("アビス冒涜Modを読み取っています…")
        threading.Thread(target=self._process, args=(prepared, generation), daemon=True).start()
        return True

    def _grab(self, rect):
        screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return QImage()
        return screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height()).toImage()

    def _process(self, prepared, generation):
        try:
            if generation != self._scan_generation:
                return
            images = [image_bytes(image) for variants in prepared.variants for image in variants]
            self._ocr.start()
            raw = self._ocr.recognize(images)
            width = len(prepared.variants[0])
            grouped = tuple(tuple(raw[index * width:(index + 1) * width]) for index in range(3))
            resolution = resolve_ocr_variants(grouped)
            if not resolution.categories:
                raise RuntimeError("Tierを安全に特定できるModがありませんでした。")
            self._ready.emit(resolution, self._client_rect, self._capture_rect, prepared.bands, generation)
        except Exception as exc:  # noqa: BLE001 - worker boundary reports to UI
            if generation == self._scan_generation:
                self._finish_error(str(exc))

    def _show_result(self, resolution, client_rect, capture_rect, bands, generation):
        if generation != self._scan_generation:
            return
        self._running = False
        self._release_scan()
        if resolution.needs_category_choice:
            self._pending = (resolution, client_rect, capture_rect, bands)
            anchor = QPoint(capture_rect.left(), capture_rect.bottom() + 8)
            self._category_overlay.show_categories(resolution.categories, anchor)
            self.status.emit("装備の種類を選択してください。")
            return
        tiers = resolution.tiers
        if tiers is None:
            self._finish_error("Tierを一意に特定できませんでした。")
            return
        self._display(client_rect, capture_rect, bands, tiers)

    def _category_selected(self, category):
        if self._pending is None:
            return
        resolution, client_rect, capture_rect, bands = self._pending
        self._pending = None
        self._display(client_rect, capture_rect, bands, resolution.tiers_by_category[category])

    def _display(self, client_rect, capture_rect, bands, tiers):
        self._overlay.show_tiers(
            client_rect, capture_rect, (capture_rect.width(), capture_rect.height()), bands, tiers
        )
        self._monitor_misses = 0
        self._monitor.start()
        self._expiry.start()
        known = sum(tier is not None for tier in tiers)
        self.status.emit(f"{known}/3件のTierを表示しました。")

    def _check_panel(self):
        if self._capture_rect is None:
            self.hide(); return
        frame = prepare_desecration_frame(self._grab(self._capture_rect))
        if frame.valid_panel:
            self._monitor_misses = 0
            return
        self._monitor_misses += 1
        if self._monitor_misses >= 2:
            self.hide()
            self.status.emit("冒涜Modの3択画面を閉じたため表示を消しました。")

    def _finish_error(self, message):
        self._running = False
        self._release_scan()
        self.failed.emit(message)

    def _release_scan(self):
        if self._scan_coordinator is not None:
            self._scan_coordinator.finish("desecration")

    def hide(self):
        self._overlay.hide()
        self._category_overlay.hide()
        self._monitor.stop()
        self._expiry.stop()
        self._pending = None

    def close(self):
        self._scan_generation += 1
        self._running = False
        self.hide()
        self._release_scan()
        if self._owns_ocr:
            self._ocr.close()
