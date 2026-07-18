import json


def test_alt_d_is_default_poetore_capture_hotkey():
    with open("default_config.json", encoding="utf-8") as file:
        config = json.load(file)
    assert config["hotkeys"]["poetore_capture"] == "alt+d"
