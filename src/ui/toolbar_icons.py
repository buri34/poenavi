"""Small theme-aware vector icons used by compact toolbar buttons."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _canvas():
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    return pixmap, painter


def _finish(pixmap, painter) -> QIcon:
    painter.end()
    return QIcon(pixmap)


def memo_icon(accent_color, panel_color, dark_color) -> QIcon:
    pixmap, painter = _canvas()
    accent, panel, dark = map(QColor, (accent_color, panel_color, dark_color))
    page = QPainterPath(QPointF(5.0, 2.8))
    page.lineTo(15.8, 2.8)
    page.lineTo(20.0, 7.0)
    page.lineTo(20.0, 21.0)
    page.lineTo(5.0, 21.0)
    page.closeSubpath()
    painter.setPen(QPen(accent, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(panel)
    painter.drawPath(page)
    painter.drawLine(QPointF(15.8, 3.1), QPointF(15.8, 7.0))
    painter.drawLine(QPointF(15.8, 7.0), QPointF(19.7, 7.0))
    painter.setPen(QPen(dark, 1.5, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(8.0, 10.0), QPointF(16.8, 10.0))
    painter.drawLine(QPointF(8.0, 14.0), QPointF(16.8, 14.0))
    painter.drawLine(QPointF(8.0, 18.0), QPointF(14.0, 18.0))
    return _finish(pixmap, painter)


def image_manager_icon(accent_color, panel_color, dark_color) -> QIcon:
    pixmap, painter = _canvas()
    accent, panel, dark = map(QColor, (accent_color, panel_color, dark_color))
    painter.setPen(QPen(accent.darker(150), 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(dark)
    painter.drawRoundedRect(2.8, 3.2, 15.5, 14.5, 2.0, 2.0)
    painter.setPen(QPen(accent, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(panel)
    painter.drawRoundedRect(5.5, 6.0, 15.5, 14.5, 2.0, 2.0)
    painter.setBrush(accent)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QPointF(16.4, 10.4), 1.7, 1.7)
    mountain = QPainterPath(QPointF(7.4, 18.4))
    mountain.lineTo(11.5, 13.2)
    mountain.lineTo(14.2, 16.1)
    mountain.lineTo(16.1, 14.3)
    mountain.lineTo(19.2, 18.4)
    mountain.closeSubpath()
    painter.setBrush(accent.darker(115))
    painter.drawPath(mountain)
    return _finish(pixmap, painter)


def _draw_gear(painter, accent, panel, dark):
    center, radius, tooth = QPointF(12.0, 12.0), 5.5, 2.4
    cx, cy = center.x(), center.y()
    painter.setPen(QPen(accent, 2.6, Qt.SolidLine, Qt.RoundCap))
    diagonal = tooth * 0.72
    for start, end in (
        ((cx, cy - radius - tooth), (cx, cy - radius)),
        ((cx, cy + radius), (cx, cy + radius + tooth)),
        ((cx - radius - tooth, cy), (cx - radius, cy)),
        ((cx + radius, cy), (cx + radius + tooth, cy)),
        ((cx - radius - diagonal, cy - radius - diagonal), (cx - radius * .72, cy - radius * .72)),
        ((cx + radius * .72, cy + radius * .72), (cx + radius + diagonal, cy + radius + diagonal)),
        ((cx - radius - diagonal, cy + radius + diagonal), (cx - radius * .72, cy + radius * .72)),
        ((cx + radius * .72, cy - radius * .72), (cx + radius + diagonal, cy - radius - diagonal)),
    ):
        painter.drawLine(QPointF(*start), QPointF(*end))
    painter.setPen(QPen(accent, 1.2))
    painter.setBrush(panel)
    painter.drawEllipse(center, radius, radius)
    painter.setBrush(dark)
    painter.drawEllipse(center, radius * .36, radius * .36)


def settings_icon(accent_color, panel_color, dark_color) -> QIcon:
    pixmap, painter = _canvas()
    _draw_gear(painter, QColor(accent_color), QColor(panel_color), QColor(dark_color))
    return _finish(pixmap, painter)


def vendor_presets_icon(accent_color, panel_color, dark_color) -> QIcon:
    pixmap, painter = _canvas()
    accent, panel, dark = map(QColor, (accent_color, panel_color, dark_color))
    painter.setPen(QPen(accent, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(panel)
    painter.drawRoundedRect(3.0, 8.0, 16.0, 12.5, 1.8, 1.8)
    painter.setBrush(accent)
    painter.drawRect(2.5, 5.0, 17.0, 4.0)
    painter.setPen(QPen(dark, 1.2))
    for x in (6.8, 11.0, 15.2):
        painter.drawLine(QPointF(x, 5.3), QPointF(x, 8.7))
    painter.setPen(QPen(accent, 1.2))
    painter.setBrush(dark)
    painter.drawRoundedRect(5.0, 11.2, 5.0, 9.3, 1.0, 1.0)
    painter.setPen(QPen(dark, 1.5, Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(accent)
    painter.drawRoundedRect(12.0, 11.0, 10.0, 10.0, 1.7, 1.7)
    painter.setPen(QPen(dark, 1.3, Qt.SolidLine, Qt.RoundCap))
    for y in (14.0, 17.0):
        painter.drawLine(QPointF(14.4, y), QPointF(19.6, y))
    return _finish(pixmap, painter)
