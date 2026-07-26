import time

from pynput import keyboard as pynput_keyboard
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from src.ui.styles import Styles
from src.ui.window_flags import _with_optional_always_on_top
from src.utils.search_query_patterns import join_query_patterns, split_query_patterns
from src.utils.window_focus import (
    focus_window,
    get_foreground_window,
    get_next_visible_window_after,
)


class SearchStringPasteTestDialog(QDialog):
    """検索文字列メニュー → PoE復帰 → 検索欄貼り付けの技術検証用ダイアログ"""

    def __init__(self, target_hwnd, choices=None, parent=None, owner=None):
        super().__init__(parent)
        self.owner = owner
        self.target_hwnd = target_hwnd
        self.choices = choices or []
        self.setWindowTitle("店売り・スタッシュ検索")
        self.setWindowFlags(_with_optional_always_on_top(Qt.Tool | Qt.FramelessWindowHint, parent))
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setStyleSheet(Styles.MAIN_WINDOW)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("🔍 店売り・スタッシュ検索")
        title.setStyleSheet(f"color: {Styles.TEXT_COLOR}; font-size: 13px; font-weight: bold;")
        layout.addWidget(title)

        hint = QLabel("選択後、ホットキー時点のウィンドウへ戻して Ctrl+F → 貼り付けます。")
        hint.setStyleSheet("color: #cccccc; font-size: 10px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        for preset in self.choices:
            name = preset.get("name", "")
            query = preset.get("query", "")
            btn = QPushButton(name or query)
            btn.setToolTip(query)
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.setStyleSheet(Styles.BUTTON)
            btn.clicked.connect(
                lambda _checked=False, choice=preset: self._select(self._query_for_choice(choice))
            )
            layout.addWidget(btn)

        cancel = QPushButton("キャンセル")
        cancel.setAutoDefault(False)
        cancel.setDefault(False)
        cancel.setStyleSheet(Styles.BUTTON)
        cancel.clicked.connect(self.close)
        layout.addWidget(cancel)

        self.adjustSize()
        pos = QCursor.pos()
        self.move(pos.x() + 12, pos.y() + 12)

    def _query_for_choice(self, choice):
        """選択時点の動的ジェムRegexを既存プリセットへ重複なく結合する。"""
        query = choice.get("query", "")
        provider = choice.get("gem_query_provider")
        gem_query = provider() if callable(provider) else ""
        patterns = split_query_patterns(query)
        patterns.extend(split_query_patterns(gem_query))
        return join_query_patterns(patterns)

    def _select(self, text):
        self.hide()
        parent = self.parent()
        if self.owner is not None:
            self.owner._debug_search(f"select preset text={text!r} initial_target={self.target_hwnd} title={self.owner._window_title(self.target_hwnd)!r}")
        if self.owner is not None:
            self.owner._set_clipboard_text_debug("search preset select", text)
        else:
            QApplication.clipboard().setText(text)
        QApplication.processEvents()
        time.sleep(0.05)
        if self.owner is not None:
            self.owner._debug_search(f"clipboard after preset copy={self.owner._clipboard_text_preview()!r}")

        target_hwnd = self.target_hwnd
        if target_hwnd and hasattr(parent, "_own_top_level_hwnds") and int(target_hwnd) in parent._own_top_level_hwnds():
            if self.owner is not None:
                self.owner._debug_search(f"target was own window; finding external behind hwnd={target_hwnd}")
            target_hwnd = get_next_visible_window_after(target_hwnd, skip_current_process=True)

        if not target_hwnd:
            QMessageBox.warning(self.parent(), "検索文字列の貼り付け", "復帰先ウィンドウを取得できませんでした。")
            return

        self.target_hwnd = target_hwnd
        if self.owner is not None:
            self.owner._search_paste_in_progress = True
            self.owner._debug_search(f"paste in progress ON target={target_hwnd} title={self.owner._window_title(target_hwnd)!r}")
        QTimer.singleShot(220, lambda: self._focus_and_paste(text, target_hwnd))

    def _focus_and_paste(self, text, target_hwnd):
        if self.owner is not None:
            self.owner._debug_search(f"focus start target={target_hwnd} title={self.owner._window_title(target_hwnd)!r} foreground_before={get_foreground_window()} title={self.owner._window_title(get_foreground_window())!r}")
        focused = focus_window(target_hwnd, wait_seconds=0.65)
        if self.owner is not None:
            self.owner._debug_search(f"focus result={focused} foreground_after={get_foreground_window()} title={self.owner._window_title(get_foreground_window())!r}")
        if not focused:
            QMessageBox.warning(
                self.parent(),
                "検索文字列の貼り付け",
                "元のウィンドウを前面化できませんでした。文字列はクリップボードへコピー済みです。",
            )
            if self.owner is not None:
                self.owner._search_paste_in_progress = False
                self.owner._debug_search("paste in progress OFF: focus failed")
            return
        QTimer.singleShot(650, lambda: self._paste_to_search(text))

    def _paste_to_search(self, text):
        try:
            controller = pynput_keyboard.Controller()
            ctrl = pynput_keyboard.Key.ctrl

            def tap(key):
                if self.owner is not None:
                    self.owner._debug_search(f"tap {key!r} foreground={get_foreground_window()} title={self.owner._window_title(get_foreground_window())!r} clipboard={self.owner._clipboard_text_preview()!r}")
                controller.press(key)
                controller.release(key)

            if self.owner is not None:
                self.owner._debug_search(f"send keys start text={text!r} foreground={get_foreground_window()} title={self.owner._window_title(get_foreground_window())!r}")
            with controller.pressed(ctrl):
                if self.owner is not None:
                    self.owner._debug_search("press Ctrl+F")
                tap('f')
            time.sleep(0.20)
            with controller.pressed(ctrl):
                if self.owner is not None:
                    self.owner._debug_search("press Ctrl+V")
                tap('v')
            time.sleep(0.08)
            print(f"[SEARCH TEST] pasted: {text}")
        except Exception as exc:
            print(f"[SEARCH TEST] paste failed: {exc}")
        finally:
            if self.owner is not None:
                self.owner._search_paste_in_progress = False
                self.owner._debug_search("paste in progress OFF: done")
