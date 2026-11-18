from pathlib import Path
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from src.ui.main_window import MainWindow
from src.update.qt_controller import UpdateController
from src.update.release_client import ReleaseInfo


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


def release_info():
    return ReleaseInfo(
        "2.5.0",
        "notes",
        "https://github.com/page",
        "https://github.com/a.zip",
        "https://github.com/a.sha256",
    )


class ImmediateThread:
    def __init__(self, target):
        self.target = target

    def start(self):
        self.target()


def test_startup_gate_finishes_before_setup_when_no_update():
    window = MainWindow.__new__(MainWindow)
    window.config = {}
    window.update_controller = UpdateController(
        thread_factory=lambda target: ImmediateThread(target)
    )

    with patch("src.update.qt_controller.fetch_latest_release", return_value=None):
        assert window._run_startup_update_gate() is True


def test_show_event_state_exists_before_startup_update_gate():
    """Update dialogs may trigger showEvent before MainWindow.__init__ finishes."""
    observed = {}

    def stop_after_observation(window):
        observed["pending_map"] = window._pending_initial_map_auto_open
        observed["positioned"] = window._initial_positioned
        return False

    with patch("src.ui.main_window.ConfigManager.load_config", return_value={}), \
         patch.object(MainWindow, "_run_startup_update_gate", stop_after_observation):
        MainWindow()

    assert observed == {"pending_map": False, "positioned": False}


def test_show_event_state_exists_before_python_init_body():
    """Qt may dispatch showEvent from QMainWindow.__init__ itself."""
    window = MainWindow.__new__(MainWindow)

    assert window._pending_initial_map_auto_open is False
    assert window._initial_positioned is False


def test_show_event_is_noop_before_main_window_initialization():
    """An early Qt showEvent must not touch partially initialized UI state."""
    window = MainWindow.__new__(MainWindow)

    with patch.object(QMainWindow, "showEvent"):
        window.showEvent(Mock())

    assert window._main_window_initialized is False


def test_show_event_startup_reset_ignores_saved_geometry():
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window._main_window_initialized = True
    window._initial_positioned = False
    window._pending_initial_map_auto_open = False
    window.config = {
        "reset_window_position_on_startup": True,
        "window_geometry": {
            "x": 5000,
            "y": 3000,
            "width": 900,
            "height": 700,
        },
    }
    window._position_right_edge = Mock()

    with patch.object(QMainWindow, "showEvent"):
        window.showEvent(Mock())

    window._position_right_edge.assert_called_once_with(
        reset_position_only=True,
        saved_geometry=window.config["window_geometry"],
    )


def test_startup_reset_preserves_saved_size_at_target_screen_top_right():
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.setGeometry(0, 0, 420, 1200)
    window._main_window_min_height = Mock(return_value=120)
    screen = Mock()
    screen.availableGeometry.return_value = QRect(1920, 0, 2560, 1440)
    window._target_display_screen = Mock(return_value=screen)

    window._position_right_edge(
        reset_position_only=True,
        saved_geometry={
            "x": 5000,
            "y": 3000,
            "width": 635,
            "height": 867,
        },
    )

    assert window.geometry() == QRect(3845, 0, 635, 867)


def test_main_window_drag_prefers_qt_system_move():
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.window_locked = False
    window.drag_position = QPoint(1, 1)
    window.resize_edge = None
    window.resize_start_geo = None
    window.resize_start_pos = None
    window._detect_edge = Mock(return_value=None)
    handle = Mock()
    handle.startSystemMove.return_value = True
    event = Mock()
    event.button.return_value = Qt.LeftButton
    event.position.return_value = QPointF(10, 10)
    event.globalPosition.return_value = QPointF(100, 100)

    with patch.object(MainWindow, "windowHandle", return_value=handle):
        window.mousePressEvent(event)

    handle.startSystemMove.assert_called_once_with()
    assert window.drag_position is None
    event.accept.assert_called_once_with()


def test_main_window_drag_falls_back_when_system_move_is_unavailable():
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.setGeometry(20, 30, 400, 600)
    window.window_locked = False
    window.drag_position = None
    window.resize_edge = None
    window.resize_start_geo = None
    window.resize_start_pos = None
    window._detect_edge = Mock(return_value=None)
    handle = Mock()
    handle.startSystemMove.return_value = False
    event = Mock()
    event.button.return_value = Qt.LeftButton
    event.position.return_value = QPointF(10, 10)
    event.globalPosition.return_value = QPointF(100, 100)

    with patch.object(MainWindow, "windowHandle", return_value=handle):
        window.mousePressEvent(event)

    assert window.drag_position == QPoint(80, 70)


def test_startup_check_skips_already_notified_release():
    window = MainWindow.__new__(MainWindow)
    window.config = {"notified_update_version": "2.5.0"}
    window._show_update_available = Mock()

    window._on_update_check_finished(release_info(), False)

    window._show_update_available.assert_not_called()


def test_manual_check_shows_same_release_again():
    window = MainWindow.__new__(MainWindow)
    window.config = {"notified_update_version": "2.5.0"}
    window._show_update_available = Mock()

    window._on_update_check_finished(release_info(), True)

    window._show_update_available.assert_called_once_with(release_info())


def test_manual_check_without_release_reports_latest():
    window = MainWindow.__new__(MainWindow)
    with patch("src.ui.main_window.show_update_message") as show_message:
        window._on_update_check_finished(None, True)
    show_message.assert_called_once_with(
        window,
        QMessageBox.Information,
        "アップデート",
        "最新バージョンです。",
    )


def test_declining_apply_keeps_verified_download():
    window = MainWindow.__new__(MainWindow)
    window._update_progress_dialog = None
    window.update_controller = Mock()

    with patch(
        "src.ui.main_window.show_update_message",
        return_value=QMessageBox.No,
    ):
        window._on_update_download_ready(Path("PoENavi.zip"), release_info())

    window.update_controller.discard_download.assert_not_called()
    window.update_controller.launch_updater.assert_not_called()


def test_start_update_reuses_verified_download():
    window = MainWindow.__new__(MainWindow)
    window.update_controller = Mock()
    window._on_update_download_ready = Mock()
    archive = Path("cached-PoENavi.zip")
    window.update_controller.ready_archive.return_value = archive
    release = release_info()

    window._start_update_download(release)

    window._on_update_download_ready.assert_called_once_with(archive, release)
    window.update_controller.download.assert_not_called()


def test_close_before_initial_position_does_not_overwrite_saved_geometry():
    """Startup update exit must preserve the user's saved window geometry."""
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window._main_window_initialized = False
    window._initial_positioned = False
    window.setGeometry(0, 0, 420, 1200)

    with patch("src.ui.main_window.ConfigManager.load_config") as load_config, \
         patch("src.ui.main_window.ConfigManager.save_config") as save_config, \
         patch.object(QMainWindow, "closeEvent"):
        window.closeEvent(Mock())

    load_config.assert_not_called()
    save_config.assert_not_called()


def test_close_after_initial_position_saves_current_geometry():
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window._main_window_initialized = True
    window._initial_positioned = True
    window.setGeometry(12, 34, 800, 900)
    config = {"window_geometry": {"x": 1, "y": 2, "width": 3, "height": 4}}

    with patch("src.ui.main_window.ConfigManager.load_config", return_value=config), \
         patch("src.ui.main_window.ConfigManager.save_config") as save_config, \
         patch.object(QMainWindow, "closeEvent"):
        window.closeEvent(Mock())

    assert config["window_geometry"] == {
        "x": 12,
        "y": 34,
        "width": 800,
        "height": 900,
    }
    save_config.assert_called_once_with(config)
