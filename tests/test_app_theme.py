from src.app_mode import POENAVI_MODE, POETORE_MODE
from src.ui.app_theme import POENAVI_THEME, POETORE_THEME, theme_for_mode


def test_theme_for_mode_keeps_existing_poennavi_green():
    assert theme_for_mode(POENAVI_MODE) is POENAVI_THEME
    assert POENAVI_THEME.accent == "#B0FF7B"


def test_theme_for_mode_uses_poetore_teal_on_neutral_surfaces():
    assert theme_for_mode(POETORE_MODE) is POETORE_THEME
    assert POETORE_THEME.accent == "#49D6B0"
    assert POETORE_THEME.background == "#111416"
    assert POETORE_THEME.panel == "#1A1F21"
