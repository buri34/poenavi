import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QGroupBox

from src.ui.settings_dialog import GuideEditorDialog


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_entering_flooded_depths_sets_the_new_progress_flag():
    source = (ROOT / "src/ui/main_window.py").read_text(encoding="utf-8")

    assert 'if zone_id == "act1_area9":' in source
    assert 'self.set_progress_flag("act1_floodeddepths_enter")' in source
    assert "act1_lowerprison_enter" not in source


def test_submerged_passage_has_only_the_new_flag_editor_section():
    guide_data = json.loads((ROOT / "guide_data.json").read_text(encoding="utf-8"))
    flags = guide_data["act1_area4"]["visits"]["1"]["flags"]

    assert set(flags) == {"act1_floodeddepths_enter"}
    assert isinstance(flags["act1_floodeddepths_enter"], dict)


def test_submerged_passage_editor_displays_the_new_flag_section(qapp):
    guide_data = json.loads((ROOT / "guide_data.json").read_text(encoding="utf-8"))
    guide = guide_data["act1_area4"]["visits"]["1"]
    dialog = GuideEditorDialog(
        None,
        "海底通路 (act1_area4)",
        guide,
        zone_id="act1_area4",
        flag_guides=guide["flags"],
    )

    group_titles = [group.title() for group in dialog.findChildren(QGroupBox)]

    assert "act1_floodeddepths_enter" in group_titles
    assert "act1_lowerprison_enter" not in group_titles
    dialog.close()
