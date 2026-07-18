import ast
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.ui.main_window import MainWindow


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
        poetore_window = Mock()
        with patch("src.poetore.ui.show_poetore_window", return_value=poetore_window) as show_window:
            MainWindow.capture_poetore_item(window)
        show_window.assert_called_once_with(window, activate=False)
        poetore_window.capture_from_poe.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
