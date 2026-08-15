import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QTabWidget

from src.ui.main_window import MainWindow
from src.ui.settings_dialog import SettingsDialog
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

        callback.assert_called_once_with(POE1)
        information.assert_called_once()

    def test_poe2_hides_regex_tab_and_omits_poe1_only_reset_guidance(self):
        callback = Mock()
        dialog = SettingsDialog(
            current_config={"poe_version": POE2},
            guide_progress_reset_callback=callback,
        )
        tabs = dialog.findChild(QTabWidget)
        tab_names = [tabs.tabText(index) for index in range(tabs.count())]

        self.assertNotIn("Regex短縮設定", tab_names)
        self.assertEqual(tab_names[-2:], ["その他", "アプリ情報"])
        description = dialog.findChild(QLabel, "guideProgressResetDescription")
        self.assertNotIn("なお、Act 6以降", description.text())

        button = dialog.findChild(QPushButton, "guideProgressResetButton")
        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.Yes),
            patch.object(QMessageBox, "information"),
        ):
            button.click()
        callback.assert_called_once_with(POE2)

    def test_switching_version_updates_version_specific_tabs_and_description(self):
        dialog = SettingsDialog(current_config={"poe_version": POE1})
        tabs = dialog.findChild(QTabWidget)
        self.assertIn("Regex短縮設定", [tabs.tabText(i) for i in range(tabs.count())])

        dialog.poe_version_radios[POE2].setChecked(True)
        self.assertNotIn("Regex短縮設定", [tabs.tabText(i) for i in range(tabs.count())])
        description = dialog.findChild(QLabel, "guideProgressResetDescription")
        self.assertNotIn("なお、Act 6以降", description.text())

        dialog.poe_version_radios[POE1].setChecked(True)
        self.assertIn("Regex短縮設定", [tabs.tabText(i) for i in range(tabs.count())])
        self.assertIn("なお、Act 6以降", description.text())

    def test_manual_reset_clears_guide_state_without_touching_timer(self):
        window = MainWindow.__new__(MainWindow)
        window.poe_version = POE1
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

    def test_resetting_inactive_poe2_version_clears_persisted_guide_state(self):
        with TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress_flags_poe2.json"
            progress_path.write_text(
                json.dumps({"active_flags": ["poe2_old_flag"]}),
                encoding="utf-8",
            )
            window = MainWindow.__new__(MainWindow)
            window.poe_version = POE1
            window.clear_progress_flags = Mock()

            with patch(
                "src.ui.main_window.ConfigManager.get_user_data_path",
                return_value=progress_path,
            ):
                MainWindow._reset_guide_progress_from_settings(window, POE2)

            window.clear_progress_flags.assert_not_called()
            self.assertEqual(
                json.loads(progress_path.read_text(encoding="utf-8")),
                {
                    "active_flags": [],
                    "zone_visit_counts": {},
                    "last_visit_key": None,
                    "visited_town": False,
                },
            )

    def test_poe2_progress_state_is_saved_and_restored_like_poe1(self):
        with TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress_flags_poe2.json"
            window = MainWindow.__new__(MainWindow)
            window.poe_version = POE2
            window.progress_flags = {"act2_traitor_clear"}
            window.zone_visit_counts = {"poe2_act2_area06": 2}
            window._last_visit_key = "poe2_act2_area06"
            window._visited_town = True
            window._progress_flags_path = Mock(return_value=str(progress_path))

            MainWindow._save_progress_flags(window)
            self.assertEqual(
                json.loads(progress_path.read_text(encoding="utf-8")),
                {
                    "active_flags": ["act2_traitor_clear"],
                    "zone_visit_counts": {"poe2_act2_area06": 2},
                    "last_visit_key": "poe2_act2_area06",
                    "visited_town": True,
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
                },
            )

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
                },
            )


if __name__ == "__main__":
    unittest.main()
