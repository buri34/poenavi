"""State transitions and inherited QSS must survive custom font fitting."""

import pytest
from PySide6.QtCore import QEvent, QSize
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QLayout, QPushButton, QStyle, QStyleOptionButton, QTabWidget,
    QVBoxLayout, QWidget,
)

from src.app_font import bundled_font_path
from src.ui.appearance import (
    apply_application_appearance, configure_appearance, current_appearance,
    fit_theme_fixed_geometry, requested_appearance, suspend_theme_fixed_geometry,
)


@pytest.fixture(autouse=True)
def appearance(qapp, monkeypatch):
    screens = qapp.screens()
    saved, requested = current_appearance(), requested_appearance()
    font, palette = qapp.font(), qapp.palette()
    font_id = QFontDatabase.addApplicationFont(str(bundled_font_path()))
    assert font_id >= 0
    monkeypatch.setattr("src.poetore.ui.PoetoreWindow._close_if_focus_is_still_outside", lambda *a: None)
    monkeypatch.setattr("src.poetore.ui.PoetoreWindow._start_outside_click_listener", lambda *a: None)
    yield
    configure_appearance(None)
    for window in QApplication.topLevelWidgets():
        window.hide()
        window.deleteLater()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()
    configure_appearance(saved, requested=requested)
    qapp.setFont(font)
    qapp.setPalette(palette)
    QFontDatabase.removeApplicationFont(font_id)
    assert screens


def _apply(qapp, size):
    apply_application_appearance(qapp, {"appearance": {"overrides": {
        "base_font_size": size, "font_family": "Noto Sans JP",
    }}})


def _settle(qapp):
    for _ in range(6):
        qapp.sendPostedEvents(None, QEvent.LayoutRequest)
        qapp.processEvents()


@pytest.mark.parametrize("size", [13, 14, 18, 24])
def test_trade_obs_collapse_disable_reenable_and_expand(qapp, size):
    from src.poetore.ui import PoetoreWindow

    _apply(qapp, size)
    window = PoetoreWindow(app_config={})
    window.show()
    _settle(qapp)
    for _ in range(2):
        window.set_obs_streaming_mode(True)
        _settle(qapp)
        assert window.height() == window.maximumHeight() == 30
        assert window.minimumHeight() <= 30
        assert window._title_bar.height() == 24
        window.apply_result_display_size()
        _settle(qapp)
        assert window.height() == 30
        window.show_at_context(activate=False)
        _settle(qapp)
        assert window.height() > 30
        if size != 13:
            assert window.minimumHeight() > 30
        assert window.maximumHeight() == 16777215
        window.collapse_for_obs()
        _settle(qapp)
        assert window.height() == 30
        window.set_obs_streaming_mode(False)
        window.show()
        _settle(qapp)
        if size != 13:
            assert window.minimumHeight() > 30
        assert window.maximumHeight() == 16777215


@pytest.mark.parametrize("size", [14, 18, 24])
def test_settings_area_memo_fits_after_inherited_style(qapp, size):
    from src.ui.settings_dialog import SettingsDialog

    _apply(qapp, size)
    dialog = SettingsDialog(current_config={})
    dialog.show()
    tabs = dialog.findChild(QTabWidget)
    buttons = [button for button in dialog.findChildren(QPushButton)
               if button.text() == "📝 エリアメモ"]
    assert buttons
    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        _settle(qapp)
        for button in buttons:
            if not button.isVisibleTo(dialog):
                continue
            option = QStyleOptionButton()
            button.initStyleOption(option)
            content = button.style().subElementRect(QStyle.SE_PushButtonContents, option, button)
            assert content.width() >= button.fontMetrics().horizontalAdvance(button.text())


@pytest.mark.parametrize("size", [14, 24])
def test_mini_obs_waiting_size_survives_repeated_transitions(qapp, size, monkeypatch):
    from src.ui.mini_navi import MiniNaviOverlay

    _apply(qapp, size)
    monkeypatch.setattr(MiniNaviOverlay, "_apply_click_through", lambda self: None)
    monkeypatch.setattr(MiniNaviOverlay, "_refresh_topmost_state", lambda self: None)
    owner = QWidget()
    owner.config = {"mini_guide_overlay": {"enabled": True}}
    window = MiniNaviOverlay(owner)
    for _ in range(2):
        window.update_content({"text": "次のエリアへ進む", "direction": "right"})
        _settle(qapp)
        assert window.width() > window.OBS_WAITING_SIZE
        assert window.height() > window.OBS_WAITING_SIZE
        window.collapse_for_obs()
        _settle(qapp)
        assert window.size() == QSize(window.OBS_WAITING_SIZE, window.OBS_WAITING_SIZE)


def test_explicit_maximum_and_zero_size_are_preserved(qapp):
    _apply(qapp, 24)
    root = QWidget()
    layout = QVBoxLayout(root)
    button = QPushButton("An intentionally constrained control")
    button.setMaximumSize(90, 20)
    layout.addWidget(button)
    zero = QPushButton("Hidden during a transition")
    zero.setFixedSize(0, 0)
    layout.addWidget(zero)
    root.show()
    _settle(qapp)
    assert button.maximumSize() == QSize(90, 20)
    assert button.minimumWidth() <= 90
    assert button.minimumHeight() <= 20
    assert zero.size() == QSize(0, 0)


def test_parent_padding_change_invalidates_cached_measurement(qapp):
    _apply(qapp, 14)
    root = QWidget()
    layout = QVBoxLayout(root)
    button = QPushButton("📝 エリアメモ")
    button.setFixedWidth(105)
    layout.addWidget(button)
    root.setStyleSheet("QPushButton {font-size: 14px; padding: 2px;}")
    root.show()
    _settle(qapp)
    fit_theme_fixed_geometry(root)
    root.setStyleSheet("QPushButton {font-size: 14px; padding: 2px 30px;}")
    _settle(qapp)
    option = QStyleOptionButton()
    button.initStyleOption(option)
    content = button.style().subElementRect(QStyle.SE_PushButtonContents, option, button)
    assert content.width() >= button.fontMetrics().horizontalAdvance(button.text())


def test_suspension_releases_fitted_limits_and_respects_new_profile(qapp):
    _apply(qapp, 24)
    root = QWidget()
    layout = QVBoxLayout(root)
    button = QPushButton("A larger font needs more room")
    button.setFixedWidth(40)
    layout.addWidget(button)
    root.show()
    _settle(qapp)
    assert button.minimumWidth() > 120
    # A caller-owned profile change must replace the saved pre-fit width.
    button.setFixedWidth(120)
    fit_theme_fixed_geometry(root)
    assert button.minimumWidth() > 120
    suspend_theme_fixed_geometry(root, True)
    assert button.minimumWidth() == button.maximumWidth() == 120
    layout.setSizeConstraint(QLayout.SetNoConstraint)
    for height in [0, 5, 10, 0]:
        root.setFixedHeight(height)
        _settle(qapp)
        fit_theme_fixed_geometry(button)  # Includes suspended ancestors.
        assert root.height() == height
        assert button.width() == 120
    root.setMinimumHeight(0)
    root.setMaximumHeight(16777215)
    suspend_theme_fixed_geometry(root, False)
    fit_theme_fixed_geometry(root)
    _settle(qapp)
    assert root.minimumHeight() > 10
    assert button.width() > 120


@pytest.mark.parametrize("appearance", [None, {"preset": "tokyo_night"}, {"overrides": {"base_font_size": 13}}])
def test_default_font_geometry_fitting_is_a_noop(qapp, appearance):
    apply_application_appearance(qapp, {"appearance": appearance})
    root = QWidget()
    layout = QVBoxLayout(root)
    button = QPushButton("Legacy fixed dimensions")
    button.setFixedSize(50, 20)
    layout.addWidget(button)
    root.show()
    _settle(qapp)
    widgets = [root, button]
    before = [(w.size(), w.minimumSize(), w.maximumSize(), w.font(), w.palette()) for w in widgets]
    fit_theme_fixed_geometry(root)
    suspend_theme_fixed_geometry(root, True)
    suspend_theme_fixed_geometry(root, False)
    _settle(qapp)
    assert [(w.size(), w.minimumSize(), w.maximumSize(), w.font(), w.palette()) for w in widgets] == before
    assert all(not hasattr(w, "_theme_fit_limits") for w in widgets)
