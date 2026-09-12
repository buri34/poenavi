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
from src.poetore.poe2.desecration_tiers import available_categories
from src.poetore.window_position import path_of_exile_client_rect

CATEGORY_LABELS = {
    "amulet": "アミュレット", "belt": "ベルト", "body_armour": "鎧",
    "boots": "靴", "bow": "弓", "claw": "クロー", "crossbow": "クロスボウ",
    "dagger": "ダガー", "flail": "フレイル", "focus": "フォーカス",
    "gloves": "手袋", "helmet": "兜", "jewel": "ジュエル",
    "one_hand_axe": "片手斧", "one_hand_mace": "片手メイス",
    "one_hand_sword": "片手剣", "quiver": "矢筒", "ring": "指輪",
    "sceptre": "セプター", "shield": "盾", "spear": "スピア",
    "staff": "スタッフ", "quarterstaff": "クォータースタッフ",
    "talisman": "タリスマン", "two_hand_axe": "両手斧",
    "two_hand_mace": "両手メイス", "two_hand_sword": "両手剣", "wand": "ワンド",
}

UNAVAILABLE_POE2_CATEGORIES = frozenset({
    "claw", "dagger", "flail", "one_hand_axe", "one_hand_sword",
    "two_hand_axe", "two_hand_sword",
})


def selectable_categories(categories=None) -> tuple[str, ...]:
    source = available_categories() if categories is None else categories
    return tuple(
        category for category in source
        if category not in UNAVAILABLE_POE2_CATEGORIES
    )


STATUS_LABELS = {
    "read_failed": "読取失敗",
    "unsupported": "未対応",
    "tierless": "Tierなし",
    "category_unselected": "部位未選択",
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
        self._statuses: tuple[str, ...] = ()
        self._range_labels: tuple[tuple[str, ...], ...] = ()
        self._show_ranges = False
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def show_tiers(
        self, client_rect: QRect, capture_rect: QRect, source_size, bands, tiers,
        *, statuses=(), range_labels=(), show_ranges=False,
    ):
        self.setGeometry(client_rect)
        self._capture_offset = capture_rect.topLeft() - client_rect.topLeft()
        self._capture_size = source_size
        self._bands = tuple(bands)
        self._tiers = tuple(tiers)
        self._statuses = tuple(statuses)
        self._range_labels = tuple(tuple(labels) for labels in range_labels)
        self._show_ranges = bool(show_ranges)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _event):
        if not self._bands:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale_y = 1.0
        right_edge = self._capture_offset.x() + self._capture_size[0] - 8
        rows = zip(
            self._bands,
            self._tiers,
            self._statuses or ("matched",) * len(self._tiers),
            self._range_labels or ((),) * len(self._tiers),
        )
        for band, tier, status, range_labels in rows:
            y = self._capture_offset.y() + round(((band.top + band.bottom) / 2) * scale_y)
            label = f"T{tier}" if tier is not None else STATUS_LABELS.get(status, "読取失敗")
            badge_width = 50 if tier is not None else 82
            rect = QRectF(right_edge - badge_width, y - 15, badge_width, 30)
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
            elif status == "unsupported":
                painter.setBrush(QColor(10, 13, 12, 230)); painter.setPen(QPen(QColor("#B79CFF"), 2))
                text_color = QColor("#D8CAFF")
            elif status == "tierless":
                painter.setBrush(QColor(30, 34, 33, 230)); painter.setPen(QPen(QColor("#8D9894"), 2))
                text_color = QColor("#D0D6D4")
            elif status == "category_unselected":
                painter.setBrush(QColor(10, 13, 12, 230)); painter.setPen(QPen(QColor("#E7C85E"), 2))
                text_color = QColor("#FFE88A")
            elif tier is None:
                painter.setBrush(QColor(10, 13, 12, 230)); painter.setPen(QPen(QColor("#FF9F43"), 2))
                text_color = QColor("#FFCC80")
            else:
                painter.setBrush(QColor(10, 13, 12, 220)); painter.setPen(QPen(QColor("#DDE7E3"), 1))
                text_color = QColor("white")
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(text_color)
            painter.drawText(rect, Qt.AlignCenter, label)
            if self._show_ranges and tier is not None and range_labels:
                self._draw_ranges(painter, y, range_labels)

    def _draw_ranges(self, painter: QPainter, center_y: int, labels: tuple[str, ...]):
        range_font = QFont(self.font())
        range_font.setBold(True)
        range_font.setPixelSize(13)
        painter.setFont(range_font)
        metrics = painter.fontMetrics()
        desired_width = max(metrics.horizontalAdvance(label) for label in labels) + 14
        x = self._capture_offset.x() + self._capture_size[0] + 8
        available = self.width() - x - 6
        if available < 36:
            return
        width = min(max(54, desired_width), available)
        line_height = 18
        height = line_height * len(labels) + 6
        rect = QRectF(x, center_y - height / 2, width, height)
        painter.setBrush(QColor(10, 13, 12, 218))
        painter.setPen(QPen(QColor("#7E8B87"), 1))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor("#F0F4F2"))
        for index, label in enumerate(labels):
            line = QRectF(x, rect.top() + 3 + index * line_height, width, line_height)
            painter.drawText(line, Qt.AlignCenter, label)


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
        categories = selectable_categories(categories)
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
    _retry_closed_requested = Signal(int)

    def __init__(
        self, parent=None, *, regions_getter=None, ocr_server=None,
        scan_coordinator=None, trace_factory=None,
    ):
        super().__init__(parent)
        self._regions_getter = regions_getter or dict
        self._ocr = ocr_server or WindowsOcrServer()
        self._owns_ocr = ocr_server is None
        self._scan_coordinator = scan_coordinator
        self._trace_factory = trace_factory
        self._active_trace = None
        self._overlay = DesecrationTierOverlay()
        self._category_overlay = CategoryChoiceOverlay()
        self._category_overlay.selected.connect(self._category_selected)
        self._category_overlay.cancelled.connect(self._category_cancelled)
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
        self._retry_closed_requested.connect(self._scan_closed)

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
        trace = self._create_trace()
        self._mark_trace(trace, "scan_requested", schema_version=1)
        if self._running:
            self._mark_trace(trace, "scan_completed", outcome="rejected_running")
            return False
        if self._scan_coordinator is not None and not self._scan_coordinator.try_begin("desecration"):
            self._mark_trace(trace, "scan_completed", outcome="rejected_ocr_busy")
            self.failed.emit("別の画面読み取り処理中です。")
            return False
        self._active_trace = trace
        self._mark_trace(trace, "scan_gate_acquired")
        client_rect = path_of_exile_client_rect()
        if client_rect is None:
            self._finish_error(
                "Path of Exileのゲーム画面が見つかりませんでした。",
                failure_stage="client_rect",
            )
            return False
        self._mark_trace(
            trace, "client_rect_resolved",
            client_width=client_rect.width(), client_height=client_rect.height(),
        )
        regions = self._regions_getter() or {}
        open_rect = normalized_capture_rect(client_rect, regions.get("inventory_open_region"))
        if open_rect is None:
            self._finish_error(
                "インベントリを開いた状態の読取範囲が未設定です。",
                failure_stage="open_region",
            )
            return False
        self._mark_trace(
            trace, "capture_region_resolved", capture_mode="open",
            capture_width=open_rect.width(), capture_height=open_rect.height(),
        )
        self._running = True
        self._scan_generation += 1
        generation = self._scan_generation
        self.hide()
        self._client_rect = QRect(client_rect)
        image = self._grab(open_rect)
        self._mark_trace(
            trace, "capture_completed", capture_mode="open",
            image_width=image.width(), image_height=image.height(),
        )
        prepared = prepare_desecration_frame(image)
        self._mark_frame_prepared(trace, prepared, "open")
        if not prepared.valid_panel:
            self._mark_trace(
                trace, "closed_fallback_requested", reason="open_panel_not_detected",
            )
            return self._scan_closed(generation)
        self._capture_rect = QRect(open_rect)
        self._bands = prepared.bands
        self.status.emit("アビス冒涜Modを読み取っています…")
        allow_closed = normalized_capture_rect(
            client_rect, regions.get("inventory_closed_region")
        ) is not None
        threading.Thread(
            target=self._process,
            args=(prepared, QRect(open_rect), generation, allow_closed, "open"), daemon=True,
        ).start()
        return True

    def _scan_closed(self, generation):
        if generation != self._scan_generation or self._client_rect is None:
            return False
        regions = self._regions_getter() or {}
        closed_rect = normalized_capture_rect(
            self._client_rect, regions.get("inventory_closed_region")
        )
        if closed_rect is None:
            self._finish_error(
                "冒涜Modの3択を検出できませんでした。",
                failure_stage="closed_region",
            )
            return False
        trace = self._active_trace
        self._mark_trace(
            trace, "capture_region_resolved", capture_mode="closed",
            capture_width=closed_rect.width(), capture_height=closed_rect.height(),
        )
        closed_image = self._grab(closed_rect)
        self._mark_trace(
            trace, "capture_completed", capture_mode="closed",
            image_width=closed_image.width(), image_height=closed_image.height(),
        )
        closed_prepared = prepare_desecration_frame(closed_image)
        self._mark_frame_prepared(trace, closed_prepared, "closed")
        if not closed_prepared.valid_panel:
            self._finish_error(
                "冒涜Modの3択を検出できませんでした。",
                failure_stage="closed_frame_preparation",
            )
            return False
        self._capture_rect = QRect(closed_rect)
        self._bands = closed_prepared.bands
        self.status.emit("閉じた状態の範囲で再確認しています…")
        threading.Thread(
            target=self._process,
            args=(closed_prepared, QRect(closed_rect), generation, False, "closed"),
            daemon=True,
        ).start()
        return True

    def _grab(self, rect):
        screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return QImage()
        return screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height()).toImage()

    def _process(self, prepared, capture_rect, generation, allow_closed, capture_mode):
        trace = self._active_trace
        try:
            if generation != self._scan_generation:
                self._mark_trace(trace, "scan_completed", outcome="stale_worker")
                return
            self._mark_trace(trace, "worker_started", capture_mode=capture_mode)
            images = [image_bytes(image) for variants in prepared.variants for image in variants]
            self._mark_trace(
                trace, "image_encoding_completed", capture_mode=capture_mode,
                image_count=len(images), encoded_bytes=sum(len(image) for image in images),
            )
            self._ocr.start()
            self._mark_trace(trace, "ocr_start_completed", capture_mode=capture_mode)
            raw = self._ocr.recognize(images)
            self._mark_trace(
                trace, "ocr_recognition_completed", capture_mode=capture_mode,
                result_count=len(raw),
                nonempty_result_count=sum(bool(str(value).strip()) for value in raw),
                character_count=sum(len(str(value)) for value in raw),
            )
            width = len(prepared.variants[0])
            grouped = tuple(tuple(raw[index * width:(index + 1) * width]) for index in range(3))
            resolution = resolve_ocr_variants(grouped, selectable_categories())
            self._mark_trace(
                trace, "tier_resolution_completed", capture_mode=capture_mode,
                category_count=len(resolution.categories),
                needs_category_choice=bool(resolution.needs_category_choice),
                fallback_status_count=len(resolution.fallback_statuses or ()),
            )
            if not resolution.categories:
                if allow_closed:
                    self._mark_trace(
                        trace, "closed_fallback_requested",
                        reason="open_result_unresolved",
                    )
                    self._retry_closed_requested.emit(generation)
                    return
                if not resolution.fallback_statuses or all(
                    status == "read_failed" for status in resolution.fallback_statuses
                ):
                    raise RuntimeError("3つのModを読み取れませんでした。読取範囲を確認してください。")
            self._mark_trace(trace, "result_queued", capture_mode=capture_mode)
            self._ready.emit(
                resolution, self._client_rect, capture_rect, prepared.bands, generation,
            )
        except Exception as exc:  # noqa: BLE001 - worker boundary reports to UI
            if generation == self._scan_generation:
                self._finish_error(
                    str(exc), failure_stage="worker",
                    error_type=type(exc).__name__,
                )

    def _show_result(self, resolution, client_rect, capture_rect, bands, generation):
        if generation != self._scan_generation:
            return
        self._mark_trace(self._active_trace, "result_received")
        self._running = False
        self._release_scan()
        if not resolution.categories:
            count = len(bands)
            statuses = resolution.fallback_statuses or ("read_failed",) * count
            self._display(
                client_rect, capture_rect, bands,
                resolution.fallback_tiers or (None,) * count,
                statuses=statuses,
                range_labels=resolution.fallback_ranges or ((),) * count,
            )
            return
        if resolution.needs_category_choice:
            self._pending = (resolution, client_rect, capture_rect, bands)
            anchor = QPoint(capture_rect.left(), capture_rect.bottom() + 8)
            self._category_overlay.show_categories(resolution.categories, anchor)
            self._mark_trace(
                self._active_trace, "category_choice_displayed",
                category_count=len(resolution.categories),
            )
            self.status.emit("装備の種類を選択してください。")
            return
        tiers = resolution.tiers
        if tiers is None:
            self._finish_error("Tierを一意に特定できませんでした。")
            return
        self._display(
            client_rect, capture_rect, bands, tiers,
            statuses=resolution.statuses or (), range_labels=resolution.ranges or (),
        )

    def _category_selected(self, category):
        if self._pending is None:
            return
        resolution, client_rect, capture_rect, bands = self._pending
        self._pending = None
        self._mark_trace(self._active_trace, "category_selected")
        self._display(
            client_rect, capture_rect, bands,
            resolution.tiers_by_category[category],
            statuses=resolution.statuses_by_category[category],
            range_labels=resolution.ranges_by_category[category],
        )

    def _category_cancelled(self):
        if self._pending is None:
            return
        _resolution, client_rect, capture_rect, bands = self._pending
        self._pending = None
        self._mark_trace(self._active_trace, "category_cancelled")
        count = len(bands)
        self._display(
            client_rect, capture_rect, bands, (None,) * count,
            statuses=("category_unselected",) * count,
            range_labels=((),) * count,
        )

    def _display(
        self, client_rect, capture_rect, bands, tiers, *, statuses=(), range_labels=(),
    ):
        config = self._regions_getter() or {}
        self._overlay.show_tiers(
            client_rect, capture_rect, (capture_rect.width(), capture_rect.height()), bands, tiers,
            statuses=statuses, range_labels=range_labels,
            show_ranges=bool(config.get("show_tier_ranges", True)),
        )
        self._monitor_misses = 0
        self._monitor.start()
        self._expiry.start()
        known = sum(tier is not None for tier in tiers)
        unresolved = [STATUS_LABELS.get(status, status) for tier, status in zip(
            tiers, statuses or ("matched",) * len(tiers),
        ) if tier is None]
        suffix = f"（{'、'.join(unresolved)}）" if unresolved else ""
        self.status.emit(f"{known}/3件のTierを表示しました。{suffix}")
        trace = self._active_trace
        self._mark_trace(
            trace, "overlay_displayed", resolved_count=known,
            unresolved_count=len(unresolved),
        )
        self._mark_trace(trace, "scan_completed", outcome="displayed")
        self._active_trace = None

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

    def _finish_error(self, message, *, failure_stage="unknown", error_type=None):
        self._running = False
        self._release_scan()
        trace = self._active_trace
        details = {"outcome": "failed", "failure_stage": failure_stage}
        if error_type is not None:
            details["error_type"] = error_type
        self._mark_trace(trace, "scan_completed", **details)
        self._active_trace = None
        self.failed.emit(message)

    def _create_trace(self):
        if self._trace_factory is None:
            return None
        try:
            return self._trace_factory()
        except Exception:  # noqa: BLE001 - diagnostics must never break scanning
            return None

    @staticmethod
    def _mark_trace(trace, event, **details):
        if trace is None:
            return
        try:
            trace.mark(event, **details)
        except Exception:  # noqa: BLE001, S110 - diagnostics must never break scanning
            pass

    def _mark_frame_prepared(self, trace, prepared, capture_mode):
        self._mark_trace(
            trace, "frame_preparation_completed", capture_mode=capture_mode,
            valid_panel=bool(prepared.valid_panel), band_count=len(prepared.bands),
            variant_count=sum(len(variants) for variants in prepared.variants),
        )

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
        trace = self._active_trace
        if trace is not None:
            self._mark_trace(trace, "scan_completed", outcome="controller_closed")
            self._active_trace = None
        self._scan_generation += 1
        self._running = False
        self.hide()
        self._release_scan()
        if self._owns_ocr:
            self._ocr.close()
