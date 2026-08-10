import json
import unittest
from pathlib import Path

from src.utils.guide_data import get_zone_guide


class Poe2Act3ZicoatlFlagGuideTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guide_data = json.loads(Path("guide_data_poe2.json").read_text(encoding="utf-8"))

    def test_flag_frame_belongs_to_jungle_ruins_not_infested_barrens(self):
        self.assertIn("act3_zicoatl_dead", self.guide_data["poe2_act3_area02"]["flags"])
        self.assertNotIn("act3_zicoatl_dead", self.guide_data["poe2_act3_area04"]["flags"])

    def test_flag_switches_jungle_ruins_guide(self):
        guide = get_zone_guide(
            self.guide_data,
            "poe2_act3_area02",
            active_flags={"act3_zicoatl_dead"},
        )

        self.assertEqual(guide["objective"], "・「石の祭壇」を起動する\n・「マトラン水路」へ行く")

    def test_flag_does_not_switch_infested_barrens_guide(self):
        guide = get_zone_guide(
            self.guide_data,
            "poe2_act3_area04",
            active_flags={"act3_zicoatl_dead"},
        )

        self.assertEqual(guide["objective"], "「キメラル湿地」へ行く")


if __name__ == "__main__":
    unittest.main()
