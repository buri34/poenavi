from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.app_font import EXPECTED_FAMILY, apply_bundled_ui_font, bundled_font_path


ROOT = Path(__file__).resolve().parents[1]
FONT_SHA256 = "c2f3b4d463500a2ddcd3849cded1fceeb9fd6d1c32e6cbecd568453ba50fc68f"


def test_bundled_noto_sans_jp_is_the_pinned_google_fonts_file():
    path = bundled_font_path()
    assert path == ROOT / "assets" / "fonts" / "NotoSansJP[wght].ttf"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == FONT_SHA256


def test_apply_bundled_ui_font_registers_and_selects_noto_sans_jp(qapp):
    assert isinstance(qapp, QApplication)
    assert apply_bundled_ui_font(qapp) == EXPECTED_FAMILY
    assert qapp.font().family() == EXPECTED_FAMILY
    assert qapp.property("bundledUiFontFamily") == EXPECTED_FAMILY
