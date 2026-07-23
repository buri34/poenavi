from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QGroupBox, QLineEdit, QFileDialog,
                               QTabWidget, QWidget, QScrollArea, QSpinBox,
                               QFormLayout, QTextEdit, QFrame, QRadioButton,
                               QButtonGroup, QGridLayout, QCheckBox, QComboBox,
                               QApplication)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence
from src.ui.styles import Styles
from src.utils.zone_data_poe2 import DEFAULT_ZONE_DATA_POE2
from src.utils.guide_data import load_guide_data, save_guide_data, get_visit_guide_for_edit, set_visit_guide_for_edit
from src.utils.poe_version_data import POE1, POE2, POE_VERSION_ORDER, get_act_list, get_poe_label, get_town_zones
from src.utils.zone_master_data import load_zone_master_data, save_zone_master_data
from src.utils.config_manager import ConfigManager
from src.utils.area_notes import get_area_note, set_area_note
import os
from src.utils.zone_lookup import get_zone_display_name
from src.utils.i18n import EN, JA, get_locale, tr, tr_ui
from src.update.release_channel import releases_page_url
import webbrowser


def _translated_color_name(name: str) -> str:
    """Translate application-owned color labels without changing stored values."""
    return {
        "赤": tr_ui("赤"),
        "青": tr_ui("青"),
        "オレンジ": tr_ui("オレンジ"),
        "緑": tr_ui("緑"),
        "黄": tr_ui("黄"),
        "紫": tr_ui("紫"),
        "白": tr_ui("白"),
    }.get(name, name)


def _flag_guide_header(zone_id: str) -> str:
    """編集画面上で、フラグ別ガイドに付随するルート条件も明示する。"""
    if zone_id in ("act8_area13", "act8_area14"):
        return "🚩 フラグ別ガイド（通常ルート、かつ以下のフラグ成立時）"
    return "🚩 フラグ別ガイド"


def _mini_navi_flag_section_title(zone_id: str, flag_key: str) -> str:
    if zone_id in ("act8_area13", "act8_area14"):
        return f"通常ルート、かつフラグ成立時: {flag_key}"
    return f"フラグ別: {flag_key}"


def _act1_guide_dev_editor_enabled(poe_version: str, zone_id: str) -> bool:
    """開発用起動時だけPoE1 Act 1の公式ガイド編集を許可する。"""
    return (
        os.environ.get("POENAVI_ACT1_GUIDE_DEV") == "1"
        and poe_version == POE1
        and zone_id.startswith("act1_")
    )

def _spinbox_style(width=55, height=28):
    """SpinBox共通スタイル（ボタン押しやすい版）"""
    return f"""
        QSpinBox {{ 
            background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR}; 
            border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; 
            padding: 2px; padding-right: 22px;
            min-width: {width}px; min-height: {height}px;
        }}
        QSpinBox::up-button {{
            subcontrol-origin: border; subcontrol-position: top right;
            width: 20px; height: 13px;
            background: rgba(80,80,80,220);
            border: 1px solid rgba(176,255,123,0.3);
            border-radius: 0 3px 0 0;
        }}
        QSpinBox::up-button:hover {{ background: rgba(120,120,120,220); }}
        QSpinBox::up-arrow {{ 
            image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
            border-bottom: 4px solid {Styles.TEXT_COLOR}; width: 0; height: 0;
        }}
        QSpinBox::down-button {{
            subcontrol-origin: border; subcontrol-position: bottom right;
            width: 20px; height: 13px;
            background: rgba(80,80,80,220);
            border: 1px solid rgba(176,255,123,0.3);
            border-radius: 0 0 3px 0;
        }}
        QSpinBox::down-button:hover {{ background: rgba(120,120,120,220); }}
        QSpinBox::down-arrow {{ 
            image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
            border-top: 4px solid {Styles.TEXT_COLOR}; width: 0; height: 0;
        }}
    """

class HotkeyButton(QPushButton):
    def __init__(self, key_text):
        super().__init__(key_text if key_text != "none" else tr("common.none"))
        self.key_text = key_text
        self.setCheckable(True)
        self.setStyleSheet(Styles.BUTTON)
        self.toggled.connect(self.on_toggle)

    def on_toggle(self, checked):
        if checked:
            self.setText("Press any key...")
            self.grabKeyboard() # Qtの入力独占
        else:
            self.setText(self.key_text if self.key_text != "none" else tr("common.none"))
            self.releaseKeyboard()

    def keyPressEvent(self, event):
        if not self.isChecked():
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()
        
        if key == Qt.Key_Escape:
            self.setChecked(False)
            return

        # Delete/Backspaceでバインド解除
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.key_text = "none"
            self.setChecked(False)
            return

        # 修飾キー単体除外
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

        # ここで確実にテキスト化する
        # modifiers は KeyboardModifier 型なので int に変換が必要な場合があるが、
        # Qt6 (PySide6) では | 演算子がオーバーロードされているためそのまま使えるはずだが、
        # エラーメッセージを見る限り型不一致が起きているため、QKeyCombination を経由するか、
        # intへの明示的なキャストなどを試みる。
        
        # PySide6 6.0+ では QKeySequence(QKeyCombination) が推奨されるが、
        # シンプルに int キャストして渡すのが最も互換性が高い。
        
        combo = key | modifiers.value
        sequence = QKeySequence(combo)
        text = sequence.toString(QKeySequence.PortableText) 
        
        if not text:
             # それでもだめならキーコードから文字を取得
             try:
                 text = QKeySequence(key).toString()
             except:
                 pass

        # F1~F12などが空になる場合があるため、明示的にハンドル
        if not text:
            if Qt.Key_F1 <= key <= Qt.Key_F12:
                text = f"F{key - Qt.Key_F1 + 1}"
        
        if text:
            self.key_text = text
            self.setChecked(False)
        else:
            # 認識できなかった場合
            print(f"Unknown key: {key}")
            self.setChecked(False)

class RichTextEdit(QTextEdit):
    """HTML出力対応のリッチテキストエディタ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
    
    def set_from_html(self, html: str):
        """保存済みHTML（改行=\n）を読み込む"""
        if not html:
            self.clear()
            return
        # 全角スペースをnbspに変換（HTMLの空白折りたたみを防止）
        converted = html.replace("\u3000", "&nbsp;&nbsp;")
        # \nをbrに変換してHTMLとして読み込み
        self.setHtml(converted.replace("\n", "<br>"))
    
    def to_storage_html(self) -> str:
        """保存用HTML文字列を生成（Qtの冗長なHTMLをクリーンアップ）"""
        from src.utils.area_notes import qt_html_to_storage_html

        return qt_html_to_storage_html(self.toHtml())


class AreaNoteDialog(QDialog):
    """エリアに紐づく色付きエリアメモ編集画面。"""

    COLORS = [
        ("#ff6666", "赤"),
        ("#4488ff", "青"),
        ("#ff8800", "オレンジ"),
        ("#44cc44", "緑"),
        ("#dddd44", "黄"),
        ("#dd66ff", "紫"),
        ("#ffffff", "白"),
    ]

    def __init__(self, parent, zone_name: str, content: str):
        super().__init__(parent)
        self.setWindowTitle(tr_ui(f"エリアメモ — {zone_name}"))
        self.resize(520, 360)
        self.setStyleSheet(Styles.MAIN_WINDOW)

        layout = QVBoxLayout(self)
        description = QLabel(tr_ui(f"📝 {zone_name} のエリアメモ"))
        description.setStyleSheet(
            f"color: {Styles.TEXT_COLOR}; font-size: 14px; font-weight: bold;"
        )
        layout.addWidget(description)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(5)
        for color_code, color_name in self.COLORS:
            button = QPushButton()
            button.setFixedSize(22, 22)
            button.setToolTip(_translated_color_name(color_name))
            button.setStyleSheet(
                f"QPushButton {{ background: {color_code}; border: 1px solid #777; "
                "border-radius: 3px; } QPushButton:hover { border: 2px solid white; }"
            )
            button.clicked.connect(lambda checked=False, color=color_code: self._set_color(color))
            toolbar.addWidget(button)
        reset_button = QPushButton(tr_ui("標準色"))
        reset_button.setToolTip(tr_ui("選択範囲の文字色を標準色へ戻します"))
        reset_button.clicked.connect(lambda: self._set_color(Styles.TEXT_COLOR))
        toolbar.addWidget(reset_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.text_edit = RichTextEdit()
        self.text_edit.setStyleSheet(
            f"QTextEdit {{ background: #1a1a1a; color: {Styles.TEXT_COLOR}; "
            "border: 1px solid #4b6b3b; padding: 7px; font-size: 13px; }"
        )
        self.text_edit.set_from_html(content)
        layout.addWidget(self.text_edit)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton(tr_ui("キャンセル"))
        cancel_button.clicked.connect(self.reject)
        save_button = QPushButton(tr_ui("保存"))
        save_button.setDefault(True)
        save_button.clicked.connect(self.accept)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

    def _set_color(self, color: str):
        from PySide6.QtGui import QColor

        cursor = self.text_edit.textCursor()
        char_format = cursor.charFormat()
        char_format.setForeground(QColor(color))
        cursor.mergeCharFormat(char_format)
        self.text_edit.mergeCurrentCharFormat(char_format)

    def content(self) -> str:
        return self.text_edit.to_storage_html()


class GuideEditorDialog(QDialog):
    """個別エリアのガイドデータ編集ダイアログ"""
    
    COLORS = [
        ("#ff6666", "赤"),
        ("#4488ff", "青"),
        ("#ff8800", "オレンジ"),
        ("#44cc44", "緑"),
        ("#dddd44", "黄"),
        ("#dd66ff", "紫"),
        ("#ffffff", "白"),
    ]
    
    def __init__(self, parent, zone_name: str, guide: dict, guide_v2: dict = None, zone_id: str = "", route_guides: dict = None, flag_guides: dict = None):
        super().__init__(parent)
        self.setWindowTitle(tr_ui(f"ガイド編集 — {zone_name}"))
        self.resize(550, 620)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self.guide_v2 = guide_v2 or {}
        self._existing_mini_navi = guide.get("mini_navi") if isinstance(guide, dict) else None
        self._existing_v2_mini_navi = self.guide_v2.get("mini_navi") if isinstance(self.guide_v2, dict) else None
        self._existing_summary = guide.get("summary", "") if isinstance(guide, dict) else ""
        self._existing_v2_summary = self.guide_v2.get("summary", "") if isinstance(self.guide_v2, dict) else ""
        self.zone_id = zone_id
        self.is_poe2_zone = self.zone_id.startswith("poe2_") if self.zone_id else False
        self.route_guides = route_guides or {}  # {"~library_detour": {...}, "~library_detour@2": {...}}
        self.flag_guides = flag_guides or {}
        self.primary_flag_key = next(iter(self.flag_guides.keys()), "")
        if self.is_poe2_zone and self.primary_flag_key and not guide_v2:
            self.guide_v2 = self.flag_guides.get(self.primary_flag_key, {})
        
        main_layout = QVBoxLayout(self)
        
        # スクロール対応
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; }
            QScrollBar:vertical { width: 6px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(176,255,123,0.3); border-radius: 3px; }
        """)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        
        text_style = f"""
            QTextEdit {{ 
                background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR}; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 4px; 
                padding: 5px; font-size: 12px;
                font-family: "MS Gothic", "Yu Gothic", "Meiryo", monospace;
            }}
        """
        label_style = f"color: {Styles.TEXT_COLOR}; font-size: 12px; font-weight: bold;"
        radio_style = f"""
            QRadioButton {{ 
                color: {Styles.TEXT_COLOR}; font-size: 20px; 
                padding: 6px 10px;
                background: rgba(40,40,40,180);
                border: 1px solid rgba(176,255,123,0.2);
                border-radius: 4px;
                min-width: 36px; min-height: 28px;
            }}
            QRadioButton:checked {{ 
                background: rgba(176,255,123,0.2);
                border: 2px solid {Styles.TEXT_COLOR};
            }}
            QRadioButton:hover {{ 
                background: rgba(80,80,80,200);
            }}
            QRadioButton::indicator {{ width: 0; height: 0; }}
        """
        
        is_poe2_zone = self.is_poe2_zone
        self.direction_group = None
        if not is_poe2_zone:
            # ── 基本方向 ──
            dir_group_box = QGroupBox(tr_ui("🧭 基本方向（シンプルなマップ向け）"))
            dir_group_box.setStyleSheet(f"""
                QGroupBox {{ color: {Styles.TEXT_COLOR}; border: 1px solid rgba(176,255,123,0.3); 
                    border-radius: 4px; margin-top: 8px; font-size: 11px; font-weight: bold; }}
                QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }}
            """)
            dir_layout = QGridLayout(dir_group_box)
            dir_layout.setSpacing(2)
            
            self.direction_group = QButtonGroup(self)
            # 方向定義: (row, col, label, value)
            directions = [
                (0, 0, "↖", "nw"), (0, 1, "↑", "n"), (0, 2, "↗", "ne"),
                (1, 0, "←", "w"),  (1, 1, "—", "none"), (1, 2, "→", "e"),
                (2, 0, "↙", "sw"), (2, 1, "↓", "s"), (2, 2, "↘", "se"),
            ]
            current_dir = guide.get("direction", "none")
            
            for row, col, label, value in directions:
                rb = QRadioButton(label)
                rb.setStyleSheet(radio_style)
                rb.setProperty("dir_value", value)
                if value == current_dir:
                    rb.setChecked(True)
                self.direction_group.addButton(rb)
                dir_layout.addWidget(rb, row, col, Qt.AlignCenter)
            
            dir_desc = QLabel(tr_ui("中央「—」= 該当なし（複雑なマップ → ガイド参照を表示）"))
            dir_desc.setStyleSheet("color: #888888; font-size: 10px;")
            dir_desc.setWordWrap(True)
            dir_layout.addWidget(dir_desc, 3, 0, 1, 3)
            
            layout.addWidget(dir_group_box)
        
        # 目標
        layout.addWidget(QLabel(tr_ui("📋 目標 / やること")))
        layout.itemAt(layout.count()-1).widget().setStyleSheet(label_style)
        self.objective_edit = QTextEdit()
        self.objective_edit.setPlainText(guide.get("objective", ""))
        self.objective_edit.setFixedHeight(50)
        self.objective_edit.setStyleSheet(text_style)
        layout.addWidget(self.objective_edit)
        
        # レイアウト情報
        layout.addWidget(QLabel(tr_ui("🗺️ レイアウト情報")))
        layout.itemAt(layout.count()-1).widget().setStyleSheet(label_style)
        
        # ── ツールバー ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        
        # カラーボタン
        for color_code, color_name in self.COLORS:
            cbtn = QPushButton()
            cbtn.setFixedSize(22, 22)
            cbtn.setToolTip(f"{_translated_color_name(color_name)} ({color_code})")
            cbtn.setStyleSheet(f"""
                QPushButton {{ 
                    background: {color_code}; 
                    border: 2px solid rgba(255,255,255,0.3); 
                    border-radius: 3px;
                }}
                QPushButton:hover {{ border: 2px solid #ffffff; }}
            """)
            cbtn.clicked.connect(lambda checked, c=color_code: self._set_color(c))
            toolbar.addWidget(cbtn)
        
        # 色リセットボタン
        reset_color_btn = QPushButton("✕")
        reset_color_btn.setFixedSize(22, 22)
        reset_color_btn.setToolTip(tr_ui("色をリセット"))
        reset_color_btn.setStyleSheet(f"""
            QPushButton {{ 
                background: rgba(40,40,40,200); color: #888; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; font-size: 11px;
            }}
            QPushButton:hover {{ background: rgba(80,80,80,200); }}
        """)
        reset_color_btn.clicked.connect(self._reset_color)
        toolbar.addWidget(reset_color_btn)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        # リッチテキストエディタ
        self.layout_edit = RichTextEdit()
        self.layout_edit.set_from_html(guide.get("layout", ""))
        self.layout_edit.setFixedHeight(200)
        self.layout_edit.setStyleSheet(text_style)
        layout.addWidget(self.layout_edit)
        self._active_editor = self.layout_edit  # ツールバーの対象
        
        # Tips
        layout.addWidget(QLabel(tr_ui("💡 Tips / 注意点")))
        layout.itemAt(layout.count()-1).widget().setStyleSheet(label_style)
        tips_toolbar = QHBoxLayout()
        tips_toolbar.setSpacing(4)
        for color_code, color_name in self.COLORS:
            cbtn = QPushButton()
            cbtn.setFixedSize(22, 22)
            cbtn.setToolTip(f"{_translated_color_name(color_name)} ({color_code})")
            cbtn.setStyleSheet(f"""
                QPushButton {{ 
                    background: {color_code}; 
                    border: 2px solid rgba(255,255,255,0.3); 
                    border-radius: 3px;
                }}
                QPushButton:hover {{ border: 2px solid #ffffff; }}
            """)
            cbtn.clicked.connect(lambda checked, c=color_code: self._set_color_tips(c))
            tips_toolbar.addWidget(cbtn)
        reset_tips_color_btn = QPushButton("✕")
        reset_tips_color_btn.setFixedSize(22, 22)
        reset_tips_color_btn.setToolTip(tr_ui("色をリセット"))
        reset_tips_color_btn.setStyleSheet(f"""
            QPushButton {{ 
                background: rgba(40,40,40,200); color: #888; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; font-size: 11px;
            }}
            QPushButton:hover {{ background: rgba(80,80,80,200); }}
        """)
        reset_tips_color_btn.clicked.connect(self._reset_color_tips)
        tips_toolbar.addWidget(reset_tips_color_btn)
        tips_toolbar.addStretch()
        layout.addLayout(tips_toolbar)
        self.tips_edit = RichTextEdit()
        self.tips_edit.set_from_html(guide.get("tips", ""))
        self.tips_edit.setFixedHeight(200)
        self.tips_edit.setStyleSheet(text_style)
        layout.addWidget(self.tips_edit)
        
        # ── 2回目の訪問ガイド ──
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: rgba(176,255,123,0.3);")
        layout.addWidget(separator)
        
        # zone_idからPoE1/PoE2に応じた補助ガイド説明を動的生成
        is_poe2_zone = self.zone_id.startswith("poe2_") if self.zone_id else False
        if is_poe2_zone:
            v2_label_closed = tr_ui("▶ フラグ進行後のガイド")
            v2_label_open = tr_ui("▼ フラグ進行後のガイド")
        else:
            act_num = int(self.zone_id.split("_")[0].replace("act", "")) if self.zone_id and self.zone_id.startswith("act") else 1
            act_range = "Act6-10" if act_num >= 6 else "Act1-5"
            v2_label_closed = tr_ui(f"▶ 2回目のガイド（{act_range}の間で、このエリアに２回以上訪れた場合はこちらを表示）")
            v2_label_open = tr_ui(f"▼ 2回目のガイド（{act_range}の間で、このエリアに２回以上訪れた場合はこちらを表示）")
        self._v2_label_closed = v2_label_closed
        self._v2_label_open = v2_label_open
        self.v2_toggle_btn = QPushButton(v2_label_open if self.guide_v2 else v2_label_closed)
        self.v2_toggle_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Styles.TEXT_COLOR}; border: none; 
                font-size: 11px; font-weight: bold; text-align: left; padding: 2px; }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.v2_toggle_btn.clicked.connect(self._toggle_v2)
        layout.addWidget(self.v2_toggle_btn)
        
        self.v2_frame = QFrame()
        v2_layout = QVBoxLayout(self.v2_frame)
        v2_layout.setContentsMargins(10, 0, 0, 0)
        v2_layout.setSpacing(5)
        
        self.v2_direction_group = None
        if not is_poe2_zone:
            # 基本方向（2回目）
            v2_dir_group_box = QGroupBox(tr_ui("🧭 基本方向（2回目）"))
            v2_dir_group_box.setStyleSheet(f"""
                QGroupBox {{ color: {Styles.TEXT_COLOR}; border: 1px solid rgba(176,255,123,0.3); 
                    border-radius: 4px; margin-top: 8px; font-size: 11px; font-weight: bold; }}
                QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }}
            """)
            v2_dir_layout = QGridLayout(v2_dir_group_box)
            v2_dir_layout.setSpacing(2)
            
            self.v2_direction_group = QButtonGroup(self)
            v2_directions = [
                (0, 0, "↖", "nw"), (0, 1, "↑", "n"), (0, 2, "↗", "ne"),
                (1, 0, "←", "w"),  (1, 1, "—", "none"), (1, 2, "→", "e"),
                (2, 0, "↙", "sw"), (2, 1, "↓", "s"), (2, 2, "↘", "se"),
                (1, 3, "同上", "inherit"),
            ]
            v2_current_dir = self.guide_v2.get("direction", "inherit")
            
            for row, col, label, value in v2_directions:
                rb = QRadioButton(tr_ui("同上") if label == "同上" else label)
                rb.setStyleSheet(radio_style if label != "同上" else f"""
                    QRadioButton {{ 
                        color: {Styles.TEXT_COLOR}; font-size: 11px; 
                        padding: 6px 8px; background: rgba(40,40,40,180);
                        border: 1px solid rgba(176,255,123,0.2); border-radius: 4px;
                        min-width: 36px; min-height: 28px;
                    }}
                    QRadioButton:checked {{ background: rgba(176,255,123,0.2); border: 2px solid {Styles.TEXT_COLOR}; }}
                    QRadioButton:hover {{ background: rgba(80,80,80,200); }}
                    QRadioButton::indicator {{ width: 0; height: 0; }}
                """)
                rb.setProperty("dir_value", value)
                if value == v2_current_dir:
                    rb.setChecked(True)
                self.v2_direction_group.addButton(rb)
                v2_dir_layout.addWidget(rb, row, col, Qt.AlignCenter)
            
            v2_dir_desc = QLabel(tr_ui("「同上」= 1回目と同じ方向を使用"))
            v2_dir_desc.setStyleSheet("color: #888888; font-size: 10px;")
            v2_dir_layout.addWidget(v2_dir_desc, 3, 0, 1, 4)
            
            v2_layout.addWidget(v2_dir_group_box)
        
        v2_layout.addWidget(QLabel(tr_ui("📋 目標 / やること")))
        v2_layout.itemAt(v2_layout.count()-1).widget().setStyleSheet(label_style)
        self.v2_objective_edit = QTextEdit()
        self.v2_objective_edit.setPlainText(self.guide_v2.get("objective", ""))
        self.v2_objective_edit.setFixedHeight(50)
        self.v2_objective_edit.setStyleSheet(text_style)
        v2_layout.addWidget(self.v2_objective_edit)
        
        v2_layout.addWidget(QLabel(tr_ui("🗺️ レイアウト情報")))
        v2_layout.itemAt(v2_layout.count()-1).widget().setStyleSheet(label_style)
        
        # ── カラーパレット（2回目用） ──
        v2_toolbar = QHBoxLayout()
        v2_toolbar.setSpacing(4)
        for color_code, color_name in self.COLORS:
            cbtn = QPushButton()
            cbtn.setFixedSize(22, 22)
            cbtn.setToolTip(f"{_translated_color_name(color_name)} ({color_code})")
            cbtn.setStyleSheet(f"""
                QPushButton {{ 
                    background: {color_code}; 
                    border: 2px solid rgba(255,255,255,0.3); 
                    border-radius: 3px;
                }}
                QPushButton:hover {{ border: 2px solid #ffffff; }}
            """)
            cbtn.clicked.connect(lambda checked, c=color_code: self._set_color_v2(c))
            v2_toolbar.addWidget(cbtn)
        v2_reset_btn = QPushButton("✕")
        v2_reset_btn.setFixedSize(22, 22)
        v2_reset_btn.setToolTip(tr_ui("色をリセット"))
        v2_reset_btn.setStyleSheet(f"""
            QPushButton {{ 
                background: rgba(40,40,40,200); color: #888; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; font-size: 11px;
            }}
            QPushButton:hover {{ background: rgba(80,80,80,200); }}
        """)
        v2_reset_btn.clicked.connect(self._reset_color_v2)
        v2_toolbar.addWidget(v2_reset_btn)
        v2_toolbar.addStretch()
        v2_layout.addLayout(v2_toolbar)
        
        self.v2_layout_edit = RichTextEdit()
        self.v2_layout_edit.set_from_html(self.guide_v2.get("layout", ""))
        self.v2_layout_edit.setFixedHeight(150)
        self.v2_layout_edit.setStyleSheet(text_style)
        v2_layout.addWidget(self.v2_layout_edit)
        
        v2_layout.addWidget(QLabel(tr_ui("💡 Tips / 注意点")))
        v2_layout.itemAt(v2_layout.count()-1).widget().setStyleSheet(label_style)
        tips_toolbar_v2 = QHBoxLayout()
        tips_toolbar_v2.setSpacing(4)
        for color_code, color_name in self.COLORS:
            cbtn = QPushButton()
            cbtn.setFixedSize(22, 22)
            cbtn.setToolTip(f"{_translated_color_name(color_name)} ({color_code})")
            cbtn.setStyleSheet(f"""
                QPushButton {{ 
                    background: {color_code}; 
                    border: 2px solid rgba(255,255,255,0.3); 
                    border-radius: 3px;
                }}
                QPushButton:hover {{ border: 2px solid #ffffff; }}
            """)
            cbtn.clicked.connect(lambda checked, c=color_code: self._set_color_v2_tips(c))
            tips_toolbar_v2.addWidget(cbtn)
        reset_v2_tips_color_btn = QPushButton("✕")
        reset_v2_tips_color_btn.setFixedSize(22, 22)
        reset_v2_tips_color_btn.setToolTip(tr_ui("色をリセット"))
        reset_v2_tips_color_btn.setStyleSheet(f"""
            QPushButton {{ 
                background: rgba(40,40,40,200); color: #888; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; font-size: 11px;
            }}
            QPushButton:hover {{ background: rgba(80,80,80,200); }}
        """)
        reset_v2_tips_color_btn.clicked.connect(self._reset_color_v2_tips)
        tips_toolbar_v2.addWidget(reset_v2_tips_color_btn)
        tips_toolbar_v2.addStretch()
        v2_layout.addLayout(tips_toolbar_v2)
        self.v2_tips_edit = RichTextEdit()
        self.v2_tips_edit.set_from_html(self.guide_v2.get("tips", ""))
        self.v2_tips_edit.setFixedHeight(60)
        self.v2_tips_edit.setStyleSheet(text_style)
        v2_layout.addWidget(self.v2_tips_edit)
        
        layout.addWidget(self.v2_frame)
        self.v2_frame.setVisible(bool(self.guide_v2))
        
        # ── フラグ別ガイド（PoE1用） ──
        self.flag_editors = {}  # {flag_key: {"objective": QTextEdit, "layout": RichTextEdit, "tips": QTextEdit, "direction": QButtonGroup}}
        if self.flag_guides and not self.is_poe2_zone:
            flag_separator = QFrame()
            flag_separator.setFrameShape(QFrame.HLine)
            flag_separator.setStyleSheet("color: rgba(176,255,123,0.5);")
            layout.addWidget(flag_separator)

            flag_header = QLabel(_flag_guide_header(self.zone_id))
            flag_header.setStyleSheet(f"color: #ffc832; font-size: 13px; font-weight: bold;")
            layout.addWidget(flag_header)

            for flag_key, fguide in sorted(self.flag_guides.items()):
                fg_box = QGroupBox(flag_key)
                fg_box.setStyleSheet(f"""
                    QGroupBox {{ color: {Styles.TEXT_COLOR}; border: 1px solid rgba(176,255,123,0.3);
                        border-radius: 4px; margin-top: 8px; font-size: 11px; font-weight: bold; }}
                    QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }}
                """)
                fg_layout = QVBoxLayout(fg_box)
                fg_layout.setSpacing(5)

                f_dir_label = QLabel(tr_ui("🧭 基本方向"))
                f_dir_label.setStyleSheet(label_style)
                fg_layout.addWidget(f_dir_label)
                f_dir_grid = QGridLayout()
                f_dir_grid.setSpacing(2)
                f_dir_group = QButtonGroup(self)
                f_directions = [
                    (0, 0, "↖", "nw"), (0, 1, "↑", "n"), (0, 2, "↗", "ne"),
                    (1, 0, "←", "w"),  (1, 1, "—", "none"), (1, 2, "→", "e"),
                    (2, 0, "↙", "sw"), (2, 1, "↓", "s"), (2, 2, "↘", "se"),
                    (1, 3, "同上", "inherit"),
                ]
                f_current_dir = fguide.get("direction", "inherit")
                for f_row, f_col, f_label, f_value in f_directions:
                    f_rb = QRadioButton(tr_ui("同上") if f_label == "同上" else f_label)
                    f_rb.setStyleSheet(radio_style if f_label != "同上" else f"""
                        QRadioButton {{
                            color: {Styles.TEXT_COLOR}; font-size: 11px;
                            padding: 6px 8px; background: rgba(40,40,40,180);
                            border: 1px solid rgba(176,255,123,0.2); border-radius: 4px;
                            min-width: 36px; min-height: 28px;
                        }}
                        QRadioButton:checked {{ background: rgba(176,255,123,0.2); border: 2px solid {Styles.TEXT_COLOR}; }}
                        QRadioButton:hover {{ background: rgba(80,80,80,200); }}
                        QRadioButton::indicator {{ width: 0; height: 0; }}
                    """)
                    f_rb.setProperty("dir_value", f_value)
                    if f_value == f_current_dir:
                        f_rb.setChecked(True)
                    f_dir_group.addButton(f_rb)
                    f_dir_grid.addWidget(f_rb, f_row, f_col, Qt.AlignCenter)
                fg_layout.addLayout(f_dir_grid)


                fg_layout.addWidget(QLabel(tr_ui("📋 目標 / やること")))
                fg_layout.itemAt(fg_layout.count()-1).widget().setStyleSheet(label_style)
                f_obj = QTextEdit()
                f_obj.setPlainText(fguide.get("objective", ""))
                f_obj.setFixedHeight(50)
                f_obj.setStyleSheet(text_style)
                fg_layout.addWidget(f_obj)

                fg_layout.addWidget(QLabel(tr_ui("🗺️ レイアウト")))
                fg_layout.itemAt(fg_layout.count()-1).widget().setStyleSheet(label_style)
                f_lay = RichTextEdit()
                f_lay.set_from_html(fguide.get("layout", ""))
                f_lay.setFixedHeight(120)
                f_lay.setStyleSheet(text_style)
                fg_layout.addWidget(f_lay)

                fg_layout.addWidget(QLabel(tr_ui("💡 Tips / 注意点")))
                fg_layout.itemAt(fg_layout.count()-1).widget().setStyleSheet(label_style)
                f_tips = RichTextEdit()
                f_tips.set_from_html(fguide.get("tips", ""))
                f_tips.setFixedHeight(50)
                f_tips.setStyleSheet(text_style)
                fg_layout.addWidget(f_tips)

                layout.addWidget(fg_box)
                self.flag_editors[flag_key] = {"objective": f_obj, "layout": f_lay, "tips": f_tips, "direction": f_dir_group}

        # ── ルート別ガイド ──
        self.route_editors = {}  # {suffix: {"objective": QTextEdit, "layout": RichTextEdit, "tips": RichTextEdit, "direction": QButtonGroup}}
        self.route_flag_editors = {}  # {(suffix, flag_key): {"objective": QTextEdit, "layout": RichTextEdit, "tips": RichTextEdit, "direction": QButtonGroup}}
        if self.route_guides:
            route_separator = QFrame()
            route_separator.setFrameShape(QFrame.HLine)
            route_separator.setStyleSheet("color: rgba(176,255,123,0.5);")
            layout.addWidget(route_separator)
            
            route_header = QLabel(tr_ui("📍 ルート別ガイド"))
            route_header.setStyleSheet(f"color: #ffc832; font-size: 13px; font-weight: bold;")
            layout.addWidget(route_header)
            
            # ルート名の表示マッピング
            route_display = {
                "~library_detour": "図書館ルート 1回目",
                "~library_detour@2": "図書館ルート 2回目",
                "~underbelly": "裏道ルート 1回目",
                "~underbelly@2": "裏道ルート 2回目",
            }
            
            for suffix, rguide in sorted(self.route_guides.items()):
                display = route_display.get(suffix, suffix)
                rg_box = QGroupBox(display)
                rg_box.setStyleSheet(f"""
                    QGroupBox {{ color: {Styles.TEXT_COLOR}; border: 1px solid rgba(176,255,123,0.3); 
                        border-radius: 4px; margin-top: 8px; font-size: 11px; font-weight: bold; }}
                    QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }}
                """)
                rg_layout = QVBoxLayout(rg_box)
                rg_layout.setSpacing(5)
                
                rg_layout.addWidget(QLabel(tr_ui("📋 目標")))
                rg_layout.itemAt(rg_layout.count()-1).widget().setStyleSheet(label_style)
                r_obj = QTextEdit()
                r_obj.setPlainText(rguide.get("objective", ""))
                r_obj.setFixedHeight(50)
                r_obj.setStyleSheet(text_style)
                rg_layout.addWidget(r_obj)
                
                rg_layout.addWidget(QLabel(tr_ui("🗺️ レイアウト")))
                rg_layout.itemAt(rg_layout.count()-1).widget().setStyleSheet(label_style)
                r_lay = RichTextEdit()
                r_lay.set_from_html(rguide.get("layout", ""))
                r_lay.setFixedHeight(120)
                r_lay.setStyleSheet(text_style)
                rg_layout.addWidget(r_lay)
                
                rg_layout.addWidget(QLabel("💡 Tips"))
                rg_layout.itemAt(rg_layout.count()-1).widget().setStyleSheet(label_style)
                r_tips = RichTextEdit()
                r_tips.set_from_html(rguide.get("tips", ""))
                r_tips.setFixedHeight(50)
                r_tips.setStyleSheet(text_style)
                rg_layout.addWidget(r_tips)
                
                # 基本方向（9方向ラジオボタン）
                r_dir_label = QLabel(tr_ui("🧭 基本方向"))
                r_dir_label.setStyleSheet(label_style)
                rg_layout.addWidget(r_dir_label)
                r_dir_grid = QGridLayout()
                r_dir_grid.setSpacing(2)
                r_dir_group = QButtonGroup(self)
                r_directions = [
                    (0, 0, "↖", "nw"), (0, 1, "↑", "n"), (0, 2, "↗", "ne"),
                    (1, 0, "←", "w"),  (1, 1, "—", "none"), (1, 2, "→", "e"),
                    (2, 0, "↙", "sw"), (2, 1, "↓", "s"), (2, 2, "↘", "se"),
                ]
                r_current_dir = rguide.get("direction", "none")
                for r_row, r_col, r_label, r_value in r_directions:
                    r_rb = QRadioButton(r_label)
                    r_rb.setStyleSheet(radio_style)
                    r_rb.setProperty("dir_value", r_value)
                    if r_value == r_current_dir:
                        r_rb.setChecked(True)
                    r_dir_group.addButton(r_rb)
                    r_dir_grid.addWidget(r_rb, r_row, r_col, Qt.AlignCenter)
                rg_layout.addLayout(r_dir_grid)

                route_flags = rguide.get("flags", {}) if isinstance(rguide.get("flags", {}), dict) else {}
                for flag_key, flag_guide in sorted(route_flags.items()):
                    if not isinstance(flag_guide, dict):
                        continue
                    rf_box = QGroupBox(tr_ui(f"🚩 条件分岐: {flag_key}"))
                    rf_box.setStyleSheet(f"""
                        QGroupBox {{ color: {Styles.TEXT_COLOR}; border: 1px solid rgba(255,200,50,0.35);
                            border-radius: 4px; margin-top: 8px; font-size: 11px; font-weight: bold; }}
                        QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }}
                    """)
                    rf_layout = QVBoxLayout(rf_box)
                    rf_layout.setSpacing(5)

                    rf_layout.addWidget(QLabel(tr_ui("📋 目標")))
                    rf_layout.itemAt(rf_layout.count()-1).widget().setStyleSheet(label_style)
                    rf_obj = QTextEdit()
                    rf_obj.setPlainText(flag_guide.get("objective", ""))
                    rf_obj.setFixedHeight(50)
                    rf_obj.setStyleSheet(text_style)
                    rf_layout.addWidget(rf_obj)

                    rf_layout.addWidget(QLabel(tr_ui("🗺️ レイアウト")))
                    rf_layout.itemAt(rf_layout.count()-1).widget().setStyleSheet(label_style)
                    rf_lay = RichTextEdit()
                    rf_lay.set_from_html(flag_guide.get("layout", ""))
                    rf_lay.setFixedHeight(120)
                    rf_lay.setStyleSheet(text_style)
                    rf_layout.addWidget(rf_lay)

                    rf_layout.addWidget(QLabel("💡 Tips"))
                    rf_layout.itemAt(rf_layout.count()-1).widget().setStyleSheet(label_style)
                    rf_tips = RichTextEdit()
                    rf_tips.set_from_html(flag_guide.get("tips", ""))
                    rf_tips.setFixedHeight(50)
                    rf_tips.setStyleSheet(text_style)
                    rf_layout.addWidget(rf_tips)

                    rf_dir_label = QLabel(tr_ui("🧭 基本方向"))
                    rf_dir_label.setStyleSheet(label_style)
                    rf_layout.addWidget(rf_dir_label)
                    rf_dir_grid = QGridLayout()
                    rf_dir_grid.setSpacing(2)
                    rf_dir_group = QButtonGroup(self)
                    rf_directions = [
                        (0, 0, "↖", "nw"), (0, 1, "↑", "n"), (0, 2, "↗", "ne"),
                        (1, 0, "←", "w"),  (1, 1, "—", "none"), (1, 2, "→", "e"),
                        (2, 0, "↙", "sw"), (2, 1, "↓", "s"), (2, 2, "↘", "se"),
                        (1, 3, "同上", "inherit"),
                    ]
                    rf_current_dir = flag_guide.get("direction", "inherit")
                    for rf_row, rf_col, rf_label, rf_value in rf_directions:
                        rf_rb = QRadioButton(tr_ui("同上") if rf_label == "同上" else rf_label)
                        rf_rb.setStyleSheet(radio_style if rf_label != "同上" else f"""
                            QRadioButton {{ color: {Styles.TEXT_COLOR}; font-size: 11px; padding: 6px 8px;
                                background: rgba(40,40,40,180); border: 1px solid rgba(176,255,123,0.2);
                                border-radius: 4px; min-width: 36px; min-height: 28px; }}
                            QRadioButton:checked {{ background: rgba(176,255,123,0.2); border: 2px solid {Styles.TEXT_COLOR}; }}
                            QRadioButton:hover {{ background: rgba(80,80,80,200); }}
                            QRadioButton::indicator {{ width: 0; height: 0; }}
                        """)
                        rf_rb.setProperty("dir_value", rf_value)
                        if rf_value == rf_current_dir:
                            rf_rb.setChecked(True)
                        rf_dir_group.addButton(rf_rb)
                        rf_dir_grid.addWidget(rf_rb, rf_row, rf_col, Qt.AlignCenter)
                    rf_layout.addLayout(rf_dir_grid)

                    rg_layout.addWidget(rf_box)
                    self.route_flag_editors[(suffix, flag_key)] = {"objective": rf_obj, "layout": rf_lay, "tips": rf_tips, "direction": rf_dir_group}

                layout.addWidget(rg_box)
                self.route_editors[suffix] = {"objective": r_obj, "layout": r_lay, "tips": r_tips, "direction": r_dir_group}
        
        layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)
        
        # OK/Cancel
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton(tr_ui("保存"))
        ok_btn.setStyleSheet(Styles.BUTTON)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(tr_ui("キャンセル"))
        cancel_btn.setStyleSheet(Styles.BUTTON)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)
    
    def _toggle_bold(self):
        """選択テキストの太字をトグル"""
        from PySide6.QtGui import QTextCharFormat
        cursor = self._active_editor.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        current = cursor.charFormat()
        if current.fontWeight() == QFont.Weight.Bold:
            fmt.setFontWeight(QFont.Weight.Normal)
        else:
            fmt.setFontWeight(QFont.Weight.Bold)
        cursor.mergeCharFormat(fmt)
    
    def _apply_color_to(self, editor, color: str):
        """指定エディタの選択テキストに色を適用"""
        from PySide6.QtGui import QTextCharFormat, QColor
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.mergeCharFormat(fmt)
    
    def _apply_reset_to(self, editor):
        """指定エディタの選択テキストの色をデフォルトに戻す"""
        from PySide6.QtGui import QTextCharFormat, QColor
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(Styles.TEXT_COLOR))
        cursor.mergeCharFormat(fmt)
    
    def _set_color(self, color: str):
        self._apply_color_to(self._active_editor, color)
    
    def _reset_color(self):
        self._apply_reset_to(self._active_editor)
    
    def _set_color_v2(self, color: str):
        self._apply_color_to(self.v2_layout_edit, color)
    
    def _reset_color_v2(self):
        self._apply_reset_to(self.v2_layout_edit)

    def _set_color_tips(self, color: str):
        self._apply_color_to(self.tips_edit, color)

    def _reset_color_tips(self):
        self._apply_reset_to(self.tips_edit)

    def _set_color_v2_tips(self, color: str):
        self._apply_color_to(self.v2_tips_edit, color)

    def _reset_color_v2_tips(self):
        self._apply_reset_to(self.v2_tips_edit)
    
    def _toggle_v2(self):
        """2回目セクションの表示切替"""
        visible = not self.v2_frame.isVisible()
        self.v2_frame.setVisible(visible)
        self.v2_toggle_btn.setText(self._v2_label_open if visible else self._v2_label_closed)
    
    def get_guide(self) -> dict:
        result = {
            "objective": self.objective_edit.toPlainText().strip(),
            "layout": self.layout_edit.to_storage_html(),
            "tips": self.tips_edit.to_storage_html(),
        }
        if self.direction_group is not None:
            direction = "none"
            checked = self.direction_group.checkedButton()
            if checked:
                direction = checked.property("dir_value")
            result["direction"] = direction
        if self._existing_summary:
            result["summary"] = self._existing_summary
        if self._existing_mini_navi:
            result["mini_navi"] = self._existing_mini_navi
        return result
    
    def get_guide_v2(self) -> dict:
        """2回目/フラグ進行後ガイドを取得（空なら空dict）"""
        result = {
            "objective": self.v2_objective_edit.toPlainText().strip(),
            "layout": self.v2_layout_edit.to_storage_html(),
            "tips": self.v2_tips_edit.to_storage_html(),
        }
        if self.v2_direction_group is not None:
            v2_direction = "inherit"
            checked = self.v2_direction_group.checkedButton()
            if checked:
                v2_direction = checked.property("dir_value")
            if v2_direction != "inherit":
                result["direction"] = v2_direction
        if self._existing_v2_summary:
            result["summary"] = self._existing_v2_summary
        if self._existing_v2_mini_navi:
            result["mini_navi"] = self._existing_v2_mini_navi
        
        if any(v for v in [result["objective"], result["layout"], result["tips"], result.get("summary", ""), result.get("mini_navi")]):
            return result
        if "direction" in result:
            return result
        return {}

    def get_route_guides(self) -> dict:
        """ルート別ガイドデータを取得 {suffix: {objective, layout, tips, direction, flags}}"""
        result = {}
        for suffix, editors in self.route_editors.items():
            r_direction = "none"
            checked = editors["direction"].checkedButton()
            if checked:
                r_direction = checked.property("dir_value")
            g = {
                "objective": editors["objective"].toPlainText().strip(),
                "layout": editors["layout"].to_storage_html(),
                "tips": editors["tips"].to_storage_html(),
                "direction": r_direction,
            }
            source_route = self.route_guides.get(suffix, {}) if isinstance(self.route_guides.get(suffix, {}), dict) else {}
            existing_mini = source_route.get("mini_navi")
            if existing_mini:
                g["mini_navi"] = existing_mini

            route_flags = source_route.get("flags", {}) if isinstance(source_route.get("flags", {}), dict) else {}
            new_flags = dict(route_flags)
            for (editor_suffix, flag_key), flag_editors in self.route_flag_editors.items():
                if editor_suffix != suffix:
                    continue
                direction = "inherit"
                checked = flag_editors["direction"].checkedButton()
                if checked:
                    direction = checked.property("dir_value")
                fg = {
                    "objective": flag_editors["objective"].toPlainText().strip(),
                    "layout": flag_editors["layout"].to_storage_html(),
                    "tips": flag_editors["tips"].to_storage_html(),
                }
                if direction != "inherit":
                    fg["direction"] = direction
                existing_flag_mini = route_flags.get(flag_key, {}).get("mini_navi") if isinstance(route_flags.get(flag_key, {}), dict) else None
                if existing_flag_mini:
                    fg["mini_navi"] = existing_flag_mini
                new_flags[flag_key] = fg
            if new_flags:
                g["flags"] = new_flags

            if any(v for v in g.values()):
                result[suffix] = g
            else:
                result[suffix] = g  # 空でも保持（キーは残す）
        return result

    def get_flag_guides(self) -> dict:
        """フラグ別ガイドデータを取得 {flag_key: {objective, layout, tips, direction}}"""
        result = {}
        for flag_key, editors in self.flag_editors.items():
            direction = "inherit"
            checked = editors["direction"].checkedButton()
            if checked:
                direction = checked.property("dir_value")
            g = {
                "objective": editors["objective"].toPlainText().strip(),
                "layout": editors["layout"].to_storage_html(),
                "tips": editors["tips"].to_storage_html(),
            }
            if direction != "inherit":
                g["direction"] = direction
            existing_mini = self.flag_guides.get(flag_key, {}).get("mini_navi") if isinstance(self.flag_guides.get(flag_key, {}), dict) else None
            if existing_mini:
                g["mini_navi"] = existing_mini
            if any(v for v in g.values()):
                result[flag_key] = g
            else:
                result[flag_key] = g  # 空でも枠を保持
        return result


class GuideSummaryEditorDialog(QDialog):
    """PoE2用: エリアごとの中級者向けサマリー編集ダイアログ"""

    COLORS = GuideEditorDialog.COLORS

    def __init__(self, parent, zone_name: str, entry: dict):
        super().__init__(parent)
        self.setWindowTitle(tr_ui(f"要約編集 — {zone_name}"))
        self.resize(520, 460)
        self.setStyleSheet(Styles.MAIN_WINDOW)

        self.entry = entry if isinstance(entry, dict) else {}
        self.default_guide = self.entry.get("default", {}) if isinstance(self.entry.get("default", {}), dict) else {}
        self.flag_guides = self.entry.get("flags", {}) if isinstance(self.entry.get("flags", {}), dict) else {}
        self.flag_editors = {}
        self.summary_count_labels = {}

        main_layout = QVBoxLayout(self)

        hint = QLabel(tr_ui("中級者向け表示で使う要点だけを書きます。未入力の場合は通常ガイドを表示します。"))
        hint.setStyleSheet("color: #888888; font-size: 11px;")
        hint.setWordWrap(True)
        main_layout.addWidget(hint)

        text_style = f"""
            QTextEdit {{
                background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176,255,123,0.3); border-radius: 4px;
                padding: 6px; font-size: 12px;
                font-family: "MS Gothic", "Yu Gothic", "Meiryo", monospace;
            }}
        """
        label_style = f"color: {Styles.TEXT_COLOR}; font-size: 12px; font-weight: bold;"

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(8)

        default_header = self._build_summary_header(tr_ui("通常時 summary"), "default", label_style)
        body_layout.addLayout(default_header)
        self.default_summary_edit = RichTextEdit()
        self.default_summary_edit.set_from_html(self.default_guide.get("summary", ""))
        self.default_summary_edit.setFixedHeight(90)
        self.default_summary_edit.setStyleSheet(text_style)
        self.default_summary_edit.textChanged.connect(lambda key="default", editor=self.default_summary_edit: self._update_summary_count(key, editor))
        body_layout.addLayout(self._build_color_toolbar(self.default_summary_edit))
        body_layout.addWidget(self.default_summary_edit)
        self._update_summary_count("default", self.default_summary_edit)

        for flag_key, guide in self.flag_guides.items():
            if not isinstance(guide, dict):
                continue
            flag_header = self._build_summary_header(f"フラグ進行後 summary: {flag_key}", flag_key, label_style)
            body_layout.addLayout(flag_header)
            edit = RichTextEdit()
            edit.set_from_html(guide.get("summary", ""))
            edit.setFixedHeight(90)
            edit.setStyleSheet(text_style)
            edit.textChanged.connect(lambda key=flag_key, editor=edit: self._update_summary_count(key, editor))
            body_layout.addLayout(self._build_color_toolbar(edit))
            body_layout.addWidget(edit)
            self.flag_editors[flag_key] = edit
            self._update_summary_count(flag_key, edit)

        body_layout.addStretch()
        scroll.setWidget(body)
        main_layout.addWidget(scroll)

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QPushButton(tr_ui("キャンセル"))
        cancel_btn.setStyleSheet(Styles.BUTTON)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        save_btn = QPushButton(tr_ui("保存"))
        save_btn.setStyleSheet(Styles.BUTTON)
        save_btn.clicked.connect(self.accept)
        button_row.addWidget(save_btn)
        main_layout.addLayout(button_row)

    def _build_summary_header(self, title: str, key: str, label_style: str):
        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet(label_style)
        header.addWidget(title_label)
        header.addStretch()
        count_label = QLabel(tr_ui("0文字"))
        count_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        header.addWidget(count_label)
        self.summary_count_labels[key] = count_label
        return header

    def _update_summary_count(self, key: str, editor):
        label = self.summary_count_labels.get(key)
        if label is None:
            return
        count = len(editor.toPlainText())
        if count <= 80:
            color = "#aaaaaa"
        elif count <= 140:
            color = "#dddd44"
        else:
            color = "#ff8888"
        label.setText(tr_ui(f"{count}文字"))
        label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: {'bold' if count > 140 else 'normal'};")

    def _build_color_toolbar(self, editor):
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        for color_code, color_name in self.COLORS:
            cbtn = QPushButton()
            cbtn.setFixedSize(22, 22)
            cbtn.setToolTip(f"{_translated_color_name(color_name)} ({color_code})")
            cbtn.setStyleSheet(f"""
                QPushButton {{
                    background: {color_code};
                    border: 2px solid rgba(255,255,255,0.3);
                    border-radius: 3px;
                }}
                QPushButton:hover {{ border: 2px solid #ffffff; }}
            """)
            cbtn.clicked.connect(lambda checked, e=editor, c=color_code: self._apply_color_to(e, c))
            toolbar.addWidget(cbtn)

        reset_color_btn = QPushButton("✕")
        reset_color_btn.setFixedSize(22, 22)
        reset_color_btn.setToolTip(tr_ui("色をリセット"))
        reset_color_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(40,40,40,200); color: #888;
                border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; font-size: 11px;
            }}
            QPushButton:hover {{ background: rgba(80,80,80,200); }}
        """)
        reset_color_btn.clicked.connect(lambda checked, e=editor: self._reset_color(e))
        toolbar.addWidget(reset_color_btn)
        toolbar.addStretch()
        return toolbar

    def _apply_color_to(self, editor, color: str):
        from PySide6.QtGui import QTextCharFormat, QColor
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.mergeCharFormat(fmt)

    def _reset_color(self, editor):
        from PySide6.QtGui import QTextCharFormat, QColor
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(Styles.TEXT_COLOR))
        cursor.mergeCharFormat(fmt)

    def apply_to_entry(self, entry: dict) -> dict:
        result = entry if isinstance(entry, dict) else {}
        if "default" not in result or not isinstance(result.get("default"), dict):
            result = {"default": dict(result) if result else {}, "flags": {}}
        if "flags" not in result or not isinstance(result.get("flags"), dict):
            result["flags"] = {}

        default_summary = self.default_summary_edit.to_storage_html()
        if default_summary:
            result["default"]["summary"] = default_summary
        else:
            result["default"].pop("summary", None)

        for flag_key, edit in self.flag_editors.items():
            if flag_key not in result["flags"] or not isinstance(result["flags"].get(flag_key), dict):
                result["flags"][flag_key] = {}
            summary = edit.to_storage_html()
            if summary:
                result["flags"][flag_key]["summary"] = summary
            else:
                result["flags"][flag_key].pop("summary", None)
        return result


class MiniNaviEditorDialog(QDialog):
    """PoE1用: みになび編集ダイアログ"""

    COLORS = GuideEditorDialog.COLORS

    def __init__(self, parent, zone_name: str, sections: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(tr_ui(f"みになび編集 — {zone_name}"))
        self.resize(520, 560)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self.sections = sections
        self.section_editors = []

        main_layout = QVBoxLayout(self)

        text_style = f"""
            QTextEdit {{
                background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176,255,123,0.3); border-radius: 4px;
                padding: 6px; font-size: 12px;
                font-family: "MS Gothic", "Yu Gothic", "Meiryo", monospace;
            }}
        """
        label_style = f"color: {Styles.TEXT_COLOR}; font-size: 12px; font-weight: bold;"
        radio_style = f"""
            QRadioButton {{
                color: {Styles.TEXT_COLOR}; font-size: 20px;
                padding: 6px 10px;
                background: rgba(40,40,40,180);
                border: 1px solid rgba(176,255,123,0.2);
                border-radius: 4px;
                min-width: 36px; min-height: 28px;
            }}
            QRadioButton:checked {{
                background: rgba(176,255,123,0.2);
                border: 2px solid {Styles.TEXT_COLOR};
            }}
            QRadioButton:hover {{ background: rgba(80,80,80,200); }}
            QRadioButton::indicator {{ width: 0; height: 0; }}
        """

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(10)

        for section in self.sections:
            box = QGroupBox(section["title"])
            box.setStyleSheet(f"""
                QGroupBox {{ color: {Styles.TEXT_COLOR}; border: 1px solid rgba(176,255,123,0.3);
                    border-radius: 4px; margin-top: 8px; font-size: 11px; font-weight: bold; }}
                QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }}
            """)
            layout = QVBoxLayout(box)
            layout.setSpacing(6)

            guide = section.get("guide", {}) if isinstance(section.get("guide"), dict) else {}
            mini = guide.get("mini_navi", {}) if isinstance(guide, dict) else {}
            if not isinstance(mini, dict):
                mini = {"text": str(mini)} if mini else {}

            dir_label = QLabel(tr_ui("🧭 基本方向"))
            dir_label.setStyleSheet(label_style)
            layout.addWidget(dir_label)
            dir_grid = QGridLayout()
            dir_grid.setSpacing(2)
            direction_group = QButtonGroup(self)
            directions = [
                (0, 0, "↖", "nw"), (0, 1, "↑", "n"), (0, 2, "↗", "ne"),
                (1, 0, "←", "w"),  (1, 1, "—", "none"), (1, 2, "→", "e"),
                (2, 0, "↙", "sw"), (2, 1, "↓", "s"), (2, 2, "↘", "se"),
            ]
            allow_inherit = not (section.get("kind") == "visit" and section.get("visit") == 1 and not section.get("route"))
            if allow_inherit:
                directions.append((1, 3, "同上", "inherit"))
            current_dir = mini.get("direction", guide.get("direction", "inherit" if allow_inherit else "none"))
            for row, col, label, value in directions:
                rb = QRadioButton(tr_ui("同上") if label == "同上" else label)
                rb.setStyleSheet(radio_style if label != "同上" else f"""
                    QRadioButton {{ color: {Styles.TEXT_COLOR}; font-size: 11px; padding: 6px 8px;
                        background: rgba(40,40,40,180); border: 1px solid rgba(176,255,123,0.2);
                        border-radius: 4px; min-width: 36px; min-height: 28px; }}
                    QRadioButton:checked {{ background: rgba(176,255,123,0.2); border: 2px solid {Styles.TEXT_COLOR}; }}
                    QRadioButton:hover {{ background: rgba(80,80,80,200); }}
                    QRadioButton::indicator {{ width: 0; height: 0; }}
                """)
                rb.setProperty("dir_value", value)
                if value == current_dir:
                    rb.setChecked(True)
                direction_group.addButton(rb)
                dir_grid.addWidget(rb, row, col, Qt.AlignCenter)
            layout.addLayout(dir_grid)

            text_header = QHBoxLayout()
            text_label = QLabel(tr_ui("みになび本文"))
            text_label.setStyleSheet(label_style)
            text_header.addWidget(text_label)
            text_header.addStretch()
            count_label = QLabel(tr_ui("0文字"))
            count_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
            text_header.addWidget(count_label)
            layout.addLayout(text_header)

            editor = RichTextEdit()
            editor.set_from_html(mini.get("text", ""))
            editor.setFixedHeight(90)
            editor.setStyleSheet(text_style)
            editor.textChanged.connect(lambda e=editor, l=count_label: self._update_count(e, l))
            layout.addLayout(self._build_color_toolbar(editor))
            layout.addWidget(editor)
            self._update_count(editor, count_label)

            body_layout.addWidget(box)
            self.section_editors.append({
                "section": section,
                "editor": editor,
                "direction": direction_group,
            })

        body_layout.addStretch()
        scroll.setWidget(body)
        main_layout.addWidget(scroll)

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QPushButton(tr_ui("キャンセル"))
        cancel_btn.setStyleSheet(Styles.BUTTON)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        save_btn = QPushButton(tr_ui("保存"))
        save_btn.setStyleSheet(Styles.BUTTON)
        save_btn.clicked.connect(self.accept)
        button_row.addWidget(save_btn)
        main_layout.addLayout(button_row)

    def _update_count(self, editor, label):
        count = len(editor.toPlainText())
        if count <= 80:
            color = "#aaaaaa"
        elif count <= 140:
            color = "#dddd44"
        else:
            color = "#ff8888"
        label.setText(tr_ui(f"{count}文字"))
        label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: {'bold' if count > 140 else 'normal'};")

    def _build_color_toolbar(self, editor):
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        for color_code, color_name in self.COLORS:
            cbtn = QPushButton()
            cbtn.setFixedSize(22, 22)
            cbtn.setToolTip(f"{_translated_color_name(color_name)} ({color_code})")
            cbtn.setStyleSheet(f"""
                QPushButton {{ background: {color_code}; border: 2px solid rgba(255,255,255,0.3); border-radius: 3px; }}
                QPushButton:hover {{ border: 2px solid #ffffff; }}
            """)
            cbtn.clicked.connect(lambda checked, e=editor, c=color_code: self._apply_color_to(e, c))
            toolbar.addWidget(cbtn)
        reset_btn = QPushButton("✕")
        reset_btn.setFixedSize(22, 22)
        reset_btn.setToolTip(tr_ui("色をリセット"))
        reset_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(40,40,40,200); color: #888;
                border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; font-size: 11px; }}
            QPushButton:hover {{ background: rgba(80,80,80,200); }}
        """)
        reset_btn.clicked.connect(lambda checked, e=editor: self._reset_color(e))
        toolbar.addWidget(reset_btn)
        toolbar.addStretch()
        return toolbar

    def _apply_color_to(self, editor, color: str):
        from PySide6.QtGui import QTextCharFormat, QColor
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.mergeCharFormat(fmt)

    def _reset_color(self, editor):
        from PySide6.QtGui import QTextCharFormat, QColor
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(Styles.TEXT_COLOR))
        cursor.mergeCharFormat(fmt)

    def apply_to_sections(self):
        for item in self.section_editors:
            guide = item["section"].get("guide")
            if not isinstance(guide, dict):
                continue
            text = item["editor"].to_storage_html()
            checked = item["direction"].checkedButton()
            direction = checked.property("dir_value") if checked else "none"
            # みになび編集画面の「基本方向」は、通常ガイド側の方向にも同期する。
            # 「同上」は方向を明示保存せず、通常ガイド/1回目側の方向へフォールバックさせる。
            if direction == "inherit":
                guide.pop("direction", None)
                if text:
                    guide["mini_navi"] = {"text": text}
                else:
                    guide.pop("mini_navi", None)
            else:
                # 特に本文0文字の2回目ガイドでは、mini_navi.directionだけだと別の編集/保存経路で
                # 方向変更が保存されていないように見えるため、セクション本体のdirectionも正とする。
                guide["direction"] = direction
                if text or direction != "none":
                    guide["mini_navi"] = {"text": text, "direction": direction}
                else:
                    guide.pop("mini_navi", None)


class SettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle(tr_ui("設定"))
        self.resize(500, 600)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        
        self.current_config = current_config or {}
        self.hotkeys = self.current_config.get("hotkeys", {
            "start_stop": "F1", 
            "reset": "F2",
            "lap": "F3",
            "undo_lap": "F4",
            "click_through": "F6",
            "logout": "F5",
            "hideout": "F11",
            "monastery": "F12",
            "search_string_test": "none",
            "poetore_capture": "alt+d",
        })
        self.poe_version = self.current_config.get("poe_version", POE1)
        self.poe_version_mode = self.current_config.get("poe_version_mode", "ask")
        self.language = self.current_config.get("language", get_locale())
        zone_master_data = load_zone_master_data()
        self.zone_data_by_version = zone_master_data["zone_data_by_version"]
        self.town_zones_by_version = zone_master_data["town_zones_by_version"]
        self.zone_data = self.zone_data_by_version.get(self.poe_version, {})
        self.guide_data = load_guide_data(self.poe_version, language=self.language)
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # タブ切り替え
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {Styles.TEXT_COLOR}; }}
            QTabBar::tab {{ 
                background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR}; 
                padding: 8px 16px; border: 1px solid {Styles.TEXT_COLOR};
                border-bottom: none; border-radius: 4px 4px 0 0;
            }}
            QTabBar::tab:selected {{ background: rgba(60,60,60,200); }}
        """)
        
        # ── Tab 1: General ──
        general_tab = QScrollArea()
        general_tab.setWidgetResizable(True)
        general_tab.setStyleSheet("QScrollArea { border: none; }")
        general_content = QWidget()
        general_layout = QVBoxLayout(general_content)
        general_tab.setWidget(general_content)

        language_group = QGroupBox(tr("startup.language_title"))
        language_layout = QHBoxLayout(language_group)
        language_layout.addWidget(QLabel(tr("settings.language")))
        self.language_combo = QComboBox()
        self.language_combo.addItem(tr("settings.language_japanese"), JA)
        self.language_combo.addItem(tr("settings.language_english"), EN)
        language_index = self.language_combo.findData(self.language)
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)
        language_layout.addWidget(self.language_combo)
        language_layout.addWidget(QLabel(tr("settings.language_help")))
        language_layout.addStretch()
        general_layout.addWidget(language_group)
        
        # 共通スタイル
        group_style = f"QGroupBox {{ color: {Styles.TEXT_COLOR}; border: 1px solid {Styles.TEXT_COLOR}; border-radius: 5px; margin-top: 10px; }} QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; }}"
        checkbox_style = f"""
            QCheckBox {{ color: {Styles.TEXT_COLOR}; font-size: 12px; spacing: 8px; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; border: 2px solid {Styles.TEXT_COLOR}; border-radius: 3px; background: transparent; }}
            QCheckBox::indicator:checked {{ background: {Styles.TEXT_COLOR}; }}
        """
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
        
        # ━━━━━ 1. PoE ログファイル ━━━━━
        log_group = QGroupBox(tr_ui("PoE ログファイル"))
        log_group.setStyleSheet(group_style)
        log_layout = QVBoxLayout(log_group)

        self.log_path_edits = {
            POE1: QLineEdit(self.current_config.get("client_log_paths", {}).get(POE1, "")),
            POE2: QLineEdit(self.current_config.get("client_log_paths", {}).get(POE2, "")),
        }
        for version, label_text in (
            (POE1, tr_ui("PoE1ログファイル:")),
            (POE2, tr_ui("PoE2ログファイル:")),
        ):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
            row.addWidget(label)
            edit = self.log_path_edits[version]
            edit.setPlaceholderText("C:\\Program Files (x86)\\...\\logs\\Client.txt")
            edit.setStyleSheet(f"""
                QLineEdit {{ 
                    background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR}; 
                    border: 1px solid {Styles.TEXT_COLOR}; border-radius: 4px; padding: 5px;
                }}
            """)
            row.addWidget(edit)
            browse_btn = QPushButton(tr_ui("参照"))
            browse_btn.setStyleSheet(Styles.BUTTON)
            browse_btn.clicked.connect(lambda checked, v=version: self.browse_log_file(v))
            row.addWidget(browse_btn)
            log_layout.addLayout(row)

        general_layout.addWidget(log_group)

        # ━━━━━ PoEバージョン ━━━━━
        poe_group = QGroupBox(tr_ui("PoEバージョン"))
        poe_group.setStyleSheet(group_style)
        poe_layout = QVBoxLayout(poe_group)

        self.poe_version_group = QButtonGroup(self)
        self.poe_version_radios = {}
        radio_style = f"""
            QRadioButton {{ color: {Styles.TEXT_COLOR}; font-size: 13px; spacing: 8px; padding: 4px 0; }}
            QRadioButton::indicator {{ width: 16px; height: 16px; border: 2px solid {Styles.TEXT_COLOR}; border-radius: 8px; background: transparent; }}
            QRadioButton::indicator:checked {{ background: {Styles.TEXT_COLOR}; }}
        """
        for version in POE_VERSION_ORDER:
            radio = QRadioButton(get_poe_label(version))
            radio.setChecked(version == self.poe_version)
            radio.toggled.connect(lambda checked, v=version: self._on_poe_version_changed(v, checked))
            radio.setStyleSheet(radio_style)
            poe_layout.addWidget(radio)
            self.poe_version_group.addButton(radio)
            self.poe_version_radios[version] = radio

        mode_row = QHBoxLayout()
        mode_label = QLabel(tr_ui("起動時:"))
        mode_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        mode_row.addWidget(mode_label)

        self.poe_version_mode_combo = QComboBox()
        self.poe_version_mode_combo.addItem(tr_ui("毎回確認"), "ask")
        self.poe_version_mode_combo.addItem(tr_ui("PoE1固定"), POE1)
        self.poe_version_mode_combo.addItem(tr_ui("PoE2固定"), POE2)
        self.poe_version_mode_combo.setFixedWidth(120)
        self.poe_version_mode_combo.setStyleSheet(combo_style)
        idx = self.poe_version_mode_combo.findData(self.poe_version_mode)
        if idx >= 0:
            self.poe_version_mode_combo.setCurrentIndex(idx)
        mode_row.addWidget(self.poe_version_mode_combo)
        mode_row.addStretch()
        poe_layout.addLayout(mode_row)

        general_layout.addWidget(poe_group)
        
        # ━━━━━ 2. ホットキー ━━━━━
        group = QGroupBox(tr_ui("ホットキー"))
        group.setStyleSheet(group_style)
        group_layout = QVBoxLayout(group)
        
        hotkey_hint = QLabel(tr_ui("※ DeleteまたはBackspaceで解除できます"))
        hotkey_hint.setStyleSheet("color: #888888; font-size: 10px;")
        group_layout.addWidget(hotkey_hint)
        
        h_layout1 = QHBoxLayout()
        h_layout1.addWidget(QLabel(tr_ui("開始/停止:")))
        self.start_stop_btn = HotkeyButton(self.hotkeys.get("start_stop", "F1"))
        h_layout1.addWidget(self.start_stop_btn)
        group_layout.addLayout(h_layout1)
        
        h_layout2 = QHBoxLayout()
        h_layout2.addWidget(QLabel(tr_ui("リセット:")))
        self.reset_btn = HotkeyButton(self.hotkeys.get("reset", "F2"))
        h_layout2.addWidget(self.reset_btn)
        group_layout.addLayout(h_layout2)
        
        h_layout3 = QHBoxLayout()
        h_layout3.addWidget(QLabel(tr_ui("ラップ（次のAct）:")))
        self.lap_btn = HotkeyButton(self.hotkeys.get("lap", "F3"))
        h_layout3.addWidget(self.lap_btn)
        group_layout.addLayout(h_layout3)
        
        h_layout4 = QHBoxLayout()
        h_layout4.addWidget(QLabel(tr_ui("ラップ取消:")))
        self.undo_lap_btn = HotkeyButton(self.hotkeys.get("undo_lap", "F4"))
        h_layout4.addWidget(self.undo_lap_btn)
        group_layout.addLayout(h_layout4)
        
        h_layout5 = QHBoxLayout()
        h_layout5.addWidget(QLabel(tr_ui("クリックスルー:")))
        self.click_through_btn = HotkeyButton(self.hotkeys.get("click_through", "F6"))
        h_layout5.addWidget(self.click_through_btn)
        group_layout.addLayout(h_layout5)
        
        h_layout6 = QHBoxLayout()
        h_layout6.addWidget(QLabel(tr_ui("ログアウト:")))
        self.logout_btn = HotkeyButton(self.hotkeys.get("logout", "F5"))
        h_layout6.addWidget(self.logout_btn)
        group_layout.addLayout(h_layout6)

        h_layout7 = QHBoxLayout()
        h_layout7.addWidget(QLabel(tr_ui("隠れ家へ移動（/hideout）:")))
        self.hideout_btn = HotkeyButton(self.hotkeys.get("hideout", "F11"))
        h_layout7.addWidget(self.hideout_btn)
        group_layout.addLayout(h_layout7)

        h_layout8 = QHBoxLayout()
        h_layout8.addWidget(QLabel(tr_ui("（仮）修道院へ移動（/monastery）:")))
        self.monastery_btn = HotkeyButton(self.hotkeys.get("monastery", "F12"))
        h_layout8.addWidget(self.monastery_btn)
        group_layout.addLayout(h_layout8)

        h_layout9 = QHBoxLayout()
        h_layout9.addWidget(QLabel(tr_ui("検索文字列の貼り付け:")))
        self.search_string_test_btn = HotkeyButton(self.hotkeys.get("search_string_test", "none"))
        h_layout9.addWidget(self.search_string_test_btn)
        group_layout.addLayout(h_layout9)

        h_layout10 = QHBoxLayout()
        h_layout10.addWidget(QLabel(tr_ui("ぽえとれ検索:")))
        self.poetore_capture_btn = HotkeyButton(
            self.hotkeys.get("poetore_capture", "alt+d")
        )
        h_layout10.addWidget(self.poetore_capture_btn)
        group_layout.addLayout(h_layout10)
        
        self.logout_enabled_cb = QCheckBox(tr_ui("ログアウト機能を有効にする（TCP切断）"))
        self.logout_enabled_cb.setChecked(self.current_config.get("logout_enabled", True))
        Styles.apply_checkbox_style(self.logout_enabled_cb)
        group_layout.addWidget(self.logout_enabled_cb)
        
        general_layout.addWidget(group)
        
        # ━━━━━ 3. タイマー表示 ━━━━━
        timer_group = QGroupBox(tr_ui("タイマー表示"))
        timer_group.setStyleSheet(group_style)
        timer_layout = QVBoxLayout(timer_group)
        
        # タイマーサイズ
        timer_size_row = QHBoxLayout()
        timer_size_label = QLabel(tr_ui("タイマーサイズ:"))
        timer_size_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        timer_size_row.addWidget(timer_size_label)
        
        self.timer_size_combo = QComboBox()
        self.timer_size_combo.addItem(tr_ui("大"), "large")
        self.timer_size_combo.addItem(tr_ui("中"), "medium")
        self.timer_size_combo.addItem(tr_ui("小"), "small")
        self.timer_size_combo.addItem(tr_ui("オフ"), "off")
        self.timer_size_combo.setFixedWidth(100)
        self.timer_size_combo.setStyleSheet(combo_style)
        current_timer_size = self.current_config.get("timer_size", "large")
        idx = self.timer_size_combo.findData(current_timer_size)
        if idx >= 0:
            self.timer_size_combo.setCurrentIndex(idx)
        timer_size_row.addWidget(self.timer_size_combo)
        timer_size_row.addStretch()
        timer_layout.addLayout(timer_size_row)
        
        # リセット確認ダイアログ
        self.confirm_reset_cb = QCheckBox(tr_ui("タイマーリセット時に確認ダイアログを表示する"))
        self.confirm_reset_cb.setChecked(self.current_config.get("confirm_reset", True))
        Styles.apply_checkbox_style(self.confirm_reset_cb)
        timer_layout.addWidget(self.confirm_reset_cb)
        
        general_layout.addWidget(timer_group)
        
        # ━━━━━ 4. ガイド表示 ━━━━━
        font_group = QGroupBox(tr_ui("ガイド表示"))
        font_group.setStyleSheet(group_style)
        font_group_layout = QVBoxLayout(font_group)
        
        font_row = QHBoxLayout()
        font_label = QLabel(tr_ui("フォントサイズ:"))
        font_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        font_row.addWidget(font_label)
        
        self.guide_font_spin = QSpinBox()
        self.guide_font_spin.setRange(8, 20)
        self.guide_font_spin.setValue(self.current_config.get("guide_font_size", 12))
        self.guide_font_spin.setSuffix(" px")
        self.guide_font_spin.setFixedWidth(100)
        self.guide_font_spin.setStyleSheet(_spinbox_style(width=80, height=30))
        font_row.addWidget(self.guide_font_spin)
        font_row.addStretch()
        font_group_layout.addLayout(font_row)
        
        from PySide6.QtWidgets import QComboBox as _QComboBox
        guide_level_row = QHBoxLayout()
        guide_level_tag = QLabel(tr_ui("PoE2専用"))
        guide_level_tag.setStyleSheet("""
            QLabel {
                color: #111111;
                background: #b0ff7b;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: bold;
            }
        """)
        guide_level_row.addWidget(guide_level_tag)
        guide_level_label = QLabel(tr_ui("ガイド表示:"))
        guide_level_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        guide_level_row.addWidget(guide_level_label)
        self.guide_detail_level_combo = _QComboBox()
        self.guide_detail_level_combo.addItem(tr_ui("初心者向け（詳細）"), "beginner")
        self.guide_detail_level_combo.addItem(tr_ui("中級者向け（要点）"), "intermediate")
        self.guide_detail_level_combo.setStyleSheet(combo_style)
        cur_guide_level = self.current_config.get("guide_detail_level", "beginner")
        idx_level = self.guide_detail_level_combo.findData(cur_guide_level)
        if idx_level >= 0:
            self.guide_detail_level_combo.setCurrentIndex(idx_level)
        guide_level_row.addWidget(self.guide_detail_level_combo)
        guide_level_row.addStretch()
        font_group_layout.addLayout(guide_level_row)
        
        # ルート選択
        poe1_only_tag_style = """
            QLabel {
                color: #111111;
                background: #b0ff7b;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: bold;
            }
        """
        poe1_route_act3_row = QHBoxLayout()
        route_poe1_tag = QLabel(tr_ui("PoE1専用"))
        route_poe1_tag.setStyleSheet(poe1_only_tag_style)
        poe1_route_act3_row.addWidget(route_poe1_tag)
        poe1_route_act3_label = QLabel(tr_ui("Act3 ルート:"))
        poe1_route_act3_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        poe1_route_act3_row.addWidget(poe1_route_act3_label)
        self.poe1_route_act3_combo = _QComboBox()
        self.poe1_route_act3_combo.addItem(tr_ui("通常ルート（図書館スキップ）"), "standard")
        self.poe1_route_act3_combo.addItem(tr_ui("図書館寄り道ルート"), "library_detour")
        self.poe1_route_act3_combo.setStyleSheet(combo_style)
        cur3 = ConfigManager.effective_poe1_route_act3(self.current_config)
        idx3 = self.poe1_route_act3_combo.findData(cur3)
        if idx3 >= 0:
            self.poe1_route_act3_combo.setCurrentIndex(idx3)
        poe1_route_act3_row.addWidget(self.poe1_route_act3_combo)
        poe1_route_act3_row.addStretch()
        font_group_layout.addLayout(poe1_route_act3_row)
        
        poe1_route_act8_row = QHBoxLayout()
        route_poe1_tag2 = QLabel(tr_ui("PoE1専用"))
        route_poe1_tag2.setStyleSheet(poe1_only_tag_style)
        poe1_route_act8_row.addWidget(route_poe1_tag2)
        poe1_route_act8_label = QLabel(tr_ui("Act8 ルート:"))
        poe1_route_act8_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        poe1_route_act8_row.addWidget(poe1_route_act8_label)
        self.poe1_route_act8_combo = _QComboBox()
        self.poe1_route_act8_combo.addItem(tr_ui("通常ルート"), "standard")
        self.poe1_route_act8_combo.addItem(tr_ui("隠れた裏道（The Hidden Underbelly）ルート"), "underbelly")
        self.poe1_route_act8_combo.setStyleSheet(combo_style)
        cur8 = ConfigManager.effective_poe1_route_act8(self.current_config)
        idx8 = self.poe1_route_act8_combo.findData(cur8)
        if idx8 >= 0:
            self.poe1_route_act8_combo.setCurrentIndex(idx8)
        poe1_route_act8_row.addWidget(self.poe1_route_act8_combo)
        poe1_route_act8_row.addStretch()
        font_group_layout.addLayout(poe1_route_act8_row)
        
        general_layout.addWidget(font_group)
        
        # ━━━━━ 5. マップ表示 ━━━━━
        map_group = QGroupBox(tr_ui("マップ表示"))
        map_group.setStyleSheet(group_style)
        map_layout = QVBoxLayout(map_group)

        self.auto_open_map_check = QCheckBox(tr_ui("エリア移動時にマップレイアウトの拡大画像を自動で開く"))
        Styles.apply_checkbox_style(self.auto_open_map_check)
        self.auto_open_map_check.setChecked(self.current_config.get("auto_open_map", False))
        map_layout.addWidget(self.auto_open_map_check)

        self.auto_position_map_check = QCheckBox(tr_ui("マップレイアウトの拡大画像を開く際、ぽえなびの隣に自動配置する"))
        Styles.apply_checkbox_style(self.auto_position_map_check)
        self.auto_position_map_check.setChecked(self.current_config.get("auto_position_map", True))
        map_layout.addWidget(self.auto_position_map_check)

        general_layout.addWidget(map_group)
        
        # ━━━━━ 6. ウィンドウ設定 ━━━━━
        window_group = QGroupBox(tr_ui("ウィンドウ設定（本体）"))
        window_group.setStyleSheet(group_style)
        window_layout = QVBoxLayout(window_group)
        window_layout.setSpacing(10)
        
        # 透過率
        opacity_row = QHBoxLayout()
        opacity_label = QLabel(tr_ui("透過率:"))
        opacity_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        opacity_row.addWidget(opacity_label)

        from PySide6.QtWidgets import QSlider
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setValue(self.current_config.get("window_opacity", 100))
        self.opacity_slider.setFixedWidth(200)
        self.opacity_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ background: #555; height: 6px; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {Styles.TEXT_COLOR}; width: 16px; margin: -5px 0; border-radius: 8px; }}
        """)
        opacity_row.addWidget(self.opacity_slider)

        self.opacity_value_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_value_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        self.opacity_value_label.setFixedWidth(40)
        opacity_row.addWidget(self.opacity_value_label)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_value_label.setText(f"{v}%"))
        opacity_row.addStretch()
        window_layout.addLayout(opacity_row)
        
        # 文字透過率
        text_opacity_row = QHBoxLayout()
        text_opacity_label = QLabel(tr_ui("文字透過率:"))
        text_opacity_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        text_opacity_row.addWidget(text_opacity_label)

        from PySide6.QtWidgets import QSlider as _QSlider
        self.text_opacity_slider = _QSlider(Qt.Horizontal)
        self.text_opacity_slider.setRange(0, 100)
        self.text_opacity_slider.setValue(self.current_config.get("text_opacity", 100))
        self.text_opacity_slider.setFixedWidth(200)
        self.text_opacity_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ background: #555; height: 6px; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {Styles.TEXT_COLOR}; width: 16px; margin: -5px 0; border-radius: 8px; }}
        """)
        text_opacity_row.addWidget(self.text_opacity_slider)

        self.text_opacity_value_label = QLabel(f"{self.text_opacity_slider.value()}%")
        self.text_opacity_value_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        self.text_opacity_value_label.setFixedWidth(40)
        text_opacity_row.addWidget(self.text_opacity_value_label)
        self.text_opacity_slider.valueChanged.connect(lambda v: self.text_opacity_value_label.setText(f"{v}%"))
        text_opacity_row.addStretch()
        window_layout.addLayout(text_opacity_row)
        
        # ウィンドウロック
        self.window_lock_check = QCheckBox(tr_ui("ウィンドウの移動・リサイズを禁止する"))
        Styles.apply_checkbox_style(self.window_lock_check)
        self.window_lock_check.setChecked(self.current_config.get("window_locked", False))
        window_layout.addWidget(self.window_lock_check)

        # 常に最前面表示
        self.always_on_top_check = QCheckBox(tr_ui("常に最前面に表示する"))
        Styles.apply_checkbox_style(self.always_on_top_check)
        self.always_on_top_check.setChecked(self.current_config.get("always_on_top", True))
        window_layout.addWidget(self.always_on_top_check)
        
        # 右端配置チェックボックス
        self.snap_right_edge_cb = QCheckBox(tr_ui("起動時にモニター右端に配置"))
        self.snap_right_edge_cb.setChecked(self.current_config.get("snap_to_right_edge", False))
        Styles.apply_checkbox_style(self.snap_right_edge_cb)
        window_layout.addWidget(self.snap_right_edge_cb)
        
        # モニター選択
        monitor_row = QHBoxLayout()
        monitor_label = QLabel(tr_ui("起動時の配置先:"))
        monitor_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        monitor_row.addWidget(monitor_label)
        self.monitor_combo = QComboBox()
        self.monitor_combo.setStyleSheet(combo_style)
        screens = QApplication.screens()
        current_monitor = self.current_config.get("display_monitor", 0)
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            name = tr_ui(f"モニター {i + 1}（{geo.width()}x{geo.height()}）")
            if screen == QApplication.primaryScreen():
                name += tr_ui(" [メイン]")
            self.monitor_combo.addItem(name, i)
        if 0 <= current_monitor < len(screens):
            self.monitor_combo.setCurrentIndex(current_monitor)
        monitor_row.addWidget(self.monitor_combo)
        monitor_row.addStretch()
        window_layout.addLayout(monitor_row)
        
        # チェックボックスとモニター選択の連動
        self._monitor_label = monitor_label
        def _update_monitor_enabled(checked):
            self.monitor_combo.setEnabled(checked)
            self._monitor_label.setStyleSheet(
                f"color: {Styles.TEXT_COLOR}; font-size: 12px;" if checked
                else "color: #555555; font-size: 12px;"
            )
        _update_monitor_enabled(self.snap_right_edge_cb.isChecked())
        self.snap_right_edge_cb.toggled.connect(_update_monitor_enabled)
        
        general_layout.addWidget(window_group)

        # ━━━━━ 7. みになびウィンドウ設定 ━━━━━
        mini_navi_window_group = QGroupBox(tr_ui("ウィンドウ設定（みになび）"))
        mini_navi_window_group.setStyleSheet(group_style)
        mini_navi_window_layout = QVBoxLayout(mini_navi_window_group)
        mini_navi_window_layout.setSpacing(10)

        mini_navi_config = self.current_config.get("mini_guide_overlay", {})
        mini_navi_display_mode_row = QHBoxLayout()
        mini_navi_display_mode_label = QLabel(tr_ui("表示形式:"))
        mini_navi_display_mode_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        mini_navi_display_mode_row.addWidget(mini_navi_display_mode_label)
        self.mini_navi_display_mode_combo = QComboBox()
        self.mini_navi_display_mode_combo.addItem(tr_ui("標準"), "standard")
        self.mini_navi_display_mode_combo.addItem(tr_ui("コンパクト"), "compact")
        display_mode = mini_navi_config.get("display_mode", "standard") if isinstance(mini_navi_config, dict) else "standard"
        self.mini_navi_display_mode_combo.setCurrentIndex(
            max(0, self.mini_navi_display_mode_combo.findData(display_mode))
        )
        self.mini_navi_display_mode_combo.setFixedWidth(120)
        self.mini_navi_display_mode_combo.setStyleSheet(combo_style)
        mini_navi_display_mode_row.addWidget(self.mini_navi_display_mode_combo)
        mini_navi_display_mode_row.addStretch()
        mini_navi_window_layout.addLayout(mini_navi_display_mode_row)

        mini_navi_font_size = int(mini_navi_config.get("font_size", 15)) if isinstance(mini_navi_config, dict) else 15
        mini_navi_font_row = QHBoxLayout()
        mini_navi_font_label = QLabel(tr_ui("フォントサイズ:"))
        mini_navi_font_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        mini_navi_font_row.addWidget(mini_navi_font_label)
        self.mini_navi_font_size_combo = QComboBox()
        self.mini_navi_font_size_combo.addItem(tr_ui("小"), 15)
        self.mini_navi_font_size_combo.addItem(tr_ui("中"), 18)
        self.mini_navi_font_size_combo.addItem(tr_ui("大"), 22)
        self.mini_navi_font_size_combo.setFixedWidth(100)
        self.mini_navi_font_size_combo.setStyleSheet(combo_style)
        if mini_navi_font_size <= 16:
            self.mini_navi_font_size_combo.setCurrentIndex(self.mini_navi_font_size_combo.findData(15))
        elif mini_navi_font_size <= 20:
            self.mini_navi_font_size_combo.setCurrentIndex(self.mini_navi_font_size_combo.findData(18))
        else:
            self.mini_navi_font_size_combo.setCurrentIndex(self.mini_navi_font_size_combo.findData(22))
        mini_navi_font_row.addWidget(self.mini_navi_font_size_combo)
        mini_navi_font_row.addStretch()
        mini_navi_window_layout.addLayout(mini_navi_font_row)

        # みになび専用のウィンドウ透過率
        mini_navi_window_opacity_row = QHBoxLayout()
        mini_navi_window_opacity_label = QLabel(tr_ui("ウィンドウ透過率:"))
        mini_navi_window_opacity_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        mini_navi_window_opacity_row.addWidget(mini_navi_window_opacity_label)
        self.mini_navi_window_opacity_slider = QSlider(Qt.Horizontal)
        self.mini_navi_window_opacity_slider.setRange(5, 100)
        self.mini_navi_window_opacity_slider.setValue(int(mini_navi_config.get("window_opacity", 100)) if isinstance(mini_navi_config, dict) else 100)
        self.mini_navi_window_opacity_slider.setFixedWidth(200)
        self.mini_navi_window_opacity_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ background: #555; height: 6px; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {Styles.TEXT_COLOR}; width: 16px; margin: -5px 0; border-radius: 8px; }}
        """)
        mini_navi_window_opacity_row.addWidget(self.mini_navi_window_opacity_slider)
        self.mini_navi_window_opacity_value_label = QLabel(f"{self.mini_navi_window_opacity_slider.value()}%")
        self.mini_navi_window_opacity_value_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        self.mini_navi_window_opacity_value_label.setFixedWidth(40)
        mini_navi_window_opacity_row.addWidget(self.mini_navi_window_opacity_value_label)
        self.mini_navi_window_opacity_slider.valueChanged.connect(lambda v: self.mini_navi_window_opacity_value_label.setText(f"{v}%"))
        mini_navi_window_opacity_row.addStretch()
        mini_navi_window_layout.addLayout(mini_navi_window_opacity_row)

        # みになび専用の文字透過率
        mini_navi_text_opacity_row = QHBoxLayout()
        mini_navi_text_opacity_label = QLabel(tr_ui("文字透過率:"))
        mini_navi_text_opacity_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        mini_navi_text_opacity_row.addWidget(mini_navi_text_opacity_label)
        self.mini_navi_text_opacity_slider = QSlider(Qt.Horizontal)
        self.mini_navi_text_opacity_slider.setRange(0, 100)
        self.mini_navi_text_opacity_slider.setValue(int(mini_navi_config.get("text_opacity", 100)) if isinstance(mini_navi_config, dict) else 100)
        self.mini_navi_text_opacity_slider.setFixedWidth(200)
        self.mini_navi_text_opacity_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ background: #555; height: 6px; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {Styles.TEXT_COLOR}; width: 16px; margin: -5px 0; border-radius: 8px; }}
        """)
        mini_navi_text_opacity_row.addWidget(self.mini_navi_text_opacity_slider)
        self.mini_navi_text_opacity_value_label = QLabel(f"{self.mini_navi_text_opacity_slider.value()}%")
        self.mini_navi_text_opacity_value_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        self.mini_navi_text_opacity_value_label.setFixedWidth(40)
        mini_navi_text_opacity_row.addWidget(self.mini_navi_text_opacity_value_label)
        self.mini_navi_text_opacity_slider.valueChanged.connect(lambda v: self.mini_navi_text_opacity_value_label.setText(f"{v}%"))
        mini_navi_text_opacity_row.addStretch()
        mini_navi_window_layout.addLayout(mini_navi_text_opacity_row)

        self.mini_navi_always_on_top_cb = QCheckBox(tr_ui("常に最前面に表示する"))
        self.mini_navi_always_on_top_cb.setChecked(bool(mini_navi_config.get("always_on_top", True)) if isinstance(mini_navi_config, dict) else True)
        Styles.apply_checkbox_style(self.mini_navi_always_on_top_cb)
        mini_navi_window_layout.addWidget(self.mini_navi_always_on_top_cb)

        self.mini_navi_fade_enabled_cb = QCheckBox(tr_ui("一定時間経過で薄く表示する（自動フェード。ウィンドウロック中のみ）"))
        self.mini_navi_fade_enabled_cb.setChecked(bool(mini_navi_config.get("fade_enabled", True)) if isinstance(mini_navi_config, dict) else True)
        Styles.apply_checkbox_style(self.mini_navi_fade_enabled_cb)
        mini_navi_window_layout.addWidget(self.mini_navi_fade_enabled_cb)

        general_layout.addWidget(mini_navi_window_group)
        
        # 街エリア設定
        town_group = QGroupBox(tr_ui("街エリア（ガイド更新スキップ）"))
        town_group.setStyleSheet(group.styleSheet())
        town_layout = QVBoxLayout(town_group)
        
        town_desc = QLabel(tr_ui("ここに登録したエリアに入った時、攻略ガイドは更新されません（前のエリアのガイドを維持）"))
        town_desc.setStyleSheet(f"color: #888888; font-size: 10px;")
        town_desc.setWordWrap(True)
        town_layout.addWidget(town_desc)
        
        default_towns = get_town_zones(self.poe_version)
        current_towns = self.town_zones_by_version.get(self.poe_version, default_towns)
        
        self.town_zones_edit = QTextEdit()
        self.town_zones_edit.setPlainText("\n".join(current_towns))
        self.town_zones_edit.setFixedHeight(100)
        self.town_zones_edit.setStyleSheet(f"""
            QTextEdit {{ 
                background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR}; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 4px; 
                padding: 5px; font-size: 11px;
            }}
        """)
        town_layout.addWidget(self.town_zones_edit)
        
        town_group.setVisible(False)  # 一般ユーザーには非表示（機能は残す）
        general_layout.addWidget(town_group)
        general_layout.addStretch()
        
        tabs.addTab(general_tab, tr_ui("基本設定"))
        
        # ── Tab 2: Zone Info ──
        zone_tab = QWidget()
        zone_layout = QVBoxLayout(zone_tab)

        self.zone_scroll = QScrollArea()
        self.zone_scroll.setWidgetResizable(True)
        self.zone_scroll.setStyleSheet("""
            QScrollArea { border: none; }
            QScrollBar:vertical { width: 8px; background: #222; }
            QScrollBar::handle:vertical { background: #555; border-radius: 4px; }
        """)

        self.zone_scroll_widget = QWidget()
        self.zone_scroll_inner = QVBoxLayout(self.zone_scroll_widget)
        self.zone_scroll_inner.setSpacing(5)
        self.zone_spinboxes = {}
        self._rebuild_zone_tab()

        self.zone_scroll.setWidget(self.zone_scroll_widget)
        zone_layout.addWidget(self.zone_scroll)
        
        tabs.addTab(zone_tab, tr_ui("エリア情報"))

        # === アプリ情報タブ ===
        about_tab = QWidget()
        about_layout = QVBoxLayout(about_tab)
        about_layout.setContentsMargins(20, 20, 20, 20)
        about_layout.setSpacing(15)

        # バージョン情報
        try:
            from main import __version__
        except ImportError:
            __version__ = "不明"
        
        version_label = QLabel(tr_ui(f"ぽえなび v{__version__}"))
        version_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 18px; font-weight: bold;")
        about_layout.addWidget(version_label)

        # GitHubリンク
        github_btn = QPushButton(tr_ui("GitHub（最新版のダウンロード）"))
        github_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(45, 45, 45, 200); color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176,255,123,0.4); border-radius: 6px;
                padding: 10px 20px; font-size: 13px;
            }}
            QPushButton:hover {{ background: rgba(65, 65, 65, 220); }}
        """)
        github_btn.setCursor(Qt.PointingHandCursor)
        github_btn.clicked.connect(lambda: webbrowser.open(releases_page_url()))
        about_layout.addWidget(github_btn)

        # 区切り線
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"color: rgba(176,255,123,0.3);")
        about_layout.addWidget(separator)

        # サポートセクション
        support_title = QLabel(tr_ui("☕ ぽえなびを応援する"))
        support_title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 16px; font-weight: bold;")
        about_layout.addWidget(support_title)

        support_desc = QLabel(
            tr_ui("ぽえなびを気に入っていただけたら、応援いただけると嬉しいです。\n"
            "いただいたサポートは、開発環境の維持・改善に充てさせていただきます。")
        )
        support_desc.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px;")
        support_desc.setWordWrap(True)
        about_layout.addWidget(support_desc)

        # OFUSEボタン
        ofuse_btn = QPushButton(tr_ui("OFUSE（おふせ）で応援する"))
        ofuse_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 147, 69, 200); color: white;
                border: none; border-radius: 6px;
                padding: 12px 20px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(255, 167, 99, 220); }}
        """)
        ofuse_btn.setCursor(Qt.PointingHandCursor)
        ofuse_btn.clicked.connect(lambda: webbrowser.open("https://ofuse.me/48eca107"))
        about_layout.addWidget(ofuse_btn)

        # Ko-fiボタン
        kofi_btn = QPushButton(tr_ui("Ko-fi で応援する"))
        kofi_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(41, 171, 224, 200); color: white;
                border: none; border-radius: 6px;
                padding: 12px 20px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(61, 191, 244, 220); }}
        """)
        kofi_btn.setCursor(Qt.PointingHandCursor)
        kofi_btn.clicked.connect(lambda: webbrowser.open("https://ko-fi.com/buri8857"))
        about_layout.addWidget(kofi_btn)

        # Patreonボタン
        patreon_btn = QPushButton(tr_ui("Patreon で応援する"))
        patreon_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255, 66, 77, 200); color: white;
                border: none; border-radius: 6px;
                padding: 12px 20px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(255, 86, 97, 220); }}
        """)
        patreon_btn.setCursor(Qt.PointingHandCursor)
        patreon_btn.clicked.connect(lambda: webbrowser.open("https://www.patreon.com/cw/Buri8857"))
        about_layout.addWidget(patreon_btn)

        support_note = QLabel(tr_ui("※ ブラウザが開きます"))
        support_note.setStyleSheet(f"color: rgba(200,200,200,150); font-size: 11px;")
        about_layout.addWidget(support_note)

        # アプリの免責事項
        poetore_separator = QFrame()
        poetore_separator.setFrameShape(QFrame.HLine)
        poetore_separator.setStyleSheet("color: rgba(176,255,123,0.3);")
        about_layout.addWidget(poetore_separator)

        self.app_disclaimer_label = QLabel(
            tr_ui("ぽえなびは無料の非公式ツールです。Grinding Gear Gamesとの提携・承認関係はありません。")
        )
        self.app_disclaimer_label.setWordWrap(True)
        self.app_disclaimer_label.setStyleSheet("color: rgba(200,200,200,180); font-size: 12px;")
        about_layout.addWidget(self.app_disclaimer_label)

        about_layout.addStretch()

        tabs.addTab(about_tab, tr_ui("アプリ情報"))

        layout.addWidget(tabs)
        
        # OK/Cancel
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton(tr_ui("保存"))
        self.ok_btn.setStyleSheet(Styles.BUTTON)
        self.ok_btn.clicked.connect(self.accept)
        
        self.cancel_btn = QPushButton(tr_ui("キャンセル"))
        self.cancel_btn.setStyleSheet(Styles.BUTTON)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
    
    def browse_log_file(self, poe_version=None):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Client.txt", "", "Log files (*.txt);;All files (*)"
        )
        if path:
            target_version = poe_version or self.poe_version
            self.log_path_edits[target_version].setText(path)
    
    def _create_small_action_button(self, text: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(30, 26)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(40,40,40,200); color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176,255,123,0.3); border-radius: 3px;
                font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(80,80,80,200); }}
        """)
        return btn

    def _poe1_route_suffixes_for_zone(self, zone_id: str) -> list[str]:
        if zone_id == "act3_area14":
            return ["~library_detour", "~library_detour@2"]
        if zone_id in ("act8_area8", "act8_area10", "act8_area11", "act8_area12",
                       "act8_area13", "act8_area14", "act8_area15", "act8_area16",
                       "act8_area17", "act8_area18", "act8_area19", "act8_area20"):
            return ["~underbelly", "~underbelly@2"]
        return []

    def _open_mini_navi_editor(self, name_edit: QLineEdit, zone_id: str = ""):
        """PoE1の各エリア向けに、みになび編集ダイアログを開く。"""
        zone_name = name_edit.text().strip()
        if not zone_name or not zone_id or self.poe_version != POE1:
            return

        sections = []
        guide_v1 = get_visit_guide_for_edit(self.guide_data, zone_id, visit=1)
        guide_v2 = get_visit_guide_for_edit(self.guide_data, zone_id, visit=2)
        sections.append({"kind": "visit", "title": "1回目", "visit": 1, "route": "", "guide": guide_v1})
        sections.append({"kind": "visit", "title": "2回目", "visit": 2, "route": "", "guide": guide_v2})

        for suffix in self._poe1_route_suffixes_for_zone(zone_id):
            route_name = suffix[1:].split("@")[0]
            visit = 2 if suffix.endswith("@2") else 1
            display_route = {"library_detour": "図書館ルート", "underbelly": "裏道ルート"}.get(route_name, route_name)
            route_guide = get_visit_guide_for_edit(self.guide_data, zone_id, visit=visit, route=route_name)
            sections.append({
                "kind": "route",
                "title": f"{display_route} {visit}回目",
                "visit": visit,
                "route": route_name,
                "guide": route_guide,
            })
            if zone_id == "act8_area14" and route_name == "underbelly":
                flag_key = "act8_lunaristemple2_enter+act8_solaristemple2_enter"
                route_flags = route_guide.setdefault("flags", {})
                if isinstance(route_flags, dict):
                    flag_guide = route_flags.setdefault(flag_key, {})
                    sections.append({
                        "kind": "route_flag",
                        "title": f"{display_route} {visit}回目 条件分岐: {flag_key}",
                        "visit": visit,
                        "route": route_name,
                        "flag_key": flag_key,
                        "guide": flag_guide,
                    })

        base_flags = guide_v1.get("flags", {}) if isinstance(guide_v1.get("flags", {}), dict) else {}
        if zone_id == "act1_area12":
            base_flags.setdefault("act1_shipgraveyardcave_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act2_area7":
            base_flags.setdefault("act2_westernforest_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act2_area8":
            base_flags.setdefault("act2_weaverschambers_enter+act2_wetlands_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act3_area11":
            base_flags.setdefault("act3_solaris_enter+act3_lunaris_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act4_area6":
            base_flags.setdefault("act4_grandarena_enter+act4_kaomstronghold_enter", {})
            base_flags.setdefault("act4_grandarena_enter", {})
            base_flags.setdefault("act4_kaomstronghold_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act5_area7":
            base_flags.setdefault("act5_reliquary_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act6_area10":
            base_flags.setdefault("act6_wetlands_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act7_area2":
            base_flags.setdefault("act7_crypt_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act7_area10":
            base_flags.setdefault("act7_dreadthicket_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act8_area13":
            base_flags.setdefault("act8_lunaristemple2_enter+act8_solaristemple2_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act8_area14":
            base_flags.setdefault("act8_bloodaqueduct_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act9_area2":
            base_flags.setdefault("act9_oasis_enter", {})
            guide_v1["flags"] = base_flags
        if zone_id == "act10_area3":
            base_flags.setdefault("act10_controlblocks_enter", {})
            base_flags.setdefault("act10_controlblocks_enter+act10_ossuary_enter", {})
            base_flags.setdefault("act10_controlblocks_enter+act10_ossuary_enter+act10_desecratedchambers_enter", {})
            guide_v1["flags"] = base_flags
        for flag_key, flag_guide in sorted(base_flags.items()):
            if isinstance(flag_guide, dict):
                sections.append({
                    "kind": "flag",
                    "title": _mini_navi_flag_section_title(zone_id, flag_key),
                    "flag_key": flag_key,
                    "guide": flag_guide,
                })

        dialog = MiniNaviEditorDialog(self, f"{zone_name} ({zone_id})", sections)
        if dialog.exec():
            dialog.apply_to_sections()
            set_visit_guide_for_edit(self.guide_data, zone_id, guide_v1, visit=1)
            set_visit_guide_for_edit(self.guide_data, zone_id, guide_v2, visit=2)
            for section in sections:
                if section.get("kind") == "route":
                    set_visit_guide_for_edit(
                        self.guide_data,
                        zone_id,
                        section["guide"],
                        visit=section["visit"],
                        route=section["route"],
                    )
                elif section.get("kind") == "route_flag":
                    route_guide = get_visit_guide_for_edit(self.guide_data, zone_id, visit=section["visit"], route=section["route"])
                    route_flags = route_guide.setdefault("flags", {})
                    if isinstance(route_flags, dict):
                        route_flags[section["flag_key"]] = section["guide"]
                    set_visit_guide_for_edit(
                        self.guide_data,
                        zone_id,
                        route_guide,
                        visit=section["visit"],
                        route=section["route"],
                    )
            save_guide_data(self.guide_data, self.poe_version, language=self.language)

    def _add_zone_row(self, act_name, act_layout, act_widgets):
        """エリア行を動的追加"""
        # 自動発番: act{N}_area_new_{連番}
        act_num = act_name.split()[1]
        new_count = sum(1 for _, zid in act_widgets if zid.startswith(f"act{act_num}_area_new_")) + 1 if act_widgets else 1
        zone_id = f"act{act_num}_area_new_{new_count}"
        
        row = QHBoxLayout()
        row.setSpacing(5)
        
        name_edit = QLineEdit("")
        name_edit.setFixedWidth(200)
        name_edit.setPlaceholderText(tr_ui("エリア名"))
        name_edit.setStyleSheet(f"""
            QLineEdit {{ 
                background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR}; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; 
                padding: 3px 5px; font-size: 11px;
            }}
        """)
        row.addWidget(name_edit)
        
        row.addStretch()
        
        # Insert before the "+" button (last widget)
        act_layout.insertLayout(act_layout.count() - 1, row)
        act_widgets.append((name_edit, zone_id))
    
    def _open_summary_editor(self, name_edit: QLineEdit, zone_id: str = ""):
        """PoE2の中級者向けサマリー編集ダイアログを開く"""
        zone_name = name_edit.text().strip()
        if not zone_name or not zone_id or not zone_id.startswith("poe2_"):
            return
        raw_entry = self.guide_data.get(zone_id, {})
        dialog = GuideSummaryEditorDialog(self, f"{zone_name} ({zone_id})", raw_entry)
        if dialog.exec():
            self.guide_data[zone_id] = dialog.apply_to_entry(raw_entry)
            from src.utils.guide_data import save_guide_data
            save_guide_data(self.guide_data, self.poe_version, language=self.language)

    def _open_guide_editor(self, name_edit: QLineEdit, zone_id: str = ""):
        """ガイドデータ編集ダイアログを開く"""
        zone_name = name_edit.text().strip()
        if not zone_name or not zone_id:
            return
        
        guide_key = zone_id
        display_name = f"{zone_name} ({zone_id})"
        is_poe2_zone = zone_id.startswith("poe2_")

        v2_key = f"{guide_key}@2"
        
        # ルート別ガイドの収集
        route_guides = {}
        route_suffixes = []
        # Act3: 帝国の庭園のみルート別
        if zone_id == "act3_area14":
            route_suffixes = ["~library_detour", "~library_detour@2"]
        # Act8: 裏道ルートで異なるガイドが必要な全エリア
        elif zone_id in ("act8_area8", "act8_area10", "act8_area11", "act8_area12",
                          "act8_area13", "act8_area14", "act8_area15", "act8_area16",
                          "act8_area17", "act8_area18", "act8_area19", "act8_area20"):
            route_suffixes = ["~underbelly", "~underbelly@2"]
        for suffix in route_suffixes:
            route_name = suffix[1:].split("@")[0]
            visit = 2 if suffix.endswith("@2") else 1
            route_guides[suffix] = get_visit_guide_for_edit(self.guide_data, guide_key, visit=visit, route=route_name)
        if zone_id == "act8_area14":
            flag_key = "act8_lunaristemple2_enter+act8_solaristemple2_enter"
            for suffix in ("~underbelly", "~underbelly@2"):
                if suffix in route_guides:
                    flags = route_guides[suffix].setdefault("flags", {})
                    if isinstance(flags, dict):
                        flags.setdefault(flag_key, {})
        
        raw_entry = self.guide_data.get(guide_key, {})
        flag_guides = {}
        if is_poe2_zone and isinstance(raw_entry, dict) and ("default" in raw_entry or "flags" in raw_entry):
            base_guide = raw_entry.get("default", {})
            flag_guides = raw_entry.get("flags", {}) if isinstance(raw_entry.get("flags", {}), dict) else {}
            flag_guide = next(iter(flag_guides.values()), {}) if flag_guides else {}
        elif is_poe2_zone:
            base_guide = raw_entry
            flag_guide = self.guide_data.get(v2_key, {})
        else:
            base_guide = get_visit_guide_for_edit(self.guide_data, guide_key, visit=1)
            flag_guides = base_guide.get("flags", {}) if isinstance(base_guide.get("flags", {}), dict) else {}
            if zone_id == "act1_area12":
                flag_guides.setdefault("act1_shipgraveyardcave_enter", {})
            if zone_id == "act2_area7":
                flag_guides.setdefault("act2_westernforest_enter", {})
            if zone_id == "act2_area8":
                flag_guides.setdefault("act2_weaverschambers_enter+act2_wetlands_enter", {})
            if zone_id == "act3_area11":
                flag_guides.setdefault("act3_solaris_enter+act3_lunaris_enter", {})
            if zone_id == "act4_area6":
                flag_guides.setdefault("act4_grandarena_enter+act4_kaomstronghold_enter", {})
                flag_guides.setdefault("act4_grandarena_enter", {})
                flag_guides.setdefault("act4_kaomstronghold_enter", {})
            if zone_id == "act5_area7":
                flag_guides.setdefault("act5_reliquary_enter", {})
            if zone_id == "act6_area10":
                flag_guides.setdefault("act6_wetlands_enter", {})
            if zone_id == "act7_area2":
                flag_guides.setdefault("act7_crypt_enter", {})
            if zone_id == "act7_area10":
                flag_guides.setdefault("act7_dreadthicket_enter", {})
            if zone_id == "act8_area13":
                flag_guides.setdefault("act8_lunaristemple2_enter+act8_solaristemple2_enter", {})
            if zone_id == "act8_area14":
                flag_guides.setdefault("act8_bloodaqueduct_enter", {})
            if zone_id == "act9_area2":
                flag_guides.setdefault("act9_oasis_enter", {})
            if zone_id == "act10_area3":
                flag_guides.setdefault("act10_controlblocks_enter", {})
                flag_guides.setdefault("act10_controlblocks_enter+act10_ossuary_enter", {})
                flag_guides.setdefault("act10_controlblocks_enter+act10_ossuary_enter+act10_desecratedchambers_enter", {})
            flag_guide = get_visit_guide_for_edit(self.guide_data, guide_key, visit=2)

        dialog = GuideEditorDialog(self, display_name, base_guide, flag_guide, zone_id=zone_id, route_guides=route_guides, flag_guides=flag_guides)
        if dialog.exec():
            guide = dialog.get_guide()
            guide_v2 = dialog.get_guide_v2()
            if is_poe2_zone:
                if any(v for v in guide.values()) or guide_v2:
                    entry = {"default": guide, "flags": {}}
                    for existing_flag_key, existing_flag_guide in flag_guides.items():
                        entry["flags"][existing_flag_key] = existing_flag_guide
                    if dialog.primary_flag_key:
                        if guide_v2:
                            entry["flags"][dialog.primary_flag_key] = guide_v2
                        else:
                            entry["flags"].pop(dialog.primary_flag_key, None)
                    self.guide_data[guide_key] = entry
                elif guide_key in self.guide_data:
                    del self.guide_data[guide_key]
                if v2_key in self.guide_data:
                    del self.guide_data[v2_key]
            else:
                new_flag_guides = dialog.get_flag_guides()
                if new_flag_guides:
                    guide["flags"] = new_flag_guides
                elif "flags" in guide:
                    guide.pop("flags", None)
                set_visit_guide_for_edit(self.guide_data, guide_key, guide, visit=1)
                set_visit_guide_for_edit(self.guide_data, guide_key, guide_v2, visit=2)
                # 旧フラットキーが残っている場合は削除して、新visits構造を正とする
                if v2_key in self.guide_data:
                    del self.guide_data[v2_key]
            
            # ルート別ガイド保存
            for suffix, rguide in dialog.get_route_guides().items():
                route_name = suffix[1:].split("@")[0]
                visit = 2 if suffix.endswith("@2") else 1
                set_visit_guide_for_edit(self.guide_data, guide_key, rguide, visit=visit, route=route_name)
                # 旧フラットキーが残っている場合は削除して、新visits構造を正とする
                rkey = f"{guide_key}{suffix}"
                if rkey in self.guide_data:
                    del self.guide_data[rkey]
            
            # ガイド編集のSaveで即座にファイル保存（Settings画面のSaveを待たない）
            from src.utils.guide_data import save_guide_data
            save_guide_data(self.guide_data, self.poe_version, language=self.language)
    
    def _default_zone_data_for_version(self, poe_version: str):
        return self.zone_data_by_version.get(poe_version, DEFAULT_ZONE_DATA_POE2 if poe_version != POE1 else {})

    def _save_current_zone_ui_to_memory(self):
        if not hasattr(self, "zone_spinboxes"):
            return
        zone_data = {}
        for act_name, widgets in self.zone_spinboxes.items():
            zones = []
            for _name_edit, zone_id in widgets:
                source_entry = None
                for z in self.zone_data.get(act_name, []):
                    if z.get("id") == zone_id:
                        source_entry = dict(z)
                        break
                if source_entry:
                    zones.append(source_entry)
            zone_data[act_name] = zones
        self.zone_data_by_version[self.poe_version] = zone_data

    def _rebuild_zone_tab(self):
        while self.zone_scroll_inner.count():
            item = self.zone_scroll_inner.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

        self.zone_spinboxes = {}
        for act_name in get_act_list(self.poe_version):
            if self.poe_version == POE2 and act_name == "クリア":
                continue
            act_group = QGroupBox(act_name)
            act_group.setStyleSheet(f"""
                QGroupBox {{ 
                    color: {Styles.TEXT_COLOR}; 
                    border: 1px solid rgba(176,255,123,0.3); 
                    border-radius: 4px; 
                    margin-top: 8px; 
                    font-weight: bold;
                }}
                QGroupBox::title {{ 
                    subcontrol-origin: margin; 
                    subcontrol-position: top left; 
                    padding: 0 5px; 
                }}
            """)
            act_layout = QVBoxLayout(act_group)
            act_layout.setSpacing(2)

            zones = self.zone_data.get(act_name, [])
            act_widgets = []

            for z in zones:
                if z.get("hidden", False):
                    continue
                zone_id = z.get("id", "")
                row = QHBoxLayout()
                row.setSpacing(5)

                level = z.get("level", 0)
                level_suffix = f" [{tr('zone.unknown_level')}]" if level == 0 else f" [Lv{level}]"
                name_edit = QLineEdit(f"{get_zone_display_name(z)}{level_suffix}")
                name_edit.setFixedWidth(260)
                name_edit.setReadOnly(True)
                name_edit.setToolTip(
                    tr_ui("エリアレベルは訪問順で変動")
                    if level == 0
                    else tr_ui(f"推奨エリアレベル: {level}")
                )
                name_edit.setStyleSheet(f"""
                    QLineEdit {{ 
                        background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR}; 
                        border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; 
                        padding: 3px 5px; font-size: 11px;
                    }}
                """)
                row.addWidget(name_edit)

                memo_button = QPushButton(tr_ui("📝 エリアメモ"))
                memo_button.setToolTip(
                    tr_ui(f"{get_zone_display_name(z)} のエリアメモを編集します")
                )
                memo_button.setFixedWidth(105)
                memo_button.setStyleSheet(Styles.BUTTON)
                memo_button.clicked.connect(
                    lambda checked=False, zid=zone_id, zname=get_zone_display_name(z):
                    self._open_area_note_editor(zid, zname)
                )
                row.addWidget(memo_button)

                if _act1_guide_dev_editor_enabled(self.poe_version, zone_id):
                    guide_button = self._create_small_action_button(
                        "📝", tr_ui("Act 1公式ガイドを編集")
                    )
                    guide_button.clicked.connect(
                        lambda checked=False, ne=name_edit, zid=zone_id:
                        self._open_guide_editor(ne, zid)
                    )
                    row.addWidget(guide_button)

                    mini_button = self._create_small_action_button(
                        "み", tr_ui("Act 1みになびを編集")
                    )
                    mini_button.clicked.connect(
                        lambda checked=False, ne=name_edit, zid=zone_id:
                        self._open_mini_navi_editor(ne, zid)
                    )
                    row.addWidget(mini_button)

                row.addStretch()
                act_layout.addLayout(row)
                act_widgets.append((name_edit, zone_id))

            add_btn = QPushButton(tr_ui("+ エリア追加"))
            add_btn.setFixedWidth(120)
            add_btn.setStyleSheet(f"""
                QPushButton {{ 
                    background: transparent; color: rgba(176,255,123,0.6); 
                    border: 1px dashed rgba(176,255,123,0.3); border-radius: 3px; 
                    padding: 3px; font-size: 10px;
                }}
                QPushButton:hover {{ color: {Styles.TEXT_COLOR}; }}
            """)
            add_btn.clicked.connect(lambda checked, an=act_name, al=act_layout, aw=act_widgets: self._add_zone_row(an, al, aw))
            add_btn.setEnabled(False)
            add_btn.setVisible(False)
            act_layout.addWidget(add_btn)

            self.zone_scroll_inner.addWidget(act_group)
            self.zone_spinboxes[act_name] = act_widgets

        self.zone_scroll_inner.addStretch()

    def _open_area_note_editor(self, zone_id: str, zone_name: str):
        """設定画面から任意エリアのエリアメモを編集して即時保存する。"""
        if not zone_id:
            return
        dialog = AreaNoteDialog(self, zone_name or zone_id, get_area_note(self.poe_version, zone_id))
        if dialog.exec():
            set_area_note(self.poe_version, zone_id, dialog.content())

    def _on_poe_version_changed(self, poe_version: str, checked: bool):
        if not checked or self.poe_version == poe_version:
            return
        self._save_current_zone_ui_to_memory()
        self.poe_version = poe_version
        self.zone_data = self.zone_data_by_version.get(poe_version, self._default_zone_data_for_version(poe_version))
        self.language = self.language_combo.currentData()
        self.guide_data = load_guide_data(self.poe_version, language=self.language)
        self.town_zones_edit.setPlainText("\n".join(self.town_zones_by_version.get(self.poe_version, get_town_zones(self.poe_version))))
        self._rebuild_zone_tab()

    def get_settings(self):
        self._save_current_zone_ui_to_memory()
        self.town_zones_by_version[self.poe_version] = [z.strip() for z in self.town_zones_edit.toPlainText().split("\n") if z.strip()]

        # エリア一覧のみ保存する。公式ガイドはユーザー編集対象外。
        save_zone_master_data(self.zone_data_by_version, self.town_zones_by_version)
        
        def normalize_log_path(text: str) -> str:
            # Explorerの「パスのコピー」は前後に引用符を付けるため、保存時に外側だけ除去する
            return text.strip().strip('"').strip("'").strip()
        
        mini_navi_overlay_config = dict(self.current_config.get("mini_guide_overlay", {}))
        mini_navi_overlay_config["display_mode"] = self.mini_navi_display_mode_combo.currentData()
        mini_navi_overlay_config["font_size"] = self.mini_navi_font_size_combo.currentData()
        mini_navi_overlay_config["window_opacity"] = self.mini_navi_window_opacity_slider.value()
        mini_navi_overlay_config["text_opacity"] = self.mini_navi_text_opacity_slider.value()
        mini_navi_overlay_config["always_on_top"] = self.mini_navi_always_on_top_cb.isChecked()
        mini_navi_overlay_config["fade_enabled"] = self.mini_navi_fade_enabled_cb.isChecked()

        return {
            "language": self.language_combo.currentData(),
            "language_selected": True,
            "hotkeys": {
                "start_stop": self.start_stop_btn.key_text,
                "reset": self.reset_btn.key_text,
                "lap": self.lap_btn.key_text,
                "undo_lap": self.undo_lap_btn.key_text,
                "click_through": self.click_through_btn.key_text,
                "logout": self.logout_btn.key_text,
                "hideout": self.hideout_btn.key_text,
                "monastery": self.monastery_btn.key_text,
                "search_string_test": self.search_string_test_btn.key_text,
                "poetore_capture": self.poetore_capture_btn.key_text,
            },
            "logout_enabled": self.logout_enabled_cb.isChecked(),
            "client_log_paths": {
                POE1: normalize_log_path(self.log_path_edits[POE1].text()),
                POE2: normalize_log_path(self.log_path_edits[POE2].text()),
            },
            "poe_version": self.poe_version,
            "poe_version_mode": self.poe_version_mode_combo.currentData(),
            "guide_font_size": self.guide_font_spin.value(),
            "guide_detail_level": self.guide_detail_level_combo.currentData(),
            "timer_size": self.timer_size_combo.currentData(),
            "confirm_reset": self.confirm_reset_cb.isChecked(),
            "window_opacity": self.opacity_slider.value(),
            "text_opacity": self.text_opacity_slider.value(),
            "window_locked": self.window_lock_check.isChecked(),
            "always_on_top": self.always_on_top_check.isChecked(),
            "display_monitor": self.monitor_combo.currentData(),
            "snap_to_right_edge": self.snap_right_edge_cb.isChecked(),
            "auto_open_map": self.auto_open_map_check.isChecked(),
            "auto_position_map": self.auto_position_map_check.isChecked(),
            "poe1_route_act3": self.poe1_route_act3_combo.currentData(),
            "poe1_route_act8": self.poe1_route_act8_combo.currentData(),
            "mini_guide_overlay": mini_navi_overlay_config,
        }
