import os
import sys

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from src.ui.styles import Styles
from src.utils.config_manager import ConfigManager
from src.utils.poe_version_data import POE1, POE2


class PoeVersionSelectionDialog(QDialog):
    """起動時のPoEバージョン選択ダイアログ"""

    def __init__(self, parent=None, current_version=POE1):
        super().__init__(parent)
        self.setWindowTitle("PoEバージョン選択")
        self.setModal(True)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self.resize(680, 360)
        self.selected_version = current_version

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        title = QLabel("起動する対象を選んでください")
        title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        tile_row = QHBoxLayout()
        tile_row.setSpacing(14)
        self.poe1_tile = self._create_version_tile(POE1, "PoE1", current_version == POE1)
        self.poe2_tile = self._create_version_tile(POE2, "PoE2", current_version == POE2)
        tile_row.addWidget(self.poe1_tile)
        tile_row.addWidget(self.poe2_tile)
        layout.addLayout(tile_row)

        desc2 = QLabel("※ デフォルトでは起動時に毎回確認します。設定画面からPoE1/PoE2固定にもできます。")
        desc2.setStyleSheet("color: rgba(176, 255, 123, 0.78); font-size: 12px;")
        desc2.setWordWrap(True)
        layout.addWidget(desc2)

        button_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(Styles.BUTTON)
        ok_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setStyleSheet(Styles.BUTTON)
        cancel_btn.clicked.connect(self.reject)
        button_row.addStretch()
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addStretch()
        layout.addLayout(button_row)

    def _assets_dir(self):
        """assetsフォルダのパス（exeフォルダ優先 → _MEIPASS）"""
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            if os.path.isdir(os.path.join(exe_dir, "assets")):
                return os.path.join(exe_dir, "assets")
            return os.path.join(getattr(sys, '_MEIPASS', exe_dir), "assets")
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets")

    def _version_icon_path(self, version):
        """バージョンタイル用アイコン候補を返す"""
        base = self._assets_dir()
        names = {
            POE1: ["poe1.png", "poe1.jpg", "poe1.ico", os.path.join("icons", "poe1.png"), os.path.join("icons", "poe1.jpg")],
            POE2: ["poe2.png", "poe2.jpg", "poe2.ico", os.path.join("icons", "poe2.png"), os.path.join("icons", "poe2.jpg")],
        }.get(version, [])
        for name in names:
            path = os.path.join(base, name)
            if os.path.exists(path):
                return path
        return None

    def _create_version_tile(self, version, title, checked=False):
        btn = QPushButton(title)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setMinimumHeight(180)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(26, 35, 24, 235), stop:1 rgba(5, 8, 6, 245));
                color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176, 255, 123, 0.28);
                border-radius: 12px;
                padding: 16px;
                text-align: center;
                font-size: 28px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(176, 255, 123, 0.72);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(40, 58, 34, 245), stop:1 rgba(8, 15, 10, 250));
            }}
            QPushButton:checked {{
                border: 2px solid {Styles.TEXT_COLOR};
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(73, 110, 50, 245), stop:1 rgba(15, 27, 16, 250));
            }}
        """)
        icon_path = self._version_icon_path(version)
        if icon_path:
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(150, 150))
        self.group.addButton(btn)
        return btn

    def _accept(self):
        self.selected_version = POE2 if self.poe2_tile.isChecked() else POE1
        self.accept()


class GuideDetailLevelSelectionDialog(QDialog):
    """PoE2用のガイド表示レベル初回選択ダイアログ"""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"

    def __init__(self, parent=None, current_level=BEGINNER):
        super().__init__(parent)
        self.setWindowTitle("ガイド表示の選択")
        self.setModal(True)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self.resize(780, 460)
        self.selected_level = current_level if current_level in (self.BEGINNER, self.INTERMEDIATE) else self.BEGINNER

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        title = QLabel("PoE2のガイド表示を選んでください")
        title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel("後から設定画面でいつでも変更できます。")
        desc.setStyleSheet("color: rgba(176, 255, 123, 0.78); font-size: 12px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        tile_row = QHBoxLayout()
        tile_row.setSpacing(14)
        self.beginner_tile = self._create_level_tile(
            self.BEGINNER,
            "初心者向け（詳細）",
            "目的・進み方・補足をしっかり表示します。\n初見や慣れていないエリア向けです。",
            self.selected_level == self.BEGINNER,
        )
        self.intermediate_tile = self._create_level_tile(
            self.INTERMEDIATE,
            "中級者向け（要点）",
            "次の目標と重要ポイントを短く表示します。\n周回に慣れてきた方向けです。",
            self.selected_level == self.INTERMEDIATE,
        )
        tile_row.addWidget(self.beginner_tile)
        tile_row.addWidget(self.intermediate_tile)
        layout.addLayout(tile_row)

        note = QLabel("※ この選択画面はPoE2モードの初回のみ表示されます。")
        note.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        button_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(Styles.BUTTON)
        ok_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setStyleSheet(Styles.BUTTON)
        cancel_btn.clicked.connect(self.reject)
        button_row.addStretch()
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addStretch()
        layout.addLayout(button_row)

    def _assets_dir(self):
        """assetsフォルダのパス（exeフォルダ優先 → _MEIPASS）"""
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            if os.path.isdir(os.path.join(exe_dir, "assets")):
                return os.path.join(exe_dir, "assets")
            return os.path.join(getattr(sys, '_MEIPASS', exe_dir), "assets")
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets")

    def _level_image_path(self, level):
        """ガイド表示レベル選択タイル用の画像候補を返す"""
        base = self._assets_dir()
        names = {
            self.BEGINNER: [os.path.join("guide", "beginner.png")],
            self.INTERMEDIATE: [os.path.join("guide", "intermediate.png")],
        }.get(level, [])
        for name in names:
            path = os.path.join(base, name)
            if os.path.exists(path):
                return path
        return None

    def _create_level_tile(self, level, title, description, checked=False):
        btn = QPushButton(f"{title}\n\n{description}")
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setMinimumHeight(260)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(26, 35, 24, 235), stop:1 rgba(5, 8, 6, 245));
                color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176, 255, 123, 0.28);
                border-radius: 12px;
                padding: 12px;
                text-align: center;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(176, 255, 123, 0.72);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(40, 58, 34, 245), stop:1 rgba(8, 15, 10, 250));
            }}
            QPushButton:checked {{
                border: 2px solid {Styles.TEXT_COLOR};
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(73, 110, 50, 245), stop:1 rgba(15, 27, 16, 250));
            }}
        """)
        image_path = self._level_image_path(level)
        if image_path:
            btn.setIcon(QIcon(image_path))
            btn.setIconSize(QSize(320, 180))
        self.group.addButton(btn)
        return btn

    def _accept(self):
        self.selected_level = self.INTERMEDIATE if self.intermediate_tile.isChecked() else self.BEGINNER
        self.accept()


class RouteSelectionDialog(QDialog):
    """ルート選択ダイアログ（初回セットアップ用）"""
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("ルート設定")
        self.setFixedSize(400, 270)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        config = config or {}

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        desc = QLabel("攻略ルートを選択してください。後から設定画面で変更できます。")
        desc.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        combo_style = f"""
            QComboBox {{
                background-color: #2a2a2a; color: {Styles.TEXT_COLOR};
                border: 1px solid #555; border-radius: 4px;
                padding: 4px 8px; font-size: 12px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: #2a2a2a; color: {Styles.TEXT_COLOR};
                selection-background-color: #444;
            }}
        """
        label_style = f"color: {Styles.TEXT_COLOR}; font-size: 12px;"

        form = QFormLayout()

        self.act3_combo = QComboBox()
        self.act3_combo.addItem("通常ルート（図書館スキップ）", "standard")
        self.act3_combo.addItem("図書館寄り道ルート", "library_detour")
        self.act3_combo.setStyleSheet(combo_style)
        cur3 = ConfigManager.effective_poe1_route_act3(config)
        idx3 = self.act3_combo.findData(cur3)
        if idx3 >= 0:
            self.act3_combo.setCurrentIndex(idx3)
        lbl3 = QLabel("Act3 ルート:")
        lbl3.setStyleSheet(label_style)
        form.addRow(lbl3, self.act3_combo)

        self.act8_combo = QComboBox()
        self.act8_combo.addItem("通常ルート", "standard")
        self.act8_combo.addItem("隠れた裏道（The Hidden Underbelly）ルート", "underbelly")
        self.act8_combo.setStyleSheet(combo_style)
        cur8 = ConfigManager.effective_poe1_route_act8(config)
        idx8 = self.act8_combo.findData(cur8)
        if idx8 >= 0:
            self.act8_combo.setCurrentIndex(idx8)
        lbl8 = QLabel("Act8 ルート:")
        lbl8.setStyleSheet(label_style)
        form.addRow(lbl8, self.act8_combo)

        layout.addLayout(form)
        layout.addStretch()

        tip = QLabel("あまり経験のない方は、Act3ルートは「図書館寄り道ルート」、\nAct8ルートは「通常ルート」を選択するのがおすすめです。")
        tip.setStyleSheet(f"color: #aaaaaa; font-size: 13px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(Styles.BUTTON)
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn)

    def get_routes(self) -> dict:
        return {
            "poe1_route_act3": self.act3_combo.currentData(),
            "poe1_route_act8": self.act8_combo.currentData(),
        }
