import json
import os
import re
import sys
import time
from pynput import keyboard as pynput_keyboard
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QPushButton, QMenu, QFrame, QScrollArea, QSplitter,
                               QSizeGrip, QSizePolicy, QMessageBox, QRadioButton, QButtonGroup, QApplication,
                               QToolTip)
from PySide6.QtCore import Qt, QTimer, Signal, QRect, QEvent, QEventLoop, QPoint, QSize, QMimeData, QUrl
from PySide6.QtGui import QCursor, QMouseEvent, QIcon, QDesktopServices, QKeySequence
from src.ui.styles import Styles
from src.ui.detached_panel import DetachedPanelWindow
from src.ui.settings_dialog import AreaNoteDialog, SettingsDialog
from src.ui.map_viewer import MapThumbnailWidget
from src.utils.config_manager import ConfigManager
from src.utils.lap_recorder import LapRecorder
from src.utils.segment_recorder import SegmentRecorder
from src.utils.log_watcher import LogWatcher
from src.utils.window_focus import (
    get_foreground_window,
    focus_window,
    get_next_visible_window_after,
    is_path_of_exile_window,
)
from src.utils.log_path_detector import fill_missing_client_log_paths
from src.utils.performance_metrics import measure
from src.utils.zone_lookup import get_zone_info, get_level_advice
from src.utils.guide_data import load_guide_data, get_zone_guide, get_zone_guide_level, format_guide_html, get_mini_navi_content
from src.utils.poe_version_data import POE1, POE2, get_lap_labels, get_poe_label, get_timer_filename, get_progress_flags_filename
from src.utils.zone_master_data import load_zone_master_data
from src.utils.poe_progress_data import get_auto_lap_triggers, get_clear_message, get_special_lap_event
from src.utils.pob_importer import import_pob, get_pob_skill_sets
from src.utils.gem_resolver import load_gem_names_ja, resolve_gem_acquisition
from src.utils.gem_shop_search import (
    HoldTrigger,
    build_act_vendor_gem_query,
    format_gem_shop_search_preview,
    get_gem_shop_search_feedback,
)
from src.utils.poelab_links import POELAB_HOME, find_daily_notes_url
from src.utils.area_notes import get_area_note, set_area_note
from src.ui.gem_tracker_widget import GemTrackerWidget, PoBImportDialog, PoBSkillSetSelectionDialog
from src.ui.update_dialogs import UpdateAvailableDialog, UpdateProgressDialog
from src.update.qt_controller import UpdateController
from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout

from src.ui.startup_dialogs import (
    GuideDetailLevelSelectionDialog,
    PoeVersionSelectionDialog,
    RouteSelectionDialog,
)
from src.ui.memo_dialog import MemoDialog
from src.ui.mini_navi import MiniNaviOverlay
from src.ui.search_paste_dialog import SearchStringPasteTestDialog
from src.ui.window_flags import (
    _is_always_on_top_enabled,
    _is_mini_always_on_top_enabled,
    _with_optional_always_on_top,
    _with_optional_mini_always_on_top,
)

from src.ui.vendor_search_dialog import VendorSearchPresetDialog

DEFAULT_CLICK_THROUGH_HOTKEY = "F6"


def _listener_hotkey_name(key_text: str) -> str:
    """設定画面の表記をpynputのキー名表記へ揃える。"""
    return str(key_text).lower().replace("capslock", "caps_lock")


def _hotkey_key_name(key) -> str | None:
    """pynputのキーイベントを設定値と比較できる名前へ正規化する。"""
    if hasattr(key, "name") and key.name:
        return key.name.lower()

    char = getattr(key, "char", None)
    if char and char.isprintable():
        return char.lower()

    # WindowsではCtrl+A～Zが制御文字(\x01～\x1a)として届く。
    # vkが取れる場合は物理キー名へ戻し、Ctrl+D等も設定可能にする。
    vk = getattr(key, "vk", None)
    if isinstance(vk, int):
        if ord("A") <= vk <= ord("Z"):
            return chr(vk).lower()
        if ord("0") <= vk <= ord("9"):
            return chr(vk)

    if char and len(char) == 1 and 1 <= ord(char) <= 26:
        return chr(ord("a") + ord(char) - 1)
    return None


class MainWindow(QMainWindow):
    # Qt may call an overridden showEvent from QMainWindow.__init__ before
    # this class' __init__ body can initialize instance attributes.
    _initial_positioned = False
    _pending_initial_map_auto_open = False
    _main_window_initialized = False

    POELAB_ZONE_TYPES = {
        "act4_area3": "normal",
        "act8_area2": "cruel",
        "act10_area8": "merciless",
    }

    # ホットキーイベントをメインスレッドで処理するためのシグナル
    hotkey_signal = Signal(str)
    poelab_url_resolved = Signal(str)
    poelab_url_failed = Signal(str)

    def _detached_panel_config(self, panel_id: str) -> dict:
        panels = self.config.setdefault("detached_panels", {})
        return panels.setdefault(panel_id, {"detached": False})

    def _is_panel_detached(self, panel_id: str) -> bool:
        return panel_id in getattr(self, "detached_panel_windows", {})

    def _save_detached_panel_state(self, panel_id: str, persist: bool = True):
        state = self._detached_panel_config(panel_id)
        panel_window = self.detached_panel_windows.get(panel_id)
        state["detached"] = panel_window is not None
        if panel_window is not None:
            geometry = panel_window.geometry()
            state.update({
                "x": geometry.x(),
                "y": geometry.y(),
                "width": geometry.width(),
                "height": geometry.height(),
            })
        if persist:
            ConfigManager.save_config(self.config)
            return
        if not getattr(self, "_detached_state_save_scheduled", False):
            self._detached_state_save_scheduled = True
            QTimer.singleShot(250, self._flush_detached_panel_state)

    def _flush_detached_panel_state(self):
        self._detached_state_save_scheduled = False
        ConfigManager.save_config(self.config)

    def _detach_guide_lower_section(self):
        """ガイドを外す際、マップ／ジェム領域は本体に残す。"""
        if getattr(self, "_guide_lower_in_main", False):
            return

        lower_section = self.guide_lower_widget
        self._guide_lower_splitter_sizes = self.guide_body_splitter.sizes()
        lower_section.setParent(None)
        guide_record = self.panel_registry["guide"]
        guide_record["layout"].insertWidget(guide_record["index"] + 1, lower_section, 1)
        self._guide_lower_in_main = True

    def _restore_guide_lower_section(self):
        """本体へ戻したガイドへ、下部領域を元のSplitter位置で戻す。"""
        if not getattr(self, "_guide_lower_in_main", False):
            return

        lower_section = self.guide_lower_widget
        self.panel_registry["guide"]["layout"].removeWidget(lower_section)
        lower_section.setParent(None)
        self.guide_body_splitter.insertWidget(1, lower_section)
        sizes = getattr(self, "_guide_lower_splitter_sizes", None)
        if isinstance(sizes, list) and len(sizes) == 2:
            QTimer.singleShot(0, lambda: self.guide_body_splitter.setSizes(sizes))
        self._guide_lower_in_main = False

    def detach_panel(self, panel_id: str):
        if panel_id in self.detached_panel_windows:
            return

        if panel_id == "guide":
            self._detach_guide_lower_section()

        record = self.panel_registry[panel_id]
        content = record["content"]
        record["layout"].removeWidget(content)
        if panel_id == "timer" and hasattr(self, "global_controls_widget"):
            self.timer_button_layout.removeWidget(self.global_controls_widget)
            record["layout"].insertWidget(record["index"], self.global_controls_widget)
        record["expanded_size_policies"] = {
            widget: widget.sizePolicy() for widget in record.get("expand_widgets", ())
        }
        for widget in record.get("expand_widgets", ()):
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if record.get("detach_button") is not None:
            record["detach_button"].hide()

        panel_window = DetachedPanelWindow(
            panel_id,
            record["title"],
            content,
            self.restore_panel,
            self._save_detached_panel_state,
        )
        self.detached_panel_windows[panel_id] = panel_window
        panel_window.apply_window_settings(self.config)
        panel_window.show()
        self._save_detached_panel_state(panel_id)
        self._adjust_main_window_after_panel_change()

    def restore_panel(self, panel_id: str):
        panel_window = self.detached_panel_windows.pop(panel_id, None)
        if panel_window is None:
            return

        record = self.panel_registry[panel_id]
        if panel_id == "timer" and hasattr(self, "global_controls_widget"):
            record["layout"].removeWidget(self.global_controls_widget)
            self.timer_button_layout.addWidget(self.global_controls_widget)
        panel_window.layout().removeWidget(record["content"])
        panel_window.restore_content_size_policy()
        for widget, size_policy in record.pop("expanded_size_policies", {}).items():
            widget.setSizePolicy(size_policy)
        record["layout"].insertWidget(record["index"], record["content"], record.get("stretch", 0))
        if panel_id == "guide":
            self._restore_guide_lower_section()
        if record.get("detach_button") is not None:
            record["detach_button"].show()
        panel_window._returning = True
        panel_window.close()
        panel_window.deleteLater()
        self._save_detached_panel_state(panel_id)
        self._adjust_main_window_after_panel_change()

    def _register_detachable_panel(
        self, panel_id: str, title: str, widgets: list[QWidget], layout, expand_widgets=(),
        header_widgets=(),
    ):
        """連続したUIを、初期化時に一つの移動可能なコンテナへまとめる。"""
        index = layout.indexOf(widgets[0])
        stretch = layout.stretch(index)
        panel = QWidget()
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        title_widget = widgets[0]
        layout.removeWidget(title_widget)
        header_layout.addWidget(title_widget)
        header_layout.addStretch()
        for widget in header_widgets:
            header_layout.addWidget(widget)

        detach_button = QPushButton("↗ 切り離す")
        detach_button.setStyleSheet(Styles.BUTTON)
        detach_button.setCursor(QCursor(Qt.PointingHandCursor))
        detach_button.clicked.connect(lambda: self.detach_panel(panel_id))
        header_layout.addWidget(detach_button)
        panel_layout.addWidget(header_widget)

        for widget in widgets[1:]:
            layout.removeWidget(widget)
            panel_layout.addWidget(widget, stretch=1 if widget in expand_widgets else 0)
        layout.insertWidget(index, panel, stretch)
        self.panel_registry[panel_id] = {
            "content": panel,
            "layout": layout,
            "index": index,
            "stretch": stretch,
            "title": title,
            "detach_button": detach_button,
            "header_widget": header_widget,
            "expand_widgets": tuple(expand_widgets),
        }

    def _restore_detached_panels(self):
        for panel_id in tuple(self.panel_registry):
            state = dict(self._detached_panel_config(panel_id))
            if not state.get("detached", False):
                continue

            self.detach_panel(panel_id)
            panel_window = self.detached_panel_windows[panel_id]
            width, height = state.get("width"), state.get("height")
            x, y = state.get("x"), state.get("y")
            if (
                isinstance(x, int) and isinstance(y, int)
                and isinstance(width, int) and width >= 320
                and isinstance(height, int) and height >= 180
            ):
                saved_geometry = QRect(x, y, width, height)
                screens = QApplication.screens()
                visible = any(screen.availableGeometry().intersects(saved_geometry) for screen in screens)
                if visible:
                    panel_window.setGeometry(saved_geometry)
                elif screens:
                    available = screens[0].availableGeometry()
                    panel_window.setGeometry(
                        available.center().x() - width // 2,
                        available.center().y() - height // 2,
                        width,
                        height,
                    )

    def _close_detached_panels(self):
        """アプリ終了時はパネルを本体へ戻さず閉じ、切り離し状態を保持する。"""
        for panel_window in tuple(getattr(self, "detached_panel_windows", {}).values()):
            self._save_detached_panel_state(panel_window.panel_id, persist=True)
            panel_window._returning = True
            panel_window.close()

    def _apply_detached_panel_window_settings(self):
        for panel_window in getattr(self, "detached_panel_windows", {}).values():
            panel_window.apply_window_settings(self.config)

    def __init__(self):
        super().__init__()

        # Qt can deliver showEvent while startup dialogs are running.  Keep
        # showEvent side-effect free until every widget/state it uses exists.
        self._main_window_initialized = False

        # 設定読み込み
        self.config = ConfigManager.load_config()
        self.setWindowTitle(f"ぽえなび [{get_poe_label(self.config.get('poe_version', POE1))}]")

        # config の display_monitor で指定されたモニターの右端に縦長で配置
        from PySide6.QtWidgets import QApplication
        _config = self.config
        self._display_monitor_index = _config.get("display_monitor", 0)
        self._initial_positioned = False
        # Startup update dialogs can cause Qt to deliver showEvent while
        # __init__ is still running.  Initialize every flag read by
        # showEvent before the update gate can display a dialog.
        self._pending_initial_map_auto_open = False
        self.resize(420, 1200)  # 仮サイズ、showEvent で実際に配置

        # アプリアイコン設定
        icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "icon.ico")
        if not os.path.exists(icon_path):
            # PyInstaller _MEIPASS対応
            base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.argv[0])))
            icon_path = os.path.join(base, "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self._apply_window_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setStyleSheet(Styles.MAIN_WINDOW)
        
        # 設定読み込み
        self.config = ConfigManager.load_config()
        self.update_controller = UpdateController(self)
        self._update_progress_dialog = None
        if not self._run_startup_update_gate():
            QTimer.singleShot(0, QApplication.instance().quit)
            return
        self._connect_update_controller()
        if not self._ensure_poe_version_selected():
            from PySide6.QtWidgets import QApplication
            QTimer.singleShot(0, QApplication.instance().quit)
            return
        self.poe_version = self.config.get("poe_version", POE1)
        
        self.drag_position = None
        self.resize_edge = None  # None or combination of 'left','right','top','bottom'
        self.resize_start_geo = None
        self.resize_start_pos = None
        self.window_locked = self.config.get("window_locked", False)
        self.EDGE_MARGIN = 14
        
        # エリア訪問回数カウンター（街エリアはカウントしない）— zone_id基準
        self.zone_visit_counts = {}
        # PoE2 進行フラグ（ログ検知ベースの高度制御用）
        self.progress_flags = set()
        self._restore_progress_flags()
        self.interlude_ready = set()
        # 起動時の復元中はvisitカウントしない
        self._restoring = False
        # 起動時復元で自動表示されるマップは、メインウィンドウ配置完了後に開く
        # 訪問回数の手動オーバーライド（None=自動, 1 or 2=固定）— ゾーン移動でリセット
        self.visit_override = None
        # Lab中フラグ（志す者の広場→Lab内エリア→街帰還を追跡）
        self._in_lab = False
        self._lab_zone_id = None  # Lab入口の志す者の広場のzone_id
        
        # ガイド折りたたみ状態（初回はTrue、以降はconfig保持）
        self.guide_expanded = self.config.get("guide_expanded", True)
        # セクション個別折りたたみ状態（保存しない — 毎回展開）
        self.zone_header_expanded = True
        self.guide_text_expanded = True
        self.map_section_expanded = True
        # ガイドフォントサイズ
        self.guide_font_size = self.config.get("guide_font_size", 18)
        # タイマーサイズ
        configured_timer_size = self.config.get("timer_size", "large")
        self.timer_size = self._effective_timer_size(configured_timer_size)
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
            "ブラインキングの岩礁", "The Brine King's Reef",
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
        self.timer_ready = False
        self._normal_log_poll_interval_ms = 500
        
        # ラップタイム用
        self.poe_version = self.config.get("poe_version", POE1)
        self.lap_labels = get_lap_labels(self.poe_version)
        self.lap_times = [None] * len(self.lap_labels)
        self.lap_record_order = []
        self.segment_recorder = SegmentRecorder()
        self.current_act = 1
        self.current_zone_act = 1  # 現在エリアから判定したAct（ジェム取得表示の自動追従用）
        self._last_search_target_hwnd = None
        self.panel_registry = {}
        self.detached_panel_windows = {}
        
        self.setup_ui()
        self._restore_detached_panels()
        self.map_thumbnail.auto_open = self.config.get("auto_open_map", False)
        self.map_thumbnail.auto_position = self.config.get("auto_position_map", True)
        self.setMouseTracking(True)
        self.centralWidget().setMouseTracking(True)
        self._apply_bg_opacity(self.config.get("window_opacity", 100))
        self._apply_text_opacity(self.config.get("text_opacity", 100))
        
        # レベルガイド状態
        self.player_level = 1
        self.current_zone = ""
        self._current_zone_id = None
        self._current_zone_name = ""
        self._current_area_note = ""
        self._current_poelab_type = None
        with measure("startup data load"):
            zone_master_data = load_zone_master_data()
            self.zone_data_by_version = zone_master_data["zone_data_by_version"]
        self.town_zones_by_version = zone_master_data["town_zones_by_version"]
        self.zone_data = self.zone_data_by_version.get(self.poe_version, {})
        self.guide_data = load_guide_data(self.poe_version)
        self.mini_navi_overlay = MiniNaviOverlay(self)
        self.poelab_url_resolved.connect(self._open_resolved_poelab_url)
        self.poelab_url_failed.connect(self._handle_poelab_url_error)
        
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
        if fill_missing_client_log_paths(self.config):
            ConfigManager.save_config(self.config)

        client_log_paths = self.config.get("client_log_paths", {})
        current_log_path = client_log_paths.get(self.poe_version, "")
        self.log_watcher = LogWatcher(
            log_path=current_log_path,
            parent=self
        )
        self.log_watcher.set_poe_version(self.poe_version)
        self._normal_log_poll_interval_ms = self.log_watcher.poll_interval_ms
        self.log_watcher.actual_zone_entered.connect(self._on_actual_zone_entered_for_auto_start)
        self.log_watcher.zone_entered.connect(self.on_zone_entered)
        self.log_watcher.level_up.connect(self.on_level_up)
        self.log_watcher.kitava_defeated.connect(self.on_kitava_defeated)
        self.log_watcher.act10_cleared.connect(self.on_act10_cleared)
        self.log_watcher.act4_cleared.connect(self.on_poe2_act4_cleared)
        self.log_watcher.progress_flag_detected.connect(self.set_progress_flag)
        
        # ホットキー初期化
        self.hotkey_signal.connect(self.handle_hotkey)
        self.keyboard_listener = None
        self._gem_shop_search_hold = HoldTrigger()
        self.register_hotkeys()
        
        # ログ監視開始（復元中はvisitカウントしない）
        if current_log_path:
            self._restoring = True
            self.log_watcher.start()
            self._restoring = False
        
        # タイマー状態復元
        self._restore_timer_state()
        self._refresh_ready_button()
        
        # エリアメモ導入案内（全モード共通で一度だけ）
        self._show_area_note_migration_notice_once()

        # 初回起動チェック（ポップアップ + ガイドエリア案内）
        self._check_first_run()
        
        # 全ウィジェットのマウスイベントを横取りしてリサイズ処理
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        self._ef_resize_active = False
        self._ef_resize_edge = None
        self._ef_resize_start_geo = None
        self._ef_resize_start_pos = None
        self._main_window_initialized = True

    def _connect_update_controller(self):
        """Connect handlers used after the startup update gate."""
        self.update_controller.check_finished.connect(self._on_update_check_finished)
        self.update_controller.check_failed.connect(self._on_update_check_failed)
        self.update_controller.download_progress.connect(self._on_update_download_progress)
        self.update_controller.download_ready.connect(self._on_update_download_ready)
        self.update_controller.download_failed.connect(self._on_update_download_failed)
        self.update_controller.download_cancelled.connect(self._on_update_download_cancelled)

    def _run_startup_update_gate(self):
        """Finish the startup update decision before showing setup dialogs."""
        check_loop = QEventLoop()
        result = {"release": None, "error": None}

        def on_finished(release, _manual):
            result["release"] = release
            check_loop.quit()

        def on_failed(message, _manual):
            result["error"] = message
            check_loop.quit()

        self.update_controller.check_finished.connect(on_finished)
        self.update_controller.check_failed.connect(on_failed)
        QTimer.singleShot(0, lambda: self.update_controller.check(False))
        check_loop.exec()
        self.update_controller.check_finished.disconnect(on_finished)
        self.update_controller.check_failed.disconnect(on_failed)

        release = result["release"]
        if release is None:
            return True
        if self.config.get("notified_update_version") == release.version:
            return True

        self.config["notified_update_version"] = release.version
        ConfigManager.save_config(self.config)
        supported = getattr(sys, "frozen", False) and sys.platform == "win32"
        dialog = UpdateAvailableDialog(release, supported, self)
        if not dialog.exec():
            return True
        if not supported:
            QDesktopServices.openUrl(QUrl(release.page_url))
            return True

        progress = UpdateProgressDialog(release.version, self)
        progress.cancel_requested.connect(self.update_controller.cancel_download)
        download_loop = QEventLoop()
        download_result = {"archive": None, "error": None, "cancelled": False}

        def on_progress(done, total):
            progress.set_progress(done, total)

        def on_ready(archive, _release):
            download_result["archive"] = archive
            download_loop.quit()

        def on_download_failed(message):
            download_result["error"] = message
            download_loop.quit()

        def on_cancelled():
            download_result["cancelled"] = True
            download_loop.quit()

        self.update_controller.download_progress.connect(on_progress)
        self.update_controller.download_ready.connect(on_ready)
        self.update_controller.download_failed.connect(on_download_failed)
        self.update_controller.download_cancelled.connect(on_cancelled)
        progress.show()
        QTimer.singleShot(0, lambda: self.update_controller.download(release))
        download_loop.exec()
        progress.close()
        self.update_controller.download_progress.disconnect(on_progress)
        self.update_controller.download_ready.disconnect(on_ready)
        self.update_controller.download_failed.disconnect(on_download_failed)
        self.update_controller.download_cancelled.disconnect(on_cancelled)

        if download_result["cancelled"]:
            return True
        if download_result["error"]:
            QMessageBox.warning(
                self,
                "アップデート",
                f"更新をダウンロードできませんでした。\n{download_result['error']}",
            )
            return True

        answer = QMessageBox.question(
            self,
            "アップデートを適用",
            f"v{release.version} の検証が完了しました。\n"
            "ぽえなびを終了して更新しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return True
        try:
            self.update_controller.launch_updater(download_result["archive"])
        except Exception as exc:
            QMessageBox.critical(self, "アップデート", str(exc))
            return True
        return False
        
    def _ensure_poe_version_selected(self):
        mode = self.config.get("poe_version_mode", "ask")
        if mode in (POE1, POE2):
            self.config["poe_version"] = mode
            return self._ensure_guide_detail_level_selected_if_needed()

        dialog = PoeVersionSelectionDialog(self, self.config.get("poe_version", POE1))
        if dialog.exec():
            self.config["poe_version"] = dialog.selected_version
            ConfigManager.save_config(self.config)
            return self._ensure_guide_detail_level_selected_if_needed()
        return False

    def _ensure_guide_detail_level_selected_if_needed(self):
        """PoE2選択後、初回だけガイド表示レベルを選ばせる。"""
        if self.config.get("poe_version") != POE2:
            return True
        if self.config.get("guide_detail_level_selected"):
            return True

        dialog = GuideDetailLevelSelectionDialog(self, self.config.get("guide_detail_level", "beginner"))
        if dialog.exec():
            self.config["guide_detail_level"] = dialog.selected_level
            self.config["guide_detail_level_selected"] = True
            ConfigManager.save_config(self.config)
            return True
        return False

    def _check_for_updates(self, manual=False):
        """GitHub Releasesから最新バージョンを確認する。"""
        self.update_controller.check(manual)

    def _on_update_check_finished(self, release, manual):
        if release is None:
            if manual:
                QMessageBox.information(self, "アップデート", "最新バージョンです。")
            return
        if not manual and self.config.get("notified_update_version") == release.version:
            return
        self._show_update_available(release)

    def _on_update_check_failed(self, message, manual):
        if manual:
            QMessageBox.warning(
                self,
                "アップデート",
                f"更新を確認できませんでした。\n{message}",
            )

    def _show_update_available(self, release):
        self.config["notified_update_version"] = release.version
        ConfigManager.save_config(self.config)
        supported = getattr(sys, "frozen", False) and sys.platform == "win32"
        dialog = UpdateAvailableDialog(release, supported, self)
        if not dialog.exec():
            return
        if not supported:
            QDesktopServices.openUrl(QUrl(release.page_url))
            return
        self._start_update_download(release)

    def _start_update_download(self, release):
        cached = self.update_controller.ready_archive(release.version)
        if cached is not None:
            self._on_update_download_ready(cached, release)
            return
        self._update_progress_dialog = UpdateProgressDialog(release.version, self)
        self._update_progress_dialog.cancel_requested.connect(
            self.update_controller.cancel_download
        )
        self.update_controller.download(release)
        self._update_progress_dialog.show()

    def _on_update_download_progress(self, done, total):
        if self._update_progress_dialog:
            self._update_progress_dialog.set_progress(done, total)

    def _on_update_download_cancelled(self):
        if self._update_progress_dialog:
            self._update_progress_dialog.reject()
            self._update_progress_dialog = None

    def _on_update_download_failed(self, message):
        self._on_update_download_cancelled()
        QMessageBox.warning(
            self,
            "アップデート",
            f"更新をダウンロードできませんでした。\n{message}",
        )

    def _on_update_download_ready(self, archive, release):
        if self._update_progress_dialog:
            self._update_progress_dialog.accept()
            self._update_progress_dialog = None
        answer = QMessageBox.question(
            self,
            "アップデートを適用",
            f"v{release.version} の検証が完了しました。\n"
            "ぽえなびを終了して更新しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.update_controller.launch_updater(archive)
        except Exception as exc:
            QMessageBox.critical(self, "アップデート", str(exc))
            return
        QApplication.instance().quit()
    
    def _check_first_run(self):
        """現在のPoEバージョンに対応するログファイル設定案内"""
        client_log_paths = self.config.get("client_log_paths", {})
        log_path = client_log_paths.get(self.poe_version, "")
        is_first_run = not self.config.get("setup_completed", False)
        poe_label = get_poe_label(self.poe_version)

        if not log_path:
            # 初回または、選択中バージョンのログファイルが未設定なら案内を出す
            msg = QMessageBox(self)
            msg.setStyleSheet("QMessageBox { font-size: 14px; } QMessageBox QLabel { font-size: 14px; }")
            msg.setWindowTitle("⚙️ ログファイル設定")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText(
                "ぽえなびをご利用いただきありがとうございます！\n\n"
                f"現在は {poe_label} モードです。対応するログファイル（Client.txt）を設定してください。\n\n"
                "1. 右クリックメニューの「設定」、または右側中央の ⚙️ ボタンから設定画面を開く\n"
                "2. 「基本設定」タブで、現在のモードに対応するログファイル欄を設定\n"
                f"   - {poe_label}ログファイル\n"
                "3. 通常のパス例（これはPoE1 Steam版の例です）：\n"
                "    C:\\Program Files (x86)\\Steam\\steamapps\n"
                "    \\common\\Path of Exile\\logs\\Client.txt\n\n"
                "⚠️ 対応するログファイルが未設定だと、エリア検知が動作しません。"
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
            # setup_completedフラグはログパス設定時に立てる

            self.guide_text_label.setText(
                '<div style="padding: 15px;">'
                '<span style="font-size: 20px;">⚙️</span>'
                f'<span style="font-size: 15px; color: #ffc832; font-weight: bold;"> {poe_label}ログファイル（Client.txt）が未設定です</span><br><br>'
                '<span style="font-size: 13px; color: #cccccc;">'
                '右クリック →「設定」→「基本設定」タブから<br>'
                f'{poe_label}ログファイル を設定してください</span><br><br>'
                '<span style="font-size: 12px; color: #999999;">'
                '通常のパス例（これはPoE1 Steam版の例です）：<br>'
                '<span style="color: #b0ffb0;">C:\\Program Files (x86)\\Steam\\steamapps<br>'
                '\\common\\Path of Exile\\logs\\Client.txt</span></span>'
                '</div>'
            )

    def _show_area_note_migration_notice_once(self):
        """公式ガイド編集からエリアメモへの移行案内を一度だけ表示する。"""
        flag = "area_note_migration_notice_shown"
        if self.config.get(flag, False):
            return

        msg = QMessageBox(self)
        msg.setStyleSheet("QMessageBox { font-size: 14px; } QMessageBox QLabel { font-size: 14px; }")
        msg.setWindowTitle("📝 エリアメモ機能について")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            "今回のバージョンから、各エリアのガイドデータは\n"
            "編集できない仕様に変更しました。\n"
            "（PoENaviの自動アップデート機能を正しく動作させるためです）\n"
            "その代わり、各エリアにエリアメモを追加できる\n"
            "「エリアメモ」機能を実装しました。\n\n"
            "大変お手数ですが、以前のガイドを編集していた方は、\n"
            "旧PoENaviフォルダのJSONファイルから、\n"
            "必要な内容を各エリアのエリアメモへコピーしてください。\n\n"
            "今後は公式ガイドとエリアメモを分けて保存するため、\n"
            "次回以降のアップデートでエリアメモが失われることはありません。"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

        self.config[flag] = True
        ConfigManager.save_config(self.config)

    def _show_route_selection_dialog(self):
        """ルート選択ダイアログを表示して設定を保存"""
        dialog = RouteSelectionDialog(self, self.config)
        if dialog.exec():
            routes = dialog.get_routes()
            self.config.update(routes)
            self.config["poe1_route_selected"] = True
            ConfigManager.save_config(self.config)

    def eventFilter(self, obj, event):
        """本体ウィンドウ内のマウスイベントだけで端のリサイズを処理する。"""
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
            # グローバル座標 → ウィンドウ座標
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                if self.window_locked or not self._is_main_window_widget(obj):
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
                min_w, min_h = 300, self._main_window_min_height()
                
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

    def _is_main_window_widget(self, obj):
        """イベント元が本体または本体配下のウィジェットか判定する。"""
        widget = obj if isinstance(obj, QWidget) else None
        while widget is not None:
            if widget is self:
                return True
            widget = widget.parentWidget()
        return False
    
    def _global_detect_edge(self, gpos):
        """グローバル座標からリサイズ方向を検出"""
        geo = self.frameGeometry()
        if not geo.contains(gpos):
            return None
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

    def _apply_text_opacity(self, opacity_pct: int):
        """ガイドテキストエリア全体の透過率を適用（QGraphicsOpacityEffect）"""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        opacity = opacity_pct / 100.0
        for attr in ('guide_container', 'timer_container', 'timer_toggle_btn', 'guide_toggle_btn'):
            w = getattr(self, attr, None)
            if w:
                effect = QGraphicsOpacityEffect(w)
                effect.setOpacity(opacity)
                w.setGraphicsEffect(effect)

    def _effective_timer_size(self, timer_size=None):
        """表示に使う実サイズを返す（off時は直前サイズを保持）"""
        timer_size = timer_size or self.config.get("timer_size", "large")
        if timer_size == "off":
            return self.config.get("timer_size_before_off", "medium")
        return timer_size

    def _set_timer_expanded(self, expanded: bool):
        """タイマー本体と操作ボタンの表示状態をまとめて切り替える"""
        self.timer_expanded = expanded
        self.timer_content.setVisible(expanded)
        self.start_btn.setVisible(expanded)
        self.stop_btn.setVisible(expanded)
        self.reset_btn.setVisible(expanded)
        self.ready_btn.setVisible(expanded)
        self.timer_toggle_btn.setText("▼ タイマー" if expanded else "▶ タイマー")

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
        # リサイズ用の端つかみ範囲（EDGE_MARGIN=14）は維持しつつ、
        # 最小化/閉じるボタンが上端・右端の判定に被らないよう少し内側へ逃がす。
        title_bar.setContentsMargins(5, 16, 16, 0)
        
        # クリックスルー状態表示
        self.click_through = False
        self.click_through_label = QLabel("")
        self._update_click_through_label()
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
        minimize_btn.setToolTip("最小化（みになび表示中は本体だけ隠します）")
        minimize_btn.clicked.connect(self.minimize_main_window)
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
        if self.config.get("timer_size") == "off":
            self.timer_expanded = False
        
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

        self.segment_summary_label = QLabel()
        self.segment_summary_label.setAlignment(Qt.AlignCenter)
        self.segment_summary_label.setWordWrap(True)
        self.segment_summary_label.setStyleSheet(
            f"color: {Styles.TEXT_COLOR}; font-size: 14px; padding: 2px 0;"
        )

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
        
        # ラップタイム行
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
        self.lap_content_layout = QVBoxLayout(self.lap_content)
        self.lap_content_layout.setContentsMargins(0, 0, 0, 0)
        self.lap_content_layout.setSpacing(0)
        self.lap_label_widgets = []
        self._rebuild_lap_ui()
        
        timer_content_layout.addWidget(self.lap_content)
        self.lap_content.setVisible(self.lap_expanded)
        
        self.update_lap_display()
        
        # timer_contentをtimer_containerに追加
        timer_container_layout.addWidget(self.timer_content)
        self.timer_content.setVisible(self.timer_expanded)
        
        # 操作ボタン（レベルガイドより上に配置）
        timer_container_layout.addSpacing(10)

        # 操作ボタン
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.setAlignment(Qt.AlignCenter)
        self.timer_button_layout = button_layout
        
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

        self.ready_btn = QPushButton("Ready")
        self.ready_btn.setStyleSheet(Styles.BUTTON)
        self.ready_btn.setToolTip("黄昏の岸辺への入場を待ってタイマーを自動開始")
        self.ready_btn.clicked.connect(self.toggle_timer_ready)
        button_layout.addWidget(self.ready_btn)
        
        # タイマー折りたたみ時はボタンも隠す
        if not self.timer_expanded:
            self.start_btn.setVisible(False)
            self.stop_btn.setVisible(False)
            self.reset_btn.setVisible(False)
            self.ready_btn.setVisible(False)
        
        button_layout.addStretch()

        # PoENavi全体の操作。本体内ではタイマー操作と同じ行に置くが、
        # タイマー切り離し時は本体側へ残す。
        self.global_controls_widget = QWidget()
        global_controls_layout = QHBoxLayout(self.global_controls_widget)
        global_controls_layout.setContentsMargins(0, 0, 0, 0)
        global_controls_layout.setSpacing(10)
        global_controls_layout.addStretch()

        self.memo_btn = QPushButton("📝")
        self.memo_btn.setStyleSheet(Styles.BUTTON)
        self.memo_btn.setFixedSize(35, 35)
        self.memo_btn.setToolTip("共通メモ")
        self.memo_btn.clicked.connect(self.open_memo)
        global_controls_layout.addWidget(self.memo_btn)

        self.vendor_search_btn = QPushButton("🔍")
        self.vendor_search_btn.setStyleSheet(Styles.BUTTON)
        self.vendor_search_btn.setFixedSize(35, 35)
        self.vendor_search_btn.setToolTip("店売り・スタッシュ検索プリセット")
        self.vendor_search_btn.clicked.connect(self.open_vendor_search_presets)
        global_controls_layout.addWidget(self.vendor_search_btn)

        self.poetore_btn = QPushButton("💰")
        self.poetore_btn.setStyleSheet(Styles.BUTTON)
        self.poetore_btn.setFixedSize(35, 35)
        self._update_poetore_hotkey_tooltip()
        self.poetore_btn.clicked.connect(self.open_poetore)
        global_controls_layout.addWidget(self.poetore_btn)
        
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setStyleSheet(Styles.BUTTON)
        self.settings_btn.setFixedSize(35, 35)
        self.settings_btn.clicked.connect(self.open_settings)
        global_controls_layout.addWidget(self.settings_btn)
        button_layout.addWidget(self.global_controls_widget)
        
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

        # ガイドの表示範囲・進行方法に関する操作はガイドと一緒に移動する。
        self.guide_mode_controls = QWidget()
        guide_mode_layout = QHBoxLayout(self.guide_mode_controls)
        guide_mode_layout.setContentsMargins(0, 0, 0, 0)
        guide_mode_layout.setSpacing(8)

        self.part2_btn = QPushButton("Act 6-10" if self.part2_mode else "Act 1-5")
        self.part2_btn.setStyleSheet(self._part2_btn_style())
        self.part2_btn.setFixedHeight(22)
        self.part2_btn.clicked.connect(self.toggle_part2)
        self.part2_btn.setVisible(self.poe_version == POE1)
        guide_mode_layout.addWidget(self.part2_btn)

        self.visit_btn = QPushButton("自動")
        self.visit_btn.setStyleSheet(self._visit_btn_style())
        self.visit_btn.setFixedHeight(22)
        self.visit_btn.clicked.connect(self.toggle_visit_override)
        guide_mode_layout.addWidget(self.visit_btn)
        
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
        
        self.level_label = QLabel("キャラLv. 1")
        self.level_label.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px; font-weight: bold;")
        zone_info_layout.addWidget(self.level_label)
        guide_layout.addLayout(zone_info_layout)
        
        # アドバイスメッセージ
        self.advice_label = QLabel("ログ監視待機中...")
        self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
        self.advice_label.setWordWrap(True)
        guide_layout.addWidget(self.advice_label)
        
        self.guide_info_frame = guide_frame
        
        # ゾーンヘッダー折りたたみトグル
        self.zone_header_toggle_btn = QPushButton("▼ ゾーン情報")
        self.zone_header_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 11px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.zone_header_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.zone_header_toggle_btn.clicked.connect(self.toggle_zone_header)
        self.zone_header_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        guide_container_layout.addWidget(self.zone_header_toggle_btn)
        guide_container_layout.addWidget(self.guide_info_frame)
        
        # ── 攻略ガイド表示エリア ──
        # ガイドテキスト折りたたみトグル
        self.guide_text_toggle_btn = QPushButton("▼ ガイドテキスト")
        self.guide_text_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 11px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.guide_text_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.guide_text_toggle_btn.clicked.connect(self.toggle_guide_text)
        self.guide_text_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        guide_text_header_layout = QHBoxLayout()
        guide_text_header_layout.setContentsMargins(0, 0, 0, 0)
        guide_text_header_layout.setSpacing(6)
        guide_text_header_layout.addWidget(self.guide_text_toggle_btn)
        guide_text_header_layout.addStretch()

        self.area_note_edit_button = QPushButton("📝 エリアメモ")
        self.area_note_edit_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.area_note_edit_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.area_note_edit_button.setToolTip("現在のエリアのエリアメモを編集します")
        self.area_note_edit_button.setStyleSheet(f"""
            QPushButton {{
                background: rgba(20, 30, 20, 160);
                color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176, 255, 123, 0.75);
                border-radius: 5px;
                padding: 3px 9px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(73, 110, 50, 180); color: #ffffff; }}
            QPushButton:disabled {{ color: #666666; border-color: #555555; }}
        """)
        self.area_note_edit_button.clicked.connect(self.open_area_note_editor)
        self.area_note_edit_button.setEnabled(False)
        guide_text_header_layout.addWidget(self.area_note_edit_button)

        self.guide_detail_level_toggle_btn = QPushButton()
        self.guide_detail_level_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.guide_detail_level_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.guide_detail_level_toggle_btn.setToolTip("詳細版ガイド / 要点版ガイドを切り替えます")
        self.guide_detail_level_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(20, 30, 20, 160);
                color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176, 255, 123, 0.75);
                border-radius: 5px;
                padding: 3px 9px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(73, 110, 50, 180);
                color: #ffffff;
            }}
        """)
        self.mini_navi_toggle_btn = QPushButton()
        self.mini_navi_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.mini_navi_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.mini_navi_toggle_btn.setToolTip("みになびのON/OFFを切り替えます。ロック操作はみになび側の鍵ボタンで行えます。")
        self.mini_navi_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(20, 30, 20, 160);
                color: {Styles.TEXT_COLOR};
                border: 1px solid rgba(176, 255, 123, 0.75);
                border-radius: 5px;
                padding: 3px 9px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: rgba(73, 110, 50, 180);
                color: #ffffff;
            }}
        """)
        self.mini_navi_toggle_btn.clicked.connect(self.toggle_mini_navi_overlay)
        guide_text_header_layout.addWidget(self.mini_navi_toggle_btn)

        self.guide_detail_level_toggle_btn.clicked.connect(self.toggle_guide_detail_level)
        guide_text_header_layout.addWidget(self.guide_detail_level_toggle_btn)
        guide_container_layout.addLayout(guide_text_header_layout)
        self._refresh_mini_navi_toggle()
        self._refresh_guide_detail_level_toggle()
        
        # ── 攻略ガイド表示エリア（本体） ──
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

        self.area_note_frame = QFrame()
        self.area_note_frame.setStyleSheet("""
            QFrame {
                background: rgba(55, 45, 15, 190);
                border: 1px solid rgba(255, 210, 80, 150);
                border-radius: 5px;
            }
        """)
        area_note_layout = QVBoxLayout(self.area_note_frame)
        area_note_layout.setContentsMargins(9, 6, 9, 6)
        area_note_layout.setSpacing(3)
        area_note_title = QLabel("📝 エリアメモ")
        area_note_title.setStyleSheet(
            "color: #ffd86b; font-size: 11px; font-weight: bold; border: none; background: transparent;"
        )
        area_note_layout.addWidget(area_note_title)
        self.area_note_label = QLabel()
        self.area_note_label.setTextFormat(Qt.RichText)
        self.area_note_label.setWordWrap(True)
        self.area_note_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.area_note_label.setStyleSheet(
            f"color: {Styles.TEXT_COLOR}; font-size: {self.guide_font_size}px; border: none; background: transparent;"
        )
        area_note_layout.addWidget(self.area_note_label)
        self.area_note_frame.hide()
        guide_text_layout.addWidget(self.area_note_frame)

        poelab_button_layout = QHBoxLayout()
        poelab_button_layout.setContentsMargins(0, 0, 0, 0)
        self.poelab_link_button = QPushButton("🏛️ 今日のPoELabを開く")
        self.poelab_link_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.poelab_link_button.setToolTip("当日のPoELab Daily Notesを標準ブラウザで開きます")
        self.poelab_link_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.poelab_link_button.setStyleSheet("""
            QPushButton {
                background: rgba(150, 30, 30, 210);
                color: #ffffff;
                border: 1px solid rgba(255, 115, 105, 230);
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(205, 45, 40, 235);
                border-color: #ffaaa2;
            }
            QPushButton:pressed { background: rgba(115, 20, 20, 235); }
            QPushButton:disabled { color: #777777; border-color: #555555; }
        """)
        self.poelab_link_button.clicked.connect(self.open_daily_poelab)
        self.poelab_link_button.hide()
        poelab_button_layout.addWidget(self.poelab_link_button)
        poelab_button_layout.addStretch()
        guide_text_layout.addLayout(poelab_button_layout)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
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

        # ガイドテキストと下部セクション（マップ/ジェム取得）の高さをドラッグで調整
        self.guide_body_splitter = QSplitter(Qt.Vertical)
        self.guide_body_splitter.setChildrenCollapsible(False)
        self.guide_body_splitter.setHandleWidth(8)
        self.guide_body_splitter.setStyleSheet(f"""
            QSplitter::handle:vertical {{
                background: rgba(176, 255, 123, 0.12);
                border-top: 1px solid rgba(176, 255, 123, 0.28);
                border-bottom: 1px solid rgba(176, 255, 123, 0.28);
                margin: 1px 0;
            }}
            QSplitter::handle:vertical:hover {{
                background: rgba(176, 255, 123, 0.30);
            }}
        """)
        self.guide_body_splitter.addWidget(self.guide_text_frame)

        self.guide_lower_widget = QWidget()
        guide_lower_layout = QVBoxLayout(self.guide_lower_widget)
        guide_lower_layout.setContentsMargins(0, 0, 0, 0)
        guide_lower_layout.setSpacing(5)
        self.guide_body_splitter.addWidget(self.guide_lower_widget)
        self.guide_body_splitter.setStretchFactor(0, 3)
        self.guide_body_splitter.setStretchFactor(1, 1)
        self.guide_body_splitter.splitterMoved.connect(self._on_guide_body_splitter_moved)
        guide_container_layout.addWidget(self.guide_body_splitter, stretch=1)
        
        # ── マップサムネイル一覧 ──
        # マップ折りたたみトグル
        self.map_toggle_btn = QPushButton("▼ マップ")
        self.map_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 11px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.map_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.map_toggle_btn.clicked.connect(self.toggle_map_section)
        self.map_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.map_toggle_btn.setMinimumHeight(30)
        guide_lower_layout.addWidget(self.map_toggle_btn)
        
        self.map_thumbnail = MapThumbnailWidget()
        self.map_thumbnail.setVisible(False)
        guide_lower_layout.addWidget(self.map_thumbnail, stretch=0)
        
        # ── ジェム取得タイミング表示 ──
        # ジェムトラッカー折りたたみトグル
        self.gem_tracker_expanded = self.config.get("gem_tracker_expanded", True)
        self.gem_tracker_toggle_btn = QPushButton("▼ ジェム取得" if self.gem_tracker_expanded else "▶ ジェム取得")
        self.gem_tracker_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Styles.TEXT_COLOR};
                border: none; font-size: 11px; font-weight: bold;
                text-align: left; padding: 2px 5px;
            }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        self.gem_tracker_toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.gem_tracker_toggle_btn.clicked.connect(self.toggle_gem_tracker)
        self.gem_tracker_toggle_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        guide_lower_layout.addWidget(self.gem_tracker_toggle_btn)
        
        # ジェムトラッカーコンテナ
        self.gem_tracker_frame = QFrame()
        self.gem_tracker_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 160);
                border: 1px solid rgba(176, 255, 123, 0.2);
                border-radius: 6px;
            }
        """)
        gem_tracker_layout = QVBoxLayout(self.gem_tracker_frame)
        gem_tracker_layout.setContentsMargins(8, 4, 8, 4)
        gem_tracker_layout.setSpacing(4)
        
        # PoBインポートボタン
        pob_btn_layout = QHBoxLayout()
        pob_btn_layout.setSpacing(6)
        
        self.pob_import_btn = QPushButton("📥 PoBインポート")
        self.pob_import_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(68,136,255,0.2); color: #4488ff;
                border: 1px solid rgba(68,136,255,0.5); border-radius: 3px;
                padding: 3px 10px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(68,136,255,0.35); }}
        """)
        self.pob_import_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.pob_import_btn.clicked.connect(self._on_pob_import)
        pob_btn_layout.addWidget(self.pob_import_btn)
        
        # PoBクリアボタン
        self.pob_clear_btn = QPushButton("データクリア")
        self.pob_clear_btn.setMinimumHeight(22)
        self.pob_clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,102,102,0.10); color: #ff8888;
                border: 1px solid rgba(255,102,102,0.45); border-radius: 3px;
                padding: 3px 8px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(255,102,102,0.22); color: #ffaaaa; }}
        """)
        self.pob_clear_btn.setToolTip("PoBデータをクリア")
        self.pob_clear_btn.clicked.connect(self._on_pob_clear)
        pob_btn_layout.addWidget(self.pob_clear_btn)

        pob_btn_layout.addStretch()
        gem_tracker_layout.addLayout(pob_btn_layout)

        gem_search_preview_layout = QHBoxLayout()
        gem_search_preview_layout.setSpacing(6)
        self.gem_shop_search_preview_label = QLabel()
        self.gem_shop_search_preview_label.setStyleSheet("color: #88aacc; font-size: 10px;")
        self.gem_shop_search_preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.gem_shop_search_preview_label.setWordWrap(True)
        gem_search_preview_layout.addWidget(self.gem_shop_search_preview_label, stretch=1)

        self.gem_shop_search_copy_btn = QPushButton("Regexをコピー")
        self.gem_shop_search_copy_btn.setMinimumHeight(22)
        self.gem_shop_search_copy_btn.setToolTip("現在Actのショップ検索Regexをクリップボードへコピー（ゲームには入力しません）")
        self.gem_shop_search_copy_btn.setStyleSheet(Styles.BUTTON)
        self.gem_shop_search_copy_btn.clicked.connect(self.copy_gem_shop_search_query)
        gem_search_preview_layout.addWidget(self.gem_shop_search_copy_btn)
        gem_tracker_layout.addLayout(gem_search_preview_layout)

        # ジェムトラッカーウィジェット
        self.gem_tracker = GemTrackerWidget()
        self.gem_tracker.gem_checked.connect(self._on_gem_checked)
        self.gem_tracker.act_changed.connect(self._on_manual_gem_tracker_act_changed)
        self.gem_tracker.gem_search_requested.connect(self.search_gem_in_poe)
        gem_tracker_layout.addWidget(self.gem_tracker)
        
        # 保存済みPoBデータがあれば復元
        if self._has_pob_import_data():
            self._update_gem_tracker()
        self._refresh_gem_shop_search_preview()
        
        self.gem_tracker_frame.setVisible(self.gem_tracker_expanded and self.poe_version == POE1)
        self.gem_tracker_toggle_btn.setVisible(self.poe_version == POE1)
        guide_lower_layout.addWidget(self.gem_tracker_frame, stretch=1)

        saved_splitter_sizes = self.config.get("guide_body_splitter_sizes")
        if (
            isinstance(saved_splitter_sizes, list)
            and len(saved_splitter_sizes) == 2
            and all(isinstance(v, int) and v > 0 for v in saved_splitter_sizes)
        ):
            QTimer.singleShot(0, lambda sizes=saved_splitter_sizes: self.guide_body_splitter.setSizes(sizes))
        
        layout.addWidget(self.guide_container, stretch=1)

        self._register_detachable_panel(
            "timer", "タイマー", [self.timer_toggle_btn, self.timer_container], layout,
        )
        self._register_detachable_panel(
            "guide", "ガイド", [self.guide_toggle_btn, self.guide_container], layout,
            expand_widgets=(self.guide_container,), header_widgets=(self.guide_mode_controls,),
        )
        self._register_detachable_panel(
            "map", "マップ", [self.map_toggle_btn, self.map_thumbnail], guide_lower_layout,
            expand_widgets=(self.map_thumbnail,),
        )
        self._register_detachable_panel(
            "gem", "ジェム取得", [self.gem_tracker_toggle_btn, self.gem_tracker_frame],
            guide_lower_layout, expand_widgets=(self.gem_tracker_frame,),
        )
        self.panel_registry["gem"]["content"].setVisible(self.poe_version == POE1)
        
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

    def _adjust_height_keep_width(self):
        """折りたたみ操作時に、現在の横幅を維持したまま高さだけ再調整する。"""
        current_width = self.width()
        self.adjustSize()
        if self.width() != current_width:
            self.resize(current_width, self.height())

    def _adjust_main_window_after_panel_change(self):
        """パネル移動後に、本体の横幅を保ったまま適切な高さへ調整する。"""
        if self._are_all_visible_panels_detached():
            self._collapse_main_window_to_controls()
            # reparent直後はQtのレイアウト最小サイズが古いことがあるため、
            # レイアウト更新後にも同じ縮小を適用する。
            QTimer.singleShot(0, self._collapse_main_window_to_controls)
            return
        self.setMinimumHeight(self.MIN_HEIGHT)
        self._adjust_height_keep_width()

    def _collapse_main_window_to_controls(self):
        """全パネル切り離し中の本体を、共通操作列だけの高さへ縮める。"""
        if not self._are_all_visible_panels_detached():
            return
        central = self.centralWidget()
        if central is not None and central.layout() is not None:
            central.layout().invalidate()
            central.updateGeometry()
        # QtのminimumSizeHintが切り離し前の内容を保持していても、
        # 明示した最小高さを優先して操作列まで縮められるようにする。
        self.setMinimumHeight(self.DETACHED_ONLY_MIN_HEIGHT)
        self.resize(self.width(), self.DETACHED_ONLY_MIN_HEIGHT)

    def _adjust_detached_panel_height(self, panel_id: str):
        """切り離しパネルの展開内容を収めつつ、ユーザー指定サイズは維持する。"""
        panel_window = self.detached_panel_windows.get(panel_id)
        if panel_window is None:
            return

        panel_window.content.updateGeometry()
        panel_window.layout().activate()
        required_height = max(panel_window.minimumHeight(), panel_window.sizeHint().height())
        if required_height > panel_window.height():
            panel_window.resize(panel_window.width(), required_height)

    def _fit_detached_panel_height(self, panel_id: str):
        """折りたたみ後の内容量に合わせて、切り離しパネルの余白を除去する。"""
        panel_window = self.detached_panel_windows.get(panel_id)
        if panel_window is None:
            return

        panel_window.content.updateGeometry()
        panel_window.layout().activate()
        required_height = max(panel_window.minimumHeight(), panel_window.sizeHint().height())
        panel_window.resize(panel_window.width(), required_height)

    def _adjust_panel_or_main(self, panel_id: str):
        if self._is_panel_detached(panel_id):
            self._adjust_detached_panel_height(panel_id)
        else:
            self._adjust_height_keep_width()

    def _on_guide_body_splitter_moved(self, _pos: int, _index: int):
        """ガイドテキスト欄のドラッグ調整位置を保存する。"""
        if not hasattr(self, "guide_body_splitter"):
            return
        self.config["guide_body_splitter_sizes"] = self.guide_body_splitter.sizes()
        ConfigManager.save_config(self.config)

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

    def _interlude_boss_zone_map(self):
        return {
            "ホルテンの豪邸": 5,
            "Holten Estate": 5,
            "キーマの貯水池": 6,
            "Qimah Reservoir": 6,
            "クアチクの地下避難所": 7,
            "The Cuachic Vault": 7,
        }

    def _interlude_start_zone_map(self):
        return {
            "避難所": 5,
            "The Refuge": 5,
            "カーリバザール": 6,
            "The Khari Bazaar": 6,
            "森の広場": 7,
            "The Glade": 7,
        }

    def _handle_interlude_lap_progress(self, zone_name: str):
        if self.poe_version != POE2 or not self.is_running:
            return
        boss_lap = self._interlude_boss_zone_map().get(zone_name)
        if boss_lap:
            self.interlude_ready.add(boss_lap)
            return
        start_lap = self._interlude_start_zone_map().get(zone_name)
        if not start_lap:
            return
        completed = sorted(lap for lap in self.interlude_ready if lap != start_lap and self.lap_times[lap - 1] is None)
        for lap_num in completed:
            print(f"[AUTO-LAP] {self.lap_labels[lap_num - 1]}完了 — {zone_name}到達")
            self.record_lap_at(lap_num)
            self.interlude_ready.discard(lap_num)

    def _try_auto_lap(self, zone_name: str):
        """エリア入場時に自動ラップを試行"""
        if not self.auto_lap or not self.is_running:
            return
        lap_num = get_auto_lap_triggers(self.poe_version).get(zone_name)
        if lap_num is None:
            return
        # Act1トリガー(南の森)はAct6にも同名あるのでpart2_modeで判別
        if lap_num == 1 and self.part2_mode:
            return

        # PoE2の幕間1-3は自由順で記録、クリアは幕間完了後のみ
        if self.poe_version == POE2 and 5 <= lap_num <= 7:
            print(f"[AUTO-LAP] {self.lap_labels[lap_num - 1]}完了 — {zone_name}")
            self.record_lap_at(lap_num)
            return
        if self.poe_version == POE2 and lap_num == 8:
            pending_interludes = sorted(lap for lap in self.interlude_ready if 5 <= lap <= 7 and self.lap_times[lap - 1] is None)
            for pending_lap in pending_interludes:
                print(f"[AUTO-LAP] {self.lap_labels[pending_lap - 1]}完了 — キャンペーンクリア到達")
                self.record_lap_at(pending_lap)
                self.interlude_ready.discard(pending_lap)
            if any(self.lap_times[i] is None for i in range(4, 7)):
                return
            print(f"[AUTO-LAP] {self.lap_labels[lap_num - 1]}完了 — {zone_name}")
            self.record_lap_at(lap_num)
            if zone_name in ("ジッグラトの避難所", "The Ziggurat Refuge"):
                clear_html = get_clear_message(POE2, "final")
                if clear_html:
                    self.guide_text_label.setText(clear_html)
                    self.guide_text_label.setStyleSheet(
                        f"color: #e0e0e0; font-size: {self.guide_font_size}px; background: transparent;"
                    )
                    self.map_thumbnail.load_maps("", part2=False)
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
    
    def _set_part2(self, enabled: bool, update_guide: bool = True):
        """Part 2モードの切り替え"""
        if self.part2_mode == enabled:
            return
        self.part2_mode = enabled
        self.config["part2_mode"] = enabled
        ConfigManager.save_config(self.config)
        self.part2_btn.setText("Act 6-10" if enabled else "Act 1-5")
        self.part2_btn.setStyleSheet(self._part2_btn_style())
        # 現在のゾーンを再評価（カウントアップせずガイド表示だけ更新）
        if update_guide and self.current_zone:
            zone_id = self._get_zone_id(self.current_zone)
            act_name, zone_level = get_zone_info(self.zone_data, self.current_zone, part2=self.part2_mode)
            self._update_guide_and_map(self.current_zone, zone_id, 1)
    
    def toggle_timer(self):
        """タイマー+ラップ表示の折りたたみ/展開"""
        new_expanded = not self.timer_expanded
        self._set_timer_expanded(new_expanded)
        self.config["timer_expanded"] = self.timer_expanded
        # 設定で「オフ」を選んだ後に手動展開した場合は、直前のサイズへ戻す
        if new_expanded and self.config.get("timer_size") == "off":
            restored_size = self.config.get("timer_size_before_off", "medium")
            self.config["timer_size"] = restored_size
            self.timer_size = restored_size
            self._apply_timer_size()
        ConfigManager.save_config(self.config)
        self._adjust_panel_or_main("timer")
    
    def toggle_lap(self):
        """ラップタイム表示の折りたたみ/展開"""
        self.lap_expanded = not self.lap_expanded
        self.lap_content.setVisible(self.lap_expanded)
        self.lap_toggle_btn.setText("▼ ラップタイム" if self.lap_expanded else "▶ ラップタイム")
        self.config["lap_expanded"] = self.lap_expanded
        ConfigManager.save_config(self.config)
        if self._is_panel_detached("timer"):
            if self.lap_expanded:
                self._adjust_detached_panel_height("timer")
            else:
                self._fit_detached_panel_height("timer")
        else:
            self._adjust_height_keep_width()
    
    def toggle_gem_tracker(self):
        """ジェム取得リストの折りたたみ/展開"""
        if self.poe_version != POE1:
            return
        self.gem_tracker_expanded = not self.gem_tracker_expanded
        self.gem_tracker_frame.setVisible(self.gem_tracker_expanded)
        self.gem_tracker_toggle_btn.setText("▼ ジェム取得" if self.gem_tracker_expanded else "▶ ジェム取得")
        self.config["gem_tracker_expanded"] = self.gem_tracker_expanded
        ConfigManager.save_config(self.config)
        self._adjust_panel_or_main("gem")

    def _load_pob_import_state(self):
        return ConfigManager.load_pob_import_data()

    def _current_pob_data(self):
        return self._load_pob_import_state().get("pob_data")

    def _has_pob_import_data(self):
        return bool(self._current_pob_data())

    def _on_pob_import(self):
        """PoBインポートボタンのクリックハンドラ"""
        dialog = PoBImportDialog(self)
        if dialog.exec() == QDialog.Accepted:
            pob_code = dialog.get_pob_code()
            if not pob_code:
                return
            try:
                skill_sets = get_pob_skill_sets(pob_code)
                selected_skill_set_ids = []
                if skill_sets:
                    skill_set_dialog = PoBSkillSetSelectionDialog(skill_sets, self)
                    if skill_set_dialog.exec() != QDialog.Accepted:
                        return
                    selected_skill_set_ids = skill_set_dialog.selected_skill_set_ids()

                result = import_pob(pob_code, selected_skill_set_ids=selected_skill_set_ids)
                if not result or not result.get("gem_groups"):
                    QMessageBox.warning(self, "インポートエラー", "選択されたSkill setからジェム情報を取得できませんでした。")
                    return

                # PoBインポート結果は設定ではなく専用JSONへ保存
                ConfigManager.save_pob_import_data({
                    "pob_data": result,
                    "pob_code": pob_code,
                    "selected_skill_set_ids": selected_skill_set_ids,
                })
                # 旧バージョンでconfig.jsonに入っていた場合は掃除する
                self.config.pop("pob_data", None)
                self.config.pop("pob_code", None)
                ConfigManager.save_config(self.config)

                # ジェム取得リストを更新
                self._update_gem_tracker()
                selected_titles = [
                    skill_set.get("title", "")
                    for skill_set in result.get("skill_sets", [])
                    if str(skill_set.get("id", "")) in set(selected_skill_set_ids)
                ]
                skill_set_summary = "\n".join(f"- {title}" for title in selected_titles[:8])
                if len(selected_titles) > 8:
                    skill_set_summary += f"\n- 他 {len(selected_titles) - 8}件"
                QMessageBox.information(self, "インポート成功",
                    f"クラス: {result.get('class', '?')}\n"
                    f"昇華: {result.get('ascendancy', '?')}\n"
                    f"Skill set: {len(selected_titles) if selected_titles else '全'}個\n"
                    f"ジェムグループ: {len(result.get('gem_groups', []))}個"
                    + (f"\n\n{skill_set_summary}" if skill_set_summary else ""))
            except Exception as e:
                QMessageBox.warning(self, "インポートエラー", f"PoBコードの解析に失敗しました:\n{e}")

    def _update_gem_tracker(self):
        """ジェム取得リストを現在のActに基づいて更新"""
        pob_data = self._current_pob_data()
        if not pob_data:
            self._refresh_gem_shop_search_preview()
            return

        use_library = ConfigManager.effective_poe1_route_act3(self.config) == "library_detour"
        checked_gems = self._load_pob_import_state().get("gem_tracker_checked", [])

        # PoBデータからジェム名リストを抽出
        gem_names = []
        for group in pob_data.get("gem_groups", []):
            for gem in group.get("gems", []):
                name = gem.get("name", "").lower()
                if name and name not in gem_names:
                    gem_names.append(name)

        plan = resolve_gem_acquisition(
            gem_names=gem_names,
            char_class=pob_data.get("class", "").lower(),
            library_route=use_library,
        )

        self._apply_gem_tracker_data(self.gem_tracker, plan, pob_data, use_library, checked_gems)
        self._refresh_gem_shop_search_preview()

    def _apply_gem_tracker_data(self, widget: GemTrackerWidget, plan: list, pob_data: dict, use_library: bool, checked_gems: list):
        """GemTrackerWidgetへ現在のPoB/チェック/Act状態を反映する。"""
        widget.set_library_route(use_library)
        widget._checked_gems = set(checked_gems)
        widget.set_acquisition_plan(
            plan=plan,
            char_class=pob_data.get("class", ""),
            ascendancy=pob_data.get("ascendancy", ""),
        )
        widget.set_current_act(getattr(self, "current_zone_act", self.current_act))

    def _sync_gem_tracker_checked_state(self):
        """保存済みのチェック状態をジェム取得表示へ同期する。"""
        checked = set(self._load_pob_import_state().get("gem_tracker_checked", []))
        if hasattr(self, "gem_tracker"):
            self.gem_tracker.set_checked_gems(checked)

    def _on_manual_gem_tracker_act_changed(self, act: int):
        """手動Act切替をショップRegexへ反映する。"""
        if hasattr(self, "gem_tracker") and self.gem_tracker._current_act != act:
            self.gem_tracker.set_current_act(act)
        self._refresh_gem_shop_search_preview()

    def _on_pob_clear(self):
        """PoBデータをクリア"""
        ConfigManager.clear_pob_import_data()
        self.config.pop("pob_data", None)
        self.config.pop("pob_code", None)
        self.config.pop("gem_tracker_checked", None)
        ConfigManager.save_config(self.config)
        self.gem_tracker.clear()
        self._refresh_gem_shop_search_preview()

    def _on_gem_checked(self, gem_name: str, checked: bool):
        """ジェムチェックボックスの状態変更ハンドラ"""
        pob_state = self._load_pob_import_state()
        checked_gems = list(pob_state.get("gem_tracker_checked", []))
        if checked and gem_name not in checked_gems:
            checked_gems.append(gem_name)
        elif not checked and gem_name in checked_gems:
            checked_gems.remove(gem_name)
        pob_state["gem_tracker_checked"] = checked_gems
        ConfigManager.save_pob_import_data(pob_state)
        self.config.pop("gem_tracker_checked", None)
        ConfigManager.save_config(self.config)
        self._sync_gem_tracker_checked_state()
        self._refresh_gem_shop_search_preview()

    def toggle_guide(self):
        """ガイドエリアの折りたたみ/展開をトグル"""
        self.guide_expanded = not self.guide_expanded
        self._apply_guide_visibility()
        self._refresh_mini_navi_toggle()
        # config保存
        self.config["guide_expanded"] = self.guide_expanded
        ConfigManager.save_config(self.config)
        self._adjust_panel_or_main("guide")
    
    def toggle_zone_header(self):
        """ゾーンヘッダーの折りたたみ/展開"""
        self.zone_header_expanded = not self.zone_header_expanded
        self.guide_info_frame.setVisible(self.zone_header_expanded)
        self.zone_header_toggle_btn.setText("▼ ゾーン情報" if self.zone_header_expanded else "▶ ゾーン情報")
        self._adjust_panel_or_main("guide")
    
    def toggle_guide_text(self):
        """ガイドテキストの折りたたみ/展開"""
        self.guide_text_expanded = not self.guide_text_expanded
        self.guide_text_frame.setVisible(self.guide_text_expanded)
        self.guide_text_toggle_btn.setText("▼ ガイドテキスト" if self.guide_text_expanded else "▶ ガイドテキスト")
        self._adjust_panel_or_main("guide")

    def _update_poelab_link_visibility(self, zone_id: str | None):
        """本体ガイド欄のPoELabボタンを対象3エリアだけに表示する。"""
        self._current_poelab_type = self.POELAB_ZONE_TYPES.get(zone_id)
        self.poelab_link_button.setVisible(self._current_poelab_type is not None)
        if self._current_poelab_type is None:
            self._reset_poelab_link_button()

    def _update_area_note(self, zone_name: str, zone_id: str | None):
        self._current_zone_id = zone_id
        self._current_zone_name = zone_name
        self.area_note_edit_button.setEnabled(bool(zone_id))
        if not zone_id:
            self._current_area_note = ""
            self.area_note_label.clear()
            self.area_note_frame.hide()
            return
        try:
            content = get_area_note(self.poe_version, zone_id)
        except ValueError as exc:
            self._current_area_note = ""
            self.area_note_label.clear()
            self.area_note_frame.hide()
            self.area_note_edit_button.setEnabled(False)
            QMessageBox.warning(self, "エリアメモ読込エラー", str(exc))
            return
        self._current_area_note = content
        self.area_note_label.setText(content.replace("\n", "<br>"))
        self.area_note_frame.setVisible(bool(content.strip()))

    def open_area_note_editor(self):
        zone_id = self._current_zone_id
        if not zone_id:
            return
        dialog = AreaNoteDialog(self, self._current_zone_name or zone_id, self._current_area_note)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            set_area_note(self.poe_version, zone_id, dialog.content())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "エリアメモ保存エラー", str(exc))
            return
        self._update_area_note(self._current_zone_name, zone_id)

    def open_daily_poelab(self):
        """当日のDaily Notes URLだけを取得し、標準ブラウザで開く。"""
        lab_type = self._current_poelab_type
        if not lab_type or not self.poelab_link_button.isEnabled():
            return
        self.poelab_link_button.setEnabled(False)
        self.poelab_link_button.setText("🏛️ PoELabリンクを取得中…")

        def resolve():
            try:
                self.poelab_url_resolved.emit(find_daily_notes_url(lab_type))
            except Exception as exc:
                self.poelab_url_failed.emit(str(exc))

        threading.Thread(target=resolve, daemon=True).start()

    def _open_resolved_poelab_url(self, url: str):
        QDesktopServices.openUrl(QUrl(url))
        self._reset_poelab_link_button()

    def _handle_poelab_url_error(self, _message: str):
        # サイト側の構造変更や一時的な通信失敗時も、PoELab自体には到達できるようにする。
        QDesktopServices.openUrl(QUrl(POELAB_HOME))
        self._reset_poelab_link_button()

    def _reset_poelab_link_button(self):
        self.poelab_link_button.setEnabled(True)
        self.poelab_link_button.setText("🏛️ 今日のPoELabを開く")
    
    def _is_mini_navi_available(self):
        """みになびは現状PoE1専用。PoE2では未実装なので入口を出さない。"""
        return self.poe_version == POE1

    def _mini_navi_toggle_text(self):
        overlay_config = self.config.get("mini_guide_overlay", {})
        enabled = bool(overlay_config.get("enabled", False))
        return "みになび ON" if enabled else "みになび OFF"

    def _refresh_mini_navi_toggle(self):
        if not hasattr(self, "mini_navi_toggle_btn"):
            return
        self.mini_navi_toggle_btn.setText(self._mini_navi_toggle_text())
        self.mini_navi_toggle_btn.setVisible(self._is_mini_navi_available() and self.guide_expanded)

    def toggle_mini_navi_overlay(self):
        if not self._is_mini_navi_available():
            if hasattr(self, "mini_navi_overlay"):
                self.mini_navi_overlay.hide()
            self._refresh_mini_navi_toggle()
            return
        overlay_config = self.config.setdefault("mini_guide_overlay", {})
        overlay_config["enabled"] = not bool(overlay_config.get("enabled", False))
        ConfigManager.save_config(self.config)
        if hasattr(self, "mini_navi_overlay"):
            self.mini_navi_overlay.apply_settings(refresh_window_flags=True)
        self._refresh_mini_navi_toggle()
        if self.current_zone:
            if self._is_town_zone(self.current_zone):
                self.mini_navi_overlay.show_last_content_or_waiting()
                return
            zone_id = self._get_zone_id(self.current_zone)
            visit_num = self.zone_visit_counts.get(zone_id or self.current_zone, 1)
            self._update_guide_and_map(self.current_zone, zone_id, visit_num)

    def _guide_detail_level_toggle_text(self):
        """現在のガイド表示レベルからトグルボタン文言を返す。"""
        if self.config.get("guide_detail_level", "beginner") == "intermediate":
            return "要点版ガイド"
        return "詳細版ガイド"

    def _refresh_guide_detail_level_toggle(self):
        """PoE2専用のガイド表示レベルトグル状態を反映する。"""
        if not hasattr(self, "guide_detail_level_toggle_btn"):
            return
        self.guide_detail_level_toggle_btn.setText(self._guide_detail_level_toggle_text())
        self.guide_detail_level_toggle_btn.setVisible(
            self.poe_version == POE2 and self.guide_expanded
        )

    def toggle_guide_detail_level(self):
        """詳細版ガイド / 要点版ガイドを即時切り替えする。"""
        current = self.config.get("guide_detail_level", "beginner")
        self.config["guide_detail_level"] = "intermediate" if current != "intermediate" else "beginner"
        self.config["guide_detail_level_selected"] = True
        ConfigManager.save_config(self.config)
        self._refresh_guide_detail_level_toggle()

        if self.current_zone:
            zone_id = self._get_zone_id(self.current_zone)
            visit_num = self.zone_visit_counts.get(zone_id or self.current_zone, 1)
            self._update_guide_and_map(self.current_zone, zone_id, visit_num)

    
    def toggle_map_section(self):
        """マップセクションの折りたたみ/展開"""
        self.map_section_expanded = not self.map_section_expanded
        if self.map_section_expanded:
            self.map_thumbnail.setVisible(len(self.map_thumbnail.current_paths) > 0)
        else:
            self.map_thumbnail.setVisible(False)
        self.map_toggle_btn.setText("▼ マップ" if self.map_section_expanded else "▶ マップ")
        self._adjust_panel_or_main("map")
    
    def _apply_guide_visibility(self):
        """ガイドの表示/非表示を適用"""
        if self.guide_expanded:
            # 全体展開時は各セクションの個別状態に従う
            self.guide_info_frame.setVisible(self.zone_header_expanded)
            self.guide_text_frame.setVisible(self.guide_text_expanded)
            has_maps = len(self.map_thumbnail.current_paths) > 0
            self.map_thumbnail.setVisible(self.map_section_expanded and has_maps)
            # サブトグルボタンも表示
            self.zone_header_toggle_btn.setVisible(True)
            self.guide_text_toggle_btn.setVisible(True)
            self._refresh_guide_detail_level_toggle()
            if not self._is_panel_detached("map"):
                self.map_toggle_btn.setVisible(True)
        else:
            # 全体折りたたみ時は3セクションすべて非表示
            self.guide_info_frame.setVisible(False)
            self.guide_text_frame.setVisible(False)
            if not self._is_panel_detached("map") and not self._is_panel_detached("guide"):
                self.map_thumbnail.setVisible(False)
            # サブトグルボタンも非表示
            self.zone_header_toggle_btn.setVisible(False)
            self.guide_text_toggle_btn.setVisible(False)
            if hasattr(self, "guide_detail_level_toggle_btn"):
                self.guide_detail_level_toggle_btn.setVisible(False)
            if not self._is_panel_detached("map") and not self._is_panel_detached("guide"):
                self.map_toggle_btn.setVisible(False)
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
        self._set_timer_ready(False)
        if not self.is_running:
            self.start_time = time.time()
            self.timer.start(10)
            self.is_running = True
            if self.current_zone:
                self.segment_recorder.record_entry(
                    self._get_zone_id(self.current_zone) or self.current_zone,
                    self.current_zone,
                    self.get_elapsed_time(),
                )
                self._update_segment_summary()
        self._refresh_ready_button()
            
    def stop_timer(self):
        if self.is_running:
            self.timer.stop()
            self.accumulated_time += time.time() - self.start_time
            self.is_running = False
            self._save_timer_state()
        self._refresh_ready_button()
            
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
            LapRecorder.save_run(self.lap_times, total, segments=self.segment_recorder.segments)
        
        self._set_timer_ready(False)
        self.stop_timer()
        self.accumulated_time = 0.0
        self.update_text(0.0)
        self.reset_laps()
        self._clear_saved_timer()
        self._refresh_ready_button()

    def _has_timer_record(self):
        """自動開始を禁止すべき既存タイマー記録があるか。"""
        return (
            self.accumulated_time > 0
            or any(t is not None for t in self.lap_times)
            or bool(getattr(self, "lap_record_order", []))
            or bool(getattr(getattr(self, "segment_recorder", None), "segments", []))
        )

    def _can_set_timer_ready(self):
        watcher = getattr(self, "log_watcher", None)
        return (
            self.poe_version == POE1
            and not self.is_running
            and not self._has_timer_record()
            and watcher is not None
            and watcher.is_active
        )

    def _can_use_ready_button(self):
        """Ready開始または既存記録の注意表示を行えるか。"""
        watcher = getattr(self, "log_watcher", None)
        return (
            self.poe_version == POE1
            and not self.is_running
            and watcher is not None
            and watcher.is_active
        )

    def _ready_button_style(self):
        if self.timer_ready:
            return """
                QPushButton {
                    background-color: #2e7d32;
                    color: white;
                    border: 1px solid #66bb6a;
                    border-radius: 4px;
                    padding: 5px 12px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #388e3c; }
            """
        return Styles.BUTTON

    def _refresh_ready_button(self):
        if not hasattr(self, "ready_btn"):
            return
        self.ready_btn.setText("Ready ✓" if self.timer_ready else "Ready")
        self.ready_btn.setStyleSheet(self._ready_button_style())
        self.ready_btn.setEnabled(self.timer_ready or self._can_use_ready_button())
        if self.timer_ready:
            tooltip = "黄昏の岸辺への入場を待機中（クリックで解除）"
        elif self.poe_version != POE1:
            tooltip = "Ready自動開始はPoE1専用です"
        elif self.is_running or self._has_timer_record():
            tooltip = "ReadyにするにはタイマーをResetしてください"
        else:
            tooltip = "Client.txtを監視できる時だけReadyを使用できます"
        self.ready_btn.setToolTip(tooltip)

    def _set_timer_ready(self, ready: bool):
        ready = bool(ready)
        if ready and not self._can_set_timer_ready():
            ready = False
        self.timer_ready = ready
        watcher = getattr(self, "log_watcher", None)
        if watcher is not None:
            interval = 100 if ready else self._normal_log_poll_interval_ms
            watcher.set_poll_interval(interval)
        self._refresh_ready_button()

    def toggle_timer_ready(self):
        if not self.timer_ready and self._has_timer_record():
            QMessageBox.warning(
                self,
                "Readyにできません",
                "タイマーの記録が残っています。\n"
                "問題ないか確認のうえ、リセットしてからReadyしてください。",
            )
            return
        self._set_timer_ready(not self.timer_ready)

    def _on_actual_zone_entered_for_auto_start(self, zone_name: str):
        """LiveSplit準拠: 明示的な黄昏の岸辺入場ログで一度だけ開始する。"""
        if not self.timer_ready:
            return
        if (
            self._restoring
            or self.poe_version != POE1
            or self.is_running
            or self._has_timer_record()
        ):
            self._set_timer_ready(False)
            return
        if zone_name not in ("黄昏の岸辺", "The Twilight Strand"):
            return
        # zone_enteredの通常処理より先に呼ばれるため、開始区間を前エリアにしない。
        self.current_zone = zone_name
        self.start_timer()
    
    def reset_laps(self):
        """全ラップをリセット"""
        self.lap_labels = get_lap_labels(self.poe_version)
        self.lap_times = [None] * len(self.lap_labels)
        self.segment_recorder.reset()
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
    
    def _timer_state_key(self):
        # 旧config.json保存形式の移行用キー。新規保存はtimer_poe*.jsonへ行う。
        return f"saved_timer::{get_timer_filename(self.poe_version)}"

    def _timer_state_path(self):
        return ConfigManager.get_user_data_dir() / get_timer_filename(self.poe_version)

    def _timer_state_payload(self):
        return {
            "accumulated_time": self.accumulated_time,
            "lap_times": self.lap_times,
            "lap_record_order": self.lap_record_order,
            "current_act": self.current_act,
            "segments": getattr(self, "segment_recorder", SegmentRecorder()).segments,
        }

    def _save_timer_state_payload(self, payload):
        path = self._timer_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path

    def _load_timer_state_payload(self):
        path = self._timer_state_path()
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except Exception as e:
            print(f"[WARN] タイマー状態の読み込みに失敗しました [{self.poe_version}]: {e}")
            return None

    def _migrate_legacy_timer_state_from_config(self):
        key = self._timer_state_key()
        saved = self.config.get(key)
        if not isinstance(saved, dict):
            return None

        # timer_poe*.json がまだ無い場合だけ旧config内タイマーを移行する。
        if not self._timer_state_path().exists():
            self._save_timer_state_payload(saved)

        # 以後config.jsonにタイマー状態を残さない。
        del self.config[key]
        ConfigManager.save_config(self.config)
        return saved

    def _save_timer_state(self):
        """タイマー状態をPoEバージョン別のtimer_poe*.jsonへ保存"""
        self._save_timer_state_payload(self._timer_state_payload())
        print(f"[INFO] タイマー状態を保存しました [{self.poe_version}] (経過: {self.accumulated_time:.1f}秒, Act{self.current_act})")
    
    def _clear_saved_timer(self):
        """現在のPoEバージョンの保存済みタイマー状態をクリア"""
        path = self._timer_state_path()
        if path.exists():
            try:
                path.unlink()
            except Exception as e:
                print(f"[WARN] タイマー状態の削除に失敗しました [{self.poe_version}]: {e}")
        key = self._timer_state_key()
        if key in self.config:
            del self.config[key]
            ConfigManager.save_config(self.config)
    
    def _restore_timer_state(self):
        """起動時に現在のPoEバージョンの保存済みタイマー状態を復元"""
        saved = self._load_timer_state_payload() or self._migrate_legacy_timer_state_from_config()
        if not saved:
            return
        self.accumulated_time = saved.get("accumulated_time", 0.0)
        self.lap_labels = get_lap_labels(self.poe_version)
        self.lap_times = saved.get("lap_times", [None] * len(self.lap_labels))
        while len(self.lap_times) < len(self.lap_labels):
            self.lap_times.append(None)
        self.lap_record_order = [lap for lap in saved.get("lap_record_order", []) if 1 <= lap <= len(self.lap_labels)]
        self.current_act = saved.get("current_act", 1)
        self.segment_recorder = SegmentRecorder(saved.get("segments", []))
        if self.accumulated_time > 0:
            self.update_text(self.accumulated_time)
            self.update_lap_display()
            if self.poe_version == POE1 and self.current_act > 5:
                self._set_part2(True)
            print(f"[INFO] タイマー状態を復元しました [{self.poe_version}] (経過: {self.accumulated_time:.1f}秒, Act{self.current_act})")
    
    def _rebuild_lap_ui(self):
        while self.lap_content_layout.count():
            item = self.lap_content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

        self.lap_label_widgets = []
        for label in self.lap_labels:
            lap_layout = QHBoxLayout()
            lap_layout.setSpacing(5)

            act_label = QLabel(label)
            act_label.setFixedWidth(90)
            time_label = QLabel("--:--.--")
            time_label.setFixedWidth(100)
            split_label = QLabel("(--:--.--)")
            split_label.setFixedWidth(100)

            lap_layout.addWidget(act_label)
            lap_layout.addWidget(time_label)
            lap_layout.addWidget(split_label)
            lap_layout.addStretch()

            self.lap_content_layout.addLayout(lap_layout)
            self.lap_label_widgets.append((act_label, time_label, split_label))

        if hasattr(self, "segment_summary_label"):
            self.lap_content_layout.addWidget(self.segment_summary_label)

    def _refresh_current_lap_index(self):
        for idx, lap in enumerate(self.lap_times, start=1):
            if lap is None:
                self.current_act = idx
                return
        self.current_act = len(self.lap_times)

    def record_lap(self):
        """現在のAct/幕間のラップを記録"""
        if self.current_act > len(self.lap_times):
            return
        
        elapsed = self.get_elapsed_time()
        self.lap_times[self.current_act - 1] = elapsed
        if self.current_act not in self.lap_record_order:
            self.lap_record_order.append(self.current_act)
        
        if self.current_act < len(self.lap_times):
            self.current_act += 1
        else:
            LapRecorder.save_run(self.lap_times, elapsed, segments=self.segment_recorder.segments)
        
        self.update_lap_display()
        # ジェムトラッカーをAct変更に連動
        if self._has_pob_import_data():
            self._update_gem_tracker()

    def record_lap_at(self, lap_num: int):
        """指定ラップ枠を直接記録（PoE2幕間など自由順用）"""
        if lap_num < 1 or lap_num > len(self.lap_times):
            return
        if self.lap_times[lap_num - 1] is not None:
            return
        elapsed = self.get_elapsed_time()
        self.lap_times[lap_num - 1] = elapsed
        if lap_num not in self.lap_record_order:
            self.lap_record_order.append(lap_num)
        if all(lap is not None for lap in self.lap_times):
            LapRecorder.save_run(self.lap_times, elapsed, segments=self.segment_recorder.segments)
        else:
            self._refresh_current_lap_index()
        self.update_lap_display()
        if self._has_pob_import_data():
            self._update_gem_tracker()
    
    def undo_lap(self):
        """直前のラップを取り消し"""
        if self.current_act > 1 and self.lap_times[self.current_act - 2] is not None:
            lap_num = self.current_act - 1
            self.lap_times[self.current_act - 2] = None
            if lap_num in self.lap_record_order:
                self.lap_record_order.remove(lap_num)
            self.current_act -= 1
            self.update_lap_display()
        elif self.current_act == 1 and self.lap_times[0] is not None:
            self.lap_times[0] = None
            if 1 in self.lap_record_order:
                self.lap_record_order.remove(1)
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

    def _update_segment_summary(self):
        """直近区間と遅い区間をコンパクトに表示する。"""
        if not hasattr(self, "segment_summary_label"):
            return

        summary = self.segment_recorder.summary()
        latest = summary["latest"]
        if not latest:
            self.segment_summary_label.setText("区間: エリア移動を待機中")
            return

        latest_name = latest.get("zone_name") or latest.get("zone_id", "不明")
        latest_text = f"直近: {latest_name} {self.format_lap_time(latest.get('duration', 0.0))}"
        slowest_text = " / ".join(
            f"{segment.get('zone_name') or segment.get('zone_id', '不明')} {self.format_lap_time(segment.get('duration', 0.0))}"
            for segment in summary["slowest"]
        )
        self.segment_summary_label.setText(
            f"{latest_text}\n遅い区間: {slowest_text}"
        )

    def update_lap_display(self):
        """ラップタイム表示を更新"""
        self._update_segment_summary()
        for i, (act_lbl, time_lbl, split_lbl) in enumerate(self.lap_label_widgets):
            act_name = self.lap_labels[i]
            lap_time = self.lap_times[i] if i < len(self.lap_times) else None

            if lap_time is not None:
                lap_num = i + 1
                prev_time = None
                if lap_num in self.lap_record_order:
                    order_idx = self.lap_record_order.index(lap_num)
                    if order_idx > 0:
                        prev_lap_num = self.lap_record_order[order_idx - 1]
                        prev_time = self.lap_times[prev_lap_num - 1]
                split_time = lap_time if prev_time is None else lap_time - prev_time
            else:
                split_time = None

            display_name = act_name

            if lap_time is not None:
                act_lbl.setText(display_name)
                time_lbl.setText(self.format_lap_time(lap_time))
                split_lbl.setText(f"({self.format_lap_time(split_time)})")
                act_lbl.setStyleSheet(Styles.LAP_ITEM_COMPLETED)
                time_lbl.setStyleSheet(Styles.LAP_ITEM_COMPLETED)
                split_lbl.setStyleSheet(Styles.LAP_ITEM_COMPLETED)
            elif (i + 1) == self.current_act:
                act_lbl.setText(f"⇒ {display_name}")
                time_lbl.setText("進行中...")
                split_lbl.setText("")
                act_lbl.setStyleSheet(Styles.LAP_ITEM_CURRENT)
                time_lbl.setStyleSheet(Styles.LAP_ITEM_CURRENT)
                split_lbl.setStyleSheet(Styles.LAP_ITEM_CURRENT)
            else:
                act_lbl.setText(display_name)
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
            
            self.hotkey_map = {}
            for action, default in [("start_stop", "F1"), ("reset", "F2"), ("lap", "F3"),
                                     ("undo_lap", "F4"), ("click_through", DEFAULT_CLICK_THROUGH_HOTKEY), ("logout", "F5"),
                                     ("hideout", "F11"), ("monastery", "F12"),
                                     ("search_string_test", "none"), ("poetore_capture", "alt+d")]:
                key = hotkeys.get(action, default)
                if key and key != "none":
                    self.hotkey_map[_listener_hotkey_name(key)] = action
            self._gem_shop_search_key = _listener_hotkey_name(hotkeys.get("gem_shop_search", "CapsLock"))
            
            print(f"Registering hotkeys: {self.hotkey_map}")
            
            pressed_modifiers = set()
            triggered_combos = set()

            def on_press(key):
                try:
                    key_name = _hotkey_key_name(key)
                    if key_name is None:
                        return

                    if key_name == self._gem_shop_search_key:
                        self.hotkey_signal.emit("gem_shop_search_pressed")
                        return
                    
                    if key_name in {"alt", "alt_l", "alt_r", "alt_gr"}:
                        pressed_modifiers.add("alt")
                    elif key_name in {"ctrl", "ctrl_l", "ctrl_r"}:
                        pressed_modifiers.add("ctrl")
                    elif key_name in {"shift", "shift_l", "shift_r"}:
                        pressed_modifiers.add("shift")

                    combo = "+".join([modifier for modifier in ("ctrl", "alt", "shift") if modifier in pressed_modifiers] + [key_name])
                    if combo in self.hotkey_map:
                        if combo not in triggered_combos:
                            triggered_combos.add(combo)
                            self.hotkey_signal.emit(self.hotkey_map[combo])
                        return

                    # 単独ホットキーマップをチェック
                    if key_name in self.hotkey_map:
                        command = self.hotkey_map[key_name]
                        print(f"[HOTKEY DEBUG] key={key_name} command={command} search_in_progress={getattr(self, '_search_paste_in_progress', False)}")
                        self.hotkey_signal.emit(command)
                except Exception as e:
                    print(f"Hotkey error: {e}")

            def on_release(key):
                key_name = _hotkey_key_name(key)
                if key_name is None:
                    return
                if key_name == self._gem_shop_search_key:
                    self.hotkey_signal.emit("gem_shop_search_released")
                if key_name in {"alt", "alt_l", "alt_r", "alt_gr"}:
                    pressed_modifiers.discard("alt")
                elif key_name in {"ctrl", "ctrl_l", "ctrl_r"}:
                    pressed_modifiers.discard("ctrl")
                elif key_name in {"shift", "shift_l", "shift_r"}:
                    pressed_modifiers.discard("shift")
                triggered_combos.clear()
            
            self.keyboard_listener = pynput_keyboard.Listener(on_press=on_press, on_release=on_release)
            self.keyboard_listener.start()
            
        except Exception as e:
            print(f"Failed to register hotkeys: {e}")

    def handle_hotkey(self, command):
        print(f"[HOTKEY DEBUG] handle command={command} search_in_progress={getattr(self, '_search_paste_in_progress', False)}")
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
        elif command == "logout":
            self.execute_logout()
        elif command == "hideout":
            self.execute_chat_command("/hideout")
        elif command == "monastery":
            self.execute_chat_command("/monastery")
        elif command == "search_string_test":
            self.open_search_string_paste_test()
        elif command == "poetore_capture":
            self.capture_poetore_item()
        elif command == "gem_shop_search_pressed":
            self._start_gem_shop_search_hold()
        elif command == "gem_shop_search_released":
            self._finish_gem_shop_search_hold()

    def _start_gem_shop_search_hold(self):
        """長押し判定を開始する。キーリピートではタイマーを延長しない。"""
        generation = self._gem_shop_search_hold.start()
        QTimer.singleShot(self._gem_shop_search_hold_delay_ms(), lambda: self._run_gem_shop_search_hold(generation))

    def _finish_gem_shop_search_hold(self):
        self._gem_shop_search_hold.release()

    def _gem_shop_search_hold_delay_ms(self) -> int:
        return round(float(self.config.get("gem_shop_search_hold_seconds", 0.4)) * 1000)

    def _gem_shop_search_query(self) -> str:
        if self.poe_version != POE1 or not hasattr(self, "gem_tracker"):
            return ""
        return build_act_vendor_gem_query(
            self.gem_tracker._acquisition_plan,
            self.gem_tracker._current_act,
            load_gem_names_ja(),
            self.config.get("gem_shop_search_include_reward_purchases", True),
            self.config.get("gem_shop_search_term_overrides", {}),
            checked_gems=self.gem_tracker.get_checked_gems(),
        )

    def _refresh_gem_shop_search_preview(self):
        if not hasattr(self, "gem_shop_search_preview_label"):
            return
        query = self._gem_shop_search_query()
        self.gem_shop_search_preview_label.setText(format_gem_shop_search_preview(query))
        self.gem_shop_search_copy_btn.setEnabled(bool(query))

    def copy_gem_shop_search_query(self):
        """現在ActのRegexだけをクリップボードへコピーする。"""
        query = self._gem_shop_search_query()
        if not query:
            self._refresh_gem_shop_search_preview()
            return
        QApplication.clipboard().setText(query)
        self.gem_shop_search_copy_btn.setText("コピー済み")
        QTimer.singleShot(1200, lambda: self.gem_shop_search_copy_btn.setText("Regexをコピー"))

    def _show_gem_shop_search_status(self, message: str):
        QToolTip.showText(QCursor.pos(), message, self, QRect(), 2500)

    def _run_gem_shop_search_hold(self, generation: int):
        if not self._gem_shop_search_hold.consume_if_current(generation):
            return
        query = self._gem_shop_search_query()
        target_hwnd = get_foreground_window() if query else None
        poe_is_foreground = bool(target_hwnd and is_path_of_exile_window(target_hwnd))
        act = getattr(getattr(self, "gem_tracker", None), "_current_act", 0)
        self._show_gem_shop_search_status(
            get_gem_shop_search_feedback(act, query, poe_is_foreground)
        )
        if not query or not poe_is_foreground:
            return
        self.paste_text_to_poe_search(query, target_hwnd=target_hwnd)

    def open_search_string_paste_test(self):
        """ベンダー検索プリセット→元ウィンドウ復帰→検索欄貼り付け。"""
        previous_target_hwnd = None

        def close_existing_dialog(dialog):
            if dialog is None:
                return None
            try:
                target = getattr(dialog, "target_hwnd", None)
                dialog.hide()
                dialog.close()
                return target
            except RuntimeError:
                # QtのC++側オブジェクトが既に削除済みの場合がある。
                return None

        # 参照が外れた古いメニューも含め、残っている検索メニューを全て閉じる。
        # F4連打時に複数表示されるのを防ぐため、親参照だけに頼らない。
        app = QApplication.instance()
        if app is not None:
            for widget in list(app.topLevelWidgets()):
                if isinstance(widget, SearchStringPasteTestDialog):
                    previous_target_hwnd = previous_target_hwnd or close_existing_dialog(widget)

        existing_dialog = getattr(self, "_search_string_test_dialog", None)
        previous_target_hwnd = previous_target_hwnd or close_existing_dialog(existing_dialog)
        self._search_string_test_dialog = None

        # 既存メニュー表示中にもう一度ホットキーを押した場合、前面ウィンドウは旧メニューや
        # みになび/鍵ボタンになりやすい。自プロセスのウィンドウは復帰先にしない。
        target_hwnd = previous_target_hwnd or self._external_foreground_window()
        if target_hwnd and int(target_hwnd) in self._own_top_level_hwnds():
            target_hwnd = get_next_visible_window_after(target_hwnd, skip_current_process=True)
        if target_hwnd:
            self._last_search_target_hwnd = target_hwnd
        choices = self._load_vendor_search_presets(enabled_only=True)
        self._debug_search(f"open menu target={target_hwnd} title={self._window_title(target_hwnd)!r} choices={choices!r}")
        if not choices:
            QMessageBox.information(self, "ベンダー検索", "有効なベンダー検索プリセットがありません。")
            return

        # 設定画面などのモーダルダイアログが開いている場合、メインウィンドウを親にした
        # ツールウィンドウは表示されても操作できない。現在のモーダルを親にして前面操作可能にする。
        app = QApplication.instance()
        popup_parent = app.activeModalWidget() if app is not None else None
        if popup_parent is None or popup_parent is self:
            popup_parent = self

        self._search_string_test_dialog = SearchStringPasteTestDialog(target_hwnd, choices, popup_parent, owner=self)
        self._search_string_test_dialog.show()
        self._search_string_test_dialog.raise_()
        self._search_string_test_dialog.activateWindow()

    def _debug_search(self, message: str):
        print(f"[SEARCH DEBUG] {message}")

    def _set_clipboard_text_debug(self, reason: str, text: str):
        preview = text if len(text) <= 160 else text[:157] + "..."
        print(f"[CLIPBOARD DEBUG] setText reason={reason} text={preview!r}")
        if "monastery" in text.lower():
            import traceback
            print("[CLIPBOARD DEBUG] !!! monastery text is being set; stack follows")
            print("".join(traceback.format_stack(limit=12)).rstrip())
        QApplication.clipboard().setText(text)

    def _window_title(self, hwnd):
        if not hwnd or sys.platform != "win32":
            return ""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextLengthW.restype = ctypes.c_int
            user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            length = user32.GetWindowTextLengthW(wintypes.HWND(int(hwnd)))
            if length <= 0:
                return ""
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(wintypes.HWND(int(hwnd)), buffer, length + 1)
            return buffer.value
        except Exception as exc:
            return f"<title error: {exc}>"

    def _clipboard_text_preview(self):
        try:
            text = QApplication.clipboard().text()
            if len(text) > 120:
                return text[:117] + "..."
            return text
        except Exception as exc:
            return f"<clipboard error: {exc}>"

    def _own_top_level_hwnds(self) -> set[int]:
        app = QApplication.instance()
        own_hwnds = set()
        if app is not None:
            for widget in app.topLevelWidgets():
                try:
                    own_hwnds.add(int(widget.winId()))
                except RuntimeError:
                    pass
        return own_hwnds

    def _external_foreground_window(self):
        foreground = get_foreground_window()
        if foreground and int(foreground) in self._own_top_level_hwnds():
            return get_next_visible_window_after(foreground, skip_current_process=True)
        return foreground

    def _vendor_search_presets_path(self, poe_version: str | None = None):
        version = poe_version or getattr(self, "poe_version", POE2)
        if version == POE1:
            return str(ConfigManager.get_user_data_path("vendor_search_presets_poe1.json"))
        # PoE2は旧 vendor_search_presets.json から新ファイルへ一度だけ移行し、以後は新名で入出力する。
        return str(ConfigManager.migrate_renamed_user_file(
            "vendor_search_presets.json",
            "vendor_search_presets_poe2.json",
        ))

    def _load_vendor_search_presets(self, enabled_only=False):
        path = self._vendor_search_presets_path(self.poe_version)
        presets = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                presets = data.get("presets", [])
            except Exception as e:
                print(f"[VENDOR SEARCH] Failed to load presets: {e}")
        if not presets:
            presets = VendorSearchPresetDialog.POE1_DEFAULT_PRESETS if self.poe_version == POE1 else VendorSearchPresetDialog.DEFAULT_PRESETS
        normalized = []
        for preset in presets:
            name = str(preset.get("name", "")).strip()
            query = str(preset.get("query", "")).strip()
            enabled = bool(preset.get("enabled", True))
            if not query:
                continue
            if enabled_only and not enabled:
                continue
            normalized_preset = {"name": name or query, "query": query, "enabled": enabled}
            if self.poe_version == POE1 and preset.get("include_current_act_gems", False):
                normalized_preset["gem_query_provider"] = self._gem_shop_search_query
            normalized.append(normalized_preset)
        return normalized

    def open_vendor_search_presets(self):
        """ベンダー検索プリセット編集ダイアログをトグル表示"""
        if hasattr(self, '_vendor_search_dialog') and self._vendor_search_dialog is not None:
            if self._vendor_search_dialog.isVisible():
                self._vendor_search_dialog.close()
                return
            self._vendor_search_dialog.show()
            self._vendor_search_dialog.raise_()
            return
        self._vendor_search_dialog = VendorSearchPresetDialog(
            self,
            presets_path=self._vendor_search_presets_path(self.poe_version),
            poe_version=self.poe_version,
            gem_shop_query_provider=self._gem_shop_search_query if self.poe_version == POE1 else None,
        )
        self._vendor_search_dialog.show()

    # --- PoE検索欄貼り付け ---
    def paste_text_to_poe_search(self, text: str, target_hwnd=None):
        """対象ウィンドウへ戻して Ctrl+F → 検索文字列貼り付けを行う。"""
        if not text:
            return
        target_hwnd = target_hwnd or getattr(self, "_last_search_target_hwnd", None)
        if not target_hwnd:
            target_hwnd = self._external_foreground_window()
        elif int(target_hwnd) in self._own_top_level_hwnds():
            target_hwnd = get_next_visible_window_after(target_hwnd, skip_current_process=True)
        clipboard = QApplication.clipboard()
        self._set_clipboard_text_debug("paste_text_to_poe_search", text)
        QApplication.processEvents()
        time.sleep(0.05)

        if not target_hwnd:
            QMessageBox.warning(self, "検索文字列の貼り付け", "復帰先ウィンドウを取得できませんでした。文字列はクリップボードへコピー済みです。")
            return

        if not focus_window(target_hwnd, wait_seconds=0.45):
            QMessageBox.warning(
                self,
                "検索文字列の貼り付け",
                "元のウィンドウを前面化できませんでした。文字列はクリップボードへコピー済みです。",
            )
            return

        self._last_search_target_hwnd = target_hwnd
        QTimer.singleShot(450, lambda: self._paste_to_poe_search_field(text))

    def _paste_to_poe_search_field(self, text: str):
        try:
            controller = pynput_keyboard.Controller()
            ctrl = pynput_keyboard.Key.ctrl

            def tap(key):
                controller.press(key)
                controller.release(key)

            with controller.pressed(ctrl):
                tap('f')
            time.sleep(0.20)
            with controller.pressed(ctrl):
                tap('v')
            time.sleep(0.08)
            print(f"[POE SEARCH] pasted: {text}")
        except Exception as exc:
            print(f"[POE SEARCH] paste failed: {exc}")

    def search_gem_in_poe(self, gem_name: str):
        """ジェム取得リストのジェム名クリックからPoE検索欄へ貼り付ける。"""
        self.paste_text_to_poe_search(gem_name)

    # --- チャットコマンド ---
    def execute_chat_command(self, command: str):
        """PoEのチャットにコマンドを送信する。IMEの入力モードに左右されないよう貼り付けで送る。"""
        if not command:
            return
        print(f"[CHAT COMMAND] Requested: {command} search_in_progress={getattr(self, '_search_paste_in_progress', False)} clipboard_before={self._clipboard_text_preview()!r}")
        if getattr(self, "_search_paste_in_progress", False):
            print(f"[CHAT COMMAND] Ignored during search paste: {command}")
            return
        try:
            clipboard = QApplication.clipboard()
            original_mime = self._clone_clipboard_mime_data(clipboard.mimeData())
            self._set_clipboard_text_debug("execute_chat_command", command)

            controller = pynput_keyboard.Controller()

            def tap(key):
                controller.press(key)
                controller.release(key)

            tap(pynput_keyboard.Key.enter)
            time.sleep(0.05)
            with controller.pressed(pynput_keyboard.Key.ctrl):
                tap('v')
            time.sleep(0.05)
            tap(pynput_keyboard.Key.enter)

            # Ctrl+V処理が終わったあと、ユーザーのクリップボードをできるだけ元に戻す。
            QTimer.singleShot(500, lambda: clipboard.setMimeData(original_mime))
            print(f"[CHAT COMMAND] Sent: {command}")
        except Exception as e:
            print(f"[CHAT COMMAND] Failed: {e}")

    def _clone_clipboard_mime_data(self, source):
        """QClipboardの内容を復元用にコピーする。主要な形式を保持する。"""
        clone = QMimeData()
        if source is None:
            return clone
        for fmt in source.formats():
            clone.setData(fmt, source.data(fmt))
        if source.hasText():
            clone.setText(source.text())
        if source.hasHtml():
            clone.setHtml(source.html())
        if source.hasUrls():
            clone.setUrls(source.urls())
        if source.hasImage():
            clone.setImageData(source.imageData())
        if source.hasColor():
            clone.setColorData(source.colorData())
        return clone

    # --- ログアウト（TCP切断） ---
    def execute_logout(self):
        """TCP切断によるログアウト"""
        if not self.config.get("logout_enabled", True):
            return
        from src.utils.tcp_disconnect import disconnect_poe
        success, msg = disconnect_poe()
        if success:
            print(f"[LOGOUT] {msg}")
        else:
            print(f"[LOGOUT] Failed: {msg}")
            if "管理者権限" in msg:
                QMessageBox.warning(
                    self, "ログアウトマクロ",
                    "ログアウト機能を使用するためには、ぽえなびを「管理者として実行」する必要があります"
                )

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
        self._update_click_through_label()
        hotkey = self.config.get('hotkeys', {}).get('click_through', DEFAULT_CLICK_THROUGH_HOTKEY)
        if self.click_through:
            print(f"[INFO] クリックスルー ON（{hotkey}で解除）")
        else:
            print(f"[INFO] クリックスルー OFF（{hotkey}でON）")

    def _update_click_through_label(self):
        """クリックスルー状態の案内表示を更新する。"""
        if not hasattr(self, "click_through_label"):
            return
        hotkey = self.config.get('hotkeys', {}).get('click_through', DEFAULT_CLICK_THROUGH_HOTKEY)
        if getattr(self, 'click_through', False):
            self.click_through_label.setText(f"🔓 クリックスルーON（{hotkey}で解除）")
            self.click_through_label.setStyleSheet("color: #ff9944; font-size: 14px; font-weight: bold;")
        else:
            self.click_through_label.setText(f"クリックスルーOFF（{hotkey}でON）")
            self.click_through_label.setStyleSheet("color: rgba(176, 255, 123, 0.45); font-size: 12px; font-weight: normal;")
        self.click_through_label.setVisible(True)

    # --- レベルガイド ---
    def _is_town_zone(self, zone_name: str) -> bool:
        """街エリアかどうか判定"""
        town_zones = self.town_zones_by_version.get(self.poe_version, [])
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
    
    def _format_zone_display_name(self, zone_name: str) -> str:
        """表示用のエリア名表記を整える"""
        return re.sub(r"^アクト\s*([0-9０-９]+)$", r"Act \1", zone_name)

    def _sync_gem_tracker_act_from_zone_act(self, act_name: str | None):
        """現在エリアのActにジェム取得リストを自動追従させる。"""
        if self.poe_version != POE1 or not act_name:
            return
        m = re.search(r"Act\s*(\d+)", act_name)
        if not m:
            return
        act = int(m.group(1))
        if not 1 <= act <= 10:
            return
        self.current_zone_act = act
        if hasattr(self, "gem_tracker"):
            self.gem_tracker.set_current_act(act)
        self._refresh_gem_shop_search_preview()

    def on_zone_entered(self, zone_name: str, actual_entry: bool = True):
        with measure("zone update"):
            return self._handle_zone_entered(zone_name, actual_entry)

    def _handle_zone_entered(self, zone_name: str, actual_entry: bool = True):
        """エリア入場検知

        actual_entry=False はレベルアップ等による現在エリア表示の再評価用。
        訪問回数・自動ラップ・マップ自動表示など、実際のエリア移動時だけの副作用を抑止する。
        """
        display_zone_name = self._format_zone_display_name(zone_name)
        print(
            f"[DEBUG] ENTER start: zone={zone_name}, actual_entry={actual_entry}, "
            f"poe={self.poe_version}, restoring={self._restoring}, "
            f"last_before={getattr(self, '_last_visit_key', None)}, "
            f"visited_town_before={getattr(self, '_visited_town', False)}"
        )
        self.current_zone = zone_name
        if actual_entry and self.is_running and not self._restoring:
            self.segment_recorder.record_entry(
                self._get_zone_id(zone_name) or zone_name,
                zone_name,
                self.get_elapsed_time(),
            )
            self._update_segment_summary()
        if actual_entry and self.poe_version == POE2 and zone_name in ("川岸", "The Riverbank") and not self._restoring:
            self.clear_progress_flags()
            self.player_level = 1
            self.level_label.setText("キャラLv. 1")

        # 自動ラップ判定（街エリアでも実行 — 橋の野営地/オリアスの船着場がトリガー）
        if actual_entry and not self._restoring:
            self._handle_interlude_lap_progress(zone_name)
            self._try_auto_lap(zone_name)

        # PoE2クリア後のジッグラトの避難所は通常ガイド更新を行わない
        if self.poe_version == POE2 and zone_name in ("ジッグラトの避難所", "The Ziggurat Refuge"):
            if actual_entry:
                self._visited_town = True
            self.zone_label.setText(f"🏠 {display_zone_name}")
            self.advice_label.setText("")
            self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
            return

        # 街エリアの場合はゾーン名表示のみ更新、ガイド・マップは前のまま維持
        # （visit_overrideもリセットしない — 街を挟んでも手動切替を維持）
        if self._is_town_zone(zone_name):
            if actual_entry:
                self._visited_town = True  # 街通過フラグ（always_count_zones用）
            print(
                f"[DEBUG] TOWN: zone={zone_name}, actual_entry={actual_entry}, "
                f"set_visited_town={actual_entry}, last_kept={getattr(self, '_last_visit_key', None)}, "
                f"counts={self.zone_visit_counts}"
            )
            if actual_entry and self.poe_version == POE1:
                self._save_progress_flags()
            self.zone_label.setText(f"🏠 {display_zone_name}")
            if hasattr(self, "mini_navi_overlay") and self._is_mini_navi_available():
                self.mini_navi_overlay.show_last_content_or_waiting()
            # Labクリア後の街帰還 → 志す者の広場の2回目ガイドを表示
            if actual_entry and self._in_lab and self._lab_zone_id:
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
        if actual_entry and self.visit_override is not None:
            self.visit_override = None
            self._update_visit_btn()
        
        # 荒廃した広場(Act10固有)入場 → Act10フラグON
        if actual_entry and zone_name in ("荒廃した広場", "The Ravaged Square") and not self._restoring:
            self._in_act10 = True
        
        # 黄昏の岸辺入場 → 新キャラ判定フラグON（Lv2検知でリセット確定）
        if actual_entry and zone_name in ("黄昏の岸辺", "The Twilight Strand") and not self._restoring:
            self._twilight_strand_entered = True
        
        # C: Part2固有エリアに入場 → 自動切替
        if actual_entry and not self.part2_mode and zone_name in self.part2_only_zones:
            self._set_part2(True)
        
        # zone_id検索
        zone_id = self._get_zone_id(zone_name)
        
        # Lab処理: 志す者の広場に入場 → Labフラグ設定
        _lab_zone_ids = {"act4_area3", "act8_area2", "act10_area8"}
        if actual_entry and zone_id in _lab_zone_ids and not self._restoring:
            self._in_lab = True
            self._lab_zone_id = zone_id
        elif actual_entry and self._in_lab and zone_id and zone_id not in _lab_zone_ids:
            # Lab中に既知の別エリアに入った → Labフラグ解除
            self._in_lab = False
            self._lab_zone_id = None
        elif actual_entry and self._in_lab and not zone_id:
            # Lab中に未知のエリア（Lab内部）→ ガイド更新スキップ
            self.zone_label.setText(f"📍 {display_zone_name}")
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
                self.zone_label.setText(f"🏠 {display_zone_name}")
                self.advice_label.setText("（街エリア — ガイドは前のエリアを表示中）")
                self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
                return
            elif exclude_type == "boss":
                # ボスエリア — ペナルティ判定スキップ
                self.current_zone = zone_name
                act_name, _ = get_zone_info(self.zone_data, zone_name, part2=self.part2_mode)
                act_prefix = f"{act_name} — " if act_name else ""
                self.zone_label.setText(f"📍 {act_prefix}{display_zone_name}")
                self.advice_label.setText("⚔️ ボスエリア")
                self.advice_label.setStyleSheet("color: #ff9944; font-size: 12px;")
                # ガイド・マップ更新は続行
                self._update_guide_and_map(zone_name, zone_id, 1, zone_changed=actual_entry)
                return
            elif exclude_type == "non_combat":
                # 非戦闘エリア — ペナルティ判定スキップ
                self.current_zone = zone_name
                act_name, _ = get_zone_info(self.zone_data, zone_name, part2=self.part2_mode)
                act_prefix = f"{act_name} — " if act_name else ""
                self.zone_label.setText(f"📍 {act_prefix}{display_zone_name}")
                self.advice_label.setText("🏛️ 非戦闘エリア")
                self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
                self._update_guide_and_map(zone_name, zone_id, 1, zone_changed=actual_entry)
                return
        
        # 訪問回数カウント（zone_id基準）
        visit_key = zone_id if zone_id else zone_name
        last_visit_key = getattr(self, '_last_visit_key', None)
        # 街を挟んでも常にカウントするエリア（ポータルで街に戻って再入場するパターン）
        always_count_zones = {"act5_area5", "act10_area3", "act8_area20", "act9_area2"}  # イノセンスの間, 荒廃した広場, 隠れた裏道, ヴァスティリ砂漠
        if self._restoring:
            # 復元時はカウントアップしないが、未記録なら1回目として記録（次回訪問で2回目になるように）
            self._last_visit_key = visit_key
            if visit_key not in self.zone_visit_counts:
                self.zone_visit_counts[visit_key] = 1
            visit_num = self.zone_visit_counts.get(visit_key, 1)
            if self.poe_version == POE1:
                self._save_progress_flags()
        elif not actual_entry:
            # レベルアップ等の表示再評価では、訪問回数や街通過フラグを変更しない
            visit_num = self.zone_visit_counts.get(visit_key, 1)
        else:
            # カウントアップ判定:
            # 1. 別ゾーンから来た場合 → カウントアップ（通常の訪問）
            # 2. 同一ゾーン連続の場合 → always_count_zones かつ街経由のみカウントアップ
            #    （ログ重複や街経由の回復戻りではカウントしない）
            should_count = False
            visited_town = getattr(self, '_visited_town', False)
            if visit_key != last_visit_key:
                # 別ゾーンからの入場 → カウントアップ
                should_count = True
            else:
                # 同一ゾーン再入場 → always_count_zones かつ街を経由した場合のみ
                if visit_key in always_count_zones and visited_town:
                    should_count = True
            print(
                f"[DEBUG] COUNT before: zone={zone_name}, zone_id={zone_id}, visit_key={visit_key}, "
                f"last_visit_key={last_visit_key}, visited_town={visited_town}, "
                f"should_count={should_count}, counts_before={self.zone_visit_counts}"
            )
            
            if should_count:
                self.zone_visit_counts[visit_key] = self.zone_visit_counts.get(visit_key, 0) + 1
            
            # 街通過フラグをリセット（街以外のゾーンに入ったらクリア）
            self._visited_town = False
            self._last_visit_key = visit_key
            visit_num = self.zone_visit_counts.get(visit_key, 1)
            print(
                f"[DEBUG] COUNT after: zone={zone_name}, visit_key={visit_key}, "
                f"last_after={self._last_visit_key}, visited_town_after={self._visited_town}, "
                f"visit_num={visit_num}, counts_after={self.zone_visit_counts}"
            )
            if self.poe_version == POE1:
                self._save_progress_flags()
        if actual_entry and self.poe_version == POE1:
            # Act1 海底通路 到達フラグ。海岸へ戻った後のガイド切替に使う。
            if zone_id == "act1_area4":
                self.set_progress_flag("act1_submergedpassage_enter")
            # Act1 水没した海底洞窟 到達フラグ。海底通路の復帰後ガイド切替に使う。
            if zone_id == "act1_area9":
                self.set_progress_flag("act1_floodeddepths_enter")
            # Act1 船の墓場の洞窟 到達フラグ。船の墓場の復帰後ガイド切替に使う。
            if zone_id == "act1_area13":
                self.set_progress_flag("act1_shipgraveyardcave_enter")
            # Act2 西の森 到達フラグ。川沿いの道の復帰後ガイド切替に使う。
            if zone_id == "act2_area8":
                self.set_progress_flag("act2_westernforest_enter")
            # Act2 編む者の巣穴/湿地 到達フラグ。西の森の復帰後ガイド切替に使う。
            if zone_id == "act2_area9":
                self.set_progress_flag("act2_weaverschambers_enter")
            if zone_id == "act2_area14":
                self.set_progress_flag("act2_wetlands_enter")
            # Act3 ソラリス/ルナリス第二層 到達フラグ。黒檀の兵舎の復帰後ガイド切替に使う。
            if zone_id == "act3_area10":
                self.set_progress_flag("act3_solaris_enter")
            if zone_id == "act3_area13":
                self.set_progress_flag("act3_lunaris_enter")
            # Act4 大闘技場/カオムの要塞 到達フラグ。水晶鉱脈の復帰後ガイド切替に使う。
            if zone_id == "act4_area8":
                self.set_progress_flag("act4_grandarena_enter")
            if zone_id == "act4_area10":
                self.set_progress_flag("act4_kaomstronghold_enter")
            # Act5 聖廟 到達フラグ。破壊された広場の復帰後ガイド切替に使う。
            if zone_id == "act5_area9":
                self.set_progress_flag("act5_reliquary_enter")
            # Act6 湿地 到達フラグ。Act6 川沿いの道の復帰後ガイド切替に使う。
            # 同名のAct2「湿地」と混同しないよう、zone_idでAct6のみ判定する。
            if zone_id == "act6_area11":
                self.set_progress_flag("act6_wetlands_enter")
            # Act7 地下聖堂 到達フラグ。Act7 十字路の復帰後ガイド切替に使う。
            # Act2の地下聖堂と混同しないよう、zone_idでAct7のみ判定する。
            if zone_id == "act7_area4":
                self.set_progress_flag("act7_crypt_enter")
            # Act7 マリガロの聖域 到達フラグ。Act6 囚人の門のAct7後ガイド切替に使う。
            if zone_id == "act7_area6":
                self.set_progress_flag("act7_maligarosanctum_enter")
            # Act7 恐怖の密林 到達フラグ。Act7 北の森の復帰後ガイド切替に使う。
            # 同名/類似名エリアと混同しないよう、zone_idでAct7のみ判定する。
            if zone_id == "act7_area12":
                self.set_progress_flag("act7_dreadthicket_enter")
            # Act8 ソラリス/ルナリス寺院 第二層 到達フラグ。
            # Act3にも同名エリアがあるため、zone_idでAct8のみ判定する。
            if zone_id == "act8_area11":
                self.set_progress_flag("act8_solaristemple2_enter")
            if zone_id == "act8_area16":
                self.set_progress_flag("act8_lunaristemple2_enter")
            # Act8 血の水道橋 到達フラグ。通常ルートのルナリスの中央広場で
            # 帰還後ガイドを切り替えるために使う。
            if zone_id == "act8_area17":
                self.set_progress_flag("act8_bloodaqueduct_enter")
            # Act9 オアシス 到達フラグ。Act9 ヴァスティリ砂漠の復帰後ガイド切替に使う。
            if zone_id == "act9_area3":
                self.set_progress_flag("act9_oasis_enter")
            # Act10 奴隷管理区画/納骨堂/冒涜された広間 到達フラグ。Act10 荒廃した広場の復帰後ガイド切替に使う。
            # Act5の同名エリアと混同しないよう、zone_idでAct10のみ判定する。
            if zone_id == "act10_area4":
                self.set_progress_flag("act10_controlblocks_enter")
            if zone_id == "act10_area5":
                self.set_progress_flag("act10_ossuary_enter")
            if zone_id == "act10_area7":
                self.set_progress_flag("act10_desecratedchambers_enter")
        if actual_entry and visit_num == 1:
            if self.poe_version == POE2:
                if zone_name in ("裏切り者の通路", "Traitor's Passage"):
                    self.set_progress_flag("act2_traitor_clear")
                if zone_name in ("ジクアニの聖所", "Jiquani's Sanctum"):
                    self.set_progress_flag("act3_zicoatl_dead")
                if zone_name in ("吠える洞窟", "Howling Caves"):
                    self.set_progress_flag("interlude3_yeti_dead")
        print(f"[DEBUG] zone={zone_name}, id={zone_id}, visit_num={visit_num}, restoring={self._restoring}, counts={self.zone_visit_counts}")
        
        self.current_zone = zone_name
        # 自動ラップ判定は on_zone_entered() 冒頭で実行済み
        act_name, zone_level = get_zone_info(self.zone_data, zone_name, part2=self.part2_mode)
        self._sync_gem_tracker_act_from_zone_act(act_name)
        
        # monster_levels.jsonからモンスターレベルを取得（優先）
        monster_lv = None
        if monster_info and monster_info.get("lv", 0) > 0 and "exclude" not in monster_info:
            monster_lv = monster_info["lv"]
        
        # 2回目以降はガイドデータ内の適正レベル上書きをチェック
        if visit_num >= 2 and zone_id:
            guide_level = get_zone_guide_level(self.guide_data, zone_id, visit=visit_num, config=self.config)
            if guide_level:
                zone_level = guide_level
                # ガイドデータにレベル上書きがある場合はそちらを優先
                monster_lv = guide_level
        
        # 表示用レベル決定: monster_levels優先、なければzone_data
        display_lv = monster_lv if monster_lv else zone_level
        is_town_zone = self._is_town_zone(zone_name)
        
        if is_town_zone:
            self.zone_label.setText(f"📍 {display_zone_name}")
            self.advice_label.setText("")
            self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
        elif act_name and display_lv:
            visit_label = ""
            lv_prefix = "MLv" if monster_lv else "Lv"
            self.zone_label.setText(f"📍 {act_name} — {display_zone_name} ({lv_prefix}.{display_lv}){visit_label}")
            msg, color = get_level_advice(self.player_level, display_lv)
            self.advice_label.setText(msg)
            self.advice_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        else:
            self.zone_label.setText(f"📍 {display_zone_name}")
            if act_name:
                self.advice_label.setText("（エリアレベルは攻略順で変動するため固定表示なし）")
            else:
                self.advice_label.setText("（適正レベル未登録エリア）")
            self.advice_label.setStyleSheet("color: #888888; font-size: 12px;")
        
        # 攻略ガイド・マップ更新
        self._update_guide_and_map(zone_name, zone_id, visit_num, zone_changed=actual_entry, exp_level=display_lv)
    
    def _mini_navi_exp_guide(self, enemy_level: int | None, zone_id: str | None = None) -> dict | None:
        if zone_id:
            monster_info = self.monster_levels.get(zone_id) if isinstance(getattr(self, "monster_levels", None), dict) else None
            if isinstance(monster_info, dict) and monster_info.get("exclude"):
                return None
        if not enemy_level:
            return None
        player_level = int(getattr(self, "player_level", 1) or 1)
        msg, _color = get_level_advice(player_level, int(enemy_level))
        if "🔴" in msg:
            status = "🔴 ペナ発生"
        elif "🟢" in msg:
            status = "🟢 最適"
        else:
            status = "🟡 ペナなし"
        return {"player_level": player_level, "enemy_level": int(enemy_level), "status": status}

    def _update_guide_and_map(self, zone_name: str, zone_id: str | None, visit_num: int, zone_changed: bool = False, exp_level: int | None = None):
        """攻略ガイドとマップ画像を更新"""
        self._update_area_note(zone_name, zone_id)
        self._update_poelab_link_visibility(zone_id)
        # 訪問回数オーバーライド適用
        effective_visit = self.visit_override if self.visit_override is not None else visit_num
        if exp_level is None:
            _act_name, fallback_zone_level = get_zone_info(self.zone_data, zone_name, part2=self.part2_mode)
            exp_level = fallback_zone_level
            if effective_visit >= 2 and zone_id:
                guide_level = get_zone_guide_level(self.guide_data, zone_id, visit=effective_visit, config=self.config)
                if guide_level:
                    exp_level = guide_level
        if zone_id:
            guide = get_zone_guide(self.guide_data, zone_id, visit=effective_visit, config=self.config, active_flags=self.progress_flags)
        else:
            guide = None
        
        if guide:
            html = format_guide_html(
                guide,
                font_size=self.guide_font_size,
                show_direction=(self.poe_version == POE1),
                guide_detail_level=self.config.get("guide_detail_level", "beginner") if self.poe_version == POE2 else "beginner",
            )
            self.guide_text_label.setText(html)
            self.guide_text_label.setStyleSheet(f"color: #dddddd; font-size: {self.guide_font_size}px; background: transparent;")
            if hasattr(self, "mini_navi_overlay"):
                if self._is_mini_navi_available():
                    overlay_config = self.config.get("mini_guide_overlay", {})
                    display_mode = overlay_config.get("display_mode", "standard") if isinstance(overlay_config, dict) else "standard"
                    max_lines = None if display_mode == "compact" else overlay_config.get("max_lines", 4)
                    self.mini_navi_overlay.update_content(
                        get_mini_navi_content(guide, max_lines=max_lines),
                        self._mini_navi_exp_guide(exp_level, zone_id=zone_id),
                        zone_id=zone_id,
                        has_area_note=bool(self._current_area_note.strip()),
                    )
                else:
                    self.mini_navi_overlay.hide()
        else:
            self.guide_text_label.setText(f"「{zone_name}」のガイドデータはありません")
            self.guide_text_label.setStyleSheet(f"color: #666666; font-size: {self.guide_font_size}px; background: transparent;")
            if hasattr(self, "mini_navi_overlay"):
                self.mini_navi_overlay.hide()
        
        # マップ画像は日本語フォルダ名で検索（英語クライアント対応）
        map_zone_name = zone_name
        if zone_id:
            for act_zones in self.zone_data.values():
                for z in act_zones:
                    if z.get("id") == zone_id:
                        map_zone_name = z["zone"]  # 日本語名
                        break
        # ルート設定を取得してマップ画像にも反映
        map_route = ""
        if zone_id:
            if zone_id.startswith("act3_"):
                r = ConfigManager.effective_poe1_route_act3(self.config)
                if r != "standard": map_route = r
            elif zone_id.startswith("act8_"):
                r = ConfigManager.effective_poe1_route_act8(self.config)
                if r != "standard": map_route = r
        defer_initial_auto_open = bool(self._restoring and zone_changed and self.map_thumbnail.auto_open)
        self.map_thumbnail.load_maps(
            map_zone_name,
            part2=self.part2_mode,
            zone_changed=(zone_changed and not defer_initial_auto_open),
            route=map_route,
            poe_version=get_poe_label(self.poe_version),
        )
        if defer_initial_auto_open and self.map_thumbnail.current_paths:
            self._pending_initial_map_auto_open = True
    
    def on_kitava_defeated(self):
        """PoE1 Act5相当の特別ラップイベント"""
        if self.poe_version != POE1:
            return
        if not self.part2_mode:
            print("[INFO] キタヴァ討伐を検知 — Act 6-10に切替")
            self._set_part2(True, update_guide=False)
        lap_num = get_special_lap_event(self.poe_version, "kitava_act5")
        if lap_num:
            self._auto_lap_kitava(lap_num)
    
    def on_act10_cleared(self):
        """最終クリアイベント → act10_area11（渇望の祭壇）ガイド表示 + 自動ラップ"""
        lap_num = get_special_lap_event(self.poe_version, "final_clear")
        if lap_num:
            self._auto_lap_kitava(lap_num)
        print(f"[INFO] {get_poe_label(self.poe_version)} の最終クリアを検知 — 渇望の祭壇ガイド表示")
        zone_name = "渇望の祭壇"
        zone_id = "act10_area11"
        self.current_zone = zone_name
        self.zone_label.setText("📍 Act 10 — 渇望の祭壇")
        self.advice_label.setText("🎉 Act10クリア — クリア後ガイドを表示中")
        self.advice_label.setStyleSheet("color: #ffd700; font-size: 12px;")
        self._update_guide_and_map(zone_name, zone_id, 1, zone_changed=True)

    def on_poe2_act4_cleared(self):
        """PoE2 Act4クリアイベントによる自動ラップ"""
        lap_num = get_special_lap_event(self.poe_version, "act4_clear")
        if lap_num:
            self._auto_lap_kitava(lap_num)

    def _progress_flags_path(self):
        filename = get_progress_flags_filename(self.poe_version)
        if not filename:
            return None
        return str(ConfigManager.get_user_data_path(filename))

    def _save_progress_flags(self):
        path = self._progress_flags_path()
        if not path:
            return
        data = {"active_flags": sorted(self.progress_flags)}
        if self.poe_version == POE1:
            data.update({
                "zone_visit_counts": self.zone_visit_counts,
                "last_visit_key": getattr(self, "_last_visit_key", None),
                "visited_town": getattr(self, "_visited_town", False),
            })
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def clear_progress_flags(self):
        self.progress_flags = set()
        self.interlude_ready = set()
        if self.poe_version == POE1:
            self.zone_visit_counts = {}
            self._last_visit_key = None
            self._visited_town = False
        self._save_progress_flags()

    def _restore_progress_flags(self):
        self.progress_flags = set()
        if self.poe_version == POE1:
            self.zone_visit_counts = {}
            self._last_visit_key = None
            self._visited_town = False
        path = self._progress_flags_path()
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.progress_flags = set(data.get('active_flags', []))
            if self.poe_version == POE1:
                counts = data.get('zone_visit_counts', {})
                self.zone_visit_counts = counts if isinstance(counts, dict) else {}
                self._last_visit_key = data.get('last_visit_key')
                self._visited_town = bool(data.get('visited_town', False))
        except Exception as e:
            print(f"[WARN] progress flags load failed [{self.poe_version}]: {e}")
            self.progress_flags = set()
            if self.poe_version == POE1:
                self.zone_visit_counts = {}
                self._last_visit_key = None
                self._visited_town = False

    def set_progress_flag(self, flag_name: str, enabled: bool = True):
        """進行フラグを更新し、必要ならガイド再評価する"""
        changed = False
        if enabled:
            if flag_name not in self.progress_flags:
                self.progress_flags.add(flag_name)
                changed = True
        else:
            if flag_name in self.progress_flags:
                self.progress_flags.discard(flag_name)
                changed = True
        if changed:
            self._save_progress_flags()
        if self.current_zone:
            zone_id = self._get_zone_id(self.current_zone)
            visit_num = self.zone_visit_counts.get(zone_id or self.current_zone, 1)
            self._update_guide_and_map(self.current_zone, zone_id, visit_num)

    def on_level_up(self, char_name: str, level: int):
        """レベルアップ検知"""
        self.player_level = level
        self.level_label.setText(f"キャラLv. {level}")
        
        # 新キャラ判定: 黄昏の岸辺入場済み + Lv2 = ヒロック討伐 → visitカウントリセット
        if level == 2 and getattr(self, '_twilight_strand_entered', False):
            print("[INFO] 新キャラ確定（黄昏の岸辺 + Lv2）— visitカウント/進行フラグをリセット")
            self.clear_progress_flags()
            self._twilight_strand_entered = False
            self.visit_override = None
            self._update_visit_btn()
            self._in_act10 = False
            self._set_part2(False)  # Act 1-5に戻す
        
        # 現在のゾーン情報があれば再評価
        if self.current_zone:
            self.on_zone_entered(self.current_zone, actual_entry=False)
    
    def update_level_guide_display(self):
        """レベルガイド表示を更新"""
        if self.current_zone:
            self.on_zone_entered(self.current_zone, actual_entry=False)
    
    # --- ウィンドウ移動 & 下端リサイズ ---
    MIN_HEIGHT = 400
    DETACHED_ONLY_MIN_HEIGHT = 90

    def _are_all_visible_panels_detached(self) -> bool:
        """現在のPoEバージョンで表示対象の全パネルが切り離されているか。"""
        registry = getattr(self, "panel_registry", {})
        relevant_panels = {
            panel_id
            for panel_id in registry
            if panel_id != "gem" or getattr(self, "poe_version", POE1) == POE1
        }
        detached_panels = set(getattr(self, "detached_panel_windows", {}))
        return bool(relevant_panels and relevant_panels.issubset(detached_panels))

    def _main_window_min_height(self) -> int:
        """表示対象の全パネルを切り離した本体だけ、操作列相当まで縮小可能にする。"""
        if self._are_all_visible_panels_detached():
            return self.DETACHED_ONLY_MIN_HEIGHT
        return self.MIN_HEIGHT
    
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
            min_h = self._main_window_min_height()
            
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

        update_action = menu.addAction("アップデートを確認")
        update_action.triggered.connect(
            lambda: self._check_for_updates(manual=True)
        )
        
        menu.addSeparator()
        
        quit_action = menu.addAction("終了")
        quit_action.triggered.connect(self.close)
        
        menu.exec(event.globalPos())

    def open_memo(self):
        """メモダイアログをトグル表示"""
        if hasattr(self, '_memo_dialog') and self._memo_dialog is not None:
            if self._memo_dialog.isVisible():
                self._memo_dialog._save_and_close()
                return
            else:
                self._memo_dialog.show()
                self._memo_dialog.raise_()
                return
        # 初回: ダイアログ生成
        notes_filename = "notes_poe2.json" if self.poe_version == POE2 else "notes_poe1.json"
        notes_path = str(ConfigManager.get_user_data_path(notes_filename))
        self._memo_dialog = MemoDialog(self, notes_path=notes_path)
        self._memo_dialog.apply_opacity(
            self.config.get("window_opacity", 100),
            self.config.get("text_opacity", 100)
        )
        self._memo_dialog.show()

    def open_poetore(self):
        """ぽえとれを必要になった時だけ読み込んで別ウィンドウで開く。"""
        from src.poetore.ui import show_poetore_window

        show_poetore_window(self)

    def capture_poetore_item(self):
        """設定済みホットキーからぽえとれを開き、PoE上のアイテムを自動取得する。"""
        from src.poetore.ui import show_poetore_window

        # コピーが終わるまでPoEからフォーカスを奪わない。
        show_poetore_window(self, activate=False).capture_from_poe()

    def _update_poetore_hotkey_tooltip(self):
        hotkey = self.config.get("hotkeys", {}).get("poetore_capture", "alt+d")
        if hotkey and hotkey != "none":
            display_hotkey = QKeySequence(hotkey).toString(QKeySequence.NativeText)
            self.poetore_btn.setToolTip(
                f"ぽえとれ（{display_hotkey}で日本語名＋詳細Modを取得）"
            )
        else:
            self.poetore_btn.setToolTip("ぽえとれ（ホットキー未設定）")
    
    def open_settings(self):
        dialog = SettingsDialog(self, self.config)
        if dialog.exec():
            self._set_timer_ready(False)
            # 設定保存
            previous_timer_size_setting = self.config.get("timer_size", "large")
            previous_always_on_top = self.config.get("always_on_top", True)
            new_settings = dialog.get_settings()
            self.config.update(new_settings)
            ConfigManager.save_config(self.config)
            self._refresh_gem_shop_search_preview()
            if self.config.get("always_on_top", True) != previous_always_on_top:
                self._apply_window_flags()
            
            # ホットキー再登録
            self.register_hotkeys()
            self._update_click_through_label()
            self._update_poetore_hotkey_tooltip()
            
            # ログ監視の再設定
            active_version = self.config.get("poe_version", self.poe_version)
            client_log_paths = self.config.get("client_log_paths", {})
            log_path = client_log_paths.get(active_version, "")
            if log_path:
                self.log_watcher.set_log_path(log_path)
                self.log_watcher.start()
                # PoE1ルート未選択なら、初回セットアップ完了済みでもPoE1ログ設定時に表示する
                if active_version == POE1 and not self.config.get("poe1_route_selected", False):
                    self._show_route_selection_dialog()
                if not self.config.get("setup_completed"):
                    self.config["setup_completed"] = True
                    ConfigManager.save_config(self.config)
                # ログファイル未設定メッセージをクリア
                self.guide_text_label.setText("")
            
            # ゾーンデータ・ガイドデータ更新
            prev_version = self.poe_version
            self.poe_version = self.config.get("poe_version", POE1)
            self.lap_labels = get_lap_labels(self.poe_version)
            zone_master_data = load_zone_master_data()
            self.zone_data_by_version = zone_master_data["zone_data_by_version"]
            self.town_zones_by_version = zone_master_data["town_zones_by_version"]
            self.zone_data = self.zone_data_by_version.get(self.poe_version, {})
            self.log_watcher.set_poe_version(self.poe_version)
            self.setWindowTitle(f"ぽえなび [{get_poe_label(self.poe_version)}]")
            if prev_version != self.poe_version:
                self.lap_times = [None] * len(self.lap_labels)
                self.current_act = 1
                self.accumulated_time = 0.0
                self.update_text(0.0)
                self._rebuild_lap_ui()
                self._restore_timer_state()
                self._restore_progress_flags()
                self.update_lap_display()
                switched_log_path = self.config.get("client_log_paths", {}).get(self.poe_version, "")
                if switched_log_path:
                    self.log_watcher.set_log_path(switched_log_path)
                    self.log_watcher.start()
                if hasattr(self, '_memo_dialog') and self._memo_dialog is not None:
                    self._memo_dialog.close()
                    self._memo_dialog = None
                if hasattr(self, '_vendor_search_dialog') and self._vendor_search_dialog is not None:
                    self._vendor_search_dialog.close()
                    self._vendor_search_dialog = None
            
            # ガイドフォントサイズ更新
            self.guide_font_size = self.config.get("guide_font_size", 18)
            if self.poe_version != POE1 and self._is_panel_detached("gem"):
                self.restore_panel("gem")
            self.gem_tracker_frame.setVisible(self.poe_version == POE1 and self.gem_tracker_expanded)
            if "gem" in self.panel_registry:
                self.panel_registry["gem"]["content"].setVisible(self.poe_version == POE1)
            self.part2_btn.setVisible(self.poe_version == POE1)
            self._refresh_mini_navi_toggle()
            self._refresh_guide_detail_level_toggle()
            
            # タイマーサイズ更新
            new_timer_size_setting = self.config.get("timer_size", "large")
            if new_timer_size_setting == "off":
                if self.timer_size in self.TIMER_SIZES:
                    self.config["timer_size_before_off"] = self.timer_size
                self._set_timer_expanded(False)
                self.config["timer_expanded"] = False
                effective_timer_size = self._effective_timer_size(new_timer_size_setting)
            else:
                self.config["timer_size_before_off"] = new_timer_size_setting
                effective_timer_size = new_timer_size_setting
                if previous_timer_size_setting == "off":
                    self._set_timer_expanded(True)
                    self.config["timer_expanded"] = True
            if effective_timer_size != self.timer_size:
                self.timer_size = effective_timer_size
                self._apply_timer_size()
            ConfigManager.save_config(self.config)
            
            # ウィンドウロック更新
            self.window_locked = self.config.get("window_locked", False)
            # マップ自動表示更新
            self.map_thumbnail.auto_open = self.config.get("auto_open_map", False)
            self.map_thumbnail.auto_position = self.config.get("auto_position_map", True)
            # 透過率更新
            self._apply_bg_opacity(self.config.get("window_opacity", 100))
            self._apply_text_opacity(self.config.get("text_opacity", 100))
            self._apply_detached_panel_window_settings()
            if hasattr(self, "mini_navi_overlay"):
                self.mini_navi_overlay.apply_settings(refresh_window_flags=True)
            # メモダイアログにも透過率を反映
            if hasattr(self, '_memo_dialog') and self._memo_dialog is not None and self._memo_dialog.isVisible():
                self._memo_dialog.apply_opacity(
                    self.config.get("window_opacity", 100),
                    self.config.get("text_opacity", 100)
                )
            
            self._refresh_ready_button()
            self.update_level_guide_display()
        
        # ガイドデータは常にリロード（ガイド編集Saveで即保存されるため、Cancelでも反映する）
        self.guide_data = load_guide_data(self.poe_version)
        # 現在表示中のガイドを再描画
        if self.current_zone:
            zone_id = self._get_zone_id(self.current_zone)
            visit_num = self.zone_visit_counts.get(self.current_zone, 1)
            self._update_guide_and_map(self.current_zone, zone_id, visit_num)

    def _main_window_flags(self):
        return _with_optional_always_on_top(Qt.FramelessWindowHint, self)

    def minimize_main_window(self):
        """みになび表示中は本体だけ隠し、それ以外は通常どおり最小化する。"""
        overlay = getattr(self, "mini_navi_overlay", None)
        if overlay is not None and self._is_mini_navi_available() and overlay.isVisible():
            self.hide_for_mini_navi()
            return
        self.showMinimized()

    def hide_for_mini_navi(self):
        """ぽえなび本体だけを隠し、みになびの表示を維持する。"""
        self._hidden_for_mini_navi = True
        self.hide()
        overlay = getattr(self, "mini_navi_overlay", None)
        if overlay is not None:
            overlay.show()
            overlay.raise_()
            overlay._sync_lock_button()

    def restore_from_mini_navi(self):
        """みになびだけの表示状態から、ぽえなび本体を復帰する。"""
        self._hidden_for_mini_navi = False
        self.showNormal()
        self.raise_()
        self.activateWindow()
        overlay = getattr(self, "mini_navi_overlay", None)
        if overlay is not None:
            overlay._sync_lock_button()

    def _apply_window_flags(self):
        was_visible = self.isVisible()
        self.setWindowFlags(self._main_window_flags())
        if was_visible:
            self.show()
            
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_main_window_initialized", False):
            return
        if not getattr(self, "_initial_positioned", False):
            self._initial_positioned = True
            from PySide6.QtWidgets import QApplication
            
            snap_to_right = self.config.get("snap_to_right_edge", False)
            saved_geo = self.config.get("window_geometry")
            
            if snap_to_right:
                # モニター右端配置ON:
                # 保存済みの幅・高さ・Y位置を尊重し、Xだけ対象モニターの右端に合わせる。
                # Yは画面外にはみ出す場合のみ表示可能範囲内に補正する。
                if saved_geo:
                    screens = QApplication.screens()
                    idx = self._display_monitor_index
                    if screens and 0 <= idx < len(screens):
                        target_screen = screens[idx]
                    elif screens:
                        target_screen = screens[0]
                    else:
                        return
                    screen_geo = target_screen.availableGeometry()
                    w = saved_geo.get("width", 420)
                    h = saved_geo.get("height", 1200)
                    saved_y = saved_geo.get("y", screen_geo.top())
                    x = screen_geo.left() + screen_geo.width() - w
                    max_y = screen_geo.top() + screen_geo.height() - h
                    if max_y < screen_geo.top():
                        y = screen_geo.top()
                    else:
                        y = max(screen_geo.top(), min(saved_y, max_y))
                    self.setGeometry(x, y, w, h)
                else:
                    # 初回など保存済みジオメトリがない場合は従来どおり右端フル高さ
                    self._position_right_edge()
            elif saved_geo:
                # 保存済みジオメトリを復元
                x = saved_geo.get("x", 0)
                y = saved_geo.get("y", 0)
                w = saved_geo.get("width", 420)
                h = saved_geo.get("height", 1200)
                # 画面外チェック: 全スクリーンのunionに収まるか
                screens = QApplication.screens()
                if screens:
                    union = screens[0].availableGeometry()
                    for s in screens[1:]:
                        union = union.united(s.availableGeometry())
                    window_rect = QRect(x, y, w, h)
                    if union.intersects(window_rect):
                        self.setGeometry(x, y, w, h)
                    else:
                        # 画面外 → デフォルト（右端配置）
                        self._position_right_edge()
                else:
                    self.setGeometry(x, y, w, h)
            else:
                # デフォルト: 右端配置
                self._position_right_edge()

            if getattr(self, "_pending_initial_map_auto_open", False):
                self._pending_initial_map_auto_open = False
                QTimer.singleShot(50, self.map_thumbnail.open_first_map)
    
    def _position_right_edge(self):
        """デフォルトの右端配置"""
        from PySide6.QtWidgets import QApplication
        screens = QApplication.screens()
        if not screens:
            return
        target_screen = screens[0]
        geo = target_screen.availableGeometry()
        actual_w = self.frameGeometry().width()
        win_h = geo.height()
        self.resize(self.width(), win_h)
        x = geo.left() + geo.width() - actual_w
        y = geo.top()
        self.move(x, y)

    def closeEvent(self, event):
        # 起動時アップデートでは、保存済みジオメトリを復元する前の仮サイズ
        # (420x1200) のまま終了する。初期化・初期配置が完了した通常終了時だけ
        # 位置とサイズを保存し、ユーザー設定を仮サイズで上書きしない。
        if (
            getattr(self, "_main_window_initialized", False)
            and getattr(self, "_initial_positioned", False)
        ):
            # 他のウィンドウが終了直前に保存した設定（例: map_viewer_width/height）を
            # 古い self.config で上書きしないよう、最新configを読み直して必要キーだけ更新する。
            geo = self.geometry()
            config = ConfigManager.load_config()
            config["window_geometry"] = {
                "x": geo.x(),
                "y": geo.y(),
                "width": geo.width(),
                "height": geo.height(),
            }
            ConfigManager.save_config(config)
            self.config = config

        self._close_detached_panels()

        # みになびは本体と独立したトップレベルウィンドウなので、アプリ終了時は
        # 明示的に一緒に閉じる。
        overlay = getattr(self, "mini_navi_overlay", None)
        if overlay is not None:
            overlay.close()

        keyboard_listener = getattr(self, "keyboard_listener", None)
        if keyboard_listener:
            keyboard_listener.stop()
        log_watcher = getattr(self, "log_watcher", None)
        if log_watcher is not None:
            log_watcher.stop()
        super().closeEvent(event)
