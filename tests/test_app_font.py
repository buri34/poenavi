from __future__ import annotations

import hashlib
import sys
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


def test_bundled_font_path_prefers_frozen_distribution_assets(monkeypatch, tmp_path):
    executable = tmp_path / "PoENavi.exe"
    frozen_font = tmp_path / "assets" / "fonts" / "NotoSansJP[wght].ttf"
    frozen_font.parent.mkdir(parents=True)
    frozen_font.write_bytes(b"distribution-font")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert bundled_font_path() == frozen_font
