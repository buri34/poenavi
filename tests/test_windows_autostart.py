from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
from src.app_mode import POETORE_MODE
from src.ui.main_window import MainWindow
from src.ui.poetore_mode_window import PoetoreModeWindow
from src.windows_autostart import (
    REGISTRY_PATH,
    REGISTRY_VALUE_NAME,
    WINDOWS_STARTUP_POETORE_ARGUMENT,
    build_windows_poetore_autostart_command,
    consume_windows_startup_poetore_argument,
    sync_windows_poetore_autostart,
    sync_windows_poetore_autostart_with_error,
)


class FakeRegistry:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    def CreateKeyEx(self, root, path, _reserved, access):
        assert (root, path, access) == ("HKCU", REGISTRY_PATH, self.KEY_SET_VALUE)
        return nullcontext("run-key")

    def OpenKey(self, root, path, _reserved, access):
        assert (root, path, access) == ("HKCU", REGISTRY_PATH, self.KEY_SET_VALUE)
        return nullcontext("run-key")

    def SetValueEx(self, key, name, _reserved, kind, value):
        assert (key, kind) == ("run-key", self.REG_SZ)
        self.values[name] = value

    def DeleteValue(self, key, name):
        assert key == "run-key"
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_internal_windows_startup_argument_is_consumed():
    arguments = ["PoENavi.exe", WINDOWS_STARTUP_POETORE_ARGUMENT, "--sample"]

    assert consume_windows_startup_poetore_argument(arguments) is True
    assert arguments == ["PoENavi.exe", "--sample"]


def test_windows_run_command_quotes_executable_and_forces_poetore():
    command = build_windows_poetore_autostart_command(
        Path(r"C:\PoE Tools\PoENavi.exe")
    )

    assert command == (
        r'"C:\PoE Tools\PoENavi.exe" --windows-startup-poetore'
    )


def test_enabled_setting_registers_current_packaged_executable():
    registry = FakeRegistry()

    assert sync_windows_poetore_autostart(
        {"startup": {"windows_autostart_poetore": True}},
        executable=r"D:\PoENavi\PoENavi.exe",
        platform="win32",
        frozen=True,
        registry=registry,
    ) is True
    assert registry.values[REGISTRY_VALUE_NAME] == (
        r"D:\PoENavi\PoENavi.exe --windows-startup-poetore"
    )

    sync_windows_poetore_autostart(
        {"startup": {"windows_autostart_poetore": True}},
        executable=r"E:\Moved PoENavi\PoENavi.exe",
        platform="win32",
        frozen=True,
        registry=registry,
    )
    assert registry.values[REGISTRY_VALUE_NAME] == (
        r'"E:\Moved PoENavi\PoENavi.exe" --windows-startup-poetore'
    )


def test_disabled_setting_removes_existing_registration():
    registry = FakeRegistry()
    registry.values[REGISTRY_VALUE_NAME] = "old command"

    assert sync_windows_poetore_autostart(
        {"startup": {"windows_autostart_poetore": False}},
        platform="win32",
        frozen=True,
        registry=registry,
    ) is True
    assert REGISTRY_VALUE_NAME not in registry.values


def test_development_and_non_windows_runs_do_not_touch_registry():
    registry = FakeRegistry()
    config = {"startup": {"windows_autostart_poetore": True}}

    assert sync_windows_poetore_autostart(
        config, platform="darwin", frozen=True, registry=registry
    ) is False
    assert sync_windows_poetore_autostart(
        config, platform="win32", frozen=False, registry=registry
    ) is False
    assert registry.values == {}


def test_windows_startup_launch_forces_poetore_without_changing_preferences():
    config = {
        "poe_version": "poe2",
        "poe_version_mode": "ask",
        "startup": {
            "preferred_mode": "poenavi",
            "show_mode_selector": True,
            "windows_autostart_poetore": True,
        },
    }

    selected, mode = main.select_startup_options(config, force_poetore=True)

    assert selected == config
    assert mode == POETORE_MODE


def test_registry_error_is_returned_without_crashing(monkeypatch):
    def fail(_config):
        raise PermissionError("denied")

    monkeypatch.setattr(
        "src.windows_autostart.sync_windows_poetore_autostart",
        fail,
    )

    assert sync_windows_poetore_autostart_with_error({}) == "denied"


def test_poetore_settings_save_syncs_windows_registration():
    window = MagicMock()
    window.config = {}
    window.poe_version = "poe2"
    dialog = MagicMock()
    dialog.exec.return_value = True
    dialog.get_settings.return_value = {
        "startup": {"windows_autostart_poetore": True}
    }

    with patch(
        "src.ui.poetore_settings_dialog.PoetoreSettingsDialog",
        return_value=dialog,
    ), patch(
        "src.ui.poetore_mode_window.ConfigManager.save_config"
    ), patch(
        "src.windows_autostart.sync_windows_poetore_autostart_with_error",
        return_value=None,
    ) as sync, patch(
        "src.app_restart.confirm_mode_switch_restart",
        return_value=True,
    ):
        PoetoreModeWindow.open_settings(window)

    sync.assert_called_once_with(window.config)


def test_poenavi_settings_save_syncs_windows_registration():
    window = MagicMock()
    window.config = {}
    window.poe_version = "poe2"
    dialog = MagicMock()
    dialog.exec.return_value = True
    dialog.get_settings.return_value = {
        "startup": {"windows_autostart_poetore": True}
    }

    with patch(
        "src.ui.main_window.SettingsDialog",
        return_value=dialog,
    ), patch(
        "src.ui.main_window.ConfigManager.save_config"
    ), patch(
        "src.windows_autostart.sync_windows_poetore_autostart_with_error",
        return_value=None,
    ) as sync, patch(
        "src.app_restart.confirm_mode_switch_restart",
        return_value=True,
    ):
        MainWindow.open_settings(window)

    sync.assert_called_once_with(window.config)
