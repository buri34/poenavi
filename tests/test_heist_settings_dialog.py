from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel

from src.poetore.poe2.ndlocr_pack import PackStatus
from src.ui.dialog_theme import POETORE_DIALOG_THEME
from src.ui.heist_settings_dialog import (
    DEFAULT_EXAMPLE_IMAGE_PATH,
    HeistSettingsDialog,
)


class FakePackController(QObject):
    status_changed = Signal(object)

    def __init__(self, status):
        super().__init__()
        self.status = status
        self.retry_count = 0

    def retry(self):
        self.retry_count += 1


def test_heist_settings_reuses_poetore_dialog_structure_and_defaults():
    QApplication.instance() or QApplication([])
    dialog = HeistSettingsDialog()
    try:
        assert dialog.windowTitle() == "ハイスト報酬OCR設定"
        assert dialog.theme == POETORE_DIALOG_THEME
        assert not dialog.enabled_checkbox.isChecked()
        assert dialog.hotkey_widget.key_text == "alt+e"
        assert not dialog.keep_high_accuracy_checkbox.isChecked()
        assert dialog.settings() == ("alt+e", False, False)
        assert dialog.findChild(QGroupBox, "basicSettingsGroup") is not None
        assert dialog.findChild(QGroupBox, "highAccuracyOcrGroup") is not None
        assert dialog.findChild(QGroupBox, "readMethodGroup") is not None
        assert [group.title() for group in dialog.findChildren(QGroupBox)] == [
            "1. 基本設定",
            "2. 高精度OCR",
            "3. 読み取り方法",
        ]
        assert dialog.cancel_button.property("buttonRole") == "secondary"
        assert dialog.save_button.property("buttonRole") == "primary"
    finally:
        dialog.close()


def test_heist_settings_shares_pack_download_progress_and_retry_ui(qtbot):
    controller = FakePackController(PackStatus("downloading", done=1, total=2))
    dialog = HeistSettingsDialog(ocr_pack_controller=controller)
    qtbot.addWidget(dialog)

    assert dialog.ocr_pack_status.text().endswith("50%")
    assert not dialog.ocr_pack_progress.isHidden()

    controller.status = PackStatus("error", "network")
    controller.status_changed.emit(controller.status)
    assert "通常の読み取り機能は引き続き利用できます" in dialog.ocr_pack_status.text()
    assert not dialog.ocr_pack_retry.isHidden()
    dialog.ocr_pack_retry.click()
    assert controller.retry_count == 1


def test_heist_settings_shows_manual_selection_example():
    QApplication.instance() or QApplication([])
    dialog = HeistSettingsDialog(enabled=True, hotkey="ctrl+h")
    try:
        assert Path(DEFAULT_EXAMPLE_IMAGE_PATH).is_file()
        assert not dialog.example_thumbnail.pixmap().isNull()
        source = dialog.example_thumbnail.pixmap()
        assert source.width() > 250
        assert source.height() > 100
        assert "報酬名・ベースタイプ・青いMod全体" in dialog.findChild(
            QLabel, "heistSelectionInstruction"
        ).text()
        assert "自動で確定" in dialog.findChild(
            QLabel, "heistSelectionInstruction"
        ).text()
        assert "Enter" not in dialog.findChild(
            QLabel, "heistSelectionInstruction"
        ).text()
        assert dialog.settings() == ("ctrl+h", True, False)
    finally:
        dialog.close()


def test_heist_settings_can_keep_high_accuracy_ocr_ready():
    QApplication.instance() or QApplication([])
    dialog = HeistSettingsDialog(
        enabled=True,
        hotkey="ctrl+h",
        keep_high_accuracy_ready=True,
    )
    try:
        assert dialog.keep_high_accuracy_checkbox.isChecked()
        assert dialog.keep_high_accuracy_checkbox.text() == (
            "高精度OCRをあらかじめ起動しておく"
        )
        assert "約1GB" in dialog.keep_high_accuracy_hint.text()
        assert "すぐに開始" in dialog.keep_high_accuracy_hint.text()
        assert "必要なときだけ起動" in dialog.keep_high_accuracy_off_hint.text()
        assert "メモリ消費を抑えられます" in dialog.keep_high_accuracy_off_hint.text()
        assert "10～15秒" in dialog.keep_high_accuracy_off_hint.text()
        assert "180秒後に自動終了" in dialog.keep_high_accuracy_off_hint.text()
        assert "今までどおり" not in dialog.keep_high_accuracy_off_hint.text()
        assert dialog.settings() == ("ctrl+h", True, True)
    finally:
        dialog.close()
