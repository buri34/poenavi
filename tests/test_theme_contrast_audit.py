"""Contrast contracts for the shipped explicit presets (custom colours are free).

Disabled controls and decorative translucent separators are exempt from WCAG
contrast requirements. Essential borders, selection marks and handles are not.
"""

import re

import pytest
from PySide6.QtGui import QColor, QImage, QPalette
from PySide6.QtWidgets import QCheckBox, QDialog, QPushButton

from src.ui.appearance import configure_appearance, current_appearance, resolve_tokens
from src.ui.app_info_widget import AppInfoWidget
from src.ui.app_theme import theme_for_mode
from src.ui.dialog_theme import apply_dialog_theme, dialog_theme_for_mode
from src.ui.styles import Styles


def contrast(first, second):
    def luminance(value):
        color = QColor(value)
        values = [color.redF(), color.greenF(), color.blueF()]
        return sum((v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4) * w
                   for v, w in zip(values, (.2126, .7152, .0722)))
    low, high = sorted((luminance(first), luminance(second)))
    return (high + .05) / (low + .05)


@pytest.fixture(params=["poenavi", "poetore", "tokyo_night", "vscode_dark_2026"])
def preset(request, qapp):
    previous = current_appearance()
    configure_appearance({"preset": request.param})
    yield request.param
    configure_appearance(previous)


def test_text_and_essential_nontext_pairs(preset):
    tokens = resolve_tokens({"preset": preset})
    for foreground in ("text", "muted_text", "accent", "success", "warning", "danger"):
        for background in ("background", "surface", "control"):
            ratio = contrast(getattr(tokens, foreground), getattr(tokens, background))
            assert ratio >= 4.5, (preset, foreground, background, ratio)
    for foreground, background in (("text", "accent_soft"), ("background", "accent"), ("overlay_text", "overlay_bg")):
        assert contrast(getattr(tokens, foreground), getattr(tokens, background)) >= 4.5
    for foreground in ("border", "border_strong", "selection_control", "overlay_border"):
        for background in ("background", "surface", "control"):
            assert contrast(getattr(tokens, foreground), getattr(tokens, background)) >= 3, (preset, foreground, background)
    assert contrast(tokens.background, tokens.selection_control) >= 3  # Checkmark inside the indicator.


def test_actual_primary_button_foregrounds(qapp, preset):
    host = QDialog()
    apply_dialog_theme(host, dialog_theme_for_mode("poenavi"))
    button = QPushButton("保存", host)
    button.setProperty("buttonRole", "primary")
    button.ensurePolished()
    info = AppInfoWidget(theme_for_mode("poenavi"))
    info.update_button.setEnabled(True)
    info.update_button.ensurePolished()
    try:
        for control in (button, info.update_button):
            palette = control.palette()
            ratio = contrast(palette.color(QPalette.ButtonText), palette.color(QPalette.Button))
            assert ratio >= 4.5, (preset, control.objectName(), ratio)
    finally:
        host.close()
        info.close()


def test_actual_checkbox_ink_and_fill(qapp, preset):
    checkbox = QCheckBox("選択")
    Styles.apply_checkbox_style(checkbox)
    path = re.search(r'image:\s*url\("?([^"\)]+)', checkbox.styleSheet()).group(1)
    image = QImage(path)
    assert not image.isNull()
    background = image.pixelColor(0, 0)
    # The antialiased checkmark contains at least one fully covered pixel.
    best = max(contrast(image.pixelColor(x, y), background)
               for x in range(image.width()) for y in range(image.height()))
    assert best >= 3, (preset, best)
