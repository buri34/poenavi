import unittest

from PySide6.QtWidgets import QApplication

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
        self.assertFalse(dialog.poenavi_card.icon().isNull())
        self.assertFalse(dialog.poetore_card.icon().isNull())
        self.assertTrue(
            AppModeSelectionDialog._app_icon_path("icon.ico").endswith(
                "assets/app/icon.ico"
            )
        )
        self.assertTrue(
            AppModeSelectionDialog._app_icon_path("icon2.ico").endswith(
                "assets/app/icon2.ico"
            )
        )

    def test_dialog_returns_checked_mode(self):
        dialog = AppModeSelectionDialog(current_mode=POENAVI_MODE)
        dialog.poetore_card.setChecked(True)
        dialog._accept_selection()

        self.assertEqual(dialog.selected_mode, POETORE_MODE)


if __name__ == "__main__":
    unittest.main()
