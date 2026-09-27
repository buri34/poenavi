"""ぽえなび／ぽえとれの設定画面で共有するアプリ情報UI。"""

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from src.ui.app_theme import AppTheme
from src.ui.dialog_theme import DialogTheme


class AppInfoWidget(QWidget):
    """アプリ情報を一元管理し、呼び出し元のテーマで表示する。"""

    def __init__(
        self,
        theme: AppTheme | DialogTheme,
        parent=None,
        update_check_callback=None,
    ):
        super().__init__(parent)
        shared_dialog_theme = isinstance(theme, DialogTheme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        try:
            from main import __version__
        except ImportError:
            __version__ = "不明"

        version_label = QLabel(f"ぽえなび v{__version__}")
        version_label.setObjectName("appInfoVersion")
        if shared_dialog_theme:
            version_label.setProperty("uiRole", "title")
        else:
            version_label.setStyleSheet(
                f"color: {theme.text}; font-size: 18px; font-weight: bold;"
            )
        layout.addWidget(version_label)
        self.update_button = QPushButton("アップデートを確認")
        self.update_button.setObjectName("appInfoUpdateButton")
        if shared_dialog_theme:
            self.update_button.setProperty("buttonRole", "primary")
        else:
            self.update_button.setStyleSheet(
                f"QPushButton {{ background: {theme.accent}; color: #101010; "
                "border: none; border-radius: 6px; padding: 10px 20px; "
                "font-size: 13px; font-weight: bold; }"
            )
        self.update_button.setCursor(Qt.PointingHandCursor)
        self.update_button.setEnabled(update_check_callback is not None)
        if update_check_callback is not None:
            self.update_button.clicked.connect(update_check_callback)
        layout.addWidget(self.update_button)
        layout.addWidget(
            self._link_button(
                "GitHub（最新版のダウンロード）",
                "https://github.com/buri34/poenavi/releases",
                None
                if shared_dialog_theme
                else (
                    f"background: {theme.panel}; color: {theme.text}; "
                    f"border: 1px solid {theme.accent};"
                ),
            )
        )
        layout.addWidget(self._separator(theme))

        support_title = QLabel("☕ ぽえなびを応援する")
        if shared_dialog_theme:
            support_title.setProperty("uiRole", "section")
        else:
            support_title.setStyleSheet(
                f"color: {theme.text}; font-size: 16px; font-weight: bold;"
            )
        layout.addWidget(support_title)
        support_desc = QLabel(
            "ぽえなびを気に入っていただけたら、応援いただけると嬉しいです。\n"
            "いただいたサポートは、開発環境の維持・改善に充てさせていただきます。"
        )
        if not shared_dialog_theme:
            support_desc.setStyleSheet(f"color: {theme.text}; font-size: 13px;")
        support_desc.setWordWrap(True)
        layout.addWidget(support_desc)

        for text, url, color in (
            (
                "OFUSE（おふせ）で応援する",
                "https://ofuse.me/48eca107",
                "rgba(255,147,69,200)",
            ),
            ("Ko-fi で応援する", "https://ko-fi.com/buri8857", "rgba(41,171,224,200)"),
            (
                "Patreon で応援する",
                "https://www.patreon.com/cw/Buri8857",
                "rgba(255,66,77,200)",
            ),
        ):
            layout.addWidget(
                self._link_button(
                    text,
                    url,
                    None
                    if shared_dialog_theme
                    else (f"background: {color}; color: white; border: none;"),
                )
            )

        support_note = QLabel("※ ブラウザが開きます")
        if shared_dialog_theme:
            support_note.setProperty("uiRole", "muted")
        else:
            support_note.setStyleSheet(f"color: {theme.muted_text}; font-size: 11px;")
        layout.addWidget(support_note)
        layout.addWidget(self._separator(theme))

        self.disclaimer_label = QLabel(
            "ぽえなびは無料の非公式ツールです。"
            "Grinding Gear Gamesとの提携・承認関係はありません。"
        )
        self.disclaimer_label.setObjectName("appDisclaimerLabel")
        self.disclaimer_label.setWordWrap(True)
        if shared_dialog_theme:
            self.disclaimer_label.setProperty("uiRole", "muted")
        else:
            self.disclaimer_label.setStyleSheet(
                f"color: {theme.muted_text}; font-size: 12px;"
            )
        layout.addWidget(self.disclaimer_label)

        self.ndlocr_license_label = QLabel(
            "補助OCR: NDLOCR-Lite 1.3.1 © 国立国会図書館 / CC BY 4.0\n"
            "国立国会図書館の公認・提携製品ではありません。"
        )
        self.ndlocr_license_label.setObjectName("ndlocrLicenseLabel")
        self.ndlocr_license_label.setWordWrap(True)
        if shared_dialog_theme:
            self.ndlocr_license_label.setProperty("uiRole", "muted")
        else:
            self.ndlocr_license_label.setStyleSheet(
                f"color: {theme.muted_text}; font-size: 11px;"
            )
        layout.addWidget(self.ndlocr_license_label)
        layout.addStretch()

    @staticmethod
    def _separator(theme: AppTheme | DialogTheme):
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"color: {theme.accent};")
        return separator

    @staticmethod
    def _link_button(text: str, url: str, colors: str | None):
        button = QPushButton(text)
        if colors is not None:
            button.setStyleSheet(
                f"QPushButton {{ {colors} border-radius: 6px; padding: 10px 20px; "
                "font-size: 13px; font-weight: bold; }"
            )
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda: webbrowser.open(url))
        return button
