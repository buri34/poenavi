import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.utils.guide_data import get_zone_guide
from src.utils.poe_version_data import POE1
from src.utils.zone_master_data import load_zone_data_by_version


class Act10RavagedSquareFlagsTest(unittest.TestCase):
    def test_ravaged_square_has_required_flag_frames(self):
        guide_data = json.loads(Path("guide_data.json").read_text(encoding="utf-8"))

        flags = guide_data["act10_area3"]["visits"]["1"].get("flags", {})

        for flag_key in (
            "act10_controlblocks_enter",
            "act10_controlblocks_enter+act10_ossuary_enter",
            "act10_controlblocks_enter+act10_ossuary_enter+act10_desecratedchambers_enter",
        ):
            with self.subTest(flag_key=flag_key):
                self.assertIn(flag_key, flags)
                self.assertIsInstance(flags[flag_key], dict)

    def test_act5_and_act10_duplicate_names_have_distinct_zone_ids(self):
        zone_data = load_zone_data_by_version()[POE1]
        act5_control = [z for z in zone_data["Act 5"] if z["zone"] == "奴隷管理区画"]
        act10_control = [z for z in zone_data["Act 10"] if z["zone"] == "奴隷管理区画"]
        act5_ossuary = [z for z in zone_data["Act 5"] if z["zone"] == "納骨堂"]
        act10_ossuary = [z for z in zone_data["Act 10"] if z["zone"] == "納骨堂"]
        act5_reliquary = [z for z in zone_data["Act 5"] if z["zone"] == "聖廟"]
        act10_reliquary = [z for z in zone_data["Act 10"] if z["zone"] == "聖廟"]
        desecrated = [z for z in zone_data["Act 10"] if z["zone"] == "冒涜された広間"]

        self.assertEqual(act5_control[0]["id"], "act5_area2")
        self.assertEqual(act10_control[0]["id"], "act10_area4")
        self.assertEqual(act5_ossuary[0]["id"], "act5_area8")
        self.assertEqual(act10_ossuary[0]["id"], "act10_area5")
        self.assertEqual(act5_reliquary[0]["id"], "act5_area9")
        self.assertEqual(act10_reliquary[0]["id"], "act10_area12")
        self.assertEqual(desecrated[0]["id"], "act10_area7")

    def test_part2_mode_resolves_reliquary_to_act10_empty_guide_slot(self):
        from src.ui.main_window import MainWindow

        window = SimpleNamespace(
            zone_data=load_zone_data_by_version()[POE1],
            part2_mode=True,
            _in_act10=True,
        )
        guide_data = json.loads(Path("guide_data.json").read_text(encoding="utf-8"))

        zone_id = MainWindow._get_zone_id(window, "聖廟")
        guide = get_zone_guide(guide_data, zone_id, visit=1)

        self.assertEqual(zone_id, "act10_area12")
        self.assertIsNone(guide)

    def test_controlblocks_two_flags_and_three_flags_select_different_guides(self):
        guide_data = {
            "act10_area3": {
                "visits": {
                    "1": {
                        "objective": "default objective",
                        "direction": "none",
                        "flags": {
                            "act10_controlblocks_enter": {"objective": "control only"},
                            "act10_controlblocks_enter+act10_ossuary_enter": {"objective": "control ossuary"},
                            "act10_controlblocks_enter+act10_ossuary_enter+act10_desecratedchambers_enter": {
                                "objective": "all three",
                                "mini_navi": {"text": "all three mini", "direction": "se"},
                            },
                        },
                    },
                    "2": {"objective": "visit2 objective", "direction": "se"},
                }
            }
        }

        control_guide = get_zone_guide(
            guide_data,
            "act10_area3",
            visit=2,
            active_flags={"act10_controlblocks_enter"},
        )
        two_guide = get_zone_guide(
            guide_data,
            "act10_area3",
            visit=2,
            active_flags={"act10_controlblocks_enter", "act10_ossuary_enter"},
        )
        three_guide = get_zone_guide(
            guide_data,
            "act10_area3",
            visit=2,
            active_flags={"act10_controlblocks_enter", "act10_ossuary_enter", "act10_desecratedchambers_enter"},
        )
        ossuary_only_guide = get_zone_guide(
            guide_data,
            "act10_area3",
            visit=2,
            active_flags={"act10_ossuary_enter"},
        )

        self.assertEqual(control_guide["objective"], "control only")
        self.assertEqual(two_guide["objective"], "control ossuary")
        self.assertEqual(three_guide["objective"], "all three")
        self.assertEqual(three_guide["mini_navi"], {"text": "all three mini", "direction": "se"})
        self.assertEqual(ossuary_only_guide["objective"], "visit2 objective")


if __name__ == "__main__":
    unittest.main()
