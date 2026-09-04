import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from src.ui.main_window import MainWindow, MiniNaviOverlay
from src.utils.config_manager import ConfigManager


class MiniNaviStandaloneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.save_config_patch = patch.object(ConfigManager, "save_config")
        cls.save_config_patch.start()
        cls.click_through_patch = patch.object(MiniNaviOverlay, "_apply_click_through")
        cls.click_through_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.click_through_patch.stop()
        cls.save_config_patch.stop()

    def _dispose_overlay(self, overlay, main):
        overlay.lock_button_window.close()
        overlay.close()
        main.close()
        overlay.lock_button_window.deleteLater()
        overlay.deleteLater()
        main.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def test_poennavi_tray_icon_uses_app_icon_asset(self):
        icon_path = Path(MainWindow._app_icon_path())

        self.assertEqual(icon_path.parts[-3:], ("assets", "app", "icon.ico"))
        self.assertTrue(icon_path.is_file())

    def test_overlay_is_top_level_but_keeps_logical_main_window(self):
        main = QWidget()
        main.config = {"mini_guide_overlay": {}}
        overlay = MiniNaviOverlay(main)
        try:
            self.assertIsNone(overlay.parent())
            self.assertIs(overlay.main_window, main)
        finally:
            self._dispose_overlay(overlay, main)

    def test_overlay_is_always_an_obs_capture_window_while_disabled(self):
        main = QWidget()
        main.config = {"mini_guide_overlay": {"enabled": False}}
        overlay = MiniNaviOverlay(main)
        try:
            self.app.processEvents()

            self.assertTrue(overlay.isVisible())
            self.assertTrue(overlay.windowFlags() & Qt.Window)
            self.assertTrue(overlay.windowFlags() & Qt.FramelessWindowHint)
            self.assertEqual(overlay.windowTitle(), MiniNaviOverlay.OBS_WINDOW_TITLE)
            self.assertEqual(overlay.size().width(), MiniNaviOverlay.OBS_WAITING_SIZE)
            self.assertEqual(overlay.size().height(), MiniNaviOverlay.OBS_WAITING_SIZE)
            self.assertAlmostEqual(
                overlay.windowOpacity(), MiniNaviOverlay.OBS_WAITING_OPACITY, delta=1 / 255
            )
            self.assertFalse(overlay.outer.isVisible())
            self.assertFalse(overlay.lock_button_window.isVisible())
        finally:
            self._dispose_overlay(overlay, main)

    def test_obs_window_keeps_native_id_when_content_expands_and_collapses(self):
        main = QWidget()
        main.config = {
            "mini_guide_overlay": {
                "enabled": True,
                "position": {"x": 80, "y": 160},
                "width": 640,
                "height": 120,
            }
        }
        overlay = MiniNaviOverlay(main)
        try:
            self.app.processEvents()
            waiting_id = int(overlay.winId())

            overlay.update_content({"text": "次のエリアへ進む", "direction": "e"})
            self.app.processEvents()

            self.assertEqual(int(overlay.winId()), waiting_id)
            self.assertFalse(overlay._obs_waiting)
            self.assertTrue(overlay.outer.isVisible())
            self.assertGreaterEqual(overlay.width(), 220)

            main.config["mini_guide_overlay"]["enabled"] = False
            overlay.update_content({"text": "次のエリアへ進む", "direction": "e"})
            self.app.processEvents()

            self.assertEqual(int(overlay.winId()), waiting_id)
            self.assertTrue(overlay._obs_waiting)
            self.assertEqual(overlay.width(), MiniNaviOverlay.OBS_WAITING_SIZE)
        finally:
            self._dispose_overlay(overlay, main)

    def test_obs_content_stays_hidden_until_expanded_geometry_is_complete(self):
        main = QWidget()
        main.config = {
            "mini_guide_overlay": {
                "enabled": True,
                "width": 750,
                "height": 118,
            }
        }
        overlay = MiniNaviOverlay(main)
        try:
            self.assertFalse(overlay.outer.isVisible())

            overlay.expand_from_obs()

            self.assertFalse(overlay.outer.isVisible())
            overlay.apply_settings(refresh_window_flags=False)
            self.assertEqual((overlay.width(), overlay.height()), (750, 118))
            self.assertFalse(overlay.outer.isVisible())
        finally:
            self._dispose_overlay(overlay, main)

    def test_obs_waiting_state_does_not_overwrite_saved_user_geometry(self):
        saved = {
            "enabled": False,
            "position": {"x": 123, "y": 234},
            "width": 700,
            "height": 140,
        }
        main = QWidget()
        main.config = {"mini_guide_overlay": dict(saved)}
        overlay = MiniNaviOverlay(main)
        try:
            overlay.close()
            self.app.processEvents()

            self.assertEqual(main.config["mini_guide_overlay"], saved)
        finally:
            self._dispose_overlay(overlay, main)

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
            overlay.update_content({"text": "次のエリアへ進む", "direction": "e"})
            self.assertEqual(overlay.width(), 390)
            overlay.setGeometry(40, 50, 420, 140)
            overlay._remember_current_geometry_to_config()

            self.assertEqual(main.config["mini_guide_overlay"]["width"], 800)
            self.assertEqual(main.config["mini_guide_overlay"]["height"], 130)
            self.assertEqual(main.config["mini_guide_overlay"]["compact_geometry"]["width"], 420)
        finally:
            self._dispose_overlay(overlay, main)

    def test_compact_mode_uses_bottom_center_geometry_when_unsaved(self):
        main = QWidget()
        main.config = {"mini_guide_overlay": {"enabled": True, "display_mode": "compact"}}
        overlay = MiniNaviOverlay(main)
        try:
            available = QApplication.primaryScreen().availableGeometry()
            overlay.update_content({"text": "次のエリアへ進む", "direction": "e"})

            self.assertEqual(MiniNaviOverlay.COMPACT_DEFAULT_WIDTH, 600)
            self.assertEqual(MiniNaviOverlay.COMPACT_DEFAULT_HEIGHT, 110)
            self.assertEqual(overlay.width(), min(MiniNaviOverlay.COMPACT_DEFAULT_WIDTH, available.width()))
            self.assertGreaterEqual(overlay.height(), overlay.minimumHeight())
            self.assertLessEqual(overlay.height(), min(MiniNaviOverlay.COMPACT_DEFAULT_HEIGHT, available.height()))
            self.assertEqual(overlay.geometry().center().x(), available.center().x())
            self.assertLessEqual(overlay.geometry().bottom(), available.bottom())
            self.assertGreaterEqual(overlay.geometry().top(), available.top())
        finally:
            self._dispose_overlay(overlay, main)

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
            self._dispose_overlay(overlay, main)

    def test_compact_mode_hides_experience_level_guide(self):
        main = QWidget()
        main.config = {"mini_guide_overlay": {"enabled": True, "display_mode": "compact"}}
        overlay = MiniNaviOverlay(main)
        try:
            overlay.update_content(
                {"text": "次のエリアへ進む", "direction": "right"},
                {"player_level": 4, "enemy_level": 5, "status": "🟢 最適"},
            )

            self.assertFalse(overlay.exp_label.isVisible())
        finally:
            self._dispose_overlay(overlay, main)

    def test_minimize_hides_only_main_when_mini_navi_is_visible(self):
        window = MainWindow.__new__(MainWindow)
        window._hidden_for_mini_navi = False
        window._tray_notification_shown = False
        window.hide = Mock()
        window.showMinimized = Mock()
        window.tray_icon = Mock()
        window._is_mini_navi_available = Mock(return_value=True)
        window.mini_navi_overlay = Mock()
        window.mini_navi_overlay.isVisible.return_value = True

        with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True):
            MainWindow.minimize_main_window(window)

        self.assertTrue(window._hidden_for_mini_navi)
        window.hide.assert_called_once_with()
        window.showMinimized.assert_not_called()
        window.tray_icon.show.assert_called_once_with()
        window.tray_icon.showMessage.assert_called_once()
        window.mini_navi_overlay.show.assert_called_once_with()
        window.mini_navi_overlay._sync_lock_button.assert_called_once_with()

    def test_minimize_hides_to_tray_without_visible_mini_navi(self):
        window = MainWindow.__new__(MainWindow)
        window._tray_notification_shown = True
        window.hide = Mock()
        window.showMinimized = Mock()
        window.tray_icon = Mock()
        window._is_mini_navi_available = Mock(return_value=True)
        window.mini_navi_overlay = Mock()
        window.mini_navi_overlay.isVisible.return_value = False

        with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True):
            MainWindow.minimize_main_window(window)

        window.hide.assert_called_once_with()
        window.showMinimized.assert_not_called()
        window.tray_icon.show.assert_called_once_with()
        window.tray_icon.showMessage.assert_not_called()

    def test_minimize_uses_normal_minimize_when_tray_is_unavailable(self):
        window = Mock()
        with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=False):
            MainWindow.minimize_main_window(window)

        window.showMinimized.assert_called_once_with()
        window.hide.assert_not_called()

    def test_tray_activation_restores_hidden_main_window(self):
        window = Mock()
        window._hidden_for_mini_navi = True

        MainWindow.restore_from_tray(window)

        window.restore_from_mini_navi.assert_called_once_with()
        window.showNormal.assert_not_called()
        window.tray_icon.hide.assert_called_once_with()

    def test_tray_activation_restores_normal_main_window(self):
        window = Mock()
        window._hidden_for_mini_navi = False

        MainWindow.restore_from_tray(window)

        window.showNormal.assert_called_once_with()
        window.raise_.assert_called_once_with()
        window.activateWindow.assert_called_once_with()
        window.tray_icon.hide.assert_called_once_with()

    def test_tray_click_and_double_click_restore_main_window(self):
        window = Mock()

        MainWindow._handle_tray_activation(window, QSystemTrayIcon.Trigger)
        MainWindow._handle_tray_activation(window, QSystemTrayIcon.DoubleClick)
        MainWindow._handle_tray_activation(window, QSystemTrayIcon.Context)

        self.assertEqual(window.restore_from_tray.call_count, 2)

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

    def test_overlay_has_no_gem_shop_purchase_controls(self):
        main = QWidget()
        main.config = {
            "mini_guide_overlay": {
                "enabled": True,
                "locked": True,
                "click_through_when_locked": True,
            }
        }
        overlay = MiniNaviOverlay(main)
        try:
            overlay.show()
            self.app.processEvents()

            self.assertFalse(hasattr(overlay, "gem_shop_prompt_label"))
            self.assertFalse(hasattr(overlay.lock_button_window, "gem_shop_copy_button"))
        finally:
            self._dispose_overlay(overlay, main)


if __name__ == "__main__":
    unittest.main()
