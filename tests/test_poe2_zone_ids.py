import json
import unittest
from collections import Counter
from pathlib import Path

from src.utils.zone_data_poe2 import DEFAULT_ZONE_DATA_POE2


def flatten_zone_data(zone_data):
    for act_name, zones in zone_data.items():
        for zone in zones:
            yield act_name, zone


class Poe2ZoneIdTest(unittest.TestCase):
    def test_default_poe2_zone_ids_are_unique(self):
        ids = [zone["id"] for _, zone in flatten_zone_data(DEFAULT_ZONE_DATA_POE2)]
        duplicates = sorted(zone_id for zone_id, count in Counter(ids).items() if count > 1)
        self.assertEqual(duplicates, [])

    def test_runtime_poe2_zone_ids_are_unique(self):
        zone_master_path = Path(__file__).resolve().parents[1] / "data" / "zone_data.json"
        zone_master = json.loads(zone_master_path.read_text(encoding="utf-8"))
        poe2_zones = zone_master["zone_data_by_version"]["poe2"]
        ids = [zone["id"] for _, zone in flatten_zone_data(poe2_zones)]
        duplicates = sorted(zone_id for zone_id, count in Counter(ids).items() if count > 1)
        self.assertEqual(duplicates, [])

    def test_trial_of_the_sekhemas_has_separate_id_from_dreadnoughts_wake(self):
        act2 = DEFAULT_ZONE_DATA_POE2["Act 2"]
        by_name = {zone["zone_en"]: zone["id"] for zone in act2}

        self.assertEqual(by_name["The Dreadnought's Wake"], "poe2_act2_area19")
        self.assertEqual(by_name["Trial of the Sekhemas"], "poe2_act2_area20")


if __name__ == "__main__":
    unittest.main()
