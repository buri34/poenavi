import json
import unittest
from pathlib import Path

from src.utils.gem_shop_search import (
    HoldTrigger,
    build_act_vendor_gem_query,
    build_unique_gem_search_terms,
    format_gem_shop_search_preview,
)
from src.utils.gem_resolver import load_gem_names_ja
from src.utils.window_focus import is_path_of_exile_process_name


class GemShopSearchTest(unittest.TestCase):
    def test_default_config_sets_capslock_for_gem_shop_search(self):
        config_path = Path(__file__).parents[1] / "default_config.json"
        with config_path.open(encoding="utf-8") as file:
            config = json.load(file)

        self.assertEqual(config["hotkeys"]["gem_shop_search"], "CapsLock")
        self.assertTrue(config["gem_shop_search_exclude_quest_rewards"])

    def test_current_act_query_excludes_quest_rewards_when_enabled(self):
        plan = [
            {
                "act": 1,
                "gems": [
                    {"name": "ground slam", "type": "vendor"},
                    {"name": "momentum support", "type": "quest"},
                    {"name": "chance to bleed support", "type": "vendor"},
                ],
            },
            {
                "act": 2,
                "gems": [{"name": "precision", "type": "vendor"}],
            },
        ]

        query = build_act_vendor_gem_query(
            plan,
            1,
            {
                "ground slam": "グランドスラム",
                "chance to bleed support": "出血付与サポート",
            },
            True,
        )

        self.assertEqual(query, "グランド|出血付与")

    def test_current_act_query_includes_quest_rewards_when_disabled(self):
        plan = [{
            "act": 1,
            "gems": [
                {"name": "ground slam", "type": "vendor"},
                {"name": "momentum support", "type": "quest"},
            ],
        }]

        query = build_act_vendor_gem_query(
            plan,
            1,
            {
                "ground slam": "グランドスラム",
                "momentum support": "モーメンタムサポート",
            },
            False,
        )

        self.assertEqual(query, "グランド|モーメン")

    def test_current_act_query_keeps_lilly_gems_and_removes_duplicates(self):
        plan = [
            {
                "act": 6,
                "gems": [
                    {"name": "leap slam", "type": "lilly"},
                    {"name": "leap slam", "type": "vendor"},
                    {"name": "dash", "type": "quest"},
                ],
            },
        ]

        query = build_act_vendor_gem_query(
            plan,
            6,
            {"leap slam": "リープスラム", "dash": "ダッシュ"},
            True,
        )

        self.assertEqual(query, "リープス")

    def test_unique_terms_use_the_shortest_non_overlapping_four_characters(self):
        terms = build_unique_gem_search_terms(load_gem_names_ja())

        self.assertEqual(terms["momentum support"], "モーメン")
        self.assertEqual(terms["precision"], "プレシジ")
        self.assertEqual(terms["leap slam"], "リープス")
        self.assertEqual(terms["spectral throw"], "ラルスロ")
        self.assertEqual(terms["chance to bleed support"], "出血付与")
        self.assertEqual(terms["frostblink"], "ストブリ")
        for key, term in terms.items():
            self.assertEqual(
                sum(term in name for name in load_gem_names_ja().values()),
                1,
                key,
            )

    def test_preview_text_describes_the_current_regex_or_empty_target(self):
        self.assertEqual(
            format_gem_shop_search_preview("モーメン|プレシジ"),
            "ショップRegex: モーメン|プレシジ",
        )
        self.assertEqual(
            format_gem_shop_search_preview(""),
            "ショップRegex: 対象ジェムなし",
        )

    def test_released_hold_never_triggers(self):
        trigger = HoldTrigger()
        token = trigger.start()
        trigger.release()

        self.assertFalse(trigger.consume_if_current(token))

    def test_hold_trigger_is_consumed_once(self):
        trigger = HoldTrigger()
        token = trigger.start()

        self.assertTrue(trigger.consume_if_current(token))
        self.assertFalse(trigger.consume_if_current(token))

    def test_path_of_exile_process_name_accepts_only_game_executables(self):
        self.assertTrue(is_path_of_exile_process_name("PathOfExile_x64.exe"))
        self.assertTrue(is_path_of_exile_process_name("PathOfExileSteam.exe"))
        self.assertFalse(is_path_of_exile_process_name("PoENavi.exe"))


if __name__ == "__main__":
    unittest.main()
