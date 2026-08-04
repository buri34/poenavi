from contextlib import contextmanager
from unittest.mock import patch

from PySide6.QtCore import QMimeData

from src.utils.chat_command import send_chat_command
from src.utils.internal_key_input import is_internal_key_input


class FakeClipboard:
    def __init__(self):
        self.current = QMimeData()
        self.current.setText("元の内容")
        self.restored = None

    def mimeData(self):
        return self.current

    def setText(self, text):
        self.current = QMimeData()
        self.current.setText(text)

    def setMimeData(self, mime):
        self.restored = mime


class FakeController:
    def __init__(self):
        self.events = []

    def press(self, key):
        assert is_internal_key_input()
        self.events.append(("press", str(key)))

    def release(self, key):
        assert is_internal_key_input()
        self.events.append(("release", str(key)))

    @contextmanager
    def pressed(self, key):
        self.events.append(("hold", str(key)))
        yield
        self.events.append(("unhold", str(key)))


def test_send_chat_command_pastes_and_restores_clipboard():
    clipboard = FakeClipboard()
    controller = FakeController()

    with patch("src.utils.chat_command.QTimer.singleShot", side_effect=lambda _ms, fn: fn()):
        assert send_chat_command(
            "/exit",
            clipboard=clipboard,
            controller=controller,
            sleep_fn=lambda _seconds: None,
        )

    assert clipboard.restored.text() == "元の内容"
    assert ("press", "v") in controller.events
    assert len([event for event in controller.events if event[0] == "press"]) == 3
