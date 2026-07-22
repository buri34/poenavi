import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

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
