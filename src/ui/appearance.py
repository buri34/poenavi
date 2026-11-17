"""One application appearance, resolved once at startup.

The default preset keeps each existing surface's colours and type sizes. UI
call sites supply that legacy value while naming its semantic role. Explicit
presets and overrides replace those roles; game-content colours never enter
this module.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace


PRESETS = {
    "default": "現在の配色（既定）", "poenavi": "ぽえなび", "poetore": "ぽえとれ",
    "tokyo_night": "Tokyo Night", "vscode_dark_2026": "VS Code Dark 2026",
}
DEFAULT_FONT_FAMILY = "Noto Sans JP"
DEFAULT_FONT_SIZE = 13
MIN_FONT_SIZE = 9
MAX_FONT_SIZE = 24


@dataclass(frozen=True)
class ThemeTokens:
    accent: str = "#B0FF7B"
    accent_soft: str = "#22321D"
    text: str = "#E6ECEA"
    muted_text: str = "#98A39F"
    background: str = "#111416"
    surface: str = "#171B1D"
    control: str = "#1A1F21"
    border: str = "#3B4441"
    border_strong: str = "#59635F"
    selection_control: str = "#4488FF"
    success: str = "#5ED38A"
    warning: str = "#F6C85F"
    danger: str = "#FF6B6B"
    disabled: str = "#66706C"
    overlay_bg: str = "#000000"
    overlay_text: str = "#B0FF7B"
    overlay_border: str = "#B0FF7B"
    font_family: str = DEFAULT_FONT_FAMILY
    base_font_size: int = DEFAULT_FONT_SIZE


LEGACY_DIALOG_TOKENS = ThemeTokens()
POENAVI_TOKENS = replace(
    LEGACY_DIALOG_TOKENS, text="#E9FFBD", muted_text="#C9D4C2",
    background="#101310", surface="#1E241E", control="#1E241E",
)
POETORE_TOKENS = replace(
    LEGACY_DIALOG_TOKENS, accent="#65FFCA", accent_soft="#17332B",
    overlay_text="#E6ECEA", overlay_border="#65FFCA",
)
# Tokyo Night (standard dark, MIT), formerly enkia/tokyo-night-vscode-theme.
# themes/tokyo-night-color-theme.json @ 7c0f11eaef322f293621ca7befe462214b7ea468
# https://github.com/tokyo-night/tokyo-night-vscode-theme/blob/7c0f11eaef322f293621ca7befe462214b7ea468/themes/tokyo-night-color-theme.json
# Use the workbench terminal palette for accent/success/danger: the original
# button, focus and error colours are too dim for this UI's text/primary buttons.
# descriptionForeground/foreground also fail AA here; textPreformat is readable.
# App-only overlay roles reuse editor colours and the accent, with caller alpha.
TOKYO_NIGHT_TOKENS = ThemeTokens(
    accent="#7AA2F7",             # terminal.ansiBlue
    accent_soft="#202330",        # list.activeSelectionBackground
    text="#A9B1D6",               # editor.foreground / input.foreground
    muted_text="#9699A8",         # textPreformat.foreground (AA alternative)
    background="#1A1B26",         # editor.background
    surface="#16161E",            # sideBar.background
    control="#14141B",            # input.background
    border="#667089",             # AA-adjusted editorBracketMatch border (3:1)
    border_strong="#9699A8",      # textPreformat.foreground (visible controls)
    selection_control="#7AA2F7",  # terminal.ansiBlue (opaque, visible indicator)
    success="#73DACA",            # terminal.ansiGreen (no generic success role)
    warning="#E0AF68",            # editorWarning.foreground
    danger="#F7768E",             # terminal.ansiRed (readable error alternative)
    disabled="#545C7E",           # disabledForeground
    overlay_bg="#1A1B26",         # editor.background
    overlay_text="#A9B1D6",       # editor.foreground
    overlay_border="#7AA2F7",     # terminal.ansiBlue
)
# VS Code Dark 2026 (MIT); extensions/theme-defaults/themes/2026-dark.json
# @ fde6187a02fc9e24a94947feadc1c2c38f04be22 (all mapped colours are explicit).
# https://github.com/microsoft/vscode/blob/fde6187a02fc9e24a94947feadc1c2c38f04be22/extensions/theme-defaults/themes/2026-dark.json
# textLink is brighter than button.background for this UI's accent text and
# dark-on-accent buttons. infoBorder supplies the opaque focus/indicator blue
# instead of the translucent focusBorder. App-only overlays reuse editor/text.
VSCODE_DARK_2026_TOKENS = ThemeTokens(
    accent="#48A0C7",             # textLink.foreground
    accent_soft="#2C2D2E",        # list.inactiveSelectionBackground
    text="#BFBFBF",               # foreground / input.foreground
    muted_text="#8C8C8C",         # descriptionForeground
    background="#121314",         # editor.background
    surface="#191A1B",            # sideBar.background
    control="#191A1B",            # input.background
    border="#707070",             # checkbox.border (3:1 alternative to input.border)
    border_strong="#707070",      # checkbox.border
    selection_control="#3994BC",  # inputValidation.infoBorder
    success="#73C991",            # gitDecoration.addedResourceForeground (success)
    warning="#E5BA7D",            # list.warningForeground
    danger="#F48771",             # errorForeground
    disabled="#555555",           # disabledForeground
    overlay_bg="#121314",         # editor.background
    overlay_text="#BFBFBF",       # foreground
    overlay_border="#3994BC",     # inputValidation.infoBorder
)
COLOR_ROLES = tuple(key for key in asdict(POENAVI_TOKENS) if key not in ("font_family", "base_font_size"))
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_FONT_FAMILY = re.compile(r"[\w .,+()\-]{1,128}\Z", re.UNICODE)


def normalize_appearance(value, legacy_text_color=None) -> dict:
    """Drop invalid/unknown values. Stored colours are opaque #RRGGBB.

    The old default text_color was never used; migrating that particular value
    would change the default appearance. Only a non-default legacy choice is
    carried forward, and an explicit new override always wins.
    """
    value = value if isinstance(value, dict) else {}
    preset = value.get("preset", "default")
    if not isinstance(preset, str) or preset not in PRESETS:
        preset = "default"
    raw = value.get("overrides")
    raw = raw if isinstance(raw, dict) else {}
    overrides = {}
    for key in COLOR_ROLES:
        color = raw.get(key)
        if isinstance(color, str) and _HEX_COLOR.fullmatch(color):
            overrides[key] = color.upper()
    family = raw.get("font_family")
    if isinstance(family, str) and _FONT_FAMILY.fullmatch(family.strip()):
        overrides["font_family"] = family.strip()
    size = raw.get("base_font_size")
    if type(size) is int and MIN_FONT_SIZE <= size <= MAX_FONT_SIZE:
        overrides["base_font_size"] = size
    if (
        isinstance(legacy_text_color, str)
        and _HEX_COLOR.fullmatch(legacy_text_color)
        and legacy_text_color.upper() not in ("#B0FF7B", "#E9FFBD")
    ):
        overrides.setdefault("overlay_text", legacy_text_color.upper())
    return {"preset": preset, "overrides": overrides}


def resolve_tokens(appearance=None, mode="poenavi") -> ThemeTokens:
    settings = normalize_appearance(appearance)
    preset = settings["preset"]
    if preset == "tokyo_night":
        base = TOKYO_NIGHT_TOKENS
    elif preset == "vscode_dark_2026":
        base = VSCODE_DARK_2026_TOKENS
    else:
        base = POETORE_TOKENS if (preset == "poetore" or (preset == "default" and mode == "poetore")) else POENAVI_TOKENS
        if preset != "default":
            base = replace(base, border="#76817C", border_strong="#76817C")
    return replace(base, **_effective_overrides(settings, base))


def _effective_overrides(settings, base=None):
    overrides = dict(settings["overrides"])
    if "surface" in overrides:
        overrides.setdefault("control", overrides["surface"])
    if "border" in overrides:
        overrides.setdefault("border_strong", overrides["border"])
        overrides.setdefault("overlay_border", overrides["border"])
    if "muted_text" in overrides:
        overrides.setdefault("disabled", overrides["muted_text"])
    if "accent" in overrides:
        overrides.setdefault("selection_control", overrides["accent"])
        overrides.setdefault("overlay_border", overrides["accent"])
        background = overrides.get("background", (base or POENAVI_TOKENS).background)
        accent = overrides["accent"]
        rgb = [round(int(background[i:i + 2], 16) * .85 + int(accent[i:i + 2], 16) * .15) for i in (1, 3, 5)]
        overrides.setdefault("accent_soft", "#" + "".join(f"{channel:02X}" for channel in rgb))
    return overrides


_appearance = normalize_appearance(None)
_requested_appearance = normalize_appearance(None)


def current_appearance() -> dict:
    return normalize_appearance(_appearance)


def requested_appearance() -> dict:
    """Return the startup request before platform-specific font fallback."""
    return normalize_appearance(_requested_appearance)


def configure_appearance(appearance, *, requested=None) -> None:
    """Set startup effective/requested snapshots; saving settings does not call it."""
    global _appearance, _requested_appearance
    _appearance = normalize_appearance(appearance)
    _requested_appearance = normalize_appearance(appearance if requested is None else requested)


def theme_color(role: str, legacy: str | None = None) -> str:
    if role not in COLOR_ROLES:
        raise ValueError(f"Unknown UI colour role: {role}")
    if _appearance["preset"] == "default" and role not in _effective_overrides(_appearance) and legacy is not None:
        return legacy
    return getattr(resolve_tokens(_appearance), role)


def theme_rgba(role: str, red: int, green: int, blue: int, alpha) -> str:
    """Replace RGB only, preserving the caller's existing opacity convention."""
    legacy = f"rgba({red}, {green}, {blue}, {alpha})"
    if _appearance["preset"] == "default" and role not in _effective_overrides(_appearance):
        return legacy
    color = theme_color(role)
    rgb = tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})"


def theme_font_family(legacy=DEFAULT_FONT_FAMILY) -> str:
    return _appearance["overrides"].get("font_family", legacy)


def theme_qcolor(role, red, green, blue, alpha=255):
    """Painter counterpart of theme_rgba; QColor does not parse QSS rgba()."""
    from PySide6.QtGui import QColor

    color = QColor(theme_color(role, f"#{red:02X}{green:02X}{blue:02X}"))
    color.setAlpha(alpha)
    return color


def theme_font_size(size):
    """Scale existing type hierarchy, including explicit per-panel sizes."""
    base = _appearance["overrides"].get("base_font_size", DEFAULT_FONT_SIZE)
    return max(1, round(size * base / DEFAULT_FONT_SIZE))


def has_custom_theme_font() -> bool:
    overrides = _appearance["overrides"]
    return (overrides.get("base_font_size", DEFAULT_FONT_SIZE) != DEFAULT_FONT_SIZE
            or overrides.get("font_family", DEFAULT_FONT_FAMILY) != DEFAULT_FONT_FAMILY)


def _geometry_limits(widget):
    return (widget.minimumWidth(), widget.minimumHeight(),
            widget.maximumWidth(), widget.maximumHeight())


def _unfitted_geometry_limits(widget):
    current = _geometry_limits(widget)
    saved = getattr(widget, "_theme_fit_limits", None)
    if saved is None:
        return current
    original, fitted = saved
    # Treat each axis as a pair: setFixedSize/profile changes can replace
    # one bound with a value that happens to equal the fitter's other bound.
    result = list(current)
    for axis in (0, 1):
        if ((current[axis], current[axis + 2]) == (fitted[axis], fitted[axis + 2])
                or (current[axis] > current[axis + 2] and current[axis + 2] == fitted[axis + 2])):
            # QSS can temporarily apply a minimum above a fixed maximum.
            result[axis], result[axis + 2] = original[axis], original[axis + 2]
    return tuple(result)


def suspend_theme_fixed_geometry(root, suspended: bool) -> None:
    """Release fitter-owned constraints before an intentional compact state.

    The state owner sets its compact limits while suspended, then releases
    those limits before resuming. Descendant Show/LayoutRequest events must
    respect the same suspension, including while the owner is hidden.
    """
    root._theme_geometry_suspended = suspended
    if not suspended:
        return
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QWidget

    for widget in reversed([root, *root.findChildren(QWidget)]):
        if hasattr(widget, "_theme_fit_limits"):
            min_w, min_h, max_w, max_h = _unfitted_geometry_limits(widget)
            widget.setMinimumSize(QSize(min_w, min_h))
            widget.setMaximumSize(QSize(max_w, max_h))
            del widget._theme_fit_limits
        if hasattr(widget, "_theme_fit_signature"):
            del widget._theme_fit_signature


def fit_theme_fixed_geometry(root) -> None:
    """Let existing fixed text controls grow for a user-selected font.

    Run after styling/layout construction. Keep the legacy geometry entirely
    untouched for the default type, including colour-only presets.
    """
    if not has_custom_theme_font():
        return

    from PySide6.QtCore import QSize, Qt
    from PySide6.QtWidgets import (
        QAbstractButton, QAbstractSpinBox, QApplication, QComboBox, QLabel, QLineEdit, QStyle,
        QStyleOptionButton, QStyleOptionComboBox, QStyleOptionFrame, QToolButton, QWidget,
    )

    ancestor = root
    while ancestor is not None:
        if getattr(ancestor, "_theme_geometry_suspended", False):
            return
        ancestor = ancestor.parentWidget()
    styles = {}
    application_style = QApplication.instance().styleSheet()
    # Children first: fixed-width composite chips/hotkeys must include the
    # enlarged child editors/buttons in their layout minimum.
    for widget in reversed([root, *root.findChildren(QWidget)]):
        ancestor = widget
        inherited_style = []
        while ancestor is not None:
            if getattr(ancestor, "_theme_geometry_suspended", False):
                break
            if ancestor not in styles:
                styles[ancestor] = ancestor.styleSheet()
            inherited_style.append(styles[ancestor])
            ancestor = ancestor.parentWidget()
        if ancestor is not None:
            continue
        original_limits = _unfitted_geometry_limits(widget)
        # QSS may impose a minimum above a caller's fixed size during polish.
        # Such conflicting bounds still describe a fixed text control.
        fixed_width = original_limits[0] >= original_limits[2]
        fixed_height = original_limits[1] >= original_limits[3]
        widget.ensurePolished()
        text = (widget.currentText() if isinstance(widget, QComboBox)
                else widget.text() if isinstance(widget, (QAbstractButton, QAbstractSpinBox, QLabel, QLineEdit)) else None)
        signature = (widget.font().key(), tuple(inherited_style),
                     application_style, text, original_limits)
        if isinstance(widget, QLabel) and widget.wordWrap():
            signature += (widget.width(), widget.isVisibleTo(root))
        if (text is not None and getattr(widget, "_theme_fit_signature", None) == signature
                and widget.size().expandedTo(widget._theme_fit_needed) == widget.size()):
            continue
        if isinstance(widget, (QAbstractButton, QLabel)):
            if not widget.text():  # Icon-only controls don't scale with text.
                continue
            needed = widget.sizeHint()
            if isinstance(widget, QAbstractButton) and not isinstance(widget, QToolButton):
                option = QStyleOptionButton()
                widget.initStyleOption(option)
                element = (QStyle.SE_CheckBoxContents if widget.inherits("QCheckBox")
                           else QStyle.SE_RadioButtonContents if widget.inherits("QRadioButton")
                           else QStyle.SE_PushButtonContents)
                content = widget.style().subElementRect(element, option, widget)
                metrics = widget.fontMetrics()
                lines = widget.text().splitlines()
                width = max(metrics.horizontalAdvance(line.replace("&", "")) for line in lines)
                if not widget.icon().isNull():
                    width += widget.iconSize().width() + 4
                needed = needed.expandedTo(QSize(
                    width + widget.width() - content.width(),
                    metrics.size(Qt.TextShowMnemonic, widget.text()).height() + widget.height() - content.height(),
                ))
            elif isinstance(widget, QLabel) and widget.wordWrap():
                if not widget.isVisibleTo(root):
                    continue
                needed = QSize(widget.minimumSizeHint().width(), widget.heightForWidth(widget.width()))
            if type(widget).__name__ == "ElidedLabel":
                needed.setWidth(widget.minimumWidth())
        elif isinstance(widget, QAbstractSpinBox):
            editor = widget.findChild(QLineEdit)
            option = QStyleOptionFrame()
            editor.initStyleOption(option)
            content = editor.style().subElementRect(QStyle.SE_LineEditContents, option, editor)
            metrics = editor.fontMetrics()
            text_size = metrics.size(Qt.TextSingleLine, widget.text())
            needed = widget.sizeHint().expandedTo(QSize(
                text_size.width() + widget.width() - content.width() + 4,
                text_size.height() + widget.height() - content.height(),
            ))
        elif isinstance(widget, QLineEdit):
            metrics = widget.fontMetrics()
            validator = widget.validator()
            samples = [widget.text(), "000"]
            if validator is not None and hasattr(validator, "top"):
                samples.extend((str(validator.bottom()), str(validator.top())))
            option = QStyleOptionFrame()
            widget.initStyleOption(option)
            content = widget.style().subElementRect(QStyle.SE_LineEditContents, option, widget)
            needed = QSize(
                (max(metrics.horizontalAdvance(text) for text in samples)
                 + widget.width() - content.width() + 4) if fixed_width else widget.minimumWidth(),
                max(widget.sizeHint().height(), metrics.size(Qt.TextSingleLine, widget.text()).height()
                    + widget.height() - content.height()),
            )
        elif isinstance(widget, QComboBox):
            # These explicitly fit the current text and keep a wider popup.
            option = QStyleOptionComboBox()
            widget.initStyleOption(option)
            content = widget.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField, widget)
            metrics = widget.fontMetrics()
            needed = widget.minimumSizeHint().expandedTo(QSize(
                metrics.horizontalAdvance(widget.currentText()) + widget.width() - content.width() + 2,
                metrics.size(Qt.TextSingleLine, widget.currentText()).height() + widget.height() - content.height(),
            ))
            if widget.property("compactAction"):
                needed.setWidth(widget.minimumWidth())
        elif widget.layout() is not None:
            layout = widget.layout()
            needed = layout.minimumSize().expandedTo(widget.minimumSizeHint())
            if layout.hasHeightForWidth():
                needed.setHeight(max(needed.height(), layout.heightForWidth(max(widget.width(), needed.width()))))
        else:
            continue
        if text is not None:
            widget._theme_fit_signature = signature
            widget._theme_fit_needed = needed
        if fixed_width:
            if widget.maximumWidth() > 0 and needed.width() > widget.maximumWidth():
                widget.setFixedWidth(needed.width())
        elif not (isinstance(widget, QLabel) and type(widget).__name__ == "ElidedLabel"):
            # A finite maximum is a caller-owned limit, not another fixed
            # text size. Do not turn it into min == max on the next pass.
            if needed.width() <= widget.maximumWidth():
                widget.setMinimumWidth(max(widget.minimumWidth(), needed.width()))
        if fixed_height:
            if widget.maximumHeight() > 0 and needed.height() > widget.maximumHeight():
                widget.setFixedHeight(needed.height())
        else:
            if needed.height() <= widget.maximumHeight():
                widget.setMinimumHeight(max(widget.minimumHeight(), needed.height()))
        widget._theme_fit_limits = (original_limits, _geometry_limits(widget))


def _install_theme_geometry_filter(app):
    """Fit constructed/dynamic UI after layout, only for an explicit custom font.

    A single application filter includes Qt dialogs and lazily created pages;
    constructor-only fitting misses both. The default path does no work.
    """
    if hasattr(app, "_theme_geometry_filter"):
        return
    import weakref
    from PySide6.QtCore import QEvent, QObject, QTimer
    from PySide6.QtWidgets import QWidget
    from shiboken6 import isValid

    class ThemeGeometryFilter(QObject):
        fitting = False

        def __init__(self, parent):
            super().__init__(parent)
            self.pending = {}

        def fit(self, widget):
            self.fitting = True
            try:
                fit_theme_fixed_geometry(widget)
            finally:
                self.fitting = False

        def flush_styles(self):
            pending, self.pending = self.pending, {}
            if not has_custom_theme_font():
                return
            for reference in pending.values():
                widget = reference()
                if widget is not None and isValid(widget):
                    self.fit(widget)

        def eventFilter(self, watched, event):
            if not self.fitting and has_custom_theme_font() and isinstance(watched, QWidget):
                if event.type() in (QEvent.Polish, QEvent.StyleChange, QEvent.FontChange):
                    # Filters run before QWidget handles the event. Coalesce
                    # until inherited QSS/font propagation has completed.
                    if hasattr(watched, "_theme_fit_signature"):
                        del watched._theme_fit_signature
                    if not self.pending:
                        QTimer.singleShot(0, self.flush_styles)
                    window = watched.window()
                    self.pending[id(window)] = weakref.ref(window)
                elif event.type() in (QEvent.Show, QEvent.LayoutRequest):
                    self.fit(watched)
            return False

    app._theme_geometry_filter = ThemeGeometryFilter(app)
    app.installEventFilter(app._theme_geometry_filter)


def resolve_app_theme(theme):
    changes = {
        key: theme_color("control" if key == "panel" else key, getattr(theme, key))
        for key in ("accent", "text", "muted_text", "background", "panel")
    }
    return theme if all(getattr(theme, key) == value for key, value in changes.items()) else replace(theme, **changes)


def resolve_dialog_theme(theme):
    changes = {key: theme_color(key, getattr(theme, key)) for key in COLOR_ROLES if hasattr(theme, key)}
    changes["font_family"] = theme_font_family(theme.font_family)
    for key in ("title_size", "section_size", "body_size", "caption_size"):
        changes[key] = theme_font_size(getattr(theme, key))
    # Taller controls keep large fonts legible without changing the default.
    if "base_font_size" in _appearance["overrides"]:
        for key in ("form_control_height", "compact_row_height"):
            changes[key] = max(getattr(theme, key), changes["body_size"] + 12)
    return theme if all(getattr(theme, key) == value for key, value in changes.items()) else replace(theme, **changes)


def apply_application_appearance(app, config) -> None:
    """Apply validated user type and palette after registering the bundled font."""
    from PySide6.QtGui import QColor, QFontDatabase, QPalette

    _install_theme_geometry_filter(app)

    appearance = normalize_appearance((config or {}).get("appearance"))
    family = appearance["overrides"].get("font_family")
    if family and family not in QFontDatabase.families():
        appearance["overrides"].pop("font_family")
    configure_appearance(appearance, requested=(config or {}).get("appearance"))
    font = app.font()
    font.setFamily(theme_font_family())
    if "base_font_size" in appearance["overrides"]:
        font.setPixelSize(theme_font_size(DEFAULT_FONT_SIZE))
    app.setFont(font)
    if appearance["preset"] != "default" or any(key in COLOR_ROLES for key in appearance["overrides"]):
        palette = app.palette()
        for palette_role, token in (
            (QPalette.Window, "background"), (QPalette.Base, "control"),
            (QPalette.AlternateBase, "surface"), (QPalette.WindowText, "text"),
            (QPalette.Text, "text"), (QPalette.Button, "control"),
            (QPalette.ButtonText, "text"), (QPalette.Highlight, "accent_soft"),
            (QPalette.HighlightedText, "text"), (QPalette.ToolTipBase, "background"),
            (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "muted_text"),
        ):
            palette.setColor(palette_role, QColor(theme_color(token)))
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(theme_color("disabled")))
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(theme_color("disabled")))
        app.setPalette(palette)
