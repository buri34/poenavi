import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utils.config_manager import ConfigManager


def write_default_config(app_dir: Path, overrides=None):
    config = {
        "schemaVersion": ConfigManager.CURRENT_SCHEMA_VERSION,
        "hotkeys": {
            "start_stop": "F1",
            "reset": "F2",
            "lap": "F3",
            "undo_lap": "F4",
            "logout": "F5",
            "click_through": "F6",
            "hideout": "F11",
            "monastery": "F12",
            "search_string_test": "none",
        },
        "poe_version": "poe1",
        "poe_version_mode": "ask",
        "text_color": "#e9ffbd",
        "guide_detail_level": "beginner",
        "guide_detail_level_selected": False,
        "always_on_top": True,
        "notified_update_version": "",
    }
    if overrides:
        for key, value in overrides.items():
            if isinstance(config.get(key), dict) and isinstance(value, dict):
                config[key].update(value)
            else:
                config[key] = value
    (app_dir / ConfigManager.DEFAULT_CONFIG_FILE).write_text(
        json.dumps(config), encoding="utf-8"
    )
    return config


class ConfigManagerTest(unittest.TestCase):
    def test_schema_v4_config_receives_poetrieve_hotkey_without_losing_locale(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            user_dir.mkdir()
            write_default_config(app_dir, {
                "hotkeys": {"poetore_capture": "alt+d"},
                "language": "ja",
                "language_selected": False,
                "mini_guide_overlay": {"display_mode": "standard"},
            })
            (user_dir / ConfigManager.CONFIG_FILE).write_text(
                json.dumps({
                    "schemaVersion": 4,
                    "language": "en",
                    "language_selected": True,
                    "hotkeys": {"start_stop": "F7"},
                    "mini_guide_overlay": {"display_mode": "compact"},
                }),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)},
            ), patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()

            self.assertEqual(loaded["schemaVersion"], 4)
            self.assertEqual(loaded["language"], "en")
            self.assertTrue(loaded["language_selected"])
            self.assertEqual(loaded["hotkeys"]["poetore_capture"], "alt+d")
            self.assertEqual(
                loaded["mini_guide_overlay"]["display_mode"],
                "compact",
            )

    def test_existing_alt_d_hotkey_is_not_stolen_by_poetrieve_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            user_dir.mkdir()
            write_default_config(app_dir, {
                "hotkeys": {"poetore_capture": "alt+d"},
            })
            (user_dir / ConfigManager.CONFIG_FILE).write_text(
                json.dumps({
                    "schemaVersion": 4,
                    "hotkeys": {"start_stop": "Alt+D"},
                }),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)},
            ), patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()

            self.assertEqual(loaded["hotkeys"]["start_stop"], "Alt+D")
            self.assertEqual(loaded["hotkeys"]["poetore_capture"], "none")

    def test_schema_v4_adds_standard_mode_to_localized_schema_v3_config(self):
        migrated = ConfigManager._migrate_config({
            "schemaVersion": 3,
            "mini_guide_overlay": {
                "position": {"x": 30, "y": 40},
                "width": 800,
                "height": 130,
                "font_size": 18,
            },
        })

        self.assertEqual(migrated["schemaVersion"], 4)
        self.assertEqual(migrated["mini_guide_overlay"]["display_mode"], "standard")
        self.assertEqual(migrated["mini_guide_overlay"]["position"], {"x": 30, "y": 40})
        self.assertEqual(migrated["mini_guide_overlay"]["width"], 800)
        self.assertEqual(migrated["mini_guide_overlay"]["height"], 130)

    def test_schema_v4_adds_standard_mode_without_changing_existing_geometry(self):
        migrated = ConfigManager._migrate_config({
            "schemaVersion": 2,
            "mini_guide_overlay": {
                "position": {"x": 30, "y": 40},
                "width": 795,
                "height": 126,
            },
        })

        self.assertEqual(migrated["schemaVersion"], ConfigManager.CURRENT_SCHEMA_VERSION)
        self.assertEqual(migrated["mini_guide_overlay"]["display_mode"], "standard")
        self.assertEqual(migrated["mini_guide_overlay"]["position"], {"x": 30, "y": 40})
        self.assertEqual(migrated["mini_guide_overlay"]["width"], 795)
        self.assertEqual(migrated["mini_guide_overlay"]["height"], 126)

    def test_schema_v3_migrates_only_old_mini_navi_defaults(self):
        migrated = ConfigManager._migrate_config({
            "schemaVersion": 1,
            "mini_guide_overlay": {
                "width": 360,
                "height": 100,
                "font_size": 16,
            },
        })

        self.assertEqual(migrated["schemaVersion"], ConfigManager.CURRENT_SCHEMA_VERSION)
        self.assertEqual(migrated["mini_guide_overlay"]["width"], 800)
        self.assertEqual(migrated["mini_guide_overlay"]["height"], 130)
        self.assertEqual(migrated["mini_guide_overlay"]["font_size"], 18)

    def test_schema_v3_preserves_custom_mini_navi_values(self):
        migrated = ConfigManager._migrate_config({
            "schemaVersion": 1,
            "mini_guide_overlay": {
                "width": 795,
                "height": 126,
                "font_size": 17,
            },
        })

        self.assertEqual(migrated["mini_guide_overlay"]["width"], 795)
        self.assertEqual(migrated["mini_guide_overlay"]["height"], 126)
        self.assertEqual(migrated["mini_guide_overlay"]["font_size"], 17)

    def test_schema_v3_size_and_font_migrations_are_independent(self):
        migrated = ConfigManager._migrate_config({
            "schemaVersion": 1,
            "mini_guide_overlay": {
                "width": 600,
                "height": 150,
                "font_size": 16,
            },
        })

        self.assertEqual(migrated["mini_guide_overlay"]["width"], 600)
        self.assertEqual(migrated["mini_guide_overlay"]["height"], 150)
        self.assertEqual(migrated["mini_guide_overlay"]["font_size"], 18)

    def test_schema_v3_migration_runs_only_once(self):
        migrated = ConfigManager._migrate_config({
            "schemaVersion": 3,
            "mini_guide_overlay": {
                "width": 360,
                "height": 100,
                "font_size": 16,
            },
        })

        self.assertEqual(migrated["mini_guide_overlay"]["width"], 360)
        self.assertEqual(migrated["mini_guide_overlay"]["height"], 100)
        self.assertEqual(migrated["mini_guide_overlay"]["font_size"], 16)

    def test_load_config_persists_localized_schema_v2_mini_navi_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            user_dir.mkdir()
            write_default_config(app_dir, {
                "mini_guide_overlay": {
                    "width": 800,
                    "height": 130,
                    "font_size": 18,
                },
            })
            config_path = user_dir / ConfigManager.CONFIG_FILE
            config_path.write_text(json.dumps({
                "schemaVersion": 2,
                "mini_guide_overlay": {
                    "width": 360,
                    "height": 100,
                    "font_size": 15,
                },
            }), encoding="utf-8")

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()
                persisted = json.loads(config_path.read_text(encoding="utf-8"))

            self.assertEqual(loaded["mini_guide_overlay"]["width"], 800)
            self.assertEqual(loaded["mini_guide_overlay"]["height"], 130)
            self.assertEqual(loaded["mini_guide_overlay"]["font_size"], 18)
            self.assertEqual(persisted["mini_guide_overlay"], loaded["mini_guide_overlay"])
            self.assertEqual(persisted["schemaVersion"], ConfigManager.CURRENT_SCHEMA_VERSION)

    def test_save_and_load_uses_user_data_dir_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            write_default_config(app_dir)
            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                config = {"text_color": "#ffffff"}
                ConfigManager.save_config(config)

                config_path = user_dir / ConfigManager.CONFIG_FILE
                self.assertTrue(config_path.exists())
                self.assertEqual(ConfigManager.load_config()["text_color"], "#ffffff")
                self.assertEqual(ConfigManager.load_config()["schemaVersion"], ConfigManager.CURRENT_SCHEMA_VERSION)
                self.assertEqual(ConfigManager.load_config()["hotkeys"]["reset"], "F2")

    def test_legacy_config_is_migrated_to_user_data_dir_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            write_default_config(app_dir)
            legacy_config = {
                "hotkeys": {"start_stop": "F7"},
                "text_color": "#abcdef",
            }
            (app_dir / ConfigManager.CONFIG_FILE).write_text(
                json.dumps(legacy_config), encoding="utf-8"
            )

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()

                self.assertEqual(loaded["hotkeys"]["start_stop"], "F7")
                self.assertEqual(loaded["hotkeys"]["reset"], "F2")
                self.assertEqual(loaded["text_color"], "#abcdef")
                self.assertEqual(loaded["guide_detail_level"], "beginner")
                self.assertFalse(loaded["guide_detail_level_selected"])
                self.assertTrue(loaded["always_on_top"])
                self.assertEqual(loaded["notified_update_version"], "")
                self.assertEqual(loaded["schemaVersion"], ConfigManager.CURRENT_SCHEMA_VERSION)
                self.assertTrue((user_dir / ConfigManager.CONFIG_FILE).exists())
                self.assertFalse((app_dir / ConfigManager.CONFIG_FILE).exists())
                self.assertEqual(len(list(user_dir.glob("config.backup-legacy-*.json"))), 1)

    def test_existing_user_config_wins_over_legacy_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            user_dir.mkdir()
            write_default_config(app_dir)
            (app_dir / ConfigManager.CONFIG_FILE).write_text(
                json.dumps({"text_color": "#legacy"}), encoding="utf-8"
            )
            (user_dir / ConfigManager.CONFIG_FILE).write_text(
                json.dumps({"text_color": "#user"}), encoding="utf-8"
            )

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()

                self.assertEqual(loaded["text_color"], "#user")
                self.assertEqual(loaded["hotkeys"]["reset"], "F2")
                self.assertFalse((app_dir / ConfigManager.CONFIG_FILE).exists())
                self.assertEqual(len(list(user_dir.glob("config.backup-legacy-*.json"))), 0)
                self.assertEqual(len(list(user_dir.glob("config.backup-ignored-legacy-*.json"))), 1)

    def test_default_config_template_is_used_when_no_user_or_legacy_config_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            write_default_config(app_dir, {
                "hotkeys": {"start_stop": "F12"},
                "text_color": "#123456",
            })

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()

                self.assertEqual(loaded["hotkeys"]["start_stop"], "F12")
                self.assertEqual(loaded["hotkeys"]["reset"], "F2")
                self.assertEqual(loaded["text_color"], "#123456")
                self.assertEqual(loaded["schemaVersion"], ConfigManager.CURRENT_SCHEMA_VERSION)
                self.assertTrue((user_dir / ConfigManager.CONFIG_FILE).exists())

    def test_legacy_config_wins_over_default_config_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            write_default_config(app_dir, {"text_color": "#default"})
            (app_dir / ConfigManager.CONFIG_FILE).write_text(
                json.dumps({"text_color": "#legacy"}), encoding="utf-8"
            )

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()

                self.assertEqual(loaded["text_color"], "#legacy")
                self.assertFalse((app_dir / ConfigManager.CONFIG_FILE).exists())
                self.assertEqual(len(list(user_dir.glob("config.backup-legacy-*.json"))), 1)

    def test_load_config_migrates_startup_user_files_at_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            write_default_config(app_dir)
            legacy_files = {
                "notes_poe1.json": "[]",
                "notes_extra.json": "[\"extra\"]",
                "vendor_search_presets.json": "{\"presets\": [{\"name\": \"legacy-poe2\", \"query\": \"abc\"}]}",
                "progress_flags_poe2.json": "{\"active_flags\": []}",
                "timer_poe1.json": "{\"elapsed_ms\": 123}",
            }
            for filename, content in legacy_files.items():
                (app_dir / filename).write_text(content, encoding="utf-8")

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                ConfigManager.load_config()

                for filename, content in legacy_files.items():
                    if filename == "vendor_search_presets.json":
                        migrated = user_dir / "vendor_search_presets_poe2.json"
                        self.assertEqual(migrated.read_text(encoding="utf-8"), content)
                        self.assertFalse((user_dir / filename).exists())
                    else:
                        self.assertEqual((user_dir / filename).read_text(encoding="utf-8"), content)
                    self.assertFalse((app_dir / filename).exists())


    def test_renamed_vendor_presets_migration_does_not_overwrite_existing_poe2_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_dir = Path(tmp) / "user-data"
            user_dir.mkdir()
            old_path = user_dir / "vendor_search_presets.json"
            new_path = user_dir / "vendor_search_presets_poe2.json"
            old_path.write_text("old", encoding="utf-8")
            new_path.write_text("new", encoding="utf-8")

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}):
                migrated_path = ConfigManager.migrate_renamed_user_file(
                    "vendor_search_presets.json",
                    "vendor_search_presets_poe2.json",
                )

                self.assertEqual(migrated_path, new_path.resolve())
                self.assertEqual(new_path.read_text(encoding="utf-8"), "new")
                self.assertFalse(old_path.exists())
                self.assertEqual(len(list(user_dir.glob("vendor_search_presets.backup-renamed-to-vendor_search_presets_poe2-*.json"))), 1)

    def test_legacy_user_file_is_copied_to_user_data_dir_and_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            (app_dir / "notes_poe1.json").write_text("[]", encoding="utf-8")

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                migrated_path = ConfigManager.migrate_legacy_user_file("notes_poe1.json")

                self.assertEqual(migrated_path, (user_dir / "notes_poe1.json").resolve())
                self.assertEqual((user_dir / "notes_poe1.json").read_text(encoding="utf-8"), "[]")
                self.assertFalse((app_dir / "notes_poe1.json").exists())

    def test_existing_user_file_wins_and_legacy_user_file_is_backed_up_then_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            user_dir.mkdir()
            (app_dir / "notes_poe1.json").write_text("[\"legacy\"]", encoding="utf-8")
            (user_dir / "notes_poe1.json").write_text("[\"user\"]", encoding="utf-8")

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                migrated_path = ConfigManager.migrate_legacy_user_file("notes_poe1.json")

                self.assertEqual(migrated_path, (user_dir / "notes_poe1.json").resolve())
                self.assertEqual((user_dir / "notes_poe1.json").read_text(encoding="utf-8"), "[\"user\"]")
                self.assertFalse((app_dir / "notes_poe1.json").exists())
                backups = list(user_dir.glob("notes_poe1.backup-ignored-legacy-*.json"))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_text(encoding="utf-8"), "[\"legacy\"]")

    def test_missing_default_config_template_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                with self.assertRaises(FileNotFoundError):
                    ConfigManager.load_config()
    def test_pob_import_data_is_migrated_out_of_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            write_default_config(app_dir)
            legacy_config = {
                "pob_data": {"class": "witch", "gem_groups": [{"gems": []}]},
                "pob_code": "abc123",
                "gem_tracker_checked": ["raise zombie"],
                "text_color": "#abcdef",
            }
            user_dir.mkdir()
            (user_dir / ConfigManager.CONFIG_FILE).write_text(
                json.dumps(legacy_config), encoding="utf-8"
            )

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()

                self.assertNotIn("pob_data", loaded)
                self.assertNotIn("pob_code", loaded)
                self.assertNotIn("gem_tracker_checked", loaded)
                saved_config = json.loads((user_dir / ConfigManager.CONFIG_FILE).read_text(encoding="utf-8"))
                self.assertNotIn("pob_data", saved_config)
                self.assertNotIn("pob_code", saved_config)
                self.assertNotIn("gem_tracker_checked", saved_config)
                pob_file = user_dir / "pob_import_data.json"
                self.assertTrue(pob_file.exists())
                pob_state = json.loads(pob_file.read_text(encoding="utf-8"))
                self.assertEqual(pob_state["pob_data"]["class"], "witch")
                self.assertEqual(pob_state["pob_code"], "abc123")
                self.assertEqual(pob_state["gem_tracker_checked"], ["raise zombie"])


    def test_poe1_route_selected_migration_keeps_poe2_only_users_unselected(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            write_default_config(app_dir, {
                "poe1_route_act3": "",
                "poe1_route_act8": "",
                "poe1_route_selected": False,
                "client_log_paths": {"poe1": "", "poe2": ""},
            })
            user_dir.mkdir()
            # 旧default由来のルート値だけが入っていて、PoE1ログは未設定のPoE2-only想定。
            (user_dir / ConfigManager.CONFIG_FILE).write_text(json.dumps({
                "setup_completed": True,
                "poe_version": "poe2",
                "poe1_route_act3": "library_detour",
                "poe1_route_act8": "underbelly",
                "client_log_paths": {"poe1": "", "poe2": "C:/poe2/Client.txt"},
            }), encoding="utf-8")

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()

                self.assertFalse(loaded["poe1_route_selected"])

    def test_poe1_route_selected_migration_marks_existing_poe1_log_users_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            write_default_config(app_dir, {
                "poe1_route_act3": "",
                "poe1_route_act8": "",
                "poe1_route_selected": False,
                "client_log_paths": {"poe1": "", "poe2": ""},
            })
            user_dir.mkdir()
            (user_dir / ConfigManager.CONFIG_FILE).write_text(json.dumps({
                "setup_completed": True,
                "poe_version": "poe1",
                "poe1_route_act3": "library_detour",
                "poe1_route_act8": "underbelly",
                "client_log_paths": {"poe1": "C:/poe1/Client.txt", "poe2": ""},
            }), encoding="utf-8")

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()

                self.assertTrue(loaded["poe1_route_selected"])

    def test_poe1_route_selected_migration_marks_changed_routes_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            write_default_config(app_dir, {
                "poe1_route_act3": "",
                "poe1_route_act8": "",
                "poe1_route_selected": False,
                "client_log_paths": {"poe1": "", "poe2": ""},
            })
            user_dir.mkdir()
            (user_dir / ConfigManager.CONFIG_FILE).write_text(json.dumps({
                "poe1_route_act3": "standard",
                "poe1_route_act8": "standard",
                "client_log_paths": {"poe1": "", "poe2": ""},
            }), encoding="utf-8")

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                loaded = ConfigManager.load_config()

                self.assertTrue(loaded["poe1_route_selected"])
                self.assertEqual(ConfigManager.effective_poe1_route_act3(loaded), "standard")
                self.assertEqual(ConfigManager.effective_poe1_route_act8(loaded), "standard")

    def test_save_config_skips_unchanged_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            user_dir = Path(tmp) / "user-data"
            app_dir.mkdir()
            user_dir.mkdir()
            write_default_config(app_dir)

            with patch.dict(os.environ, {ConfigManager.ENV_USER_DATA_DIR: str(user_dir)}), \
                 patch.object(ConfigManager, "get_app_dir", return_value=app_dir):
                config = ConfigManager.load_config()
                with patch.object(ConfigManager, "_write_json", wraps=ConfigManager._write_json) as write_json:
                    ConfigManager.save_config(config)

            write_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
