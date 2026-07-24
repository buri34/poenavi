import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.validate_locales import (
    validate_all,
    validate_local_import_scoping,
    validate_raw_ui_literals,
)


class LocaleValidationTest(unittest.TestCase):
    def test_release_locale_assets_pass_validation(self):
        self.assertEqual(validate_all(Path(__file__).resolve().parents[1]), [])

    def test_local_import_shadowing_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "src"
            source_dir.mkdir()
            (source_dir / "broken.py").write_text(
                "from example import Widget\n"
                "def build():\n"
                "    Widget()\n"
                "    from example import Widget\n",
                encoding="utf-8",
            )

            failures = validate_local_import_scoping(root)

        self.assertEqual(len(failures), 1)
        self.assertIn("local import shadows earlier use", failures[0])

    def test_local_import_before_use_is_allowed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "src"
            source_dir.mkdir()
            (source_dir / "safe.py").write_text(
                "def build():\n"
                "    from example import Widget\n"
                "    Widget()\n",
                encoding="utf-8",
            )

            failures = validate_local_import_scoping(root)

        self.assertEqual(failures, [])

    def test_poetrieve_ui_raw_japanese_literal_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            poetore_dir = root / "src" / "poetore"
            poetore_dir.mkdir(parents=True)
            (poetore_dir / "ui.py").write_text(
                "from PySide6.QtWidgets import QLabel\n"
                "def build():\n"
                "    return QLabel('価格検索')\n",
                encoding="utf-8",
            )

            failures = validate_raw_ui_literals(root)

        self.assertEqual(len(failures), 1)
        self.assertIn("src", failures[0])
        self.assertIn("poetore", failures[0])
        self.assertIn("ui.py", failures[0])


if __name__ == "__main__":
    unittest.main()
