"""
ジェム取得タイミング表示ウィジェット

Act単位でジェム取得リストを表示し、チェックボックスで取得済み管理。
ジェム名はattribute別に色分け（1=赤STR, 2=緑DEX, 3=青INT）。
"""

import json
import os
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QCheckBox, QDialog, QTextEdit,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor

from src.ui.styles import Styles
from src.utils.i18n import EN, get_locale, tr, tr_ui


# attribute別の色
ATTR_COLORS = {
    1: "#ff6666",  # STR = 赤
    2: "#66ff66",  # DEX = 緑
    3: "#6688ff",  # INT = 青
    0: "#cccccc",  # 不明 = グレー
}

def format_quest_english_name(quest_key: str) -> str:
    """内部クエストキーを表示用の英語名に整形する。"""
    name = quest_key.rstrip("0123456789")
    return " ".join(word[:1].upper() + word[1:].lower() for word in name.split())


class PoBImportDialog(QDialog):
    """PoBコードインポートダイアログ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr_ui("PoBコードインポート"))
        self.setFixedSize(500, 350)
        self.setStyleSheet(f"""
            QDialog {{
                background: #1a1a2e;
                color: {Styles.TEXT_COLOR};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)
        
        # 説明
        desc = QLabel(
            tr_ui("Path of Building のエクスポートコードを貼り付けてください。\n"
            "PoBで「Export」→「Copy」でクリップボードにコピーできます。")
        )
        desc.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # テキスト入力
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(tr_ui("PoBコード（Base64）をここに貼り付け..."))
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background: #2a2a2a;
                color: {Styles.TEXT_COLOR};
                border: 1px solid #555;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', monospace;
                font-size: 12px;
            }}
        """)
        layout.addWidget(self.text_edit, stretch=1)
        
        # ボタン
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton(tr_ui("キャンセル"))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: #888;
                border: 1px solid #555; border-radius: 4px;
                padding: 6px 16px; font-size: 13px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.1); }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        import_btn = QPushButton(tr_ui("インポート"))
        import_btn.setStyleSheet(f"""
            QPushButton {{
                background: #4488ff; color: #ffffff;
                border: none; border-radius: 4px;
                padding: 6px 16px; font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #5599ff; }}
        """)
        import_btn.clicked.connect(self.accept)
        btn_layout.addWidget(import_btn)
        
        layout.addLayout(btn_layout)
    
    def get_pob_code(self) -> str:
        return self.text_edit.toPlainText().strip()


class PoBSkillSetSelectionDialog(QDialog):
    """PoB内のSkill setを選択するダイアログ。"""

    def __init__(self, skill_sets: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr_ui("Skill set選択"))
        self.setFixedSize(420, 420)
        self._checkboxes = []
        self.setStyleSheet(f"""
            QDialog {{
                background: #1a1a2e;
                color: {Styles.TEXT_COLOR};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)

        desc = QLabel(
            tr_ui("ジェム取得支援に取り込むSkill setを選んでください。\n"
            "Act中に不要なEndgame用セットなどはチェックを外せます。")
        )
        desc.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #444; background: #202035; }")
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 8, 10, 8)
        content_layout.setSpacing(6)

        for skill_set in skill_sets:
            title = skill_set.get("title", "") or f"Skill set {skill_set.get('index', 0) + 1}"
            label = f"{title}"
            if skill_set.get("active"):
                label += tr_ui("  （現在選択中）")
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.setProperty("skill_set_id", str(skill_set.get("id", "")))
            cb.setStyleSheet(f"""
                QCheckBox {{ color: {Styles.TEXT_COLOR}; font-size: 13px; padding: 2px; }}
                QCheckBox::indicator {{ width: 15px; height: 15px; }}
            """)
            content_layout.addWidget(cb)
            self._checkboxes.append(cb)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

        quick_layout = QHBoxLayout()
        all_btn = QPushButton(tr_ui("すべて選択"))
        act_btn = QPushButton(tr_ui("Actっぽいもの"))
        clear_btn = QPushButton(tr_ui("すべて解除"))
        for btn in (all_btn, act_btn, clear_btn):
            btn.setStyleSheet(self._small_btn_style())
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        all_btn.clicked.connect(lambda: self._set_all_checked(True))
        clear_btn.clicked.connect(lambda: self._set_all_checked(False))
        act_btn.clicked.connect(self._select_act_like_sets)
        layout.addLayout(quick_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton(tr_ui("キャンセル"))
        cancel_btn.setStyleSheet(self._cancel_btn_style())
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        import_btn = QPushButton(tr_ui("選択してインポート"))
        import_btn.setStyleSheet(self._primary_btn_style())
        import_btn.clicked.connect(self._accept_if_any_selected)
        btn_layout.addWidget(import_btn)
        layout.addLayout(btn_layout)

    def selected_skill_set_ids(self) -> list[str]:
        return [
            str(cb.property("skill_set_id"))
            for cb in self._checkboxes
            if cb.isChecked() and cb.property("skill_set_id") is not None
        ]

    def _set_all_checked(self, checked: bool):
        for cb in self._checkboxes:
            cb.setChecked(checked)

    @staticmethod
    def _is_act_like_skill_set_title(title: str) -> bool:
        """Skill set名からAct中に使うセットらしいかを判定する。

        - `act` が含まれる場合は、map/early/mid等を含んでもAct用として優先ON。
        - `early` / `mid` は earlygame/midgame のようにMap移行帯を指すことがあるため除外寄り。
        """
        text = title.lower()
        if "act" in text:
            return True

        is_excluded = any(word in text for word in ("early", "mid", "late", "endgame", "mapping", "map"))
        is_act_like = bool(re.search(r"\b\d+\s*-\s*\d+\b", text)) or any(word in text for word in ("leveling", "levelling"))
        return is_act_like and not is_excluded

    def _select_act_like_sets(self):
        """Act系をON、Early/Mid/Late/Endgame/Map系をOFFにする補助。"""
        for cb in self._checkboxes:
            cb.setChecked(self._is_act_like_skill_set_title(cb.text()))

    def _accept_if_any_selected(self):
        if not self.selected_skill_set_ids():
            QMessageBox.warning(self, tr_ui("Skill set未選択"), tr_ui("少なくとも1つSkill setを選択してください。"))
            return
        self.accept()

    def _small_btn_style(self):
        return """
            QPushButton {
                background: transparent; color: #bbbbbb;
                border: 1px solid #555; border-radius: 4px;
                padding: 4px 8px; font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.1); }
        """

    def _cancel_btn_style(self):
        return """
            QPushButton {
                background: transparent; color: #888;
                border: 1px solid #555; border-radius: 4px;
                padding: 6px 16px; font-size: 13px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.1); }
        """

    def _primary_btn_style(self):
        return """
            QPushButton {
                background: #4488ff; color: #ffffff;
                border: none; border-radius: 4px;
                padding: 6px 16px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #5599ff; }
        """


class GemTrackerWidget(QWidget):
    """ジェム取得タイミング表示ウィジェット"""
    
    # 外部からAct変更を受け取るシグナル
    act_changed = Signal(int)
    # ジェムチェック状態変更を外部に通知
    gem_checked = Signal(str, bool)  # (gem_name, checked)
    gem_search_requested = Signal(str)  # gem_name
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._acquisition_plan = []  # resolve結果
        self._current_act = 1
        self._checked_gems = set()   # チェック済みジェム名のセット
        self._char_class = ""
        self._ascendancy = ""
        self._library_route = False  # デフォルトはスキップルート
        self._gem_widgets = []       # (checkbox, gem_name) のリスト
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # ヘッダー行
        header = QHBoxLayout()
        header.setSpacing(6)
        
        header.addStretch()
        
        # クラス表示
        self._class_label = QLabel("")
        self._class_label.setStyleSheet("color: #888; font-size: 11px;")
        header.addWidget(self._class_label)
        
        # Act切り替えボタン
        self._prev_act_btn = QPushButton("◀")
        self._prev_act_btn.setFixedSize(22, 22)
        self._prev_act_btn.setStyleSheet(self._nav_btn_style())
        self._prev_act_btn.clicked.connect(self._prev_act)
        header.addWidget(self._prev_act_btn)
        
        self._act_label = QLabel("Act 1")
        self._act_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 11px; font-weight: bold;")
        self._act_label.setAlignment(Qt.AlignCenter)
        self._act_label.setFixedWidth(45)
        header.addWidget(self._act_label)
        
        self._next_act_btn = QPushButton("▶")
        self._next_act_btn.setFixedSize(22, 22)
        self._next_act_btn.setStyleSheet(self._nav_btn_style())
        self._next_act_btn.clicked.connect(self._next_act)
        header.addWidget(self._next_act_btn)
        
        layout.addLayout(header)
        
        # ジェムリストエリア（スクロール）
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                width: 16px;
                background: rgba(176,255,123,0.08);
                border-radius: 7px;
                margin: 0 2px;
            }
            QScrollBar::handle:vertical {
                min-height: 36px;
                background: rgba(176,255,123,0.55);
                border-radius: 7px;
            }
            QScrollBar::handle:vertical:hover { background: rgba(176,255,123,0.85); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { width: 0; height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        
        self._gem_list_widget = QWidget()
        self._gem_list_layout = QVBoxLayout(self._gem_list_widget)
        self._gem_list_layout.setContentsMargins(4, 4, 4, 4)
        self._gem_list_layout.setSpacing(2)
        self._gem_list_layout.addStretch()
        
        self._scroll.setWidget(self._gem_list_widget)
        layout.addWidget(self._scroll, stretch=1)
        
        # 未インポート時の案内
        self._empty_label = QLabel(
            tr_ui("PoBコードをインポートすると\nジェム取得タイミングが表示されます")
        )
        self._empty_label.setStyleSheet("color: #666; font-size: 11px;")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)
        
        self._scroll.setVisible(False)
        self._prev_act_btn.setVisible(False)
        self._next_act_btn.setVisible(False)
        self._act_label.setVisible(False)
    
    def _nav_btn_style(self):
        return f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: 1px solid #555; border-radius: 3px;
                font-size: 10px;
            }}
            QPushButton:hover {{ background: rgba(176,255,123,0.2); border-color: {Styles.TEXT_COLOR}; }}
        """
    

    def set_acquisition_plan(self, plan: list, char_class: str = "", ascendancy: str = ""):
        """ジェム取得計画をセット"""
        self._acquisition_plan = plan
        self._char_class = char_class
        self._ascendancy = ascendancy
        
        if plan:
            self._empty_label.setVisible(False)
            self._scroll.setVisible(True)
            self._prev_act_btn.setVisible(True)
            self._next_act_btn.setVisible(True)
            self._act_label.setVisible(True)
            
            # クラス表示
            class_text = char_class.capitalize()
            if ascendancy:
                class_text += f" ({ascendancy.capitalize()})"
            self._class_label.setText(class_text)
        else:
            self._empty_label.setVisible(True)
            self._scroll.setVisible(False)
            self._prev_act_btn.setVisible(False)
            self._next_act_btn.setVisible(False)
            self._act_label.setVisible(False)
            self._class_label.setText("")
        
        self._update_display()
    
    def set_current_act(self, act: int):
        """現在のActを設定してリストを更新"""
        if act < 1:
            act = 1
        if act > 10:
            act = 10
        self._current_act = act
        self._update_display()
    
    def set_library_route(self, library_route: bool):
        """図書館ルート設定を更新"""
        self._library_route = library_route
    
    def set_checked_gems(self, checked: set):
        """チェック済みジェムを復元"""
        self._checked_gems = set(checked)
        self._update_display()
    
    def get_checked_gems(self) -> set:
        """チェック済みジェムのセットを返す"""
        return set(self._checked_gems)
    
    def _prev_act(self):
        if self._current_act > 1:
            self._current_act -= 1
            self._update_display()
    
    def _next_act(self):
        if self._current_act < 10:
            self._current_act += 1
            self._update_display()
    
    def _update_display(self):
        """現在のActに対応するジェムリストを表示"""
        # 既存のウィジェットをクリア
        self._gem_widgets.clear()
        while self._gem_list_layout.count() > 0:
            item = self._gem_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        
        self._act_label.setText(f"Act {self._current_act}")
        
        if not self._acquisition_plan:
            return
        
        # 現在のActのエントリを取得
        act_entries = [e for e in self._acquisition_plan if e["act"] == self._current_act]
        
        if not act_entries:
            no_gem_label = QLabel(tr("gems.no_gems"))
            no_gem_label.setStyleSheet("color: #666; font-size: 11px;")
            no_gem_label.setAlignment(Qt.AlignCenter)
            self._gem_list_layout.addWidget(no_gem_label)
            self._gem_list_layout.addStretch()
            return
        
        for entry in act_entries:
            # クエストヘッダー
            quest_key = entry["quest"]
            quest_ja = entry.get("quest_ja", quest_key)
            # 内部的に breaking some eggs1/2 のような枝番を付けているクエストは、表示では枝番を外す
            quest_en = format_quest_english_name(quest_key)
            if get_locale() == EN:
                quest_display = quest_en
                npc_display = entry.get("npc", "").title()
            else:
                quest_display = f"{quest_ja}（{quest_en}）" if quest_ja != quest_en else quest_ja
                npc_display = entry.get("npc_ja", entry["npc"])
            
            first_type = entry["gems"][0]["type"] if entry["gems"] else "vendor"
            type_label = tr("gems.reward") if first_type == "quest" else tr("gems.vendor")
            
            # ヘッダーフレーム
            header_frame = QFrame()
            header_frame.setStyleSheet("""
                QFrame {
                    background: rgba(176,255,123,0.08);
                    border: none;
                    border-radius: 3px;
                    padding: 2px;
                }
            """)
            header_layout = QHBoxLayout(header_frame)
            header_layout.setContentsMargins(6, 2, 6, 2)
            header_layout.setSpacing(4)
            
            quest_label = QLabel(f"📜 {quest_display}")
            quest_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 11px; font-weight: bold;")
            header_layout.addWidget(quest_label)
            
            header_layout.addStretch()
            
            if npc_display:
                npc_label = QLabel(f"NPC: {npc_display}")
                npc_label.setStyleSheet("color: #aaa; font-size: 10px;")
                header_layout.addWidget(npc_label)
            
            self._gem_list_layout.addWidget(header_frame)
            
            # ジェムリスト
            for gem in entry["gems"]:
                gem_name = gem["name"]
                gem_name_ja = gem.get("name_ja", "")
                display_name = gem_name.title() if get_locale() == EN else (gem_name_ja or gem_name.title())
                attr_color = ATTR_COLORS.get(gem.get("attribute", 0), ATTR_COLORS[0])
                type_label = (
                    tr("gems.reward")
                    if gem.get("type") == "quest"
                    else tr("gems.vendor")
                )
                
                # チェックボックス行
                gem_row = QWidget()
                gem_row.setStyleSheet("background: transparent;")
                row_layout = QHBoxLayout(gem_row)
                row_layout.setContentsMargins(12, 1, 4, 1)
                row_layout.setSpacing(4)
                
                checkbox = QCheckBox()
                checkbox.setChecked(gem_name in self._checked_gems)
                checkbox.setStyleSheet(Styles.CHECKBOX)
                Styles.apply_checkbox_style(checkbox)
                checkbox.stateChanged.connect(
                    lambda state, name=gem_name: self._on_gem_checked(name, state)
                )
                row_layout.addWidget(checkbox)
                
                # タイプラベル（報酬/購入）
                type_label_widget = QLabel(type_label)
                type_label_widget.setFixedWidth(28)
                type_color = "#ffcc44" if gem.get("type") == "quest" else "#88aacc"
                type_label_widget.setStyleSheet(f"font-size: 9px; color: {type_color};")
                row_layout.addWidget(type_label_widget)
                
                # ジェム名（色分け）
                name_label = QLabel(display_name)
                checked_style = "text-decoration: line-through; " if gem_name in self._checked_gems else ""
                name_label.setToolTip(tr("gems.search_hint"))
                name_label.setCursor(Qt.PointingHandCursor)
                name_label.setStyleSheet(
                    f"color: {attr_color}; font-size: 12px; {checked_style}"
                )
                name_label.mousePressEvent = lambda _event, text=gem_name.title(): self.gem_search_requested.emit(text)
                row_layout.addWidget(name_label)
                
                row_layout.addStretch()
                
                # 英語名表示（日本語名がある場合のみ）
                if gem_name_ja and get_locale() != EN:
                    en_label = QLabel(gem_name.title())
                    en_label.setToolTip(tr("gems.search_hint"))
                    en_label.setCursor(Qt.PointingHandCursor)
                    en_label.setStyleSheet("color: #666; font-size: 9px;")
                    en_label.mousePressEvent = lambda _event, text=gem_name.title(): self.gem_search_requested.emit(text)
                    row_layout.addWidget(en_label)
                
                self._gem_list_layout.addWidget(gem_row)
                self._gem_widgets.append((checkbox, gem_name))
        
        self._gem_list_layout.addStretch()
    
    def _on_gem_checked(self, gem_name: str, state: int):
        """ジェムチェック状態変更"""
        checked = (state == Qt.Checked.value)
        if checked:
            self._checked_gems.add(gem_name)
        else:
            self._checked_gems.discard(gem_name)
        # 外部に通知
        self.gem_checked.emit(gem_name, checked)
        # 表示を更新（取り消し線など）
        self._update_display()
    
    def clear(self):
        """全データをクリア"""
        self._acquisition_plan = []
        self._checked_gems.clear()
        self._char_class = ""
        self._ascendancy = ""
        self._gem_widgets.clear()
        
        while self._gem_list_layout.count() > 0:
            item = self._gem_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        
        self._empty_label.setVisible(True)
        self._scroll.setVisible(False)
        self._prev_act_btn.setVisible(False)
        self._next_act_btn.setVisible(False)
        self._act_label.setVisible(False)
        self._class_label.setText("")
