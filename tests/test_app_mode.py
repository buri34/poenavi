import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog

import main
from src.app_mode import (
    POENAVI_MODE,
    POETORE_MODE,
    normalize_app_mode,
    save_startup_preferences,
    startup_preferences,
)
from src.ui.startup_dialogs import AppModeSelectionDialog
from src.utils.poe_version_data import POE1, POE2


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

    def test_dialog_allows_poetore_when_poe2_is_selected(self):
        dialog = AppModeSelectionDialog(
            current_mode=POETORE_MODE,
            poe_version=POE2,
        )

        self.assertEqual(dialog.selected_mode, POETORE_MODE)
        self.assertTrue(dialog.poetore_card.isChecked())
        self.assertTrue(dialog.poetore_card.isEnabled())

    def test_saved_poetore_mode_can_skip_selector_in_poe2(self):
        dialog = MagicMock()
        dialog.exec.return_value = QDialog.Accepted
        dialog.selected_mode = POENAVI_MODE
        dialog.skip_selector = False
        config = {
            "poe_version": POE2,
            "startup": {
                "preferred_mode": POETORE_MODE,
                "show_mode_selector": False,
            },
        }

        with patch(
            "src.ui.startup_dialogs.AppModeSelectionDialog",
            return_value=dialog,
        ) as dialog_class, patch.object(main.ConfigManager, "save_config"):
            selected = main.select_app_mode(config)

        self.assertEqual(selected, POETORE_MODE)
        dialog_class.assert_not_called()

    def test_fixed_poe_version_is_resolved_before_mode_selection(self):
        config = {"poe_version": POE1, "poe_version_mode": POE2}

        with patch.object(main.ConfigManager, "save_config") as save_config:
            selected = main.select_poe_version(config)

        self.assertEqual(selected["poe_version"], POE2)
        self.assertEqual(config["poe_version"], POE1)
        save_config.assert_called_once_with(selected)

    def test_ask_poe_version_returns_dialog_selection(self):
        dialog = MagicMock()
        dialog.exec.return_value = QDialog.Accepted
        dialog.selected_version = POE2
        config = {"poe_version": POE1, "poe_version_mode": "ask"}

        with patch(
            "src.ui.startup_dialogs.PoeVersionSelectionDialog",
            return_value=dialog,
        ) as dialog_class, patch.object(
            main.ConfigManager, "save_config",
        ) as save_config:
            selected = main.select_poe_version(config)

        self.assertEqual(selected["poe_version"], POE2)
        dialog_class.assert_called_once_with(current_version=POE1)
        save_config.assert_called_once_with(selected)

    def test_cancelling_poe_version_selection_stops_startup(self):
        dialog = MagicMock()
        dialog.exec.return_value = QDialog.Rejected

        with patch(
            "src.ui.startup_dialogs.PoeVersionSelectionDialog",
            return_value=dialog,
        ), patch.object(main.ConfigManager, "save_config") as save_config:
            selected = main.select_poe_version({"poe_version_mode": "ask"})

        self.assertIsNone(selected)
        save_config.assert_not_called()

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

        def select_version(config):
            events.append("select_version")
            return config

        def select_mode(_config):
            events.append("select_mode")
            return POENAVI_MODE

        update_module = SimpleNamespace(run_startup_update_gate=update_gate)
        composition_module = SimpleNamespace(
            create_mode_window=lambda _mode: window
        )
        single_instance = MagicMock()
        single_instance.start.return_value = True
        with patch.object(main, "QApplication", return_value=app), \
             patch.object(main, "SingleInstanceGuard", return_value=single_instance), \
             patch.object(main.ConfigManager, "load_config", side_effect=load_config), \
             patch.object(main, "select_poe_version", side_effect=select_version), \
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
            ["load_config", "update_gate", "load_config", "select_version", "select_mode"],
        )
        app.setProperty.assert_any_call("startupUpdateChecked", True)
        app.setProperty.assert_any_call("startupPoeVersionSelected", True)
        app.setProperty.assert_any_call("appMode", POENAVI_MODE)
        single_instance.set_window.assert_called_once_with(window)
        window.show.assert_called_once_with()

    def test_second_instance_exits_before_loading_config(self):
        app = MagicMock()
        single_instance = MagicMock()
        single_instance.start.return_value = False

        with patch.object(main, "QApplication", return_value=app), \
             patch.object(main, "SingleInstanceGuard", return_value=single_instance), \
             patch.object(main.QMessageBox, "information") as information, \
             patch.object(main.ConfigManager, "load_config") as load_config:
            self.assertEqual(main.run(), 0)

        information.assert_called_once_with(
            None,
            "ぽえなびは起動済みです",
            "ぽえなびはすでに起動しています。\n"
            "起動中の画面を前面に表示します。",
        )
        load_config.assert_not_called()
        app.exec.assert_not_called()

    def test_mode_selection_dialog_uses_act_support_label(self):
        dialog = AppModeSelectionDialog()

        self.assertEqual(dialog.poenavi_card.text(), "ぽえなび\nAct攻略支援")
        self.assertNotIn("レベリング・進行支援", dialog.poenavi_card.text())


if __name__ == "__main__":
    unittest.main()
