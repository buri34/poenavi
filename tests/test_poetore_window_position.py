from PySide6.QtCore import QPoint, QRect, QSize

from src.poetore.window_position import (
    PLACEMENT_INVENTORY,
    PLACEMENT_STASH,
    PlacementContext,
    calculate_panel_position,
    placement_side,
    position_from_relative,
    relative_panel_position,
)


def test_cursor_on_right_places_panel_inward_from_inventory():
    position = calculate_panel_position(
        QRect(100, 50, 1920, 1080), QPoint(1700, 400), QSize(860, 720), margin=16,
    )
    assert position == QPoint(494, 50)


def test_cursor_on_left_places_panel_inward_from_stash():
    position = calculate_panel_position(
        QRect(100, 50, 1920, 1080), QPoint(300, 400), QSize(860, 720), margin=16,
    )
    assert position == QPoint(766, 50)


def test_1280p_layout_matches_awakened_horizontal_formula():
    position = calculate_panel_position(
        QRect(0, 0, 1920, 1280), QPoint(1750, 300), QSize(845, 710), margin=16,
    )
    assert position == QPoint(286, 0)


def test_panel_is_clamped_when_target_is_smaller():
    position = calculate_panel_position(
        QRect(-1280, 0, 800, 600), QPoint(-600, 100), QSize(860, 720), margin=16,
    )
    assert position == QPoint(-1264, 0)


def test_placement_side_matches_stash_and_inventory_halves():
    target = QRect(100, 50, 1920, 1080)
    assert placement_side(PlacementContext(target, QPoint(300, 400))) == PLACEMENT_STASH
    assert placement_side(PlacementContext(target, QPoint(1700, 400))) == PLACEMENT_INVENTORY


def test_relative_position_round_trips_in_current_poe_window():
    context = PlacementContext(QRect(100, 50, 1920, 1080), QPoint(300, 400))
    size = QSize(860, 720)
    original = QPoint(630, 230)

    saved = relative_panel_position(context, original, size)

    assert position_from_relative(context, size, saved) == original


def test_relative_position_adapts_to_new_poe_size_and_clamps_ratios():
    context = PlacementContext(QRect(-1920, 0, 1920, 1080), QPoint(-1700, 400))
    size = QSize(860, 720)

    assert position_from_relative(
        context, size, {"x_ratio": 2, "y_ratio": -1},
    ) == QPoint(-860, 0)


def test_invalid_saved_position_falls_back_to_default_caller_path():
    context = PlacementContext(QRect(0, 0, 1920, 1080), QPoint(200, 400))

    assert position_from_relative(context, QSize(860, 720), {"x_ratio": "bad"}) is None
