from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QGroupBox, QLineEdit, QFileDialog,
                               QTabWidget, QWidget, QScrollArea, QSpinBox,
                               QFormLayout, QTextEdit, QFrame, QRadioButton,
                               QButtonGroup, QGridLayout)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence
from src.ui.styles import Styles
from src.utils.zone_data import DEFAULT_ZONE_DATA
from src.utils.guide_data import load_guide_data, save_guide_data

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
    
    def __init__(self, parent, zone_name: str, guide: dict, guide_v2: dict = None, zone_id: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"ガイド編集 — {zone_name}")
        self.resize(550, 620)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self.guide_v2 = guide_v2 or {}
        self.zone_id = zone_id
        
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
        
        layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)
        
        # OK/Cancel
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Save")
        ok_btn.setStyleSheet(Styles.BUTTON)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
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


class SettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
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
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        
        # ホットキー設定グループ
        group = QGroupBox("Hotkeys")
        group.setStyleSheet(f"QGroupBox {{ color: {Styles.TEXT_COLOR}; border: 1px solid {Styles.TEXT_COLOR}; border-radius: 5px; margin-top: 10px; }} QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; }}")
        group_layout = QVBoxLayout(group)
        
        h_layout1 = QHBoxLayout()
        h_layout1.addWidget(QLabel("Start/Stop:"))
        self.start_stop_btn = HotkeyButton(self.hotkeys.get("start_stop", "F1"))
        h_layout1.addWidget(self.start_stop_btn)
        group_layout.addLayout(h_layout1)
        
        h_layout2 = QHBoxLayout()
        h_layout2.addWidget(QLabel("Reset:"))
        self.reset_btn = HotkeyButton(self.hotkeys.get("reset", "F2"))
        h_layout2.addWidget(self.reset_btn)
        group_layout.addLayout(h_layout2)
        
        h_layout3 = QHBoxLayout()
        h_layout3.addWidget(QLabel("Lap (Next Act):"))
        self.lap_btn = HotkeyButton(self.hotkeys.get("lap", "F3"))
        h_layout3.addWidget(self.lap_btn)
        group_layout.addLayout(h_layout3)
        
        h_layout4 = QHBoxLayout()
        h_layout4.addWidget(QLabel("Undo Lap:"))
        self.undo_lap_btn = HotkeyButton(self.hotkeys.get("undo_lap", "F4"))
        h_layout4.addWidget(self.undo_lap_btn)
        group_layout.addLayout(h_layout4)
        
        general_layout.addWidget(group)
        
        # Client.txt パス設定
        log_group = QGroupBox("PoE Log File")
        log_group.setStyleSheet(group.styleSheet())
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
        
        browse_btn = QPushButton("Browse")
        browse_btn.setStyleSheet(Styles.BUTTON)
        browse_btn.clicked.connect(self.browse_log_file)
        log_layout.addWidget(browse_btn)
        
        general_layout.addWidget(log_group)
        
        # ガイドフォントサイズ設定
        font_group = QGroupBox("ガイド表示")
        font_group.setStyleSheet(group.styleSheet())
        font_layout = QHBoxLayout(font_group)
        
        font_label = QLabel("フォントサイズ:")
        font_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 12px;")
        font_layout.addWidget(font_label)
        
        self.guide_font_spin = QSpinBox()
        self.guide_font_spin.setRange(8, 20)
        self.guide_font_spin.setValue(self.current_config.get("guide_font_size", 12))
        self.guide_font_spin.setSuffix(" px")
        self.guide_font_spin.setFixedWidth(100)
        self.guide_font_spin.setStyleSheet(_spinbox_style(width=80, height=30))
        font_layout.addWidget(self.guide_font_spin)
        font_layout.addStretch()
        
        general_layout.addWidget(font_group)
        
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
                zone_id = z.get("id", "")
                row = QHBoxLayout()
                row.setSpacing(5)
                
                name_edit = QLineEdit(z.get("zone", ""))
                name_edit.setFixedWidth(200)
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
        zone_layout.addWidget(reset_zones_btn)
        
        tabs.addTab(zone_tab, "エリア情報")
        
        layout.addWidget(tabs)
        
        # OK/Cancel
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Save")
        self.ok_btn.setStyleSheet(Styles.BUTTON)
        self.ok_btn.clicked.connect(self.accept)
        
        self.cancel_btn = QPushButton("Cancel")
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
        dialog = GuideEditorDialog(self, display_name, self.guide_data.get(guide_key, {}), self.guide_data.get(v2_key, {}), zone_id=zone_id)
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
                    # Preserve existing level from config
                    existing_level = 1
                    for z in self.zone_data.get(act_name, []):
                        if z.get("id") == zone_id:
                            existing_level = z.get("level", 1)
                            break
                    zones.append({"id": zone_id, "zone": zone_name, "level": existing_level})
            zone_data[act_name] = zones
        
        # ガイドデータも保存
        save_guide_data(self.guide_data)
        
        return {
            "hotkeys": {
                "start_stop": self.start_stop_btn.key_text,
                "reset": self.reset_btn.key_text,
                "lap": self.lap_btn.key_text,
                "undo_lap": self.undo_lap_btn.key_text
            },
            "client_log_path": self.log_path_edit.text().strip(),
            "zone_data": zone_data,
            "guide_font_size": self.guide_font_spin.value(),
            "town_zones": [z.strip() for z in self.town_zones_edit.toPlainText().split("\n") if z.strip()],
        }
