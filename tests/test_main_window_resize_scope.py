import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QSizePolicy, QVBoxLayout, QWidget

from src.ui.main_window import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


def _window():
    _app()
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.EDGE_MARGIN = 14
    window.setGeometry(QRect(500, 300, 400, 600))
    return window


def test_resize_scope_accepts_only_main_window_and_its_children():
    window = _window()
    child = QWidget(window)
    separate_tool = QWidget()

    assert window._is_main_window_widget(window)
    assert window._is_main_window_widget(child)
    assert not window._is_main_window_widget(separate_tool)
    assert not window._is_main_window_widget(object())

    separate_tool.deleteLater()
    window.deleteLater()


def test_edge_detection_rejects_points_outside_main_window_even_when_axis_matches():
    window = _window()
    geo = window.frameGeometry()

    assert "top" in window._global_detect_edge(QPoint(geo.center().x(), geo.top()))
    assert window._global_detect_edge(QPoint(geo.left() - 300, geo.top())) is None
    assert window._global_detect_edge(QPoint(geo.left(), geo.top() - 300)) is None

    window.deleteLater()


def test_rebuild_lap_ui_keeps_segment_summary_inside_collapsible_lap_content():
    _app()
    lap_content = QWidget()
    window = MainWindow.__new__(MainWindow)
    window.lap_content_layout = QVBoxLayout(lap_content)
    window.lap_labels = ["Act 1"]
    window.segment_summary_label = QLabel("区間: エリア移動を待機中")

    window._rebuild_lap_ui()

    assert window.lap_content_layout.indexOf(window.segment_summary_label) == window.lap_content_layout.count() - 1
    lap_content.deleteLater()


def test_segment_summary_reserves_two_lines_and_cannot_shrink_vertically():
    _app()
    window = MainWindow.__new__(MainWindow)
    window.segment_summary_label = QLabel()

    window._configure_segment_summary_label()

    expected_height = window.segment_summary_label.fontMetrics().lineSpacing() * 2 + 4
    assert window.segment_summary_label.minimumHeight() == expected_height
    assert window.segment_summary_label.sizePolicy().verticalPolicy() == QSizePolicy.Fixed
    window.segment_summary_label.deleteLater()


def test_expanded_attached_timer_uses_taller_main_window_minimum():
    window = MainWindow.__new__(MainWindow)
    window.timer_expanded = True
    window.lap_expanded = True
    window._are_all_visible_panels_outside_main = lambda: False
    window._is_panel_detached = lambda panel_id: False

    assert window._main_window_min_height() == window.EXPANDED_TIMER_MIN_HEIGHT


def test_collapsed_or_detached_timer_keeps_normal_main_window_minimum():
    window = MainWindow.__new__(MainWindow)
    window.timer_expanded = True
    window.lap_expanded = False
    window._are_all_visible_panels_outside_main = lambda: False
    window._is_panel_detached = lambda panel_id: False
    assert window._main_window_min_height() == window.MIN_HEIGHT

    window.lap_expanded = True
    window._is_panel_detached = lambda panel_id: panel_id == "timer"
    assert window._main_window_min_height() == window.MIN_HEIGHT
