"""起動モードごとの共通テーマトークン。"""

from dataclasses import dataclass

from src.app_mode import POENAVI_MODE, POETORE_MODE, normalize_app_mode


@dataclass(frozen=True)
class AppTheme:
    accent: str
    text: str
    muted_text: str
    background: str
    panel: str


POENAVI_THEME = AppTheme(
    accent="#B0FF7B",
    text="#E9FFBD",
    muted_text="#C9D4C2",
    background="#101310",
    panel="#1E241E",
)

# 設定画面はアプリモードにかかわらず、長文を読みやすい共通テーマにする。
SETTINGS_THEME = POENAVI_THEME

POETORE_THEME = AppTheme(
    accent="#65FFCA",
    text="#E6ECEA",
    muted_text="#98A39F",
    background="#111416",
    panel="#1A1F21",
)


def theme_for_mode(mode: str) -> AppTheme:
    return POETORE_THEME if normalize_app_mode(mode) == POETORE_MODE else POENAVI_THEME
