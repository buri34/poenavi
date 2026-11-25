import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

try:
    from src.ui.main_window import MainWindow
except ModuleNotFoundError as exc:  # pragma: no cover - local dev without GUI deps
    MainWindow = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

from src.utils.config_manager import ConfigManager
from src.utils.poe_version_data import POE1, POE2


@unittest.skipIf(MainWindow is None, f"GUI dependencies unavailable: {IMPORT_ERROR}")
class TimerStateStorageTest(unittest.TestCase):
    def make_window(self, poe_version=POE1):
        window = MainWindow.__new__(MainWindow)
        window.poe_version = poe_version
        window.config = {"poe_version": poe_version}
        window.accumulated_time = 12.5
        window.lap_times = [1.0, None]
        window.lap_record_order = [1]
        window.current_act = 2
        window.is_running = False
        window.start_time = 0.0
        window.segment_recorder = Mock(segments=[])
        return window

    def test_timer_state_is_saved_to_user_data_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: tmp}):
                window = self.make_window(POE2)

                window._save_timer_state()

                path = Path(tmp) / "timer_poe2.json"
                self.assertTrue(path.exists())
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["accumulated_time"], 12.5)
                self.assertEqual(data["current_act"], 2)
                self.assertNotIn("saved_timer::timer_poe2.json", window.config)

    def test_legacy_config_timer_state_is_migrated_and_removed_from_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: tmp}):
                legacy_key = "saved_timer::timer_poe1.json"
                legacy_payload = {
                    "accumulated_time": 34.0,
                    "lap_times": [2.0],
                    "lap_record_order": [1],
                    "current_act": 1,
                }
                window = self.make_window(POE1)
                window.config = {
                    "poe_version": POE1,
                    legacy_key: legacy_payload,
                }

                migrated = window._migrate_legacy_timer_state_from_config()

                self.assertEqual(migrated, legacy_payload)
                self.assertNotIn(legacy_key, window.config)
                path = Path(tmp) / "timer_poe1.json"
                self.assertTrue(path.exists())
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), legacy_payload)
                saved_config = ConfigManager.load_config()
                self.assertNotIn(legacy_key, saved_config)

    def test_elapsed_time_uses_monotonic_clock(self):
        window = self.make_window()
        window.is_running = True
        window.start_time = 100.0

        with patch("src.ui.main_window.time.monotonic", return_value=107.5), patch(
            "src.ui.main_window.time.time",
            return_value=-999999.0,
        ):
            self.assertEqual(window.get_elapsed_time(), 20.0)

    def test_display_uses_monotonic_elapsed_time(self):
        window = self.make_window()
        window.is_running = True
        window.start_time = 100.0
        window.update_text = Mock()

        with patch("src.ui.main_window.time.monotonic", return_value=107.5):
            window.update_display()

        window.update_text.assert_called_once_with(20.0)

    def test_running_snapshot_includes_current_elapsed_time(self):
        window = self.make_window()
        window.is_running = True
        window.start_time = 100.0

        with patch("src.ui.main_window.time.monotonic", return_value=107.5):
            payload = window._timer_state_payload()

        self.assertEqual(payload["accumulated_time"], 20.0)
        self.assertTrue(window.is_running)

    def test_interrupted_atomic_write_preserves_previous_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: tmp}):
                window = self.make_window()
                path = Path(tmp) / "timer_poe1.json"
                path.write_text('{"previous": true}', encoding="utf-8")

                with patch("src.ui.main_window.os.replace", side_effect=OSError("stop")):
                    with self.assertRaises(OSError):
                        window._save_timer_state_payload({"replacement": True})

                self.assertEqual(
                    json.loads(path.read_text(encoding="utf-8")),
                    {"previous": True},
                )
                self.assertEqual(list(Path(tmp).glob(".*.tmp")), [])

    def test_lap_operations_save_after_each_successful_change(self):
        window = self.make_window()
        window.lap_times = [None, None]
        window.lap_record_order = []
        window.current_act = 1
        window.get_elapsed_time = Mock(return_value=30.0)
        window.update_lap_display = Mock()
        window._has_pob_import_data = Mock(return_value=False)
        window._save_timer_state = Mock()

        window.record_lap()
        window._save_timer_state.assert_called_once_with()

        window._save_timer_state.reset_mock()
        window.record_lap_at(2)
        window._save_timer_state.assert_called_once_with()

        window._save_timer_state.reset_mock()
        window.undo_lap()
        window._save_timer_state.assert_called_once_with()

    def test_completed_zone_segment_saves_once(self):
        window = self.make_window()
        completed = {"zone_id": "act1_area1", "duration": 10.0}
        window.segment_recorder.record_entry.return_value = completed
        window.get_elapsed_time = Mock(return_value=20.0)
        window._update_segment_summary = Mock()
        window._save_timer_state = Mock()

        result = window._record_zone_segment("act1_area2", "海岸")

        self.assertEqual(result, completed)
        window.segment_recorder.record_entry.assert_called_once_with(
            "act1_area2", "海岸", 20.0,
        )
        window._save_timer_state.assert_called_once_with()

    def test_restored_timer_is_paused(self):
        window = self.make_window()
        window.is_running = True
        window.start_time = 123.0
        window._load_timer_state_payload = Mock(return_value={
            "accumulated_time": 45.0,
            "lap_times": [10.0, None],
            "lap_record_order": [1],
            "current_act": 2,
            "segments": [],
        })
        window._migrate_legacy_timer_state_from_config = Mock()
        window.update_text = Mock()
        window.update_lap_display = Mock()
        window._set_part2 = Mock()

        window._restore_timer_state()

        self.assertFalse(window.is_running)
        self.assertEqual(window.start_time, 0.0)
        self.assertEqual(window.accumulated_time, 45.0)

    def test_close_saves_non_empty_timer_state(self):
        window = self.make_window()
        window._main_window_initialized = False
        window._initial_positioned = False
        window._has_timer_record = Mock(return_value=True)
        window._save_timer_state = Mock()
        window._close_detached_panels = Mock()

        with patch("src.ui.main_window.QMainWindow.closeEvent") as base_close:
            window.closeEvent(Mock())

        window._save_timer_state.assert_called_once_with()
        base_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
