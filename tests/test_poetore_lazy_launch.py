import ast
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.ui.main_window import MainWindow
from src.utils.poe_version_data import POE1, POE2


class PoetoreLazyLaunchTest(unittest.TestCase):
    def test_main_window_module_does_not_import_poetore_ui_at_startup(self):
        source = Path("src/ui/main_window.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_imports = [
            node for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
            and "poetore" in ast.unparse(node)
        ]
        self.assertEqual(top_level_imports, [])

    def test_open_poetore_delegates_to_lazy_entrypoint(self):
        window = MainWindow.__new__(MainWindow)
        with patch("src.poetore.ui.show_poetore_window") as show_window:
            MainWindow.open_poetore(window)
        show_window.assert_called_once_with(window)

    def test_capture_poetore_item_starts_capture(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {"poe_version": POE1}
        window.poe_version = POE1
        poetore_window = Mock()
        with patch("src.poetore.ui.show_poetore_window", return_value=poetore_window) as show_window:
            MainWindow.capture_poetore_item(window)
        show_window.assert_called_once_with(window, activate=False)
        poetore_window.capture_from_poe.assert_called_once_with()

    def test_poetore_capture_hotkey_is_ignored_in_poe2_mode(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {"poe_version": POE2}
        window.poe_version = POE2
        window.capture_poetore_item = Mock()

        MainWindow.handle_hotkey(window, "poetore_capture")

        window.capture_poetore_item.assert_not_called()

    def test_poetore_availability_refresh_hides_and_closes_it_after_poe2_switch(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {"poe_version": POE1}
        window.poe_version = POE1
        window.poetore_btn = Mock()
        window._poetore_window = Mock()

        MainWindow._refresh_poetore_availability(window)
        window.poetore_btn.setVisible.assert_called_once_with(True)
        window._poetore_window.close.assert_not_called()

        window.config["poe_version"] = POE2
        window.poe_version = POE2
        MainWindow._refresh_poetore_availability(window)

        window.poetore_btn.setVisible.assert_called_with(False)
        window._poetore_window.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
