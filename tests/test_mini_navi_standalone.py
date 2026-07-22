import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from src.ui.main_window import MainWindow, MiniNaviOverlay
from src.utils.config_manager import ConfigManager


class MiniNaviStandaloneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.save_config_patch = patch.object(ConfigManager, "save_config")
        cls.save_config_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.save_config_patch.stop()

    def test_overlay_is_top_level_but_keeps_logical_main_window(self):
        main = QWidget()
        main.config = {"mini_guide_overlay": {}}
        overlay = MiniNaviOverlay(main)
        try:
            self.assertIsNone(overlay.parent())
            self.assertIs(overlay.main_window, main)
        finally:
            overlay.close()
            main.close()

    def test_compact_mode_uses_saved_geometry_without_overwriting_standard_geometry(self):
        main = QWidget()
        main.config = {
            "mini_guide_overlay": {
                "enabled": True,
                "display_mode": "compact",
                "width": 800,
                "height": 130,
                "compact_geometry": {"position": {"x": 20, "y": 30}, "width": 390, "height": 100},
            }
        }
        overlay = MiniNaviOverlay(main)
        try:
            self.assertEqual(overlay.width(), 390)
            overlay.setGeometry(40, 50, 420, 140)
            overlay._remember_current_geometry_to_config()

            self.assertEqual(main.config["mini_guide_overlay"]["width"], 800)
            self.assertEqual(main.config["mini_guide_overlay"]["height"], 130)
            self.assertEqual(main.config["mini_guide_overlay"]["compact_geometry"]["width"], 420)
        finally:
            overlay.close()
            main.close()

    def test_compact_mode_uses_bottom_center_geometry_when_unsaved(self):
        main = QWidget()
        main.config = {"mini_guide_overlay": {"enabled": True, "display_mode": "compact"}}
        overlay = MiniNaviOverlay(main)
        try:
            available = QApplication.primaryScreen().availableGeometry()

            self.assertEqual(overlay.width(), MiniNaviOverlay.COMPACT_DEFAULT_WIDTH)
            self.assertEqual(overlay.geometry().center().x(), available.center().x())
            self.assertEqual(overlay.geometry().bottom(), available.bottom())
        finally:
            overlay.close()
            main.close()

    def test_compact_mode_expands_height_for_long_japanese_text(self):
        main = QWidget()
        main.config = {"mini_guide_overlay": {"enabled": True, "display_mode": "compact"}}
        overlay = MiniNaviOverlay(main)
        try:
            overlay.update_content({"text": "長い日本語案内です。" * 40, "direction": "right"})
            self.app.processEvents()

            self.assertGreater(overlay.height(), MiniNaviOverlay.COMPACT_DEFAULT_HEIGHT)
            self.assertLessEqual(overlay.text_label.width(), overlay.outer.layout().contentsRect().width())
        finally:
            overlay.close()
            main.close()

    def test_minimize_hides_only_main_when_mini_navi_is_visible(self):
        window = MainWindow.__new__(MainWindow)
        window._hidden_for_mini_navi = False
        window.hide = Mock()
        window.showMinimized = Mock()
        window._is_mini_navi_available = Mock(return_value=True)
        window.mini_navi_overlay = Mock()
        window.mini_navi_overlay.isVisible.return_value = True

        MainWindow.minimize_main_window(window)

        self.assertTrue(window._hidden_for_mini_navi)
        window.hide.assert_called_once_with()
        window.showMinimized.assert_not_called()
        window.mini_navi_overlay.show.assert_called_once_with()
        window.mini_navi_overlay._sync_lock_button.assert_called_once_with()

    def test_minimize_uses_normal_minimize_without_visible_mini_navi(self):
        window = MainWindow.__new__(MainWindow)
        window.showMinimized = Mock()
        window._is_mini_navi_available = Mock(return_value=True)
        window.mini_navi_overlay = Mock()
        window.mini_navi_overlay.isVisible.return_value = False

        MainWindow.minimize_main_window(window)

        window.showMinimized.assert_called_once_with()

    def test_main_button_restores_hidden_main_window(self):
        main = Mock()
        overlay = MiniNaviOverlay.__new__(MiniNaviOverlay)
        overlay.main_window = main
        overlay.is_main_window_hidden = Mock(return_value=True)

        MiniNaviOverlay.toggle_main_window(overlay)

        main.restore_from_mini_navi.assert_called_once_with()
        main.hide_for_mini_navi.assert_not_called()

    def test_main_button_hides_visible_main_window(self):
        main = Mock()
        overlay = MiniNaviOverlay.__new__(MiniNaviOverlay)
        overlay.main_window = main
        overlay.is_main_window_hidden = Mock(return_value=False)

        MiniNaviOverlay.toggle_main_window(overlay)

        main.hide_for_mini_navi.assert_called_once_with()
        main.restore_from_mini_navi.assert_not_called()


if __name__ == "__main__":
    unittest.main()
