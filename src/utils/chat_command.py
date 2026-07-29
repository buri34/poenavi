"""PoEチャットコマンド送信の共通実装。"""

import time

from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtWidgets import QApplication


def clone_clipboard_mime_data(source):
    clone = QMimeData()
    if source is None:
        return clone
    for fmt in source.formats():
        clone.setData(fmt, source.data(fmt))
    if source.hasText():
        clone.setText(source.text())
    if source.hasHtml():
        clone.setHtml(source.html())
    if source.hasUrls():
        clone.setUrls(source.urls())
    if source.hasImage():
        clone.setImageData(source.imageData())
    if source.hasColor():
        clone.setColorData(source.colorData())
    return clone


def send_chat_command(command, *, clipboard=None, controller=None, sleep_fn=time.sleep):
    """IME状態に依存しないよう、クリップボード経由でPoEチャットへ送る。"""
    if not command:
        return False
    try:
        from pynput import keyboard

        clipboard = clipboard or QApplication.clipboard()
        original_mime = clone_clipboard_mime_data(clipboard.mimeData())
        clipboard.setText(command)
        controller = controller or keyboard.Controller()

        def tap(key):
            controller.press(key)
            controller.release(key)

        tap(keyboard.Key.enter)
        sleep_fn(0.05)
        with controller.pressed(keyboard.Key.ctrl):
            tap("v")
        sleep_fn(0.05)
        tap(keyboard.Key.enter)
        QTimer.singleShot(500, lambda: clipboard.setMimeData(original_mime))
        return True
    except Exception as exc:
        print(f"[CHAT COMMAND] Failed: {exc}")
        return False
