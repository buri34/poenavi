import pytest
from PySide6.QtCore import QObject, Signal

from src.poetore.poe2.ndlocr_pack import PackStatus
from src.ui.high_accuracy_ocr_pack_group import HighAccuracyOcrPackGroup


class FakePackController(QObject):
    status_changed = Signal(object)

    def __init__(self, status):
        super().__init__()
        self.status = status
        self.retry_count = 0

    def retry(self):
        self.retry_count += 1


def test_shared_pack_group_tracks_progress_ready_and_error_states(qtbot):
    controller = FakePackController(PackStatus("downloading", done=1, total=4))
    group = HighAccuracyOcrPackGroup(controller)
    qtbot.addWidget(group)

    assert group.status_label.text().endswith("25%")
    assert not group.progress_bar.isHidden()
    assert group.progress_bar.value() == 25
    assert group.retry_button.isHidden()

    controller.status = PackStatus("ready")
    controller.status_changed.emit(controller.status)
    assert "利用できます" in group.status_label.text()
    assert group.status_label.property("state") == "success"
    assert not group.progress_bar.isVisible()

    controller.status = PackStatus("error", "network")
    controller.status_changed.emit(controller.status)
    assert "通常の読み取り機能は引き続き利用できます" in group.status_label.text()
    assert group.status_label.property("state") == "warning"
    assert not group.retry_button.isHidden()
    group.retry_button.click()
    assert controller.retry_count == 1


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("checking", "初回のみ高精度OCRパックをダウンロードします"),
        ("idle", "初回のみ高精度OCRパックをダウンロードします"),
        ("installing", "高精度OCRをインストールしています…"),
        ("unavailable", "高精度OCRの状態を確認できません"),
    ],
)
def test_shared_pack_group_covers_all_non_progress_states(qtbot, state, expected):
    group = HighAccuracyOcrPackGroup(FakePackController(PackStatus(state)))
    qtbot.addWidget(group)

    assert expected in group.status_label.text()
    assert group.progress_bar.isHidden()
    assert group.retry_button.isHidden()
