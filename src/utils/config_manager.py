import json
import os
import sys

class ConfigManager:
    CONFIG_FILE = "config.json"

    @classmethod
    def _get_base_dir(cls):
        """exeの場合はexeのあるフォルダ、通常はカレントディレクトリ"""
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.getcwd()
    DEFAULT_CONFIG = {
        "hotkeys": {
            "start_stop": "F1",
            "reset": "F2"
        },
        # 今後色設定などもここから読み込むように拡張可能
        "text_color": "#e9ffbd"
    }

    @classmethod
    def _get_config_path(cls):
        """config.jsonのパスを取得（exeフォルダ優先 → _MEIPASS → カレント）"""
        # exeと同じフォルダ（ユーザーが編集したconfig）
        base = cls._get_base_dir()
        path = os.path.join(base, cls.CONFIG_FILE)
        if os.path.exists(path):
            return path
        # PyInstaller同梱（初期config）
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            bundled = os.path.join(meipass, cls.CONFIG_FILE)
            if os.path.exists(bundled):
                return bundled
        return path  # デフォルト（なければload_configでDEFAULT_CONFIG）

    @classmethod
    def load_config(cls):
        config_path = cls._get_config_path()
        if not os.path.exists(config_path):
            return cls.DEFAULT_CONFIG.copy()
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                # マージ処理（新しいキーが増えた場合などに対応）
                default = cls.DEFAULT_CONFIG.copy()
                # 簡易的なマージ（1階層のみ）
                for key, value in config.items():
                    if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                        default[key].update(value)
                    else:
                        default[key] = value
                return default
        except:
            return cls.DEFAULT_CONFIG.copy()

    @classmethod
    def save_config(cls, config):
        path = os.path.join(cls._get_base_dir(), cls.CONFIG_FILE)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
