from unittest.mock import Mock, patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QPushButton

from src.poetore.poe2.desecration_ocr import ChoiceBand
from src.poetore.poe2.desecration_overlay import (
    CATEGORY_LABELS,
    STATUS_LABELS,
    CategoryChoiceOverlay,
    DesecrationTierController,
    DesecrationTierOverlay,
    normalized_capture_rect,
    selectable_categories,
    should_retry_closed_region,
    tier_badge_label,
)
from src.poetore.poe2.ndlocr_lite import NdlOcrResult


class RecordingTrace:
    def __init__(self):
        self.records = []

    def mark(self, event, **details):
        self.records.append((event, details))


class ImmediateThread:
    def __init__(self, *, target, args=(), daemon=None):
        self.target = target
        self.args = args

    def start(self):
        self.target(*self.args)


def test_normalized_capture_rect_is_client_relative():
    rect = normalized_capture_rect(QRect(100, 50, 1000, 500), {
        "left": .2, "top": .1, "right": .8, "bottom": .7,
    })
    assert rect == QRect(300, 100, 600, 300)


def test_normalized_capture_rect_rejects_invalid_values():
    assert normalized_capture_rect(QRect(0, 0, 100, 100), None) is None
    assert normalized_capture_rect(QRect(0, 0, 100, 100), {
        "left": .8, "top": 0, "right": .2, "bottom": 1,
    }) is None


def test_category_selector_is_non_modal_and_does_not_accept_focus():
    QApplication.instance() or QApplication([])
    overlay = CategoryChoiceOverlay()
    assert overlay.windowFlags() & Qt.WindowDoesNotAcceptFocus
    assert overlay.testAttribute(Qt.WA_ShowWithoutActivating)
    assert not overlay.isModal()
    overlay.close()


def test_category_selector_excludes_equipment_types_not_implemented_in_poe2():
    QApplication.instance() or QApplication([])
    unavailable = (
        "claw", "dagger", "flail", "one_hand_axe", "one_hand_sword",
        "two_hand_axe", "two_hand_sword",
    )
    assert selectable_categories(("bow", *unavailable, "spear")) == (
        "bow", "spear",
    )

    overlay = CategoryChoiceOverlay()
    overlay.show_categories(("bow", *unavailable, "spear"), QPoint(0, 0))
    labels = {button.text() for button in overlay.findChildren(QPushButton)}
    assert {"弓", "スピア", "閉じる"} <= labels
    assert not labels.intersection({
        "クロー", "ダガー", "フレイル", "片手斧", "片手剣",
        "両手斧", "両手剣",
    })
    overlay.close()


def test_category_selector_uses_distinct_staff_names_and_armour_wording():
    QApplication.instance() or QApplication([])
    assert CATEGORY_LABELS["body_armour"] == "鎧"
    assert CATEGORY_LABELS["staff"] == "スタッフ"
    assert CATEGORY_LABELS["quarterstaff"] == "クォータースタッフ"

    overlay = CategoryChoiceOverlay()
    overlay.show_categories(
        ("body_armour", "staff", "quarterstaff"), QPoint(0, 0),
    )
    labels = {button.text() for button in overlay.findChildren(QPushButton)}
    assert {"鎧", "スタッフ", "クォータースタッフ", "閉じる"} <= labels
    assert "胴体防具" not in labels
    overlay.close()


def test_unresolved_statuses_have_distinct_user_facing_labels():
    assert STATUS_LABELS == {
        "read_failed": "読取失敗",
        "unsupported": "未対応",
        "tierless": "Tierなし",
        "category_unselected": "部位未選択",
    }


def test_multi_tier_badge_lists_only_the_ambiguous_tiers():
    assert tier_badge_label((7, 8), "multiple_tiers") == "T7/T8"
    assert tier_badge_label(10, "matched") == "T10"


def test_affix_candidates_render_with_japanese_labels_and_ranges():
    QApplication.instance() or QApplication([])
    from src.poetore.poe2.desecration_tiers import AffixTierOption

    overlay = DesecrationTierOverlay()
    overlay.show_tiers(
        QRect(0, 0, 800, 360), QRect(60, 30, 600, 300), (600, 300),
        (ChoiceBand(0, 100), ChoiceBand(100, 200), ChoiceBand(200, 300)),
        (3, 7, 9), statuses=("matched",) * 3,
        range_labels=(("",), ("50–64%",), ("8–17",)),
        affix_options=((
            AffixTierOption("prefix", 3, ("8–11%",)),
            AffixTierOption("suffix", 3, ("6–10%",)),
        ), (), ()),
        show_ranges=True,
    )
    image = QImage(overlay.size(), QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    overlay.render(image)

    assert overlay._affix_display_labels(overlay._affix_options[0]) == (
        ("プレフィックス T3", ("8–11%",)),
        ("サフィックス T3", ("6–10%",)),
    )
    overlay.close()


def test_closed_retry_requires_two_independent_readable_open_choices():
    one_readable = Mock(categories=(), fallback_statuses=(
        "matched", "read_failed", "read_failed",
    ))
    two_readable = Mock(categories=(), fallback_statuses=(
        "matched", "unsupported", "read_failed",
    ))
    fully_resolved = Mock(categories=("boots",), fallback_statuses=())
    conflicting = Mock(
        categories=(), category_conflict=True,
        fallback_statuses=("matched", "matched", "unsupported"),
    )

    assert should_retry_closed_region(one_readable)
    assert not should_retry_closed_region(two_readable)
    assert should_retry_closed_region(conflicting)
    assert not should_retry_closed_region(fully_resolved)


def test_controller_tries_open_region_before_optional_closed_region():
    QApplication.instance() or QApplication([])
    valid = QImage("tests/fixtures/poetore/poe2/desecration/boots-reveal.png")
    regions = {
        "inventory_open_region": {"left": 0, "top": 0, "right": .5, "bottom": .5},
        "inventory_closed_region": {"left": .5, "top": .5, "right": 1, "bottom": 1},
    }
    ocr = Mock()
    gate = Mock()
    gate.try_begin.return_value = True
    controller = DesecrationTierController(
        regions_getter=lambda: regions, ocr_server=ocr, scan_coordinator=gate,
    )
    controller._grab = Mock(side_effect=[QImage(), valid])
    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch("src.poetore.poe2.desecration_overlay.threading.Thread"):
        assert controller.request_scan()
    assert controller._grab.call_count == 2
    controller.close()
    ocr.close.assert_not_called()


def test_controller_does_not_try_closed_region_when_open_panel_is_detected():
    QApplication.instance() or QApplication([])
    valid = QImage("tests/fixtures/poetore/poe2/desecration/spear-reveal.png")
    region = {"left": 0, "top": 0, "right": .5, "bottom": .5}
    controller = DesecrationTierController(
        regions_getter=lambda: {
            "inventory_open_region": region,
            "inventory_closed_region": region,
        },
        ocr_server=Mock(), scan_coordinator=Mock(try_begin=Mock(return_value=True)),
    )
    controller._grab = Mock(return_value=valid)
    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch("src.poetore.poe2.desecration_overlay.threading.Thread"):
        assert controller.request_scan()
    controller._grab.assert_called_once()
    controller.close()


def test_controller_retries_closed_region_when_open_panel_ocr_cannot_resolve():
    """A structurally plausible open crop must not suppress the closed fallback."""
    QApplication.instance() or QApplication([])
    open_image = QImage("tests/fixtures/poetore/poe2/desecration/boots-reveal.png")
    closed_image = QImage("tests/fixtures/poetore/poe2/desecration/spear-reveal.png")
    regions = {
        "inventory_open_region": {"left": 0, "top": 0, "right": .5, "bottom": .5},
        "inventory_closed_region": {"left": .5, "top": .5, "right": 1, "bottom": 1},
    }
    unresolved = ["読取不能"] * 12
    resolved = [
        *("この武器によるアタックは20%の火耐性を貫通する",) * 4,
        *("26から43の冷気ダメージを追加する",) * 4,
        *("物理ダメージが28%増加する\n命中力 +57",) * 4,
    ]
    ocr = Mock()
    ocr.recognize.side_effect = [unresolved, resolved]
    gate = Mock()
    gate.try_begin.return_value = True
    controller = DesecrationTierController(
        regions_getter=lambda: regions, ocr_server=ocr, scan_coordinator=gate,
    )
    controller._grab = Mock(side_effect=[open_image, closed_image])

    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch(
        "src.poetore.poe2.desecration_overlay.threading.Thread", ImmediateThread,
    ):
        assert controller.request_scan()
    assert controller._grab.call_count == 2
    assert ocr.recognize.call_count == 2
    assert controller._capture_rect == QRect(960, 540, 960, 540)
    controller.close()


def test_controller_keeps_confident_partial_open_result_without_closed_retry():
    """Two independently readable choices prove that the open region is active."""
    QApplication.instance() or QApplication([])
    image = QImage("tests/fixtures/poetore/poe2/desecration/boots-reveal.png")
    region = {"left": 0, "top": 0, "right": .5, "bottom": .5}
    ocr = Mock()
    ocr.recognize.return_value = [
        *("最大マナ +108",) * 4,
        *("移動スピードが30%増加する",) * 4,
        *("未知の効果が123%増加する",) * 4,
    ]
    controller = DesecrationTierController(
        regions_getter=lambda: {
            "inventory_open_region": region,
            "inventory_closed_region": region,
        },
        ocr_server=ocr,
        scan_coordinator=Mock(try_begin=Mock(return_value=True)),
    )
    controller._grab = Mock(return_value=image)
    controller._overlay.show_tiers = Mock()

    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch(
        "src.poetore.poe2.desecration_overlay.threading.Thread", ImmediateThread,
    ):
        assert controller.request_scan()

    controller._grab.assert_called_once()
    ocr.recognize.assert_called_once()
    assert controller._pending is not None
    assert controller._pending[0].categories == ("boots", "focus", "staff", "wand")
    controller.close()


def test_controller_displays_three_read_failed_badges_when_all_are_unreadable():
    QApplication.instance() or QApplication([])
    image = QImage("tests/fixtures/poetore/poe2/desecration/boots-reveal.png")
    region = {"left": 0, "top": 0, "right": .5, "bottom": .5}
    ocr = Mock()
    ocr.recognize.return_value = ["", "読取不能", "別の誤読", ""] * 3
    gate = Mock()
    gate.try_begin.return_value = True
    controller = DesecrationTierController(
        regions_getter=lambda: {"inventory_open_region": region},
        ocr_server=ocr,
        scan_coordinator=gate,
    )
    controller._grab = Mock(return_value=image)
    controller._overlay.show_tiers = Mock()
    failures = []
    controller.failed.connect(failures.append)

    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch(
        "src.poetore.poe2.desecration_overlay.threading.Thread", ImmediateThread,
    ):
        assert controller.request_scan()

    assert failures == []
    controller._overlay.show_tiers.assert_called_once()
    args = controller._overlay.show_tiers.call_args.args
    kwargs = controller._overlay.show_tiers.call_args.kwargs
    assert args[4] == (None, None, None)
    assert kwargs["statuses"] == ("read_failed",) * 3
    gate.finish.assert_called_once_with("desecration")
    controller.close()


def test_controller_uses_en_us_ocr_only_for_stable_short_missing_integer():
    QApplication.instance() or QApplication([])
    image = QImage(
        "tests/fixtures/poetore/poe2/desecration/"
        "reported-ring-accuracy-read-failed.png"
    )
    region = {"left": 0, "top": 0, "right": .5, "bottom": .5}
    ocr = Mock()
    ocr.recognize.return_value = [
        *("命 中 力 +",) * 4,
        *("最 大 マ ナ + 66",) * 4,
        *("プ レ イ ヤ ー が 生 成 し た レ ム ナ ン ト は 効 果 が 14 % 増 加 す る",) * 4,
    ]
    numeric_ocr = Mock()
    numeric_ocr.recognize.return_value = [
        *("+64",) * 4,
        *("+66",) * 4,
        *("",) * 4,
    ]
    controller = DesecrationTierController(
        regions_getter=lambda: {"inventory_open_region": region},
        ocr_server=ocr,
        numeric_ocr_server=numeric_ocr,
        scan_coordinator=Mock(try_begin=Mock(return_value=True)),
    )
    controller._grab = Mock(return_value=image)

    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch(
        "src.poetore.poe2.desecration_overlay.threading.Thread", ImmediateThread,
    ):
        assert controller.request_scan()

    numeric_ocr.start.assert_called_once_with()
    numeric_ocr.recognize.assert_called_once()
    assert controller._pending is not None
    assert controller._pending[0].tiers_by_category["ring"] == (6, 7, 1)
    controller.close()


def test_controller_uses_ndl_only_for_stable_unresolved_numeric_gap():
    QApplication.instance() or QApplication([])
    image = QImage(
        "tests/fixtures/poetore/poe2/desecration/"
        "reported-spear-physical-read-failed.png"
    )
    region = {"left": 0, "top": 0, "right": .5, "bottom": .5}
    ocr = Mock()
    ocr.recognize.return_value = [
        *("物 理 ダ メ ー ジ が % 増 加 す る",) * 4,
        *("1 か ら 4 の 雷 ダ メ ー ジ を 追 加 す る",) * 4,
        *("物 理 ダ メ ー ジ が 24 % 増 加 す る\n命 中 力 + 41",) * 4,
    ]
    ndl_ocr = Mock()
    ndl_ocr.recognize.return_value = [
        NdlOcrResult("物理ダメージが64%増加する", .874),
    ]
    controller = DesecrationTierController(
        regions_getter=lambda: {"inventory_open_region": region},
        ocr_server=ocr,
        ndl_ocr_server=ndl_ocr,
        scan_coordinator=Mock(try_begin=Mock(return_value=True)),
    )
    controller._grab = Mock(return_value=image)
    controller._display = Mock()

    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch(
        "src.poetore.poe2.desecration_overlay.threading.Thread", ImmediateThread,
    ):
        assert controller.request_scan()

    ndl_ocr.recognize.assert_called_once()
    assert len(ndl_ocr.recognize.call_args.args[0]) == 1
    controller._display.assert_called_once()
    assert controller._display.call_args.args[3] == (7, 10, 7)
    controller.close()


def test_controller_does_not_run_ndl_when_windows_already_resolved_all_choices():
    QApplication.instance() or QApplication([])
    image = QImage(
        "tests/fixtures/poetore/poe2/desecration/"
        "reported-spear-companion-wrapped.png"
    )
    ocr = Mock()
    ocr.recognize.return_value = [
        *("6 か ら 9 の 物 理 ダ メ ー ジ を 追 加 す る",) * 4,
        *("1 か ら 5 の 雷 ダ メ ー ジ を 追 加 す る",) * 4,
        *(
            (
                "コ ン パ ニ オ ン の ダ メ ー ジ が 49 % 増 加 す る\n"
                "コ ン パ ニ オ ン が プ レ イ ヤ ー の 存 在 下 に い る 時 に "
                "ダ メ ー ジ が 51 % 増\n加 す る"
            ),
        ) * 4,
    ]
    ndl_ocr = Mock()
    controller = DesecrationTierController(
        regions_getter=lambda: {
            "inventory_open_region": {"left": 0, "top": 0, "right": .5, "bottom": .5},
        },
        ocr_server=ocr,
        ndl_ocr_server=ndl_ocr,
        scan_coordinator=Mock(try_begin=Mock(return_value=True)),
    )
    controller._grab = Mock(return_value=image)
    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch(
        "src.poetore.poe2.desecration_overlay.threading.Thread", ImmediateThread,
    ):
        assert controller.request_scan()

    ndl_ocr.recognize.assert_not_called()
    controller.close()


def test_controller_records_sanitized_stage_timings_until_overlay_display():
    QApplication.instance() or QApplication([])
    image = QImage("tests/fixtures/poetore/poe2/desecration/spear-reveal.png")
    region = {"left": 0, "top": 0, "right": .5, "bottom": .5}
    raw_ocr = [
        *("この武器によるアタックは20%の火耐性を貫通する",) * 4,
        *("26から43の冷気ダメージを追加する",) * 4,
        *("物理ダメージが28%増加する\n命中力 +57",) * 4,
    ]
    trace = RecordingTrace()
    ocr = Mock()
    ocr.recognize.return_value = raw_ocr
    controller = DesecrationTierController(
        regions_getter=lambda: {"inventory_open_region": region},
        ocr_server=ocr,
        scan_coordinator=Mock(try_begin=Mock(return_value=True)),
        trace_factory=lambda: trace,
    )
    controller._grab = Mock(return_value=image)
    controller._overlay.show_tiers = Mock()

    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch(
        "src.poetore.poe2.desecration_overlay.threading.Thread", ImmediateThread,
    ):
        assert controller.request_scan()
    assert controller._pending is not None
    controller._category_selected(controller._pending[0].categories[0])

    events = [event for event, _details in trace.records]
    assert events == [
        "scan_requested",
        "scan_gate_acquired",
        "client_rect_resolved",
        "capture_region_resolved",
        "capture_completed",
        "frame_preparation_completed",
        "worker_started",
        "image_encoding_completed",
        "ocr_start_completed",
        "ocr_recognition_completed",
        "tier_resolution_completed",
        "result_queued",
        "result_received",
        "category_choice_displayed",
        "category_selected",
        "overlay_displayed",
        "scan_completed",
    ]
    serialized = repr(trace.records)
    assert all(text not in serialized for text in raw_ocr)
    assert trace.records[9][1]["nonempty_result_count"] == 12
    assert trace.records[9][1]["character_count"] > 0
    assert trace.records[-1][1]["outcome"] == "displayed"
    controller.close()


def test_controller_records_closed_region_fallback_as_separate_attempt():
    QApplication.instance() or QApplication([])
    open_image = QImage("tests/fixtures/poetore/poe2/desecration/boots-reveal.png")
    closed_image = QImage("tests/fixtures/poetore/poe2/desecration/spear-reveal.png")
    region = {"left": 0, "top": 0, "right": .5, "bottom": .5}
    trace = RecordingTrace()
    ocr = Mock()
    ocr.recognize.side_effect = [
        ["読取不能"] * 12,
        [
            *("この武器によるアタックは20%の火耐性を貫通する",) * 4,
            *("26から43の冷気ダメージを追加する",) * 4,
            *("物理ダメージが28%増加する\n命中力 +57",) * 4,
        ],
    ]
    controller = DesecrationTierController(
        regions_getter=lambda: {
            "inventory_open_region": region,
            "inventory_closed_region": region,
        },
        ocr_server=ocr,
        scan_coordinator=Mock(try_begin=Mock(return_value=True)),
        trace_factory=lambda: trace,
    )
    controller._grab = Mock(side_effect=[open_image, closed_image])
    controller._overlay.show_tiers = Mock()

    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch(
        "src.poetore.poe2.desecration_overlay.threading.Thread", ImmediateThread,
    ):
        assert controller.request_scan()
    assert controller._pending is not None
    controller._category_selected(controller._pending[0].categories[0])

    records = trace.records
    fallbacks = [details for event, details in records if event == "closed_fallback_requested"]
    assert fallbacks == [{"reason": "open_result_unresolved"}]
    assert [
        details["capture_mode"] for event, details in records
        if event == "ocr_recognition_completed"
    ] == ["open", "closed"]
    assert records[-1] == ("scan_completed", {"outcome": "displayed"})
    controller.close()


def test_controller_records_failure_stage_without_user_facing_message():
    QApplication.instance() or QApplication([])
    trace = RecordingTrace()
    controller = DesecrationTierController(
        regions_getter=dict,
        ocr_server=Mock(),
        scan_coordinator=Mock(try_begin=Mock(return_value=True)),
        trace_factory=lambda: trace,
    )
    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=None,
    ):
        assert not controller.request_scan()

    assert trace.records[-1] == (
        "scan_completed",
        {"outcome": "failed", "failure_stage": "client_rect"},
    )
    assert "Path of Exileのゲーム画面が見つかりませんでした。" not in repr(trace.records)
    controller.close()


def test_diagnostic_failure_never_blocks_the_scan_error_path():
    QApplication.instance() or QApplication([])
    broken_trace = Mock()
    broken_trace.mark.side_effect = OSError("read-only diagnostic folder")
    controller = DesecrationTierController(
        regions_getter=dict,
        ocr_server=Mock(),
        scan_coordinator=Mock(try_begin=Mock(return_value=True)),
        trace_factory=lambda: broken_trace,
    )
    failures = []
    controller.failed.connect(failures.append)

    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=None,
    ):
        assert not controller.request_scan()

    assert failures == ["Path of Exileのゲーム画面が見つかりませんでした。"]
    controller.close()


def test_controller_rejects_repeated_scan_while_current_scan_is_running():
    QApplication.instance() or QApplication([])
    image = QImage("tests/fixtures/poetore/poe2/desecration/boots-reveal.png")
    region = {"left": 0, "top": 0, "right": .5, "bottom": .5}
    gate = Mock()
    gate.try_begin.return_value = True
    controller = DesecrationTierController(
        regions_getter=lambda: {"inventory_open_region": region},
        ocr_server=Mock(), scan_coordinator=gate,
    )
    controller._grab = Mock(return_value=image)
    with patch(
        "src.poetore.poe2.desecration_overlay.path_of_exile_client_rect",
        return_value=QRect(0, 0, 1920, 1080),
    ), patch("src.poetore.poe2.desecration_overlay.threading.Thread"):
        assert controller.request_scan()
        assert not controller.request_scan()

    gate.try_begin.assert_called_once_with("desecration")
    controller.close()


def test_stale_async_result_cannot_replace_a_newer_scan_or_release_its_gate():
    QApplication.instance() or QApplication([])
    gate = Mock()
    controller = DesecrationTierController(ocr_server=Mock(), scan_coordinator=gate)
    controller._scan_generation = 2
    controller._running = True
    controller._display = Mock()

    controller._show_result(
        Mock(), QRect(0, 0, 1920, 1080), QRect(100, 100, 600, 300),
        (ChoiceBand(0, 100), ChoiceBand(100, 200), ChoiceBand(200, 300)), 1,
    )

    controller._display.assert_not_called()
    gate.finish.assert_not_called()
    assert controller.running
    controller.close()


def test_tier_ranges_render_outside_the_registered_panel():
    QApplication.instance() or QApplication([])
    overlay = DesecrationTierOverlay()
    client = QRect(0, 0, 800, 360)
    capture = QRect(60, 30, 600, 300)
    overlay.show_tiers(
        client, capture, (600, 300),
        (ChoiceBand(0, 100), ChoiceBand(100, 200), ChoiceBand(200, 300)),
        (1, 5, 6),
        statuses=("matched", "matched", "matched"),
        range_labels=(("15–25%",), ("22–29", "34–44"), ("25–34%", "47–72")),
        show_ranges=True,
    )
    image = QImage(overlay.size(), QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    overlay.render(image)
    outside_left = capture.right() + 1
    assert any(
        image.pixelColor(x, y).alpha() > 0
        for y in range(image.height())
        for x in range(outside_left, image.width())
    )
    overlay.close()


def test_controller_shows_tier_ranges_by_default_and_preserves_explicit_off():
    QApplication.instance() or QApplication([])
    bands = (ChoiceBand(0, 100), ChoiceBand(100, 200), ChoiceBand(200, 300))
    client = QRect(0, 0, 800, 360)
    capture = QRect(60, 30, 600, 300)
    for config, expected in (({}, True), ({"show_tier_ranges": False}, False)):
        controller = DesecrationTierController(
            regions_getter=lambda value=config: value, ocr_server=Mock(),
        )
        controller._overlay.show_tiers = Mock()
        controller._display(
            client, capture, bands, (1, 5, 6),
            statuses=("matched",) * 3,
            range_labels=(("15–25%",), ("22–29", "34–44"), ("25–34%",)),
        )
        assert controller._overlay.show_tiers.call_args.kwargs["show_ranges"] is expected
        controller.close()


def test_category_cancel_displays_explicit_unselected_state():
    QApplication.instance() or QApplication([])
    controller = DesecrationTierController(ocr_server=Mock())
    controller._display = Mock()
    bands = (ChoiceBand(0, 10), ChoiceBand(10, 20), ChoiceBand(20, 30))
    controller._pending = (Mock(), QRect(0, 0, 800, 600), QRect(100, 100, 500, 300), bands)
    controller._category_cancelled()
    assert controller._pending is None
    assert controller._display.call_args.kwargs["statuses"] == (
        "category_unselected", "category_unselected", "category_unselected",
    )
    controller.close()
