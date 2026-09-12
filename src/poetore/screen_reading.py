"""Shared lifecycle and mutual exclusion for local Windows screen OCR."""

from __future__ import annotations

import threading

from src.poetore.expedition_ocr_probe import WindowsOcrServer


class ScreenReadingCoordinator:
    """Own one OCR helper and allow only one feature scan at a time."""

    def __init__(self, ocr_server=None):
        self.ocr = ocr_server or WindowsOcrServer()
        self._lock = threading.Lock()
        self._owner: str | None = None

    @property
    def owner(self) -> str | None:
        with self._lock:
            return self._owner

    def try_begin(self, owner: str) -> bool:
        with self._lock:
            if self._owner is not None:
                return False
            self._owner = owner
            return True

    def finish(self, owner: str) -> None:
        with self._lock:
            if self._owner == owner:
                self._owner = None

    def start(self) -> None:
        self.ocr.start()

    def recognize(self, images):
        return self.ocr.recognize(images)

    def close(self) -> None:
        with self._lock:
            self._owner = None
        self.ocr.close()
