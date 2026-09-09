from unittest.mock import patch

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QImage, QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog

from src.ui.expedition_settings_dialog import (
    ExpeditionRegionSelector,
    ExpeditionSettingsDialog,
    normalized_region,
    valid_normalized_region,
)


def test_normalized_region_uses_poe_client_coordinates():
    client = QRect(100, 200, 1000, 800)
    selection = QRect(200, 280, 600, 640)

    assert normalized_region(selection, client) == {
        "left": 0.1,
        "top": 0.1,
        "right": 0.7,
        "bottom": 0.9,
    }


def test_normalized_region_rejects_tiny_and_outside_selections():
    client = QRect(100, 200, 1000, 800)

    assert normalized_region(QRect(110, 210, 20, 20), client) is None
    assert normalized_region(QRect(50, 250, 300, 300), client) is None
    assert valid_normalized_region({
        "left": 0.2, "top": 0.2, "right": 1.1, "bottom": 0.8,
    }) is None


def test_region_selector_enter_confirms_valid_selection_and_escape_cancels():
    QApplication.instance() or QApplication([])
    selector = ExpeditionRegionSelector(QRect(100, 200, 1000, 800))
    selector._selection = QRect(100, 80, 600, 640)

    selector.keyPressEvent(QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key_Return, Qt.NoModifier
    ))
    assert selector.result() == QDialog.Accepted

    cancelled = ExpeditionRegionSelector(QRect(100, 200, 1000, 800))
    cancelled.keyPressEvent(QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key_Escape, Qt.NoModifier
    ))
    assert cancelled.result() == QDialog.Rejected
    selector.close()
    cancelled.close()


def test_region_selector_uses_large_bold_guide_font():
    QApplication.instance() or QApplication([])
    selector = ExpeditionRegionSelector(QRect(100, 200, 1000, 800))

    assert selector.font().pixelSize() == 36
    assert selector.font().bold()
    selector.close()


def test_region_selector_rejects_tiny_selection():
    QApplication.instance() or QApplication([])
    selector = ExpeditionRegionSelector(QRect(100, 200, 1000, 800))
    selector._selection = QRect(10, 10, 20, 20)

    with patch(
        "src.ui.expedition_settings_dialog.QMessageBox.warning"
    ) as warning:
        selector.keyPressEvent(QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key_Return, Qt.NoModifier
        ))

    assert selector.result() != QDialog.Accepted
    warning.assert_called_once()
    selector.close()


def test_expedition_dialog_saves_status_hotkey_and_region():
    QApplication.instance() or QApplication([])
    region = {"left": 0.05, "top": 0.15, "right": 0.55, "bottom": 0.95}
    dialog = ExpeditionSettingsDialog(
        expedition_config={"enabled": True, "region": region},
        hotkey="alt+r",
    )

    assert dialog.enabled_checkbox.isChecked()
    assert dialog.hotkey_widget.key_text == "alt+r"
    assert dialog.status_label.text() == "設定済み"
    assert dialog.set_region_button.text() == "読取範囲を再設定"
    assert dialog.reset_region_button.isEnabled()
    assert dialog.settings() == (
        {"enabled": True, "region": region},
        "alt+r",
    )

    dialog.reset_region_button.click()
    assert dialog.status_label.text() == "未設定"
    assert dialog.set_region_button.text() == "読取範囲を設定"
    assert not dialog.reset_region_button.isEnabled()
    assert dialog.settings() == ({"enabled": True}, "alt+r")
    dialog.close()


def test_expedition_dialog_accepts_region_from_selector():
    QApplication.instance() or QApplication([])
    region = {"left": 0.1, "top": 0.2, "right": 0.6, "bottom": 0.9}
    selection_opacities = []

    class AcceptedSelector:
        def __init__(self, client_rect, parent):
            self.selected_region = region
            self.parent = parent

        def exec(self):
            selection_opacities.append((
                self.parent.windowOpacity(),
                self.parent.parentWidget().windowOpacity(),
            ))
            return QDialog.Accepted

    owner = QDialog()
    owner.setWindowOpacity(0.75)
    dialog = ExpeditionSettingsDialog(
        owner,
        client_rect_getter=lambda: QRect(100, 200, 1000, 800),
        selector_class=AcceptedSelector,
    )

    dialog.set_region_button.click()

    assert dialog.settings()[0]["region"] == region
    assert dialog.status_label.text() == "設定済み"
    assert selection_opacities == [(0.0, 0.0)]
    assert dialog.windowOpacity() == 1.0
    assert abs(owner.windowOpacity() - 0.75) < 0.01
    dialog.close()
    owner.close()


def test_region_selection_keeps_modal_settings_dialog_open():
    QApplication.instance() or QApplication([])
    region = {"left": 0.1, "top": 0.2, "right": 0.6, "bottom": 0.9}

    class AcceptedSelector:
        def __init__(self, client_rect, parent):
            self.selected_region = region

        def exec(self):
            return QDialog.Accepted

    dialog = ExpeditionSettingsDialog(
        client_rect_getter=lambda: QRect(100, 200, 1000, 800),
        selector_class=AcceptedSelector,
    )
    QTimer.singleShot(0, dialog.set_region_button.click)
    QTimer.singleShot(50, dialog.accept)

    assert dialog.exec() == QDialog.Accepted
    assert dialog.settings()[0]["region"] == region


def test_expedition_dialog_shows_example_or_clear_placeholder(tmp_path):
    QApplication.instance() or QApplication([])
    missing = ExpeditionSettingsDialog(example_image_path=tmp_path / "missing.png")
    assert "準備中" in missing.example_thumbnail.text()
    missing.close()

    image_path = tmp_path / "example.png"
    image = QImage(320, 180, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    available = ExpeditionSettingsDialog(example_image_path=image_path)
    assert available.example_thumbnail.pixmap() is not None
    assert not available.example_thumbnail.pixmap().isNull()
    assert available.example_thumbnail.toolTip() == "クリックして拡大"
    available.close()
