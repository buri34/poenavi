import copy
import json
import re

import pytest
from PySide6.QtGui import QColor, QFontDatabase, QPalette

from src.ui.appearance import (
    COLOR_ROLES, DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE,
    POENAVI_TOKENS, POETORE_TOKENS, TOKYO_NIGHT_TOKENS, VSCODE_DARK_2026_TOKENS,
    apply_application_appearance, configure_appearance, current_appearance,
    normalize_appearance, resolve_tokens, theme_color, theme_font_size,
    theme_qcolor, theme_rgba,
)
from src.ui.app_theme import POENAVI_THEME, POETORE_THEME, theme_for_mode
from src.ui.dialog_theme import (
    POENAVI_DIALOG_THEME, POETORE_DIALOG_THEME, build_dialog_stylesheet,
    dialog_theme_for_mode,
)
from src.ui.styles import Styles
from src.utils.config_manager import ConfigManager


@pytest.fixture(autouse=True)
def reset_appearance(qapp):
    previous = current_appearance()
    font, palette = qapp.font(), qapp.palette()
    configure_appearance(None)
    yield
    configure_appearance(previous)
    qapp.setFont(font)
    qapp.setPalette(palette)


@pytest.mark.parametrize("value", [None, [], "poetore", 42, {"preset": []}, {"preset": "missing"}])
def test_invalid_settings_fall_back_to_legacy_default(value):
    assert normalize_appearance(value) == {"preset": "default", "overrides": {}}


def test_invalid_tokens_cannot_inject_qss_or_break_font_scaling():
    settings = normalize_appearance({"preset": "poetore", "overrides": {
        "text": "red; background: white", "border": "#12", "unknown": "#123456",
        "overlay_bg": "#01020380", "font_family": "Font'; color: red;",
        "base_font_size": True, "accent": "#abcdef",
    }})
    assert settings == {"preset": "poetore", "overrides": {"accent": "#ABCDEF"}}
    assert resolve_tokens(settings).text == POETORE_TOKENS.text


@pytest.mark.parametrize("size", [0, 8, 25, "14", 13.5, None])
def test_invalid_font_sizes_use_preset(size):
    assert resolve_tokens({"overrides": {"base_font_size": size}}).base_font_size == 13


def test_default_keeps_all_three_legacy_themes_and_imported_styles():
    assert theme_for_mode("poenavi") is POENAVI_THEME
    assert theme_for_mode("poetore") is POETORE_THEME
    assert dialog_theme_for_mode("poenavi") is POENAVI_DIALOG_THEME
    assert dialog_theme_for_mode("poetore") is POETORE_DIALOG_THEME
    assert Styles.TEXT_COLOR == "#b0ff7b"
    assert "rgba(0, 0, 0, 180)" in Styles.MAIN_WINDOW
    assert theme_font_size(96) == 96
    assert theme_color("text", "#123456") == "#123456"


@pytest.mark.parametrize("preset, expected", [
    ("poenavi", POENAVI_TOKENS), ("poetore", POETORE_TOKENS),
    ("tokyo_night", TOKYO_NIGHT_TOKENS), ("vscode_dark_2026", VSCODE_DARK_2026_TOKENS),
])
def test_explicit_preset_is_shared_across_modes(preset, expected):
    configure_appearance({"preset": preset})
    for mode in ("poenavi", "poetore"):
        assert theme_for_mode(mode).accent == expected.accent
        assert dialog_theme_for_mode(mode).accent == expected.accent
        assert dialog_theme_for_mode(mode).text == expected.text


@pytest.mark.parametrize("preset, background, text, accent", [
    ("tokyo_night", "#1A1B26", "#A9B1D6", "#7AA2F7"),
    ("vscode_dark_2026", "#121314", "#BFBFBF", "#48A0C7"),
])
def test_upstream_presets_resolve_opaque_colors_and_apply_at_startup(qapp, preset, background, text, accent):
    settings = normalize_appearance({"preset": preset})
    assert settings == {"preset": preset, "overrides": {}}
    tokens = resolve_tokens(settings)
    for role in COLOR_ROLES:
        color = getattr(tokens, role)
        assert re.fullmatch(r"#[0-9A-F]{6}", color), role
        assert QColor(color).isValid(), role
    assert tokens.background == tokens.overlay_bg == background
    assert tokens.text == tokens.overlay_text == text
    assert tokens.accent == accent
    assert tokens.font_family == DEFAULT_FONT_FAMILY
    assert tokens.base_font_size == DEFAULT_FONT_SIZE
    apply_application_appearance(qapp, {"appearance": settings})
    assert qapp.palette().color(QPalette.Window).name().upper() == background
    assert qapp.palette().color(QPalette.Text).name().upper() == text
    assert qapp.font().family() == DEFAULT_FONT_FAMILY
    assert theme_qcolor("overlay_bg", 0, 0, 0, 137).alpha() == 137
    rgb = tuple(int(background[index:index + 2], 16) for index in (1, 3, 5))
    assert theme_rgba("overlay_bg", 0, 0, 0, .35) == f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, 0.35)"
    overridden = resolve_tokens({"preset": preset, "overrides": {"text": "#ABCDEF"}})
    assert overridden.text == "#ABCDEF"
    assert overridden.background == background


def _contrast_ratio(first, second):
    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))

    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + .05) / (darker + .05)


@pytest.mark.parametrize("preset", ["tokyo_night", "vscode_dark_2026"])
def test_upstream_presets_keep_main_text_pairs_at_aa_contrast(preset):
    tokens = resolve_tokens({"preset": preset})
    for foreground in ("text", "muted_text", "accent", "success", "warning", "danger"):
        for background in ("background", "surface", "control"):
            ratio = _contrast_ratio(getattr(tokens, foreground), getattr(tokens, background))
            assert ratio >= 4.5, (preset, foreground, background, ratio)
    assert _contrast_ratio(tokens.text, tokens.accent_soft) >= 4.5
    assert _contrast_ratio(tokens.background, tokens.accent) >= 4.5  # Primary buttons.
    assert _contrast_ratio(tokens.overlay_text, tokens.overlay_bg) >= 4.5  # Before caller opacity.
    assert _contrast_ratio(tokens.selection_control, tokens.control) >= 3


def test_overrides_apply_after_import_and_preserve_opacity_and_hierarchy():
    configure_appearance({"overrides": {
        "overlay_bg": "#123456", "overlay_text": "#FEDCBA", "border": "#778899",
        "base_font_size": 20,
    }})
    assert Styles.TEXT_COLOR == "#FEDCBA"
    assert "rgba(18, 52, 86, 180)" in Styles.MAIN_WINDOW
    assert "#778899" in Styles.MAIN_WINDOW
    assert theme_rgba("overlay_bg", 0, 0, 0, .35) == "rgba(18, 52, 86, 0.35)"
    color = theme_qcolor("overlay_bg", 0, 0, 0, 137)
    assert color.getRgb() == (18, 52, 86, 137)
    theme = dialog_theme_for_mode("poenavi")
    assert theme.body_size == 20
    assert theme.title_size == round(20 * 20 / 13)
    assert theme.body_size < theme.section_size < theme.title_size
    assert theme.border_strong == "#778899"
    assert f"font-size: {theme.body_size}px" in build_dialog_stylesheet(POENAVI_DIALOG_THEME)


def test_surface_override_covers_panels_and_controls():
    configure_appearance({"overrides": {"surface": "#203040"}})
    assert theme_for_mode("poetore").panel == "#203040"
    assert dialog_theme_for_mode("poenavi").control == "#203040"


def test_startup_selects_installed_font_and_falls_back_for_missing_font(qapp):
    from src.app_font import apply_bundled_ui_font

    apply_bundled_ui_font(qapp)
    family = QFontDatabase.families()[0]
    apply_application_appearance(qapp, {"appearance": {"overrides": {
        "font_family": family, "base_font_size": 18,
    }}})
    assert qapp.font().family() == family
    assert qapp.font().pixelSize() == 18
    apply_application_appearance(qapp, {"appearance": {"overrides": {"font_family": "Missing-PoENavi-Font-123"}}})
    assert qapp.font().family() == DEFAULT_FONT_FAMILY


@pytest.mark.parametrize("legacy", ["#e9ffbd", "#b0ff7b"])
def test_dead_legacy_default_does_not_change_existing_appearance(legacy):
    migrated = ConfigManager._migrate_config({"text_color": legacy})
    assert "text_color" not in migrated
    assert migrated["appearance"] == normalize_appearance(None)


def test_legacy_color_migration_is_idempotent_and_explicit_override_wins():
    source = {"schemaVersion": 22, "text_color": "#123456", "appearance": {
        "preset": "poetore", "overrides": {"overlay_text": "#abcdef"},
    }}
    original = copy.deepcopy(source)
    migrated = ConfigManager._migrate_config(source)
    assert migrated["appearance"]["overrides"]["overlay_text"] == "#ABCDEF"
    assert ConfigManager._migrate_config(migrated) == migrated
    assert source == original


def test_save_load_roundtrip_does_not_apply_appearance_until_restart(monkeypatch, tmp_path):
    monkeypatch.setenv(ConfigManager.ENV_USER_DATA_DIR, str(tmp_path))
    monkeypatch.setattr(ConfigManager, "migrate_startup_legacy_user_files", lambda: [])
    monkeypatch.setattr(ConfigManager, "_get_legacy_config_paths", lambda: [])
    config = ConfigManager.load_config()
    config["appearance"] = {"preset": "poetore", "overrides": {"text": "#abcdef", "base_font_size": 17}}
    ConfigManager.save_config(config)
    loaded = ConfigManager.load_config()
    assert loaded["appearance"] == {"preset": "poetore", "overrides": {"text": "#ABCDEF", "base_font_size": 17}}
    assert current_appearance() == normalize_appearance(None)
    assert "text_color" not in json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    configure_appearance(loaded["appearance"])
    assert dialog_theme_for_mode("poenavi").text == "#ABCDEF"


def test_game_content_colors_remain_fixed():
    from src.ui.gem_tracker_widget import ATTR_COLORS

    before = dict(ATTR_COLORS)
    configure_appearance({"preset": "poetore", "overrides": {"text": "#123456"}})
    assert ATTR_COLORS == before


@pytest.mark.parametrize("family, expected", [(None, "DSEG7 Classic"), ("Arial", "Arial")])
def test_timer_keeps_its_default_font_and_accepts_user_font(qapp, family, expected):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout
    from src.ui.main_window import MainWindow

    configure_appearance({"overrides": {"font_family": family}} if family else None)
    container = QWidget()
    QVBoxLayout(container)
    state = SimpleNamespace(
        TIMER_SIZES={"large": {"main": 96, "ms": 32, "container_pad": 8}},
        timer_size="large", _custom_font_family="DSEG7 Classic", timer_container=container,
        **{key: QLabel() for key in ("lbl_hours", "lbl_c1", "lbl_mins", "lbl_c2", "lbl_secs", "lbl_ms")},
    )
    MainWindow._apply_timer_size(state)
    assert expected in state.lbl_hours.styleSheet()
    assert expected in state.lbl_ms.styleSheet()


def test_main_background_override_preserves_existing_opacity(qapp):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QWidget
    from src.ui.main_window import MainWindow

    configure_appearance({"overrides": {"overlay_bg": "#123456"}})
    central = QWidget()
    state = SimpleNamespace(centralWidget=lambda: central, guide_text_frame=QWidget(), guide_container=QWidget())
    MainWindow._apply_bg_opacity(state, 50)
    assert "rgba(18, 52, 86, 127)" in central.styleSheet()
    assert "rgba(18, 52, 86, 80)" in state.guide_text_frame.styleSheet()
    assert "rgba(18, 52, 86, 69)" in state.guide_container.styleSheet()


def test_trade_results_use_shared_colors_and_scale_existing_size_profile(qapp):
    from src.poetore.ui import PoetoreWindow

    configure_appearance({"preset": "poetore", "overrides": {
        "text": "#EEDDCC", "surface": "#203040", "accent": "#AABBCC",
        "base_font_size": 20, "font_family": "Noto Sans JP",
    }})
    window = PoetoreWindow(app_config={})
    try:
        style = window.styleSheet()
        assert "#EEDDCC" in style
        assert "#AABBCC" in style
        assert "rgba(32, 48, 64, 246)" in style
        assert f"font-size: {theme_font_size(12)}px" in style
        assert 'font-family:  "Noto Sans JP"' in style
    finally:
        window.close()


def test_mode_title_bar_uses_startup_snapshot_even_when_imported_earlier(qapp):
    from PySide6.QtWidgets import QWidget
    from src.ui.poetore_mode_window import _PoetoreModeTitleBar

    class Owner(QWidget):
        def minimize_to_tray(self):
            pass

    configure_appearance({"overrides": {"text": "#DDEEFF"}})
    owner = Owner()
    bar = _PoetoreModeTitleBar(owner)
    assert "#DDEEFF" in bar.minimize_button.styleSheet()
    assert "#DDEEFF" in bar.close_button.styleSheet()
    owner.close()
