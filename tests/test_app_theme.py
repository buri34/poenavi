from src.app_mode import POENAVI_MODE, POETORE_MODE
from src.ui.app_theme import POENAVI_THEME, POETORE_THEME, SETTINGS_THEME, theme_for_mode


def test_theme_for_mode_keeps_existing_poennavi_green():
    assert theme_for_mode(POENAVI_MODE) is POENAVI_THEME
    assert POENAVI_THEME.accent == "#B0FF7B"


def test_theme_for_mode_uses_poetore_teal_on_neutral_surfaces():
    assert theme_for_mode(POETORE_MODE) is POETORE_THEME
    assert POETORE_THEME.accent == "#65FFCA"
    assert POETORE_THEME.background == "#111416"
    assert POETORE_THEME.panel == "#1A1F21"


def test_settings_theme_is_shared_readable_green_theme():
    assert SETTINGS_THEME is POENAVI_THEME
    assert SETTINGS_THEME.text == "#E9FFBD"
    assert SETTINGS_THEME.muted_text == "#C9D4C2"
    assert SETTINGS_THEME.background == "#101310"
    assert SETTINGS_THEME.panel == "#1E241E"
