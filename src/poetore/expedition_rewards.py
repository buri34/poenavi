"""Runtime OCR and unit-price helpers for the PoE2 Expedition reward panel."""

from __future__ import annotations

import json
import os
import sys
import threading
from collections import Counter
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from src.poetore.expedition_ocr_probe import (
    PreparedOcrFrame,
    RowBand,
    WindowsOcrServer,
    match_item_name,
    normalize_text,
    prepare_qimage_rows,
    prepare_retry_row_images,
    strip_quantity,
)
from src.poetore.window_position import path_of_exile_client_rect

EXPEDITION_PRICE_FONT_SIZE = 14
EXPEDITION_PRICE_BACKGROUND = QColor(0, 0, 0, 190)
EXPEDITION_PRICE_CORNER_RADIUS = 5
EXPEDITION_PRICE_HORIZONTAL_PADDING = 6
EXPEDITION_PRICE_VERTICAL_PADDING = 3
EXPEDITION_PRICE_ICON_SIZE = 24
EXPEDITION_PRICE_ICON_GAP = 5
# QPainter strokes are centered on the glyph path, so width 4 creates a
# visible outline of about 2 px outside the filled text.
EXPEDITION_PRICE_TEXT_OUTLINE_PEN_WIDTH = 4
EXPEDITION_DIAGNOSTIC_ENV = "POENAVI_EXPEDITION_DIAGNOSTICS"
EXPEDITION_DIAGNOSTIC_FLAG = "expedition-diagnostics.flag"


def expedition_diagnostics_enabled(marker_root: Path | None = None) -> bool:
    enabled = os.environ.get(EXPEDITION_DIAGNOSTIC_ENV, "").strip().casefold()
    if enabled in {"1", "true", "yes", "on"}:
        return True
    root = marker_root or Path(sys.executable).resolve().parent
    return (root / EXPEDITION_DIAGNOSTIC_FLAG).is_file()


def format_expedition_diagnostic_report(steps: list[str]) -> str:
    body = "\n".join(steps) if steps else "診断情報を取得できませんでした。"
    return (
        "エクスペディション報酬OCR 診断結果\n\n"
        f"{body}\n\n"
        "この画面全体をスクリーンショットして送ってください。"
    )


@dataclass(frozen=True)
class RewardIdentity:
    top: int
    bottom: int
    japanese_name: str
    english_name: str
    exact_match: bool = False


@dataclass(frozen=True)
class RewardPriceRow:
    top: int
    bottom: int
    text: str
    unit_price: float
    highlighted: bool = False


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


def load_reward_alias_bundle(path: Path | None = None) -> tuple[dict[str, str], str]:
    source = path or (
        Path(__file__).resolve().parents[2]
        / "data" / "poetore" / "poe2" / "expedition_ocr_items.json"
    )
    content = source.read_bytes()
    loaded = json.loads(content.decode("utf-8"))
    aliases = {
        str(row["ja"]): str(row["en"])
        for row in loaded.get("items", ())
        if row.get("ja") and row.get("en")
    }
    return aliases, sha256(content).hexdigest()


class SafeRewardNameResolver:
    """Cache only trusted OCR resolutions, scoped to the exact dictionary."""

    def __init__(self, aliases: dict[str, str], dictionary_version: str):
        self.aliases = aliases
        self.dictionary_version = dictionary_version
        self._candidates = tuple(aliases)
        self._cache: dict[tuple[str, str], tuple[str, str, bool]] = {}

    def resolve(self, raw_text: str) -> tuple[str, str, bool] | None:
        _quantity, item_text = strip_quantity(raw_text)
        key = (self.dictionary_version, normalize_text(item_text))
        if not key[1]:
            return None
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        best, score, _margin, trusted = match_item_name(
            item_text, self._candidates,
        )
        if not trusted:
            return None
        exact_match = score == 1.0
        resolved = (best, self.aliases[best], exact_match)
        if len(self._cache) >= 2048:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = resolved
        return resolved


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
        named_rows = [row for row in rows if row.english_name]
        votes = Counter(row.english_name for row in named_rows)
        if not votes:
            continue
        name, count = votes.most_common(1)[0]
        if count >= required_votes:
            agreeing = [row for row in named_rows if row.english_name == name]
        else:
            exact_rows = [row for row in named_rows if row.exact_match]
            exact_names = {row.english_name for row in exact_rows}
            if len(exact_names) != 1:
                continue
            exact_name = exact_names.pop()
            agreeing = [row for row in exact_rows if row.english_name == exact_name]
        agreeing.sort(key=lambda row: (row.top, row.bottom))
        middle = agreeing[len(agreeing) // 2]
        stable.append(middle)
    return stable


def select_retry_resolution(
    resolved: list[tuple[str, str, bool] | None],
) -> tuple[str, str, bool] | None:
    """Select one safe identity from alternate views of the same source row."""
    valid = [value for value in resolved if value is not None]
    if not valid:
        return None
    exact = [value for value in valid if value[2]]
    exact_names = {value[1] for value in exact}
    if len(exact_names) > 1:
        return None
    if exact:
        return exact[0]
    names = {value[1] for value in valid}
    return valid[0] if len(names) == 1 else None


def retry_unresolved_identities(
    prepared: list[PreparedOcrFrame],
    frames: list[list[RewardIdentity]],
    ocr: WindowsOcrServer,
    resolver: SafeRewardNameResolver,
) -> tuple[int, int, list[str]]:
    """Retry only unresolved rows with alternate preprocessing variants."""
    requests: list[bytes] = []
    groups: list[tuple[int, int, int]] = []
    max_rows = max((len(frame) for frame in frames), default=0)
    already_stable = {
        row_index
        for row_index in range(max_rows)
        if stable_reward_identities([
            [frame[row_index]] if row_index < len(frame) else []
            for frame in frames
        ])
    }
    for frame_index, (prepared_frame, frame) in enumerate(zip(prepared, frames)):
        unresolved = [
            row_index
            for row_index, row in enumerate(frame)
            if not row.english_name and row_index not in already_stable
        ]
        if not unresolved:
            continue
        retry_images = prepare_retry_row_images(prepared_frame, unresolved)
        for row_index, images in retry_images.items():
            groups.append((frame_index, row_index, len(images)))
            requests.extend(images)
    if not requests:
        return 0, 0, []

    raw_texts = ocr.recognize(requests)
    recovered = 0
    offset = 0
    for frame_index, row_index, image_count in groups:
        raw_group = raw_texts[offset : offset + image_count]
        offset += image_count
        selected = select_retry_resolution([
            resolver.resolve(raw_text) for raw_text in raw_group
        ])
        if selected is None:
            continue
        japanese_name, english_name, exact_match = selected
        row = frames[frame_index][row_index]
        frames[frame_index][row_index] = RewardIdentity(
            row.top,
            row.bottom,
            japanese_name,
            english_name,
            exact_match,
        )
        recovered += 1
    return recovered, len(groups), raw_texts


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


def expedition_exalted_icon_path() -> Path:
    """Resolve the bundled PoE2 Exalted Orb icon in dev and packaged runs."""
    source_root = Path(__file__).resolve().parents[2]
    executable_root = Path(sys.executable).resolve().parent
    roots = (executable_root, Path(getattr(sys, "_MEIPASS", source_root)), source_root)
    for root in roots:
        path = root / "assets" / "icons" / "ExaltedOrb2.png"
        if path.is_file():
            return path
    return source_root / "assets" / "icons" / "ExaltedOrb2.png"


def reward_price_text_color(row: RewardPriceRow) -> QColor:
    return QColor("#B0FF7B" if row.highlighted else "#FFFFFF")


def highlight_highest_price_rows(rows: list[RewardPriceRow]) -> list[RewardPriceRow]:
    if not rows:
        return []
    highest_price = max(row.unit_price for row in rows)
    return [replace(row, highlighted=row.unit_price == highest_price) for row in rows]


def price_label_x(display_width: int, source_width: int, panel_width: int) -> int:
    """Place price text immediately to the right of the detected reward panel."""
    if display_width <= 0 or source_width <= 0:
        return 8
    scaled_panel_right = round(panel_width * display_width / source_width)
    return max(8, min(display_width - 8, scaled_panel_right + 8))


def expedition_capture_rect(client_rect: QRect) -> QRect:
    """Capture only the left area that can contain the Expedition panel."""
    width = min(client_rect.width(), max(1, round(client_rect.height() * 0.70)))
    return QRect(client_rect.x(), client_rect.y(), width, client_rect.height())


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
        self._exalted_icon = QPixmap(str(expedition_exalted_icon_path()))
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
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        font = QFont("Yu Gothic UI", EXPEDITION_PRICE_FONT_SIZE)
        font.setBold(True)
        painter.setFont(font)
        x = price_label_x(self.width(), self._source_width, self._panel_width)
        scale_y = self.height() / self._source_height
        metrics = painter.fontMetrics()
        for row in self._rows:
            y = round(((row.top + row.bottom) / 2) * scale_y)
            has_icon = not self._exalted_icon.isNull()
            text_width = metrics.horizontalAdvance(row.text)
            content_width = text_width
            if has_icon:
                content_width += EXPEDITION_PRICE_ICON_SIZE + EXPEDITION_PRICE_ICON_GAP
            content_height = max(EXPEDITION_PRICE_ICON_SIZE if has_icon else 0, metrics.height())
            plate_width = content_width + EXPEDITION_PRICE_HORIZONTAL_PADDING * 2
            plate_height = content_height + EXPEDITION_PRICE_VERTICAL_PADDING * 2
            plate = QRectF(x, y - plate_height / 2, plate_width, plate_height)

            painter.setPen(Qt.NoPen)
            painter.setBrush(EXPEDITION_PRICE_BACKGROUND)
            painter.drawRoundedRect(
                plate,
                EXPEDITION_PRICE_CORNER_RADIUS,
                EXPEDITION_PRICE_CORNER_RADIUS,
            )

            content_x = x + EXPEDITION_PRICE_HORIZONTAL_PADDING
            text_x = content_x
            if has_icon:
                painter.drawPixmap(
                    round(content_x),
                    y - EXPEDITION_PRICE_ICON_SIZE // 2,
                    EXPEDITION_PRICE_ICON_SIZE,
                    EXPEDITION_PRICE_ICON_SIZE,
                    self._exalted_icon,
                )
                text_x += EXPEDITION_PRICE_ICON_SIZE + EXPEDITION_PRICE_ICON_GAP
            baseline = y + (metrics.ascent() - metrics.descent()) / 2
            text_path = QPainterPath()
            text_path.addText(text_x, baseline, font, row.text)
            painter.setPen(QPen(
                QColor(0, 0, 0, 255),
                EXPEDITION_PRICE_TEXT_OUTLINE_PEN_WIDTH,
                Qt.SolidLine,
                Qt.RoundCap,
                Qt.RoundJoin,
            ))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(text_path)
            painter.fillPath(text_path, reward_price_text_color(row))


class ExpeditionRewardController(QObject):
    status = Signal(str)
    failed = Signal(str)
    diagnostic = Signal(str)
    _ready = Signal(object, object, object, object, object)

    def __init__(self, league_getter, parent=None, *, diagnostics_enabled=None):
        super().__init__(parent)
        self._league_getter = league_getter
        self._overlay = ExpeditionPriceOverlay()
        aliases, dictionary_version = load_reward_alias_bundle()
        self._name_resolver = SafeRewardNameResolver(aliases, dictionary_version)
        self._ocr = WindowsOcrServer()
        self._captures: list[QImage] = []
        self._client_rect: QRect | None = None
        self._capture_rect: QRect | None = None
        self._running = False
        self._helper_warm_started = False
        self._price_warm_running = False
        self._monitor_misses = 0
        self._bands: list[RowBand] = []
        self._panel_width = 0
        self._diagnostics_enabled = (
            expedition_diagnostics_enabled()
            if diagnostics_enabled is None else bool(diagnostics_enabled)
        )
        self._diagnostic_steps: list[str] = []
        self._monitor = QTimer(self)
        self._monitor.setInterval(650)
        self._monitor.timeout.connect(self._check_panel)
        self._ready.connect(self._show_result)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.close)

    @property
    def running(self) -> bool:
        return self._running

    def hide(self) -> None:
        self._overlay.hide()
        self._monitor.stop()

    def close(self) -> None:
        self.hide()
        self._ocr.close()

    def warm_up(self) -> None:
        if not self._helper_warm_started:
            self._helper_warm_started = True
            threading.Thread(target=self._warm_ocr, daemon=True).start()
        if not self._price_warm_running:
            self._price_warm_running = True
            threading.Thread(target=self._warm_prices, daemon=True).start()

    def _warm_ocr(self) -> None:
        try:
            self._ocr.start()
        except Exception:  # noqa: BLE001 - warm-up failure is retried by scan
            # A scan retries startup and reports the actionable error to the user.
            self._helper_warm_started = False

    def _warm_prices(self) -> None:
        try:
            from src.poetore.poe_ninja import default_poe_ninja_service

            default_poe_ninja_service.prefetch_poe2_expedition_rewards(
                self._league_getter(),
            )
        except Exception:  # noqa: BLE001, S110 - on-demand lookup remains available
            pass
        finally:
            self._price_warm_running = False

    def request_scan(self) -> bool:
        if self._running:
            return False
        self._diagnostic_steps = []
        client_rect = path_of_exile_client_rect()
        if client_rect is None:
            self._trace(
                "❌ 1. ゲーム画面検出: "
                "Path of Exileのゲーム画面が見つかりませんでした。"
            )
            self._finish_error("Path of Exileのゲーム画面が見つかりませんでした。")
            return False
        self._trace(
            f"✅ 1. ゲーム画面検出: {client_rect.width()}x{client_rect.height()}"
        )
        self._running = True
        self.hide()
        self._client_rect = QRect(client_rect)
        self._capture_rect = expedition_capture_rect(client_rect)
        self._captures = []
        self.warm_up()
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
            self._trace("❌ 2. 画面キャプチャ: 画像を取得できません")
            self._finish_error("ゲーム画面をキャプチャできませんでした。")
            return
        self._captures.append(image)
        if len(self._captures) < 3:
            QTimer.singleShot(220, self._capture_frame)
            return
        self._trace("✅ 2. 画面キャプチャ: 3/3枚")
        images = list(self._captures)
        client_rect = QRect(self._client_rect)
        capture_rect = QRect(self._capture_rect)
        threading.Thread(
            target=self._process, args=(images, client_rect, capture_rect), daemon=True,
        ).start()

    def _process(
        self, images: list[QImage], client_rect: QRect, capture_rect: QRect,
    ) -> None:
        try:
            prepared: list[PreparedOcrFrame] = [
                prepare_qimage_rows(
                    image,
                    scan_width=round(image.height() * 0.55),
                    full_screen=True,
                )
                for image in images
            ]
            row_counts = "/".join(str(len(frame.images)) for frame in prepared)
            self._trace(f"✅ 3. 報酬行検出: {row_counts}行")
            all_crops = [
                crop for frame in prepared for crop in frame.images
            ]
            try:
                self._ocr.start()
            except Exception as exc:
                self._trace(f"❌ 4. Windows日本語OCR起動: {exc}")
                raise
            self._trace("✅ 4. Windows日本語OCR起動: ja-JP 利用可能")
            raw_texts = self._ocr.recognize(all_crops)
            non_empty_count = sum(bool(text.strip()) for text in raw_texts)
            self._trace(
                f"✅ 5. OCR応答: {non_empty_count}/{len(all_crops)}行に文字あり"
            )
            offset = 0
            frames: list[list[RewardIdentity]] = []
            for prepared_frame in prepared:
                frame: list[RewardIdentity] = []
                for band, raw in zip(
                    prepared_frame.bands,
                    raw_texts[offset:offset + len(prepared_frame.images)],
                ):
                    resolved = self._name_resolver.resolve(raw)
                    if resolved is not None:
                        japanese_name, english_name, exact_match = resolved
                        frame.append(RewardIdentity(
                            band.top,
                            band.bottom,
                            japanese_name,
                            english_name,
                            exact_match,
                        ))
                    else:
                        frame.append(RewardIdentity(
                            band.top, band.bottom, "", "",
                        ))
                frames.append(frame)
                offset += len(prepared_frame.images)
            recovered, retry_count, retry_raw_texts = retry_unresolved_identities(
                prepared,
                frames,
                self._ocr,
                self._name_resolver,
            )
            if retry_count:
                self._trace(
                    f"✅ 5b. 失敗行再OCR: {recovered}/{retry_count}行を追加確定"
                )
            stable = [row for row in stable_reward_identities(frames) if row.english_name]
            resolved_counts = "/".join(
                str(sum(bool(row.english_name) for row in frame)) for frame in frames
            )
            self._trace(
                f"✅ 6. 名称照合: 各フレーム {resolved_counts}件、安定確定 {len(stable)}件"
            )
            if not stable:
                samples = list(dict.fromkeys(
                    normalize_text(text)
                    for text in [*raw_texts, *retry_raw_texts]
                    if text.strip()
                ))[:5]
                if samples:
                    self._trace("   OCR文字例: " + " / ".join(samples))
                raise RuntimeError("安全に特定できる報酬名がありませんでした。")

            from src.poetore.poe_ninja import default_poe_ninja_service

            league = self._league_getter()
            try:
                prices = default_poe_ninja_service.lookup_poe2_expedition_rewards(
                    tuple(row.english_name for row in stable), league,
                )
                exalted_chaos = default_poe_ninja_service.exalted_chaos_rate(league)
            except Exception as exc:
                self._trace(f"❌ 7. poe.ninja価格取得: {exc}")
                raise
            if not exalted_chaos:
                raise RuntimeError("高貴なオーブの換算レートを取得できませんでした。")
            priced = [
                (row, prices[row.english_name].chaos / exalted_chaos)
                for row in stable
                if row.english_name in prices and prices[row.english_name].chaos > 0
            ]
            self._trace(
                f"✅ 7. poe.ninja価格取得: {len(priced)}/{len(stable)}件（{league}）"
            )
            shown = highlight_highest_price_rows([
                RewardPriceRow(
                    row.top,
                    row.bottom,
                    format_exalted_unit_price(value),
                    value,
                )
                for row, value in priced
            ])
            if not shown:
                raise RuntimeError("特定した報酬のpoe.ninja価格が見つかりませんでした。")
            first = prepared[0]
            source_width = round(
                first.width * client_rect.width() / max(1, capture_rect.width())
            )
            self._ready.emit(
                client_rect, shown, (source_width, first.height),
                (first.panel_width, list(first.bands)), len(stable),
            )
        except Exception as exc:  # noqa: BLE001 - worker boundary reports to UI
            self._finish_error(str(exc))

    def _show_result(self, client_rect, rows, source_size, panel_data, stable_count):
        self._running = False
        self._panel_width, self._bands = panel_data
        self._client_rect = QRect(client_rect)
        self._capture_rect = expedition_capture_rect(client_rect)
        try:
            self._overlay.show_prices(
                client_rect, source_size[0], source_size[1], self._panel_width, rows,
            )
        except Exception as exc:  # noqa: BLE001 - final UI boundary is diagnosed
            self._trace(f"❌ 8. オーバーレイ表示: {exc}")
            self._finish_error(f"価格表示に失敗しました: {exc}")
            return
        self._monitor_misses = 0
        self._monitor.start()
        self.status.emit(f"{len(rows)}/{stable_count}件の単価を表示しました。")
        self._trace(f"✅ 8. オーバーレイ表示: {len(rows)}/{stable_count}件")
        self._emit_diagnostic()

    def _finish_error(self, message: str) -> None:
        self._running = False
        self.failed.emit(message)
        if not self._diagnostic_steps or not self._diagnostic_steps[-1].startswith("❌"):
            self._trace(f"❌ 処理停止: {message}")
        self._emit_diagnostic()

    def _trace(self, message: str) -> None:
        if self._diagnostics_enabled:
            self._diagnostic_steps.append(message)

    def _emit_diagnostic(self) -> None:
        if self._diagnostics_enabled:
            self.diagnostic.emit(
                format_expedition_diagnostic_report(self._diagnostic_steps)
            )

    def _check_panel(self) -> None:
        image = self._grab_game()
        if reward_cards_still_visible(image, self._bands, self._panel_width):
            self._monitor_misses = 0
            return
        self._monitor_misses += 1
        if self._monitor_misses >= 2:
            self.hide()
            self.status.emit("エクスペディション報酬画面を閉じたため表示を消しました。")
