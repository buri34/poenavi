"""Inventory-based offscreen audit at representative application font sizes.

No fitting is done by this test: it inspects the geometry the application gives
its widgets. Tabs are visited, dynamic trade rows are populated, and painter
text has its own inspectors below rather than being silently skipped.
"""

import ast
import importlib
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QComboBox, QDialog,
    QGroupBox, QLabel, QLineEdit, QStyle, QStyleOptionButton,
    QStyleOptionComboBox, QStyleOptionFrame, QTabWidget, QToolButton, QWidget,
)

from src.app_font import bundled_font_path
from src.ui.appearance import (
    MIN_FONT_SIZE, MAX_FONT_SIZE, apply_application_appearance, configure_appearance,
    current_appearance, requested_appearance,
)


# Deliberate elision/scrolling, keyed by the actual widget class/property.
# These exceptions still have their height checked. They are not a blanket
# exemption for labels, buttons, editable fields, or all fixed-size controls.
WIDTH_ALLOWLIST = {
    "ElidedLabel": "Rate item names elide at the right; the tooltip has the full name.",
    "compactAction": "Trade action popup shows the complete choices; its closed control is compact.",
    "editableText": "Free text/path inputs scroll horizontally; their line height is still required.",
}


# Exercise the entire inventory at each size, without multiplying every size
# by every family. The alternate family retains its full maximum-size audit.
# Default geometry intentionally preserves main, including its pre-existing
# clipping; test_theme_geometry_states checks the default fitter stays inert.
FONT_CASES = [("bundled", size) for size in (MIN_FONT_SIZE, 14, 18, MAX_FONT_SIZE)] + [("alternate", MAX_FONT_SIZE)]


@pytest.fixture(autouse=True, params=FONT_CASES, ids=[f"{family}-{size}" for family, size in FONT_CASES])
def maximum_font(qapp, monkeypatch, request):
    screens = qapp.screens()  # Keep Windows offscreen screen wrappers alive.
    saved, requested = current_appearance(), requested_appearance()
    font, palette, mode = qapp.font(), qapp.palette(), qapp.property("appMode")
    font_ids = [QFontDatabase.addApplicationFont(str(path)) for path in (
        bundled_font_path(), Path(__file__).resolve().parents[1] / "assets/fonts/visitor1.ttf")]
    assert all(font_id >= 0 for font_id in font_ids)
    family, size = request.param
    overrides = {"base_font_size": size}
    if family == "alternate":
        overrides["font_family"] = QFontDatabase.applicationFontFamilies(font_ids[1])[0]
    apply_application_appearance(qapp, {"appearance": {"overrides": overrides}})
    monkeypatch.setattr("src.ui.poetore_settings_dialog.PoetoreSettingsDialog._refresh_trade_leagues", lambda *a: None)
    monkeypatch.setattr("src.poetore.ui.PoetoreWindow._close_if_focus_is_still_outside", lambda *a: None)
    monkeypatch.setattr("src.poetore.ui.PoetoreWindow._start_outside_click_listener", lambda *a: None)
    monkeypatch.setattr("src.ui.map_check.MapCheckWindow.focusOutEvent", lambda *a: None)
    monkeypatch.setattr("src.ui.map_check.MapCheckWindow.event", QDialog.event)
    yield
    for window in QApplication.topLevelWidgets():
        window.hide()
        window.deleteLater()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()
    configure_appearance(saved, requested=requested)
    qapp.setFont(font)
    qapp.setPalette(palette)
    qapp.setProperty("appMode", mode)
    for font_id in font_ids:
        QFontDatabase.removeApplicationFont(font_id)
    assert screens


WINDOWS = {
    "act4_checklist": ["Act4ChecklistWindow"],
    "startup_dialogs": ["StartupSelectionDialog", "RouteSelectionDialog"],
    "settings_dialog": ["SettingsDialog", "AreaNoteDialog", "GuideEditorDialog", "GuideSummaryEditorDialog", "MiniNaviEditorDialog", "GemShopSearchTermOverridesDialog"],
    "poetore_settings_dialog": ["PoetoreSettingsDialog"],
    "gem_tracker_widget": ["PoBImportDialog", "PoBSkillSetSelectionDialog"],
    "cheat_sheets": ["CheatSheetManagerDialog", "CheatSheetOverlay"],
    "map_check": ["MapModManagerDialog", "MapCheckWindow"],
    "map_viewer": ["MapImageDialog"],
    "memo_dialog": ["MemoDialog"],
    "vendor_search_dialog": ["VendorSearchPresetDialog"],
    "search_paste_dialog": ["SearchStringPasteTestDialog"],
    "expedition_settings_dialog": ["ExpeditionSettingsDialog", "ExpeditionRegionSelector"],
    "desecration_settings_dialog": ["DesecrationSettingsDialog", "DesecrationRegionSelector"],
    "heist_settings_dialog": ["HeistSettingsDialog"],
    "update_dialogs": ["UpdateAvailableDialog", "UpdateProgressDialog"],
    "exchange_rate_management_dialog": ["ExchangeRateManagementDialog"],
    "detached_panel": ["DetachedPanelWindow"],
    "main_window": ["MainWindow"],
    "poetore_mode_window": ["PoetoreModeWindow"],
    "mini_navi": ["MiniNaviOverlay"],
}
CASES = [(module, name) for module, names in WINDOWS.items() for name in names]


def _window(module, name, version, tmp_path):
    cls = getattr(importlib.import_module("src.ui." + module), name)
    config = {"poe_version": version, "hotkeys": {}, "notified_update_version": "99.99.99"}
    if name in ("MainWindow", "PoetoreModeWindow"):
        # Build real widgets but do not start tray, filesystem, OCR or network services.
        method = "setup_ui" if name == "MainWindow" else "_build_ui"
        original = getattr(cls, method)
        class Built(Exception):
            pass
        def build(window):
            original(window)
            raise Built
        window = cls.__new__(cls)
        with ExitStack() as stack:
            stack.enter_context(patch(f"src.ui.{module}.ConfigManager.load_config", return_value=config))
            for optional in ("_run_startup_update_gate", "_ensure_poe_version_selected", "_sync_voicevox_service", "_restore_progress_flags"):
                if hasattr(cls, optional):
                    stack.enter_context(patch.object(cls, optional, return_value=True))
            stack.enter_context(patch.object(cls, method, build))
            with pytest.raises(Built):
                window.__init__()
        return window
    if name in ("SettingsDialog", "PoetoreSettingsDialog"):
        return cls(current_config=config)
    if name == "AreaNoteDialog":
        return cls(None, "テストエリア", "メモ")
    if name == "GuideEditorDialog":
        return cls(None, "テストエリア", {"text": "テスト"}, zone_id="poe2_test" if version == "poe2" else "test", flag_guides={"complete": {"text": "完了後"}})
    if name == "GuideSummaryEditorDialog":
        return cls(None, "テストエリア", {"default": {"summary": "要約"}, "flags": {"complete": {"summary": "完了後"}}})
    if name == "MiniNaviEditorDialog":
        return cls(None, "テストエリア", [{"title": "通常", "key": "default", "text": "次へ", "mini_navi": []}], show_direction=version == "poe1")
    if name == "PoBSkillSetSelectionDialog":
        return cls([{"id": "1", "title": "Act leveling", "active": True}, {"id": "2", "title": "Endgame"}])
    if name in ("CheatSheetManagerDialog", "CheatSheetOverlay", "MapModManagerDialog", "MapCheckWindow"):
        return cls({})
    if name == "MapImageDialog":
        return cls(str(tmp_path / "missing.png"), poe_version=version)
    if name == "VendorSearchPresetDialog":
        return cls(poe_version=version)
    if name == "SearchStringPasteTestDialog":
        return cls(0, [{"name": "検索例", "query": "test"}])
    if name.endswith("RegionSelector"):
        return cls(QRect(0, 0, 1920, 1080))
    if name == "UpdateAvailableDialog":
        from src.update.release_client import ReleaseInfo
        return cls(ReleaseInfo("99.99.99", "Release notes", "https://example.com", "https://example.com/a.zip", "https://example.com/a.sha256"), True)
    if name == "UpdateProgressDialog":
        return cls("99.99.99")
    if name == "DetachedPanelWindow":
        from src.ui.gem_tracker_widget import GemTrackerWidget
        return cls("gems", "ジェム取得支援", GemTrackerWidget(), lambda *a: None, lambda *a: None)
    if name == "ExchangeRateManagementDialog":
        from src.poetore.exchange_rate_settings import ExchangeRatePairStore, default_rate_pairs_config
        from src.poetore.exchange_catalog import exchange_catalog_by_id
        config["poetore"] = {"exchange_rate_pairs": default_rate_pairs_config()}
        return cls(None, poe_version=version, store=ExchangeRatePairStore(config, lambda *a: None), available_item_ids=list(exchange_catalog_by_id(version)), icon_cache=Mock())
    if name == "MiniNaviOverlay":
        owner = QWidget()
        owner.config = {"mini_guide_overlay": {"enabled": True}}
        window = cls(owner)
        window.update_content({"text": "次のエリアへ進む", "direction": "right"}, exp_guide={"player_level": 99, "enemy_level": 100, "status": "適正レベル"})
        window._audit_owner = owner
        return window
    return cls()


def _label_requirement(widget):
    if widget.wordWrap():
        return QSize(widget.minimumSizeHint().width(), widget.heightForWidth(widget.width()))
    return widget.sizeHint()


def geometry_failures(root):
    failures = []
    for widget in [root, *root.findChildren(QWidget)]:
        if not widget.isVisibleTo(root) or not isinstance(widget, (QLabel, QAbstractButton, QLineEdit, QComboBox, QGroupBox)):
            continue
        text = widget.currentText() if isinstance(widget, QComboBox) else widget.title() if isinstance(widget, QGroupBox) else widget.text()
        if not text or (isinstance(widget, QLabel) and not widget.pixmap().isNull()):
            continue
        rect = widget.rect()
        exception = ("ElidedLabel" if type(widget).__name__ == "ElidedLabel"
                     else "compactAction" if isinstance(widget, QComboBox) and widget.property("compactAction") else None)
        skip_width = exception in WIDTH_ALLOWLIST
        if isinstance(widget, QLabel):
            needed = _label_requirement(widget)
        elif isinstance(widget, QAbstractButton):
            if isinstance(widget, QToolButton):
                needed = widget.sizeHint()
                if needed.width() > rect.width() or needed.height() > rect.height():
                    failures.append(f"QToolButton {text!r}: needs {needed}, has {rect.size()}")
                continue
            option = QStyleOptionButton()
            if hasattr(widget, "initStyleOption"):
                widget.initStyleOption(option)
            element = QStyle.SE_CheckBoxContents if widget.inherits("QCheckBox") else QStyle.SE_RadioButtonContents if widget.inherits("QRadioButton") else QStyle.SE_PushButtonContents
            rect = widget.style().subElementRect(element, option, widget)
            metrics = widget.fontMetrics()
            needed = QSize(max(metrics.horizontalAdvance(line.replace("&", "")) for line in text.splitlines()), metrics.height() * len(text.splitlines()))
            if not widget.icon().isNull():
                needed.setWidth(needed.width() + widget.iconSize().width() + 4)
        elif isinstance(widget, QLineEdit):
            option = QStyleOptionFrame()
            widget.initStyleOption(option)
            rect = widget.style().subElementRect(QStyle.SE_LineEditContents, option, widget)
            needed = widget.fontMetrics().size(Qt.TextSingleLine, text)
            # Editable text is intentionally horizontally scrollable; numeric
            # controls must nevertheless fit their actual displayed value.
            if widget.validator() is None and not widget.isReadOnly():
                skip_width = "editableText" in WIDTH_ALLOWLIST
        elif isinstance(widget, QComboBox):
            option = QStyleOptionComboBox()
            widget.initStyleOption(option)
            rect = widget.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField, widget)
            needed = widget.fontMetrics().size(Qt.TextSingleLine, text)
        else:  # Group titles, independently of child-layout dimensions.
            needed = widget.fontMetrics().size(Qt.TextShowMnemonic, text)
            rect = widget.rect()
        if (not skip_width and needed.width() > rect.width()) or needed.height() > rect.height():
            failures.append(f"{type(widget).__name__} {widget.objectName()} {text[:70]!r}: needs {needed.width()}x{needed.height()}, has {rect.width()}x{rect.height()}")
        parent = widget.parentWidget()
        if parent is not None and parent.layout() is not None and not parent.rect().contains(widget.geometry()):
            failures.append(f"{type(widget).__name__} {widget.objectName()} {text[:70]!r}: outside parent layout {type(parent).__name__}")
    return failures


def _audit_pages(qapp, root):
    def settle():
        previous = None
        for _ in range(8):
            qapp.sendPostedEvents(None, QEvent.LayoutRequest)
            qapp.processEvents()
            sizes = [(widget.size(), widget.pos()) for widget in [root, *root.findChildren(QWidget)]]
            if sizes == previous:
                break
            previous = sizes
    root.show()
    settle()
    tabs = root.findChildren(QTabWidget)
    failures = []
    failures.extend(geometry_failures(root))
    for tab in tabs:
        for ancestor in tabs:
            for index in range(ancestor.count()):
                if ancestor.widget(index).isAncestorOf(tab):
                    ancestor.setCurrentIndex(index)
        for index in range(tab.count()):
            tab.setCurrentIndex(index)
            settle()
            failures.extend(geometry_failures(root))
    return sorted(set(failures))


@pytest.mark.parametrize("mode", ["poenavi", "poetore"])
@pytest.mark.parametrize("version", ["poe1", "poe2"])
@pytest.mark.parametrize("module,name", CASES, ids=[name for _, name in CASES])
def test_all_window_text_fits(qapp, tmp_path, module, name, version, mode):
    qapp.setProperty("appMode", mode)
    window = _window(module, name, version, tmp_path)
    assert not (failures := _audit_pages(qapp, window)), "\n" + "\n".join(failures)


@pytest.mark.parametrize("version", ["poe1", "poe2"])
@pytest.mark.parametrize("profile", ["small", "medium", "large"])
def test_trade_text_fits_every_profile(qapp, version, profile):
    from src.poetore.ui import PoetoreWindow
    from src.poetore.trade import TradeStatFilter
    window = PoetoreWindow(app_config={"poe_version": version, "poetore": {"result_font_size": profile}})
    window._populate_stat_filters((TradeStatFilter("explicit.stat_1", "最大ライフ +#", 123.5, "prefix", True, max_value=123.5, tier_tags=(1, 2)),))
    for _, chip in window._filter_chips:
        chip.show()
    window.corrupted_combo.setCurrentIndex(1)
    from src.poetore.trade import PriceListing, PriceResult
    window._show_price_result(PriceResult("Standard", "query", 1, (PriceListing(100, "chaos"),)))
    assert not (failures := _audit_pages(qapp, window)), "\n" + "\n".join(failures)


def test_trade_obs_transitions_keep_legacy_collapsed_height(qapp):
    from src.poetore.ui import PoetoreWindow

    window = PoetoreWindow(app_config={})
    assert not (failures := _audit_pages(qapp, window)), "\n".join(failures)
    for _ in range(2):
        window.set_obs_streaming_mode(True)
        qapp.processEvents()
        assert window.height() == window.maximumHeight() == 30
        assert window._title_bar.height() == 24
        window.show_at_context(activate=False)
        assert not (failures := _audit_pages(qapp, window)), "\n".join(failures)
        assert window.height() > 30
        window.collapse_for_obs()
        qapp.processEvents()
        assert window.height() == 30
        window.set_obs_streaming_mode(False)
        assert not (failures := _audit_pages(qapp, window)), "\n".join(failures)
        assert window.maximumHeight() == 16777215


@pytest.mark.parametrize("module", ["expedition_settings_dialog", "desecration_settings_dialog", "heist_settings_dialog"])
def test_anonymous_example_dialogs(qapp, module):
    cls = getattr(importlib.import_module("src.ui." + module), {
        "expedition_settings_dialog": "ExpeditionSettingsDialog", "desecration_settings_dialog": "DesecrationSettingsDialog", "heist_settings_dialog": "HeistSettingsDialog"}[module])
    owner = cls(example_image_path="missing-example.png")
    captured = []
    def inspect(dialog):
        captured.append(_audit_pages(qapp, dialog))
        return QDialog.Rejected
    with patch.object(QDialog, "exec", inspect):
        owner._show_example_popup()
    assert captured == [[]]


def test_category_choice_and_separate_mini_controls(qapp, tmp_path):
    from src.poetore.poe2.desecration_overlay import CategoryChoiceOverlay, CATEGORY_LABELS
    category = CategoryChoiceOverlay()
    category.show_categories(tuple(CATEGORY_LABELS), QPoint(0, 0))
    assert not (failures := _audit_pages(qapp, category)), "\n".join(failures)
    mini = _window("mini_navi", "MiniNaviOverlay", "poe1", tmp_path)
    assert not (failures := _audit_pages(qapp, mini.lock_button_window)), "\n".join(failures)


@pytest.mark.parametrize("display_mode", ["standard", "compact"])
def test_mini_all_text_in_both_modes(qapp, tmp_path, display_mode):
    mini = _window("mini_navi", "MiniNaviOverlay", "poe1", tmp_path)
    mini._audit_owner.config["mini_guide_overlay"]["display_mode"] = display_mode
    mini.update_content({"text": "次のエリアへ進む\nボスを倒して街へ戻る", "direction": "right"},
                        exp_guide={"player_level": 99, "enemy_level": 100, "status": "適正レベル"}, has_area_note=True)
    assert not (failures := _audit_pages(qapp, mini)), "\n".join(failures)


@pytest.mark.parametrize("font_size", [14, 18, 24])
def test_act4_all_profiles_and_completion(qapp, font_size):
    from src.ui.act4_checklist import Act4ChecklistWindow, Act4ChecklistState, ACT4_REQUIRED_ITEMS
    owner = QWidget()
    owner.config = {"mini_guide_overlay": {"font_size": font_size}}
    window = Act4ChecklistWindow(owner)
    window.apply_settings()
    window.set_optional_available(True)
    state = Act4ChecklistState()
    for item in ACT4_REQUIRED_ITEMS:
        state.set_checked(item.zone_id, True)
    window.apply_state(state)
    assert not (failures := _audit_pages(qapp, window)), "\n".join(failures)


def test_unknown_mod_and_augment_hints_keep_game_colors(qapp):
    from src.poetore.models import ItemModifier, ParsedItem
    from src.poetore.ui import PoetoreWindow
    from src.ui.map_check import MapCheckWindow
    from src.ui.appearance import COLOR_ROLES
    configure_appearance({"preset": "tokyo_night", "overrides": {role: "#123456" for role in COLOR_ROLES}})
    trade = PoetoreWindow(app_config={})
    assert "color: #79b8b2;" in trade.installed_augment_recovery_hint.styleSheet()
    assert 'color: #ff5757;' in trade.styleSheet().split('cycleToggle[alert="true"]', 1)[1].split('}', 1)[0]
    map_check = MapCheckWindow({})
    map_check._render(ParsedItem("Maps", "Rare", "Test map", "Test", "map", modifiers=(ItemModifier("未知のMod", stat_id="missing"),)))
    label = next(label for label in map_check.findChildren(QLabel) if "未認識Mod" in label.text())
    assert "color:#efb366;" in label.styleSheet()
    assert not (failures := _audit_pages(qapp, map_check)), "\n".join(failures)


def test_standard_qt_dialogs(qapp):
    from PySide6.QtWidgets import QColorDialog, QFileDialog, QInputDialog, QMessageBox
    message = QMessageBox(QMessageBox.Warning, "設定", "外観を反映するには再起動が必要です。", QMessageBox.Ok | QMessageBox.Cancel)
    input_dialog = QInputDialog()
    input_dialog.setLabelText("プリセット名を入力してください")
    files = QFileDialog()
    files.setOption(QFileDialog.DontUseNativeDialog)
    color = QColorDialog()
    color.setOption(QColorDialog.DontUseNativeDialog)
    for dialog in (message, input_dialog, files, color):
        assert not (failures := _audit_pages(qapp, dialog)), "\n".join(failures)


def test_window_inventory_is_complete():
    # Embedded widgets are covered through their actual owning windows. New
    # window/component classes must be explicitly assigned to a generating
    # scenario, rather than disappearing from a hand-written factory list.
    embedded = {
        "_UniqueRollSlider", "_BinaryToggle", "_CycleButton", "_AreaSegmentedControl",
        "_NumericFilterChip", "_RequiredNumericFilterChip", "_SparklineWidget", "_PoetoreTitleBar",
        "AppearanceSettingsWidget", "AppInfoWidget", "CustomCommandSettingsWidget",
        "ElidedLabel", "DecimalAlignedRateLabel", "CustomExchangeRatePanel",
        "_RegisteredPairRow", "_RegisteredPairsWidget", "RegionPreview", "ClickableImageLabel",
        "GemTrackerWidget", "HighAccuracyOcrPackGroup", "ClickableThumb", "MapThumbnailWidget",
        "MiniNaviLockButtonWindow", "_PoetoreModeTitleBar", "HotkeyButton", "TriggerKeyButton", "AutoHideHotkeyWidget", "RichTextEdit",
    }
    painter_windows = {"ExpeditionPriceOverlay", "CurioRegionSelector", "DesecrationTierOverlay", "CategoryChoiceOverlay", "OutlinedLabel", "HighAccuracyOcrStatusOverlay", "PoetoreWindow"}
    from PySide6 import QtWidgets
    bases = {name for name in dir(QtWidgets) if isinstance(value := getattr(QtWidgets, name), type) and issubclass(value, QWidget)}
    classes = {}
    for file in (Path(__file__).resolve().parents[1] / "src").rglob("*.py"):
        for cls in ast.walk(ast.parse(file.read_text(encoding="utf-8-sig"))):
            if isinstance(cls, ast.ClassDef):
                classes[cls.name] = {base.id if isinstance(base, ast.Name) else base.attr if isinstance(base, ast.Attribute) else "" for base in cls.bases}
    found = set()
    while added := {name for name, parents in classes.items() if parents & (bases | found)} - found:
        found.update(added)
    assert found == {name for _, name in CASES} | embedded | painter_windows
