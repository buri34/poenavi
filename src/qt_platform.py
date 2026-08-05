"""Qt platform selection for best-effort Linux compatibility."""

from __future__ import annotations

import os
import sys
from collections.abc import MutableMapping


def configure_qt_platform(
    env: MutableMapping[str, str] | None = None,
    platform_name: str | None = None,
) -> bool:
    """Use Qt's X11 backend for a Wayland session when XWayland is available.

    The setting must be applied before importing PySide6. An explicitly supplied
    ``QT_QPA_PLATFORM`` is always left untouched.
    """
    env = os.environ if env is None else env
    platform_name = sys.platform if platform_name is None else platform_name

    if not platform_name.startswith("linux"):
        return False
    if "QT_QPA_PLATFORM" in env:
        return False

    is_wayland_session = bool(env.get("WAYLAND_DISPLAY")) or (
        env.get("XDG_SESSION_TYPE", "").casefold() == "wayland"
    )
    if not is_wayland_session or not env.get("DISPLAY"):
        return False

    env["QT_QPA_PLATFORM"] = "xcb"
    return True
