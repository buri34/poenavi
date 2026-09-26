"""PoE2 Act4攻略チェックの状態モデルとミニウィンドウ。"""

from __future__ import annotations

from dataclasses import dataclass, field

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

from src.ui.window_flags import _with_optional_mini_always_on_top

ACT4_CONTEXT_ZONE_IDS = frozenset(
    f"poe2_act4_area{index:02d}" for index in range(1, 18)
)
ACT4_TOWN_NAMES = frozenset({"キングスマーチ", "Kingsmarch"})


@dataclass(frozen=True)
class Act4ChecklistItem:
    zone_id: str
    label: str
    number: int | None
    depth: int = 0
    parent_id: str | None = None


ACT4_REQUIRED_ITEMS = (
    Act4ChecklistItem("poe2_act4_area01", "キンの島", 1),
    Act4ChecklistItem("poe2_act4_area02", "火山地帯", None, 1, "poe2_act4_area01"),
    Act4ChecklistItem("poe2_act4_area03", "ケッジ湾", 2),
    Act4ChecklistItem("poe2_act4_area04", "旅の終わり", None, 1, "poe2_act4_area03"),
    Act4ChecklistItem("poe2_act4_area05", "放棄された監獄", 3),
    Act4ChecklistItem("poe2_act4_area06", "監禁独房", None, 1, "poe2_act4_area05"),
    Act4ChecklistItem("poe2_act4_area07", "ワーカパヌ島", 4),
    Act4ChecklistItem("poe2_act4_area08", "歌う大洞窟", None, 1, "poe2_act4_area07"),
    Act4ChecklistItem("poe2_act4_area09", "モズの島", 5),
    Act4ChecklistItem("poe2_act4_area10", "ヒネコラの目", 6),
    Act4ChecklistItem("poe2_act4_area11", "死者の殿堂", None, 1, "poe2_act4_area10"),
    Act4ChecklistItem("poe2_act4_area12", "祖先の試練", None, 2, "poe2_act4_area11"),
    Act4ChecklistItem("poe2_act4_area13", "アラスタス", 7),
    Act4ChecklistItem("poe2_act4_area14", "発掘現場", 8),
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
            item.zone_id
            for item in ACT4_REQUIRED_ITEMS
            if item.parent_id == parent_id
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
        checked_ids = {
            zone_id
            for zone_id in checked
            if isinstance(zone_id, str) and zone_id in ACT4_REQUIRED_ZONE_IDS
        } if isinstance(checked, list) else set()
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
        self.setMinimumWidth(340)
        self._drag_offset: QPoint | None = None
        self._position_timer = QTimer(self)
        self._position_timer.setSingleShot(True)
        self._position_timer.timeout.connect(self._emit_position)
        self._checkboxes: dict[str, QCheckBox] = {}

        self.outer = QFrame(self)
        self.outer.setObjectName("act4ChecklistOuter")
        self.outer.setStyleSheet("""
            #act4ChecklistOuter {
                background-color: rgba(10, 10, 10, 242);
                border: 1px solid rgba(176, 255, 123, 165);
                border-radius: 8px;
            }
            QLabel { color: #ffffff; background: transparent; }
            QCheckBox {
                color: #f0f0f0;
                spacing: 7px;
                min-height: 23px;
                background: transparent;
            }
            QCheckBox:focus {
                border: 1px solid rgba(176, 255, 123, 210);
                border-radius: 3px;
            }
            QCheckBox::indicator { width: 0px; height: 0px; }
        """)
        outer_layout = QVBoxLayout(self.outer)
        outer_layout.setContentsMargins(12, 9, 12, 11)
        outer_layout.setSpacing(4)

        self.title_bar = QFrame()
        self.title_bar.setCursor(QCursor(Qt.SizeAllCursor))
        self.title_bar.installEventFilter(self)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(0, 0, 0, 2)
        title_layout.setSpacing(8)
        title = QLabel("Act4 攻略チェック")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #b0ff7b;")
        title_layout.addWidget(title)
        title_layout.addStretch()
        self.progress_label = QLabel("0 / 14")
        self.progress_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #dddddd;")
        title_layout.addWidget(self.progress_label)
        self.close_button = QPushButton("×")
        self.close_button.setAccessibleName("Act4攻略チェックを閉じる")
        self.close_button.setToolTip("このキャラクターでは自動表示しません。Act4ボタンから再表示できます")
        self.close_button.setFixedSize(28, 28)
        self.close_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.close_button.setStyleSheet("""
            QPushButton {
                color: #ffffff; background: #252525;
                border: 1px solid #777777; border-radius: 5px;
                font-size: 18px; font-weight: bold;
            }
            QPushButton:hover, QPushButton:focus { background: #743838; border-color: #ff9999; }
            QPushButton:pressed { background: #552828; }
        """)
        self.close_button.clicked.connect(self._dismiss)
        title_layout.addWidget(self.close_button)
        outer_layout.addWidget(self.title_bar)

        for item in ACT4_REQUIRED_ITEMS:
            if item.depth == 0 and self._checkboxes:
                outer_layout.addSpacing(2)
            prefix = f"{item.number}  " if item.number is not None else f"{'   ' * (item.depth - 1)}└  "
            checkbox = QCheckBox(f"{prefix}{item.label}")
            checkbox.setProperty("checklistLabel", f"{prefix}{item.label}")
            checkbox.setCursor(QCursor(Qt.PointingHandCursor))
            checkbox.setAccessibleName(f"{item.label} 入場済み")
            checkbox.setContentsMargins(item.depth * 17, 0, 0, 0)
            checkbox.toggled.connect(
                lambda checked, control=checkbox: self._refresh_checkbox_text(control, checked)
            )
            checkbox.toggled.connect(
                lambda checked, zone_id=item.zone_id: self.required_toggled.emit(zone_id, checked)
            )
            self._refresh_checkbox_text(checkbox, False)
            self._checkboxes[item.zone_id] = checkbox
            outer_layout.addWidget(checkbox)

        self.complete_label = QLabel("✓ Act4の攻略必須エリアをすべて完了済み")
        self.complete_label.setWordWrap(True)
        self.complete_label.setStyleSheet(
            "color: #b0ff7b; font-size: 12px; font-weight: bold; "
            "padding: 6px; border: 1px solid rgba(176,255,123,120); border-radius: 4px;"
        )
        self.complete_label.hide()
        outer_layout.addWidget(self.complete_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: rgba(176,255,123,90); margin-top: 5px;")
        outer_layout.addWidget(separator)
        self.optional_frame = QFrame()
        self.optional_frame.setObjectName("act4OptionalFrame")
        optional_layout = QVBoxLayout(self.optional_frame)
        optional_layout.setContentsMargins(8, 5, 8, 6)
        optional_layout.setSpacing(2)
        optional_title = QLabel("任意のお得ポイント")
        optional_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #f0c674;")
        optional_layout.addWidget(optional_title)
        self.optional_checkbox = QCheckBox("ナカヌの装備販売NPCを確認")
        self.optional_checkbox.setProperty("checklistLabel", "ナカヌの装備販売NPCを確認")
        self.optional_checkbox.setCursor(QCursor(Qt.PointingHandCursor))
        self.optional_checkbox.setAccessibleName("ナカヌの装備販売NPCを確認済み")
        self.optional_checkbox.toggled.connect(
            lambda checked: self._refresh_checkbox_text(self.optional_checkbox, checked)
        )
        self.optional_checkbox.toggled.connect(self.optional_toggled.emit)
        self._refresh_checkbox_text(self.optional_checkbox, False)
        optional_layout.addWidget(self.optional_checkbox)
        optional_note = QLabel("発掘現場を攻略前に立ち寄る")
        optional_note.setStyleSheet("font-size: 11px; color: #bbbbbb; padding-left: 25px;")
        optional_layout.addWidget(optional_note)
        outer_layout.addWidget(self.optional_frame)
        self.set_optional_available(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.outer)
        self.adjustSize()

    def apply_state(self, state: Act4ChecklistState):
        for zone_id, checkbox in self._checkboxes.items():
            checkbox.blockSignals(True)
            checked = zone_id in state.checked_zone_ids
            checkbox.setChecked(checked)
            self._refresh_checkbox_text(checkbox, checked)
            checkbox.blockSignals(False)
        self.optional_checkbox.blockSignals(True)
        self.optional_checkbox.setChecked(state.optional_npc_checked)
        self._refresh_checkbox_text(
            self.optional_checkbox,
            state.optional_npc_checked,
        )
        self.optional_checkbox.blockSignals(False)
        self.progress_label.setText(f"{state.completed_count} / {len(ACT4_REQUIRED_ITEMS)}")
        self.complete_label.setVisible(state.is_complete)

    @staticmethod
    def _refresh_checkbox_text(checkbox: QCheckBox, checked: bool):
        label = str(checkbox.property("checklistLabel") or "")
        checkbox.setText(f"{'✓' if checked else '□'}  {label}")

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

    def eventFilter(self, watched, event):
        if watched is self.title_bar:
            if event.type() == QEvent.MouseButtonPress and isinstance(event, QMouseEvent):
                if event.button() == Qt.LeftButton:
                    self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
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
