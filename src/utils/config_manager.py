import copy
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from src.utils.poe_version_data import POE1


class ConfigManager:
    CONFIG_FILE = "config.json"
    DEFAULT_CONFIG_FILE = "default_config.json"
    APP_NAME = "PoENavi"
    ENV_USER_DATA_DIR = "POENAVI_USER_DATA_DIR"
    CURRENT_SCHEMA_VERSION = 3
    POE1_ROUTE_ACT3_DEFAULT = "library_detour"
    POE1_ROUTE_ACT8_DEFAULT = "standard"
    POE1_ROUTE_ACT3_OLD_DEFAULT = "library_detour"
    POE1_ROUTE_ACT8_OLD_DEFAULT = "underbelly"
    STARTUP_LEGACY_USER_FILES = [
        "notes.json",
        "notes_poe1.json",
        "notes_poe2.json",
        "vendor_search_presets.json",
        "vendor_search_presets_poe1.json",
        "vendor_search_presets_poe2.json",
        "progress_flags_poe1.json",
        "progress_flags_poe2.json",
        "timer_poe1.json",
        "timer_poe2.json",
        "pob_import_data.json",
    ]

    @classmethod
    def _get_base_dir(cls):
        """アプリ本体のあるフォルダを取得する。"""
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        # src/utils/config_manager.py から見たリポジトリルート。
        # main.pyを別カレントディレクトリから起動しても同じ場所を指すようにする。
        return str(Path(__file__).resolve().parents[2])

    @classmethod
    def get_app_dir(cls):
        """アプリ本体のあるフォルダをPathで取得する。"""
        return Path(cls._get_base_dir())

    @classmethod
    def get_user_data_dir(cls):
        """ユーザー設定を保存するフォルダを取得する。

        開発・検証時は POENAVI_USER_DATA_DIR で保存先を上書きできる。
        通常のWindows exe版では %APPDATA%/PoENavi を使う。
        """
        override = os.getenv(cls.ENV_USER_DATA_DIR)
        if override:
            return Path(override).expanduser().resolve()

        if sys.platform == "win32":
            appdata = os.getenv("APPDATA")
            if appdata:
                return Path(appdata) / cls.APP_NAME
            return Path.home() / "AppData" / "Roaming" / cls.APP_NAME

        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / cls.APP_NAME

        xdg_config_home = os.getenv("XDG_CONFIG_HOME")
        if xdg_config_home:
            return Path(xdg_config_home) / cls.APP_NAME
        return Path.home() / ".config" / cls.APP_NAME

    @classmethod
    def get_user_data_path(cls, filename):
        """ユーザーデータ配下のファイルパスを取得する。"""
        return cls.get_user_data_dir() / filename

    @classmethod
    def migrate_legacy_user_file(cls, filename):
        """旧アプリ本体フォルダ直下のユーザーデータを正式保存先へ移行する。

        既にユーザーデータ側にファイルがある場合は上書きしない。
        移行に成功した旧ファイルは、ユーザーが混乱しないように削除する。
        """
        filename = Path(filename).name
        destination = cls.get_user_data_path(filename)
        source = cls.get_app_dir() / filename

        if destination.exists():
            if source.exists() and source.resolve() != destination.resolve():
                # 正式保存先が既にある場合は上書きしない。
                # ただし旧ファイルが見える場所に残ると移行失敗に見えるため、バックアップして削除する。
                cls._backup_user_file(source, reason="ignored-legacy")
                cls._remove_file_if_safe(source)
            return destination

        if source.exists() and source.resolve() != destination.resolve():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            cls._remove_file_if_safe(source)
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination


    @classmethod
    def migrate_renamed_user_file(cls, old_filename, new_filename):
        """ユーザーデータのファイル名変更を安全に移行する。

        new側が無ければ old→new にコピーして old を削除する。
        new側が既にある場合は上書きせず、oldはバックアップして削除する。
        旧アプリ本体フォルダ直下にold/newが残っている場合も同じ方針で片付ける。
        """
        old_filename = Path(old_filename).name
        new_filename = Path(new_filename).name
        user_dir = cls.get_user_data_dir()
        user_dir.mkdir(parents=True, exist_ok=True)
        old_user = cls.get_user_data_path(old_filename)
        new_user = cls.get_user_data_path(new_filename)

        if not new_user.exists() and old_user.exists():
            shutil.copy2(old_user, new_user)
            cls._remove_file_if_safe(old_user)
        elif new_user.exists() and old_user.exists():
            cls._backup_user_file(old_user, reason=f"renamed-to-{Path(new_filename).stem}")
            cls._remove_file_if_safe(old_user)

        app_dir = cls.get_app_dir()
        for legacy in (app_dir / new_filename, app_dir / old_filename):
            if not legacy.exists() or legacy.resolve() == new_user.resolve():
                continue
            if not new_user.exists():
                shutil.copy2(legacy, new_user)
                cls._remove_file_if_safe(legacy)
            else:
                cls._backup_user_file(legacy, reason="ignored-legacy")
                cls._remove_file_if_safe(legacy)

        return new_user

    @classmethod
    def pob_import_data_path(cls):
        """PoBインポート結果の保存先。config.jsonとは分離する。"""
        return cls.get_user_data_path("pob_import_data.json")

    @classmethod
    def load_pob_import_data(cls):
        path = cls.pob_import_data_path()
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            print(f"[ConfigManager] Failed to load PoB import data: {exc}")
            cls._backup_user_file(path, reason="broken")
            cls._remove_file_if_safe(path)
            return {}

    @classmethod
    def save_pob_import_data(cls, data):
        cls._write_json(cls.pob_import_data_path(), data or {})

    @classmethod
    def clear_pob_import_data(cls):
        cls._remove_file_if_safe(cls.pob_import_data_path())

    @classmethod
    def migrate_pob_import_data_from_config(cls, config):
        """旧config.json内のPoBインポート内容を専用JSONへ移す。"""
        if not isinstance(config, dict):
            return config
        pob_data = config.pop("pob_data", None)
        pob_code = config.pop("pob_code", None)
        gem_tracker_checked = config.pop("gem_tracker_checked", None)
        if pob_data is not None or pob_code is not None or gem_tracker_checked is not None:
            path = cls.pob_import_data_path()
            if not path.exists():
                payload = {"pob_data": pob_data, "pob_code": pob_code}
                if gem_tracker_checked is not None:
                    payload["gem_tracker_checked"] = gem_tracker_checked
                cls.save_pob_import_data(payload)
            else:
                existing = cls.load_pob_import_data()
                changed = False
                if gem_tracker_checked is not None and "gem_tracker_checked" not in existing:
                    existing["gem_tracker_checked"] = gem_tracker_checked
                    changed = True
                if changed:
                    cls.save_pob_import_data(existing)
                print("[ConfigManager] pob_import_data.json already exists; keeping existing file and removing legacy config PoB fields")
        return config

    @classmethod
    def _get_startup_legacy_user_filenames(cls):
        """起動時にまとめて移行する旧ユーザーデータファイル名を取得する。"""
        filenames = list(cls.STARTUP_LEGACY_USER_FILES)
        app_dir = cls.get_app_dir()
        if app_dir.exists():
            # 将来 notes_foo.json のようなメモファイルが増えても起動時に移行する。
            filenames.extend(path.name for path in app_dir.glob("note*.json") if path.is_file())

        unique = []
        seen = set()
        for filename in filenames:
            safe_name = Path(filename).name
            if safe_name not in seen:
                seen.add(safe_name)
                unique.append(safe_name)
        return unique

    @classmethod
    def migrate_startup_legacy_user_files(cls):
        """PoENavi起動時に旧ユーザーデータをまとめて正式保存先へ移行する。"""
        migrated_paths = []
        for filename in cls._get_startup_legacy_user_filenames():
            destination = cls.migrate_legacy_user_file(filename)
            migrated_paths.append(destination)
        migrated_paths.append(
            cls.migrate_renamed_user_file(
                "vendor_search_presets.json",
                "vendor_search_presets_poe2.json",
            )
        )
        return migrated_paths

    @classmethod
    def _get_config_path(cls):
        """現在の正式なconfig.jsonパスを取得する。"""
        return str(cls.get_user_data_path(cls.CONFIG_FILE))

    @classmethod
    def _get_legacy_config_paths(cls):
        """旧バージョン互換のconfig候補。

        v2.1以前はexe/カレントフォルダ直下のconfig.jsonを読み書きしていた。
        新バージョン初回起動時、ユーザーデータ側にconfigがまだ無い場合だけ移行する。
        """
        paths = []

        app_config = cls.get_app_dir() / cls.CONFIG_FILE
        paths.append(app_config)

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(Path(meipass) / cls.CONFIG_FILE)

        # 重複を除去しつつ順序を維持
        unique_paths = []
        seen = set()
        for path in paths:
            resolved = str(path.resolve()) if path.exists() else str(path)
            if resolved not in seen:
                seen.add(resolved)
                unique_paths.append(path)
        return unique_paths

    @classmethod
    def _get_default_config_template_paths(cls):
        """初回設定テンプレート(default_config.json)の候補。"""
        paths = [cls.get_app_dir() / cls.DEFAULT_CONFIG_FILE]

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.append(Path(meipass) / cls.DEFAULT_CONFIG_FILE)

        unique_paths = []
        seen = set()
        for path in paths:
            resolved = str(path.resolve()) if path.exists() else str(path)
            if resolved not in seen:
                seen.add(resolved)
                unique_paths.append(path)
        return unique_paths

    @classmethod
    def _deep_merge(cls, default, config):
        merged = copy.deepcopy(default)
        for key, value in config.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = cls._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    @classmethod
    def _read_json(cls, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def _write_json(cls, path, config):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

    @classmethod
    def _backup_config(cls, source_path, reason="migration"):
        source_path = Path(source_path)
        if not source_path.exists():
            return None

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"config.backup-{reason}-{timestamp}.json"
        backup_path = cls.get_user_data_dir() / backup_name
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, backup_path)
        return backup_path

    @classmethod
    def _backup_user_file(cls, source_path, reason="migration"):
        source_path = Path(source_path)
        if not source_path.exists():
            return None

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"{source_path.stem}.backup-{reason}-{timestamp}{source_path.suffix}"
        backup_path = cls.get_user_data_dir() / backup_name
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, backup_path)
        return backup_path

    @classmethod
    def _remove_file_if_safe(cls, path):
        """移行済みの旧ユーザーファイルを削除する。

        削除失敗で起動不能になるのは避けたいので、権限やロック等の失敗は警告だけにする。
        """
        try:
            path = Path(path)
            if path.exists() and path.is_file():
                path.unlink()
                return True
        except Exception as e:
            print(f"[WARN] Failed to remove migrated legacy file: {path} ({e})")
        return False

    @classmethod
    def effective_poe1_route_act3(cls, config):
        return (config or {}).get("poe1_route_act3") or cls.POE1_ROUTE_ACT3_DEFAULT

    @classmethod
    def effective_poe1_route_act8(cls, config):
        return (config or {}).get("poe1_route_act8") or cls.POE1_ROUTE_ACT8_DEFAULT

    @classmethod
    def _infer_poe1_route_selected(cls, config):
        if "poe1_route_selected" in config:
            return bool(config.get("poe1_route_selected"))
        act3 = config.get("poe1_route_act3")
        act8 = config.get("poe1_route_act8")
        # 旧デフォルト値と違う値なら、ユーザーが一度選択/変更した可能性が高い。
        if act3 and act3 != cls.POE1_ROUTE_ACT3_OLD_DEFAULT:
            return True
        if act8 and act8 != cls.POE1_ROUTE_ACT8_OLD_DEFAULT:
            return True
        # 既にPoE1ログパスが設定済みなら、既存PoE1ユーザーとして再表示を避ける。
        client_log_paths = config.get("client_log_paths") or {}
        if client_log_paths.get(POE1):
            return True
        return False

    @classmethod
    def _migrate_config(cls, config):
        """configのスキーマ差分を吸収する。

        現時点では旧configにschemaVersionを付与する。
        不足キーの補完は呼び出し側で読み込んだdefault_config.jsonを元に行う。
        将来schemaVersionを上げる場合はここに変換処理を追加する。
        """
        migrated = copy.deepcopy(config)
        schema_version = migrated.get("schemaVersion", 0)

        if not isinstance(schema_version, int):
            schema_version = 0

        if schema_version < 1:
            migrated["schemaVersion"] = 1

        if schema_version < 2:
            mini_navi = migrated.get("mini_guide_overlay")
            if isinstance(mini_navi, dict):
                if mini_navi.get("width") == 360 and mini_navi.get("height") == 100:
                    mini_navi["width"] = 800
                    mini_navi["height"] = 130
                if mini_navi.get("font_size") == 16:
                    mini_navi["font_size"] = 18

        if schema_version < 3:
            mini_navi = migrated.get("mini_guide_overlay")
            if isinstance(mini_navi, dict):
                mini_navi.setdefault("display_mode", "standard")

        if "poe1_route_selected" not in migrated:
            migrated["poe1_route_selected"] = cls._infer_poe1_route_selected(config)

        migrated["schemaVersion"] = cls.CURRENT_SCHEMA_VERSION
        return migrated

    @classmethod
    def _load_default_config_template(cls):
        """default_config.jsonを設定の正本として読み込む。"""
        errors = []
        for template_path in cls._get_default_config_template_paths():
            if not template_path.exists():
                continue
            try:
                template = cls._read_json(template_path)
                if not isinstance(template, dict):
                    raise ValueError("default_config.json must contain a JSON object")
                return cls._migrate_config(template)
            except Exception as e:
                errors.append(f"{template_path}: {e}")
        details = "; ".join(errors) if errors else "file not found"
        raise FileNotFoundError(f"default_config.json could not be loaded ({details})")

    @classmethod
    def _load_from_path(cls, config_path):
        raw_config = cls._read_json(config_path)
        default_config = cls._load_default_config_template()
        migrated = cls._migrate_config(cls._deep_merge(default_config, raw_config))
        if isinstance(raw_config, dict) and "poe1_route_selected" not in raw_config:
            migrated["poe1_route_selected"] = cls._infer_poe1_route_selected(raw_config)
        return migrated

    @classmethod
    def _migrate_legacy_config_if_needed(cls):
        config_path = Path(cls._get_config_path())
        if config_path.exists():
            app_config = cls.get_app_dir() / cls.CONFIG_FILE
            if app_config.exists() and app_config.resolve() != config_path.resolve():
                cls._backup_config(app_config, reason="ignored-legacy")
                cls._remove_file_if_safe(app_config)
            return False

        for legacy_path in cls._get_legacy_config_paths():
            if not legacy_path.exists():
                continue
            if legacy_path.resolve() == config_path.resolve():
                continue

            config = cls._load_from_path(legacy_path)
            config = cls.migrate_pob_import_data_from_config(config)
            cls._backup_config(legacy_path, reason="legacy")
            cls._write_json(config_path, config)

            # _MEIPASS 内の同梱ファイルはアプリ内部リソースなので削除しない。
            # ユーザーが見える旧ファイル（exe/アプリフォルダ直下）だけ削除する。
            if legacy_path.resolve().parent == cls.get_app_dir().resolve():
                cls._remove_file_if_safe(legacy_path)
            return True

        return False

    @classmethod
    def load_config(cls):
        cls._migrate_legacy_config_if_needed()
        config_path = Path(cls._get_config_path())

        if not config_path.exists():
            config = cls._load_default_config_template()
            config = cls.migrate_pob_import_data_from_config(config)
            cls._write_json(config_path, config)
            cls.migrate_startup_legacy_user_files()
            return config

        try:
            config = cls._load_from_path(config_path)
            config = cls.migrate_pob_import_data_from_config(config)
            # schemaVersion付与や新規キー補完が入った場合は正式保存先へ反映する。
            cls._write_json(config_path, config)
            cls.migrate_startup_legacy_user_files()
            return config
        except Exception:
            cls._backup_config(config_path, reason="broken")
            config = cls._load_default_config_template()
            cls._write_json(config_path, config)
            cls.migrate_startup_legacy_user_files()
            return config

    @classmethod
    def save_config(cls, config):
        default_config = cls._load_default_config_template()
        config = cls._migrate_config(cls._deep_merge(default_config, config))
        config = cls.migrate_pob_import_data_from_config(config)
        config_path = Path(cls._get_config_path())
        if config_path.exists():
            try:
                if cls._read_json(config_path) == config:
                    return
            except Exception:
                pass
        cls._write_json(config_path, config)
