"""Low-frequency Windows process checks for the active Path of Exile client."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath

SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102


@dataclass(frozen=True)
class ProcessCandidate:
    pid: int
    executable_path: str
    started_at: datetime
    handle: int


class PoeProcessRef:
    def __init__(self, candidate: ProcessCandidate, kernel32):
        self.pid = int(candidate.pid)
        self.executable_path = str(candidate.executable_path)
        self.started_at = candidate.started_at
        self._handle = candidate.handle
        self._kernel32 = kernel32

    def is_alive(self) -> bool:
        if not self._handle:
            return False
        result = int(self._kernel32.WaitForSingleObject(self._handle, 0))
        return result == WAIT_TIMEOUT

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = 0

    def __del__(self):
        try:
            self.close()
        except (AttributeError, OSError):
            pass


def _is_poe_executable(path: str) -> bool:
    name = PureWindowsPath(path or "").name.casefold()
    return name.startswith("pathofexile") and name.endswith(".exe")


def select_process_candidate(
    candidates: list[ProcessCandidate], client_log_path: str | Path
) -> ProcessCandidate | None:
    """Prefer the executable installed beside the selected Client.txt."""
    poe_candidates = [
        candidate
        for candidate in candidates
        if _is_poe_executable(candidate.executable_path)
    ]
    if not poe_candidates:
        return None
    log_text = str(client_log_path or "")
    if log_text:
        install_dir = PureWindowsPath(log_text).parent.parent
        matched = [
            candidate
            for candidate in poe_candidates
            if PureWindowsPath(candidate.executable_path).parent == install_dir
        ]
        if len(matched) == 1:
            return matched[0]
        if len(matched) > 1:
            return max(matched, key=lambda item: item.started_at)
    if len(poe_candidates) == 1:
        return poe_candidates[0]
    return None


def _filetime_to_local_datetime(filetime) -> datetime:
    value = (int(filetime.dwHighDateTime) << 32) | int(filetime.dwLowDateTime)
    unix_seconds = (value - 116444736000000000) / 10_000_000
    return datetime.fromtimestamp(unix_seconds)


def _windows_process_candidates():
    if sys.platform != "win32":
        return [], None
    import ctypes
    import ctypes.wintypes as wt

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wt.DWORD),
            ("cntUsage", wt.DWORD),
            ("th32ProcessID", wt.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wt.DWORD),
            ("cntThreads", wt.DWORD),
            ("th32ParentProcessID", wt.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wt.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel32.Process32FirstW.argtypes = [
        wt.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]
    kernel32.Process32FirstW.restype = wt.BOOL
    kernel32.Process32NextW.argtypes = [
        wt.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]
    kernel32.Process32NextW.restype = wt.BOOL
    kernel32.OpenProcess.restype = wt.HANDLE
    kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wt.HANDLE,
        wt.DWORD,
        wt.LPWSTR,
        ctypes.POINTER(wt.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
    kernel32.GetProcessTimes.argtypes = [
        wt.HANDLE,
        ctypes.POINTER(wt.FILETIME),
        ctypes.POINTER(wt.FILETIME),
        ctypes.POINTER(wt.FILETIME),
        ctypes.POINTER(wt.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wt.BOOL
    kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    kernel32.WaitForSingleObject.restype = wt.DWORD
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    kernel32.CloseHandle.restype = wt.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle:
        return [], kernel32

    candidates = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return [], kernel32
        while True:
            if _is_poe_executable(entry.szExeFile):
                handle = kernel32.OpenProcess(
                    SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
                    False,
                    entry.th32ProcessID,
                )
                if handle:
                    try:
                        size = wt.DWORD(32768)
                        path_buffer = ctypes.create_unicode_buffer(size.value)
                        if not kernel32.QueryFullProcessImageNameW(
                            handle, 0, path_buffer, ctypes.byref(size)
                        ):
                            raise OSError("QueryFullProcessImageNameW failed")
                        creation = wt.FILETIME()
                        exit_time = wt.FILETIME()
                        kernel = wt.FILETIME()
                        user = wt.FILETIME()
                        if not kernel32.GetProcessTimes(
                            handle,
                            ctypes.byref(creation),
                            ctypes.byref(exit_time),
                            ctypes.byref(kernel),
                            ctypes.byref(user),
                        ):
                            raise OSError("GetProcessTimes failed")
                        candidates.append(ProcessCandidate(
                            pid=int(entry.th32ProcessID),
                            executable_path=path_buffer.value,
                            started_at=_filetime_to_local_datetime(creation),
                            handle=handle,
                        ))
                        handle = None
                    except (OSError, ValueError):
                        pass
                    finally:
                        if handle:
                            kernel32.CloseHandle(handle)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return candidates, kernel32


def find_poe_process(client_log_path: str | Path) -> PoeProcessRef | None:
    """Resolve the running game associated with the selected Client.txt."""
    candidates, kernel32 = _windows_process_candidates()
    selected = select_process_candidate(candidates, client_log_path)
    for candidate in candidates:
        if candidate is not selected and candidate.handle:
            kernel32.CloseHandle(candidate.handle)
    if selected is None or kernel32 is None:
        return None
    return PoeProcessRef(selected, kernel32)
