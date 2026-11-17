"""起動モードごとの共通テーマトークン。"""

from dataclasses import dataclass


from src.ui.appearance import POENAVI_TOKENS, POETORE_TOKENS, resolve_app_theme
from src.app_mode import POENAVI_MODE, POETORE_MODE, normalize_app_mode


@dataclass(frozen=True)
class AppTheme:
    accent: str
    text: str
    muted_text: str
    background: str
    panel: str


POENAVI_THEME = AppTheme(
    accent=POENAVI_TOKENS.accent,
    text=POENAVI_TOKENS.text,
    muted_text=POENAVI_TOKENS.muted_text,
    background=POENAVI_TOKENS.background,
    panel=POENAVI_TOKENS.control,
)

# 設定画面はアプリモードにかかわらず、長文を読みやすい共通テーマにする。
SETTINGS_THEME = POENAVI_THEME

POETORE_THEME = AppTheme(
    accent=POETORE_TOKENS.accent,
    text=POETORE_TOKENS.text,
    muted_text=POETORE_TOKENS.muted_text,
    background=POETORE_TOKENS.background,
    panel=POETORE_TOKENS.control,
)


def theme_for_mode(mode: str) -> AppTheme:
    return resolve_app_theme(POETORE_THEME if normalize_app_mode(mode) == POETORE_MODE else POENAVI_THEME)
