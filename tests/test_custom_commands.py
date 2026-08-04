from src.ui.custom_command_settings import custom_command_hotkeys, normalized_custom_commands
from src.ui.custom_command_settings import CustomCommandSettingsWidget
from PySide6.QtWidgets import QApplication


def test_custom_commands_normalize_and_register_only_enabled_valid_rows():
    commands = normalized_custom_commands([
        {"enabled": True, "name": "隠れ家", "hotkey": "Ctrl+H", "command": "/hideout"},
        {"enabled": False, "name": "終了", "hotkey": "Ctrl+E", "command": "/exit"},
        {"enabled": True, "name": "不正", "hotkey": "F9", "command": "hello"},
    ])
    assert custom_command_hotkeys(commands) == {"custom_command:0": "Ctrl+H"}


def test_custom_command_widget_round_trips_rows():
    QApplication.instance() or QApplication([])
    source = [{"enabled": True, "name": "隠れ家", "hotkey": "Ctrl+H", "command": "/hideout"}]
    widget = CustomCommandSettingsWidget(source)
    assert widget.commands() == source
