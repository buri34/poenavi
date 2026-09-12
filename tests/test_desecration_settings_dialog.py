from PySide6.QtCore import QRect

from src.ui.desecration_settings_dialog import DesecrationSettingsDialog


def test_desecration_settings_defaults_to_alt_r_and_keeps_open_region_optional(qtbot):
    dialog = DesecrationSettingsDialog(
        screen_reading_enabled=True,
        client_rect_getter=lambda: QRect(0, 0, 1920, 1080),
    )
    qtbot.addWidget(dialog)
    config, hotkey, enabled = dialog.settings()
    assert hotkey == "alt+r"
    assert enabled is True
    assert "inventory_open_region" not in config
    assert "読取ショートカットは無効" in dialog._section_widgets["inventory_open_region"][0].text()


def test_desecration_settings_preserves_two_independent_regions(qtbot):
    opened = {"left": .2, "top": .1, "right": .7, "bottom": .5}
    closed = {"left": .3, "top": .2, "right": .8, "bottom": .6}
    dialog = DesecrationSettingsDialog(
        desecration_config={
            "inventory_open_region": opened,
            "inventory_closed_region": closed,
        },
    )
    qtbot.addWidget(dialog)
    config, _hotkey, _enabled = dialog.settings()
    assert config["inventory_open_region"] == opened
    assert config["inventory_closed_region"] == closed
