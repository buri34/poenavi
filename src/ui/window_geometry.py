"""Helpers for restoring top-level windows into a visible screen area."""

from __future__ import annotations

import math
from numbers import Real

from PySide6.QtCore import QRect, QSize


def _geometry_number(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    if not math.isfinite(float(value)):
        return None
    return int(value)


def _saved_rect(saved_geometry) -> QRect | None:
    if not isinstance(saved_geometry, dict):
        return None
    values = [
        _geometry_number(saved_geometry.get(key))
        for key in ("x", "y", "width", "height")
    ]
    if any(value is None for value in values):
        return None
    x, y, width, height = values
    if width <= 0 or height <= 0:
        return None
    return QRect(x, y, width, height)


def _intersection_area(first: QRect, second: QRect) -> int:
    intersection = first.intersected(second)
    if intersection.isEmpty():
        return 0
    return intersection.width() * intersection.height()


def fit_saved_window_geometry(
    saved_geometry,
    available_geometries,
    *,
    minimum_width: int = 300,
    minimum_height: int = 120,
) -> QRect | None:
    """Return saved geometry fully contained in one available screen.

    Prefer the screen with the largest real intersection. This avoids treating
    empty gaps inside the union of an L-shaped monitor layout as valid. If the
    window no longer intersects any screen, return ``None`` so the caller can
    apply its normal default placement.
    """
    saved_rect = _saved_rect(saved_geometry)
    screens = [
        QRect(geometry)
        for geometry in available_geometries
        if not geometry.isEmpty()
    ]
    if saved_rect is None or not screens:
        return None

    intersections = [
        (_intersection_area(saved_rect, screen), screen)
        for screen in screens
    ]
    intersection_area, target = max(intersections, key=lambda item: item[0])
    if intersection_area <= 0:
        return None
    size = fit_saved_window_size(
        saved_geometry,
        target,
        minimum_width=minimum_width,
        minimum_height=minimum_height,
    )
    width = size.width()
    height = size.height()
    max_x = target.x() + target.width() - width
    max_y = target.y() + target.height() - height
    x = max(target.x(), min(saved_rect.x(), max_x))
    y = max(target.y(), min(saved_rect.y(), max_y))
    return QRect(x, y, width, height)


def fit_saved_window_size(
    saved_geometry,
    available_geometry: QRect,
    *,
    minimum_width: int = 300,
    minimum_height: int = 120,
) -> QSize | None:
    """Return a valid saved size without reusing its screen coordinates."""
    saved_rect = _saved_rect(saved_geometry)
    if saved_rect is None or available_geometry.isEmpty():
        return None
    return QSize(
        min(max(saved_rect.width(), minimum_width), available_geometry.width()),
        min(max(saved_rect.height(), minimum_height), available_geometry.height()),
    )
