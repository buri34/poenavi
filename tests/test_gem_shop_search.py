import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QTabWidget

from src.ui.gem_tracker_widget import GemTrackerWidget
from src.ui.main_window import MainWindow, MiniNaviOverlay
from src.ui.settings_dialog import (
    SettingsDialog,
    find_duplicate_hotkeys,
)
from src.utils import gem_shop_search
from src.utils.gem_shop_search import (
    HoldTrigger,
    build_act_vendor_gem_query,
    build_unique_gem_search_terms,
    format_gem_shop_search_preview,
    get_gem_shop_search_feedback,
)
from src.utils.gem_resolver import load_gem_names_ja
from src.utils.window_focus import is_path_of_exile_process_name


class GemShopSearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_default_config_sets_capslock_for_gem_shop_search(self):
        config_path = Path(__file__).parents[1] / "default_config.json"
        with config_path.open(encoding="utf-8") as file:
            config = json.load(file)

        self.assertEqual(config["hotkeys"]["gem_shop_search"], "CapsLock")
        self.assertTrue(config["gem_shop_search_exclude_quest_rewards"])
        self.assertEqual(config["gem_shop_search_hold_seconds"], 0.4)

    def test_mini_navi_prompt_only_appears_in_poe1_towns_with_shop_targets(self):
        self.assertEqual(
            gem_shop_search.get_mini_navi_gem_shop_prompt("poe1", True, "モーメン|プレシジ"),
            "💎 ショップでジェム購入可 — クリックでRegexをコピー",
        )
        self.assertEqual(gem_shop_search.get_mini_navi_gem_shop_prompt("poe1", False, "モーメン"), "")
        self.assertEqual(gem_shop_search.get_mini_navi_gem_shop_prompt("poe2", True, "モーメン"), "")
        self.assertEqual(gem_shop_search.get_mini_navi_gem_shop_prompt("poe1", True, ""), "")

    def test_mini_navi_displays_the_gem_shop_prompt_only_when_provided(self):
        overlay = MiniNaviOverlay()

        overlay.set_gem_shop_prompt("💎 ショップでジェム購入可 — クリックでRegexをコピー")
        self.assertFalse(overlay.gem_shop_prompt_label.isHidden())
        self.assertIn("Regexをコピー", overlay.gem_shop_prompt_label.text())

        overlay.set_gem_shop_prompt("")
        self.assertTrue(overlay.gem_shop_prompt_label.isHidden())
        overlay.close()

    def test_custom_term_override_replaces_the_automatic_term(self):
        plan = [{"act": 1, "gems": [{"name": "ground slam", "type": "vendor"}]}]
        names = {"ground slam": "グランドスラム"}

        query = build_act_vendor_gem_query(
            plan,
            1,
            names,
            True,
            {"ground slam": "グランドス"},
        )

        self.assertEqual(query, "グランドス")

    def test_hold_delay_uses_the_saved_seconds(self):
        window = SimpleNamespace(config={"gem_shop_search_hold_seconds": 0.7})

        self.assertEqual(MainWindow._gem_shop_search_hold_delay_ms(window), 700)

    def test_settings_persist_gem_search_hold_delay_and_term_overrides(self):
        dialog = SettingsDialog(
            current_config={
                "gem_shop_search_hold_seconds": 0.7,
                "gem_shop_search_term_overrides": {"ground slam": "グラウンド"},
            }
        )

        self.assertEqual(dialog.gem_shop_search_hold_seconds_spin.value(), 0.7)
        self.assertEqual(
            dialog.get_settings()["gem_shop_search_term_overrides"],
            {"ground slam": "グラウンド"},
        )

    def test_term_review_tab_is_after_app_info_and_filters_changed_terms(self):
        settings = SettingsDialog(
            current_config={"gem_shop_search_term_overrides": {"ground slam": "グラウンド"}}
        )
        tabs = settings.findChild(QTabWidget)
        self.assertEqual(tabs.tabText(tabs.count() - 1), "短縮語を見直す")

        review = settings.gem_shop_search_term_review
        review.changed_only_checkbox.setChecked(True)
        review._apply_filter()

        ground_slam_row = review._row_by_gem_key["ground slam"]
        self.assertFalse(review._table.isRowHidden(ground_slam_row))
        self.assertTrue(review._table.isRowHidden(review._row_by_gem_key["momentum support"]))

    def test_gem_shop_search_status_is_shown_near_cursor_as_a_short_tooltip(self):
        owner = object()
        cursor_pos = QPoint(120, 240)

        with (
            patch("src.ui.main_window.QCursor.pos", return_value=cursor_pos),
            patch("src.ui.main_window.QToolTip.showText") as show_text,
        ):
            MainWindow._show_gem_shop_search_status(owner, "Act 2: 3件を検索します")

        self.assertEqual(show_text.call_args.args[0], cursor_pos)
        self.assertEqual(show_text.call_args.args[1], "Act 2: 3件を検索します")
        self.assertIs(show_text.call_args.args[2], owner)
        self.assertEqual(show_text.call_args.args[4], 2500)

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

    def test_manual_act_change_emits_the_new_act(self):
        widget = GemTrackerWidget()
        received = []
        widget.act_changed.connect(received.append)

        widget._next_act()

        self.assertEqual(received, [2])

    def test_gem_shop_search_feedback_explains_success_and_safe_skips(self):
        self.assertEqual(
            get_gem_shop_search_feedback(3, "モーメン|プレシジ", True),
            "Act 3: 2件を検索します",
        )
        self.assertEqual(
            get_gem_shop_search_feedback(3, "", True),
            "対象ジェムがありません",
        )
        self.assertEqual(
            get_gem_shop_search_feedback(3, "モーメン", False),
            "PoEが前面でないため入力しません",
        )

    def test_duplicate_hotkeys_are_reported_without_unassigned_keys(self):
        duplicates = find_duplicate_hotkeys({
            "start_stop": "F1",
            "reset": "f1",
            "lap": "none",
            "gem_shop_search": "CapsLock",
        })

        self.assertEqual(duplicates, {"f1": ["start_stop", "reset"]})

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
