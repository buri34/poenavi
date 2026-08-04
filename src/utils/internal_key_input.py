"""アプリ自身が送信したキー入力をグローバルホットキーから除外する。"""

from contextlib import contextmanager
from threading import RLock
from time import monotonic


_lock = RLock()
_depth = 0
_suppress_until = 0.0


def is_internal_key_input() -> bool:
    """内部送信中または直後ならTrueを返す。"""
    with _lock:
        return _depth > 0 or monotonic() < _suppress_until


@contextmanager
def internal_key_input(*, cooldown_seconds: float = 0.12):
    """この区間のpynput入力をホットキー操作として扱わせない。"""
    global _depth, _suppress_until
    with _lock:
        _depth += 1
    try:
        yield
    finally:
        with _lock:
            _depth = max(0, _depth - 1)
            _suppress_until = max(
                _suppress_until,
                monotonic() + max(0.0, float(cooldown_seconds)),
            )
