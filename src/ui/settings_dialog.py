from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QGroupBox, QLineEdit, QFileDialog,
                               QTabWidget, QWidget, QScrollArea, QSpinBox,
                               QFormLayout, QTextEdit, QFrame, QRadioButton,
                               QButtonGroup, QGridLayout, QCheckBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence
from src.ui.styles import Styles
from src.utils.zone_data import DEFAULT_ZONE_DATA
from src.utils.guide_data import load_guide_data, save_guide_data
import webbrowser

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
        super().__init__(key_text)
        self.key_text = key_text
        self.setCheckable(True)
        self.setStyleSheet(Styles.BUTTON)
        self.toggled.connect(self.on_toggle)

    def on_toggle(self, checked):
        if checked:
            self.setText("Press any key...")
            self.grabKeyboard() # Qtの入力独占
        else:
            self.setText(self.key_text)
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
        html = self.toHtml()
        
        import re
        # body内のコンテンツだけ取り出す
        m = re.search(r"<body[^>]*>(.*)</body>", html, re.DOTALL)
        if m:
            body = m.group(1).strip()
        else:
            body = html
        
        # Qtが生成する余計な属性を整理
        # <p> → 改行に変換
        body = re.sub(r'<p[^>]*>', '', body)
        body = body.replace('</p>', '\n')
        # <br> → 改行
        body = re.sub(r'<br\s*/?>', '\n', body)
        # <span style="...font-weight:700...">text</span> → <b>text</b>
        def span_to_tags(m):
            style = m.group(1)
            text = m.group(2)
            is_bold = 'font-weight' in style and ('700' in style or 'bold' in style)
            color_m = re.search(r'color:(#[0-9a-fA-F]{6})', style)
            
            if is_bold and color_m:
                return f"<b style='color:{color_m.group(1)}'>{text}</b>"
            elif is_bold:
                return f"<b>{text}</b>"
            elif color_m:
                return f"<span style='color:{color_m.group(1)}'>{text}</span>"
            return text
        
        body = re.sub(r'<span style="([^"]*)">(.*?)</span>', span_to_tags, body)
        
        # 連続改行を整理
        body = re.sub(r'\n{3,}', '\n\n', body)
        # QtのtoHtml()が生成するHTMLエンティティを戻す（guide_data.jsonにはプレーンテキスト+許可タグで保存）
        body = body.replace("&quot;", '"')
        body = body.replace("&#x27;", "'")
        body = body.replace("&amp;", "&")
        return body.strip()


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
    
    def __init__(self, parent, zone_name: str, guide: dict, guide_v2: dict = None, zone_id: str = "", route_guides: dict = None):
        super().__init__(parent)
        self.setWindowTitle(f"ガイド編集 — {zone_name}")
        self.resize(550, 620)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self.guide_v2 = guide_v2 or {}
        self.zone_id = zone_id
        self.route_guides = route_guides or {}  # {"~library_detour": {...}, "~library_detour@2": {...}}
        
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
        
        # ── 基本方向 ──
        dir_group_box = QGroupBox("🧭 基本方向（シンプルなマップ向け）")
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
        
        # 「該当なし」の説明
        dir_desc = QLabel("中央「—」= 該当なし（複雑なマップ → ガイド参照を表示）")
        dir_desc.setStyleSheet("color: #888888; font-size: 10px;")
        dir_desc.setWordWrap(True)
        dir_layout.addWidget(dir_desc, 3, 0, 1, 3)
        
        layout.addWidget(dir_group_box)
        
        # 目標
        layout.addWidget(QLabel("📋 目標 / やること"))
        layout.itemAt(layout.count()-1).widget().setStyleSheet(label_style)
        self.objective_edit = QTextEdit()
        self.objective_edit.setPlainText(guide.get("objective", ""))
        self.objective_edit.setFixedHeight(50)
        self.objective_edit.setStyleSheet(text_style)
        layout.addWidget(self.objective_edit)
        
        # レイアウト情報
        layout.addWidget(QLabel("🗺️ レイアウト情報"))
        layout.itemAt(layout.count()-1).widget().setStyleSheet(label_style)
        
        # ── ツールバー ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        
        # カラーボタン
        for color_code, color_name in self.COLORS:
            cbtn = QPushButton()
            cbtn.setFixedSize(22, 22)
            cbtn.setToolTip(f"{color_name} ({color_code})")
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
        reset_color_btn.setToolTip("色をリセット")
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
        layout.addWidget(QLabel("💡 Tips / 注意点"))
        layout.itemAt(layout.count()-1).widget().setStyleSheet(label_style)
        self.tips_edit = QTextEdit()
        self.tips_edit.setPlainText(guide.get("tips", ""))
        self.tips_edit.setFixedHeight(80)
        self.tips_edit.setStyleSheet(text_style)
        layout.addWidget(self.tips_edit)
        
        # ── 2回目の訪問ガイド ──
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: rgba(176,255,123,0.3);")
        layout.addWidget(separator)
        
        # zone_idからAct範囲を判定して説明文を動的生成
        act_num = int(self.zone_id.split("_")[0].replace("act", "")) if self.zone_id and self.zone_id.startswith("act") else 1
        act_range = "Act6-10" if act_num >= 6 else "Act1-5"
        v2_desc = f"{act_range}の間で、このエリアに２回以上訪れた場合はこちらを表示"
        v2_label_closed = f"▶ 2回目のガイド（{v2_desc}）"
        v2_label_open = f"▼ 2回目のガイド（{v2_desc}）"
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
        
        # 基本方向（2回目）
        v2_dir_group_box = QGroupBox("🧭 基本方向（2回目）")
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
            rb = QRadioButton(label)
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
        
        v2_dir_desc = QLabel("「同上」= 1回目と同じ方向を使用")
        v2_dir_desc.setStyleSheet("color: #888888; font-size: 10px;")
        v2_dir_layout.addWidget(v2_dir_desc, 3, 0, 1, 4)
        
        v2_layout.addWidget(v2_dir_group_box)
        
        v2_layout.addWidget(QLabel("📋 目標 / やること"))
        v2_layout.itemAt(v2_layout.count()-1).widget().setStyleSheet(label_style)
        self.v2_objective_edit = QTextEdit()
        self.v2_objective_edit.setPlainText(self.guide_v2.get("objective", ""))
        self.v2_objective_edit.setFixedHeight(50)
        self.v2_objective_edit.setStyleSheet(text_style)
        v2_layout.addWidget(self.v2_objective_edit)
        
        v2_layout.addWidget(QLabel("🗺️ レイアウト情報"))
        v2_layout.itemAt(v2_layout.count()-1).widget().setStyleSheet(label_style)
        
        # ── カラーパレット（2回目用） ──
        v2_toolbar = QHBoxLayout()
        v2_toolbar.setSpacing(4)
        for color_code, color_name in self.COLORS:
            cbtn = QPushButton()
            cbtn.setFixedSize(22, 22)
            cbtn.setToolTip(f"{color_name} ({color_code})")
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
        v2_reset_btn.setToolTip("色をリセット")
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
        
        v2_layout.addWidget(QLabel("💡 Tips / 注意点"))
        v2_layout.itemAt(v2_layout.count()-1).widget().setStyleSheet(label_style)
        self.v2_tips_edit = QTextEdit()
        self.v2_tips_edit.setPlainText(self.guide_v2.get("tips", ""))
        self.v2_tips_edit.setFixedHeight(60)
        self.v2_tips_edit.setStyleSheet(text_style)
        v2_layout.addWidget(self.v2_tips_edit)
        
        layout.addWidget(self.v2_frame)
        self.v2_frame.setVisible(bool(self.guide_v2))
        
        # ── ルート別ガイド ──
        self.route_editors = {}  # {suffix: {"objective": QTextEdit, "layout": RichTextEdit, "tips": QTextEdit, "direction": QButtonGroup}}
        if self.route_guides:
            route_separator = QFrame()
            route_separator.setFrameShape(QFrame.HLine)
            route_separator.setStyleSheet("color: rgba(176,255,123,0.5);")
            layout.addWidget(route_separator)
            
            route_header = QLabel("📍 ルート別ガイド")
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
                
                rg_layout.addWidget(QLabel("📋 目標"))
                rg_layout.itemAt(rg_layout.count()-1).widget().setStyleSheet(label_style)
                r_obj = QTextEdit()
                r_obj.setPlainText(rguide.get("objective", ""))
                r_obj.setFixedHeight(50)
                r_obj.setStyleSheet(text_style)
                rg_layout.addWidget(r_obj)
                
                rg_layout.addWidget(QLabel("🗺️ レイアウト"))
                rg_layout.itemAt(rg_layout.count()-1).widget().setStyleSheet(label_style)
                r_lay = RichTextEdit()
                r_lay.set_from_html(rguide.get("layout", ""))
                r_lay.setFixedHeight(120)
                r_lay.setStyleSheet(text_style)
                rg_layout.addWidget(r_lay)
                
                rg_layout.addWidget(QLabel("💡 Tips"))
                rg_layout.itemAt(rg_layout.count()-1).widget().setStyleSheet(label_style)
                r_tips = QTextEdit()
                r_tips.setPlainText(rguide.get("tips", ""))
                r_tips.setFixedHeight(50)
                r_tips.setStyleSheet(text_style)
                rg_layout.addWidget(r_tips)
                
                # 基本方向（9方向ラジオボタン）
                r_dir_label = QLabel("🧭 基本方向")
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
                
                layout.addWidget(rg_box)
                self.route_editors[suffix] = {"objective": r_obj, "layout": r_lay, "tips": r_tips, "direction": r_dir_group}
        
        layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)
        
        # OK/Cancel
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("保存")
        ok_btn.setStyleSheet(Styles.BUTTON)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("キャンセル")
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
    
    def _toggle_v2(self):
        """2回目セクションの表示切替"""
        visible = not self.v2_frame.isVisible()
        self.v2_frame.setVisible(visible)
        self.v2_toggle_btn.setText(self._v2_label_open if visible else self._v2_label_closed)
    
    def get_guide(self) -> dict:
        # 選択された方向を取得
        direction = "none"
        checked = self.direction_group.checkedButton()
        if checked:
            direction = checked.property("dir_value")
        
        return {
            "objective": self.objective_edit.toPlainText().strip(),
            "layout": self.layout_edit.to_storage_html(),
            "tips": self.tips_edit.toPlainText().strip(),
            "direction": direction,
        }
    
    def get_guide_v2(self) -> dict:
        """2回目の訪問ガイドを取得（空なら空dict）"""
        # 方向
        v2_direction = "inherit"
        checked = self.v2_direction_group.checkedButton()
        if checked:
            v2_direction = checked.property("dir_value")
        
        result = {
            "objective": self.v2_objective_edit.toPlainText().strip(),
            "layout": self.v2_layout_edit.to_storage_html(),
            "tips": self.v2_tips_edit.toPlainText().strip(),
        }
        # directionがinherit以外なら保存
        if v2_direction != "inherit":
            result["direction"] = v2_direction
        
        if any(v for v in [result["objective"], result["layout"], result["tips"]]):
            return result
        if "direction" in result:
            return result
        return {}

    def get_route_guides(self) -> dict:
        """ルート別ガイドデータを取得 {suffix: {objective, layout, tips, direction}}"""
        result = {}
        for suffix, editors in self.route_editors.items():
            r_direction = "none"
            checked = editors["direction"].checkedButton()
            if checked:
                r_direction = checked.property("dir_value")
            g = {
                "objective": editors["objective"].toPlainText().strip(),
                "layout": editors["layout"].to_storage_html(),
                "tips": editors["tips"].toPlainText().strip(),
                "direction": r_direction,
            }
            if any(v for v in g.values()):
                result[suffix] = g
            else:
                result[suffix] = g  # 空でも保持（キーは残す）
        return result


class SettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.resize(500, 600)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        
        self.current_config = current_config or {}
        self.hotkeys = self.current_config.get("hotkeys", {
            "start_stop": "F1", 
            "reset": "F2",
            "lap": "F3",
            "undo_lap": "F4"
        })
        self.zone_data = self.current_config.get("zone_data", DEFAULT_ZONE_DATA)
        self.guide_data = load_guide_data()
        
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
        log_group = QGroupBox("PoE ログファイル")
        log_group.setStyleSheet(group_style)
        log_layout = QHBoxLayout(log_group)
        
        self.log_path_edit = QLineEdit(self.current_config.get("client_log_path", ""))
        self.log_path_edit.setPlaceholderText("C:\\Program Files (x86)\\...\\logs\\Client.txt")
        self.log_path_edit.setStyleSheet(f"""
            QLineEdit {{ 
                background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR}; 
                border: 1px solid {Styles.TEXT_COLOR}; border-radius: 4px; padding: 5px;
            }}
        """)
        log_layout.addWidget(self.log_path_edit)
        
        browse_btn = QPushButton("参照")
        browse_btn.setStyleSheet(Styles.BUTTON)
        browse_btn.clicked.connect(self.browse_log_file)
        log_layout.addWidget(browse_btn)
        
        general_layout.addWidget(log_group)
        
        # ━━━━━ 2. ホットキー ━━━━━
        group = QGroupBox("ホットキー")
        group.setStyleSheet(group_style)
        group_layout = QVBoxLayout(group)
        
        h_layout1 = QHBoxLayout()
        h_layout1.addWidget(QLabel("開始/停止:"))
        self.start_stop_btn = HotkeyButton(self.hotkeys.get("start_stop", "F1"))
        h_layout1.addWidget(self.start_stop_btn)
        group_layout.addLayout(h_layout1)
        
        h_layout2 = QHBoxLayout()
        h_layout2.addWidget(QLabel("リセット:"))
        self.reset_btn = HotkeyButton(self.hotkeys.get("reset", "F2"))
        h_layout2.addWidget(self.reset_btn)
        group_layout.addLayout(h_layout2)
        
        h_layout3 = QHBoxLayout()
        h_layout3.addWidget(QLabel("ラップ（次のAct）:"))
        self.lap_btn = HotkeyButton(self.hotkeys.get("lap", "F3"))
        h_layout3.addWidget(self.lap_btn)
        group_layout.addLayout(h_layout3)
        
        h_layout4 = QHBoxLayout()
        h_layout4.addWidget(QLabel("ラップ取消:"))
        self.undo_lap_btn = HotkeyButton(self.hotkeys.get("undo_lap", "F4"))
        h_layout4.addWidget(self.undo_lap_btn)
        group_layout.addLayout(h_layout4)
        
        h_layout5 = QHBoxLayout()
        h_layout5.addWidget(QLabel("クリックスルー:"))
        self.click_through_btn = HotkeyButton(self.hotkeys.get("click_through", "F6"))
        h_layout5.addWidget(self.click_through_btn)
        group_layout.addLayout(h_layout5)
        
        h_layout6 = QHBoxLayout()
        h_layout6.addWidget(QLabel("ログアウト:"))
        self.logout_btn = HotkeyButton(self.hotkeys.get("logout", "F5"))
        h_layout6.addWidget(self.logout_btn)
        group_layout.addLayout(h_layout6)
        
        self.logout_enabled_cb = QCheckBox("ログアウト機能を有効にする（TCP切断）")
        self.logout_enabled_cb.setChecked(self.current_config.get("logout_enabled", True))
        self.logout_enabled_cb.setStyleSheet(checkbox_style)
        group_layout.addWidget(self.logout_enabled_cb)
        
        general_layout.addWidget(group)
        
        # ━━━━━ 3. タイマー表示 ━━━━━
        timer_group = QGroupBox("タイマー表示")
        timer_group.setStyleSheet(group_style)
        timer_layout = QVBoxLayout(timer_group)
        
        # タイマーサイズ
        timer_size_row = QHBoxLayout()
        timer_size_label = QLabel("タイマーサイズ:")
        timer_size_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        timer_size_row.addWidget(timer_size_label)
        
        from PySide6.QtWidgets import QComboBox
        self.timer_size_combo = QComboBox()
        self.timer_size_combo.addItem("大", "large")
        self.timer_size_combo.addItem("中", "medium")
        self.timer_size_combo.addItem("小", "small")
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
        self.confirm_reset_cb = QCheckBox("タイマーリセット時に確認ダイアログを表示する")
        self.confirm_reset_cb.setChecked(self.current_config.get("confirm_reset", True))
        self.confirm_reset_cb.setStyleSheet(checkbox_style)
        timer_layout.addWidget(self.confirm_reset_cb)
        
        general_layout.addWidget(timer_group)
        
        # ━━━━━ 4. ガイド表示 ━━━━━
        font_group = QGroupBox("ガイド表示")
        font_group.setStyleSheet(group_style)
        font_group_layout = QVBoxLayout(font_group)
        
        font_row = QHBoxLayout()
        font_label = QLabel("フォントサイズ:")
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
        
        # ルート選択
        from PySide6.QtWidgets import QComboBox as _QComboBox
        route_act3_row = QHBoxLayout()
        route_act3_label = QLabel("Act3 ルート:")
        route_act3_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        route_act3_row.addWidget(route_act3_label)
        self.route_act3_combo = _QComboBox()
        self.route_act3_combo.addItem("通常ルート（図書館スキップ）", "standard")
        self.route_act3_combo.addItem("図書館寄り道ルート", "library_detour")
        self.route_act3_combo.setStyleSheet(combo_style)
        cur3 = self.current_config.get("route_act3", "standard")
        idx3 = self.route_act3_combo.findData(cur3)
        if idx3 >= 0:
            self.route_act3_combo.setCurrentIndex(idx3)
        route_act3_row.addWidget(self.route_act3_combo)
        route_act3_row.addStretch()
        font_group_layout.addLayout(route_act3_row)
        
        route_act8_row = QHBoxLayout()
        route_act8_label = QLabel("Act8 ルート:")
        route_act8_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        route_act8_row.addWidget(route_act8_label)
        self.route_act8_combo = _QComboBox()
        self.route_act8_combo.addItem("通常ルート", "standard")
        self.route_act8_combo.addItem("隠れた裏道（The Hidden Underbelly）ルート", "underbelly")
        self.route_act8_combo.setStyleSheet(combo_style)
        cur8 = self.current_config.get("route_act8", "standard")
        idx8 = self.route_act8_combo.findData(cur8)
        if idx8 >= 0:
            self.route_act8_combo.setCurrentIndex(idx8)
        route_act8_row.addWidget(self.route_act8_combo)
        route_act8_row.addStretch()
        font_group_layout.addLayout(route_act8_row)
        
        general_layout.addWidget(font_group)
        
        # ━━━━━ 5. マップ表示 ━━━━━
        map_group = QGroupBox("マップ表示")
        map_group.setStyleSheet(group_style)
        map_layout = QVBoxLayout(map_group)

        self.auto_open_map_check = QCheckBox("エリア移動時にマップレイアウトの拡大画像を自動で開く")
        self.auto_open_map_check.setStyleSheet(checkbox_style)
        self.auto_open_map_check.setChecked(self.current_config.get("auto_open_map", False))
        map_layout.addWidget(self.auto_open_map_check)

        self.auto_position_map_check = QCheckBox("マップレイアウトの拡大画像を開く際、ぽえなびの隣に自動配置する")
        self.auto_position_map_check.setStyleSheet(checkbox_style)
        self.auto_position_map_check.setChecked(self.current_config.get("auto_position_map", True))
        map_layout.addWidget(self.auto_position_map_check)

        general_layout.addWidget(map_group)
        
        # ━━━━━ 6. ウィンドウ設定 ━━━━━
        window_group = QGroupBox("ウィンドウ設定")
        window_group.setStyleSheet(group_style)
        window_layout = QVBoxLayout(window_group)
        window_layout.setSpacing(10)
        
        # 透過率
        opacity_row = QHBoxLayout()
        opacity_label = QLabel("透過率:")
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
        text_opacity_label = QLabel("文字透過率:")
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
        self.window_lock_check = QCheckBox("ウィンドウの移動・リサイズを禁止する")
        self.window_lock_check.setStyleSheet(checkbox_style)
        self.window_lock_check.setChecked(self.current_config.get("window_locked", False))
        window_layout.addWidget(self.window_lock_check)
        
        # モニター選択
        monitor_row = QHBoxLayout()
        monitor_label = QLabel("起動時の配置先:")
        monitor_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        monitor_row.addWidget(monitor_label)
        self.monitor_combo = QComboBox()
        self.monitor_combo.setStyleSheet(combo_style)
        from PySide6.QtWidgets import QApplication
        screens = QApplication.screens()
        current_monitor = self.current_config.get("display_monitor", 0)
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            name = f"モニター {i + 1}（{geo.width()}x{geo.height()}）"
            if screen == QApplication.primaryScreen():
                name += " [メイン]"
            self.monitor_combo.addItem(name, i)
        if 0 <= current_monitor < len(screens):
            self.monitor_combo.setCurrentIndex(current_monitor)
        monitor_row.addWidget(self.monitor_combo)
        monitor_row.addStretch()
        window_layout.addLayout(monitor_row)
        
        general_layout.addWidget(window_group)
        
        # 街エリア設定
        town_group = QGroupBox("街エリア（ガイド更新スキップ）")
        town_group.setStyleSheet(group.styleSheet())
        town_layout = QVBoxLayout(town_group)
        
        town_desc = QLabel("ここに登録したエリアに入った時、攻略ガイドは更新されません（前のエリアのガイドを維持）")
        town_desc.setStyleSheet(f"color: #888888; font-size: 10px;")
        town_desc.setWordWrap(True)
        town_layout.addWidget(town_desc)
        
        default_towns = [
            "Lioneye's Watch", "ライオンアイの見張り場",
            "The Forest Encampment", "森のキャンプ地",
            "The Sarn Encampment", "サーンのキャンプ地",
            "Highgate", "ハイゲート",
            "Overseer's Tower", "監督官の塔",
            "The Bridge Encampment", "橋のたもとのキャンプ地",
            "The Harbour Bridge", "港の橋",
            "Oriath", "オリアス",
            "Karui Shores", "カルイの浜辺",
        ]
        current_towns = self.current_config.get("town_zones", default_towns)
        
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
        
        tabs.addTab(general_tab, "基本設定")
        
        # ── Tab 2: Zone Info ──
        zone_tab = QWidget()
        zone_layout = QVBoxLayout(zone_tab)
        
        # スクロールエリア
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; }
            QScrollBar:vertical { width: 8px; background: #222; }
            QScrollBar::handle:vertical { background: #555; border-radius: 4px; }
        """)
        
        scroll_widget = QWidget()
        scroll_inner = QVBoxLayout(scroll_widget)
        scroll_inner.setSpacing(5)
        
        self.zone_spinboxes = {}  # {act: [(zone_name_edit, level_spinbox, zone_id), ...]}
        
        for act_name in ["Act 1", "Act 2", "Act 3", "Act 4", "Act 5", 
                         "Act 6", "Act 7", "Act 8", "Act 9", "Act 10"]:
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
            
            # カラムヘッダー行
            header_row = QHBoxLayout()
            header_row.setSpacing(5)
            spacer_label = QLabel("")
            spacer_label.setFixedWidth(205)
            header_row.addWidget(spacer_label)
            guide_header = QLabel("ガイド設定")
            guide_header.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 10px; font-weight: bold;")
            header_row.addWidget(guide_header)
            header_row.addStretch()
            act_layout.addLayout(header_row)
            
            zones = self.zone_data.get(act_name, [])
            act_widgets = []
            
            for z in zones:
                if z.get("hidden", False):
                    continue  # 欠番エリアはスキップ
                zone_id = z.get("id", "")
                row = QHBoxLayout()
                row.setSpacing(5)
                
                name_edit = QLineEdit(z.get("zone", ""))
                name_edit.setFixedWidth(200)
                name_edit.setReadOnly(True)  # 一般ユーザーには編集不可
                name_edit.setStyleSheet(f"""
                    QLineEdit {{ 
                        background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR}; 
                        border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; 
                        padding: 3px 5px; font-size: 11px;
                    }}
                """)
                row.addWidget(name_edit)
                
                # ガイド編集ボタン
                guide_btn = QPushButton("📝")
                guide_btn.setFixedSize(30, 26)
                guide_btn.setToolTip("ガイドデータを編集")
                guide_btn.setStyleSheet(f"""
                    QPushButton {{ 
                        background: rgba(40,40,40,200); color: {Styles.TEXT_COLOR}; 
                        border: 1px solid rgba(176,255,123,0.3); border-radius: 3px;
                        font-size: 12px;
                    }}
                    QPushButton:hover {{ background: rgba(80,80,80,200); }}
                """)
                guide_btn.clicked.connect(lambda checked, ne=name_edit, zid=zone_id: self._open_guide_editor(ne, zid))
                row.addWidget(guide_btn)
                
                row.addStretch()
                
                act_layout.addLayout(row)
                act_widgets.append((name_edit, zone_id))
            
            # Add zone button
            add_btn = QPushButton("+ エリア追加")
            add_btn.setFixedWidth(120)
            add_btn.setStyleSheet(f"""
                QPushButton {{ 
                    background: transparent; color: rgba(176,255,123,0.6); 
                    border: 1px dashed rgba(176,255,123,0.3); border-radius: 3px; 
                    padding: 3px; font-size: 10px;
                }}
                QPushButton:hover {{ color: {Styles.TEXT_COLOR}; }}
            """)
            add_btn.clicked.connect(lambda checked, an=act_name, al=act_layout, aw=act_widgets: 
                                    self._add_zone_row(an, al, aw))
            add_btn.setEnabled(False)  # 一般ユーザーには無効
            add_btn.setVisible(False)
            act_layout.addWidget(add_btn)
            
            scroll_inner.addWidget(act_group)
            self.zone_spinboxes[act_name] = act_widgets
        
        scroll_inner.addStretch()
        scroll.setWidget(scroll_widget)
        zone_layout.addWidget(scroll)
        
        # Reset to defaults button
        reset_zones_btn = QPushButton("デフォルトに戻す")
        reset_zones_btn.setStyleSheet(Styles.BUTTON)
        reset_zones_btn.clicked.connect(self._reset_zone_defaults)
        reset_zones_btn.setEnabled(False)  # 一般ユーザーには無効（機能は残す）
        zone_layout.addWidget(reset_zones_btn)
        
        tabs.addTab(zone_tab, "エリア情報")

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
        
        version_label = QLabel(f"ぽえなび v{__version__}")
        version_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 18px; font-weight: bold;")
        about_layout.addWidget(version_label)

        # GitHubリンク
        github_btn = QPushButton("GitHub（最新版のダウンロード）")
        github_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(45, 45, 45, 200); color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176,255,123,0.4); border-radius: 6px;
                padding: 10px 20px; font-size: 13px;
            }}
            QPushButton:hover {{ background: rgba(65, 65, 65, 220); }}
        """)
        github_btn.setCursor(Qt.PointingHandCursor)
        github_btn.clicked.connect(lambda: webbrowser.open("https://github.com/buri34/poenavi/releases"))
        about_layout.addWidget(github_btn)

        # 区切り線
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"color: rgba(176,255,123,0.3);")
        about_layout.addWidget(separator)

        # サポートセクション
        support_title = QLabel("☕ ぽえなびを応援する")
        support_title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 16px; font-weight: bold;")
        about_layout.addWidget(support_title)

        support_desc = QLabel(
            "ぽえなびを気に入っていただけたら、応援いただけると嬉しいです。\n"
            "いただいたサポートは、開発環境の維持・改善に充てさせていただきます。"
        )
        support_desc.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px;")
        support_desc.setWordWrap(True)
        about_layout.addWidget(support_desc)

        # OFUSEボタン
        ofuse_btn = QPushButton("OFUSE（おふせ）で応援する")
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
        kofi_btn = QPushButton("Ko-fi で応援する")
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

        support_note = QLabel("※ ブラウザが開きます")
        support_note.setStyleSheet(f"color: rgba(200,200,200,150); font-size: 11px;")
        about_layout.addWidget(support_note)

        about_layout.addStretch()

        tabs.addTab(about_tab, "アプリ情報")

        layout.addWidget(tabs)
        
        # OK/Cancel
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("保存")
        self.ok_btn.setStyleSheet(Styles.BUTTON)
        self.ok_btn.clicked.connect(self.accept)
        
        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.setStyleSheet(Styles.BUTTON)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
    
    def browse_log_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Client.txt", "", "Log files (*.txt);;All files (*)"
        )
        if path:
            self.log_path_edit.setText(path)
    
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
        name_edit.setPlaceholderText("エリア名")
        name_edit.setStyleSheet(f"""
            QLineEdit {{ 
                background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR}; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; 
                padding: 3px 5px; font-size: 11px;
            }}
        """)
        row.addWidget(name_edit)
        
        guide_btn = QPushButton("📝")
        guide_btn.setFixedSize(30, 26)
        guide_btn.setToolTip("ガイドデータを編集")
        guide_btn.setStyleSheet(f"""
            QPushButton {{ 
                background: rgba(40,40,40,200); color: {Styles.TEXT_COLOR}; 
                border: 1px solid rgba(176,255,123,0.3); border-radius: 3px; font-size: 12px;
            }}
            QPushButton:hover {{ background: rgba(80,80,80,200); }}
        """)
        guide_btn.clicked.connect(lambda checked, ne=name_edit, zid=zone_id: self._open_guide_editor(ne, zid))
        row.addWidget(guide_btn)
        
        row.addStretch()
        
        # Insert before the "+" button (last widget)
        act_layout.insertLayout(act_layout.count() - 1, row)
        act_widgets.append((name_edit, zone_id))
    
    def _open_guide_editor(self, name_edit: QLineEdit, zone_id: str = ""):
        """ガイドデータ編集ダイアログを開く"""
        zone_name = name_edit.text().strip()
        if not zone_name or not zone_id:
            return
        
        guide_key = zone_id
        display_name = f"{zone_name} ({zone_id})"
        
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
            rkey = f"{guide_key}{suffix}"
            route_guides[suffix] = self.guide_data.get(rkey, {})
        
        dialog = GuideEditorDialog(self, display_name, self.guide_data.get(guide_key, {}), self.guide_data.get(v2_key, {}), zone_id=zone_id, route_guides=route_guides)
        if dialog.exec():
            guide = dialog.get_guide()
            if any(v for v in guide.values()):
                self.guide_data[guide_key] = guide
            elif guide_key in self.guide_data:
                del self.guide_data[guide_key]
            
            guide_v2 = dialog.get_guide_v2()
            if guide_v2:
                self.guide_data[v2_key] = guide_v2
            elif v2_key in self.guide_data:
                del self.guide_data[v2_key]
            
            # ルート別ガイド保存
            for suffix, rguide in dialog.get_route_guides().items():
                rkey = f"{guide_key}{suffix}"
                if any(v for v in rguide.values()):
                    self.guide_data[rkey] = rguide
                elif rkey in self.guide_data:
                    # 空でもキーは残す（guide_data.jsonに空エントリとして）
                    self.guide_data[rkey] = {"objective": "", "layout": "", "tips": "", "direction": ""}
            
            # ガイド編集のSaveで即座にファイル保存（Settings画面のSaveを待たない）
            from src.utils.guide_data import save_guide_data
            save_guide_data(self.guide_data)
    
    def _reset_zone_defaults(self):
        """ゾーンデータをデフォルトにリセット（UI再構築は面倒なのでダイアログを閉じて再度開く案内）"""
        self.zone_data = DEFAULT_ZONE_DATA
        # Simplification: update spinboxes with default values
        for act_name, widgets in self.zone_spinboxes.items():
            defaults = DEFAULT_ZONE_DATA.get(act_name, [])
            for i, (name_edit, _zid) in enumerate(widgets):
                if i < len(defaults):
                    name_edit.setText(defaults[i]["zone"])
    
    def get_settings(self):
        # Build zone_data from UI
        zone_data = {}
        for act_name, widgets in self.zone_spinboxes.items():
            zones = []
            for name_edit, zone_id in widgets:
                zone_name = name_edit.text().strip()
                if zone_name:  # Skip empty rows
                    # Preserve existing fields from config
                    entry = {"id": zone_id, "zone": zone_name, "level": 1}
                    for z in self.zone_data.get(act_name, []):
                        if z.get("id") == zone_id:
                            entry["level"] = z.get("level", 1)
                            # Preserve zone_en and any other extra fields
                            if z.get("zone_en"):
                                entry["zone_en"] = z["zone_en"]
                            break
                    zones.append(entry)
            zone_data[act_name] = zones
        
        # ガイドデータも保存
        save_guide_data(self.guide_data)
        
        return {
            "hotkeys": {
                "start_stop": self.start_stop_btn.key_text,
                "reset": self.reset_btn.key_text,
                "lap": self.lap_btn.key_text,
                "undo_lap": self.undo_lap_btn.key_text,
                "click_through": self.click_through_btn.key_text,
                "logout": self.logout_btn.key_text,
            },
            "logout_enabled": self.logout_enabled_cb.isChecked(),
            "client_log_path": self.log_path_edit.text().strip(),
            "zone_data": zone_data,
            "guide_font_size": self.guide_font_spin.value(),
            "timer_size": self.timer_size_combo.currentData(),
            "confirm_reset": self.confirm_reset_cb.isChecked(),
            "window_opacity": self.opacity_slider.value(),
            "text_opacity": self.text_opacity_slider.value(),
            "window_locked": self.window_lock_check.isChecked(),
            "display_monitor": self.monitor_combo.currentData(),
            "auto_open_map": self.auto_open_map_check.isChecked(),
            "auto_position_map": self.auto_position_map_check.isChecked(),
            "town_zones": [z.strip() for z in self.town_zones_edit.toPlainText().split("\n") if z.strip()],
            "route_act3": self.route_act3_combo.currentData(),
            "route_act8": self.route_act8_combo.currentData(),
        }
