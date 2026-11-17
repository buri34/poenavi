"""Offscreen regressions for font limits and game-content colours."""

from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QAbstractButton, QComboBox, QDialog, QLabel, QLineEdit,
    QScrollBar, QSlider, QStyle, QStyleOptionButton, QStyleOptionSlider, QTabWidget, QWidget,
)

from src.app_font import bundled_font_path
from src.poetore.parser import parse_item_text
from src.poetore.trade import PriceListing, PriceResult, TradeStatFilter
from src.poetore.ui import PoetoreWindow, _MOD_COLUMN_TEXT
from src.ui.appearance import (
    apply_application_appearance, configure_appearance, current_appearance,
    requested_appearance, resolve_tokens,
)
from src.ui.main_window import MainWindow
from src.ui.mini_navi import MiniNaviOverlay
from src.ui.settings_dialog import SettingsDialog


@pytest.fixture(autouse=True)
def appearance(qapp, request, registered_fonts):
    saved, requested = current_appearance(), requested_appearance()
    font, palette = qapp.font(), qapp.palette()
    preset = getattr(request.node, "callspec", None)
    configure_appearance({"preset": preset.params.get("preset", "default")} if preset else None)
    yield
    configure_appearance(saved, requested=requested)
    qapp.setFont(font)
    qapp.setPalette(palette)


@pytest.fixture(scope="module")
def registered_fonts(qapp):
    # Retain Qt-owned screen wrappers throughout the offscreen rendering run.
    screens = qapp.screens()
    font_ids = [QFontDatabase.addApplicationFont(str(path)) for path in (
        bundled_font_path(),
        Path(__file__).resolve().parents[1] / "assets/fonts/visitor1.ttf",
    )]
    assert all(font_id >= 0 for font_id in font_ids)
    yield QFontDatabase.applicationFontFamilies(font_ids[1])[0]
    assert screens
    for font_id in font_ids:
        QFontDatabase.removeApplicationFont(font_id)


@pytest.fixture
def main_ui(qapp, maximum_font):
    """Build the real UI, stopping before tray, log watchers and hotkeys start."""
    class Built(Exception):
        pass

    setup_ui = MainWindow.setup_ui

    def build(window):
        setup_ui(window)
        raise Built

    window = MainWindow.__new__(MainWindow)
    with ExitStack() as stack:
        stack.enter_context(patch("src.ui.main_window.ConfigManager.load_config", return_value={}))
        for method in ("_run_startup_update_gate", "_ensure_poe_version_selected"):
            stack.enter_context(patch.object(MainWindow, method, return_value=True))
        stack.enter_context(patch.object(MainWindow, "_sync_voicevox_service"))
        stack.enter_context(patch.object(MainWindow, "_restore_progress_flags"))
        stack.enter_context(patch.object(MainWindow, "setup_ui", build))
        with pytest.raises(Built):
            window.__init__()
    yield window
    # closeEvent belongs to the running application, whose services aren't started.
    window.hide()
    window.deleteLater()


def _render(qapp, widget):
    widget.show()
    qapp.processEvents()
    assert not widget.grab().isNull()


def _button_contents(button):
    option = QStyleOptionButton()
    button.initStyleOption(option)
    return button.style().subElementRect(QStyle.SE_PushButtonContents, option, button)


@pytest.mark.parametrize("profile", ["small", "medium", "large"])
@pytest.mark.parametrize("size", [13, 24])
@pytest.mark.parametrize("custom_family", [False, True])
def test_filter_chips_fit_font_and_keep_default_height(qapp, profile, size, custom_family, registered_fonts):
    overrides = {"base_font_size": size}
    if custom_family:
        overrides["font_family"] = registered_fonts
    apply_application_appearance(qapp, {"appearance": {"overrides": overrides}})
    window = PoetoreWindow(app_config={"poetore": {"result_font_size": profile}})
    try:
        chip = window.corrupted_combo
        chip.show()
        _render(qapp, window)
        if size == 13 and not custom_family:
            assert chip.height() == {"small": 25, "medium": 25, "large": 27}[profile]
        else:
            for _, chip in window._filter_chips:
                if isinstance(chip, QAbstractButton):
                    assert _button_contents(chip).height() >= chip.fontMetrics().height(), chip.text()
    finally:
        window.close()


@pytest.mark.parametrize("preset", ["default", "tokyo_night", "vscode_dark_2026"])
def test_main_fixed_controls_fit_font(qapp, main_ui, preset):
    _render(qapp, main_ui)
    assert main_ui.segment_summary_label.minimumHeight() >= main_ui.segment_summary_label.fontMetrics().lineSpacing() * 2 + 4
    assert main_ui.lap_content.rect().contains(main_ui.segment_summary_label.geometry())
    assert main_ui.timer_content.rect().contains(main_ui.lap_content.geometry())
    assert main_ui.timer_container.rect().contains(main_ui.timer_content.geometry())
    assert main_ui.timer_container.rect().contains(main_ui.start_btn.geometry())
    for control in (main_ui.start_btn, main_ui.segment_summary_label):
        while control.parentWidget() is not None:
            assert control.parentWidget().rect().contains(control.geometry()), control.objectName()
            control = control.parentWidget()
    for button in main_ui.findChildren(QAbstractButton):
        if button.minimumHeight() == button.maximumHeight() and button.text():
            assert _button_contents(button).height() >= button.fontMetrics().height(), button.text()
        if button.minimumWidth() == button.maximumWidth() and button.text():
            assert _button_contents(button).width() >= button.fontMetrics().horizontalAdvance(button.text()), button.text()
    main_ui.lap_times[0] = 3661.55
    main_ui.lap_record_order = [1]
    main_ui.current_act = 2
    main_ui.update_lap_display()
    qapp.processEvents()
    for labels in main_ui.lap_label_widgets:
        for label in labels:
            assert label.width() >= label.sizeHint().width(), label.text()
    expanded_height = main_ui.timer_container.minimumHeight()
    main_ui._set_timer_expanded(False)
    assert main_ui.timer_container.minimumHeight() < expanded_height
    main_ui._set_timer_expanded(True)
    _render(qapp, main_ui)
    assert main_ui.timer_content.rect().contains(main_ui.lap_content.geometry())
    with patch("src.ui.main_window.ConfigManager.save_config"):
        main_ui.toggle_lap()
        assert main_ui.timer_container.minimumHeight() < expanded_height
        main_ui.toggle_lap()
    _render(qapp, main_ui)
    assert main_ui.timer_content.rect().contains(main_ui.lap_content.geometry())


@pytest.fixture
def maximum_font(qapp):
    settings = current_appearance()
    settings["overrides"]["base_font_size"] = 24
    apply_application_appearance(qapp, {"appearance": settings})


@pytest.mark.parametrize("mode", ["normal", "compact"])
def test_mini_navi_fixed_controls_fit_font(qapp, maximum_font, mode, monkeypatch):
    monkeypatch.setattr(MiniNaviOverlay, "_apply_click_through", lambda self: None)
    monkeypatch.setattr(MiniNaviOverlay, "_refresh_topmost_state", lambda self: None)
    owner = QWidget()
    owner.config = {"mini_guide_overlay": {"enabled": True, "display_mode": mode}}
    overlay = MiniNaviOverlay(owner)
    try:
        overlay.update_content(
            {"text": "次のエリアへ進む", "direction": "right"},
            exp_guide={"player_level": 99, "enemy_level": 100, "status": "適正レベル"},
        )
        _render(qapp, overlay)
        for button in overlay.lock_button_window.findChildren(QAbstractButton):
            assert _button_contents(button).height() >= button.fontMetrics().height(), button.text()
            assert _button_contents(button).width() >= button.fontMetrics().horizontalAdvance(button.text()), button.text()
        if mode == "normal":
            assert overlay.exp_label.width() >= overlay.exp_label.sizeHint().width()
    finally:
        overlay.lock_button_window.close()
        overlay.close()
        owner.close()
        overlay.lock_button_window.deleteLater()
        overlay.deleteLater()
        owner.deleteLater()
        qapp.sendPostedEvents(None, QEvent.DeferredDelete)
        qapp.processEvents()


def test_settings_fixed_fields_fit_font(qapp, maximum_font):
    dialog = SettingsDialog(current_config={})
    try:
        _render(qapp, dialog)
        tabs = dialog.findChild(QTabWidget)
        for index in range(tabs.count()):
            tabs.setCurrentIndex(index)
            _render(qapp, dialog)
        for widget in dialog.findChildren(QWidget):
            if isinstance(widget, (QAbstractButton, QComboBox)) and widget.minimumWidth() == widget.maximumWidth():
                assert widget.width() >= widget.minimumSizeHint().width(), repr(widget)
        assert dialog.opacity_value_label.width() >= dialog.opacity_value_label.sizeHint().width()
    finally:
        dialog.close()


@pytest.mark.parametrize("profile", ["small", "medium", "large"])
def test_trade_dynamic_chip_and_result_rows_fit_font(qapp, maximum_font, profile):
    window = PoetoreWindow(app_config={"poetore": {"result_font_size": profile}})
    item = parse_item_text("""Item Class: Body Armours
Rarity: Rare
Test Armour
Sacred Chainmail
--------
Item Level: 100
""")
    try:
        window._configure_item_level(item)
        _render(qapp, window)
        for button in (window.mod_conditions_toggle, window.clear_mod_conditions_button,
                       window.hidden_mods_toggle, window.mod_sources_toggle):
            assert _button_contents(button).width() >= button.fontMetrics().horizontalAdvance(button.text()), button.text()
        assert window.item_level_tag.width() >= window.item_level_tag.layout().minimumSize().width()
        window.map_tier_chip.setValues(17, 17)
        window.map_tier_chip.show()
        window.base_percentile_chip.setValues(100, 100)
        window.base_percentile_chip.show()
        qapp.processEvents()
        for chip in (window.map_tier_chip, window.base_percentile_chip):
            assert chip.width() >= chip.layout().minimumSize().width()
        window._parsed_item = replace(item, rarity="Unique")
        window.mod_sources_toggle.setChecked(True)
        window._populate_stat_filters((TradeStatFilter(
            "explicit.test", "ライフ最大値 +100", 100, "explicit", True,
            read_value=100, roll_min=10, roll_max=100, better=1,
            source_texts=("元のModの説明文",), source_headings=("元Mod",),
        ),))
        window._show_price_result(PriceResult("Standard", "query", 1, (PriceListing(100, "chaos"),)))
        _render(qapp, window)
        row = window.mod_filter_tree.topLevelItem(0)
        for item_row, column in ((row, _MOD_COLUMN_TEXT), (row.child(0), 0)):
            cell = window.mod_filter_tree.itemWidget(item_row, column)
            assert cell.height() >= cell.minimumSizeHint().height()
            for label in cell.findChildren(QLabel):
                assert label.height() >= label.fontMetrics().height()
        slider = window.findChild(QWidget, "uniqueRollSlider")
        assert slider.height() - 6 >= slider.fontMetrics().height()
        price_row = window.price_list.topLevelItem(0)
        assert window.price_list.visualItemRect(price_row).height() >= window.price_list.fontMetrics().height()
        window._app_config["poetore"]["result_font_size"] = "large"
        window.apply_result_display_size()
        _render(qapp, window)
        assert slider.height() - 6 >= slider.fontMetrics().height()
        for item_row, column in ((row, _MOD_COLUMN_TEXT), (row.child(0), 0)):
            cell = window.mod_filter_tree.itemWidget(item_row, column)
            assert cell.height() >= cell.minimumSizeHint().height()
    finally:
        window.close()


@pytest.mark.parametrize("preset", ["default", "tokyo_night", "vscode_dark_2026"])
@pytest.mark.parametrize("category, expected", [("boss", "#ff9944"), ("town", "#888888"), ("non_combat", "#888888")])
def test_area_category_colors_are_fixed(qapp, main_ui, preset, category, expected):
    configure_appearance({"preset": preset, "overrides": {"danger": "#123456", "muted_text": "#654321"}})
    main_ui.monster_levels = {"test_area": {"exclude": category}}
    main_ui.zone_data = {}
    with (
        patch.object(main_ui, "_format_zone_display_name", side_effect=lambda name: name),
        patch.object(main_ui, "_update_act4_checklist_for_zone"),
        patch.object(main_ui, "_is_town_zone", return_value=False),
        patch.object(main_ui, "_get_zone_id", return_value="test_area"),
        patch.object(main_ui, "_update_guide_and_map"),
    ):
        main_ui.on_zone_entered("Test area", actual_entry=False)
    assert f"color: {expected};" in main_ui.advice_label.styleSheet()


def test_clear_and_lap_progress_keep_game_colors(qapp, main_ui):
    from src.ui.styles import Styles

    configure_appearance({"preset": "tokyo_night", "overrides": {"warning": "#123456", "overlay_text": "#654321", "accent": "#112233"}})
    with patch.object(main_ui, "_auto_lap_kitava"), patch.object(main_ui, "_update_guide_and_map"):
        main_ui.on_act10_cleared()
    assert "color: #ffd700;" in main_ui.advice_label.styleSheet()
    assert "color: rgba(176, 255, 123, 0.7);" in Styles.LAP_ITEM_COMPLETED
    assert "color: #b0ff7b;" in Styles.LAP_ITEM_CURRENT
    assert "color: rgba(128, 128, 128, 0.6);" in Styles.LAP_ITEM_PENDING


def test_act4_completion_and_optional_availability_keep_game_colors(qapp):
    from src.ui.act4_checklist import Act4ChecklistWindow

    configure_appearance({"preset": "tokyo_night", "overrides": {"accent": "#123456", "warning": "#654321", "overlay_border": "#112233"}})
    window = Act4ChecklistWindow()
    try:
        style = window.outer.styleSheet()
        complete = style.split("#act4ChecklistComplete", 1)[1].split("}", 1)[0]
        optional = style.split("#act4OptionalTitle", 1)[1].split("}", 1)[0]
        assert "color: #b0ff7b;" in complete
        assert "rgba(176, 255, 123, 120)" in complete
        assert "color: #f0c674;" in optional
        window.set_optional_available(True)
        assert "rgba(98, 72, 22, 150)" in window.optional_frame.styleSheet()
        assert "#f0c674" in window.optional_frame.styleSheet()
        window.set_optional_available(False)
        assert "rgba(240, 198, 116, 70)" in window.optional_frame.styleSheet()
    finally:
        window.close()


def _contrast(first, second):
    def luminance(color):
        channels = [color.redF(), color.greenF(), color.blueF()]
        channels = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4 for channel in channels]
        return sum(channel * weight for channel, weight in zip(channels, (.2126, .7152, .0722)))
    light, dark = sorted([luminance(first), luminance(second)], reverse=True)
    return (light + .05) / (dark + .05)


@pytest.mark.parametrize("preset", ["default", "tokyo_night", "vscode_dark_2026"])
def test_trade_scrollbar_rendered_contrast(qapp, preset):
    configure_appearance({"preset": preset})
    window = PoetoreWindow(app_config={})
    try:
        bar = QScrollBar(Qt.Vertical, window)
        bar.setRange(0, 100)
        bar.setPageStep(10)
        bar.setGeometry(0, 0, 10, 200)
        _render(qapp, window)
        bar.show()
        qapp.processEvents()
        option = QStyleOptionSlider()
        bar.initStyleOption(option)
        handle = bar.style().subControlRect(QStyle.CC_ScrollBar, option, QStyle.SC_ScrollBarSlider, bar)
        rendered = bar.grab().toImage()
        contrast = _contrast(rendered.pixelColor(handle.center()), rendered.pixelColor(bar.width() // 2, 180))
        assert contrast >= 3, (preset, contrast)
        if preset == "default":
            assert contrast == pytest.approx(4.27, abs=.1)
    finally:
        window.close()


@pytest.mark.parametrize("preset", ["tokyo_night", "vscode_dark_2026"])
def test_other_scrollbars_rendered_contrast(qapp, main_ui, preset):
    from src.ui.gem_tracker_widget import GemTrackerWidget
    from src.ui.vendor_search_dialog import VendorSearchPresetDialog

    dialog = SettingsDialog(current_config={})
    vendor = VendorSearchPresetDialog()
    gems = GemTrackerWidget()
    try:
        styles = [widget.styleSheet() for root in (main_ui, vendor, gems)
                  for widget in root.findChildren(QWidget)
                  if "QScrollBar::handle" in widget.styleSheet()]
        assert len(styles) >= 4  # guide, gems, maps, vendor helper
        for index, style in enumerate(styles + [dialog.styleSheet()]):
            host = QDialog()
            host.setProperty("dialogTheme", dialog.property("dialogTheme"))
            host.setStyleSheet(f"QDialog {{background: {resolve_tokens({'preset': preset}).background};}}" + style)
            try:
                for orientation in (Qt.Vertical, Qt.Horizontal):
                    if orientation == Qt.Vertical and "QScrollBar:vertical" not in style:
                        continue
                    if orientation == Qt.Horizontal and "QScrollBar:horizontal" not in style:
                        continue
                    bar = QScrollBar(orientation, host)
                    bar.setRange(0, 100)
                    bar.setPageStep(10)
                    bar.resize(16, 200) if orientation == Qt.Vertical else bar.resize(200, 16)
                    _render(qapp, host)
                    option = QStyleOptionSlider()
                    bar.initStyleOption(option)
                    handle = bar.style().subControlRect(QStyle.CC_ScrollBar, option, QStyle.SC_ScrollBarSlider, bar)
                    rendered = bar.grab().toImage()
                    track = rendered.pixelColor(bar.width() // 2, 180) if orientation == Qt.Vertical else rendered.pixelColor(180, bar.height() // 2)
                    ratio = _contrast(rendered.pixelColor(handle.center()), track)
                    assert ratio >= 3, (preset, index, orientation, ratio)
                    bar.hide()
            finally:
                host.close()
    finally:
        vendor.close()
        gems.close()
        dialog.close()


@pytest.mark.parametrize("preset", ["tokyo_night", "vscode_dark_2026"])
def test_preset_borders_and_focus_remain_visible(qapp, preset):
    from PySide6.QtGui import QColor

    tokens = resolve_tokens({"preset": preset})
    for surface in (tokens.background, tokens.surface, tokens.control):
        assert _contrast(QColor(tokens.border), QColor(surface)) >= 1.4
        assert _contrast(QColor(tokens.border_strong), QColor(surface)) >= 3
        assert _contrast(QColor(tokens.accent), QColor(surface)) >= 3
    dialog = SettingsDialog(current_config={})
    try:
        edit = QLineEdit(dialog)
        edit.setGeometry(20, 20, 200, 60)
        edit.show()
        _render(qapp, dialog)
        edit.setFocus()
        qapp.processEvents()
        frame = edit.grab().toImage()
        assert _contrast(frame.pixelColor(0, 30), frame.pixelColor(4, 30)) >= 3
        slider = QSlider(Qt.Horizontal, dialog)
        slider.setGeometry(20, 100, 200, 30)
        slider.show()
        qapp.processEvents()
        frame = slider.grab().toImage()
        assert _contrast(frame.pixelColor(100, 15), QColor(tokens.background)) >= 1.4
    finally:
        dialog.close()
