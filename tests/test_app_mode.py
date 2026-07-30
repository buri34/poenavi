import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

import main
from src.app_mode import (
    POENAVI_MODE,
    POETORE_MODE,
    normalize_app_mode,
    save_startup_preferences,
    startup_preferences,
)
from src.ui.startup_dialogs import AppModeSelectionDialog


class AppModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_missing_startup_settings_show_selector_with_safe_default(self):
        self.assertEqual(startup_preferences({}), (POENAVI_MODE, True))

    def test_valid_saved_mode_can_skip_selector(self):
        config = {
            "startup": {
                "preferred_mode": POETORE_MODE,
                "show_mode_selector": False,
            }
        }
        self.assertEqual(startup_preferences(config), (POETORE_MODE, False))

    def test_invalid_mode_falls_back_to_poennavi(self):
        self.assertEqual(normalize_app_mode("unknown"), POENAVI_MODE)

    def test_save_preferences_does_not_mutate_original(self):
        original = {"startup": {"preferred_mode": POENAVI_MODE}, "other": 1}
        updated = save_startup_preferences(original, POETORE_MODE, True)

        self.assertEqual(original["startup"]["preferred_mode"], POENAVI_MODE)
        self.assertEqual(updated["startup"]["preferred_mode"], POETORE_MODE)
        self.assertFalse(updated["startup"]["show_mode_selector"])
        self.assertEqual(updated["other"], 1)

    def test_dialog_uses_previous_mode_but_does_not_skip_by_default(self):
        dialog = AppModeSelectionDialog(current_mode=POETORE_MODE)

        self.assertTrue(dialog.poetore_card.isChecked())
        self.assertFalse(dialog.skip_selector)
        self.assertIn("border: 2px solid", dialog.skip_selector_checkbox.styleSheet())
        self.assertFalse(dialog.poenavi_card.icon().isNull())
        self.assertFalse(dialog.poetore_card.icon().isNull())
        for icon_name in ("icon.ico", "icon2.ico"):
            icon_path = Path(AppModeSelectionDialog._app_icon_path(icon_name))
            self.assertEqual(icon_path.parts[-3:], ("assets", "app", icon_name))

    def test_dialog_returns_checked_mode(self):
        dialog = AppModeSelectionDialog(current_mode=POENAVI_MODE)
        dialog.poetore_card.setChecked(True)
        dialog._accept_selection()

        self.assertEqual(dialog.selected_mode, POETORE_MODE)

    def test_mode_icons_have_transparent_corners(self):
        for icon_name in ("icon.ico", "icon2.ico"):
            pixmap = QPixmap(AppModeSelectionDialog._app_icon_path(icon_name))
            self.assertFalse(pixmap.isNull())
            image = pixmap.toImage()
            corners = (
                (0, 0),
                (image.width() - 1, 0),
                (0, image.height() - 1),
                (image.width() - 1, image.height() - 1),
            )
            self.assertTrue(
                all(image.pixelColor(x, y).alpha() < 64 for x, y in corners),
                icon_name,
            )

    def test_update_gate_runs_before_mode_selection(self):
        events = []
        app = MagicMock()
        app.exec.return_value = 0
        window = MagicMock()

        def load_config():
            events.append("load_config")
            return {}

        def update_gate(_config):
            events.append("update_gate")
            return True

        def select_mode(_config):
            events.append("select_mode")
            return POENAVI_MODE

        update_module = SimpleNamespace(run_startup_update_gate=update_gate)
        composition_module = SimpleNamespace(
            create_mode_window=lambda _mode: window
        )
        with patch.object(main, "QApplication", return_value=app), \
             patch.object(main.ConfigManager, "load_config", side_effect=load_config), \
             patch.object(main, "select_app_mode", side_effect=select_mode), \
             patch.object(main.QTimer, "singleShot"), \
             patch.dict(
                 "sys.modules",
                 {
                     "src.update.startup_gate": update_module,
                     "src.app_composition": composition_module,
                 },
             ):
            self.assertEqual(main.run(), 0)

        self.assertEqual(
            events,
            ["load_config", "update_gate", "load_config", "select_mode"],
        )
        app.setProperty.assert_any_call("startupUpdateChecked", True)
        app.setProperty.assert_any_call("appMode", POENAVI_MODE)
        window.show.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
