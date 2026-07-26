"""Windows foreground-window helpers for search-string paste experiments."""

import sys
import time
from pathlib import PureWindowsPath


def is_path_of_exile_process_name(process_name: str) -> bool:
    """Path of Exileの実行ファイル名だけを安全な送信先として受け入れる。"""
    name = PureWindowsPath(process_name or "").name.lower()
    return name.startswith("pathofexile") and name.endswith(".exe")


def is_path_of_exile_window(hwnd) -> bool:
    """指定ウィンドウがPath of Exileプロセスのものか確認する。"""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        if not pid.value:
            return False

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not process:
            return False
        try:
            size = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
                return False
            return is_path_of_exile_process_name(path.value)
        finally:
            kernel32.CloseHandle(process)
    except Exception as exc:
        print(f"[WINDOW] Path of Exile process check failed: {exc}")
        return False


def get_foreground_window():
    """Return the current foreground window handle, or None outside Windows."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        ctypes.windll.user32.GetForegroundWindow.restype = wintypes.HWND
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        return int(hwnd) if hwnd else None
    except Exception as exc:
        print(f"[WINDOW] GetForegroundWindow failed: {exc}")
        return None


def focus_window(hwnd, wait_seconds=0.12):
    """Best-effort foreground restore for a previously captured HWND."""
    if sys.platform != "win32" or not hwnd:
        return False

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.BringWindowToTop.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetFocus.argtypes = [wintypes.HWND]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        hwnd = wintypes.HWND(hwnd)
        if not user32.IsWindow(hwnd):
            print("[WINDOW] target window no longer exists")
            return False

        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)

        foreground = user32.GetForegroundWindow()
        current_thread = kernel32.GetCurrentThreadId()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0

        attached_target = False
        attached_foreground = False
        if target_thread and target_thread != current_thread:
            attached_target = bool(user32.AttachThreadInput(current_thread, target_thread, True))
        if foreground_thread and foreground_thread != current_thread:
            attached_foreground = bool(user32.AttachThreadInput(current_thread, foreground_thread, True))

        def hwnd_value(value):
            return int(getattr(value, "value", value) or 0)

        def request_foreground():
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)

        try:
            request_foreground()
        finally:
            if attached_foreground:
                user32.AttachThreadInput(current_thread, foreground_thread, False)
            if attached_target:
                user32.AttachThreadInput(current_thread, target_thread, False)

        target_value = hwnd_value(hwnd)
        deadline = time.time() + max(wait_seconds, 0.5)
        while time.time() < deadline:
            if hwnd_value(user32.GetForegroundWindow()) == target_value:
                return True
            time.sleep(0.05)

        # Windows のフォアグラウンド制限で失敗することがあるため、Alt入力で解除して再試行する。
        VK_MENU = 0x12
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        request_foreground()
        time.sleep(wait_seconds)
        return hwnd_value(user32.GetForegroundWindow()) == target_value
    except Exception as exc:
        print(f"[WINDOW] focus_window failed: {exc}")
        return False


def get_next_visible_window_after(hwnd, skip_current_process=False):
    """Return the next visible top-level window behind hwnd in Z-order on Windows.

    When skip_current_process is True, skip windows owned by this process. This is useful
    when a PoENavi popout/tool window is foreground and the target should be the game
    window behind all PoENavi windows.
    """
    if sys.platform != "win32" or not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        GW_HWNDNEXT = 2
        user32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
        user32.GetWindow.restype = wintypes.HWND
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        kernel32.GetCurrentProcessId.restype = wintypes.DWORD
        current_pid = int(kernel32.GetCurrentProcessId())

        def window_pid(window):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
            return int(pid.value or 0)

        current = user32.GetWindow(wintypes.HWND(hwnd), GW_HWNDNEXT)
        while current:
            if user32.IsWindowVisible(current) and not user32.GetParent(current):
                # タイトルなしの補助ウィンドウは候補から外す。
                if user32.GetWindowTextLengthW(current) > 0:
                    if not skip_current_process or window_pid(current) != current_pid:
                        return int(current)
            current = user32.GetWindow(current, GW_HWNDNEXT)
    except Exception as exc:
        print(f"[WINDOW] get_next_visible_window_after failed: {exc}")
    return None
