"""Position the price-check panel inside the active Path of Exile window."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QCursor, QGuiApplication


PANEL_MARGIN = 16
POE_SIDEBAR_WIDTH_RATIO = 370 / 600


@dataclass(frozen=True)
class PlacementContext:
    target_rect: QRect | None
    cursor_pos: QPoint


def _window_title(hwnd) -> str:
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, len(title))
    return title.value


def _window_client_rect(hwnd) -> QRect | None:
    user32 = ctypes.windll.user32
    client = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    if not user32.GetClientRect(hwnd, ctypes.byref(client)):
        return None
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    width = client.right - client.left
    height = client.bottom - client.top
    if width <= 0 or height <= 0:
        return None
    return _native_rect_to_qt(hwnd, QRect(origin.x, origin.y, width, height))


def path_of_exile_client_rect() -> QRect | None:
    """Return a visible PoE client rect in global coordinates on Windows.

    Prefer the foreground game, then fall back to any visible PoE window so
    placement also works when PoENavi's image button currently has focus.
    """
    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL

        foreground = user32.GetForegroundWindow()
        if foreground and "path of exile" in _window_title(foreground).casefold():
            return _window_client_rect(foreground)

        candidates = []
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @enum_proc
        def collect(hwnd, _lparam):
            if (
                user32.IsWindowVisible(hwnd)
                and "path of exile" in _window_title(hwnd).casefold()
            ):
                candidates.append(hwnd)
            return True

        user32.EnumWindows(collect, 0)
        for hwnd in candidates:
            rect = _window_client_rect(hwnd)
            if rect is not None:
                return rect
        return None
    except (AttributeError, OSError):
        return None


def _native_rect_to_qt(hwnd: int, rect: QRect) -> QRect:
    """Convert Win32 physical pixels to Qt device-independent coordinates."""
    try:
        user32 = ctypes.windll.user32
        try:
            get_dpi = user32.GetDpiForWindow
            get_dpi.argtypes = [wintypes.HWND]
            get_dpi.restype = wintypes.UINT
            dpi = get_dpi(hwnd)
        except AttributeError:
            dpi = 96
        scale = max(float(dpi or 96) / 96.0, 1.0)
        if scale == 1.0:
            return rect

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return rect
        screens = QGuiApplication.screens()
        if not screens:
            return rect
        native_left, native_top = info.rcMonitor.left, info.rcMonitor.top
        screen = min(
            screens,
            key=lambda candidate: abs(candidate.geometry().left() - native_left)
            + abs(candidate.geometry().top() - native_top),
        )
        screen_rect = screen.geometry()
        return QRect(
            screen_rect.left() + round((rect.left() - native_left) / scale),
            screen_rect.top() + round((rect.top() - native_top) / scale),
            round(rect.width() / scale),
            round(rect.height() / scale),
        )
    except (AttributeError, OSError):
        return rect


def capture_placement_context() -> PlacementContext:
    """Capture before the app takes focus from PoE."""
    return PlacementContext(path_of_exile_client_rect(), QCursor.pos())


def calculate_panel_position(
    target_rect: QRect,
    cursor_pos: QPoint,
    panel_size: QSize,
    margin: int = PANEL_MARGIN,
) -> QPoint:
    """Place inward from the PoE panel under the cursor, matching Awakened."""
    width = min(panel_size.width(), max(1, target_rect.width() - margin * 2))
    height = min(panel_size.height(), max(1, target_rect.height() - margin * 2))
    sidebar_width = round(target_rect.height() * POE_SIDEBAR_WIDTH_RATIO)
    if cursor_pos.x() < target_rect.center().x():
        x = target_rect.left() + sidebar_width
    else:
        x = target_rect.right() - sidebar_width - width + 1
    y = target_rect.top()
    max_x = target_rect.right() - margin - width + 1
    max_y = target_rect.bottom() - margin - height + 1
    return QPoint(
        max(target_rect.left() + margin, min(x, max_x)),
        max(target_rect.top(), min(y, max_y)),
    )


def fallback_screen_rect(cursor_pos: QPoint) -> QRect:
    screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
    return screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)


def position_for_context(context: PlacementContext, panel_size: QSize) -> QPoint:
    target = context.target_rect or fallback_screen_rect(context.cursor_pos)
    return calculate_panel_position(target, context.cursor_pos, panel_size)
