from src.utils.stash_tab_scroll import StashTabScrollController, is_stash_area


def test_awakened_stash_area_ratio_is_used():
    rect = (100, 200, 1920, 1080)
    assert is_stash_area(300, 400, rect)
    assert not is_stash_area(900, 400, rect)
    assert not is_stash_area(300, 250, rect)
    assert not is_stash_area(300, 400, None)


def test_ctrl_wheel_outside_stash_sends_one_directional_key():
    tapped = []
    controller = StashTabScrollController(
        foreground_window=lambda: 123,
        is_poe_window=lambda _hwnd: True,
        window_rect=lambda _hwnd: (0, 0, 1920, 1080),
        ctrl_pressed=lambda: True,
        tap_key=tapped.append,
    )

    controller.handle_scroll(1200, 500, 0, 1)
    controller.handle_scroll(1200, 500, 0, -1)

    assert tapped == ["left", "right"]


def test_scroll_is_ignored_when_disabled_ctrl_released_or_poe_inactive():
    tapped = []
    variants = (
        StashTabScrollController(
            enabled=False,
            foreground_window=lambda: 123,
            is_poe_window=lambda _hwnd: True,
            ctrl_pressed=lambda: True,
            tap_key=tapped.append,
        ),
        StashTabScrollController(
            foreground_window=lambda: 123,
            is_poe_window=lambda _hwnd: True,
            ctrl_pressed=lambda: False,
            tap_key=tapped.append,
        ),
        StashTabScrollController(
            foreground_window=lambda: 123,
            is_poe_window=lambda _hwnd: False,
            ctrl_pressed=lambda: True,
            tap_key=tapped.append,
        ),
    )
    for controller in variants:
        controller.handle_scroll(1200, 500, 0, -1)

    assert tapped == []


def test_scroll_inside_stash_is_left_to_poe_native_handling():
    tapped = []
    controller = StashTabScrollController(
        foreground_window=lambda: 123,
        is_poe_window=lambda _hwnd: True,
        window_rect=lambda _hwnd: (0, 0, 1920, 1080),
        ctrl_pressed=lambda: True,
        tap_key=tapped.append,
    )

    controller.handle_scroll(300, 500, 0, -1)

    assert tapped == []
