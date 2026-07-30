import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from src.ui import app_info_widget
from src.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_patreon_support_button_opens_configured_url(monkeypatch, qapp):
    opened_urls = []
    monkeypatch.setattr(app_info_widget.webbrowser, "open", opened_urls.append)
    dialog = SettingsDialog(current_config={})

    buttons = {
        button.text(): button
        for button in dialog.findChildren(QPushButton)
    }
    assert "OFUSE（おふせ）で応援する" in buttons
    assert "Ko-fi で応援する" in buttons
    assert "Patreon で応援する" in buttons

    buttons["Patreon で応援する"].click()

    assert opened_urls == ["https://www.patreon.com/cw/Buri8857"]
    dialog.close()
