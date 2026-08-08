import ast
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.ui.main_window import MainWindow
from src.utils.poe_version_data import POE2


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
        trace = Mock()
        with patch(
            "src.poetore.performance.start_search_trace", return_value=trace,
        ), patch(
            "src.poetore.ui.show_poetore_window", return_value=poetore_window,
        ) as show_window:
            MainWindow.capture_poetore_item(window)
        show_window.assert_called_once_with(window, activate=False)
        poetore_window.capture_from_poe.assert_called_once_with(trace)
        self.assertEqual(
            [call.args[0] for call in trace.mark.call_args_list],
            ["hotkey_dispatched", "poetore_window_ready"],
        )

    def test_capture_release_is_forwarded_to_prepared_poetore_window(self):
        window = MainWindow.__new__(MainWindow)
        window._poetore_window = Mock()

        MainWindow.handle_hotkey(window, "poetore_capture_released")

        window._poetore_window.capture_hotkey_released.assert_called_once_with()

    def test_auto_hide_capture_uses_passive_mode(self):
        window = MainWindow.__new__(MainWindow)
        poetore_window = Mock()
        trace = Mock()
        with patch(
            "src.poetore.performance.start_search_trace", return_value=trace,
        ), patch(
            "src.poetore.ui.show_poetore_window", return_value=poetore_window,
        ):
            MainWindow.capture_poetore_item(window, auto_hide=True)

        poetore_window.capture_from_poe.assert_called_once_with(
            trace, auto_hide=True, capture_hotkey="ctrl+d",
        )

    def test_poe2_blocks_open_prepare_and_capture_before_importing_ui(self):
        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE2
        window.config = {"poe_version": POE2}

        with patch("src.poetore.ui.show_poetore_window") as show_window, patch(
            "src.poetore.ui.prepare_poetore_window"
        ) as prepare_window:
            self.assertIsNone(MainWindow.open_poetore(window))
            self.assertIsNone(MainWindow._prepare_poetore_window(window))
            self.assertIsNone(MainWindow.capture_poetore_item(window))

        show_window.assert_not_called()
        prepare_window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
