import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

try:
    from src.ui.main_window import MainWindow
except ModuleNotFoundError as exc:  # pragma: no cover - local dev without GUI deps
    MainWindow = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

from src.utils.poe_version_data import POE1, POE2


class FakePoeVersionDialog:
    calls = []

    def __init__(self, parent=None, current_version=None):
        self.selected_version = POE2
        FakePoeVersionDialog.calls.append(current_version)

    def exec(self):
        return True


@unittest.skipIf(MainWindow is None, f"GUI dependencies unavailable: {IMPORT_ERROR}")
class StartupSelectionFlowTest(unittest.TestCase):
    def setUp(self):
        FakePoeVersionDialog.calls = []

    def test_legacy_ask_poe2_config_only_shows_version_selection(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {
            "poe_version": POE2,
            "poe_version_mode": "ask",
        }

        with patch("src.ui.main_window.PoeVersionSelectionDialog", FakePoeVersionDialog), \
             patch("src.ui.main_window.ConfigManager.save_config") as save_config:
            self.assertTrue(window._ensure_poe_version_selected())

        self.assertEqual(FakePoeVersionDialog.calls, [POE2])
        self.assertEqual(window.config["poe_version"], POE2)
        save_config.assert_called_once_with(window.config)

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
            with patch("src.ui.main_window.PoeVersionSelectionDialog") as dialog:
                self.assertTrue(window._ensure_poe_version_selected())
            dialog.assert_not_called()
        finally:
            app.setProperty("startupPoeVersionSelected", previous)


if __name__ == "__main__":
    unittest.main()
