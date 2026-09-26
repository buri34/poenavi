"""Register and apply the bundled application UI font."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase


FONT_FILENAME = "NotoSansJP[wght].ttf"
EXPECTED_FAMILY = "Noto Sans JP"


def bundled_font_path() -> Path:
    """Return the bundled font path for source and PyInstaller executions."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "assets" / "fonts")
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "assets" / "fonts")
    candidates.append(Path(__file__).resolve().parents[1] / "assets" / "fonts")
    for directory in candidates:
        path = directory / FONT_FILENAME
        if path.is_file():
            return path
    return candidates[-1] / FONT_FILENAME


def apply_bundled_ui_font(app) -> str | None:
    """Register Noto Sans JP and make it Qt's default application font."""
    font_id = QFontDatabase.addApplicationFont(str(bundled_font_path()))
    if font_id == -1:
        return None
    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        return None
    family = EXPECTED_FAMILY if EXPECTED_FAMILY in families else families[0]
    current = app.font()
    font = QFont(family)
    font.setPointSizeF(current.pointSizeF())
    app.setFont(font)
    app.setProperty("bundledUiFontFamily", family)
    return family
