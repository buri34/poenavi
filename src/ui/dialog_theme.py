"""設定・管理ダイアログだけに適用する共通テーマ基盤。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from src.app_mode import POETORE_MODE, normalize_app_mode


@dataclass(frozen=True)
class DialogTheme:
    """対象ダイアログ用の意味トークンと共通寸法。"""

    name: str
    accent: str
    accent_soft: str
    text: str = "#E6ECEA"
    muted_text: str = "#98A39F"
    background: str = "#111416"
    surface: str = "#171B1D"
    control: str = "#1A1F21"
    border: str = "#3B4441"
    border_strong: str = "#59635F"
    selection_control: str = "#4488FF"
    success: str = "#5ED38A"
    warning: str = "#F6C85F"
    danger: str = "#FF6B6B"
    disabled: str = "#66706C"
    font_family: str = "Noto Sans JP"
    title_size: int = 20
    section_size: int = 15
    body_size: int = 13
    caption_size: int = 11
    form_control_height: int = 32
    compact_row_height: int = 24
    radius: int = 6
    compact_radius: int = 4
    scrollbar_width: int = 8
    icon_size: int = 16


POENAVI_DIALOG_THEME = DialogTheme(
    name="poenavi",
    accent="#B0FF7B",
    accent_soft="#22321D",
)

POETORE_DIALOG_THEME = DialogTheme(
    name="poetore",
    accent="#65FFCA",
    accent_soft="#17332B",
)


def dialog_theme_for_mode(mode: str) -> DialogTheme:
    """起動モードに対応する対象ダイアログ用テーマを返す。"""
    return (
        POETORE_DIALOG_THEME
        if normalize_app_mode(mode) == POETORE_MODE
        else POENAVI_DIALOG_THEME
    )


def theme_asset_path(filename: str) -> Path:
    """source／PyInstallerの両方で共通UIアセットを解決する。"""
    relative = Path("assets") / "icons" / filename
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / relative)
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / relative)
    candidates.append(Path(__file__).resolve().parents[2] / relative)
    for path in candidates:
        if path.is_file():
            return path
    return candidates[-1]


def _qss_url(filename: str) -> str:
    return str(theme_asset_path(filename)).replace("\\", "/")


def build_dialog_stylesheet(theme: DialogTheme) -> str:
    """対象ダイアログへ明示適用する、スコープ済み共通QSSを生成する。"""
    root = f'QDialog[dialogTheme="{theme.name}"]'
    checkbox_asset = _qss_url("ui-checkbox-checked.svg")
    radio_asset = _qss_url("ui-radio-checked.svg")
    return f"""
{root} {{
    background-color: {theme.background};
    color: {theme.text};
    font-family: "{theme.font_family}";
    font-size: {theme.body_size}px;
}}
{root} QWidget {{
    color: {theme.text};
    font-family: "{theme.font_family}";
    font-size: {theme.body_size}px;
}}
{root} QFrame[uiRole="surface"],
{root} QWidget[uiRole="surface"] {{
    background-color: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: {theme.radius}px;
}}
{root} QLabel[uiRole="title"] {{
    color: {theme.accent};
    font-size: {theme.title_size}px;
    font-weight: 700;
}}
{root} QLabel[uiRole="section"] {{
    color: {theme.text};
    font-size: {theme.section_size}px;
    font-weight: 600;
}}
{root} QLabel[uiRole="muted"] {{
    color: {theme.muted_text};
    font-size: {theme.caption_size}px;
}}
{root} QLabel[state="success"] {{ color: {theme.success}; }}
{root} QLabel[state="warning"] {{ color: {theme.warning}; }}
{root} QLabel[state="error"] {{ color: {theme.danger}; }}
{root} QLabel:disabled {{ color: {theme.disabled}; }}

{root} QPushButton,
{root} QToolButton {{
    min-height: {theme.form_control_height}px;
    padding: 0 12px;
    color: {theme.text};
    background-color: {theme.control};
    border: 1px solid {theme.border_strong};
    border-radius: {theme.radius}px;
}}
{root} QPushButton:hover,
{root} QToolButton:hover {{
    background-color: {theme.surface};
    border-color: {theme.accent};
}}
{root} QPushButton:focus,
{root} QToolButton:focus {{ border-color: {theme.accent}; }}
{root} QPushButton:pressed,
{root} QToolButton:pressed {{ background-color: {theme.background}; }}
{root} QPushButton[buttonRole="primary"] {{
    color: {theme.background};
    background-color: {theme.accent};
    border-color: {theme.accent};
    font-weight: 700;
}}
{root} QPushButton[buttonRole="primary"]:hover {{
    color: {theme.background};
    background-color: {theme.accent};
    border-color: {theme.text};
}}
{root} QPushButton[buttonRole="danger"] {{
    color: {theme.text};
    background-color: {theme.control};
    border-color: {theme.border_strong};
}}
{root} QPushButton[buttonRole="danger"]:hover {{
    color: {theme.danger};
    border-color: {theme.danger};
}}
{root} QPushButton:disabled,
{root} QToolButton:disabled {{
    color: {theme.disabled};
    background-color: {theme.surface};
    border-color: {theme.border};
}}
{root} QToolButton[iconRole="operation"] {{
    min-width: {theme.form_control_height}px;
    max-width: {theme.form_control_height}px;
    padding: 0;
    color: {theme.muted_text};
}}
{root} QToolButton[iconRole="operation"]:hover {{ color: {theme.accent}; }}
{root} QToolButton[iconRole="danger"]:hover {{
    color: {theme.danger};
    border-color: {theme.danger};
}}

{root} QLineEdit,
{root} QComboBox,
{root} QSpinBox,
{root} QDoubleSpinBox,
{root} QDateEdit,
{root} QTimeEdit {{
    min-height: {theme.form_control_height}px;
    padding: 0 9px;
    color: {theme.text};
    background-color: {theme.control};
    border: 1px solid {theme.border_strong};
    border-radius: {theme.radius}px;
    selection-background-color: {theme.accent_soft};
    selection-color: {theme.text};
}}
{root} QTextEdit,
{root} QPlainTextEdit {{
    padding: 7px 9px;
    color: {theme.text};
    background-color: {theme.control};
    border: 1px solid {theme.border_strong};
    border-radius: {theme.radius}px;
    selection-background-color: {theme.accent_soft};
    selection-color: {theme.text};
}}
{root} QLineEdit:focus,
{root} QComboBox:focus,
{root} QSpinBox:focus,
{root} QDoubleSpinBox:focus,
{root} QTextEdit:focus,
{root} QPlainTextEdit:focus {{ border-color: {theme.accent}; }}
{root} QLineEdit[error="true"],
{root} QComboBox[error="true"],
{root} QTextEdit[error="true"] {{ border-color: {theme.danger}; }}
{root} QLineEdit:disabled,
{root} QComboBox:disabled,
{root} QSpinBox:disabled,
{root} QTextEdit:disabled,
{root} QPlainTextEdit:disabled {{
    color: {theme.disabled};
    background-color: {theme.surface};
    border-color: {theme.border};
}}
{root} QComboBox::drop-down {{
    width: 24px;
    border: none;
}}
{root} QComboBox QAbstractItemView {{
    color: {theme.text};
    background-color: {theme.control};
    border: 1px solid {theme.border};
    selection-background-color: {theme.accent_soft};
    selection-color: {theme.text};
}}

{root} QCheckBox,
{root} QRadioButton {{ spacing: 8px; }}
{root} QCheckBox::indicator,
{root} QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    background-color: {theme.control};
    border: 2px solid {theme.border_strong};
}}
{root} QCheckBox::indicator {{ border-radius: 4px; }}
{root} QRadioButton::indicator {{ border-radius: 10px; }}
{root} QCheckBox::indicator:hover,
{root} QRadioButton::indicator:hover {{ border-color: {theme.selection_control}; }}
{root} QCheckBox::indicator:checked {{
    image: url("{checkbox_asset}");
    background-color: {theme.selection_control};
    border-color: {theme.selection_control};
}}
{root} QRadioButton::indicator:checked {{
    image: url("{radio_asset}");
    background-color: {theme.selection_control};
    border-color: {theme.selection_control};
}}
{root} QCheckBox::indicator:disabled,
{root} QRadioButton::indicator:disabled {{
    background-color: {theme.surface};
    border-color: {theme.disabled};
}}

{root} QGroupBox {{
    margin-top: 24px;
    padding: 10px;
    padding-top: 12px;
    background-color: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: {theme.radius}px;
    font-weight: 600;
}}
{root} QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    color: {theme.text};
    background-color: transparent;
}}

{root} QTabWidget::pane {{
    top: -1px;
    background-color: {theme.background};
    border: 1px solid {theme.border};
    border-radius: {theme.radius}px;
}}
{root} QTabBar::tab {{
    min-height: {theme.form_control_height}px;
    padding: 0 14px;
    color: {theme.text};
    background-color: transparent;
    border: none;
    border-bottom: 2px solid transparent;
}}
{root} QTabBar::tab:hover {{ background-color: {theme.surface}; }}
{root} QTabBar::tab:selected {{
    color: {theme.accent};
    border-bottom-color: {theme.accent};
    font-weight: 600;
}}
{root} QTabBar::tab:disabled {{ color: {theme.disabled}; }}

{root} QListView,
{root} QTreeView,
{root} QTableView,
{root} QListWidget,
{root} QTreeWidget,
{root} QTableWidget {{
    color: {theme.text};
    background-color: {theme.control};
    alternate-background-color: {theme.surface};
    border: 1px solid {theme.border};
    border-radius: {theme.radius}px;
    outline: 0;
}}
{root} QAbstractItemView::item {{
    min-height: {theme.form_control_height}px;
    padding: 0 7px;
    border: 1px solid transparent;
}}
{root} QAbstractItemView::item:hover {{ background-color: {theme.surface}; }}
{root} QAbstractItemView::item:selected {{
    color: {theme.text};
    background-color: {theme.accent_soft};
    border-color: {theme.accent};
}}
{root} QWidget[density="compact"] QAbstractItemView::item {{
    min-height: {theme.compact_row_height}px;
    padding: 0 5px;
}}
{root} QWidget[density="compact"] QPushButton,
{root} QWidget[density="compact"] QToolButton {{
    min-height: {theme.compact_row_height}px;
    border-radius: {theme.compact_radius}px;
}}

{root} QScrollBar:vertical {{
    width: {theme.scrollbar_width}px;
    margin: 0;
    background-color: {theme.background};
    border: none;
}}
{root} QScrollBar::handle:vertical {{
    min-height: 28px;
    background-color: {theme.border_strong};
    border-radius: {theme.scrollbar_width // 2}px;
}}
{root} QScrollBar::handle:vertical:hover {{ background-color: {theme.accent}; }}
{root} QScrollBar:horizontal {{
    height: {theme.scrollbar_width}px;
    margin: 0;
    background-color: {theme.background};
    border: none;
}}
{root} QScrollBar::handle:horizontal {{
    min-width: 28px;
    background-color: {theme.border_strong};
    border-radius: {theme.scrollbar_width // 2}px;
}}
{root} QScrollBar::handle:horizontal:hover {{ background-color: {theme.accent}; }}
{root} QScrollBar::add-line,
{root} QScrollBar::sub-line {{ width: 0; height: 0; }}
{root} QScrollBar::add-page,
{root} QScrollBar::sub-page {{ background: transparent; }}

QToolTip {{
    padding: 5px 7px;
    color: {theme.text};
    background-color: {theme.background};
    border: 1px solid {theme.border_strong};
    border-radius: {theme.compact_radius}px;
    font-family: "{theme.font_family}";
    font-size: {theme.caption_size}px;
}}
""".strip()


def apply_dialog_theme(dialog, theme: DialogTheme) -> None:
    """対象ダイアログへ共通テーマを明示適用する。"""
    dialog.setProperty("dialogTheme", theme.name)
    dialog.setProperty("dialogAccent", theme.accent)
    dialog.setStyleSheet(build_dialog_stylesheet(theme))
