from PySide6.QtWidgets import QApplication

from src.ui.poetore_settings_dialog import PoetoreSettingsDialog


def test_poetore_settings_contains_only_common_and_trade_controls():
    QApplication.instance() or QApplication([])
    dialog = PoetoreSettingsDialog(
        current_config={
            "startup": {
                "preferred_mode": "poetore",
                "show_mode_selector": False,
            },
            "hotkeys": {"start_stop": "F7", "poetore_capture": "alt+d"},
            "poetore": {"league": "auto"},
        }
    )

    assert "#DB86EF" in dialog.styleSheet()
    assert not hasattr(dialog, "log_path_edits")
    assert not hasattr(dialog, "timer_size_combo")
    assert dialog.preferred_mode_combo.currentData() == "poetore"
    dialog.preferred_mode_combo.setCurrentIndex(
        dialog.preferred_mode_combo.findData("poenavi")
    )
    settings = dialog.get_settings()
    assert settings["startup"]["preferred_mode"] == "poenavi"
    assert settings["hotkeys"]["start_stop"] == "F7"
    assert settings["hotkeys"]["poetore_capture"] == "alt+d"
    dialog.close()
