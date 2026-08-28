import os
import sys

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)

from src.ui.styles import Styles
from src.app_mode import POENAVI_MODE, POETORE_MODE, normalize_app_mode
from src.ui.app_theme import theme_for_mode
from src.utils.config_manager import ConfigManager
from src.utils.feature_support import POETORE, is_feature_supported
from src.utils.poe_version_data import POE1, POE2


class StartupSelectionDialog(QDialog):
    """PoEバージョンと使用機能を一度に選ぶ起動ダイアログ。"""

    def __init__(self, parent=None, current_mode=POENAVI_MODE, poe_version=POE1):
        super().__init__(parent)
        self.selected_version = poe_version if poe_version in (POE1, POE2) else POE1
        self.selected_mode = normalize_app_mode(current_mode)
        poetore_supported = is_feature_supported(POETORE, self.selected_version)
        if self.selected_mode == POETORE_MODE and not poetore_supported:
            self.selected_mode = POENAVI_MODE
        self.setWindowTitle("起動設定")
        self.setModal(True)
        self.setFixedSize(760, 760)
        self.setStyleSheet(Styles.MAIN_WINDOW)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        title = QLabel("起動するPoEバージョンと機能を選んでください")
        title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        self.version_group = QButtonGroup(self)
        self.version_group.setExclusive(True)
        version_cards = QHBoxLayout()
        version_cards.setSpacing(16)
        self.poe1_tile = self._create_version_tile(POE1, "PoE1", self.selected_version == POE1)
        self.poe2_tile = self._create_version_tile(POE2, "PoE2", self.selected_version == POE2)
        version_cards.addWidget(self.poe1_tile)
        version_cards.addWidget(self.poe2_tile)
        layout.addLayout(version_cards)

        feature_title = QLabel("使う機能を選んでください")
        feature_title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 18px; font-weight: bold;")
        layout.addWidget(feature_title)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        cards = QHBoxLayout()
        cards.setSpacing(16)
        self.poenavi_card = self._create_card(
            POENAVI_MODE,
            "ぽえなび",
            "Act攻略支援",
            theme_for_mode(POENAVI_MODE).accent,
            "icon.ico",
            self.selected_mode == POENAVI_MODE,
        )
        self.poetore_card = self._create_card(
            POETORE_MODE,
            "ぽえとれ",
            "価格チェック・トレード支援",
            theme_for_mode(POETORE_MODE).accent,
            "icon2.ico",
            self.selected_mode == POETORE_MODE,
        )
        self.poetore_card.setEnabled(poetore_supported)
        if not poetore_supported:
            self.poetore_card.setToolTip("ぽえとれは現在PoE1専用です")
        cards.addWidget(self.poenavi_card)
        cards.addWidget(self.poetore_card)
        layout.addLayout(cards)

        notice = QLabel(
            "※デフォルトでは起動時に毎回確認します。以下のチェックボックスをONにすると固定にもできます。設定画面からも変更可能です。"
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color: rgba(176, 255, 123, 0.78); font-size: 13px;")
        layout.addWidget(notice)

        self.skip_selector_checkbox = QCheckBox("次回からこの設定で直接起動")
        self.skip_selector_checkbox.setChecked(False)
        self.skip_selector_checkbox.setStyleSheet(
            f"""
            QCheckBox {{ color: {Styles.TEXT_COLOR}; font-size: 13px; spacing: 8px; }}
            QCheckBox::indicator {{
                width: 17px; height: 17px; background: #101310;
                border: 2px solid #9eaaa0; border-radius: 3px;
            }}
            QCheckBox::indicator:hover {{ border-color: {Styles.TEXT_COLOR}; }}
            QCheckBox::indicator:checked {{
                background: {Styles.TEXT_COLOR}; border-color: {Styles.TEXT_COLOR};
            }}
            """
        )
        layout.addWidget(self.skip_selector_checkbox)

        buttons = QHBoxLayout()
        buttons.addStretch()
        start_button = QPushButton("この設定で起動")
        start_button.setStyleSheet(Styles.BUTTON)
        start_button.clicked.connect(self._accept_selection)
        cancel_button = QPushButton("キャンセル")
        cancel_button.setStyleSheet(Styles.BUTTON)
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(start_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

    @staticmethod
    def _app_icon_path(filename):
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            bundled = os.path.join(exe_dir, "assets", "app", filename)
            if os.path.exists(bundled):
                return bundled
            base = getattr(sys, "_MEIPASS", exe_dir)
            return os.path.join(base, "assets", "app", filename)
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        return os.path.join(project_root, "assets", "app", filename)

    def _create_card(self, mode, title, description, accent, icon_name, checked):
        button = QToolButton()
        button.setText(f"{title}\n{description}")
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        icon_path = self._app_icon_path(icon_name)
        if os.path.exists(icon_path):
            button.setIcon(QIcon(icon_path))
            button.setIconSize(QSize(128, 128))
        button.setProperty("app_mode", mode)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setCursor(QCursor(Qt.PointingHandCursor))
        button.setMinimumHeight(205)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        button.setStyleSheet(f"""
            QToolButton {{
                color: {accent};
                background-color: rgba(15, 18, 17, 245);
                border: 1px solid rgba(190, 200, 190, 0.28);
                border-radius: 14px;
                padding: 12px 18px 16px 18px;
                font-size: 17px;
                font-weight: bold;
            }}
            QToolButton:hover {{
                border: 2px solid {accent};
                background-color: rgba(30, 34, 32, 250);
            }}
            QToolButton:checked {{
                border: 3px solid {accent};
                background-color: rgba(42, 46, 43, 250);
            }}
        """)
        self.group.addButton(button)
        return button

    def _assets_dir(self):
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            if os.path.isdir(os.path.join(exe_dir, "assets")):
                return os.path.join(exe_dir, "assets")
            return os.path.join(getattr(sys, "_MEIPASS", exe_dir), "assets")
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets")

    def _version_icon_path(self, version):
        base = self._assets_dir()
        names = {
            POE1: ["poe1.png", "poe1.jpg", "poe1.ico", os.path.join("icons", "poe1.png")],
            POE2: ["poe2.png", "poe2.jpg", "poe2.ico", os.path.join("icons", "poe2.png")],
        }.get(version, [])
        for name in names:
            path = os.path.join(base, name)
            if os.path.exists(path):
                return path
        return None

    def _create_version_tile(self, version, title, checked=False):
        button = QToolButton()
        button.setText(title)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setProperty("poe_version", version)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setCursor(QCursor(Qt.PointingHandCursor))
        button.setMinimumHeight(170)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        button.setStyleSheet(f"""
            QToolButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(26, 35, 24, 235), stop:1 rgba(5, 8, 6, 245));
                color: {Styles.TEXT_COLOR}; border: 1px solid rgba(176, 255, 123, 0.28);
                border-radius: 12px; padding: 8px 12px 10px 12px;
                font-size: 26px; font-weight: bold;
            }}
            QToolButton:hover {{ border: 2px solid rgba(176, 255, 123, 0.72); }}
            QToolButton:checked {{
                border: 3px solid {Styles.TEXT_COLOR};
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(73, 110, 50, 245), stop:1 rgba(15, 27, 16, 250));
            }}
        """)
        icon_path = self._version_icon_path(version)
        if icon_path:
            button.setIcon(QIcon(icon_path))
            button.setIconSize(QSize(130, 130))
        self.version_group.addButton(button)
        return button

    def _accept_selection(self):
        checked_version = self.version_group.checkedButton()
        if checked_version is not None:
            self.selected_version = checked_version.property("poe_version")
        checked = self.group.checkedButton()
        if checked is not None:
            self.selected_mode = normalize_app_mode(checked.property("app_mode"))
        self.accept()

    @property
    def skip_selector(self):
        return self.skip_selector_checkbox.isChecked()


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
