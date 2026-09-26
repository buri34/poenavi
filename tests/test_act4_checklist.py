import os
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from src.ui.act4_checklist import (
    ACT4_REQUIRED_ITEMS,
    Act4ChecklistState,
    Act4ChecklistWindow,
    is_act4_context,
)
from src.ui.main_window import MainWindow
from src.ui.mini_navi import MiniNaviOverlay
from src.utils.poe_version_data import POE2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_act4_context_includes_kingsmarch_all_areas_and_plunders_point():
    assert is_act4_context("キングスマーチ", None)
    assert is_act4_context("Kingsmarch", None)
    assert is_act4_context("略奪の岬", "poe2_act4_area17")
    assert is_act4_context("部族の中心", "poe2_act4_area16")
    assert not is_act4_context("ジッグラトの野営地", None)
    assert not is_act4_context("未知のエリア", None)


def test_entering_child_checks_all_ancestors():
    state = Act4ChecklistState()

    assert state.mark_entered("poe2_act4_area12")
    assert state.checked_zone_ids == {
        "poe2_act4_area10",
        "poe2_act4_area11",
        "poe2_act4_area12",
    }


def test_manual_parent_off_clears_descendants_and_child_on_checks_parent():
    state = Act4ChecklistState()
    state.set_checked("poe2_act4_area12", True)

    state.set_checked("poe2_act4_area10", False)
    assert not state.checked_zone_ids

    state.set_checked("poe2_act4_area08", True)
    assert state.checked_zone_ids == {"poe2_act4_area07", "poe2_act4_area08"}


def test_state_round_trip_filters_unknown_ids_and_preserves_ui_state():
    state = Act4ChecklistState.from_dict({
        "checked_zone_ids": ["poe2_act4_area01", "poe2_act4_area17", "unknown"],
        "optional_npc_checked": True,
        "dismissed": True,
        "position": {"x": 123, "y": 456},
    })

    assert state.checked_zone_ids == {"poe2_act4_area01"}
    assert state.optional_npc_checked
    assert state.dismissed
    assert state.position == (123, 456)
    assert Act4ChecklistState.from_dict(state.to_dict()) == state


def test_window_uses_final_copy_and_updates_progress(qapp):
    window = Act4ChecklistWindow()
    try:
        state = Act4ChecklistState(
            checked_zone_ids={item.zone_id for item in ACT4_REQUIRED_ITEMS},
            optional_npc_checked=True,
        )
        window.apply_state(state)

        assert window.windowTitle() == "Act4 攻略チェック"
        assert window.progress_label.text() == "14 / 14"
        assert window.complete_label.text() == "✓ Act4の攻略必須エリアをすべて完了済み"
        assert window.complete_label.isVisible() is False  # 親を表示するまではQt上非表示
        assert "ナカヌの装備販売NPCを確認" in window.optional_checkbox.text()
        notes = [label.text() for label in window.findChildren(type(window.complete_label))]
        assert "発掘現場を攻略前に立ち寄る" in notes
    finally:
        window.close()


def test_window_emits_manual_and_close_actions(qapp):
    window = Act4ChecklistWindow()
    required = Mock()
    optional = Mock()
    dismissed = Mock()
    window.required_toggled.connect(required)
    window.optional_toggled.connect(optional)
    window.dismissed_by_user.connect(dismissed)
    try:
        window._checkboxes["poe2_act4_area01"].click()
        window.optional_checkbox.click()
        window.close_button.click()

        required.assert_called_once_with("poe2_act4_area01", True)
        optional.assert_called_once_with(True)
        dismissed.assert_called_once_with()
    finally:
        window.close()


def _main_window_for_zone_updates(zone_ids):
    window = MainWindow.__new__(MainWindow)
    window.poe_version = POE2
    window.config = {"mini_guide_overlay": {"enabled": True}}
    window.zone_data = {
        "Act 4": [
            {"id": zone_id}
            for zone_id in zone_ids.values()
            if zone_id.startswith("poe2_act4_")
        ]
    }
    window.act4_checklist_state = Act4ChecklistState()
    window._act4_context_active = False
    window._get_zone_id = Mock(side_effect=lambda name: zone_ids.get(name))
    window._is_town_zone = Mock(side_effect=lambda name: name in {"キングスマーチ", "ジッグラトの野営地"})
    window._save_progress_flags = Mock()
    window._show_act4_checklist = Mock()
    window._hide_act4_checklist = Mock()
    window.act4_checklist_window = Mock()
    return window


def test_zone_update_marks_required_ancestors_and_auto_shows():
    window = _main_window_for_zone_updates({"祖先の試練": "poe2_act4_area12"})

    MainWindow._update_act4_checklist_for_zone(window, "祖先の試練", True)

    assert window._act4_context_active
    assert window.act4_checklist_state.checked_zone_ids == {
        "poe2_act4_area10",
        "poe2_act4_area11",
        "poe2_act4_area12",
    }
    window._save_progress_flags.assert_called_once_with()
    window._show_act4_checklist.assert_called_once_with()


def test_zone_update_hides_on_known_non_act4_but_ignores_unknown_zone():
    window = _main_window_for_zone_updates({"オガムの農地": "poe2_act1_area05"})
    window._act4_context_active = True

    MainWindow._update_act4_checklist_for_zone(window, "未知の一時エリア", True)
    assert window._act4_context_active
    window._hide_act4_checklist.assert_not_called()

    MainWindow._update_act4_checklist_for_zone(window, "オガムの農地", True)
    assert not window._act4_context_active
    window._hide_act4_checklist.assert_called_once_with()


def test_kingsmarch_is_context_but_dismissed_state_prevents_auto_show():
    window = _main_window_for_zone_updates({})
    window.act4_checklist_state.dismissed = True

    MainWindow._update_act4_checklist_for_zone(window, "キングスマーチ", True)

    assert window._act4_context_active
    window._show_act4_checklist.assert_not_called()
    window._hide_act4_checklist.assert_called_once_with()


def test_mini_navi_act4_button_is_only_visible_in_act4(qapp):
    main = QWidget()
    main.config = {"mini_guide_overlay": {"enabled": True}}
    main.is_act4_checklist_available_context = Mock(return_value=True)
    main.act4_checklist_window = Mock()
    main.act4_checklist_window.isVisible.return_value = True
    main.toggle_act4_checklist = Mock()
    overlay = MiniNaviOverlay(main)
    try:
        overlay.update_content({"text": "ガイド", "direction": "none"})
        overlay.lock_button_window.sync_from_overlay()
        assert overlay.lock_button_window.act4_button.isVisible()
        assert overlay.lock_button_window.act4_button.isChecked()

        overlay.lock_button_window.act4_button.click()
        main.toggle_act4_checklist.assert_called_once_with()

        main.is_act4_checklist_available_context.return_value = False
        overlay.lock_button_window.sync_from_overlay()
        assert not overlay.lock_button_window.act4_button.isVisible()
    finally:
        overlay.lock_button_window.close()
        overlay.close()
        main.close()
