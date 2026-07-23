import os

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QPushButton, QSizePolicy, QSplitter, QVBoxLayout, QWidget

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


def test_detached_panel_preserves_the_content_size_policy():
    _app()
    content = QWidget()
    content.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    panel_window = DetachedPanelWindow("timer", "タイマー", content, lambda *_args: None, lambda *_args: None)

    assert content.sizePolicy().verticalPolicy() == QSizePolicy.Fixed
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


def test_collapsing_lap_content_shrinks_the_detached_timer_to_its_contents():
    _app()
    content = QWidget()
    content_layout = QVBoxLayout(content)
    lap_content = QWidget()
    lap_content.setFixedHeight(300)
    content_layout.addWidget(lap_content)
    panel_window = DetachedPanelWindow("timer", "タイマー", content, lambda *_args: None, lambda *_args: None)
    panel_window.show()
    _app().processEvents()
    panel_window.resize(640, 720)
    lap_content.hide()

    window = MainWindow.__new__(MainWindow)
    window.detached_panel_windows = {"timer": panel_window}
    MainWindow._fit_detached_panel_height(window, "timer")

    assert panel_window.height() < 720
    panel_window.close()


def test_toggle_lap_hides_lap_content_in_a_detached_timer(monkeypatch):
    _app()
    window = MainWindow.__new__(MainWindow)
    window.lap_expanded = True
    window.lap_content = QWidget()
    window.lap_content.show()
    window.lap_toggle_btn = QPushButton()
    window.config = {}
    window.detached_panel_windows = {"timer": QWidget()}
    window._adjust_detached_panel_height = lambda _panel_id: None
    window._fit_detached_panel_height = lambda _panel_id: None
    monkeypatch.setattr(ConfigManager, "save_config", lambda _config: None)

    window.toggle_lap()

    assert not window.lap_expanded
    assert window.lap_content.isHidden()
    assert window.lap_toggle_btn.text() == "▶ ラップタイム"


def test_detached_panel_applies_main_window_settings():
    _app()
    panel_window = DetachedPanelWindow("timer", "タイマー", QWidget(), lambda *_args: None, lambda *_args: None)

    panel_window.apply_window_settings({"window_opacity": 80, "text_opacity": 60, "always_on_top": True, "window_locked": True})

    assert panel_window.windowOpacity() == 0.8
    assert panel_window.windowFlags() & Qt.WindowStaysOnTopHint
    assert panel_window.window_locked
    assert not panel_window.resize_grip.isVisible()
    assert panel_window.content.graphicsEffect().opacity() == 0.6
    panel_window.close()


def test_register_detachable_panel_places_button_on_title_row():
    _app()
    host = QWidget()
    layout = QVBoxLayout(host)
    title = QPushButton("▼ タイマー")
    body = QWidget()
    panel_controls = QWidget()
    layout.addWidget(title)
    layout.addWidget(body)

    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.panel_registry = {}
    window._register_detachable_panel(
        "timer", "タイマー", [title, body], layout, header_widgets=(panel_controls,),
    )

    record = window.panel_registry["timer"]
    header_layout = record["header_widget"].layout()
    assert header_layout.indexOf(title) == 0
    assert header_layout.indexOf(panel_controls) < header_layout.indexOf(record["detach_button"])
    assert header_layout.indexOf(record["detach_button"]) >= 0
    assert record["content"].layout().count() == 2


def test_detaching_timer_keeps_global_controls_in_main_and_timer_controls_detached(monkeypatch):
    _app()
    host = QWidget()
    main_layout = QVBoxLayout(host)
    timer_panel = QWidget()
    panel_layout = QVBoxLayout(timer_panel)
    timer_controls = QWidget()
    timer_button_layout = QHBoxLayout(timer_controls)
    start_button = QPushButton("Start")
    global_controls = QWidget()
    timer_button_layout.addWidget(start_button)
    timer_button_layout.addWidget(global_controls)
    panel_layout.addWidget(timer_controls)
    main_layout.addWidget(timer_panel)

    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.config = {"detached_panels": {"timer": {"detached": False}}}
    window.detached_panel_windows = {}
    window.timer_button_layout = timer_button_layout
    window.global_controls_widget = global_controls
    window.panel_registry = {
        "timer": {
            "content": timer_panel,
            "layout": main_layout,
            "index": 0,
            "stretch": 0,
            "title": "タイマー",
            "detach_button": None,
            "expand_widgets": (),
        }
    }
    monkeypatch.setattr(ConfigManager, "save_config", lambda _config: None)

    window.detach_panel("timer")

    assert main_layout.indexOf(global_controls) == 0
    assert start_button.parentWidget() is timer_controls
    assert window.detached_panel_windows["timer"].content is timer_panel

    window.restore_panel("timer")

    assert main_layout.indexOf(timer_panel) == 0
    assert timer_button_layout.indexOf(global_controls) >= 0


def test_main_window_can_shrink_to_control_row_when_all_visible_panels_are_detached():
    _app()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    timer = QWidget()
    guide = QWidget()
    window.panel_registry = {
        "timer": {"content": timer},
        "guide": {"content": guide},
    }
    window.detached_panel_windows = {
        "timer": QWidget(),
        "guide": QWidget(),
    }

    assert window._main_window_min_height() == window.DETACHED_ONLY_MIN_HEIGHT

    window.detached_panel_windows.pop("guide")

    assert window._main_window_min_height() == window.MIN_HEIGHT


def test_main_window_automatically_shrinks_when_all_visible_panels_are_detached():
    _app()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.resize(640, 720)
    window.panel_registry = {
        "timer": {"content": QWidget()},
        "guide": {"content": QWidget()},
    }
    window.detached_panel_windows = {
        "timer": QWidget(),
        "guide": QWidget(),
    }

    window._adjust_main_window_after_panel_change()

    assert window.width() == 640
    assert window.height() == window.DETACHED_ONLY_MIN_HEIGHT
