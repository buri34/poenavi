"""Regressions found while reviewing restart-only application appearance."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QLabel, QLineEdit, QMessageBox, QStyle, QStyleOptionFrame

from src.app_restart import confirm_mode_switch_restart
from src.app_font import bundled_font_path
from src.poetore.trade import TradeStatFilter
from src.poetore.ui import (
    PoetoreWindow, _MOD_COLUMN_MAX, _MOD_COLUMN_MIN, _MOD_COLUMN_TIER,
)
from src.ui.appearance import (
    COLOR_ROLES, apply_application_appearance, configure_appearance, current_appearance,
    requested_appearance,
)
from src.utils.poe_version_data import POE1, POE2


@pytest.fixture(autouse=True)
def restore_application_appearance(qapp):
    appearance = current_appearance()
    requested = requested_appearance()
    font, palette = qapp.font(), qapp.palette()
    mode = qapp.property("appMode")
    configure_appearance(None)
    yield
    configure_appearance(appearance, requested=requested)
    qapp.setFont(font)
    qapp.setPalette(palette)
    qapp.setProperty("appMode", mode)


@pytest.fixture
def alternate_font_family(qapp):
    # The Windows offscreen plugin has no system fonts. Register real bundled
    # fonts so both the default and alternate-family cases match app startup.
    paths = [
        bundled_font_path(),
        Path(__file__).resolve().parents[1] / "assets" / "fonts" / "visitor1.ttf",
    ]
    font_ids = [QFontDatabase.addApplicationFont(str(path)) for path in paths]
    try:
        assert all(font_id >= 0 for font_id in font_ids)
        yield QFontDatabase.applicationFontFamilies(font_ids[1])[0]
    finally:
        for font_id in font_ids:
            QFontDatabase.removeApplicationFont(font_id)


@pytest.mark.parametrize("setting", ["small", "medium", "large"])
@pytest.mark.parametrize("base_size", [13, 24])
@pytest.mark.parametrize("custom_font", [False, True])
def test_mod_numeric_controls_fit_theme_font(
    qapp, setting, base_size, custom_font, alternate_font_family,
):
    overrides = {"base_font_size": base_size}
    if custom_font:
        overrides["font_family"] = alternate_font_family
    apply_application_appearance(qapp, {"appearance": {
        "overrides": overrides,
    }})
    config = {"poetore": {"result_font_size": setting}}
    window = PoetoreWindow(app_config=config)
    try:
        window._populate_stat_filters((TradeStatFilter(
            "explicit.stat_1", "Life +#", 123.5, "prefix", True,
            max_value=123.5,
        ),))
        window.show()
        qapp.processEvents()
        row = window.mod_filter_tree.topLevelItem(0)
        for column in (_MOD_COLUMN_MIN, _MOD_COLUMN_MAX):
            cell = window.mod_filter_tree.itemWidget(row, column)
            editor = cell.findChild(QLineEdit)
            if base_size == 13 and not custom_font:
                width, height = {"small": (48, 26), "medium": (56, 30), "large": (64, 34)}[setting]
                assert (editor.width(), editor.height()) == (width, height)
            else:
                option = QStyleOptionFrame()
                editor.initStyleOption(option)
                content = editor.style().subElementRect(QStyle.SE_LineEditContents, option, editor)
                assert content.width() - 4 >= editor.fontMetrics().horizontalAdvance(editor.text())
                assert content.height() >= editor.fontMetrics().height()
            assert window.mod_filter_tree.columnWidth(column) >= cell.width()
            assert window.mod_filter_tree.visualItemRect(row).height() >= editor.height() + 6

        # Existing rows and their columns must also grow when changing the panel profile.
        if base_size == 24 and setting == "small":
            config["poetore"]["result_font_size"] = "large"
            window.apply_result_display_size()
            qapp.processEvents()
            editor = window.mod_filter_tree.itemWidget(row, _MOD_COLUMN_MAX).findChild(QLineEdit)
            assert editor.height() > 34
            assert window.mod_filter_tree.visualItemRect(row).height() >= editor.height() + 6
    finally:
        window.close()


@pytest.mark.parametrize("poe_version", [POE1, POE2])
@pytest.mark.parametrize("appearance", [
    {"preset": "default"},
    {"preset": "poetore"},
    {"preset": "poetore", "overrides": {role: "#123456" for role in COLOR_ROLES}},
])
def test_mod_tier_badges_keep_game_colors(qapp, poe_version, appearance):
    configure_appearance(appearance)
    window = PoetoreWindow(app_config={"poe_version": poe_version})
    try:
        window._populate_stat_filters((TradeStatFilter(
            "explicit.stat_1", "Life +#", 100, "prefix", True,
            tier_tags=(1, 2),
        ),))
        row = window.mod_filter_tree.topLevelItem(0)
        badges = window.mod_filter_tree.itemWidget(row, _MOD_COLUMN_TIER).findChildren(QLabel)
        assert [badge.text() for badge in badges] == ["T1", "T2"]
        assert "background: #D8C47A" in badges[0].styleSheet()
        assert "color: #292416" in badges[0].styleSheet()
        assert "color: #CDBB78" in badges[1].styleSheet()
        assert "border: 1px solid #9F9162" in badges[1].styleSheet()
    finally:
        window.close()


@pytest.mark.parametrize("change", [None, "font_family", "base_font_size", "preset", "text"])
def test_restart_compares_requested_appearance_after_font_fallback(qapp, change):
    qapp.setProperty("appMode", "poetore")
    config = {
        "startup": {"preferred_mode": "poetore", "show_mode_selector": False},
        "appearance": {"preset": "poetore", "overrides": {
            "font_family": "Missing-PoENavi-Review-Font", "base_font_size": 18,
        }},
    }
    saved = deepcopy(config)
    with patch("PySide6.QtGui.QFontDatabase.families", return_value=[]):
        apply_application_appearance(qapp, config)
    assert config == saved
    assert "font_family" not in current_appearance()["overrides"]
    if change == "preset":
        config["appearance"]["preset"] = "poenavi"
    elif change is not None:
        config["appearance"]["overrides"][change] = {
            "font_family": "Another-Missing-PoENavi-Font", "base_font_size": 20,
            "text": "#ABCDEF",
        }[change]
    with (
        patch("src.app_restart._ask_mode_switch_restart", return_value=QMessageBox.Cancel) as question,
        patch("src.app_restart.restart_application") as restart,
    ):
        for _ in range(2):
            assert confirm_mode_switch_restart(None, config) is False
        assert question.call_count == (0 if change is None else 2)
        restart.assert_not_called()
