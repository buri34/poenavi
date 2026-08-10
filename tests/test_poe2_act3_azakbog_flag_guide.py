import copy
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit

from src.ui.settings_dialog import GuideEditorDialog, GuideSummaryEditorDialog, SettingsDialog
from src.utils.guide_data import get_zone_guide
from src.utils.poe_version_data import POE2


FLAG_KEY = "act3_azakbog_enter"
MATLAN_ZONE_ID = "poe2_act3_area09"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def guide_data():
    return json.loads(Path("guide_data_poe2.json").read_text(encoding="utf-8"))


def test_azak_bog_entry_sets_progress_flag():
    source = Path("src/ui/main_window.py").read_text(encoding="utf-8")

    assert 'if zone_id == "poe2_act3_area05":' in source
    assert 'self.set_progress_flag("act3_azakbog_enter")' in source


def test_matlan_waterways_has_all_three_empty_editor_frames(guide_data):
    frame = guide_data[MATLAN_ZONE_ID]["flags"][FLAG_KEY]

    assert {"objective", "layout", "tips", "summary", "mini_navi"} <= frame.keys()
    assert frame["mini_navi"] == {"text": ""}


def test_detail_and_summary_editors_expose_azak_bog_flag_frame(qapp, guide_data):
    entry = copy.deepcopy(guide_data[MATLAN_ZONE_ID])
    flags = entry["flags"]
    detail = GuideEditorDialog(
        None,
        "マトラン水路",
        entry["default"],
        flags[FLAG_KEY],
        zone_id=MATLAN_ZONE_ID,
        flag_guides=flags,
    )
    summary = GuideSummaryEditorDialog(None, "マトラン水路", entry)

    assert detail.primary_flag_key == FLAG_KEY
    assert detail._v2_label_closed == "▶ フラグ進行後のガイド"
    assert FLAG_KEY in summary.flag_editors

    detail.close()
    summary.close()


def test_mini_navi_editor_exposes_azak_bog_flag_frame(monkeypatch, qapp, guide_data):
    dialog = SettingsDialog(current_config={"poe_version": POE2})
    dialog.guide_data = copy.deepcopy(guide_data)
    captured = {}

    class FakeMiniEditor:
        def __init__(self, _parent, _title, sections, *, show_direction=True):
            captured["sections"] = sections
            captured["show_direction"] = show_direction

        def exec(self):
            return False

    monkeypatch.setattr("src.ui.settings_dialog.MiniNaviEditorDialog", FakeMiniEditor)
    dialog._open_mini_navi_editor(QLineEdit("マトラン水路"), MATLAN_ZONE_ID)

    assert [section["title"] for section in captured["sections"]] == [
        "通常時",
        f"フラグ進行後: {FLAG_KEY}",
    ]
    assert captured["show_direction"] is False
    dialog.close()


def test_authored_flag_content_is_selected_for_matlan_waterways(guide_data):
    authored = copy.deepcopy(guide_data)
    authored[MATLAN_ZONE_ID]["flags"][FLAG_KEY]["objective"] = "アザク湿原到達後"

    guide = get_zone_guide(
        authored,
        MATLAN_ZONE_ID,
        active_flags={FLAG_KEY},
    )

    assert guide["objective"] == "アザク湿原到達後"
