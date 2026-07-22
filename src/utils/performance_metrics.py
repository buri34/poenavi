"""開発時の性能計測用ヘルパー。"""

import os
from contextlib import contextmanager
from time import perf_counter


@contextmanager
def measure(operation: str):
    """POENAVI_PROFILE=1 のときだけ処理時間を標準出力へ記録する。"""
    if os.environ.get("POENAVI_PROFILE") != "1":
        yield
        return

    started = perf_counter()
    yield
    elapsed_ms = (perf_counter() - started) * 1000
    print(f"[Performance] {operation}: {elapsed_ms:.1f} ms")
