import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utils.guide_data import load_guide_data, save_guide_data
from src.utils.i18n import EN, JA, set_locale
from src.utils.poe_version_data import POE1, POE2, get_guide_filename
from src.utils.zone_lookup import get_zone_display_name


class LocalizedResourcesTest(unittest.TestCase):
    def tearDown(self):
        set_locale(JA)

    def test_english_guide_filenames_and_data_are_available(self):
        self.assertEqual(get_guide_filename(POE1, EN), "guide_data_en.json")
        self.assertEqual(get_guide_filename(POE2, EN), "guide_data_poe2_en.json")
        self.assertTrue(load_guide_data(POE1, EN))
        self.assertTrue(load_guide_data(POE2, EN))

    def test_guide_saves_are_isolated_by_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            def path_for(_version, language):
                return str(tmp_path / f"guide_{language}.json")

            with patch("src.utils.guide_data.get_guide_path", side_effect=path_for):
                save_guide_data({"language": "ja"}, POE1, JA)
                save_guide_data({"language": "en"}, POE1, EN)

            self.assertEqual(json.loads((tmp_path / "guide_ja.json").read_text())["language"], "ja")
            self.assertEqual(json.loads((tmp_path / "guide_en.json").read_text())["language"], "en")

    def test_zone_display_uses_localized_name_without_changing_identity(self):
        zone = {"id": "act1_area2", "zone": "浜辺", "zone_en": "The Coast"}
        self.assertEqual(get_zone_display_name(zone, JA), "浜辺")
        self.assertEqual(get_zone_display_name(zone, "en-US"), "The Coast")


if __name__ == "__main__":
    unittest.main()
