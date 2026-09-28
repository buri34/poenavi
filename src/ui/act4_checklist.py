"""PoE2 Act4攻略チェックの状態モデルとミニウィンドウ。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ui.dialog_theme import theme_asset_path
from src.ui.window_flags import _with_optional_mini_always_on_top

ACT4_CONTEXT_ZONE_IDS = frozenset(
    f"poe2_act4_area{index:02d}" for index in range(1, 18)
)
ACT4_TOWN_NAMES = frozenset({"キングスマーチ", "Kingsmarch"})


@dataclass(frozen=True)
class Act4ChecklistItem:
    zone_id: str
    label: str
    depth: int = 0
    parent_id: str | None = None


ACT4_REQUIRED_ITEMS = (
    Act4ChecklistItem("poe2_act4_area01", "キンの島（地図の切れ端 ①、経験値効率良）"),
    Act4ChecklistItem("poe2_act4_area02", "火山地帯", 1, "poe2_act4_area01"),
    Act4ChecklistItem("poe2_act4_area03", "ケッジ湾（地図の切れ端 ②）"),
    Act4ChecklistItem(
        "poe2_act4_area04",
        "旅の終わり（クエスト完了でスキルポイント+2）",
        1,
        "poe2_act4_area03",
    ),
    Act4ChecklistItem("poe2_act4_area05", "放棄された監獄（礼拝堂で永続バフ）"),
    Act4ChecklistItem("poe2_act4_area06", "監禁独房", 1, "poe2_act4_area05"),
    Act4ChecklistItem(
        "poe2_act4_area07",
        "ワーカパヌ島（地図の切れ端 ③、鮫ボスで永続バフ）",
    ),
    Act4ChecklistItem("poe2_act4_area08", "歌う大洞窟", 1, "poe2_act4_area07"),
    Act4ChecklistItem("poe2_act4_area09", "モズの島（地図の切れ端 ④）"),
    Act4ChecklistItem("poe2_act4_area10", "ヒネコラの目（永続バフ）"),
    Act4ChecklistItem(
        "poe2_act4_area11", "死者の殿堂（永続バフ）", 1, "poe2_act4_area10"
    ),
    Act4ChecklistItem(
        "poe2_act4_area12",
        "祖先の試練（スキルポイント+2）",
        2,
        "poe2_act4_area11",
    ),
    Act4ChecklistItem("poe2_act4_area13", "アラスタス"),
    Act4ChecklistItem("poe2_act4_area14", "発掘現場"),
)
ACT4_REQUIRED_ZONE_IDS = frozenset(item.zone_id for item in ACT4_REQUIRED_ITEMS)
_ITEMS_BY_ID = {item.zone_id: item for item in ACT4_REQUIRED_ITEMS}


def is_act4_context(
    zone_name: str | None,
    zone_id: str | None,
    act4_zone_ids: set[str] | frozenset[str] = ACT4_CONTEXT_ZONE_IDS,
) -> bool:
    """キングスマーチまたはAct4の全17エリアならTrue。"""
    return bool(zone_name in ACT4_TOWN_NAMES or zone_id in act4_zone_ids)


def _ancestor_ids(zone_id: str) -> set[str]:
    result: set[str] = set()
    current = _ITEMS_BY_ID.get(zone_id)
    while current and current.parent_id:
        result.add(current.parent_id)
        current = _ITEMS_BY_ID.get(current.parent_id)
    return result


def _descendant_ids(zone_id: str) -> set[str]:
    result: set[str] = set()
    pending = [zone_id]
    while pending:
        parent_id = pending.pop()
        children = [
            item.zone_id for item in ACT4_REQUIRED_ITEMS if item.parent_id == parent_id
        ]
        result.update(children)
        pending.extend(children)
    return result


@dataclass
class Act4ChecklistState:
    """保存可能なAct4攻略チェック状態。"""

    checked_zone_ids: set[str] = field(default_factory=set)
    optional_npc_checked: bool = False
    dismissed: bool = False
    position: tuple[int, int] | None = None

    @classmethod
    def from_dict(cls, raw: object) -> Act4ChecklistState:
        if not isinstance(raw, dict):
            return cls()
        checked = raw.get("checked_zone_ids", [])
        checked_ids = (
            {
                zone_id
                for zone_id in checked
                if isinstance(zone_id, str) and zone_id in ACT4_REQUIRED_ZONE_IDS
            }
            if isinstance(checked, list)
            else set()
        )
        raw_position = raw.get("position")
        position = None
        if isinstance(raw_position, dict):
            x = raw_position.get("x")
            y = raw_position.get("y")
            if isinstance(x, int) and isinstance(y, int):
                position = (x, y)
        return cls(
            checked_zone_ids=checked_ids,
            optional_npc_checked=bool(raw.get("optional_npc_checked", False)),
            dismissed=bool(raw.get("dismissed", False)),
            position=position,
        )

    def to_dict(self) -> dict:
        data = {
            "checked_zone_ids": sorted(self.checked_zone_ids),
            "optional_npc_checked": self.optional_npc_checked,
            "dismissed": self.dismissed,
        }
        if self.position is not None:
            data["position"] = {"x": self.position[0], "y": self.position[1]}
        return data

    @property
    def completed_count(self) -> int:
        return len(self.checked_zone_ids)

    @property
    def is_complete(self) -> bool:
        return self.completed_count == len(ACT4_REQUIRED_ITEMS)

    def mark_entered(self, zone_id: str | None) -> bool:
        if zone_id not in ACT4_REQUIRED_ZONE_IDS:
            return False
        before = set(self.checked_zone_ids)
        self.checked_zone_ids.add(zone_id)
        self.checked_zone_ids.update(_ancestor_ids(zone_id))
        return before != self.checked_zone_ids

    def set_checked(self, zone_id: str, checked: bool) -> bool:
        if zone_id not in ACT4_REQUIRED_ZONE_IDS:
            return False
        before = set(self.checked_zone_ids)
        if checked:
            self.checked_zone_ids.add(zone_id)
            self.checked_zone_ids.update(_ancestor_ids(zone_id))
        else:
            self.checked_zone_ids.discard(zone_id)
            self.checked_zone_ids.difference_update(_descendant_ids(zone_id))
        return before != self.checked_zone_ids


class Act4ChecklistWindow(QWidget):
    """みになびと一緒に使う、操作可能なAct4攻略チェック。"""

    required_toggled = Signal(str, bool)
    optional_toggled = Signal(bool)
    dismissed_by_user = Signal()
    position_changed = Signal(int, int)

    _FONT_PROFILES: ClassVar[dict[str, dict[str, int]]] = {
        "small": {
            "title": 15,
            "body": 12,
            "auxiliary": 12,
            "caption": 11,
            "row_height": 23,
            "indent": 17,
            "minimum_width": 460,
            "close_size": 28,
        },
        "medium": {
            "title": 18,
            "body": 15,
            "auxiliary": 14,
            "caption": 13,
            "row_height": 28,
            "indent": 20,
            "minimum_width": 550,
            "close_size": 32,
        },
        "large": {
            "title": 22,
            "body": 18,
            "auxiliary": 17,
            "caption": 16,
            "row_height": 34,
            "indent": 24,
            "minimum_width": 650,
            "close_size": 38,
        },
    }

    def __init__(self, main_window=None):
        super().__init__(None)
        self.main_window = main_window
        self.setWindowFlags(
            _with_optional_mini_always_on_top(
                Qt.Tool | Qt.FramelessWindowHint,
                main_window,
            )
        )
        self.setWindowTitle("Act4 攻略チェック")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._drag_offset: QPoint | None = None
        self._position_timer = QTimer(self)
        self._position_timer.setSingleShot(True)
        self._position_timer.timeout.connect(self._emit_position)
        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._fade_to_idle_opacity)
        self._checkboxes: dict[str, QCheckBox] = {}
        self.font_profile_name = "small"
        self.body_font_size = 12

        self.outer = QFrame(self)
        self.outer.setObjectName("act4ChecklistOuter")
        self.outer_layout = QVBoxLayout(self.outer)
        self.outer_layout.setContentsMargins(12, 9, 12, 11)
        self.outer_layout.setSpacing(4)

        self.title_bar = QFrame()
        self.title_bar.setCursor(QCursor(Qt.SizeAllCursor))
        self.title_bar.installEventFilter(self)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(0, 0, 0, 2)
        title_layout.setSpacing(8)
        self.title_label = QLabel("Act4 攻略チェック")
        self.title_label.setObjectName("act4ChecklistTitle")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        self.progress_label = QLabel("0 / 14")
        self.progress_label.setObjectName("act4ChecklistProgress")
        title_layout.addWidget(self.progress_label)
        self.close_button = QPushButton("×")
        self.close_button.setAccessibleName("Act4攻略チェックを閉じる")
        self.close_button.setToolTip(
            "このキャラクターでは自動表示しません。Act4ボタンから再表示できます"
        )
        self.close_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.close_button.clicked.connect(self._dismiss)
        title_layout.addWidget(self.close_button)
        self.outer_layout.addWidget(self.title_bar)

        for item in ACT4_REQUIRED_ITEMS:
            if item.depth == 0 and self._checkboxes:
                self.outer_layout.addSpacing(2)
            prefix = "" if item.depth == 0 else f"{'   ' * (item.depth - 1)}└  "
            checkbox = QCheckBox(f"{prefix}{item.label}")
            checkbox.setProperty("checklistLabel", f"{prefix}{item.label}")
            checkbox.setProperty("checklistDepth", item.depth)
            checkbox.setCursor(QCursor(Qt.PointingHandCursor))
            checkbox.setAccessibleName(f"{item.label} 入場済み")
            checkbox.toggled.connect(
                lambda checked, zone_id=item.zone_id: self.required_toggled.emit(
                    zone_id, checked
                )
            )
            self._checkboxes[item.zone_id] = checkbox
            self.outer_layout.addWidget(checkbox)

        self.complete_label = QLabel("✓ Act4の攻略必須エリアをすべて完了済み")
        self.complete_label.setObjectName("act4ChecklistComplete")
        self.complete_label.setWordWrap(True)
        self.complete_label.hide()
        self.outer_layout.addWidget(self.complete_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: rgba(176,255,123,90); margin-top: 5px;")
        self.outer_layout.addWidget(separator)
        self.optional_frame = QFrame()
        self.optional_frame.setObjectName("act4OptionalFrame")
        optional_layout = QVBoxLayout(self.optional_frame)
        optional_layout.setContentsMargins(8, 5, 8, 6)
        optional_layout.setSpacing(2)
        self.optional_title = QLabel("任意のお得ポイント")
        self.optional_title.setObjectName("act4OptionalTitle")
        optional_layout.addWidget(self.optional_title)
        self.optional_checkbox = QCheckBox("ナカヌの装備販売NPCを確認")
        self.optional_checkbox.setProperty(
            "checklistLabel", "ナカヌの装備販売NPCを確認"
        )
        self.optional_checkbox.setCursor(QCursor(Qt.PointingHandCursor))
        self.optional_checkbox.setAccessibleName("ナカヌの装備販売NPCを確認済み")
        self.optional_checkbox.toggled.connect(self.optional_toggled.emit)
        optional_layout.addWidget(self.optional_checkbox)
        self.optional_note = QLabel("発掘現場を攻略前に立ち寄る")
        self.optional_note.setObjectName("act4OptionalNote")
        optional_layout.addWidget(self.optional_note)
        self.outer_layout.addWidget(self.optional_frame)
        self.set_optional_available(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.outer)
        self.apply_settings()

    def apply_state(self, state: Act4ChecklistState):
        for zone_id, checkbox in self._checkboxes.items():
            checkbox.blockSignals(True)
            checked = zone_id in state.checked_zone_ids
            checkbox.setChecked(checked)
            checkbox.blockSignals(False)
        self.optional_checkbox.blockSignals(True)
        self.optional_checkbox.setChecked(state.optional_npc_checked)
        self.optional_checkbox.blockSignals(False)
        self.progress_label.setText(
            f"{state.completed_count} / {len(ACT4_REQUIRED_ITEMS)}"
        )
        self.complete_label.setVisible(state.is_complete)

    def _mini_navi_config(self) -> dict:
        config = getattr(self.main_window, "config", {}) if self.main_window else {}
        mini_config = (
            config.get("mini_guide_overlay", {}) if isinstance(config, dict) else {}
        )
        return mini_config if isinstance(mini_config, dict) else {}

    def _font_profile(self) -> tuple[str, dict[str, int]]:
        font_size = int(self._mini_navi_config().get("font_size", 18))
        if font_size <= 16:
            name = "small"
        elif font_size <= 20:
            name = "medium"
        else:
            name = "large"
        return name, self._FONT_PROFILES[name]

    def apply_settings(self, refresh_window_flags: bool = False):
        if refresh_window_flags:
            self.apply_window_flags()
        self.font_profile_name, profile = self._font_profile()
        self.body_font_size = profile["body"]
        self.setMinimumWidth(profile["minimum_width"])
        self.close_button.setFixedSize(profile["close_size"], profile["close_size"])
        for checkbox in self._checkboxes.values():
            depth = int(checkbox.property("checklistDepth") or 0)
            checkbox.setContentsMargins(depth * profile["indent"], 0, 0, 0)
        checked_asset = str(theme_asset_path("ui-checkbox-checked.svg")).replace(
            "\\", "/"
        )
        self.outer.setStyleSheet(f"""
            #act4ChecklistOuter {{
                background-color: rgba(10, 10, 10, 242);
                border: 1px solid rgba(176, 255, 123, 165);
                border-radius: 8px;
            }}
            QLabel {{ color: #ffffff; background: transparent; }}
            #act4ChecklistTitle {{
                color: #b0ff7b; font-size: {profile["title"]}px; font-weight: bold;
            }}
            #act4ChecklistProgress {{
                color: #dddddd; font-size: {profile["auxiliary"]}px; font-weight: bold;
            }}
            QCheckBox {{
                color: #f0f0f0; font-size: {profile["body"]}px; spacing: 8px;
                min-height: {profile["row_height"]}px; background: transparent;
            }}
            QCheckBox:focus {{
                border: 1px solid rgba(176, 255, 123, 210); border-radius: 3px;
            }}
            QCheckBox::indicator {{
                width: 18px; height: 18px; border: 2px solid #888888;
                border-radius: 4px; background: transparent;
            }}
            QCheckBox::indicator:checked {{
                image: url("{checked_asset}"); background: #4488ff;
                border: 2px solid #4488ff;
            }}
            QCheckBox::indicator:unchecked:hover {{ border-color: #ffffff; }}
            #act4ChecklistComplete {{
                color: #b0ff7b; font-size: {profile["auxiliary"]}px; font-weight: bold;
                padding: 6px; border: 1px solid rgba(176,255,123,120); border-radius: 4px;
            }}
            #act4OptionalTitle {{
                color: #f0c674; font-size: {profile["auxiliary"]}px; font-weight: bold;
            }}
            #act4OptionalNote {{
                color: #bbbbbb; font-size: {profile["caption"]}px; padding-left: 25px;
            }}
            QPushButton {{
                color: #ffffff; background: #252525; border: 1px solid #777777;
                border-radius: 5px; font-size: {profile["title"] + 3}px; font-weight: bold;
            }}
            QPushButton:hover, QPushButton:focus {{
                background: #743838; border-color: #ff9999;
            }}
            QPushButton:pressed {{ background: #552828; }}
        """)
        self.adjustSize()
        self.resize(self.sizeHint())
        self._show_strong_opacity(restart_fade=self.isVisible())

    def _fade_enabled(self) -> bool:
        return bool(self._mini_navi_config().get("fade_enabled", True))

    def _show_strong_opacity(self, restart_fade: bool = False):
        self._fade_timer.stop()
        self.setWindowOpacity(1.0)
        if restart_fade:
            self._maybe_start_fade_timer()

    def _fade_to_idle_opacity(self):
        if not self._fade_enabled() or not self.isVisible():
            return
        opacity = float(self._mini_navi_config().get("faded_opacity", 0.38))
        self.setWindowOpacity(max(0.15, min(opacity, 1.0)))

    def _maybe_start_fade_timer(self):
        if not self.isVisible() or not self._fade_enabled():
            return
        delay_ms = int(self._mini_navi_config().get("fade_delay_ms", 5000))
        self._fade_timer.start(max(500, delay_ms))

    def set_optional_available(self, available: bool):
        """開始条件確定後に、利用期間中だけ強調できる公開口。"""
        if available:
            style = (
                "#act4OptionalFrame { background: rgba(98,72,22,150); "
                "border: 1px solid #f0c674; border-radius: 5px; }"
            )
        else:
            style = (
                "#act4OptionalFrame { background: rgba(35,35,35,145); "
                "border: 1px solid rgba(240,198,116,70); border-radius: 5px; }"
            )
        self.optional_frame.setStyleSheet(style)

    def apply_window_flags(self):
        was_visible = self.isVisible()
        self.setWindowFlags(
            _with_optional_mini_always_on_top(
                Qt.Tool | Qt.FramelessWindowHint,
                self.main_window,
            )
        )
        if was_visible:
            self.show()

    def showEvent(self, event):
        self._show_strong_opacity(restart_fade=True)
        super().showEvent(event)

    def hideEvent(self, event):
        self._fade_timer.stop()
        super().hideEvent(event)

    def enterEvent(self, event):
        self._show_strong_opacity(restart_fade=False)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._maybe_start_fade_timer()
        super().leaveEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.title_bar:
            if event.type() == QEvent.MouseButtonPress and isinstance(
                event, QMouseEvent
            ):
                if event.button() == Qt.LeftButton:
                    self._drag_offset = (
                        event.globalPosition().toPoint()
                        - self.frameGeometry().topLeft()
                    )
                    return True
            elif event.type() == QEvent.MouseMove and isinstance(event, QMouseEvent):
                if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
                    self.move(event.globalPosition().toPoint() - self._drag_offset)
                    return True
            elif event.type() == QEvent.MouseButtonRelease:
                self._drag_offset = None
                return True
        return super().eventFilter(watched, event)

    def moveEvent(self, event):
        self._position_timer.start(250)
        super().moveEvent(event)

    def _emit_position(self):
        if self.isVisible():
            self.position_changed.emit(self.x(), self.y())

    def _dismiss(self):
        self.hide()
        self.dismissed_by_user.emit()
