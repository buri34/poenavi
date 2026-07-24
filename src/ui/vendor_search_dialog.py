import json
import os
import re
import sys

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.ui.styles import Styles
from src.ui.window_flags import _with_optional_always_on_top
from src.utils.config_manager import ConfigManager
from src.utils.poe_version_data import POE1, POE2


class VendorSearchPresetDialog(QDialog):
    """ベンダー検索プリセット編集ダイアログ"""

    DEFAULT_PRESETS = [
        {"name": "新規プリセット", "query": "", "enabled": True},
    ]
    POE1_DEFAULT_PRESETS = [
        {"name": "3リンク（色問わず）", "query": r"-\w-", "enabled": True},
    ]
    MAX_SEARCH_QUERY_LENGTH = 250

    def __init__(self, parent=None, presets_path: str = "", poe_version: str = POE2, gem_shop_query_provider=None):
        super().__init__(parent)
        from PySide6.QtWidgets import (
            QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
            QLineEdit, QTextEdit, QCheckBox, QGridLayout, QSpinBox,
        )

        self.QTableWidgetItem = QTableWidgetItem
        self.presets_path = presets_path
        self.poe_version = poe_version
        self.gem_shop_query_provider = gem_shop_query_provider
        self._syncing = False
        self._dirty = False
        self.option_checkboxes = []
        self.helper_categories = {}
        self._poe1_other_links_checkbox = None
        self._poe1_other_link_spins = {}
        self._last_poe1_other_links_pattern = ""
        self._last_poe1_generated_patterns = set()
        self._last_poe1_selected_labels = set()
        self._saved_snapshot = []
        self.setWindowFlags(_with_optional_always_on_top(Qt.Window | Qt.FramelessWindowHint, parent))
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 初期表示は従来どおり広めに開く。小さいモニターでは手動リサイズ + REGEX欄スクロールで対応。
        self.resize(1450, 850)
        self._drag_pos = None
        self._resize_edge = None
        self._EDGE_MARGIN = 8
        self.setMinimumSize(1150, 460)
        self.setMouseTracking(True)

        container = QWidget(self)
        self._container = container
        self._default_bg_alpha = 230
        container.setStyleSheet("""
            QWidget {
                background: rgba(20, 20, 20, 230);
                border: 1px solid rgba(176,255,123,0.4);
                border-radius: 6px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(8, 4, 8, 8)
        container_layout.setSpacing(6)

        title_bar = QWidget()
        self._title_bar = title_bar
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet("background: transparent; border: none;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(4, 0, 4, 0)
        title_label = QLabel(
            "🔍 PoE1 店売り検索プリセット" if self.poe_version == POE1 else "🔍 PoE2 店売り・スタッシュ検索プリセット"
        )
        title_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 15px; font-weight: bold; border: none;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #888; border: none; font-size: 14px; }
            QPushButton:hover { color: #ff6666; }
        """)
        close_btn.clicked.connect(self.close)
        title_layout.addWidget(close_btn)
        container_layout.addWidget(title_bar)

        hint_text = "左は一覧表示です。表示名・検索文字列は右側の編集枠で調整します。有効にチェックをつけたプリセットだけが検索ホットキー時のメニューに表示されます。"
        if self.poe_version == POE1:
            hint_text += " PoE1ではAct中の3リンク装備購入など、ベンダー検索向けのプリセットを管理します。"
        hint = QLabel(hint_text)
        hint.setStyleSheet("color: #aaaaaa; font-size: 13px; border: none;")
        hint.setWordWrap(True)
        container_layout.addWidget(hint)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(10)
        container_layout.addLayout(body_layout, stretch=1)

        # 左: 一覧（表示用 + 有効チェックのみ編集可）
        left_panel = QWidget()
        left_panel.setStyleSheet("background: transparent; border: none;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        body_layout.addWidget(left_panel, stretch=9)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["有効", "表示名", "検索文字列"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: rgba(26,26,26,200); color: {Styles.TEXT_COLOR};
                alternate-background-color: rgba(45, 55, 40, 120);
                border: 1px solid rgba(176,255,123,0.3); border-radius: 4px;
                gridline-color: rgba(176,255,123,0.15); font-size: 14px;
                selection-background-color: rgba(176,255,123,0.35);
                selection-color: #ffffff;
            }}
            QTableWidget::item:selected {{
                background: rgba(176,255,123,0.35);
                color: #ffffff;
            }}
            QTableWidget::item:focus {{ border: 1px solid #b0ff7b; }}
            QHeaderView::section {{
                background: rgba(40,40,40,230); color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176,255,123,0.25); padding: 6px;
            }}
        """)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._load_selected_to_editor)
        self.table.itemChanged.connect(self._table_item_changed)
        left_layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        for label, handler in [
            ("追加", self._add_row),
            ("削除", self._delete_selected),
            ("上へ", lambda: self._move_selected(-1)),
            ("下へ", lambda: self._move_selected(1)),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(Styles.BUTTON)
            btn.clicked.connect(handler)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        self.save_btn = QPushButton("保存")
        self.save_btn.setStyleSheet(self._save_button_style())
        self.save_btn.clicked.connect(self._save_presets)
        btn_row.addWidget(self.save_btn)
        left_layout.addLayout(btn_row)

        # 右: 編集欄 + regex支援チェックボックス
        right_panel = QWidget()
        right_panel.setStyleSheet("background: rgba(10,10,10,120); border: 1px solid rgba(176,255,123,0.25); border-radius: 5px;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 8, 10, 8)
        right_layout.setSpacing(8)
        body_layout.addWidget(right_panel, stretch=16)

        editor_title = QLabel("編集")
        editor_title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 16px; font-weight: bold; border: none;")
        right_layout.addWidget(editor_title)

        label_style = f"color: {Styles.TEXT_COLOR}; font-size: 13px; border: none;"
        input_style = f"""
            QLineEdit, QTextEdit {{
                background: rgba(26,26,26,220); color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176,255,123,0.35); border-radius: 4px;
                padding: 7px; font-size: 14px;
            }}
        """

        name_label = QLabel("表示名")
        name_label.setStyleSheet(label_style)
        right_layout.addWidget(name_label)
        self.name_edit = QLineEdit()
        self.name_edit.setStyleSheet(input_style)
        self.name_edit.textChanged.connect(self._editor_changed)
        right_layout.addWidget(self.name_edit)

        query_header = QHBoxLayout()
        query_header.setContentsMargins(0, 0, 0, 0)
        query_label = QLabel("検索文字列")
        query_label.setStyleSheet(label_style)
        query_header.addWidget(query_label)
        clear_query_btn = QPushButton("クリア")
        clear_query_btn.setFixedHeight(24)
        clear_query_btn.setStyleSheet(Styles.BUTTON)
        clear_query_btn.clicked.connect(self._clear_query)
        query_header.addWidget(clear_query_btn)
        if self.poe_version == POE1:
            self.gem_shop_query_btn = QPushButton("現在Actのジェムを追加")
            self.gem_shop_query_btn.setFixedHeight(24)
            self.gem_shop_query_btn.setStyleSheet(Styles.BUTTON)
            self.gem_shop_query_btn.setToolTip("現在Actで購入対象のジェムRegexを、選択中の検索文字列へ追加します")
            self.gem_shop_query_btn.clicked.connect(self._append_current_act_gem_shop_query)
            query_header.addWidget(self.gem_shop_query_btn)
        query_header.addStretch()
        self.query_length_label = QLabel(f"0/{self.MAX_SEARCH_QUERY_LENGTH}")
        self.query_length_label.setStyleSheet("color: #aaaaaa; font-size: 12px; border: none;")
        query_header.addWidget(self.query_length_label)
        right_layout.addLayout(query_header)
        self.query_edit = QTextEdit()
        self.query_edit.setFixedHeight(92)
        self.query_edit.setStyleSheet(input_style)
        self.query_edit.textChanged.connect(self._editor_changed)
        right_layout.addWidget(self.query_edit)

        if self.poe_version == POE1:
            self.include_current_act_gems_cb = QCheckBox("貼り付け時に現在Actのジェムを追加")
            self.include_current_act_gems_cb.setToolTip(
                "F4メニューで選択した時点のジェムRegexを、保存済みの検索文字列へ追加します"
            )
            Styles.apply_checkbox_style(self.include_current_act_gems_cb)
            self.include_current_act_gems_cb.toggled.connect(self._editor_changed)
            right_layout.addWidget(self.include_current_act_gems_cb)

        if self.poe_version != POE1:
            limit_note = "PoE2の検索窓は250文字が上限です。超過すると貼り付けができません。"
            self.query_limit_note = QLabel(limit_note)
            self.query_limit_note.setStyleSheet("color: #aaaaaa; font-size: 12px; border: none;")
            right_layout.addWidget(self.query_limit_note)

        helper_title = QLabel("PoE1検索作成支援（チェックすると検索文字列に追加）" if self.poe_version == POE1 else "正規表現の作成支援（チェックすると検索文字列に追加）")
        helper_title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 15px; font-weight: bold; border: none; margin-top: 4px;")
        right_layout.addWidget(helper_title)

        # REGEX候補は項目が多いため、小さいモニターでも編集欄全体を見失わないよう
        # この候補エリアだけ縦横スクロール可能にする。
        helper_scroll = QScrollArea()
        helper_scroll.setWidgetResizable(True)
        helper_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        helper_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        helper_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: rgba(10,10,10,80);
                border: 1px solid rgba(176,255,123,0.18);
                border-radius: 4px;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical, QScrollBar:horizontal {{
                background: rgba(30,30,30,150);
                border: none;
                margin: 0;
            }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: rgba(176,255,123,0.45);
                border-radius: 4px;
                min-height: 24px;
                min-width: 24px;
            }}
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
                background: rgba(176,255,123,0.70);
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                width: 0;
                height: 0;
            }}
        """)
        helper_content = QWidget()
        helper_content.setStyleSheet("background: transparent; border: none;")
        helper_content.setMinimumWidth(900)
        helper_layout = QVBoxLayout(helper_content)
        helper_layout.setContentsMargins(4, 4, 8, 4)
        helper_layout.setSpacing(8)
        self._build_regex_helper(helper_layout, QCheckBox, QGridLayout, QSpinBox)
        helper_layout.addStretch()
        helper_scroll.setWidget(helper_content)
        right_layout.addWidget(helper_scroll, stretch=1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)
        self._syncing = True
        try:
            self._load_presets()
        finally:
            self._syncing = False
        self._load_selected_to_editor()
        self._capture_saved_snapshot()

    def _save_button_style(self):
        return """
            QPushButton {
                background: #44cc66;
                color: #071407;
                border: 1px solid #b0ff7b;
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
            }
            QPushButton:hover { background: #66e685; }
            QPushButton:pressed { background: #2fa84f; }
        """

    def _set_dirty(self, dirty=True):
        self._dirty = bool(dirty)
        if hasattr(self, "save_btn"):
            self.save_btn.setText("保存 *" if self._dirty else "保存")

    def _update_query_length_label(self):
        if not hasattr(self, "query_length_label"):
            return
        length = len(self._query_text()) if hasattr(self, "query_edit") else 0
        over_limit = length > self.MAX_SEARCH_QUERY_LENGTH
        color = "#ff6666" if over_limit else "#aaaaaa"
        self.query_length_label.setText(f"{length}/{self.MAX_SEARCH_QUERY_LENGTH}")
        self.query_length_label.setStyleSheet(f"color: {color}; font-size: 12px; border: none; font-weight: {'bold' if over_limit else 'normal'};")
        if hasattr(self, "query_limit_note"):
            note_color = "#ffaaaa" if over_limit else "#aaaaaa"
            self.query_limit_note.setStyleSheet(f"color: {note_color}; font-size: 12px; border: none;")

    def _capture_saved_snapshot(self):
        self._saved_snapshot = self.presets()
        self._set_dirty(False)

    def _has_unsaved_changes(self):
        return getattr(self, "_dirty", False) or self.presets() != getattr(self, "_saved_snapshot", [])

    def _mark_dirty(self):
        if not getattr(self, "_syncing", False):
            self._set_dirty(True)

    def _table_item_changed(self, item):
        if getattr(self, "_syncing", False):
            return
        # 有効チェックのON/OFFも保存対象。
        self._set_dirty(True)

    WEAPON_BASE_AND_CATEGORY = "武器ベース"
    WEAPON_BASE_OR_CATEGORY = "武器ベース（OR条件）"
    WEAPON_BASE_OPTIONS = [
        ("弓", "弓$"),
        ("クロスボウ", "ロスボウ$"),
        ("槍（スピア）", "スピア$"),
        ("クォータースタッフ", "タースタッフ$"),
        ("ワンド", "ワンド$"),
        ("スタッフ", "(^|[^ー])スタッフ$"),
        ("セプター", "プター$"),
        ("片手メイス", "片手メイス$"),
        ("両手メイス", "両手メイス$"),
        ("タリスマン", "スマン$"),
        ("矢筒", "矢筒$"),
        ("盾", "盾$"),
        ("バックラー", "ックラー$"),
        ("フォーカス", "ォーカス$"),
    ]

    REGEX_HELPER_GROUPS = [
        (
            "共通",
            [
            ("移動スピード+", "動ス"),
            ("最大ライフ+", "大ラ"),
            ("耐性+", "耐"),
            ("スピリット+", "ト +"),
            ("筋力", "筋"),
            ("器用さ", "器"),
            ("知性", "知"),
        ],
        ),
        (
            "ビルド別",
            [
            ("全ての近接スキルのレベル+", "接スキ"),
            ("全ての投射物スキルのレベル+", "物スキ"),
            ("全てのスペルスキル+", "てのス"),
            ("火スペルスキル+", "火スペ"),
            ("冷気スペルスキル+", "気スペ"),
            ("雷スペルスキル+", "雷スペ"),
            ("混沌スペルスキル+", "沌スペ"),
            ("物理スペルスキル+", "理スペ"),
            ("ミニオンスキル+", "てのミ"),
            ("物理ダメージが#%増加する", "理ダ.*増"),
            ("#の物理ダメージを追加する", "理.*ジを追"),
            ("#の火ダメージを追加する", "火.*ジを追"),
            ("#の冷気ダメージを追加する", "気.*ジを追"),
            ("#の雷ダメージを追加する", "雷.*ジを追"),
            ("#の物理ダメージをアタックに追加する", "理ダ.*をア"),
            ("#の火ダメージをアタックに追加する", "火ダ.*をア"),
            ("#の冷気ダメージをアタックに追加する", "気ダ.*をア"),
            ("#の雷ダメージをアタックに追加する", "雷ダ.*をア"),
            ("スペルダメージが#%増加する ", "ルダ.*増"),
            ("ダメージの#%を追加火ダメ獲得", "加火"),
            ("ダメージの#%を追加冷気ダメ獲得", "加冷"),
            ("ダメージの#%を追加雷ダメ獲", "加雷"),
        ],
        ),
        (WEAPON_BASE_AND_CATEGORY, WEAPON_BASE_OPTIONS),
        (WEAPON_BASE_OR_CATEGORY, WEAPON_BASE_OPTIONS),
    ]

    POE1_REGEX_HELPER_GROUPS = [
        (
            'Link colors (3L)',
            [
                ('rrr', 'r-r-r'),
                ('ggg', 'g-g-g'),
                ('bbb', 'b-b-b'),
                ('rrg', 'r-r-g|r-g-r|g-r-r'),
                ('rrb', 'r-r-b|r-b-r|b-r-r'),
                ('ggb', 'g-g-b|g-b-g|b-g-g'),
                ('ggr', 'g-g-r|g-r-g|r-g-g'),
                ('bbr', 'b-b-r|b-r-b|r-b-b'),
                ('bbg', 'b-b-g|b-g-b|g-b-b'),
                ('rgb', ':.*(?=\\S*r)(?=\\S*g)(?=\\S*b)'),
                ('rr*', 'r-r-|-r-r|r-.-r'),
                ('gg*', 'g-g-|-g-g|g-.-g'),
                ('bb*', 'b-b-|-b-b|b-.-b'),
                ('r**', '.-.-r|.-r-.|r-.-.'),
                ('g**', '.-.-g|.-g-.|g-.-.'),
                ('b**', '.-.-b|.-b-.|b-.-.'),
            ],
        ),
        (
            'Link colors (2L)',
            [
                ('rr', 'r-r'),
                ('gg', 'g-g'),
                ('bb', 'b-b'),
                ('rb', 'r-b|b-r'),
                ('gr', 'g-r|r-g'),
                ('bg', 'b-g|g-b'),
            ],
        ),
        (
            'Any links',
            [
                ('Any 3 link', '-\\w-'),
                ('Any 4 link', '-\\w-.-'),
                ('Any 5 link', '(-\\w){4}'),
                ('Any 6 link', '(-\\w){5}'),
                ('Any 6 socket', '(\\w\\W){5}'),
            ],
        ),
        (
            'Movement Speed',
            [
                ('Movement speed (10%)', 'Runn'),
                ('Movement speed (15%)', 'rint'),
            ],
        ),
        (
            'Misc',
            [
                ('+1 wand (any)', '全てのスペ'),
                ('+1 lightning wand', 'derha'),
                ('+1 fire wand', '"me Sh"'),
                ('+1 cold wand', 'singe'),
                ('+1 phys wand', 'Litho'),
                ('+1 chaos wand', 'Lord'),
                ('Physical damage', 'Glint|Heav'),
                ('フラット元素ダメージ', 'Heat|roste|Humm'),
                ('Fire DOT multi', 'Earn'),
                ('Cold DOT multi', 'Incl'),
                ('Chaos DOT multi', 'Wani'),
            ],
        ),
        (
            'Weapon Bases',
            [
                ('Axe', '斧$'),
                ('Mace', 'メイス$'),
                ('Sword', '剣$'),
                ('Staff', 'スタッフ$'),
                ('Sceptre', 'セプター$'),
                ('Claw', '鉤爪$'),
                ('Bow', '弓$'),
                ('Wand', 'ワンド$'),
                ('Dagger', '短剣$'),
                ('Shield', 'ック率:'),
            ],
        ),
    ]

    POE1_REGEX_HELPER_CATEGORY_LABELS = {
        'Any links': '任意リンク・任意ソケット',
        'Link colors (2L)': 'リンク色（2リンク）',
        'Link colors (3L)': 'リンク色（3リンク）',
        'Misc': 'その他',
        'Movement Speed': '移動速度',
        'Other Links': 'その他リンク',
        'Weapon Bases': '武器ベース（上記の条件とOR条件で絞り込み。チェックした武器は条件に依らず、すべてハイライトされます）',
    }

    POE1_REGEX_HELPER_LABELS = {
        'フラット元素ダメージ': 'フラット元素ダメージ',
        '+1 chaos wand': '全ての混沌スペルスキル+1',
        '+1 cold wand': '全ての冷気スペルスキル+1',
        '+1 fire wand': '全ての火スペルスキル+1',
        '+1 lightning wand': '全ての雷スペルスキル+1',
        '+1 phys wand': '全ての物理スペルスキル+1',
        '+1 wand (any)': '全てのスペルスキル+1',
        'Any 3 link': '3リンク',
        'Any 4 link': '4リンク',
        'Any 5 link': '5リンク',
        'Any 6 link': '6リンク',
        'Any 6 socket': '6ソケット',
        'Axe': '斧',
        'Bow': '弓',
        'Chaos DOT multi': '混沌継続ダメージ',
        'Claw': '鉤爪',
        'Cold DOT multi': '冷気継続ダメージ',
        'Dagger': '短剣',
        'Fire DOT multi': '火継続ダメージ',
        'Mace': 'メイス',
        'Movement speed (10%)': '移動スピード10%',
        'Movement speed (15%)': '移動スピード15%',
        'Physical damage': '物理ダメージ',
        'Sceptre': 'セプター',
        'Shield': '盾',
        'Staff': 'スタッフ',
        'Sword': '剣',
        'Wand': 'ワンド',
        'b**': 'B●-＊-＊',
        'bb': 'B●-B●',
        'bb*': 'B●-B●-＊',
        'bbb': 'B●-B●-B●',
        'bbg': 'B●-B●-G●',
        'bbr': 'B●-B●-R●',
        'bg': 'B●-G●',
        'g**': 'G●-＊-＊',
        'gg': 'G●-G●',
        'gg*': 'G●-G●-＊',
        'ggb': 'G●-G●-B●',
        'ggg': 'G●-G●-G●',
        'ggr': 'G●-G●-R●',
        'gr': 'G●-R●',
        'r**': 'R●-＊-＊',
        'rb': 'R●-B●',
        'rgb': 'R●-G●-B●',
        'rr': 'R●-R●',
        'rr*': 'R●-R●-＊',
        'rrb': 'R●-R●-B●',
        'rrg': 'R●-R●-G●',
        'rrr': 'R●-R●-R●',
    }

    def _default_presets(self):
        return self.POE1_DEFAULT_PRESETS if self.poe_version == POE1 else self.DEFAULT_PRESETS

    def _load_regex_helper_groups(self):
        """REGEX支援チェックボックス候補を返す。tasks配下の作業CSVには依存しない。"""
        groups = self.POE1_REGEX_HELPER_GROUPS if self.poe_version == POE1 else self.REGEX_HELPER_GROUPS
        return [(category, list(options)) for category, options in groups]

    def _build_regex_helper(self, parent_layout, QCheckBox, QGridLayout, QSpinBox=None):
        assets_dir = os.path.join(ConfigManager._get_base_dir(), "assets")
        if not os.path.exists(os.path.join(assets_dir, "checkmark_lime.svg")):
            assets_dir = os.path.join(getattr(sys, "_MEIPASS", ConfigManager._get_base_dir()), "assets")
        checkmark_path = os.path.join(assets_dir, "checkmark_lime.svg").replace("\\", "/")
        checkbox_style = f"""
            QCheckBox {{ color: {Styles.TEXT_COLOR}; font-size: 14px; spacing: 8px; border: none; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid rgba(176,255,123,0.75);
                border-radius: 2px;
                background: rgba(230,230,230,0.18);
            }}
            QCheckBox::indicator:hover {{
                border: 1px solid #b0ff7b;
                background: rgba(176,255,123,0.18);
            }}
            QCheckBox::indicator:checked {{
                background: rgba(20, 28, 20, 220);
                border: 1px solid #b0ff7b;
                image: url("{checkmark_path}");
            }}
        """
        section_style = "color: #44cc66; font-size: 16px; font-weight: bold; border: none; margin-top: 6px;"
        self.option_checkboxes = []
        self.helper_categories = {}
        if self.poe_version == POE1:
            self._build_poe1_regex_helper(parent_layout, QCheckBox, QGridLayout, QSpinBox, checkbox_style, section_style)
            return
        groups = self._load_regex_helper_groups()
        if not groups:
            note = QLabel("REGEX支援候補が空です。")
            note.setStyleSheet("color: #ffaaaa; font-size: 13px; border: none;")
            parent_layout.addWidget(note)
            return
        for group_title, options in groups:
            section_text = group_title
            if group_title == self.WEAPON_BASE_AND_CATEGORY:
                section_text = "武器ベース（共通・ビルド別とAND条件で絞り込み。チェックすると特定の武器に限定した検索文字列になります）"
            elif group_title == self.WEAPON_BASE_OR_CATEGORY:
                section_text = "武器ベース（共通・ビルド別とOR条件で絞り込み。チェックした武器は共通・ビルド別の条件に依らず、すべてハイライトされます）"
            section = QLabel(section_text)
            section.setStyleSheet(section_style)
            parent_layout.addWidget(section)
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(26)
            grid.setVerticalSpacing(8)
            columns = 4
            row_offset = 0
            added_damage_row_aligned = False
            attack_row_aligned = False
            for index, (label, token) in enumerate(options):
                position = index + row_offset
                if (
                    group_title == "ビルド別"
                    and not added_damage_row_aligned
                    and "ダメージを追加" in label
                    and "アタック" not in label
                ):
                    if position % columns != 0:
                        row_offset += columns - (position % columns)
                        position = index + row_offset
                    added_damage_row_aligned = True
                if (
                    group_title == "ビルド別"
                    and not attack_row_aligned
                    and "アタックに追加" in label
                ):
                    if position % columns != 0:
                        row_offset += columns - (position % columns)
                        position = index + row_offset
                    attack_row_aligned = True
                cb = QCheckBox(label)
                cb.setToolTip(token)
                cb.setStyleSheet(checkbox_style)
                cb.toggled.connect(lambda checked, t=token: self._regex_option_toggled(t, checked))
                self.option_checkboxes.append((cb, token, group_title))
                self.helper_categories[token] = group_title
                grid.addWidget(cb, position // columns, position % columns)
            parent_layout.addLayout(grid)


    def _poe1_category_display_name(self, category):
        return self.POE1_REGEX_HELPER_CATEGORY_LABELS.get(category, category)

    def _poe1_label_display_name(self, label):
        return self.POE1_REGEX_HELPER_LABELS.get(label, label)

    def _poe1_checkbox_label_key(self, checkbox):
        return checkbox.property("poe1_label_key") or checkbox.text()

    def _poe1_icon_path(self, color):
        filename = {"r": "red.png", "g": "green.png", "b": "blue.png"}.get(color)
        if not filename:
            return ""
        candidates = [
            os.path.join(ConfigManager._get_base_dir(), "assets", "icons", filename),
            os.path.join(getattr(sys, "_MEIPASS", ConfigManager._get_base_dir()), "assets", "icons", filename),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path.replace("\\", "/")
        return ""

    def _poe1_link_icon_html(self, label):
        label = (label or "").strip().lower()
        if not re.fullmatch(r"[rgb*]{2,3}", label):
            return ""
        parts = []
        for ch in label:
            if ch == "*":
                parts.append('<span style="font-size:16px; color:#dddddd;">＊</span>')
                continue
            icon_path = self._poe1_icon_path(ch)
            if not icon_path:
                return ""
            parts.append(f'<img src="{icon_path}" width="20" height="18" style="vertical-align:middle;"/>')
        return '<span style="white-space:nowrap;">' + '<span style="color:#aaaaaa; padding:0 2px;">-</span>'.join(parts) + '</span>'

    def _toggle_checkbox_from_label(self, checkbox):
        checkbox.setChecked(not checkbox.isChecked())

    def _build_poe1_regex_helper(self, parent_layout, QCheckBox, QGridLayout, QSpinBox, checkbox_style, section_style):
        """PoE1用REGEX作成支援UI。よく使われるPoE1 regexサイトのカテゴリ構成に寄せる。"""
        groups = self._load_regex_helper_groups()
        for group_title, options in groups:
            section = QLabel(self._poe1_category_display_name(group_title))
            section.setStyleSheet(section_style)
            parent_layout.addWidget(section)

            if group_title == "Other Links":
                self._build_poe1_other_links(parent_layout, QCheckBox, QSpinBox, checkbox_style)
                continue

            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(24)
            grid.setVerticalSpacing(8)
            columns = 3 if group_title in ("Movement Speed", "Misc", "Weapon Bases") else 2
            for index, (label, token) in enumerate(options):
                icon_html = self._poe1_link_icon_html(label) if group_title in ("Link colors (3L)", "Link colors (2L)") else ""
                cb = QCheckBox("" if icon_html else self._poe1_label_display_name(label))
                cb.setProperty("poe1_label_key", label)
                cb.setToolTip(token)
                cb.setStyleSheet(checkbox_style)
                cb.toggled.connect(lambda checked, t=token: self._regex_option_toggled(t, checked))
                self.option_checkboxes.append((cb, token, group_title))
                self.helper_categories[token] = group_title
                if group_title == "Link colors (3L)":
                    if index < 6:
                        row, col = index, 0
                    elif index < 12:
                        row, col = index - 6, 1
                    else:
                        row, col = index - 12, 2
                elif group_title == "Link colors (2L)":
                    row, col = index % 2, index // 2
                elif group_title == "Any links":
                    if index < 2:
                        row, col = index, 0
                    elif index < 4:
                        row, col = index - 2, 1
                    else:
                        row, col = index - 4, 2
                elif group_title == "Weapon Bases":
                    if index < 3:
                        row, col = index, 0
                    elif index < 6:
                        row, col = index - 3, 1
                    elif index < 9:
                        row, col = index - 6, 2
                    else:
                        row, col = index - 9, 3
                else:
                    row, col = index // columns, index % columns
                if icon_html:
                    item = QWidget()
                    item_layout = QHBoxLayout(item)
                    item_layout.setContentsMargins(0, 0, 0, 0)
                    item_layout.setSpacing(6)
                    item_layout.addWidget(cb)
                    label_widget = QLabel(icon_html)
                    label_widget.setTextFormat(Qt.RichText)
                    label_widget.setToolTip(token)
                    label_widget.setCursor(QCursor(Qt.PointingHandCursor))
                    label_widget.setStyleSheet("border: none; padding: 1px 2px;")
                    label_widget.mousePressEvent = lambda _event, c=cb: self._toggle_checkbox_from_label(c)
                    item_layout.addWidget(label_widget)
                    item_layout.addStretch()
                    grid.addWidget(item, row, col)
                else:
                    grid.addWidget(cb, row, col)
            parent_layout.addLayout(grid)

            if group_title == "Any links":
                other_section = QLabel(self._poe1_category_display_name("Other Links"))
                other_section.setStyleSheet(section_style)
                parent_layout.addWidget(other_section)
                self._build_poe1_other_links(parent_layout, QCheckBox, QSpinBox, checkbox_style)

    def _build_poe1_other_links(self, parent_layout, QCheckBox, QSpinBox, checkbox_style):
        if QSpinBox is None:
            return
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        enable_cb = QCheckBox("有効化")
        enable_cb.setMinimumHeight(28)
        enable_cb.setStyleSheet(checkbox_style + """
            QCheckBox { padding: 4px 8px; }
            QCheckBox::indicator { width: 20px; height: 20px; }
        """)
        enable_cb.toggled.connect(lambda _checked: self._poe1_other_links_changed())
        self._poe1_other_links_checkbox = enable_cb
        row.addWidget(enable_cb)
        row.addStretch()
        parent_layout.addLayout(row)

        spin_style = f"""
            QSpinBox {{
                background: rgba(245,245,245,230); color: #111;
                border: 1px solid rgba(176,255,123,0.45); border-radius: 3px;
                padding: 4px 20px 4px 6px; font-size: 14px;
            }}
            QSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 16px;
                height: 14px;
                border-left: 1px solid rgba(0,0,0,0.35);
                border-bottom: 1px solid rgba(0,0,0,0.25);
                background: rgba(235,235,235,245);
            }}
            QSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 16px;
                height: 14px;
                border-left: 1px solid rgba(0,0,0,0.35);
                background: rgba(225,225,225,245);
            }}
            QSpinBox::up-arrow {{
                width: 0px; height: 0px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid #111;
            }}
            QSpinBox::down-arrow {{
                width: 0px; height: 0px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #111;
            }}
        """
        color_row = QHBoxLayout()
        color_row.setContentsMargins(24, 0, 0, 0)
        color_row.setSpacing(8)
        color_defs = [("R", "#c76a46"), ("G", "#b9c85a"), ("B", "#7f8fcf")]
        self._poe1_other_link_spins = {}
        for key, color in color_defs:
            spin = QSpinBox()
            spin.setRange(0, 6)
            spin.setValue(0)
            spin.setFixedSize(70, 32)
            spin.setStyleSheet(spin_style)
            spin.valueChanged.connect(lambda _value: self._poe1_other_links_changed())
            self._poe1_other_link_spins[key] = spin
            color_row.addWidget(spin)
            label = QLabel(key.lower())
            label.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold; border: none;")
            color_row.addWidget(label)
        color_row.addStretch()
        parent_layout.addLayout(color_row)

    def _poe1_other_links_pattern(self):
        if self.poe_version != POE1:
            return ""
        cb = getattr(self, "_poe1_other_links_checkbox", None)
        spins = getattr(self, "_poe1_other_link_spins", {})
        if cb is None or not cb.isChecked() or not spins:
            return ""
        counts = {key: spin.value() for key, spin in spins.items()}
        total = sum(counts.values())
        if total < 2 or total > 6:
            return ""
        # 参考サイト式: 全順列列挙ではなく、ソケット色数lookahead + 最低リンク条件で短く表現する。
        # 例 G=4 → ts:.+(?=(\S*g){4})
        # 例 R=1, G=4 → ts:.+(?=(\S*r){1})(?=(\S*g){4})
        parts = ["ts:.+"]
        color_counts = [
            (color, counts.get(key, 0))
            for key, color in (("R", "r"), ("G", "g"), ("B", "b"))
            if counts.get(key, 0)
        ]
        for index, (color, count) in enumerate(color_counts):
            is_last_of_three_colors = len(color_counts) == 3 and index == len(color_counts) - 1
            if is_last_of_three_colors:
                parts.append(f"(\\S*{color}){{{count}}}")
            else:
                parts.append(f"(?=(\\S*{color}){{{count}}})")
        return "".join(parts)

    def _poe1_other_links_changed(self):
        if getattr(self, "_syncing", False):
            return
        self._regex_option_toggled("", True)

    def _clear_query(self):
        if getattr(self, "_syncing", False):
            return
        self._syncing = True
        try:
            self.query_edit.clear()
            for cb, _token, _category in getattr(self, "option_checkboxes", []):
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
            if self._poe1_other_links_checkbox is not None:
                self._poe1_other_links_checkbox.blockSignals(True)
                self._poe1_other_links_checkbox.setChecked(False)
                self._poe1_other_links_checkbox.blockSignals(False)
            for spin in getattr(self, "_poe1_other_link_spins", {}).values():
                spin.blockSignals(True)
                spin.setValue(0)
                spin.blockSignals(False)
            self._last_poe1_other_links_pattern = ""
            self._last_poe1_generated_patterns = set()
            self._last_poe1_selected_labels = set()
        finally:
            self._syncing = False
        self._editor_changed()

    def _item(self, text=""):
        item = self.QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _current_row(self):
        return self.table.currentRow()

    def _load_selected_to_editor(self):
        if getattr(self, "_syncing", False):
            return
        row = self._current_row()
        self._syncing = True
        try:
            if row < 0:
                self.name_edit.clear()
                self.query_edit.clear()
                if hasattr(self, "include_current_act_gems_cb"):
                    self.include_current_act_gems_cb.setChecked(False)
                return
            name_item = self.table.item(row, 1)
            query_item = self.table.item(row, 2)
            self.name_edit.setText(name_item.text() if name_item else "")
            self.query_edit.setPlainText(query_item.text() if query_item else "")
            if hasattr(self, "include_current_act_gems_cb"):
                self.include_current_act_gems_cb.setChecked(
                    bool(query_item and query_item.data(Qt.UserRole))
                )
            self._refresh_regex_checkboxes()
        finally:
            self._syncing = False
            self._update_query_length_label()

    def _editor_changed(self):
        self._update_query_length_label()
        if getattr(self, "_syncing", False):
            return
        row = self._current_row()
        if row < 0:
            return
        name = self.name_edit.text().strip()
        query = self.query_edit.toPlainText().strip()
        self._syncing = True
        try:
            if self.table.item(row, 1):
                self.table.item(row, 1).setText(name)
            if self.table.item(row, 2):
                self.table.item(row, 2).setText(query)
                if hasattr(self, "include_current_act_gems_cb"):
                    self.table.item(row, 2).setData(
                        Qt.UserRole,
                        self.include_current_act_gems_cb.isChecked(),
                    )
            self._refresh_regex_checkboxes()
        finally:
            self._syncing = False
        self._set_dirty(True)

    ATTACK_DAMAGE_TOKEN_ORDER = [
        ("理ダ.*をア", "理"),
        ("火ダ.*をア", "火"),
        ("気ダ.*をア", "気"),
        ("雷ダ.*をア", "雷"),
    ]
    ADDED_DAMAGE_TOKEN_ORDER = [
        ("理.*ジを追", "理"),
        ("火.*ジを追", "火"),
        ("気.*ジを追", "気"),
        ("雷.*ジを追", "雷"),
    ]
    SPELL_SKILL_TOKEN_ORDER = [
        ("火スペ", "火"),
        ("気スペ", "気"),
        ("雷スペ", "雷"),
        ("沌スペ", "沌"),
        ("理スペ", "理"),
    ]

    def _query_text(self):
        return self.query_edit.toPlainText().strip()

    def _token_map(self, token_order):
        return dict(token_order)

    def _attack_token_map(self):
        return self._token_map(self.ATTACK_DAMAGE_TOKEN_ORDER)

    def _added_damage_token_map(self):
        return self._token_map(self.ADDED_DAMAGE_TOKEN_ORDER)

    def _spell_skill_token_map(self):
        return self._token_map(self.SPELL_SKILL_TOKEN_ORDER)

    def _is_attack_damage_token(self, token):
        return token in self._attack_token_map()

    def _is_added_damage_token(self, token):
        return token in self._added_damage_token_map()

    def _is_spell_skill_token(self, token):
        return token in self._spell_skill_token_map()

    def _is_combined_damage_token(self, token):
        return self._is_attack_damage_token(token) or self._is_added_damage_token(token) or self._is_spell_skill_token(token)

    def _damage_combined_pattern(self, selected_tokens, token_order, suffix):
        chars = "".join(name for token, name in token_order if token in selected_tokens)
        if len(chars) < 2:
            return ""
        return f"[{chars}]{suffix}"

    def _attack_damage_combined_pattern(self, selected_tokens):
        return self._damage_combined_pattern(selected_tokens, self.ATTACK_DAMAGE_TOKEN_ORDER, "ダ.*をア")

    def _added_damage_combined_pattern(self, selected_tokens):
        return self._damage_combined_pattern(selected_tokens, self.ADDED_DAMAGE_TOKEN_ORDER, ".*ジを追")

    def _spell_skill_combined_pattern(self, selected_tokens):
        return self._damage_combined_pattern(selected_tokens, self.SPELL_SKILL_TOKEN_ORDER, "スペ")

    def _all_damage_patterns(self, token_order, combined_pattern_func):
        patterns = [token for token, _name in token_order]
        tokens = [token for token, _name in token_order]
        for mask in range(1, 1 << len(tokens)):
            selected = [token for i, token in enumerate(tokens) if mask & (1 << i)]
            combined = combined_pattern_func(selected)
            if combined:
                patterns.append(combined)
        return patterns

    def _all_attack_damage_patterns(self):
        return self._all_damage_patterns(self.ATTACK_DAMAGE_TOKEN_ORDER, self._attack_damage_combined_pattern)

    def _all_added_damage_patterns(self):
        return self._all_damage_patterns(self.ADDED_DAMAGE_TOKEN_ORDER, self._added_damage_combined_pattern)

    def _all_spell_skill_patterns(self):
        return self._all_damage_patterns(self.SPELL_SKILL_TOKEN_ORDER, self._spell_skill_combined_pattern)

    def _all_combined_damage_patterns(self):
        return self._all_attack_damage_patterns() + self._all_added_damage_patterns() + self._all_spell_skill_patterns()

    def _combined_attack_damage_matches(self, query):
        return re.findall(r"\[([^\[\]]*)\]ダ\.\*をア", query)

    def _combined_added_damage_matches(self, query):
        return re.findall(r"\[([^\[\]]*)\]\.\*ジを追", query)

    def _combined_spell_skill_matches(self, query):
        return re.findall(r"\[([^\[\]]*)\]スペ", query)

    def _split_query_patterns(self, query):
        """検索文字列をトップレベルの | で分割する。引用/括弧/文字クラス内の | は分割しない。"""
        query = (query or "").strip().strip("|")
        if not query:
            return []
        patterns = []
        buf = []
        paren_depth = 0
        bracket_depth = 0
        in_quote = False
        for ch in query:
            if ch == '"':
                in_quote = not in_quote
            elif not in_quote and ch == "(":
                paren_depth += 1
            elif not in_quote and ch == ")" and paren_depth > 0:
                paren_depth -= 1
            elif not in_quote and ch == "[":
                bracket_depth += 1
            elif not in_quote and ch == "]" and bracket_depth > 0:
                bracket_depth -= 1
            if ch == "|" and not in_quote and paren_depth == 0 and bracket_depth == 0:
                part = "".join(buf).strip()
                if part:
                    patterns.append(part)
                buf = []
            else:
                buf.append(ch)
        part = "".join(buf).strip()
        if part:
            patterns.append(part)
        return patterns

    def _join_query_patterns(self, patterns):
        seen = []
        for pattern in patterns:
            pattern = (pattern or "").strip()
            if pattern and pattern not in seen:
                seen.append(pattern)
        return "|".join(seen)

    def _remove_exact_query_pattern_from_text(self, query, pattern):
        return self._join_query_patterns([p for p in self._split_query_patterns(query) if p != pattern])

    def _remove_attack_damage_patterns_from_text(self, query):
        attack_patterns = set(self._all_attack_damage_patterns())
        return self._join_query_patterns([p for p in self._split_query_patterns(query) if p not in attack_patterns])

    def _remove_combined_damage_patterns_from_text(self, query):
        damage_patterns = set(self._all_combined_damage_patterns())
        return self._join_query_patterns([p for p in self._split_query_patterns(query) if p not in damage_patterns])

    def _has_plain_query_token(self, token):
        return token in self._split_query_patterns(self._query_text())

    def _selected_damage_tokens_from_query(self, token_order, combined_matches_func):
        selected = set()
        combined_names = set()
        for pattern in self._split_query_patterns(self._query_text()):
            if pattern in dict(token_order):
                selected.add(pattern)
                continue
            for group in combined_matches_func(pattern):
                combined_names.update(ch for ch in group if ch.strip())
        for token, name in token_order:
            if name in combined_names:
                selected.add(token)
        return selected

    def _selected_attack_damage_tokens_from_query(self):
        return self._selected_damage_tokens_from_query(
            self.ATTACK_DAMAGE_TOKEN_ORDER,
            self._combined_attack_damage_matches,
        )

    def _selected_added_damage_tokens_from_query(self):
        return self._selected_damage_tokens_from_query(
            self.ADDED_DAMAGE_TOKEN_ORDER,
            self._combined_added_damage_matches,
        )

    def _selected_spell_skill_tokens_from_query(self):
        return self._selected_damage_tokens_from_query(
            self.SPELL_SKILL_TOKEN_ORDER,
            self._combined_spell_skill_matches,
        )

    def _has_query_token(self, token):
        if self._is_attack_damage_token(token):
            return token in self._selected_attack_damage_tokens_from_query()
        if self._is_added_damage_token(token):
            return token in self._selected_added_damage_tokens_from_query()
        if self._is_spell_skill_token(token):
            return token in self._selected_spell_skill_tokens_from_query()
        return self._has_plain_query_token(token)

    def _pattern_has_helper_token(self, pattern, token):
        pattern = (pattern or "").strip()
        if pattern == token:
            return True
        if pattern.startswith("(") and pattern.endswith(")"):
            return token in self._split_query_patterns(pattern[1:-1])
        return False

    def _and_base_tokens_from_query(self):
        base_tokens = {token for _label, token in self.WEAPON_BASE_OPTIONS}
        selected = set()
        quoted_and_re = re.compile(r'^"(?P<mod>.*)""(?P<base>.*)"$')
        for pattern in self._split_query_patterns(self._query_text()):
            match = quoted_and_re.fullmatch(pattern)
            if match:
                base_expr = match.group("base")
                selected.update(token for token in base_tokens if self._pattern_has_helper_token(base_expr, token))
        return selected

    def _or_base_tokens_from_query(self):
        base_tokens = {token for _label, token in self.WEAPON_BASE_OPTIONS}
        selected = set()
        quoted_and_re = re.compile(r'^"(?P<mod>.*)""(?P<base>.*)"$')
        for pattern in self._split_query_patterns(self._query_text()):
            match = quoted_and_re.fullmatch(pattern)
            if match:
                mod_expr = match.group("mod")
                selected.update(token for token in base_tokens if self._pattern_has_helper_token(mod_expr, token))
                continue
            if pattern in base_tokens:
                selected.add(pattern)
                continue
            if pattern.startswith("(") and pattern.endswith(")"):
                selected.update(token for token in base_tokens if self._pattern_has_helper_token(pattern, token))
        return selected

    def _append_query_token(self, token):
        patterns = self._split_query_patterns(self._query_text())
        if token not in patterns:
            patterns.append(token)
        self.query_edit.setPlainText(self._join_query_patterns(patterns))

    def _append_gem_shop_query(self, gem_query):
        """ジェム用OR候補を、選択中の装備検索文字列へ重複なく追加する。"""
        patterns = self._split_query_patterns(self._query_text())
        patterns.extend(self._split_query_patterns(gem_query))
        self.query_edit.setPlainText(self._join_query_patterns(patterns))

    def _append_current_act_gem_shop_query(self):
        provider = getattr(self, "gem_shop_query_provider", None)
        gem_query = provider() if callable(provider) else ""
        if not gem_query:
            QMessageBox.information(self, "ジェムRegex", "現在Actに追加できるジェムRegexがありません。")
            return
        self._append_gem_shop_query(gem_query)

    def _remove_query_token(self, token):
        self.query_edit.setPlainText(self._remove_exact_query_pattern_from_text(self._query_text(), token))

    def _set_attack_damage_selection(self, selected_tokens):
        patterns = self._split_query_patterns(self._remove_attack_damage_patterns_from_text(self._query_text()))
        selected_tokens = [token for token, _name in self.ATTACK_DAMAGE_TOKEN_ORDER if token in selected_tokens]
        if len(selected_tokens) == 1:
            patterns.append(selected_tokens[0])
        else:
            combined = self._attack_damage_combined_pattern(selected_tokens)
            if combined:
                patterns.append(combined)
        self.query_edit.setPlainText(self._join_query_patterns(patterns))

    def _append_damage_group_expr(self, parts, tokens, token_order, combined_pattern_func):
        selected_tokens = [token for token, _name in token_order if token in tokens]
        if len(selected_tokens) == 1:
            parts.append(selected_tokens[0])
        elif len(selected_tokens) > 1:
            parts.append(combined_pattern_func(selected_tokens))
        return selected_tokens

    def _helper_group_expr(self, tokens, force_group=False):
        tokens = [token for token in tokens if token]
        if not tokens:
            return ""
        parts = []
        attack_tokens = self._append_damage_group_expr(
            parts,
            tokens,
            self.ATTACK_DAMAGE_TOKEN_ORDER,
            self._attack_damage_combined_pattern,
        )
        added_damage_tokens = self._append_damage_group_expr(
            parts,
            tokens,
            self.ADDED_DAMAGE_TOKEN_ORDER,
            self._added_damage_combined_pattern,
        )
        spell_skill_tokens = self._append_damage_group_expr(
            parts,
            tokens,
            self.SPELL_SKILL_TOKEN_ORDER,
            self._spell_skill_combined_pattern,
        )
        grouped_tokens = set(attack_tokens + added_damage_tokens + spell_skill_tokens)
        other_tokens = [token for token in tokens if token not in grouped_tokens]
        parts.extend(other_tokens)
        if len(parts) == 1 and not force_group:
            return parts[0]
        return f"({'|'.join(parts)})"

    def _poe1_helper_tokens(self):
        if self.poe_version != POE1:
            return []
        return [token for _cb, token, _category in getattr(self, "option_checkboxes", []) if token]

    def _poe1_token_alternatives(self, token):
        token = (token or "").strip()
        if not token:
            return []
        # PoE1の既存REGEXサイトに合わせ、OR式は括らずフラットな候補列として扱う。
        return self._split_query_patterns(token) if "|" in token else [token]

    def _poe1_pattern_matches_token(self, pattern, token):
        pattern = (pattern or "").strip()
        token = (token or "").strip()
        if not pattern or not token:
            return False
        if pattern == token:
            return True
        if pattern.startswith("(") and pattern.endswith(")") and pattern[1:-1] == token:
            return True
        return pattern in self._poe1_token_alternatives(token)

    def _expand_poe1_link_pattern(self, pattern):
        """r-r-[gb] のような圧縮リンク表現を個別候補へ展開する。"""
        pattern = (pattern or "").strip()
        parts = pattern.split("-")
        if len(parts) < 2:
            return [pattern] if pattern else []
        expanded = [""]
        for part in parts:
            if re.fullmatch(r"\[[rgb.]+\]", part):
                choices = list(part[1:-1])
            else:
                choices = [part]
            expanded = [f"{prefix}-{choice}" if prefix else choice for prefix in expanded for choice in choices]
        return expanded

    def _expanded_poe1_query_patterns(self):
        expanded = []
        for pattern in self._split_query_patterns(self._query_text()):
            expanded.extend(self._expand_poe1_link_pattern(pattern))
        return expanded

    def _poe1_query_has_token(self, token):
        query_patterns = set(self._expanded_poe1_query_patterns())
        alternatives = set(self._poe1_token_alternatives(token))
        if not alternatives:
            return False
        # 圧縮後の [gb] なども展開して、候補の全パターンが揃っていたらチェックONに戻す。
        return alternatives.issubset(query_patterns)

    def _poe1_any_link_level(self, label):
        match = re.fullmatch(r"Any (\d+) link", (label or "").strip())
        return int(match.group(1)) if match else 0

    def _compress_poe1_any_link_entries(self, entries):
        """Any 3/4/5/6 link は大きいリンク数が小さいリンク数を包含する。"""
        if not entries:
            return []
        level, token = max(entries, key=lambda item: item[0])
        return self._poe1_token_alternatives(token)

    def _poe1_color_sort_key(self, value):
        # 参考サイトの出力に寄せる（例: [gr], [gb]）。
        order = {"g": 0, "r": 1, "b": 2, ".": 3}
        return order.get(value, 99)

    def _poe1_color_class(self, values):
        return "[" + "".join(sorted(set(values), key=self._poe1_color_sort_key)) + "]"

    def _poe1_simple_3link_label(self, label):
        label = (label or "").strip().lower()
        return label if re.fullmatch(r"[rgb]{3}", label) else ""

    def _poe1_majority_and_minority_color(self, label):
        label = self._poe1_simple_3link_label(label)
        if not label:
            return "", ""
        counts = {color: label.count(color) for color in "rgb"}
        majority = next((color for color, count in counts.items() if count == 2), "")
        minority = next((color for color, count in counts.items() if count == 1), "")
        return majority, minority

    def _compress_poe1_link_color_entries(self, entries):
        """Link colors (3L) の選択を参考サイト風に圧縮する。"""
        labels = [(label, token) for label, token in entries if self._poe1_simple_3link_label(label)]
        if len(labels) == 2:
            (label1, token1), (label2, token2) = labels
            maj1, min1 = self._poe1_majority_and_minority_color(label1)
            maj2, min2 = self._poe1_majority_and_minority_color(label2)
            if maj1 and maj2:
                # rrb + rrg → r-r-[gb]|r-[gb]-r|[gb]-r-r
                if maj1 == maj2 and min1 != min2:
                    cls = self._poe1_color_class([min1, min2])
                    return [f"{maj1}-{maj1}-{cls}", f"{maj1}-{cls}-{maj1}", f"{cls}-{maj1}-{maj1}"]
                # rrg + ggr → g-[gr]-r|r-[gr]-g|g-r-g|r-g-r
                if {maj1, min1} == {maj2, min2} and maj1 != maj2:
                    a = maj1
                    b = maj2
                    cls = self._poe1_color_class([a, b])
                    return [f"{b}-{cls}-{a}", f"{a}-{cls}-{b}", f"{b}-{a}-{b}", f"{a}-{b}-{a}"]
        flat = []
        for _label, token in entries:
            flat.extend(self._poe1_token_alternatives(token))
        return self._compress_poe1_link_patterns(flat)

    def _dedupe_poe1_covered_link_patterns(self, patterns):
        """ワイルドカード系リンク表現が包含する具体候補を削る。

        例: rr* の `r-r-|-r-r|r-.-r` は r-r-r を含むので、rrrを同時選択しても追加しない。
        """
        patterns = [p for p in patterns if p]
        covered_by_wildcards = set()
        for pattern in patterns:
            parts = pattern.split("-")
            if len(parts) < 2:
                continue
            wildcard_positions = [i for i, part in enumerate(parts) if part in ("", ".")]
            if not wildcard_positions:
                continue
            concrete_parts = [part for part in parts if part not in ("", ".")]
            if not concrete_parts:
                continue
            for wildcard_color in "rgb":
                expanded = [wildcard_color if part in ("", ".") else part for part in parts]
                covered_by_wildcards.add("-".join(expanded))
        return [pattern for pattern in patterns if pattern not in covered_by_wildcards]

    def _compress_poe1_link_patterns(self, patterns):
        """r-r-b + r-r-g のような同形リンク候補を r-r-[gb] に圧縮する。"""
        remaining = list(patterns)
        compressed = []
        changed = True
        color_re = re.compile(r"^[rgb.]$")

        while changed:
            changed = False
            used = set()
            best_group = None

            for length in sorted({len(p.split("-")) for p in remaining if "-" in p}, reverse=True):
                length_patterns = [(i, p, p.split("-")) for i, p in enumerate(remaining) if len(p.split("-")) == length]
                for pos in reversed(range(length)):
                    groups = {}
                    for i, pattern, parts in length_patterns:
                        if i in used or not all(color_re.fullmatch(part) for part in parts):
                            continue
                        key = tuple(part if idx != pos else "*" for idx, part in enumerate(parts))
                        groups.setdefault(key, []).append((i, parts[pos], parts))
                    for key, entries in groups.items():
                        values = {value for _i, value, _parts in entries}
                        if len(values) >= 2 and len(entries) > 1:
                            best_group = (pos, key, entries)
                            break
                    if best_group:
                        break
                if best_group:
                    break

            if not best_group:
                break

            pos, _key, entries = best_group
            indexes = {i for i, _value, _parts in entries}
            base_parts = list(entries[0][2])
            values = sorted({value for _i, value, _parts in entries}, key=self._poe1_color_sort_key)
            base_parts[pos] = f"[{''.join(values)}]"
            compressed.append("-".join(base_parts))
            remaining = [p for i, p in enumerate(remaining) if i not in indexes]
            changed = True

        return remaining + compressed

    def _regenerate_poe1_query_from_helper_checkboxes(self):
        manual_patterns = [
            pattern for pattern in self._split_query_patterns(self._query_text())
            if not self._is_helper_generated_pattern(pattern)
        ]
        helper_patterns = []
        link_color_entries = []
        any_link_entries = []
        selected_labels = set()
        selected_options = []
        for cb, token, category in getattr(self, "option_checkboxes", []):
            if not cb.isChecked():
                continue
            label = self._poe1_checkbox_label_key(cb)
            selected_labels.add((category, label))
            selected_options.append((label, token, category))
            any_link_level = self._poe1_any_link_level(label) if category == "Any links" else 0
            if any_link_level:
                any_link_entries.append((any_link_level, token))

        max_any_link_level = max((level for level, _token in any_link_entries), default=0)
        any_link_covers_color_links = max_any_link_level >= 3
        for label, token, category in selected_options:
            if category == "Any links" and self._poe1_any_link_level(label):
                continue
            # Any 3+ link は 2L/3L の具体色指定も包含するので、出力には足さない。
            if any_link_covers_color_links and category in ("Link colors (3L)", "Link colors (2L)"):
                continue
            if category == "Link colors (3L)" and self._poe1_simple_3link_label(label):
                link_color_entries.append((label, token))
                continue
            helper_patterns.extend(self._poe1_token_alternatives(token))
        if link_color_entries:
            helper_patterns.extend(self._compress_poe1_link_color_entries(link_color_entries))
        if any_link_entries:
            helper_patterns.extend(self._compress_poe1_any_link_entries(any_link_entries))
        other_links_pattern = self._poe1_other_links_pattern()
        if other_links_pattern:
            helper_patterns.extend(self._poe1_token_alternatives(other_links_pattern))
        helper_patterns = self._dedupe_poe1_covered_link_patterns(helper_patterns)
        helper_patterns = self._compress_poe1_link_patterns(helper_patterns)
        self._last_poe1_other_links_pattern = other_links_pattern
        self._last_poe1_generated_patterns = set(helper_patterns)
        self._last_poe1_selected_labels = selected_labels
        self.query_edit.setPlainText(self._join_query_patterns(manual_patterns + helper_patterns))

    def _is_helper_generated_pattern(self, pattern):
        if not pattern:
            return False
        if pattern in getattr(self, "_last_poe1_generated_patterns", set()):
            return True
        helper_tokens = {token for _cb, token, _category in getattr(self, "option_checkboxes", [])}
        if self.poe_version == POE1:
            if any(self._poe1_pattern_matches_token(pattern, token) for token in helper_tokens):
                return True
            last_other = getattr(self, "_last_poe1_other_links_pattern", "")
            if last_other and self._poe1_pattern_matches_token(pattern, last_other):
                return True
        if pattern in helper_tokens:
            return True
        if pattern == getattr(self, "_last_poe1_other_links_pattern", ""):
            return True
        if pattern in self._all_combined_damage_patterns():
            return True
        if re.fullmatch(r'".*"".*"', pattern):
            return True
        # ORでまとめたヘルパー表現も再生成対象として扱う。
        if pattern.startswith("(") and pattern.endswith(")"):
            inner = pattern[1:-1]
            return any(part in helper_tokens or part in self._all_combined_damage_patterns() for part in self._split_query_patterns(inner))
        return False

    def _strip_helper_generated_patterns(self, query):
        return self._join_query_patterns([p for p in self._split_query_patterns(query) if not self._is_helper_generated_pattern(p)])

    def _selected_helper_tokens_from_checkboxes(self):
        selected = {"mod": [], "base": [], "base_or": [], "other": []}
        for cb, token, category in getattr(self, "option_checkboxes", []):
            if not cb.isChecked():
                continue
            if category in ("共通", "ビルド別"):
                selected["mod"].append(token)
            elif category == self.WEAPON_BASE_AND_CATEGORY:
                selected["base"].append(token)
            elif category == self.WEAPON_BASE_OR_CATEGORY:
                selected["base_or"].append(token)
            else:
                selected["other"].append(token)
        return selected

    def _regenerate_query_from_helper_checkboxes(self):
        poe_version = getattr(self, "poe_version", POE2)
        if poe_version == POE1:
            self._regenerate_poe1_query_from_helper_checkboxes()
            return
        manual_query = self._strip_helper_generated_patterns(self._query_text())
        patterns = self._split_query_patterns(manual_query)
        selected = self._selected_helper_tokens_from_checkboxes()
        base_expr = self._helper_group_expr(selected["base"])
        mod_or_tokens = selected["mod"] + selected["base_or"]
        if base_expr:
            mod_or_expr = self._helper_group_expr(mod_or_tokens)
            if mod_or_expr:
                patterns.append(f'"{mod_or_expr}""{base_expr}"')
            else:
                patterns.append(base_expr)
        else:
            mod_or_expr = self._helper_group_expr(mod_or_tokens)
            if mod_or_expr:
                patterns.append(mod_or_expr)
        patterns.extend(selected["other"])
        other_links_pattern = self._poe1_other_links_pattern() if poe_version == POE1 else ""
        if other_links_pattern:
            patterns.append(other_links_pattern)
        self._last_poe1_other_links_pattern = other_links_pattern
        self.query_edit.setPlainText(self._join_query_patterns(patterns))

    def _regex_option_toggled(self, token, checked):
        if getattr(self, "_syncing", False):
            return
        self._syncing = True
        try:
            self._regenerate_query_from_helper_checkboxes()
        finally:
            self._syncing = False
        self._editor_changed()
        self._refresh_regex_checkboxes()

    def _refresh_regex_checkboxes(self):
        query = self._query_text()
        if self.poe_version == POE1:
            selected_labels = getattr(self, "_last_poe1_selected_labels", set())
            generated_patterns = getattr(self, "_last_poe1_generated_patterns", set())
            current_patterns = set(self._split_query_patterns(self._query_text()))
            use_label_state = bool(current_patterns) and bool(selected_labels) and generated_patterns.issubset(current_patterns)
            for cb, token, category in getattr(self, "option_checkboxes", []):
                cb.blockSignals(True)
                if use_label_state:
                    cb.setChecked((category, self._poe1_checkbox_label_key(cb)) in selected_labels)
                else:
                    cb.setChecked(self._poe1_query_has_token(token))
                cb.blockSignals(False)
            other_cb = getattr(self, "_poe1_other_links_checkbox", None)
            if other_cb is not None:
                other_cb.blockSignals(True)
                other_cb.setChecked(bool(getattr(self, "_last_poe1_other_links_pattern", "") and self._poe1_query_has_token(self._last_poe1_other_links_pattern)))
                other_cb.blockSignals(False)
            return
        and_base_tokens = self._and_base_tokens_from_query()
        or_base_tokens = self._or_base_tokens_from_query()
        for cb, token, category in getattr(self, "option_checkboxes", []):
            cb.blockSignals(True)
            if category in ("共通", "ビルド別"):
                cb.setChecked(self._has_query_token(token) or token in query)
            elif category == self.WEAPON_BASE_AND_CATEGORY:
                cb.setChecked(token in and_base_tokens)
            elif category == self.WEAPON_BASE_OR_CATEGORY:
                cb.setChecked(token in or_base_tokens)
            else:
                cb.setChecked(self._has_query_token(token))
            cb.blockSignals(False)

    def _enabled_item(self, enabled=True):
        item = self.QTableWidgetItem("")
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
        return item

    def _append_preset(self, preset):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, self._enabled_item(bool(preset.get("enabled", True))))
        self.table.setItem(row, 1, self._item(preset.get("name", "")))
        query_item = self._item(preset.get("query", ""))
        query_item.setData(Qt.UserRole, bool(preset.get("include_current_act_gems", False)))
        self.table.setItem(row, 2, query_item)
        if self.table.currentRow() < 0:
            self.table.selectRow(row)

    def _load_presets(self):
        presets = []
        if self.presets_path and os.path.exists(self.presets_path):
            try:
                with open(self.presets_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                presets = data.get("presets", [])
            except Exception as e:
                print(f"[VendorSearchPresetDialog] Failed to load presets: {e}")
        if not presets:
            presets = self._default_presets()
        self.table.setRowCount(0)
        for preset in presets:
            self._append_preset(preset)

    def presets(self):
        result = []
        for row in range(self.table.rowCount()):
            enabled_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            query_item = self.table.item(row, 2)
            name = name_item.text().strip() if name_item else ""
            query = query_item.text().strip() if query_item else ""
            if not name and not query:
                continue
            preset = {
                "enabled": enabled_item.checkState() == Qt.Checked if enabled_item else True,
                "name": name or query,
                "query": query,
            }
            if self.poe_version == POE1 and query_item and query_item.data(Qt.UserRole):
                preset["include_current_act_gems"] = True
            result.append(preset)
        return result

    def _find_over_limit_presets(self, presets):
        return [
            (index + 1, preset.get("name", ""), len(preset.get("query", "")))
            for index, preset in enumerate(presets)
            if len(preset.get("query", "")) > self.MAX_SEARCH_QUERY_LENGTH
        ]

    def _save_presets(self):
        try:
            presets = self.presets()
            over_limit = self._find_over_limit_presets(presets)
            if over_limit:
                details = "\n".join(
                    f"{row}行目: {name or '（名称なし）'}（{length}文字）"
                    for row, name, length in over_limit[:5]
                )
                if len(over_limit) > 5:
                    details += f"\n...ほか{len(over_limit) - 5}件"
                QMessageBox.warning(
                    self,
                    "検索文字列が長すぎます",
                    f"PoE2の検索窓は{self.MAX_SEARCH_QUERY_LENGTH}文字が上限です。\n"
                    "上限を超えるプリセットは正しく貼り付けできないため、保存を中止しました。\n\n"
                    f"{details}",
                )
                return
            data = {"presets": presets}
            with open(self.presets_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._capture_saved_snapshot()
            print(f"[VendorSearchPresetDialog] Presets saved to {self.presets_path}")
        except Exception as e:
            print(f"[VendorSearchPresetDialog] Failed to save presets: {e}")

    def _add_row(self):
        self._append_preset({"name": "新規プリセット", "query": "", "enabled": True})
        self.table.selectRow(self.table.rowCount() - 1)
        self._set_dirty(True)

    def _delete_selected(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            self.table.removeRow(row)
        self._set_dirty(True)

    def _move_selected(self, delta):
        row = self.table.currentRow()
        target = row + delta
        if row < 0 or target < 0 or target >= self.table.rowCount():
            return
        values = []
        for col in range(3):
            item = self.table.takeItem(row, col)
            values.append(item)
        self.table.removeRow(row)
        self.table.insertRow(target)
        for col, item in enumerate(values):
            self.table.setItem(target, col, item)
        self.table.selectRow(target)
        self._set_dirty(True)

    def _get_edge(self, pos):
        m = self._EDGE_MARGIN
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        edge = ""
        if y < m: edge += "t"
        elif y > h - m: edge += "b"
        if x < m: edge += "l"
        elif x > w - m: edge += "r"
        return edge

    def _edge_cursor(self, edge):
        if edge in ("t", "b"): return Qt.SizeVerCursor
        if edge in ("l", "r"): return Qt.SizeHorCursor
        if edge in ("tl", "br"): return Qt.SizeFDiagCursor
        if edge in ("tr", "bl"): return Qt.SizeBDiagCursor
        return Qt.ArrowCursor

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        edge = self._get_edge(event.position().toPoint())
        if edge:
            self._resize_edge = edge
            self._resize_start = event.globalPosition().toPoint()
            self._resize_geo = self.geometry()
            event.accept()
        elif event.position().y() < 32:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._resize_edge and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._resize_start
            geo = QRect(self._resize_geo)
            if "r" in self._resize_edge: geo.setRight(geo.right() + delta.x())
            if "b" in self._resize_edge: geo.setBottom(geo.bottom() + delta.y())
            if "l" in self._resize_edge: geo.setLeft(geo.left() + delta.x())
            if "t" in self._resize_edge: geo.setTop(geo.top() + delta.y())
            if geo.width() >= self.minimumWidth() and geo.height() >= self.minimumHeight():
                self.setGeometry(geo)
            event.accept()
        elif self._drag_pos and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            edge = self._get_edge(event.position().toPoint())
            self.setCursor(self._edge_cursor(edge))

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_edge = None
        self.setCursor(Qt.ArrowCursor)

    def _save_and_close(self):
        self._save_presets()
        self.hide()

    def closeEvent(self, event):
        if not self._has_unsaved_changes():
            event.accept()
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("未保存の変更")
        msg.setText("保存していない変更があります。保存しますか？")
        msg.setIcon(QMessageBox.Question)
        save_button = msg.addButton("保存", QMessageBox.AcceptRole)
        discard_button = msg.addButton("保存せずに閉じる", QMessageBox.DestructiveRole)
        cancel_button = msg.addButton("キャンセル", QMessageBox.RejectRole)
        msg.setDefaultButton(save_button)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == save_button:
            self._save_presets()
            event.accept()
        elif clicked == discard_button:
            self._syncing = True
            try:
                self._load_presets()
            finally:
                self._syncing = False
            self._load_selected_to_editor()
            self._capture_saved_snapshot()
            event.accept()
        else:
            event.ignore()
