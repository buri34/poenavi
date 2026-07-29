import pytest
from PySide6.QtWidgets import QApplication

from src.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_settings_can_restore_mode_selector_without_changing_preferred_mode(monkeypatch, qapp):
    monkeypatch.setattr("src.ui.settings_dialog.save_zone_master_data", lambda *_args: None)
    dialog = SettingsDialog(current_config={
        "startup": {
            "preferred_mode": "poetore",
            "show_mode_selector": False,
        }
    })

    assert not dialog.show_mode_selector_cb.isChecked()
    assert dialog.preferred_mode_combo.currentData() == "poetore"
    dialog.show_mode_selector_cb.setChecked(True)
    dialog.preferred_mode_combo.setCurrentIndex(
        dialog.preferred_mode_combo.findData("poenavi")
    )
    settings = dialog.get_settings()

    assert settings["startup"] == {
        "preferred_mode": "poenavi",
        "show_mode_selector": True,
    }
    dialog.close()
