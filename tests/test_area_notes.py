import json

import pytest

from src.utils.area_notes import (
    get_area_note,
    notes_filename,
    qt_html_to_storage_html,
    set_area_note,
)
from src.utils.poe_version_data import POE1, POE2


def test_notes_are_stored_per_version_and_zone(monkeypatch, tmp_path):
    monkeypatch.setenv("POENAVI_USER_DATA_DIR", str(tmp_path))

    set_area_note(POE1, "act1_area1", "<span style='color:#ff6666'>赤メモ</span>")
    set_area_note(POE2, "poe2_act1_area1", "PoE2メモ")

    assert "赤メモ" in get_area_note(POE1, "act1_area1")
    assert get_area_note(POE1, "act1_area2") == ""
    assert get_area_note(POE2, "poe2_act1_area1") == "PoE2メモ"
    assert (tmp_path / notes_filename(POE1)).is_file()
    assert (tmp_path / notes_filename(POE2)).is_file()


def test_empty_note_removes_zone_entry(monkeypatch, tmp_path):
    monkeypatch.setenv("POENAVI_USER_DATA_DIR", str(tmp_path))
    set_area_note(POE1, "act1_area1", "memo")
    set_area_note(POE1, "act1_area1", "   ")

    assert get_area_note(POE1, "act1_area1") == ""
    payload = json.loads((tmp_path / notes_filename(POE1)).read_text(encoding="utf-8"))
    assert payload == {"schema": 1, "notes": {}}


def test_broken_notes_file_is_not_silently_overwritten(monkeypatch, tmp_path):
    monkeypatch.setenv("POENAVI_USER_DATA_DIR", str(tmp_path))
    path = tmp_path / notes_filename(POE1)
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(ValueError, match="読み込めません"):
        set_area_note(POE1, "act1_area1", "new memo")

    assert path.read_text(encoding="utf-8") == "not json"


def test_qt_html_conversion_does_not_double_single_line_breaks():
    html = """<html><body>
<p style="margin:0">1行目</p>
<p style="margin:0"><span style=" color:#ff6666;">2行目</span></p>
<p style="margin:0"><br /></p>
<p style="margin:0">4行目</p>
</body></html>"""

    assert qt_html_to_storage_html(html) == (
        "1行目\n<span style='color:#ff6666'>2行目</span>\n\n4行目"
    )
