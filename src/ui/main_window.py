import json
import os
import re
import sys
import time
from pynput import keyboard as pynput_keyboard
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QPushButton, QMenu, QFrame, QScrollArea,
                               QSizeGrip, QMessageBox)
from PySide6.QtCore import Qt, QTimer, Signal, QRect, QEvent, QPoint
from PySide6.QtGui import QCursor, QMouseEvent, QIcon
from src.ui.styles import Styles
from src.ui.settings_dialog import SettingsDialog
from src.ui.map_viewer import MapThumbnailWidget
from src.utils.config_manager import ConfigManager
from src.utils.lap_recorder import LapRecorder
from src.utils.log_watcher import LogWatcher
from src.utils.zone_data import get_zone_info, get_level_advice, DEFAULT_ZONE_DATA
from src.utils.guide_data import load_guide_data, get_zone_guide, format_guide_html

class MainWindow(QMainWindow):
    # ホットキーイベントをメインスレッドで処理するためのシグナル
    hotkey_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ぽえなび")

        # config の display_monitor で指定されたモニターの右端に縦長で配置
        from PySide6.QtWidgets import QApplication
        _config = ConfigManager.load_config()
        self._display_monitor_index = _config.get("display_monitor", 0)
        self._initial_positioned = False
        self.resize(420, 1200)  # 仮サイズ、showEvent で実際に配置

        # アプリアイコン設定
        icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "icon.ico")
        if not os.path.exists(icon_path):
            # PyInstaller _MEIPASS対応
            base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.argv[0])))
            icon_path = os.path.join(base, "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setStyleSheet(Styles.MAIN_WINDOW)
        
        # 設定読み込み
        self.config = ConfigManager.load_config()
        
        self.drag_position = None
        self.resize_edge = None  # None or combination of 'left','right','top','bottom'
        self.resize_start_geo = None
        self.resize_start_pos = None
        self.window_locked = self.config.get("window_locked", False)
        self.EDGE_MARGIN = 14
        
        # エリア訪問回数カウンター（街エリアはカウントしない）— zone_id基準
        self.zone_visit_counts = {}
        # 起動時の復元中はvisitカウントしない
        self._restoring = False
        # 訪問回数の手動オーバーライド（None=自動, 1 or 2=固定）— ゾーン移動でリセット
        self.visit_override = None
        # Lab中フラグ（志す者の広場→Lab内エリア→街帰還を追跡）
        self._in_lab = False
        self._lab_zone_id = None  # Lab入口の志す者の広場のzone_id
        
        # ガイド折りたたみ状態（初回はTrue、以降はconfig保持）
        self.guide_expanded = self.config.get("guide_expanded", True)
        # ガイドフォントサイズ
        self.guide_font_size = self.config.get("guide_font_size", 18)
        # タイマーサイズ
        self.timer_size = self.config.get("timer_size", "large")
        self.TIMER_SIZES = {
            "large":  {"main": 96, "ms": 32, "container_pad": 20},
            "medium": {"main": 64, "ms": 22, "container_pad": 14},
            "small":  {"main": 42, "ms": 16, "container_pad": 8},
        }
        # Part 2モード
        self.part2_mode = self.config.get("part2_mode", False)
        self.part2_level_threshold = self.config.get("part2_level_threshold", 39)
        self.part2_only_zones = self.config.get("part2_only_zones", [
            "冒涜された広間", "The Desecrated Chambers",
            "谷底への道", "The Descent",
            "腐った核", "The Rotting Core",
            "有毒な排水路", "The Toxic Conduits",
            "穀物倉庫", "The Grain Gate",
            "帝国の穀倉地帯", "The Imperial Fields",
            "ルナリスの中央広場", "The Lunaris Concourse",
            "ソラリスの中央広場", "The Solaris Concourse",
            "荒廃した広場", "The Ravaged Square",
            "運河", "The Canals",
            "餌場", "The Feeding Trough",
            "カルイの要塞", "The Karui Fortress",
            "シャヴロンの塔", "Shavronne's Tower",
            "海水の王の岩礁", "The Brine King's Reef",
            "マリガロの聖域", "Maligaro's Sanctum",
            "焼け野原", "The Ashen Fields",
            "土手道", "The Causeway",
            "ヴァールの街", "The Vaal City",
            "堕落の寺院 -第一層-", "The Temple of Decay Level 1",
            "サーンの城壁", "The Sarn Ramparts",
            "ドードリの汚水槽", "Doedre's Cesspool",
            "波止場", "The Quay",
            "港の橋", "The Harbour Bridge",
            "浴場", "The Bath House",
            "ヴァスティリ砂漠", "The Vastiri Desert",
            "オアシス", "The Oasis",
            "山麓", "The Foothills",
            "沸き立つ湖", "The Boiling Lake",
            "坑道", "The Tunnel",
            "採石場", "The Quarry",
            "精錬所", "The Refinery",
        ])
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_display)
        self.start_time = 0.0
        self.accumulated_time = 0.0
        self.is_running = False
        
        # ラップタイム用
        self.lap_times = [None] * 10  # Act 1-10
        self.current_act = 1  # 1-10
        
        self.setup_ui()
        self.map_thumbnail.auto_open = self.config.get("auto_open_map", False)
        self.map_thumbnail.auto_position = self.config.get("auto_position_map", True)
        self.setMouseTracking(True)
        self.centralWidget().setMouseTracking(True)
        self._apply_bg_opacity(self.config.get("window_opacity", 100))
        
        # レベルガイド状態
        self.player_level = 1
        self.current_zone = ""
        self.zone_data = self.config.get("zone_data", DEFAULT_ZONE_DATA)
        self.guide_data = load_guide_data()
        
        # monster_levels.json 読み込み
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            base_dir = exe_dir
            if not os.path.exists(os.path.join(exe_dir, "monster_levels.json")):
                base_dir = getattr(sys, '_MEIPASS', exe_dir)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        monster_levels_path = os.path.join(base_dir, "monster_levels.json")
        self.monster_levels = {}
        if os.path.exists(monster_levels_path):
            try:
                with open(monster_levels_path, 'r', encoding='utf-8') as f:
                    self.monster_levels = json.load(f)
                print(f"Loaded monster_levels.json: {len(self.monster_levels)} entries")
            except Exception as e:
                print(f"Failed to load monster_levels.json: {e}")
        
        # ログ監視
        self.log_watcher = LogWatcher(
            log_path=self.config.get("client_log_path", ""),
            parent=self
        )
        self.log_watcher.zone_entered.connect(self.on_zone_entered)
        self.log_watcher.level_up.connect(self.on_level_up)
        self.log_watcher.kitava_defeated.connect(self.on_kitava_defeated)
        self.log_watcher.act10_cleared.connect(self.on_act10_cleared)
        
        # ホットキー初期化
        self.hotkey_signal.connect(self.handle_hotkey)
        self.keyboard_listener = None
        self.register_hotkeys()
        
        # ログ監視開始（復元中はvisitカウントしない）
        if self.config.get("client_log_path"):
            self._restoring = True
            self.log_watcher.start()
            self._restoring = False
        
        # タイマー状態復元
        self._restore_timer_state()
        
        # 初回起動チェック（ポップアップ + ガイドエリア案内）
        self._check_first_run()
        
        # 全ウィジェットのマウスイベントを横取りしてリサイズ処理
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        self._ef_resize_active = False
        self._ef_resize_edge = None
        self._ef_resize_start_geo = None
        self._ef_resize_start_pos = None
        
    def _check_first_run(self):
        """初回起動時のセットアップ案内"""
        log_path = self.config.get("client_log_path", "")
        is_first_run = not self.config.get("setup_completed", False)
        
        if is_first_run and not log_path:
            # ポップアップ表示
            msg = QMessageBox(self)
            msg.setStyleSheet("QMessageBox { font-size: 14px; } QMessageBox QLabel { font-size: 14px; }")
            msg.setWindowTitle("⚙️ 初回セットアップ")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText(
                "ぽえなびをご利用いただきありがとうございます！\n\n"
                "このアプリはPoEのログファイル（Client.txt）を監視して、"
                "エリア移動やレベルアップを自動検知します。\n\n"
                "最初にログファイルのパスを設定してください：\n\n"
                "1. 右クリックメニューの「設定」、または右側中央の ⚙️ ボタンから設定画面を開く\n"
                "2. 「基本設定」タブの「Client.txt パス」を設定\n"
                "3. 通常のパス例（Steam版）：\n"
                "    C:\\Program Files (x86)\\Steam\\steamapps\n"
                "    \\common\\Path of Exile\\logs\\Client.txt\n\n"
                "⚠️ パスが正しく設定されないと、エリア検知が動作しません。"
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
            # setup_completedフラグはログパス設定時に立てる
        
        # ログファイル未設定の場合、ガイドエリアに案内表示
        if not log_path:
            self.guide_text_label.setText(
                '<div style="padding: 15px;">'
                '<span style="font-size: 20px;">⚙️</span>'
                '<span style="font-size: 15px; color: #ffc832; font-weight: bold;">'
                ' ログファイル（Client.txt）が未設定です</span><br><br>'
                '<span style="font-size: 13px; color: #cccccc;">'
                '右クリック →「設定」→「基本設定」タブから<br>'
                'Client.txt のパスを設定してください</span><br><br>'
                '<span style="font-size: 12px; color: #999999;">'
                '通常のパス例（Steam版）：<br>'
                '<span style="color: #b0ffb0;">C:\\Program Files (x86)\\Steam\\steamapps<br>'
                '\\common\\Path of Exile\\logs\\Client.txt</span></span>'
                '</div>'
            )

    def eventFilter(self, obj, event):
        """アプリ全体のマウスイベントを監視して端のリサイズを処理"""
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
            # グローバル座標 → ウィンドウ座標
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                if self.window_locked:
                    return False
                gpos = event.globalPosition().toPoint()
                edges = self._global_detect_edge(gpos)
                if edges:
                    self._ef_resize_active = True
                    self._ef_resize_edge = edges
                    self._ef_resize_start_geo = self.geometry()
                    self._ef_resize_start_pos = gpos
                    return True  # イベント消費
            
            elif event.type() == QEvent.Type.MouseMove and self._ef_resize_active:
                gpos = event.globalPosition().toPoint()
                geo = self._ef_resize_start_geo
                dx = gpos.x() - self._ef_resize_start_pos.x()
                dy = gpos.y() - self._ef_resize_start_pos.y()
                x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
                min_w, min_h = 300, getattr(self, 'MIN_HEIGHT', 400)
                
                if 'right' in self._ef_resize_edge:
                    w = max(min_w, geo.width() + dx)
                if 'bottom' in self._ef_resize_edge:
                    h = max(min_h, geo.height() + dy)
                if 'left' in self._ef_resize_edge:
                    new_w = max(min_w, geo.width() - dx)
                    x = geo.x() + geo.width() - new_w
                    w = new_w
                if 'top' in self._ef_resize_edge:
                    new_h = max(min_h, geo.height() - dy)
                    y = geo.y() + geo.height() - new_h
                    h = new_h
                
                self.setGeometry(x, y, w, h)
                return True
            
            elif event.type() == QEvent.Type.MouseButtonRelease and self._ef_resize_active:
                self._ef_resize_active = False
                self._ef_resize_edge = None
                return True
        
        return super().eventFilter(obj, event)
    
    def _global_detect_edge(self, gpos):
        """グローバル座標からリサイズ方向を検出"""
        geo = self.frameGeometry()
        m = self.EDGE_MARGIN
        edges = []
        if abs(gpos.x() - geo.left()) <= m:
            edges.append('left')
        elif abs(gpos.x() - geo.right()) <= m:
            edges.append('right')
        if abs(gpos.y() - geo.top()) <= m:
            edges.append('top')
        elif abs(gpos.y() - geo.bottom()) <= m:
            edges.append('bottom')
        return edges if edges else None

    def load_custom_font(self):
        # フォント読み込み
        import os
        from PySide6.QtGui import QFontDatabase
        
        font_path = os.path.join("assets", "fonts", "LcdSolid-VPzB.ttf")
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    return families[0]
        return None

    def _apply_bg_opacity(self, opacity_pct: int):
        """背景の透過率を適用（テキストは変えず背景のアルファ値のみ変更）"""
        alpha = int(opacity_pct / 100.0 * 255)
        # メイン背景
        self.centralWidget().setStyleSheet(
            f"#centralWidget {{ background-color: rgba(0, 0, 0, {alpha}); border-radius: 10px; }}"
        )
        # ガイドテキストフレーム
        guide_alpha = int(alpha * 0.63)  # 元: 160/255 ≈ 63%の比率を維持
        if hasattr(self, 'guide_text_frame'):
            self.guide_text_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(0, 0, 0, {guide_alpha});
                    border: 1px solid rgba(176, 255, 123, 0.2);
                    border-radius: 6px;
                }}
            """)
        # ガイドコンテナ
        container_alpha = int(alpha * 0.55)  # 元: 140/255
        if hasattr(self, 'guide_container'):
            self.guide_container.setStyleSheet(
                f"#guideContainer {{ background-color: rgba(20, 30, 20, {container_alpha}); border-radius: 6px; }}"
            )

    def _apply_timer_size(self):
        """タイマーの表示サイズを適用する"""
        sizes = self.TIMER_SIZES.get(self.timer_size, self.TIMER_SIZES["large"])
        main_px = sizes["main"]
        ms_px = sizes["ms"]
        pad = sizes["container_pad"]
        
        base_style = Styles.TIMER_LABEL
        # フォントサイズを差し替え
        base_style = re.sub(r"font-size:.*?;", f"font-size: {main_px}px;", base_style)
        if self._custom_font_family:
            base_style = re.sub(r"font-family:.*?;", f"font-family: '{self._custom_font_family}';", base_style)
        
        ms_style = Styles.TIMER_LABEL
        ms_style = re.sub(r"font-size:.*?;", f"font-size: {ms_px}px;", ms_style)
        if self._custom_font_family:
            ms_style = re.sub(r"font-family:.*?;", f"font-family: '{self._custom_font_family}';", ms_style)
        
        self.lbl_hours.setStyleSheet(base_style)
        self.lbl_c1.setStyleSheet(base_style)
        self.lbl_mins.setStyleSheet(base_style)
        self.lbl_c2.setStyleSheet(base_style)
        self.lbl_secs.setStyleSheet(base_style)
        self.lbl_ms.setStyleSheet(ms_style)
        
        # コンテナのパディング調整
        self.timer_container.layout().setContentsMargins(pad, pad, pad, pad // 2)

    def setup_ui(self):
        from PySide6.QtWidgets import QSizePolicy
        
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        central_widget.setStyleSheet(f"#centralWidget {{ background-color: {Styles.BACKGROUND_COLOR}; border-radius: 10px; }}")
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # === タイトルバー（最小化・閉じる） ===
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(5, 2, 5, 0)
        
        # クリックスルー状態表示
        self.click_through_label = QLabel("")
        self.click_through_label.setStyleSheet("color: #ff9944; font-size: 14px; font-weight: bold;")
        self.click_through_label.setVisible(False)
        title_bar.addWidget(self.click_through_label)
        title_bar.addStretch()
        
        btn_style = f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 14px; font-weight: bold;
                padding: 2px 8px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.15); border-radius: 3px; }}
        """
        close_btn_style = f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 14px; font-weight: bold;
                padding: 2px 8px;
            }}
            QPushButton:hover {{ background: rgba(255,60,60,0.8); border-radius: 3px; color: #ffffff; }}
        """
        
        minimize_btn = QPushButton("─")
        minimize_btn.setFixedSize(30, 22)
        minimize_btn.setStyleSheet(btn_style)
        minimize_btn.setToolTip("最小化")
        minimize_btn.clicked.connect(self.showMinimized)
        title_bar.addWidget(minimize_btn)
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 22)
        close_btn.setStyleSheet(close_btn_style)
        close_btn.setToolTip("閉じる")
        close_btn.clicked.connect(self.close)
        title_bar.addWidget(close_btn)
        
        layout.addLayout(title_bar)
        
        # === タイマー折りたたみトグル ===
        self.timer_expanded = self.config.get("timer_expanded", True)
        
        self.timer_toggle_btn = QPushButton("▼ タイマー" if self.timer_expanded else "▶ タイマー")
        self.timer_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 12px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.timer_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.timer_toggle_btn.clicked.connect(self.toggle_timer)
        self.timer_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        layout.addWidget(self.timer_toggle_btn)
        
        # === タイマー部分（固定高さコンテナ） ===
        self.timer_container = QWidget()
        timer_container_layout = QVBoxLayout(self.timer_container)
        timer_container_layout.setAlignment(Qt.AlignCenter)
        timer_container_layout.setContentsMargins(20, 20, 20, 10)
        
        # タイマー内の折りたたみ対象部分
        self.timer_content = QWidget()
        timer_content_layout = QVBoxLayout(self.timer_content)
        timer_content_layout.setAlignment(Qt.AlignCenter)
        timer_content_layout.setContentsMargins(0, 0, 0, 0)
        timer_content_layout.setSpacing(0)
        
        # タイマー表示 (分割)
        # ラベル分割: Hours, Colon1, Minutes, Colon2, Seconds, Milliseconds
        # 幅固定フォントではない場合のガタツキ防止策として、各数字パーツを別ラベルにする
        
        timer_layout = QHBoxLayout()
        timer_layout.setSpacing(0)
        timer_layout.setAlignment(Qt.AlignCenter)
        
        # 部品作成ヘルパー
        def create_part(text, object_name):
            lbl = QLabel(text)
            lbl.setObjectName(object_name)
            lbl.setAlignment(Qt.AlignCenter)
            return lbl
            
        self.lbl_hours = create_part("00", "time_part")
        self.lbl_c1    = create_part(":",  "colon_part")
        self.lbl_mins  = create_part("00", "time_part")
        self.lbl_c2    = create_part(":",  "colon_part")
        self.lbl_secs  = create_part("00", "time_part")
        self.lbl_ms    = create_part(".00", "ms_part") # ドット込み
        
        # フォントサイズ調整用
        # ms_partだけ小さくするスタイルは別途適用
        
        timer_layout.addWidget(self.lbl_hours)
        timer_layout.addWidget(self.lbl_c1)
        timer_layout.addWidget(self.lbl_mins)
        timer_layout.addWidget(self.lbl_c2)
        timer_layout.addWidget(self.lbl_secs)
        timer_layout.addWidget(self.lbl_ms) # Millisecondsは左詰め気味の方が良いかもしれないが一旦Center
        
        # 既存の layout.addWidget(self.timer_label) を置き換え
        timer_content_layout.addLayout(timer_layout)

        # フォント読み込みと適用
        self._custom_font_family = self.load_custom_font()
        print(f"Loaded font family: {self._custom_font_family}")
        
        # タイマーサイズ適用
        self._apply_timer_size()
        
        # === ラップタイム折りたたみトグル ===
        self.lap_expanded = self.config.get("lap_expanded", True)
        
        self.lap_toggle_btn = QPushButton("▼ ラップタイム" if self.lap_expanded else "▶ ラップタイム")
        self.lap_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 11px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.lap_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.lap_toggle_btn.clicked.connect(self.toggle_lap)
        self.lap_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        timer_content_layout.addSpacing(10)
        
        # ラップタイム行：トグルボタン + 自動/手動ボタン
        lap_header_layout = QHBoxLayout()
        lap_header_layout.setContentsMargins(0, 0, 0, 0)
        lap_header_layout.setSpacing(8)
        lap_header_layout.addWidget(self.lap_toggle_btn)
        
        self.auto_lap = self.config.get("auto_lap", True)
        self.auto_lap_btn = QPushButton("自動" if self.auto_lap else "手動")
        self.auto_lap_btn.setStyleSheet(self._auto_lap_btn_style())
        self.auto_lap_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.auto_lap_btn.clicked.connect(self.toggle_auto_lap)
        self.auto_lap_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        lap_header_layout.addWidget(self.auto_lap_btn)
        lap_header_layout.addStretch()
        timer_content_layout.addLayout(lap_header_layout)
        
        # ラップタイムリスト（折りたたみ対象）
        self.lap_content = QWidget()
        lap_content_layout = QVBoxLayout(self.lap_content)
        lap_content_layout.setContentsMargins(0, 0, 0, 0)
        lap_content_layout.setSpacing(0)
        
        self.lap_labels = []
        for i in range(10):
            lap_layout = QHBoxLayout()
            lap_layout.setSpacing(5)
            
            act_label = QLabel(f"Act {i+1}")
            act_label.setFixedWidth(80)
            time_label = QLabel("--:--.--")
            time_label.setFixedWidth(100)
            split_label = QLabel("(--:--.--)")
            split_label.setFixedWidth(100)
            
            lap_layout.addWidget(act_label)
            lap_layout.addWidget(time_label)
            lap_layout.addWidget(split_label)
            lap_layout.addStretch()
            
            lap_content_layout.addLayout(lap_layout)
            self.lap_labels.append((act_label, time_label, split_label))
        
        timer_content_layout.addWidget(self.lap_content)
        self.lap_content.setVisible(self.lap_expanded)
        
        self.update_lap_display()
        
        # timer_contentをtimer_containerに追加
        timer_container_layout.addWidget(self.timer_content)
        self.timer_content.setVisible(self.timer_expanded)
        
        # 操作ボタン（レベルガイドより上に配置）— 常に表示
        timer_container_layout.addSpacing(10)

        # 操作ボタン
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.setAlignment(Qt.AlignCenter)
        
        self.start_btn = QPushButton("Start")
        self.start_btn.setStyleSheet(Styles.BUTTON)
        self.start_btn.clicked.connect(self.start_timer)
        button_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet(Styles.BUTTON)
        self.stop_btn.clicked.connect(self.stop_timer)
        button_layout.addWidget(self.stop_btn)
        
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setStyleSheet(Styles.BUTTON)
        self.reset_btn.clicked.connect(self.reset_timer)
        button_layout.addWidget(self.reset_btn)
        
        button_layout.addStretch()
        
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setStyleSheet(Styles.BUTTON)
        self.settings_btn.setFixedSize(35, 35)
        self.settings_btn.clicked.connect(self.open_settings)
        button_layout.addWidget(self.settings_btn)
        
        timer_container_layout.addLayout(button_layout)
        
        # タイマーコンテナを固定高さで追加
        self.timer_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.timer_container)
        
        # ── レベルガイド表示（ボタンの下）──
        # ガイド部分は左右にパディング
        self.guide_container = QWidget()
        self.guide_container.setObjectName("guideContainer")
        self.guide_container.setStyleSheet("""
            #guideContainer { background-color: rgba(20, 30, 20, 140); border-radius: 6px; }
        """)
        guide_container_layout = QVBoxLayout(self.guide_container)
        guide_container_layout.setContentsMargins(20, 5, 20, 0)
        guide_container_layout.setSpacing(5)
        
        # 折りたたみトグルボタン
        self.guide_toggle_btn = QPushButton("▼ ガイド" if self.guide_expanded else "▶ ガイド")
        self.guide_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 12px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.guide_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.guide_toggle_btn.clicked.connect(self.toggle_guide)
        self.guide_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        # トグルボタンはguide_containerの外（タイマーとガイドの間）に配置
        layout.addWidget(self.guide_toggle_btn)
        
        guide_frame = QFrame()
        guide_frame.setStyleSheet(f"""
            QFrame {{
                border: 1px solid rgba(176, 255, 123, 0.3);
                border-radius: 6px;
                padding: 5px;
            }}
        """)
        guide_layout = QVBoxLayout(guide_frame)
        guide_layout.setContentsMargins(10, 5, 10, 5)
        guide_layout.setSpacing(3)
        
        # ゾーン名 + レベル表示
        zone_info_layout = QHBoxLayout()
        self.zone_label = QLabel("📍 エリア: ---")
        self.zone_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px; font-weight: bold;")
        zone_info_layout.addWidget(self.zone_label)
        
        zone_info_layout.addStretch()
        
        # Act 1-5 / Act 6-10 切替ボタン
        self.part2_btn = QPushButton("Act 6-10" if self.part2_mode else "Act 1-5")
        self.part2_btn.setStyleSheet(self._part2_btn_style())
        self.part2_btn.setFixedHeight(22)
        self.part2_btn.clicked.connect(self.toggle_part2)
        zone_info_layout.addWidget(self.part2_btn)
        
        # 訪問回数 手動切替ボタン（1回目 / 2回目）
        self.visit_btn = QPushButton("自動")
        self.visit_btn.setStyleSheet(self._visit_btn_style())
        self.visit_btn.setFixedHeight(22)
        self.visit_btn.clicked.connect(self.toggle_visit_override)
        zone_info_layout.addWidget(self.visit_btn)
        
        self.level_label = QLabel("Lv. 1")
        self.level_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px; font-weight: bold;")
        zone_info_layout.addWidget(self.level_label)
        guide_layout.addLayout(zone_info_layout)
        
        # アドバイスメッセージ
        self.advice_label = QLabel("ログ監視待機中...")
        self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
        self.advice_label.setWordWrap(True)
        guide_layout.addWidget(self.advice_label)
        
        self.guide_info_frame = guide_frame
        guide_container_layout.addWidget(self.guide_info_frame)
        
        # ── 攻略ガイド表示エリア ──
        guide_text_frame = QFrame()
        guide_text_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 160);
                border: 1px solid rgba(176, 255, 123, 0.2);
                border-radius: 6px;
            }
        """)
        guide_text_layout = QVBoxLayout(guide_text_frame)
        guide_text_layout.setContentsMargins(10, 8, 10, 8)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 6px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(176,255,123,0.3); border-radius: 3px; }
        """)
        
        self.guide_text_label = QLabel("エリアに入場すると攻略ガイドが表示されます")
        self.guide_text_label.setStyleSheet(f"color: #888888; font-size: {self.guide_font_size}px; background: transparent;")
        self.guide_text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.guide_text_label.setWordWrap(True)
        self.guide_text_label.setTextFormat(Qt.RichText)
        self.guide_text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.guide_text_label.setOpenExternalLinks(False)
        
        scroll.setWidget(self.guide_text_label)
        guide_text_layout.addWidget(scroll)
        
        self.guide_text_frame = guide_text_frame
        guide_container_layout.addWidget(self.guide_text_frame, stretch=3)
        
        # ── マップサムネイル一覧 ──
        self.map_thumbnail = MapThumbnailWidget()
        self.map_thumbnail.setVisible(False)
        guide_container_layout.addWidget(self.map_thumbnail, stretch=0)
        
        layout.addWidget(self.guide_container, stretch=1)
        
        # 初期状態の反映
        self._apply_guide_visibility()

        # リサイズグリップ（右下）
        from PySide6.QtWidgets import QSizeGrip
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(20, 20)
        self.size_grip.setStyleSheet("""
            QSizeGrip {
                background: transparent;
                border: none;
            }
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'size_grip'):
            self.size_grip.move(self.width() - 18, self.height() - 18)

    def _part2_btn_style(self):
        if self.part2_mode:
            return f"""
                QPushButton {{
                    background: rgba(176,255,123,0.2); color: {Styles.TEXT_COLOR};
                    border: 1px solid {Styles.TEXT_COLOR}; border-radius: 3px;
                    padding: 2px 8px; font-size: 10px; font-weight: bold;
                }}
                QPushButton:hover {{ background: rgba(176,255,123,0.35); }}
            """
        else:
            return f"""
                QPushButton {{
                    background: transparent; color: #888888;
                    border: 1px solid #555555; border-radius: 3px;
                    padding: 2px 8px; font-size: 10px;
                }}
                QPushButton:hover {{ color: {Styles.TEXT_COLOR}; border-color: {Styles.TEXT_COLOR}; }}
            """
    
    def _visit_btn_style(self):
        if self.visit_override is not None:
            return f"""
                QPushButton {{
                    background: rgba(255,200,50,0.25); color: #ffc832;
                    border: 1px solid #ffc832; border-radius: 3px;
                    padding: 2px 6px; font-size: 10px; font-weight: bold;
                }}
                QPushButton:hover {{ background: rgba(255,200,50,0.4); }}
            """
        else:
            return f"""
                QPushButton {{
                    background: transparent; color: #888888;
                    border: 1px solid #555555; border-radius: 3px;
                    padding: 2px 6px; font-size: 10px;
                }}
                QPushButton:hover {{ color: {Styles.TEXT_COLOR}; border-color: {Styles.TEXT_COLOR}; }}
            """

    # === 自動ラップ機能 ===
    # Act完了トリガー: {エリア名: Actラップ番号}
    AUTO_LAP_TRIGGERS = {
        "南の森": 1, "The Southern Forest": 1,
        "サーン市街": 2, "The City of Sarn": 2,
        "水道橋": 3, "The Aqueduct": 3,
        "奴隷収容所": 4, "The Slave Pens": 4,
        # Act5 = kitava_defeated シグナル (lap 5)
        "橋の野営地": 6, "The Bridge Encampment": 6,
        "サーンの城壁": 7, "The Sarn Ramparts": 7,
        "血の水道橋": 8, "The Blood Aqueduct": 8,
        "オリアスの船着場": 9, "Oriath Docks": 9,
        # Act10 = act10_cleared シグナル (lap 10)
    }

    def _auto_lap_btn_style(self):
        if self.auto_lap:
            return f"""
                QPushButton {{
                    background: rgba(100,200,255,0.25); color: #64c8ff;
                    border: 1px solid #64c8ff; border-radius: 3px;
                    padding: 2px 6px; font-size: 10px; font-weight: bold;
                }}
                QPushButton:hover {{ background: rgba(100,200,255,0.4); }}
            """
        else:
            return f"""
                QPushButton {{
                    background: transparent; color: #888888;
                    border: 1px solid #555555; border-radius: 3px;
                    padding: 2px 6px; font-size: 10px;
                }}
                QPushButton:hover {{ color: {Styles.TEXT_COLOR}; border-color: {Styles.TEXT_COLOR}; }}
            """

    def toggle_auto_lap(self):
        self.auto_lap = not self.auto_lap
        self.auto_lap_btn.setText("自動" if self.auto_lap else "手動")
        self.auto_lap_btn.setStyleSheet(self._auto_lap_btn_style())
        self.config["auto_lap"] = self.auto_lap
        ConfigManager.save_config(self.config)

    def _try_auto_lap(self, zone_name: str):
        """エリア入場時に自動ラップを試行"""
        if not self.auto_lap or not self.is_running:
            return
        lap_num = self.AUTO_LAP_TRIGGERS.get(zone_name)
        if lap_num is None:
            return
        # Act1トリガー(南の森)はAct6にも同名あるのでpart2_modeで判別
        if lap_num == 1 and self.part2_mode:
            return
        # 現在のActと一致する場合のみ記録（重複・順序ずれ防止）
        if lap_num == self.current_act:
            print(f"[AUTO-LAP] Act{lap_num}完了 — {zone_name}")
            self.record_lap()

    def _auto_lap_kitava(self, lap_num: int):
        """キタヴァ撃破による自動ラップ"""
        if not self.auto_lap or not self.is_running:
            return
        if lap_num == self.current_act:
            print(f"[AUTO-LAP] Act{lap_num}完了 — キタヴァ撃破")
            self.record_lap()

    def toggle_visit_override(self):
        """訪問回数の表示を一時的に切り替え（自動→1回目→2回目→自動）"""
        if self.visit_override is None:
            self.visit_override = 1
        elif self.visit_override == 1:
            self.visit_override = 2
        else:
            self.visit_override = None
        self._update_visit_btn()
        # 現在のゾーンのガイドを再表示
        if self.current_zone:
            zone_id = self._current_zone_id()
            visit_num = self.visit_override if self.visit_override else self.zone_visit_counts.get(zone_id or self.current_zone, 1)
            self._update_guide_and_map(self.current_zone, zone_id, visit_num)

    def _update_visit_btn(self):
        if self.visit_override is None:
            self.visit_btn.setText("自動")
        elif self.visit_override == 1:
            self.visit_btn.setText("1回目")
        else:
            self.visit_btn.setText("2回目")
        self.visit_btn.setStyleSheet(self._visit_btn_style())

    def _current_zone_id(self):
        """現在のゾーンのzone_idを返す（_get_zone_idに委譲）"""
        if not self.current_zone:
            return None
        return self._get_zone_id(self.current_zone)

    def toggle_part2(self):
        """Part 1/2を手動トグル"""
        self._set_part2(not self.part2_mode)
    
    def _set_part2(self, enabled: bool):
        """Part 2モードの切り替え"""
        if self.part2_mode == enabled:
            return
        self.part2_mode = enabled
        self.config["part2_mode"] = enabled
        ConfigManager.save_config(self.config)
        self.part2_btn.setText("Act 6-10" if enabled else "Act 1-5")
        self.part2_btn.setStyleSheet(self._part2_btn_style())
        # 現在のゾーンを再評価
        if self.current_zone:
            self.on_zone_entered(self.current_zone)
    
    def toggle_timer(self):
        """タイマー+ラップ表示の折りたたみ/展開"""
        self.timer_expanded = not self.timer_expanded
        self.timer_content.setVisible(self.timer_expanded)
        self.timer_toggle_btn.setText("▼ タイマー" if self.timer_expanded else "▶ タイマー")
        self.config["timer_expanded"] = self.timer_expanded
        ConfigManager.save_config(self.config)
    
    def toggle_lap(self):
        """ラップタイム表示の折りたたみ/展開"""
        self.lap_expanded = not self.lap_expanded
        self.lap_content.setVisible(self.lap_expanded)
        self.lap_toggle_btn.setText("▼ ラップタイム" if self.lap_expanded else "▶ ラップタイム")
        self.config["lap_expanded"] = self.lap_expanded
        ConfigManager.save_config(self.config)
    
    def toggle_guide(self):
        """ガイドエリアの折りたたみ/展開をトグル"""
        self.guide_expanded = not self.guide_expanded
        self._apply_guide_visibility()
        # config保存
        self.config["guide_expanded"] = self.guide_expanded
        ConfigManager.save_config(self.config)
    
    def _apply_guide_visibility(self):
        """ガイドの表示/非表示を適用"""
        self.guide_info_frame.setVisible(self.guide_expanded)
        self.guide_text_frame.setVisible(self.guide_expanded)
        self.map_thumbnail.setVisible(self.guide_expanded and len(self.map_thumbnail.current_paths) > 0)
        # 背景も連動
        if self.guide_expanded:
            self.guide_container.setStyleSheet("""
                #guideContainer { background-color: rgba(20, 30, 20, 140); border-radius: 6px; }
            """)
        else:
            self.guide_container.setStyleSheet("""
                #guideContainer { background-color: transparent; }
            """)
        self.guide_toggle_btn.setText("▼ ガイド" if self.guide_expanded else "▶ ガイド")
    
    def start_timer(self):
        if not self.is_running:
            self.start_time = time.time()
            self.timer.start(10)
            self.is_running = True
            
    def stop_timer(self):
        if self.is_running:
            self.timer.stop()
            self.accumulated_time += time.time() - self.start_time
            self.is_running = False
            self._save_timer_state()
            
    def reset_timer(self):
        # 確認ダイアログ（設定ON かつ タイマーが動いているか記録がある場合）
        if self.config.get("confirm_reset", True):
            has_data = self.accumulated_time > 0 or self.is_running or any(t is not None for t in self.lap_times)
            if has_data:
                msg = QMessageBox(self)
                msg.setStyleSheet("QMessageBox { font-size: 14px; } QMessageBox QLabel { font-size: 14px; }")
                msg.setWindowTitle("リセット確認")
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setText("タイマーとラップをリセットしますか？")
                msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg.setDefaultButton(QMessageBox.StandardButton.No)
                if msg.exec() != QMessageBox.StandardButton.Yes:
                    return
        
        # ラップ記録があれば保存
        if any(t is not None for t in self.lap_times):
            total = self.get_elapsed_time()
            LapRecorder.save_run(self.lap_times, total)
        
        self.stop_timer()
        self.accumulated_time = 0.0
        self.update_text(0.0)
        self.reset_laps()
        self._clear_saved_timer()
    
    def reset_laps(self):
        """全ラップをリセット"""
        self.lap_times = [None] * 10
        self.current_act = 1
        self.update_lap_display()
        # Part 1に戻す
        self._set_part2(False)
        # 訪問回数リセット
        self.zone_visit_counts = {}
        self.visit_override = None
        self._update_visit_btn()
        # マップクリア
        self.map_thumbnail.clear()
    
    def get_elapsed_time(self):
        """現在の経過時間を取得"""
        if self.is_running:
            return self.accumulated_time + (time.time() - self.start_time)
        return self.accumulated_time
    
    def _save_timer_state(self):
        """タイマー状態をconfig.jsonに保存"""
        self.config["saved_timer"] = {
            "accumulated_time": self.accumulated_time,
            "lap_times": self.lap_times,
            "current_act": self.current_act,
        }
        ConfigManager.save_config(self.config)
        print(f"[INFO] タイマー状態を保存しました (経過: {self.accumulated_time:.1f}秒, Act{self.current_act})")
    
    def _clear_saved_timer(self):
        """保存済みタイマー状態をクリア"""
        if "saved_timer" in self.config:
            del self.config["saved_timer"]
            ConfigManager.save_config(self.config)
    
    def _restore_timer_state(self):
        """起動時に保存済みタイマー状態を復元"""
        saved = self.config.get("saved_timer")
        if not saved:
            return
        self.accumulated_time = saved.get("accumulated_time", 0.0)
        self.lap_times = saved.get("lap_times", [None] * 10)
        self.current_act = saved.get("current_act", 1)
        if self.accumulated_time > 0:
            self.update_text(self.accumulated_time)
            self.update_lap_display()
            # part2_modeも復元（Act6以降ならpart2）
            if self.current_act > 5:
                self._set_part2(True)
            print(f"[INFO] タイマー状態を復元しました (経過: {self.accumulated_time:.1f}秒, Act{self.current_act})")
    
    def record_lap(self):
        """現在のActのラップを記録"""
        if self.current_act > 10:
            return
        
        elapsed = self.get_elapsed_time()
        self.lap_times[self.current_act - 1] = elapsed
        
        if self.current_act < 10:
            self.current_act += 1
        else:
            # Act 10完了時に自動保存
            LapRecorder.save_run(self.lap_times, elapsed)
        
        self.update_lap_display()
    
    def undo_lap(self):
        """直前のラップを取り消し"""
        if self.current_act > 1 and self.lap_times[self.current_act - 2] is not None:
            self.lap_times[self.current_act - 2] = None
            self.current_act -= 1
            self.update_lap_display()
        elif self.current_act == 1 and self.lap_times[0] is not None:
            self.lap_times[0] = None
            self.update_lap_display()
    
    def format_lap_time(self, seconds):
        """ラップタイムをフォーマット"""
        if seconds is None:
            return "--:--.--"
        
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        cs = int((seconds * 100) % 100)
        
        if hours > 0:
            return f"{hours}:{mins:02d}:{secs:02d}.{cs:02d}"
        else:
            return f"{mins:02d}:{secs:02d}.{cs:02d}"
    
    def update_lap_display(self):
        """ラップタイム表示を更新"""
        for i, (act_lbl, time_lbl, split_lbl) in enumerate(self.lap_labels):
            act_num = i + 1
            lap_time = self.lap_times[i]
            
            # スプリットタイム計算（前のActとの差分）
            if lap_time is not None:
                if i == 0:
                    split_time = lap_time
                else:
                    prev_time = self.lap_times[i - 1]
                    split_time = lap_time - prev_time if prev_time else lap_time
            else:
                split_time = None
            
            if lap_time is not None:
                # 完了済み
                act_lbl.setText(f"Act {act_num}")
                time_lbl.setText(self.format_lap_time(lap_time))
                split_lbl.setText(f"({self.format_lap_time(split_time)})")
                act_lbl.setStyleSheet(Styles.LAP_ITEM_COMPLETED)
                time_lbl.setStyleSheet(Styles.LAP_ITEM_COMPLETED)
                split_lbl.setStyleSheet(Styles.LAP_ITEM_COMPLETED)
            elif act_num == self.current_act:
                # 現在進行中
                act_lbl.setText(f"⇒ Act {act_num}")
                time_lbl.setText("進行中...")
                split_lbl.setText("")
                act_lbl.setStyleSheet(Styles.LAP_ITEM_CURRENT)
                time_lbl.setStyleSheet(Styles.LAP_ITEM_CURRENT)
                split_lbl.setStyleSheet(Styles.LAP_ITEM_CURRENT)
            else:
                # 未到達
                act_lbl.setText(f"Act {act_num}")
                time_lbl.setText("--:--.--")
                split_lbl.setText("")
                act_lbl.setStyleSheet(Styles.LAP_ITEM_PENDING)
                time_lbl.setStyleSheet(Styles.LAP_ITEM_PENDING)
                split_lbl.setStyleSheet(Styles.LAP_ITEM_PENDING)

    def update_display(self):
        current_time = time.time()
        elapsed = self.accumulated_time + (current_time - self.start_time)
        self.update_text(elapsed)

    def update_text(self, elapsed_seconds):
        minutes = int(elapsed_seconds // 60)
        seconds = int(elapsed_seconds % 60)
        centiseconds = int((elapsed_seconds * 100) % 100)
        
        hours = int(minutes // 60)
        minutes = minutes % 60
        
        # 各パーツを更新
        self.lbl_hours.setText(f"{hours:02d}")
        self.lbl_mins.setText(f"{minutes:02d}")
        self.lbl_secs.setText(f"{seconds:02d}")
        self.lbl_ms.setText(f".{centiseconds:02d}")
        
        # Colonは固定なので更新不要

    # --- ホットキー処理 ---
    def register_hotkeys(self):
        """pynputを使用してグローバルホットキーを登録"""
        try:
            # 既存のリスナーを停止
            if self.keyboard_listener:
                self.keyboard_listener.stop()
                self.keyboard_listener = None
            
            hotkeys = self.config.get("hotkeys", {})
            
            self.hotkey_map = {
                hotkeys.get("start_stop", "F1").lower(): "start_stop",
                hotkeys.get("reset", "F2").lower(): "reset",
                hotkeys.get("lap", "F3").lower(): "lap",
                hotkeys.get("undo_lap", "F4").lower(): "undo_lap",
                hotkeys.get("click_through", "F6").lower(): "click_through",
            }
            
            print(f"Registering hotkeys: {self.hotkey_map}")
            
            def on_press(key):
                try:
                    # キー名を取得
                    if hasattr(key, 'name'):
                        key_name = key.name.lower()
                    elif hasattr(key, 'char') and key.char:
                        key_name = key.char.lower()
                    else:
                        return
                    
                    # ホットキーマップをチェック
                    if key_name in self.hotkey_map:
                        command = self.hotkey_map[key_name]
                        self.hotkey_signal.emit(command)
                except Exception as e:
                    print(f"Hotkey error: {e}")
            
            self.keyboard_listener = pynput_keyboard.Listener(on_press=on_press)
            self.keyboard_listener.start()
            
        except Exception as e:
            print(f"Failed to register hotkeys: {e}")

    def handle_hotkey(self, command):
        if command == "start_stop":
            if self.is_running:
                self.stop_timer()
            else:
                self.start_timer()
        elif command == "reset":
            self.reset_timer()
        elif command == "lap":
            self.record_lap()
        elif command == "undo_lap":
            self.undo_lap()
        elif command == "click_through":
            self.toggle_click_through()

    # --- クリックスルー ---
    def toggle_click_through(self):
        """クリックスルーのON/OFF切替"""
        self.click_through = not getattr(self, 'click_through', False)
        if sys.platform == 'win32':
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if self.click_through:
                style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
            else:
                style &= ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            # フラグ変更を即座に反映
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        
        # 視覚的フィードバック
        hotkey = self.config.get('hotkeys', {}).get('click_through', 'F6')
        if self.click_through:
            self.click_through_label.setText(f"🔓 クリックスルーON（{hotkey}で解除）")
            self.click_through_label.setVisible(True)
            print(f"[INFO] クリックスルー ON（{hotkey}で解除）")
        else:
            self.click_through_label.setVisible(False)
            print("[INFO] クリックスルー OFF")

    # --- レベルガイド ---
    def _is_town_zone(self, zone_name: str) -> bool:
        """街エリアかどうか判定"""
        town_zones = self.config.get("town_zones", [
            "Lioneye's Watch", "ライオンアイの見張り場",
            "The Forest Encampment", "森のキャンプ地",
            "The Sarn Encampment", "サーンのキャンプ地",
            "Highgate", "ハイゲート",
            "Overseer's Tower", "監督官の塔",
            "The Bridge Encampment", "橋のたもとのキャンプ地",
            "The Harbour Bridge", "港の橋",
            "Oriath", "オリアス",
            "Karui Shores", "カルイの浜辺",
        ])
        return zone_name in town_zones
    
    def _get_zone_id(self, zone_name: str) -> str | None:
        """zone_dataからエリア名でIDを検索。part2_modeに応じてAct6-10/Act1-5を優先"""
        # Act10フラグが立っている場合、志す者の広場はAct10を優先
        if getattr(self, '_in_act10', False) and zone_name in ("志す者の広場", "Aspirants' Plaza"):
            for z in self.zone_data.get("Act 10", []):
                if z["zone"] == zone_name:
                    return z.get("id")
        
        if self.part2_mode:
            search_order = [k for k in self.zone_data if k in ("Act 6","Act 7","Act 8","Act 9","Act 10")]
            search_order += [k for k in self.zone_data if k not in search_order]
        else:
            search_order = [k for k in self.zone_data if k in ("Act 1","Act 2","Act 3","Act 4","Act 5")]
            search_order += [k for k in self.zone_data if k not in search_order]
        
        for act_name in search_order:
            for z in self.zone_data.get(act_name, []):
                if z["zone"] == zone_name or z.get("zone_en") == zone_name:
                    return z.get("id")
        return None
    
    def on_zone_entered(self, zone_name: str):
        """エリア入場検知"""
        # 街エリアの場合はゾーン名表示のみ更新、ガイド・マップは前のまま維持
        # （visit_overrideもリセットしない — 街を挟んでも手動切替を維持）
        if self._is_town_zone(zone_name):
            act_range = "Act 6-10" if self.part2_mode else "Act 1-5"
            self.zone_label.setText(f"🏠 {zone_name} [{act_range}]")
            # Labクリア後の街帰還 → 志す者の広場の2回目ガイドを表示
            if self._in_lab and self._lab_zone_id:
                self._in_lab = False
                self.advice_label.setText("🏛️ Labクリア — 次のガイドを表示中")
                self.advice_label.setStyleSheet("color: #ffc832; font-size: 12px;")
                # 志す者の広場のvisitカウントを増やす
                self.zone_visit_counts[self._lab_zone_id] = self.zone_visit_counts.get(self._lab_zone_id, 1) + 1
                visit_num = self.zone_visit_counts[self._lab_zone_id]
                lab_zone_name = zone_name  # 日本語/英語どちらでも対応
                self._update_guide_and_map(lab_zone_name, self._lab_zone_id, visit_num)
                self._lab_zone_id = None
            else:
                self.advice_label.setText("（街エリア — ガイドは前のエリアを表示中）")
                self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
            return
        
        # 訪問回数オーバーライドをリセット（街以外のゾーン移動で自動に戻る）
        if self.visit_override is not None:
            self.visit_override = None
            self._update_visit_btn()
        
        # 荒廃した広場(Act10固有)入場 → Act10フラグON
        if zone_name in ("荒廃した広場", "The Ravaged Square") and not self._restoring:
            self._in_act10 = True
        
        # 黄昏の岸辺入場 → 新キャラ判定フラグON（Lv2検知でリセット確定）
        if zone_name in ("黄昏の岸辺", "The Twilight Strand") and not self._restoring:
            self._twilight_strand_entered = True
        
        # C: Part2固有エリアに入場 → 自動切替
        if not self.part2_mode and zone_name in self.part2_only_zones:
            self._set_part2(True)
        
        # zone_id検索
        zone_id = self._get_zone_id(zone_name)
        
        # Lab処理: 志す者の広場に入場 → Labフラグ設定
        _lab_zone_ids = {"act4_area3", "act8_area2", "act10_area8"}
        if zone_id in _lab_zone_ids and not self._restoring:
            self._in_lab = True
            self._lab_zone_id = zone_id
        elif self._in_lab and zone_id and zone_id not in _lab_zone_ids:
            # Lab中に既知の別エリアに入った → Labフラグ解除
            self._in_lab = False
            self._lab_zone_id = None
        elif self._in_lab and not zone_id:
            # Lab中に未知のエリア（Lab内部）→ ガイド更新スキップ
            self.zone_label.setText(f"📍 {zone_name}")
            self.advice_label.setText("🏛️ Lab — ガイドは前のエリアを表示中")
            self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
            return
        
        # monster_levels.jsonからデータ取得
        monster_info = self.monster_levels.get(zone_id) if zone_id else None
        
        # monster_levels.jsonのexcludeチェック
        if monster_info and "exclude" in monster_info:
            exclude_type = monster_info["exclude"]
            if exclude_type == "town":
                # 街扱い — 既存の街処理と同じ
                act_range = "Act 6-10" if self.part2_mode else "Act 1-5"
                self.zone_label.setText(f"🏠 {zone_name} [{act_range}]")
                self.advice_label.setText("（街エリア — ガイドは前のエリアを表示中）")
                self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
                return
            elif exclude_type == "boss":
                # ボスエリア — ペナルティ判定スキップ
                self.current_zone = zone_name
                act_name, _ = get_zone_info(self.zone_data, zone_name, part2=self.part2_mode)
                act_prefix = f"{act_name} — " if act_name else ""
                self.zone_label.setText(f"📍 {act_prefix}{zone_name}")
                self.advice_label.setText("⚔️ ボスエリア")
                self.advice_label.setStyleSheet("color: #ff9944; font-size: 12px;")
                # ガイド・マップ更新は続行
                self._update_guide_and_map(zone_name, zone_id, 1)
                return
            elif exclude_type == "non_combat":
                # 非戦闘エリア — ペナルティ判定スキップ
                self.current_zone = zone_name
                act_name, _ = get_zone_info(self.zone_data, zone_name, part2=self.part2_mode)
                act_prefix = f"{act_name} — " if act_name else ""
                self.zone_label.setText(f"📍 {act_prefix}{zone_name}")
                self.advice_label.setText("🏛️ 非戦闘エリア")
                self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
                self._update_guide_and_map(zone_name, zone_id, 1)
                return
        
        # 訪問回数カウント（zone_id基準）
        visit_key = zone_id if zone_id else zone_name
        last_visit_key = getattr(self, '_last_visit_key', None)
        # 街を挟んでも常にカウントするエリア（ポータルで街に戻って再入場するパターン）
        always_count_zones = {"act5_area5", "act10_area3"}  # イノセンスの間, 荒廃した広場
        if self._restoring:
            # 復元時はカウントしないが、last_visit_keyは設定（重複防止）
            self._last_visit_key = visit_key
            visit_num = 1
        else:
            # 同じエリアに連続入場はカウントしない（ログ重複対策）— 特殊エリアは常にカウント
            if visit_key != last_visit_key or visit_key in always_count_zones:
                self.zone_visit_counts[visit_key] = self.zone_visit_counts.get(visit_key, 0) + 1
            self._last_visit_key = visit_key
            visit_num = self.zone_visit_counts.get(visit_key, 1)
        print(f"[DEBUG] zone={zone_name}, id={zone_id}, visit_num={visit_num}, restoring={self._restoring}, counts={self.zone_visit_counts}")
        
        self.current_zone = zone_name
        # 自動ラップ判定（復元中は除外）
        if not self._restoring:
            self._try_auto_lap(zone_name)
        act_name, zone_level = get_zone_info(self.zone_data, zone_name, part2=self.part2_mode)
        
        # monster_levels.jsonからモンスターレベルを取得（優先）
        monster_lv = None
        if monster_info and monster_info.get("lv", 0) > 0 and "exclude" not in monster_info:
            monster_lv = monster_info["lv"]
        
        # 2回目以降はガイドデータ内の適正レベル上書きをチェック
        if visit_num >= 2 and zone_id:
            v_key = f"{zone_id}@{visit_num}"
            v_guide = self.guide_data.get(v_key, {})
            if v_guide.get("level"):
                zone_level = v_guide["level"]
                # ガイドデータにレベル上書きがある場合はそちらを優先
                monster_lv = v_guide["level"]
        
        # 表示用レベル決定: monster_levels優先、なければzone_data
        display_lv = monster_lv if monster_lv else zone_level
        
        if act_name and display_lv:
            visit_label = ""
            lv_prefix = "MLv" if monster_lv else "Lv"
            self.zone_label.setText(f"📍 {act_name} — {zone_name} ({lv_prefix}.{display_lv}){visit_label}")
            msg, color = get_level_advice(self.player_level, display_lv)
            self.advice_label.setText(msg)
            self.advice_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        else:
            self.zone_label.setText(f"📍 {zone_name}")
            self.advice_label.setText("（適正レベル未登録エリア）")
            self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
        
        # 攻略ガイド・マップ更新
        self._update_guide_and_map(zone_name, zone_id, visit_num, zone_changed=True)
    
    def _update_guide_and_map(self, zone_name: str, zone_id: str | None, visit_num: int, zone_changed: bool = False):
        """攻略ガイドとマップ画像を更新"""
        # 訪問回数オーバーライド適用
        effective_visit = self.visit_override if self.visit_override is not None else visit_num
        if zone_id:
            guide = get_zone_guide(self.guide_data, zone_id, visit=effective_visit)
        else:
            guide = None
        
        if guide:
            html = format_guide_html(guide, font_size=self.guide_font_size)
            self.guide_text_label.setText(html)
            self.guide_text_label.setStyleSheet(f"color: #dddddd; font-size: {self.guide_font_size}px; background: transparent;")
        else:
            self.guide_text_label.setText(f"「{zone_name}」のガイドデータはありません")
            self.guide_text_label.setStyleSheet(f"color: #666666; font-size: {self.guide_font_size}px; background: transparent;")
        
        # マップ画像は日本語フォルダ名で検索（英語クライアント対応）
        map_zone_name = zone_name
        if zone_id:
            for act_zones in self.zone_data.values():
                for z in act_zones:
                    if z.get("id") == zone_id:
                        map_zone_name = z["zone"]  # 日本語名
                        break
        self.map_thumbnail.load_maps(map_zone_name, part2=self.part2_mode, zone_changed=zone_changed)
    
    def on_kitava_defeated(self):
        """Act5キタヴァ討伐 → Act6-10に切替 + 自動ラップ"""
        if not self.part2_mode:
            print("[INFO] キタヴァ討伐を検知 — Act 6-10に切替")
            self._set_part2(True)
        self._auto_lap_kitava(5)
    
    def on_act10_cleared(self):
        """Act10キタヴァ討伐 → クリアメッセージ表示 + 自動ラップ"""
        self._auto_lap_kitava(10)
        print("[INFO] Act10キタヴァ討伐を検知 — クリアメッセージ表示")
        clear_html = (
            '<div style="text-align: center; padding: 20px;">'
            '<span style="font-size: 24px; color: #ffd700;">🎉</span><br>'
            '<span style="font-size: 18px; color: #ffd700; font-weight: bold;">'
            'Act10クリア！</span><br><br>'
            '<span style="font-size: 16px; color: #e0e0e0;">'
            'お疲れ様でした！</span><br><br>'
            '<span style="font-size: 13px; color: #b0ffb0;">'
            'チャットコマンドに「/passives」を入力して、パッシブポイントの取り忘れがないかチェックしましょう。<br>'
            'Act2のバンディットクエストで全員倒していれば24pt、それ以外は23ptになっていればOK</span>'
            '</div>'
        )
        self.guide_text_label.setText(clear_html)
        self.guide_text_label.setStyleSheet(
            f"color: #e0e0e0; font-size: {self.guide_font_size}px; background: transparent;"
        )
        # マップサムネイルをクリア
        self.map_thumbnail.load_maps("", part2=False)

    def on_level_up(self, char_name: str, level: int):
        """レベルアップ検知"""
        self.player_level = level
        self.level_label.setText(f"Lv. {level}")
        
        # 新キャラ判定: 黄昏の岸辺入場済み + Lv2 = ヒロック討伐 → visitカウントリセット
        if level == 2 and getattr(self, '_twilight_strand_entered', False):
            print("[INFO] 新キャラ確定（黄昏の岸辺 + Lv2）— visitカウントをリセット")
            self.zone_visit_counts = {}
            self._last_visit_key = None
            self._twilight_strand_entered = False
            self.visit_override = None
            self._update_visit_btn()
            self._in_act10 = False
            self._set_part2(False)  # Act 1-5に戻す
        
        # 現在のゾーン情報があれば再評価
        if self.current_zone:
            self.on_zone_entered(self.current_zone)
    
    def update_level_guide_display(self):
        """レベルガイド表示を更新"""
        if self.current_zone:
            self.on_zone_entered(self.current_zone)
    
    # --- ウィンドウ移動 & 下端リサイズ ---
    MIN_HEIGHT = 400
    
    def _detect_edge(self, pos):
        """マウス位置からリサイズ方向を検出"""
        m = self.EDGE_MARGIN
        edges = []
        if pos.x() <= m:
            edges.append('left')
        elif pos.x() >= self.width() - m:
            edges.append('right')
        if pos.y() <= m:
            edges.append('top')
        elif pos.y() >= self.height() - m:
            edges.append('bottom')
        return edges if edges else None

    def _edge_cursor(self, edges):
        if not edges:
            return Qt.ArrowCursor
        s = set(edges)
        if s == {'left'} or s == {'right'}:
            return Qt.SizeHorCursor
        if s == {'top'} or s == {'bottom'}:
            return Qt.SizeVerCursor
        if s == {'left', 'top'} or s == {'right', 'bottom'}:
            return Qt.SizeFDiagCursor
        if s == {'right', 'top'} or s == {'left', 'bottom'}:
            return Qt.SizeBDiagCursor
        return Qt.ArrowCursor

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.window_locked:
                event.accept()
                return
            edges = self._detect_edge(event.position().toPoint())
            if edges:
                self.resize_edge = edges
                self.resize_start_geo = self.geometry()
                self.resize_start_pos = event.globalPosition().toPoint()
            else:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.resize_edge and self.resize_start_geo:
            gpos = event.globalPosition().toPoint()
            dx = gpos.x() - self.resize_start_pos.x()
            dy = gpos.y() - self.resize_start_pos.y()
            geo = self.resize_start_geo
            x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
            min_w = 300
            min_h = self.MIN_HEIGHT if hasattr(self, 'MIN_HEIGHT') else 400
            
            if 'right' in self.resize_edge:
                w = max(min_w, geo.width() + dx)
            if 'bottom' in self.resize_edge:
                h = max(min_h, geo.height() + dy)
            if 'left' in self.resize_edge:
                new_w = max(min_w, geo.width() - dx)
                x = geo.x() + geo.width() - new_w
                w = new_w
            if 'top' in self.resize_edge:
                new_h = max(min_h, geo.height() - dy)
                y = geo.y() + geo.height() - new_h
                h = new_h
            
            self.setGeometry(x, y, w, h)
            event.accept()
        elif event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
        else:
            if not self.window_locked:
                edges = self._detect_edge(event.position().toPoint())
                self.setCursor(QCursor(self._edge_cursor(edges)))

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        self.resize_edge = None
        self.resize_start_geo = None
        self.resize_start_pos = None
        self.setCursor(QCursor(Qt.ArrowCursor))

    # --- コンテキストメニュー ---
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        settings_action = menu.addAction("設定")
        settings_action.triggered.connect(self.open_settings)
        
        menu.addSeparator()
        
        quit_action = menu.addAction("終了")
        quit_action.triggered.connect(self.close)
        
        menu.exec(event.globalPos())

    def open_settings(self):
        dialog = SettingsDialog(self, self.config)
        if dialog.exec():
            # 設定保存
            new_settings = dialog.get_settings()
            self.config.update(new_settings)
            ConfigManager.save_config(self.config)
            
            # ホットキー再登録
            self.register_hotkeys()
            
            # ログ監視の再設定
            log_path = self.config.get("client_log_path", "")
            if log_path:
                self.log_watcher.set_log_path(log_path)
                self.log_watcher.start()
                # 初回セットアップ完了フラグ
                if not self.config.get("setup_completed"):
                    self.config["setup_completed"] = True
                    ConfigManager.save_config(self.config)
                # ログファイル未設定メッセージをクリア
                self.guide_text_label.setText("")
            
            # ゾーンデータ・ガイドデータ更新
            self.zone_data = self.config.get("zone_data", DEFAULT_ZONE_DATA)
            
            # ガイドフォントサイズ更新
            self.guide_font_size = self.config.get("guide_font_size", 18)
            
            # タイマーサイズ更新
            new_timer_size = self.config.get("timer_size", "large")
            if new_timer_size != self.timer_size:
                self.timer_size = new_timer_size
                self._apply_timer_size()
            
            # ウィンドウロック更新
            self.window_locked = self.config.get("window_locked", False)
            # マップ自動表示更新
            self.map_thumbnail.auto_open = self.config.get("auto_open_map", False)
            self.map_thumbnail.auto_position = self.config.get("auto_position_map", True)
            # 透過率更新
            self._apply_bg_opacity(self.config.get("window_opacity", 100))
            
            self.update_level_guide_display()
        
        # ガイドデータは常にリロード（ガイド編集Saveで即保存されるため、Cancelでも反映する）
        self.guide_data = load_guide_data()
        # 現在表示中のガイドを再描画
        if self.current_zone:
            zone_id = self._get_zone_id(self.current_zone)
            visit_num = self.zone_visit_counts.get(self.current_zone, 1)
            self._update_guide_and_map(self.current_zone, zone_id, visit_num)
            
    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_positioned:
            self._initial_positioned = True
            from PySide6.QtWidgets import QApplication
            screens = QApplication.screens()
            idx = self._display_monitor_index
            if screens and 0 <= idx < len(screens):
                target_screen = screens[idx]
            elif screens:
                target_screen = screens[0]
            else:
                return
            geo = target_screen.availableGeometry()
            actual_w = self.frameGeometry().width()
            win_h = geo.height()
            self.resize(self.width(), win_h)
            x = geo.left() + geo.width() - actual_w
            y = geo.top()
            self.move(x, y)

    def closeEvent(self, event):
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        self.log_watcher.stop()
        super().closeEvent(event)
