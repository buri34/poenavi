import unittest
from PySide6.QtWidgets import QApplication

try:
    from src.ui.main_window import MainWindow
except ModuleNotFoundError as exc:  # pragma: no cover - local dev without GUI deps
    MainWindow = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

from src.utils.poe_version_data import POE1, POE2


@unittest.skipIf(MainWindow is None, f"GUI dependencies unavailable: {IMPORT_ERROR}")
class StartupSelectionFlowTest(unittest.TestCase):
    def test_main_window_does_not_open_a_second_version_dialog(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {
            "poe_version": POE2,
            "poe_version_mode": "ask",
        }

        self.assertTrue(window._ensure_poe_version_selected())

        self.assertEqual(window.config["poe_version"], POE2)

    def test_main_window_does_not_repeat_version_dialog_after_common_startup_selection(self):
        app = QApplication.instance() or QApplication([])
        previous = app.property("startupPoeVersionSelected")
        app.setProperty("startupPoeVersionSelected", True)
        window = MainWindow.__new__(MainWindow)
        window.config = {
            "poe_version": POE1,
            "poe_version_mode": "ask",
        }

        try:
            self.assertTrue(window._ensure_poe_version_selected())
        finally:
            app.setProperty("startupPoeVersionSelected", previous)


if __name__ == "__main__":
    unittest.main()
