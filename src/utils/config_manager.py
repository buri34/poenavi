import json
import os

class ConfigManager:
    CONFIG_FILE = "config.json"
    DEFAULT_CONFIG = {
        "hotkeys": {
            "start_stop": "F1",
            "reset": "F2"
        },
        # 今後色設定などもここから読み込むように拡張可能
        "text_color": "#e9ffbd"
    }

    @classmethod
    def load_config(cls):
        if not os.path.exists(cls.CONFIG_FILE):
            return cls.DEFAULT_CONFIG.copy()
        
        try:
            with open(cls.CONFIG_FILE, "r", encoding="utf-8") as f:
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
        with open(cls.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
