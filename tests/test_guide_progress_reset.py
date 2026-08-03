import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QTabWidget

from src.ui.main_window import MainWindow
from src.ui.settings_dialog import SettingsDialog


class GuideProgressResetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_other_tab_explains_automatic_detection_and_runs_confirmed_reset(self):
        callback = Mock()
        dialog = SettingsDialog(
            current_config={},
            guide_progress_reset_callback=callback,
        )
        tabs = dialog.findChild(QTabWidget)
        self.assertEqual(tabs.tabText(tabs.count() - 2), "その他")

        description = dialog.findChild(QLabel, "guideProgressResetDescription")
        self.assertIn("通常、自動で検知されるため操作は不要", description.text())
        self.assertIn("タイマーの記録や設定は変更されません", description.text())

        button = dialog.findChild(QPushButton, "guideProgressResetButton")
        self.assertEqual(button.text(), "ガイド進行を初期状態に戻す")
        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.Yes),
            patch.object(QMessageBox, "information") as information,
        ):
            button.click()

        callback.assert_called_once_with()
        information.assert_called_once()

    def test_manual_reset_clears_guide_state_without_touching_timer(self):
        window = MainWindow.__new__(MainWindow)
        window.clear_progress_flags = Mock()
        window.visit_override = 3
        window._update_visit_btn = Mock()
        window._in_act10 = True
        window._set_part2 = Mock()
        window.current_zone = None
        window.accumulated_time = 123.4
        window.lap_times = [10.0, 20.0]

        MainWindow._reset_guide_progress_from_settings(window)

        window.clear_progress_flags.assert_called_once_with()
        self.assertIsNone(window.visit_override)
        self.assertFalse(window._in_act10)
        window._set_part2.assert_called_once_with(False)
        self.assertEqual(window.accumulated_time, 123.4)
        self.assertEqual(window.lap_times, [10.0, 20.0])


if __name__ == "__main__":
    unittest.main()
