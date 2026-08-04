from src.ui.custom_command_settings import custom_command_hotkeys, normalized_custom_commands
from src.ui.custom_command_settings import CustomCommandSettingsWidget
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from src.ui.app_theme import POETORE_THEME
from src.ui.settings_dialog import HotkeyButton


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


def test_custom_command_hotkey_cell_captures_keys_and_uses_requested_theme():
    QApplication.instance() or QApplication([])
    widget = CustomCommandSettingsWidget(
        [{"enabled": True, "name": "隠れ家", "hotkey": "F11", "command": "/hideout"}],
        theme=POETORE_THEME,
    )
    button = widget.table.cellWidget(0, 2)
    assert isinstance(button, HotkeyButton)
    assert widget.table.rowHeight(0) >= CustomCommandSettingsWidget.ROW_HEIGHT
    button.setChecked(True)
    assert button.text() == "Press any key..."
    button.keyPressEvent(QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier,
    ))
    assert widget.commands()[0]["hotkey"] == "Ctrl+H"
    assert POETORE_THEME.background in widget.table.styleSheet()
    assert POETORE_THEME.accent in widget.table.styleSheet()
