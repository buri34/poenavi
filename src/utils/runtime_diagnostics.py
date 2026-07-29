"""モード別起動リソースを比較するための軽量診断。"""

from dataclasses import dataclass
import os
import sys
import threading
from time import perf_counter


@dataclass(frozen=True)
class RuntimeSnapshot:
    mode: str
    startup_ms: float
    memory_mib: float | None
    threads: int
    modules: int
    services: tuple[str, ...]


def _process_memory_mib() -> float | None:
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            process = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(
                process, ctypes.byref(counters), counters.cb
            ):
                return counters.WorkingSetSize / (1024 * 1024)
        except Exception:
            return None
        return None

    try:
        import resource

        maximum = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform == "darwin":
            return maximum / (1024 * 1024)
        return maximum / 1024
    except Exception:
        return None


def capture_runtime_snapshot(mode: str, started_at: float, window) -> RuntimeSnapshot:
    services = tuple(sorted(getattr(window, "active_service_names", ())))
    return RuntimeSnapshot(
        mode=mode,
        startup_ms=(perf_counter() - started_at) * 1000,
        memory_mib=_process_memory_mib(),
        threads=threading.active_count(),
        modules=len(sys.modules),
        services=services,
    )


def print_runtime_snapshot(snapshot: RuntimeSnapshot) -> None:
    if os.environ.get("POENAVI_PROFILE") != "1":
        return
    memory = (
        f"{snapshot.memory_mib:.1f} MiB"
        if snapshot.memory_mib is not None
        else "unavailable"
    )
    print(
        "[Runtime] "
        f"mode={snapshot.mode} startup={snapshot.startup_ms:.1f} ms "
        f"memory={memory} threads={snapshot.threads} modules={snapshot.modules} "
        f"services={','.join(snapshot.services) or '-'}"
    )
