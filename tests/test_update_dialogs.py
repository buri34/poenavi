import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QTextBrowser

from src.ui.update_dialogs import UpdateAvailableDialog
from src.update.release_client import ReleaseInfo


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_update_notes_render_markdown_with_external_links(qapp):
    release = ReleaseInfo(
        "2.6.3",
        "**Release notes**\n\n- Fixed labels\n\n"
        "https://github.com/fuubox/poenavi-localisation/releases/tag/v2.6.3",
        "https://github.com/fuubox/poenavi-localisation/releases/tag/v2.6.3",
        "https://github.com/fuubox/poenavi-localisation/PoENavi.zip",
        "https://github.com/fuubox/poenavi-localisation/PoENavi.zip.sha256",
    )
    dialog = UpdateAvailableDialog(release, auto_update_supported=True)
    try:
        notes = dialog.findChild(QTextBrowser)

        assert notes is not None
        assert "**Release notes**" not in notes.toPlainText()
        assert "Release notes" in notes.toPlainText()
        assert "<a href=" in notes.toHtml()
        assert notes.openExternalLinks()
    finally:
        dialog.close()
