import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QGroupBox

from src.ui.settings_dialog import GuideEditorDialog


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_entering_act1_submerged_passage_sets_the_new_progress_flag():
    source = (ROOT / "src/ui/main_window.py").read_text(encoding="utf-8")

    assert 'if zone_id == "act1_area4":' in source
    assert 'self.set_progress_flag("act1_submergedpassage_enter")' in source


def test_only_act1_coast_has_the_submerged_passage_flag_section():
    guide_data = json.loads((ROOT / "guide_data.json").read_text(encoding="utf-8"))
    act1_flags = guide_data["act1_area2"]["visits"]["1"]["flags"]
    act6_guide = guide_data["act6_area2"]["visits"]["1"]

    assert set(act1_flags) == {"act1_submergedpassage_enter"}
    assert isinstance(act1_flags["act1_submergedpassage_enter"], dict)
    assert "flags" not in act6_guide


def test_act1_coast_editor_displays_the_new_flag_section(qapp):
    guide_data = json.loads((ROOT / "guide_data.json").read_text(encoding="utf-8"))
    guide = guide_data["act1_area2"]["visits"]["1"]
    dialog = GuideEditorDialog(
        None,
        "海岸 (act1_area2)",
        guide,
        zone_id="act1_area2",
        flag_guides=guide["flags"],
    )

    group_titles = [group.title() for group in dialog.findChildren(QGroupBox)]

    assert "act1_submergedpassage_enter" in group_titles
    dialog.close()
