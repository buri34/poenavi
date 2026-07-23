import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PySide6.QtWidgets import QApplication, QDialog
    from src.ui.language_dialog import LanguageSelectionDialog
except ModuleNotFoundError as exc:  # pragma: no cover - local dev without GUI deps
    QApplication = None
    QDialog = None
    LanguageSelectionDialog = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

from src.utils.config_manager import ConfigManager
from src.utils.i18n import EN, JA


def write_template(app_dir: Path):
    (app_dir / ConfigManager.DEFAULT_CONFIG_FILE).write_text(
        json.dumps({
            "schemaVersion": ConfigManager.CURRENT_SCHEMA_VERSION,
            "language": JA,
            "language_selected": False,
        }),
        encoding="utf-8",
    )


@unittest.skipIf(LanguageSelectionDialog is None, f"GUI dependencies unavailable: {IMPORT_ERROR}")
class LanguageDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_os_locale_only_preselects_the_choice(self):
        with patch("src.ui.language_dialog.QLocale.system", return_value=type("Locale", (), {"name": lambda self: "en_CA"})()):
            dialog = LanguageSelectionDialog()
        self.assertEqual(dialog.selected_locale, EN)
        dialog.deleteLater()

        with patch("src.ui.language_dialog.QLocale.system", return_value=type("Locale", (), {"name": lambda self: "ja_JP"})()):
            dialog = LanguageSelectionDialog()
        self.assertEqual(dialog.selected_locale, JA)
        dialog.deleteLater()

    def test_cancel_remains_a_rejected_dialog(self):
        dialog = LanguageSelectionDialog(preferred_locale=JA)
        dialog.reject()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        dialog.deleteLater()


class ConfigLanguageMigrationTest(unittest.TestCase):
    def test_new_install_keeps_unselected_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user"
            app_dir.mkdir()
            write_template(app_dir)
            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()
            self.assertEqual(loaded["language"], JA)
            self.assertFalse(loaded["language_selected"])

    def test_legacy_config_is_japanese_and_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user"
            app_dir.mkdir()
            write_template(app_dir)
            user_dir.mkdir()
            (user_dir / ConfigManager.CONFIG_FILE).write_text(json.dumps({"text_color": "#fff"}), encoding="utf-8")
            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()
            self.assertEqual(loaded["language"], JA)
            self.assertTrue(loaded["language_selected"])

    def test_explicit_english_without_selection_marker_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user"
            app_dir.mkdir()
            write_template(app_dir)
            user_dir.mkdir()
            (user_dir / ConfigManager.CONFIG_FILE).write_text(json.dumps({"language": EN}), encoding="utf-8")
            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()
            self.assertEqual(loaded["language"], EN)
            self.assertTrue(loaded["language_selected"])

    def test_broken_config_recovers_in_japanese(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user"
            app_dir.mkdir()
            write_template(app_dir)
            user_dir.mkdir()
            (user_dir / ConfigManager.CONFIG_FILE).write_text("{broken", encoding="utf-8")
            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()
            self.assertEqual(loaded["language"], JA)
            self.assertTrue(loaded["language_selected"])


if __name__ == "__main__":
    unittest.main()
