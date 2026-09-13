from unittest.mock import patch

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QImage, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QLabel,
    QScrollArea,
)

from src.ui.expedition_settings_dialog import (
    DEFAULT_EXAMPLE_IMAGE_PATH,
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
    parent = ExpeditionSettingsDialog()
    selector = ExpeditionRegionSelector(QRect(100, 200, 1000, 800), parent)
    selector.show()
    QApplication.processEvents()

    assert selector.font().pixelSize() == 36
    assert selector.font().bold()
    selector.close()
    parent.close()


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
        expedition_config={"region": region},
        screen_reading_enabled=True,
        hotkey="alt+r",
    )

    assert dialog.enabled_checkbox.isChecked()
    assert dialog.hotkey_widget.key_text == "alt+r"
    assert dialog.hotkey_widget.no_modifier_button is not None
    assert dialog.status_label.text() == "設定済み"
    assert dialog.set_region_button.text() == "読取範囲を再設定"
    assert dialog.reset_region_button.isEnabled()
    assert dialog.settings() == (
        {"region": region},
        "alt+r",
        True,
    )

    dialog.reset_region_button.click()
    assert dialog.status_label.text() == "未設定"
    assert dialog.set_region_button.text() == "読取範囲を設定"
    assert not dialog.reset_region_button.isEnabled()
    assert dialog.settings() == ({}, "alt+r", True)
    dialog.close()


def test_expedition_enabled_checkbox_uses_shared_blue_style():
    QApplication.instance() or QApplication([])
    dialog = ExpeditionSettingsDialog()

    assert "poenavi_check_4488ff.png" in dialog.enabled_checkbox.styleSheet()
    dialog.close()


def test_expedition_settings_matches_abyss_grouped_layout():
    QApplication.instance() or QApplication([])
    dialog = ExpeditionSettingsDialog()

    groups = dialog.findChildren(QGroupBox)
    assert [group.title() for group in groups] == [
        "1. 基本設定",
        "2. 読取範囲",
    ]
    assert dialog.findChild(QScrollArea, "expeditionSettingsScroll") is not None

    basic = dialog.findChild(QGroupBox, "basicSettingsGroup")
    ranges = dialog.findChild(QGroupBox, "readRegionsGroup")
    assert basic.isAncestorOf(dialog.enabled_checkbox)
    assert basic.isAncestorOf(dialog.hotkey_widget)
    assert ranges.isAncestorOf(dialog.status_label)
    assert ranges.isAncestorOf(dialog.preview)
    assert ranges.isAncestorOf(dialog.example_thumbnail)
    assert dialog.findChild(QLabel, "expeditionExampleHeading").text() == "指定例"
    dialog.close()


def test_expedition_settings_warns_that_screen_reading_must_be_enabled():
    QApplication.instance() or QApplication([])
    dialog = ExpeditionSettingsDialog()

    hint = dialog.findChild(QLabel, "screenReadingEnableRequiredHint")
    assert hint.text() == "※使用するにはチェックをONにしてください"
    assert "#FFD54F" in dialog.styleSheet()
    assert "font-weight: bold" in dialog.styleSheet()
    dialog.close()


def test_expedition_dialog_accepts_unmodified_hotkey():
    QApplication.instance() or QApplication([])
    dialog = ExpeditionSettingsDialog(hotkey="e")

    assert dialog.hotkey_widget.no_modifier_button.isChecked()
    assert dialog.hotkey_widget.key_text == "e"
    assert dialog.settings()[1] == "e"
    dialog.close()


def test_screen_reading_hotkey_accepts_ctrl_alt_shift_combinations():
    QApplication.instance() or QApplication([])
    dialog = ExpeditionSettingsDialog(hotkey="ctrl+alt+shift+r")

    widget = dialog.hotkey_widget
    assert widget.ctrl_button.isChecked()
    assert widget.alt_button.isChecked()
    assert widget.shift_button.isChecked()
    assert not widget.no_modifier_button.isChecked()
    assert widget.key_text == "ctrl+alt+shift+r"

    widget.no_modifier_button.click()
    assert widget.key_text == "r"
    widget.ctrl_button.click()
    widget.shift_button.click()
    assert widget.key_text == "ctrl+shift+r"
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
    assert missing.example_hint_label.text() == (
        "※以下の画像をクリックするとポップアップで拡大表示します"
    )
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


def test_packaged_expedition_example_image_is_available():
    QApplication.instance() or QApplication([])
    assert DEFAULT_EXAMPLE_IMAGE_PATH.is_file()

    dialog = ExpeditionSettingsDialog()
    assert dialog.example_thumbnail.pixmap() is not None
    assert not dialog.example_thumbnail.pixmap().isNull()
    assert dialog.example_thumbnail.toolTip() == "クリックして拡大"
    dialog.close()


def test_expedition_dialog_warns_that_window_resize_requires_region_reset():
    dialog = ExpeditionSettingsDialog()
    warning = dialog.findChild(QLabel, "screenSizeRegionWarning")
    assert warning.text() == (
        "PoE2のウィンドウサイズを変更した場合、位置が変わるため再設定が必要です。"
    )
    assert "#FFD54F" in dialog.styleSheet()
    dialog.close()
