"""ぽえとれモードの軽量シェル。

最終UIはPhase 3で実装する。ここではモード境界と共通常駐機能を成立させる。
"""

from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from src.ui.styles import Styles
from src.utils.chat_command import send_chat_command
from src.utils.config_manager import ConfigManager
from src.utils.global_hotkeys import GlobalHotkeyService
from src.utils.stash_tab_scroll import StashTabScrollController


class PoetoreModeWindow(QMainWindow):
    MODE_ACTION_DEFAULTS = {
        "exit": "F5",
        "poetore_capture": "alt+d",
        "cheat_sheets_toggle": "shift+space",
    }

    def __init__(self):
        super().__init__()
        self.config = ConfigManager.load_config()
        self._cheat_sheet_overlay = None
        self.setWindowTitle("ぽえとれ")
        self.setMinimumSize(420, 220)
        self.resize(520, 280)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        self._build_placeholder_ui()

        self.stash_tab_scroll = StashTabScrollController(
            enabled=self.config.get("stash_tab_scroll_enabled", True)
        )
        self.stash_tab_scroll.start()

        configured = self.config.get("hotkeys", {})
        mode_hotkeys = {
            action: configured.get(action, default)
            for action, default in self.MODE_ACTION_DEFAULTS.items()
        }
        self.hotkey_service = GlobalHotkeyService(mode_hotkeys, parent=self)
        self.hotkey_service.command.connect(self.handle_hotkey)
        self.hotkey_service.start()

    def _build_placeholder_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)
        title = QLabel("ぽえとれ")
        title.setStyleSheet("color: #DB86EF; font-size: 28px; font-weight: bold;")
        description = QLabel(
            "価格チェック・トレード支援モード\n"
            "Alt+Dで価格検索を開けます。基本画面は次の段階で追加します。"
        )
        description.setStyleSheet("color: #eadcf0; font-size: 14px;")
        description.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch()
        self.setCentralWidget(central)

    @property
    def active_service_names(self):
        names = {"global_hotkeys", "stash_tab_scroll"}
        if self._cheat_sheet_overlay is not None:
            names.add("cheat_sheets")
        return frozenset(names)

    def handle_hotkey(self, command):
        if command == "poetore_capture":
            self.capture_poetore_item()
        elif command == "cheat_sheets_toggle":
            self.toggle_cheat_sheets()
        elif command == "cheat_sheets_escape":
            if self._cheat_sheet_overlay is not None and self._cheat_sheet_overlay.isVisible():
                self._cheat_sheet_overlay.hide_and_save()
        elif command == "exit":
            self.execute_chat_command("/exit")

    def capture_poetore_item(self):
        from src.poetore.ui import show_poetore_window

        show_poetore_window(self, activate=False).capture_from_poe()

    def _ensure_cheat_sheet_overlay(self):
        from src.ui.cheat_sheets import CheatSheetOverlay

        if self._cheat_sheet_overlay is None:
            overlay = CheatSheetOverlay(self.config.get("cheat_sheets", {}), self)
            overlay.config_changed.connect(self._save_cheat_sheet_config)
            overlay.manage_requested.connect(self.open_cheat_sheet_manager)
            self._cheat_sheet_overlay = overlay
        return self._cheat_sheet_overlay

    def _save_cheat_sheet_config(self, cheat_sheet_config):
        self.config["cheat_sheets"] = dict(cheat_sheet_config)
        ConfigManager.save_config(self.config)

    def toggle_cheat_sheets(self):
        self._ensure_cheat_sheet_overlay().toggle()

    def open_cheat_sheet_manager(self):
        from src.ui.cheat_sheets import CheatSheetManagerDialog

        overlay = self._ensure_cheat_sheet_overlay()
        was_visible = overlay.isVisible()
        if was_visible:
            overlay.hide_and_save()
        dialog = CheatSheetManagerDialog(self.config.get("cheat_sheets", {}), self)
        if dialog.exec():
            self._save_cheat_sheet_config(dialog.result_config())
            overlay.reload(self.config["cheat_sheets"])
            if self.config["cheat_sheets"].get("images"):
                overlay.show()
                overlay.raise_()

    def execute_chat_command(self, command):
        """共通F5操作。PoEチャットへ貼り付けて送信する。"""
        send_chat_command(command)

    def closeEvent(self, event):
        self.hotkey_service.stop()
        self.stash_tab_scroll.stop()
        if self._cheat_sheet_overlay is not None:
            self._cheat_sheet_overlay.hide_and_save()
            self._cheat_sheet_overlay.close()
        super().closeEvent(event)
