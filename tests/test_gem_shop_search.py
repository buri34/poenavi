import json
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QTabWidget

from src.ui.gem_tracker_widget import GemTrackerWidget
from src.ui.main_window import (
    MainWindow,
    MiniNaviOverlay,
    SearchStringPasteTestDialog,
    VendorSearchPresetDialog,
)
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
from src.utils.poe_version_data import POE1
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
        self.assertTrue(config["gem_shop_search_include_reward_purchases"])
        self.assertEqual(config["gem_shop_search_hold_seconds"], 0.4)

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

    def test_current_act_query_excludes_reward_only_gems(self):
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

    def test_current_act_query_includes_reward_purchase_when_enabled(self):
        plan = [{
            "act": 1,
            "gems": [
                {"name": "ground slam", "type": "vendor"},
                {"name": "momentum support", "type": "quest", "vendor_acts": [1]},
            ],
        }]

        query = build_act_vendor_gem_query(
            plan,
            1,
            {
                "ground slam": "グランドスラム",
                "momentum support": "モーメンタムサポート",
            },
            True,
        )

        self.assertEqual(query, "グランド|モーメン")

    def test_current_act_query_includes_unchecked_reward_gem_sold_in_current_act(self):
        plan = [{
            "act": 1,
            "gems": [{
                "name": "momentum support",
                "type": "quest",
                "vendor_acts": [1, 3],
            }],
        }]

        query = build_act_vendor_gem_query(
            plan,
            1,
            {"momentum support": "モーメンタムサポート"},
            True,
        )

        self.assertEqual(query, "モーメン")

    def test_current_act_query_excludes_reward_purchase_when_disabled(self):
        plan = [{
            "act": 1,
            "gems": [{
                "name": "momentum support",
                "type": "quest",
                "vendor_acts": [1, 3],
            }],
        }]

        query = build_act_vendor_gem_query(
            plan,
            1,
            {"momentum support": "モーメンタムサポート"},
            include_reward_purchases=False,
        )

        self.assertEqual(query, "")

    def test_current_act_query_excludes_checked_reward_gem_sold_in_current_act(self):
        plan = [{
            "act": 1,
            "gems": [{
                "name": "momentum support",
                "type": "quest",
                "vendor_acts": [1, 3],
            }],
        }]

        query = build_act_vendor_gem_query(
            plan,
            1,
            {"momentum support": "モーメンタムサポート"},
            True,
            checked_gems={"momentum support"},
        )

        self.assertEqual(query, "")

    def test_current_act_query_uses_later_vendor_act_for_reward_gem(self):
        plan = [{
            "act": 1,
            "gems": [{
                "name": "momentum support",
                "type": "quest",
                "vendor_acts": [1, 3],
            }],
        }]

        query = build_act_vendor_gem_query(
            plan,
            3,
            {"momentum support": "モーメンタムサポート"},
            True,
        )

        self.assertEqual(query, "モーメン")

    def test_main_window_query_excludes_checked_gems(self):
        window = SimpleNamespace(
            poe_version="poe1",
            config={
                "gem_shop_search_include_reward_purchases": True,
                "gem_shop_search_term_overrides": {},
            },
            gem_tracker=SimpleNamespace(
                _acquisition_plan=[{
                    "act": 1,
                    "gems": [{
                        "name": "momentum support",
                        "type": "quest",
                        "vendor_acts": [1, 3],
                    }],
                }],
                _current_act=1,
                get_checked_gems=lambda: {"momentum support"},
            ),
        )

        self.assertEqual(MainWindow._gem_shop_search_query(window), "")

    def test_dynamic_vendor_preset_uses_current_gem_query_when_selected(self):
        dialog = SearchStringPasteTestDialog(
            None,
            choices=[{
                "name": "3リンク",
                "query": r"-\w-",
                "gem_query_provider": lambda: "モーメン|プレシジ",
            }],
        )
        self.addCleanup(dialog.close)

        self.assertEqual(
            dialog._query_for_choice(dialog.choices[0]),
            r"-\w-|モーメン|プレシジ",
        )

    def test_dynamic_vendor_preset_keeps_base_query_when_no_gems_match(self):
        dialog = SearchStringPasteTestDialog(
            None,
            choices=[{
                "name": "3リンク",
                "query": r"-\w-",
                "gem_query_provider": lambda: "",
            }],
        )
        self.addCleanup(dialog.close)

        self.assertEqual(dialog._query_for_choice(dialog.choices[0]), r"-\w-")

    def test_vendor_preset_dynamic_flag_adds_provider_without_changing_legacy_data(self):
        with TemporaryDirectory() as tmp:
            preset_path = Path(tmp) / "vendor_search_presets_poe1.json"
            preset_path.write_text(json.dumps({"presets": [
                {"name": "legacy", "query": "legacy-query"},
                {
                    "name": "dynamic",
                    "query": "base-query",
                    "include_current_act_gems": True,
                },
            ]}), encoding="utf-8")
            window = SimpleNamespace(
                poe_version="poe1",
                _vendor_search_presets_path=lambda _version: str(preset_path),
                _gem_shop_search_query=lambda: "current-gems",
            )

            presets = MainWindow._load_vendor_search_presets(window, enabled_only=True)

        self.assertEqual(presets[0], {
            "name": "legacy", "query": "legacy-query", "enabled": True,
        })
        self.assertEqual(presets[1]["name"], "dynamic")
        self.assertEqual(presets[1]["query"], "base-query")
        self.assertEqual(presets[1]["gem_query_provider"](), "current-gems")

    def test_poe1_preset_serializes_dynamic_gem_flag_only_when_enabled(self):
        dialog = VendorSearchPresetDialog(poe_version=POE1)
        self.addCleanup(dialog.deleteLater)

        self.assertNotIn("include_current_act_gems", dialog.presets()[0])
        dialog.include_current_act_gems_cb.setChecked(True)

        self.assertTrue(dialog.presets()[0]["include_current_act_gems"])

    def test_checking_gem_refreshes_shop_regex_preview(self):
        refresh_calls = []
        owner = SimpleNamespace(
            config={},
            _load_pob_import_state=lambda: {"gem_tracker_checked": []},
            _sync_gem_tracker_checked_state=lambda: None,
            _refresh_gem_shop_search_preview=lambda: refresh_calls.append(True),
        )

        with (
            patch("src.ui.main_window.ConfigManager.save_pob_import_data"),
            patch("src.ui.main_window.ConfigManager.save_config"),
        ):
            MainWindow._on_gem_checked(owner, "momentum support", True)

        self.assertEqual(refresh_calls, [True])

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

    def test_current_act_query_uses_official_name_when_no_unique_short_term_exists(self):
        query = build_act_vendor_gem_query(
            [{"act": 1, "gems": [{"name": "sunder", "type": "vendor", "vendor_acts": [1]}]}],
            1,
            {
                "sunder": "サンダー",
                "herald of thunder": "ヘラルドオブサンダー",
                "thunderstorm": "サンダーストーム",
            },
            True,
        )

        self.assertEqual(query, "サンダー")

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
