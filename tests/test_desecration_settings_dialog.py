from PySide6.QtCore import QRect
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from src.ui.desecration_settings_dialog import (
    DEFAULT_EXAMPLE_IMAGE_PATH,
    EXAMPLE_POPUP_IMAGE_SIZE,
    EXAMPLE_POPUP_SIZE,
    DesecrationSettingsDialog,
)


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


def test_desecration_settings_saves_optional_tier_ranges(qtbot):
    dialog = DesecrationSettingsDialog()
    qtbot.addWidget(dialog)
    assert not dialog.show_ranges_checkbox.isChecked()
    dialog.show_ranges_checkbox.setChecked(True)
    assert dialog.settings()[0]["show_tier_ranges"] is True


def test_desecration_settings_explains_required_and_closed_regions(qtbot):
    dialog = DesecrationSettingsDialog()
    qtbot.addWidget(dialog)
    required = dialog.findChild(QLabel, "desecrationRequiredLabel")
    closed_note = dialog.findChild(QLabel, "desecrationClosedRegionNote")
    instruction = dialog.findChild(QLabel, "desecrationRegionInstruction")
    warning = dialog.findChild(QLabel, "screenSizeRegionWarning")
    assert required.text() == "（必須）"
    assert "#FFD54F" in dialog.styleSheet()
    assert closed_note.text() == "※インベントリを閉じると位置がずれて読取に失敗するため"
    assert instruction.text().endswith(
        "読取時は「インベントリを開いた状態」を先に確認し、読取に失敗した場合は"
        "「閉じた状態」を確認します。"
    )
    assert warning.text() == (
        "PoE2のウィンドウサイズを変更した場合、位置が変わるため再設定が必要です。"
    )


def test_desecration_settings_warns_that_screen_reading_must_be_enabled(qtbot):
    dialog = DesecrationSettingsDialog()
    qtbot.addWidget(dialog)

    hint = dialog.findChild(QLabel, "screenReadingEnableRequiredHint")
    assert hint.text() == "※使用するにはチェックをONにしてください"
    assert "#FFD54F" in dialog.styleSheet()
    assert "font-weight: bold" in dialog.styleSheet()


def test_desecration_default_example_image_is_bundled_and_loadable():
    QApplication.instance() or QApplication([])
    pixmap = QPixmap(str(DEFAULT_EXAMPLE_IMAGE_PATH))

    assert DEFAULT_EXAMPLE_IMAGE_PATH.is_file()
    assert not pixmap.isNull()
    assert pixmap.width() == 2577
    assert pixmap.height() == 698


def test_desecration_example_popup_image_is_one_and_a_half_times_larger(
    qtbot, monkeypatch
):
    captured = {}

    def capture_popup(popup):
        captured["popup"] = popup
        return QDialog.Rejected

    monkeypatch.setattr(QDialog, "exec", capture_popup)
    dialog = DesecrationSettingsDialog()
    qtbot.addWidget(dialog)

    dialog._show_example_popup()

    popup = captured["popup"]
    image = popup.findChild(QLabel, "desecrationExamplePopupImage")
    assert popup.size() == EXAMPLE_POPUP_SIZE
    assert EXAMPLE_POPUP_IMAGE_SIZE.width() == 860 * 1.5
    assert EXAMPLE_POPUP_IMAGE_SIZE.height() == 630 * 1.5
    assert image.pixmap().width() == 1290
