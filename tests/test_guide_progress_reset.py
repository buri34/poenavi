import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QTabWidget

from src.ui.main_window import MainWindow
from src.ui.settings_dialog import SettingsDialog
from src.utils.new_character_history import NewCharacterHistoryResult
from src.utils.poe_version_data import POE1, POE2


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
        self.assertEqual(
            description.text(),
            "ガイド進行制御に用いるフラグ等の状態は、新しいキャラクターの開始時に"
            "自動で検知して、初期状態にするため、通常は操作不要です。\n"
            "にもかかわらず、フラグ等の状態が前のキャラクターから残っていると思われる場合は、"
            "以下のボタンを押して初期状態に戻してください。タイマーの記録やぽえなびの設定は"
            "変更されません。\n\n"
            "なお、Act 6以降を攻略中の場合、リセット後にぽえなび本体のガイドタイル右側に"
            "表示されている「Act 1-5」のトグルをクリックして「Act 6-10」表示へ"
            "切り替えてください。",
        )

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

    def test_twilight_then_level_two_clears_old_flags_and_persisted_state(self):
        with TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress_flags_poe1.json"
            window = MainWindow.__new__(MainWindow)
            window.poe_version = POE1
            window.progress_flags = {"act7_crypt_enter"}
            window.interlude_ready = {"old"}
            window.zone_visit_counts = {"act7_area2": 2}
            window._last_visit_key = "act7_area2"
            window._visited_town = True
            window._last_log_zone = "西の森"
            window._progress_flags_path = Mock(return_value=str(progress_path))
            window._twilight_strand_entered = True
            window.player_level = 1
            window.level_label = QLabel()
            window.visit_override = 2
            window._update_visit_btn = Mock()
            window._in_act10 = True
            window._set_part2 = Mock()
            window.current_zone = None

            MainWindow.on_level_up(window, "new-character", 2)

            self.assertEqual(window.progress_flags, set())
            self.assertEqual(window.zone_visit_counts, {})
            self.assertFalse(window._twilight_strand_entered)
            self.assertIsNone(window.visit_override)
            self.assertFalse(window._in_act10)
            self.assertEqual(
                json.loads(progress_path.read_text(encoding="utf-8")),
                {
                    "active_flags": [],
                    "zone_visit_counts": {},
                    "last_visit_key": None,
                    "visited_town": False,
                    "last_log_zone": "西の森",
                },
            )

    def test_live_candidate_is_cancelled_after_leaving_twilight_strand(self):
        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE1
        window._restoring = False
        window._twilight_strand_entered = False
        window._known_zone_names = Mock(return_value={"黄昏の岸辺", "海岸"})

        MainWindow._track_live_new_character_candidate(window, "黄昏の岸辺")
        self.assertTrue(window._twilight_strand_entered)
        MainWindow._track_live_new_character_candidate(window, "海岸")
        self.assertFalse(window._twilight_strand_entered)

    def test_last_log_zone_excludes_towns_and_restoring(self):
        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE1
        window._restoring = False
        window._last_log_zone = "西の森"
        window._known_zone_names = Mock(return_value={"西の森", "海岸", "ライオンアイの見張り場"})
        window._is_town_zone = Mock(side_effect=lambda zone: zone == "ライオンアイの見張り場")
        window._save_progress_flags = Mock()

        MainWindow._record_last_non_town_zone(window, "ライオンアイの見張り場")
        self.assertEqual(window._last_log_zone, "西の森")
        window._restoring = True
        MainWindow._record_last_non_town_zone(window, "海岸")
        self.assertEqual(window._last_log_zone, "西の森")
        window._restoring = False
        MainWindow._record_last_non_town_zone(window, "海岸")
        self.assertEqual(window._last_log_zone, "海岸")
        window._save_progress_flags.assert_called_once_with()

    def test_last_log_zone_is_restored_from_poe1_progress_file(self):
        with TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress_flags_poe1.json"
            progress_path.write_text(
                json.dumps({
                    "active_flags": [],
                    "zone_visit_counts": {"act2_area8": 1},
                    "last_visit_key": "act2_area8",
                    "visited_town": False,
                    "last_log_zone": "西の森",
                }),
                encoding="utf-8",
            )
            window = MainWindow.__new__(MainWindow)
            window.poe_version = POE1
            window._progress_flags_path = Mock(return_value=str(progress_path))

            MainWindow._restore_progress_flags(window)

            self.assertEqual(window._last_log_zone, "西の森")

    def test_historical_check_uses_riverbank_rule_in_poe2_mode(self):
        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE2
        window._last_log_zone = "オガムの農地"
        window._known_zone_names = Mock(return_value={"オガムの農地", "川岸"})
        window.town_zones_by_version = {POE2: []}
        window.historical_progress_check_finished = Mock()

        with (
            patch("src.ui.main_window.threading.Thread") as thread,
            patch("src.ui.main_window.os.path.exists", return_value=True),
        ):
            MainWindow._start_historical_progress_check(window, __file__)

        thread.assert_called_once()
        target = thread.call_args.kwargs["target"]
        with patch(
            "src.ui.main_window.inspect_client_log_history",
            return_value=NewCharacterHistoryResult(True, True, "川岸"),
        ) as inspect:
            target()
        self.assertEqual(inspect.call_args.kwargs["start_zone_names"], {"川岸", "The Riverbank"})
        self.assertFalse(inspect.call_args.kwargs["require_level_two"])
        window.historical_progress_check_finished.emit.assert_called_once_with(
            (POE2, "オガムの農地", NewCharacterHistoryResult(True, True, "川岸"))
        )

    def test_historical_match_confirms_reset_and_rebases_anchor(self):
        class FakeMessageBox:
            Question = 1
            Yes = 2
            No = 4
            shown_text = None
            shown_info = None

            def __init__(self, parent):
                pass

            def setIcon(self, value):
                pass

            def setWindowTitle(self, value):
                pass

            def setText(self, value):
                type(self).shown_text = value

            def setInformativeText(self, value):
                type(self).shown_info = value

            def setStandardButtons(self, value):
                pass

            def setDefaultButton(self, value):
                pass

            def exec(self):
                return self.Yes

        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE1
        window._last_log_zone = "西の森"
        window._has_guide_progress = Mock(return_value=True)
        window._reset_guide_progress_from_settings = Mock()
        window._save_progress_flags = Mock()
        result = NewCharacterHistoryResult(True, True, "黄昏の岸辺")

        with patch("src.ui.main_window.QMessageBox", FakeMessageBox):
            MainWindow._handle_historical_progress_check_result(
                window, (POE1, "西の森", result)
            )

        self.assertEqual(
            FakeMessageBox.shown_text,
            "保存された進行状況と異なる進行状況を検知しました。\n"
            "新キャラクターに合わせるため、ガイド進行をリセットしますか？",
        )
        self.assertIn("前回最後に確認したエリア：西の森", FakeMessageBox.shown_info)
        window._reset_guide_progress_from_settings.assert_called_once_with()
        self.assertEqual(window._last_log_zone, "黄昏の岸辺")
        window._save_progress_flags.assert_called_once_with()

    def test_poe2_progress_state_is_saved_and_restored_like_poe1(self):
        with TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress_flags_poe2.json"
            window = MainWindow.__new__(MainWindow)
            window.poe_version = POE2
            window.progress_flags = {"act2_traitor_clear"}
            window.zone_visit_counts = {"poe2_act2_area06": 2}
            window._last_visit_key = "poe2_act2_area06"
            window._visited_town = True
            window._last_log_zone = "オガムの農地"
            window._progress_flags_path = Mock(return_value=str(progress_path))

            MainWindow._save_progress_flags(window)
            self.assertEqual(
                json.loads(progress_path.read_text(encoding="utf-8")),
                {
                    "active_flags": ["act2_traitor_clear"],
                    "zone_visit_counts": {"poe2_act2_area06": 2},
                    "last_visit_key": "poe2_act2_area06",
                    "visited_town": True,
                    "last_log_zone": "オガムの農地",
                },
            )

            restored = MainWindow.__new__(MainWindow)
            restored.poe_version = POE2
            restored._progress_flags_path = Mock(return_value=str(progress_path))
            MainWindow._restore_progress_flags(restored)

            self.assertEqual(restored.progress_flags, {"act2_traitor_clear"})
            self.assertEqual(restored.zone_visit_counts, {"poe2_act2_area06": 2})
            self.assertEqual(restored._last_visit_key, "poe2_act2_area06")
            self.assertTrue(restored._visited_town)
            self.assertEqual(restored._last_log_zone, "オガムの農地")

    def test_legacy_poe2_flags_file_restores_with_empty_visit_state(self):
        with TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress_flags_poe2.json"
            progress_path.write_text(
                json.dumps({"active_flags": ["act2_traitor_clear"]}),
                encoding="utf-8",
            )
            window = MainWindow.__new__(MainWindow)
            window.poe_version = POE2
            window._progress_flags_path = Mock(return_value=str(progress_path))

            MainWindow._restore_progress_flags(window)

            self.assertEqual(window.progress_flags, {"act2_traitor_clear"})
            self.assertEqual(window.zone_visit_counts, {})
            self.assertIsNone(window._last_visit_key)
            self.assertFalse(window._visited_town)
            self.assertIsNone(window._last_log_zone)

    def test_clearing_poe2_progress_also_clears_visit_state(self):
        with TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress_flags_poe2.json"
            window = MainWindow.__new__(MainWindow)
            window.poe_version = POE2
            window.progress_flags = {"act2_traitor_clear"}
            window.interlude_ready = {"old"}
            window.zone_visit_counts = {"poe2_act2_area06": 2}
            window._last_visit_key = "poe2_act2_area06"
            window._visited_town = True
            window._last_log_zone = "オガムの農地"
            window._progress_flags_path = Mock(return_value=str(progress_path))

            MainWindow.clear_progress_flags(window)

            self.assertEqual(window.progress_flags, set())
            self.assertEqual(window.zone_visit_counts, {})
            self.assertIsNone(window._last_visit_key)
            self.assertFalse(window._visited_town)
            self.assertEqual(
                json.loads(progress_path.read_text(encoding="utf-8")),
                {
                    "active_flags": [],
                    "zone_visit_counts": {},
                    "last_visit_key": None,
                    "visited_town": False,
                    "last_log_zone": "オガムの農地",
                },
            )

    def test_poe2_historical_match_shows_riverbank_evidence(self):
        class FakeMessageBox:
            Question = 1
            Yes = 2
            No = 4
            shown_info = None

            def __init__(self, parent): pass
            def setIcon(self, value): pass
            def setWindowTitle(self, value): pass
            def setText(self, value): pass
            def setInformativeText(self, value): type(self).shown_info = value
            def setStandardButtons(self, value): pass
            def setDefaultButton(self, value): pass
            def exec(self): return self.No

        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE2
        window._last_log_zone = "オガムの農地"
        window._has_guide_progress = Mock(return_value=True)
        window._reset_guide_progress_from_settings = Mock()
        window._save_progress_flags = Mock()
        result = NewCharacterHistoryResult(True, True, "川岸")

        with patch("src.ui.main_window.QMessageBox", FakeMessageBox):
            MainWindow._handle_historical_progress_check_result(
                window, (POE2, "オガムの農地", result)
            )

        self.assertIn("その後のログ：「川岸」への入場を検知", FakeMessageBox.shown_info)
        window._reset_guide_progress_from_settings.assert_not_called()
        self.assertEqual(window._last_log_zone, "川岸")
        window._save_progress_flags.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
