import os

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QSizePolicy, QSplitter, QVBoxLayout, QWidget

from src.ui.detached_panel import DetachedPanelWindow
from src.ui.main_window import MainWindow
from src.utils.config_manager import ConfigManager


def _app():
    return QApplication.instance() or QApplication([])


def _window():
    _app()
    host = QWidget()
    layout = QVBoxLayout(host)
    content = QWidget()
    layout.addWidget(content)

    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.config = {"detached_panels": {"timer": {"detached": False}}}
    window.panel_registry = {
        "timer": {
            "content": content,
            "host": host,
            "layout": layout,
            "index": 0,
            "title": "タイマー",
            "detach_button": None,
        }
    }
    window.detached_panel_windows = {}
    return window, content, layout


def test_detach_panel_removes_content_from_main_layout_and_restore_returns_it(monkeypatch):
    window, content, layout = _window()
    monkeypatch.setattr(ConfigManager, "save_config", lambda _config: None)

    window.detach_panel("timer")

    assert layout.indexOf(content) == -1
    assert window.detached_panel_windows["timer"].content is content

    window.restore_panel("timer")

    assert layout.indexOf(content) == 0
    assert window.detached_panel_windows == {}


def test_detached_panel_persists_geometry_when_moved_or_resized(monkeypatch):
    window, _content, _layout = _window()
    monkeypatch.setattr(ConfigManager, "save_config", lambda _config: None)
    window.detach_panel("timer")
    panel_window = window.detached_panel_windows["timer"]

    panel_window.setGeometry(41, 52, 420, 280)
    _app().processEvents()

    assert window.config["detached_panels"]["timer"] == {
        "detached": True,
        "x": 41,
        "y": 52,
        "width": 420,
        "height": 280,
    }


def test_restore_detached_panels_uses_saved_geometry(monkeypatch):
    window, _content, _layout = _window()
    monkeypatch.setattr(ConfigManager, "save_config", lambda _config: None)
    window.config["detached_panels"]["timer"] = {
        "detached": True,
        "x": 41,
        "y": 52,
        "width": 420,
        "height": 280,
    }

    window._restore_detached_panels()

    assert window.detached_panel_windows["timer"].geometry().getRect() == (41, 52, 420, 280)


def test_detached_panel_moves_from_its_header_drag_area():
    _app()
    panel_window = DetachedPanelWindow("timer", "タイマー", QWidget(), lambda *_args: None, lambda *_args: None)
    panel_window._drag_offset = QPoint(8, 9)

    panel_window._move_from_global_position(QPoint(108, 209))

    assert panel_window.pos() == QPoint(100, 200)
    assert panel_window.windowFlags() & Qt.FramelessWindowHint


def test_detached_panel_exposes_a_bottom_right_resize_grip():
    _app()
    panel_window = DetachedPanelWindow("timer", "タイマー", QWidget(), lambda *_args: None, lambda *_args: None)

    assert panel_window.resize_grip.parent() is panel_window
    assert panel_window.resize_grip.width() == 18
    assert panel_window.minimumWidth() >= 320
    assert panel_window.minimumHeight() >= 180


def test_resizing_detached_panel_keeps_header_at_its_original_height():
    _app()
    panel_window = DetachedPanelWindow("timer", "タイマー", QWidget(), lambda *_args: None, lambda *_args: None)
    panel_window.show()
    _app().processEvents()
    header_height = panel_window.header.height()

    panel_window.resize(640, 720)
    _app().processEvents()

    assert panel_window.header.height() == header_height
    panel_window.close()


def test_resizing_detached_panel_expands_its_fixed_content_area():
    _app()
    content = QWidget()
    content.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    panel_window = DetachedPanelWindow("timer", "タイマー", content, lambda *_args: None, lambda *_args: None)
    panel_window.show()
    _app().processEvents()
    content_height = content.height()

    panel_window.resize(640, 720)
    _app().processEvents()

    assert content.height() > content_height
    panel_window.close()


def test_detaching_guide_keeps_its_lower_section_in_the_main_layout(monkeypatch):
    _app()
    host = QWidget()
    main_layout = QVBoxLayout(host)
    guide_panel = QWidget()
    main_layout.addWidget(guide_panel)
    splitter = QSplitter(Qt.Vertical)
    splitter.addWidget(QWidget())
    lower_section = QWidget()
    splitter.addWidget(lower_section)

    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.config = {"detached_panels": {"guide": {"detached": False}}}
    window.detached_panel_windows = {}
    window.guide_body_splitter = splitter
    window.guide_lower_widget = lower_section
    window.panel_registry = {
        "guide": {
            "content": guide_panel,
            "layout": main_layout,
            "index": 0,
            "stretch": 1,
            "title": "ガイド",
            "detach_button": None,
            "expand_widgets": (),
        }
    }
    monkeypatch.setattr(ConfigManager, "save_config", lambda _config: None)

    window.detach_panel("guide")

    assert main_layout.indexOf(lower_section) >= 0
    assert lower_section.parentWidget() is host

    window.restore_panel("guide")

    assert main_layout.indexOf(lower_section) == -1
    assert splitter.indexOf(lower_section) == 1


def test_expanding_lap_content_grows_the_detached_timer_without_shrinking_it():
    _app()
    content = QWidget()
    content_layout = QVBoxLayout(content)
    lap_content = QWidget()
    lap_content.setFixedHeight(300)
    lap_content.hide()
    content_layout.addWidget(lap_content)
    panel_window = DetachedPanelWindow("timer", "タイマー", content, lambda *_args: None, lambda *_args: None)
    panel_window.show()
    _app().processEvents()
    initial_height = panel_window.height()

    window = MainWindow.__new__(MainWindow)
    window.detached_panel_windows = {"timer": panel_window}
    lap_content.show()
    MainWindow._adjust_detached_panel_height(window, "timer")

    assert panel_window.height() >= initial_height + 100
    panel_window.close()
