from unittest.mock import MagicMock, patch

from src.ui.main_window import MainWindow
from src.utils.poe_version_data import POE2


def _window(config):
    window = MagicMock()
    window.config = config
    window.poe_version = POE2
    window.timer_size = "large"
    window.TIMER_SIZES = {"small": {}, "medium": {}, "large": {}}
    window.panel_registry = {}
    window.current_zone = None
    window.gem_tracker_expanded = False
    window.mini_navi_overlay = MagicMock()
    window.act4_checklist_window = MagicMock()
    window.stash_tab_scroll = MagicMock()
    window.log_watcher = MagicMock()
    window.guide_text_label = MagicMock()
    window.map_thumbnail = MagicMock()
    window._effective_timer_size.return_value = "large"
    window._is_panel_detached.return_value = False
    return window


def _run_open_settings(
    window,
    new_settings,
    *,
    accepted=True,
    zone_data_changed=False,
    guide_data_changed=False,
):
    dialog = MagicMock()
    dialog.exec.return_value = accepted
    dialog.get_settings.return_value = new_settings
    dialog.zone_data_changed = zone_data_changed
    dialog.guide_data_changed = guide_data_changed
    patches = (
        patch("src.ui.main_window.SettingsDialog", return_value=dialog),
        patch("src.ui.main_window.ConfigManager.save_config"),
        patch(
            "src.windows_autostart.sync_windows_poetore_autostart_with_error",
            return_value=None,
        ),
        patch("src.app_restart.confirm_mode_switch_restart", return_value=False),
        patch("src.ui.main_window.load_zone_master_data", return_value={
            "zone_data_by_version": {POE2: {}},
            "town_zones_by_version": {POE2: set()},
        }),
        patch("src.ui.main_window.load_guide_data", return_value={}),
    )
    entered = [item.start() for item in patches]
    try:
        MainWindow.open_settings(window)
    finally:
        for item in reversed(patches):
            item.stop()
    return {
        "autostart": entered[2],
        "zone_data": entered[4],
        "guide_data": entered[5],
    }


def test_font_only_change_skips_unrelated_runtime_reconfiguration():
    original = {
        "poe_version": POE2,
        "mini_guide_overlay": {"font_size": 18, "topmost_mode": "poe_only"},
        "startup": {"windows_autostart_poetore": False},
        "hotkeys": {"start_stop": "F7"},
        "custom_commands": [],
        "client_log_paths": {POE2: "C:/PoE2/Client.txt"},
        "voicevox": {"enabled": False},
        "timer_size": "large",
    }
    window = _window(original)
    updated = dict(original)
    updated["mini_guide_overlay"] = {
        "font_size": 22,
        "topmost_mode": "poe_only",
    }

    calls = _run_open_settings(window, updated)

    window._apply_mini_navi_related_settings.assert_called_once_with("poe_only")
    calls["autostart"].assert_not_called()
    window.register_hotkeys.assert_not_called()
    window.log_watcher.set_log_path.assert_not_called()
    window.log_watcher.start.assert_not_called()
    window._sync_voicevox_service.assert_not_called()
    calls["zone_data"].assert_not_called()


def test_changed_runtime_categories_are_reconfigured():
    original = {
        "poe_version": POE2,
        "mini_guide_overlay": {"font_size": 18, "topmost_mode": "poe_only"},
        "startup": {"windows_autostart_poetore": False},
        "hotkeys": {"start_stop": "F7"},
        "custom_commands": [],
        "client_log_paths": {POE2: "C:/old/Client.txt"},
        "voicevox": {"enabled": False},
        "timer_size": "large",
    }
    window = _window(original)
    updated = dict(original)
    updated.update({
        "startup": {"windows_autostart_poetore": True},
        "hotkeys": {"start_stop": "F9"},
        "client_log_paths": {POE2: "C:/new/Client.txt"},
        "voicevox": {"enabled": True},
    })

    calls = _run_open_settings(window, updated)

    calls["autostart"].assert_called_once_with(window.config)
    window.register_hotkeys.assert_called_once()
    window.log_watcher.set_log_path.assert_called_once_with("C:/new/Client.txt")
    window._sync_voicevox_service.assert_called_once()


def test_edited_zone_master_is_reloaded_without_other_runtime_reconfiguration():
    original = {
        "poe_version": POE2,
        "mini_guide_overlay": {"font_size": 18, "topmost_mode": "poe_only"},
        "startup": {"windows_autostart_poetore": False},
        "hotkeys": {"start_stop": "F7"},
        "custom_commands": [],
        "client_log_paths": {POE2: "C:/PoE2/Client.txt"},
        "voicevox": {"enabled": False},
        "timer_size": "large",
    }
    window = _window(original)

    calls = _run_open_settings(
        window,
        dict(original),
        zone_data_changed=True,
    )

    calls["zone_data"].assert_called_once()
    window.register_hotkeys.assert_not_called()
    window.log_watcher.set_log_path.assert_not_called()
    window._sync_voicevox_service.assert_not_called()


def test_edited_guide_is_reloaded_even_when_settings_dialog_is_cancelled():
    original = {
        "poe_version": POE2,
        "mini_guide_overlay": {"font_size": 18, "topmost_mode": "poe_only"},
    }
    window = _window(original)
    window.current_zone = "キンの島"
    window._get_zone_id.return_value = "poe2_act4_area1"
    window.zone_visit_counts = {}

    calls = _run_open_settings(
        window,
        {},
        accepted=False,
        guide_data_changed=True,
    )

    calls["guide_data"].assert_called_once_with(POE2)
    window._update_guide_and_map.assert_called_once()
    window.register_hotkeys.assert_not_called()
