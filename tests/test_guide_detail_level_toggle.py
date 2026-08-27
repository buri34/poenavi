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
    def test_mini_navi_toggle_is_visible_in_poe2_when_guide_expanded(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {"mini_guide_overlay": {"enabled": False}}
        window.poe_version = POE2
        window.guide_expanded = True
        window.mini_navi_toggle_btn = Mock()

        window._refresh_mini_navi_toggle()

        window.mini_navi_toggle_btn.setText.assert_called_with("みになびをON")
        window.mini_navi_toggle_btn.setVisible.assert_called_once_with(True)

    def test_mini_navi_toggle_is_visible_in_poe1_when_guide_expanded(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {"mini_guide_overlay": {"enabled": False}}
        window.poe_version = POE1
        window.guide_expanded = True
        window.mini_navi_toggle_btn = Mock()

        window._refresh_mini_navi_toggle()

        window.mini_navi_toggle_btn.setText.assert_called_with("みになびをON")
        window.mini_navi_toggle_btn.setVisible.assert_called_once_with(True)

    def test_switching_to_poe2_keeps_mini_navi_and_recreates_old_poe1_poetore(self):
        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE2
        window.config = {"poe_version": POE2}
        window.mini_navi_overlay = Mock()
        window._poetore_window = Mock()
        poetore_window = window._poetore_window
        poetore_window.poe_version = POE1

        window._enforce_feature_support()

        window.mini_navi_overlay.hide.assert_not_called()
        poetore_window.close.assert_called_once_with()
        self.assertIsNone(window._poetore_window)

    def test_poe2_poetore_stays_open_when_version_matches(self):
        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE2
        window.config = {"poe_version": POE2}
        window.mini_navi_overlay = Mock()
        window._poetore_window = Mock()
        window._poetore_window.poe_version = POE2

        window._enforce_feature_support()

        window._poetore_window.close.assert_not_called()

    def test_poe2_guide_updates_mini_navi_content(self):
        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE2
        window.config = {
            "mini_guide_overlay": {"enabled": True, "display_mode": "standard"},
        }
        window.guide_data = {
            "poe2_act1_area04": {
                "objective": "詳細版本文",
                "summary": "旧要点版本文",
                "mini_navi": {"text": "PoE2みになび本文"},
            }
        }
        window.progress_flags = set()
        window.visit_override = None
        window.zone_data = {}
        window.part2_mode = False
        window.guide_font_size = 18
        window.player_level = 1
        window.monster_levels = {}
        window._restoring = False
        window.guide_text_label = Mock()
        window.mini_navi_overlay = Mock()
        window.map_thumbnail = Mock()
        window._current_area_note = ""
        window._update_area_note = Mock()
        window._update_poelab_link_visibility = Mock()

        window._update_guide_and_map(
            "グレルウッド", "poe2_act1_area04", 1, exp_level=None
        )

        rendered_html = window.guide_text_label.setText.call_args.args[0]
        self.assertIn("詳細版本文", rendered_html)
        self.assertNotIn("旧要点版本文", rendered_html)
        window.mini_navi_overlay.update_content.assert_called_once_with(
            {"text": "PoE2みになび本文", "direction": "none"},
            None,
            zone_id="poe2_act1_area04",
            has_area_note=False,
        )

    def test_poe2_actual_entry_reads_voice_text_once(self):
        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE2
        window.config = {"voicevox": {"enabled": True}}
        window.guide_data = {
            "poe2_act4_area16": {
                "objective": "表示本文",
                "mini_navi": {"text": "表示用", "voice_text": "入場時の案内"},
            }
        }
        window.progress_flags = set()
        window.visit_override = None
        window.zone_data = {}
        window.part2_mode = False
        window.guide_font_size = 18
        window.player_level = 1
        window._restoring = False
        window.guide_text_label = Mock()
        window.map_thumbnail = Mock()
        window._update_area_note = Mock()
        window._update_poelab_link_visibility = Mock()
        window._speak_poe2_guide = Mock()

        window._update_guide_and_map("部族の中心", "poe2_act4_area16", 1, zone_changed=True)
        window._speak_poe2_guide.assert_called_once()
        window._speak_poe2_guide.reset_mock()
        window._update_guide_and_map("部族の中心", "poe2_act4_area16", 1)
        window._speak_poe2_guide.assert_not_called()

    def test_progress_flag_reads_only_when_selected_voice_text_changes(self):
        window = MainWindow.__new__(MainWindow)
        window.current_zone = "部族の中心"
        window.guide_data = {
            "poe2_act4_area16": {
                "default": {"mini_navi": {"text": "表示", "voice_text": "ボスを倒します"}},
                "flags": {
                    "act4_tavakai_dead": {
                        "mini_navi": {"text": "表示後", "voice_text": "街へ戻ります"}
                    }
                },
            }
        }
        window.progress_flags = set()
        window.zone_visit_counts = {"poe2_act4_area16": 1}
        window.config = {}
        window._get_zone_id = Mock(return_value="poe2_act4_area16")
        window._save_progress_flags = Mock()
        window._update_guide_and_map = Mock()

        window.set_progress_flag("act4_tavakai_dead")
        assert "act4_tavakai_dead" in window.progress_flags
        assert window._update_guide_and_map.call_args.kwargs["voice_text_changed"] is True
        window._update_guide_and_map.reset_mock()
        window.set_progress_flag("act4_tavakai_dead")
        assert window._update_guide_and_map.call_args.kwargs["voice_text_changed"] is False

    @patch("src.ui.main_window.VoicevoxTtsService")
    def test_voicevox_service_exists_only_in_enabled_poe2_mode(self, service_class):
        window = MainWindow.__new__(MainWindow)
        window.voicevox_tts = None
        window.poe_version = POE1
        window.config = {"voicevox": {"enabled": True}}
        window._sync_voicevox_service()
        service_class.assert_not_called()

        window.poe_version = POE2
        window._sync_voicevox_service()
        service_class.assert_called_once_with(
            speaker_id=3,
            speed_scale=1.2,
            pause_length_scale=1.5,
            post_phoneme_length=0.3,
            volume_scale=1.0,
        )
        assert window.voicevox_tts is service_class.return_value

        window.poe_version = POE1
        window._sync_voicevox_service()
        service_class.return_value.stop.assert_called_once()
        assert window.voicevox_tts is None

    def test_poe1_never_sends_voicevox_request(self):
        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE1
        window.config = {"voicevox": {"enabled": True}}
        window.voicevox_tts = Mock()
        window._speak_poe2_guide({"mini_navi": {"voice_text": "読まない"}})
        window.voicevox_tts.speak_latest.assert_not_called()
    def test_mini_navi_toggle_text_shows_action_for_both_poe_versions(self):
        window = MainWindow.__new__(MainWindow)

        for poe_version in (POE1, POE2):
            window.poe_version = poe_version
            for locked in (True, False):
                window.config = {"mini_guide_overlay": {"enabled": True, "locked": locked}}
                self.assertEqual(window._mini_navi_toggle_text(), "みになびをOFF")

                window.config["mini_guide_overlay"]["enabled"] = False
                self.assertEqual(window._mini_navi_toggle_text(), "みになびをON")

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
            window.mini_navi_overlay.collapse_for_obs.assert_called_once_with()
            window.mini_navi_overlay.apply_settings.assert_called_once_with(
                refresh_window_flags=False
            )

    def test_mini_navi_remembers_current_geometry_before_lock_toggle(self):
        class FakeOverlay:
            def __init__(self):
                self.parent_config = {"mini_guide_overlay": {"width": 360, "height": 100}}

            def _mutable_config(self):
                return self.parent_config["mini_guide_overlay"]

            def _geometry_config(self):
                return self._mutable_config()

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

    def test_enabling_mini_navi_without_current_zone_expands_waiting_content(self):
        window = MainWindow.__new__(MainWindow)
        window.config = {"mini_guide_overlay": {"enabled": False, "locked": True}}
        window.current_zone = None
        window.mini_navi_overlay = Mock()
        window._is_mini_navi_available = Mock(return_value=True)
        window._refresh_mini_navi_toggle = Mock()

        with patch("src.ui.main_window.ConfigManager.save_config"):
            window.toggle_mini_navi_overlay()

        window.mini_navi_overlay.show_last_content_or_waiting.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
