import unittest
from unittest.mock import Mock, patch

try:
    from src.ui.main_window import MainWindow, MiniNaviOverlay
except ModuleNotFoundError as exc:  # pragma: no cover - local dev without GUI deps
    MainWindow = None
    MiniNaviOverlay = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

from src.utils.poe_version_data import POE1, POE2


@unittest.skipIf(MainWindow is None, f"GUI dependencies unavailable: {IMPORT_ERROR}")
class GuideDetailLevelToggleTest(unittest.TestCase):
    def make_window(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {"guide_detail_level": "beginner"}
        window.poe_version = POE2
        window.current_zone = "The Grelwood"
        window.zone_visit_counts = {"poe2_act1_area04": 2}
        window.guide_expanded = True
        window.guide_detail_level_toggle_btn = Mock()
        window._get_zone_id = Mock(return_value="poe2_act1_area04")
        window._update_guide_and_map = Mock()
        return window

    def test_toggle_guide_detail_level_saves_and_refreshes_current_guide(self):
        window = self.make_window()

        with patch("src.ui.main_window.ConfigManager.save_config") as save_config:
            window.toggle_guide_detail_level()

        self.assertEqual(window.config["guide_detail_level"], "intermediate")
        self.assertTrue(window.config["guide_detail_level_selected"])
        save_config.assert_called_once_with(window.config)
        window.guide_detail_level_toggle_btn.setText.assert_called_with("要点版ガイド")
        window._update_guide_and_map.assert_called_once_with(
            "The Grelwood", "poe2_act1_area04", 2
        )

    def test_mini_navi_toggle_is_hidden_in_poe2_mode(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {"mini_guide_overlay": {"enabled": False}}
        window.poe_version = POE2
        window.guide_expanded = True
        window.mini_navi_toggle_btn = Mock()

        window._refresh_mini_navi_toggle()

        window.mini_navi_toggle_btn.setText.assert_called_with("みになび OFF")
        window.mini_navi_toggle_btn.setVisible.assert_called_once_with(False)

    def test_mini_navi_toggle_is_visible_in_poe1_when_guide_expanded(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {"mini_guide_overlay": {"enabled": False}}
        window.poe_version = POE1
        window.guide_expanded = True
        window.mini_navi_toggle_btn = Mock()

        window._refresh_mini_navi_toggle()

        window.mini_navi_toggle_btn.setVisible.assert_called_once_with(True)

    def test_mini_navi_toggle_text_only_reflects_enabled_state(self):
        window = MainWindow.__new__(MainWindow)

        for locked in (True, False):
            window.config = {"mini_guide_overlay": {"enabled": True, "locked": locked}}
            self.assertEqual(window._mini_navi_toggle_text(), "みになび ON")

            window.config["mini_guide_overlay"]["enabled"] = False
            self.assertEqual(window._mini_navi_toggle_text(), "みになび OFF")

    def test_mini_navi_main_toggle_does_not_change_lock_state(self):
        for locked in (True, False):
            window = MainWindow.__new__(MainWindow)
            window.config = {"mini_guide_overlay": {"enabled": True, "locked": locked}}
            window.current_zone = None
            window.mini_navi_overlay = Mock()
            window._is_mini_navi_available = Mock(return_value=True)
            window._refresh_mini_navi_toggle = Mock()

            with patch("src.ui.main_window.ConfigManager.save_config"):
                window.toggle_mini_navi_overlay()

            self.assertFalse(window.config["mini_guide_overlay"]["enabled"])
            self.assertEqual(window.config["mini_guide_overlay"]["locked"], locked)

    def test_mini_navi_remembers_current_geometry_before_lock_toggle(self):
        class FakeOverlay:
            def __init__(self):
                self.parent_config = {"mini_guide_overlay": {"width": 360, "height": 100}}

            def _mutable_config(self):
                return self.parent_config["mini_guide_overlay"]

            def x(self):
                return 123

            def y(self):
                return 234

            def width(self):
                return 456

            def height(self):
                return 178

        overlay = FakeOverlay()

        MiniNaviOverlay._remember_current_geometry_to_config(overlay)

        self.assertEqual(
            overlay.parent_config["mini_guide_overlay"],
            {"width": 456, "height": 178, "position": {"x": 123, "y": 234}},
        )

    def test_mini_navi_waiting_message_uses_muted_content(self):
        overlay = MiniNaviOverlay.__new__(MiniNaviOverlay)
        overlay.update_content = Mock()

        overlay.show_waiting_for_area()

        overlay.update_content.assert_called_once_with(
            {
                "text": "エリアに入場すると攻略ガイドが表示されます",
                "direction": "none",
            },
            muted=True,
        )

    def test_mini_navi_town_keeps_last_area_content(self):
        overlay = MiniNaviOverlay.__new__(MiniNaviOverlay)
        overlay._current_content = {"text": "前エリアのガイド", "direction": "ne"}
        overlay._current_exp_guide = {"player_level": 10, "enemy_level": 12}
        overlay._current_zone_id = "act3_area1"
        overlay._current_has_area_note = True
        overlay._muted_content = False
        overlay.update_content = Mock()
        overlay.show_waiting_for_area = Mock()

        overlay.show_last_content_or_waiting()

        overlay.update_content.assert_called_once_with(
            {"text": "前エリアのガイド", "direction": "ne"},
            {"player_level": 10, "enemy_level": 12},
            muted=False,
            zone_id="act3_area1",
            has_area_note=True,
        )
        overlay.show_waiting_for_area.assert_not_called()

    def test_mini_navi_town_shows_waiting_message_without_area_history(self):
        overlay = MiniNaviOverlay.__new__(MiniNaviOverlay)
        overlay._current_content = None
        overlay.show_waiting_for_area = Mock()

        overlay.show_last_content_or_waiting()

        overlay.show_waiting_for_area.assert_called_once_with()

    def test_enabling_mini_navi_in_town_shows_waiting_message(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {"mini_guide_overlay": {"enabled": False, "locked": True}}
        window.current_zone = "ライオンアイの見張り場"
        window.mini_navi_overlay = Mock()
        window._is_mini_navi_available = Mock(return_value=True)
        window._is_town_zone = Mock(return_value=True)
        window._refresh_mini_navi_toggle = Mock()

        with patch("src.ui.main_window.ConfigManager.save_config") as save_config:
            window.toggle_mini_navi_overlay()

        self.assertTrue(window.config["mini_guide_overlay"]["enabled"])
        save_config.assert_called_once_with(window.config)
        window.mini_navi_overlay.show_last_content_or_waiting.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
