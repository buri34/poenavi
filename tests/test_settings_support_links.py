import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from src.ui import settings_dialog
from src.ui.settings_dialog import SettingsDialog
from src.utils.i18n import tr_ui


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_patreon_support_button_opens_configured_url(monkeypatch, qapp):
    opened_urls = []
    monkeypatch.setattr(settings_dialog.webbrowser, "open", opened_urls.append)
    dialog = SettingsDialog(current_config={})

    buttons = {
        button.text(): button
        for button in dialog.findChildren(QPushButton)
    }
    assert tr_ui("OFUSE（おふせ）で応援する") in buttons
    assert tr_ui("Ko-fi で応援する") in buttons
    assert tr_ui("Patreon で応援する") in buttons

    buttons[tr_ui("Patreon で応援する")].click()

    assert opened_urls == ["https://www.patreon.com/cw/Buri8857"]
    dialog.close()
