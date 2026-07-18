from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow

from src.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _window(config):
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window.config = config
    return window


def test_area_note_migration_notice_is_shown_and_saved_once(qapp):
    window = _window({})
    message = MagicMock()

    with (
        patch("src.ui.main_window.QMessageBox", return_value=message),
        patch("src.ui.main_window.ConfigManager.save_config") as save_config,
    ):
        window._show_area_note_migration_notice_once()

    message.setWindowTitle.assert_called_once_with("📝 エリアメモ機能について")
    shown_text = message.setText.call_args.args[0]
    assert "各エリアのガイドデータは\n編集できない仕様に変更しました" in shown_text
    assert "PoENaviの自動アップデート機能を正しく動作させるため" in shown_text
    assert "「エリアメモ」機能を実装しました。\n\n大変お手数ですが、以前のガイド" in shown_text
    assert "旧PoENaviフォルダのJSONファイル" in shown_text
    assert "次回以降のアップデートでエリアメモが失われることはありません" in shown_text
    message.exec.assert_called_once_with()
    assert window.config["area_note_migration_notice_shown"] is True
    save_config.assert_called_once_with(window.config)


def test_area_note_migration_notice_is_not_shown_again(qapp):
    window = _window({"area_note_migration_notice_shown": True})

    with (
        patch("src.ui.main_window.QMessageBox") as message_box,
        patch("src.ui.main_window.ConfigManager.save_config") as save_config,
    ):
        window._show_area_note_migration_notice_once()

    message_box.assert_not_called()
    save_config.assert_not_called()
