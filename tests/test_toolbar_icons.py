from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from src.ui.toolbar_icons import (
    image_manager_icon,
    memo_icon,
    settings_icon,
    vendor_presets_icon,
)


def test_poennavi_toolbar_icons_are_distinct_and_render_at_compact_size():
    QApplication.instance() or QApplication([])
    colors = {
        "accent_color": "#b0ff7b",
        "panel_color": "#263A20",
        "dark_color": "#142111",
    }
    icons = [
        memo_icon(**colors),
        vendor_presets_icon(**colors),
        image_manager_icon(**colors),
        settings_icon(**colors),
    ]
    images = [icon.pixmap(QSize(24, 24)).toImage() for icon in icons]

    assert all(not icon.isNull() for icon in icons)
    assert len({image.cacheKey() for image in images}) == len(images)


def test_poennavi_toolbar_uses_custom_icons_and_has_no_poetore_button():
    source = open("src/ui/main_window.py", encoding="utf-8").read()

    assert "self.memo_btn.setIcon(memo_icon(" in source
    assert "self.vendor_search_btn.setIcon(vendor_presets_icon(" in source
    assert "self.cheat_sheets_btn.setIcon(image_manager_icon(" in source
    assert "self.settings_btn.setIcon(settings_icon(" in source
    assert "self.poetore_btn" not in source
