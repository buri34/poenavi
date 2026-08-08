import json

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from src.ui.settings_dialog import (
    SettingsDialog,
    _act1_guide_dev_editor_enabled,
    _guide_dev_editor_enabled,
)
from src.utils import guide_data
from src.utils.poe_version_data import POE1, POE2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_act1_guide_editor_is_hidden_without_dev_environment(monkeypatch):
    monkeypatch.delenv("POENAVI_ACT1_GUIDE_DEV", raising=False)

    assert not _act1_guide_dev_editor_enabled(POE1, "act1_area1")


def test_act1_guide_editor_is_limited_to_poe1_act1(monkeypatch):
    monkeypatch.setenv("POENAVI_ACT1_GUIDE_DEV", "1")

    assert _act1_guide_dev_editor_enabled(POE1, "act1_area1")
    assert not _act1_guide_dev_editor_enabled(POE1, "act2_area1")
    assert not _act1_guide_dev_editor_enabled(POE2, "poe2_act1_area1")


def test_settings_shows_act1_editor_buttons_only_in_dev_mode(monkeypatch, qapp):
    monkeypatch.setenv("POENAVI_ACT1_GUIDE_DEV", "1")
    dialog = SettingsDialog(current_config={"poe_version": POE1})

    tooltips = [button.toolTip() for button in dialog.findChildren(QPushButton)]

    assert tooltips.count("公式ガイドを編集") == 15
    assert tooltips.count("みになびを編集") == 15
    dialog.close()


def test_settings_hides_official_editor_buttons_in_normal_mode(monkeypatch, qapp):
    monkeypatch.delenv("POENAVI_ACT1_GUIDE_DEV", raising=False)
    monkeypatch.delenv("POENAVI_GUIDE_DEV_ZONE_ID", raising=False)
    dialog = SettingsDialog(current_config={"poe_version": POE1})

    tooltips = [button.toolTip() for button in dialog.findChildren(QPushButton)]
    assert "公式ガイドを編集" not in tooltips
    assert "みになびを編集" not in tooltips
    dialog.close()


def test_settings_shows_three_poe2_guide_editors_in_dev_mode(monkeypatch, qapp):
    monkeypatch.setenv("POENAVI_POE2_GUIDE_DEV", "1")
    dialog = SettingsDialog(current_config={"poe_version": POE2})

    tooltips = [button.toolTip() for button in dialog.findChildren(QPushButton)]
    detail_count = tooltips.count("詳細版ガイドを編集")
    summary_count = tooltips.count("要約版ガイドを編集")
    mini_count = tooltips.count("みになびを編集")

    assert detail_count > 0
    assert detail_count == summary_count == mini_count
    dialog.close()


def test_settings_hides_poe2_guide_editors_outside_dev_mode(monkeypatch, qapp):
    monkeypatch.delenv("POENAVI_POE2_GUIDE_DEV", raising=False)
    dialog = SettingsDialog(current_config={"poe_version": POE2})

    tooltips = [button.toolTip() for button in dialog.findChildren(QPushButton)]
    assert "詳細版ガイドを編集" not in tooltips
    assert "要約版ガイドを編集" not in tooltips
    assert "みになびを編集" not in tooltips
    dialog.close()


def test_poe2_mini_navi_editor_updates_default_and_flag_sections(monkeypatch, qapp):
    monkeypatch.setenv("POENAVI_POE2_GUIDE_DEV", "1")
    dialog = SettingsDialog(current_config={"poe_version": POE2})
    dialog.guide_data = {
        "poe2_act1_area02": {
            "default": {"objective": "通常"},
            "flags": {"boss_done": {"objective": "ボス後"}},
        }
    }
    captured = {}

    class FakeMiniEditor:
        def __init__(self, _parent, _title, sections):
            captured["sections"] = sections

        def exec(self):
            return True

        def apply_to_sections(self):
            for section in captured["sections"]:
                section["guide"]["mini_navi"] = {
                    "text": section["title"],
                    "direction": "e",
                }

    monkeypatch.setattr(
        "src.ui.settings_dialog.MiniNaviEditorDialog", FakeMiniEditor,
    )
    monkeypatch.setattr(
        "src.ui.settings_dialog.save_guide_data", lambda *_args: None,
    )

    name_edit = QLineEdit("クリアフェル")
    dialog._open_mini_navi_editor(name_edit, "poe2_act1_area02")

    entry = dialog.guide_data["poe2_act1_area02"]
    assert entry["default"]["mini_navi"]["text"] == "通常時"
    assert entry["flags"]["boss_done"]["mini_navi"]["text"] == "フラグ進行後: boss_done"
    assert len(captured["sections"]) == 2
    dialog.close()


def test_settings_shows_only_requested_act10_guide_editor(monkeypatch, qapp):
    monkeypatch.delenv("POENAVI_ACT1_GUIDE_DEV", raising=False)
    monkeypatch.setenv("POENAVI_GUIDE_DEV_ZONE_ID", "act10_area12")

    assert _guide_dev_editor_enabled(POE1, "act10_area12")
    assert not _guide_dev_editor_enabled(POE1, "act10_area5")
    assert not _guide_dev_editor_enabled(POE2, "act10_area12")

    dialog = SettingsDialog(current_config={"poe_version": POE1})
    tooltips = [button.toolTip() for button in dialog.findChildren(QPushButton)]
    texts = [button.text() for button in dialog.findChildren(QPushButton)]

    assert tooltips.count("公式ガイドを編集") == 1
    assert tooltips.count("みになびを編集") == 1
    assert texts.count("公式ガイド") == 1
    assert texts.count("みになび") == 1
    dialog.close()


def test_dev_save_creates_backup_before_overwriting(monkeypatch, tmp_path):
    path = tmp_path / "guide_data.json"
    original = {"act1_area1": {"objective": "before"}}
    updated = {"act1_area1": {"objective": "after"}}
    path.write_text(json.dumps(original), encoding="utf-8")

    monkeypatch.setenv("POENAVI_ACT1_GUIDE_DEV", "1")
    monkeypatch.setattr(guide_data, "get_guide_path", lambda version=POE1: str(path))

    guide_data.save_guide_data(updated, POE1)

    backups = list(tmp_path.glob("guide_data.backup-before-guide-edit-*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == original
    assert json.loads(path.read_text(encoding="utf-8")) == updated


def test_normal_save_does_not_create_dev_backup(monkeypatch, tmp_path):
    path = tmp_path / "guide_data.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("POENAVI_ACT1_GUIDE_DEV", raising=False)
    monkeypatch.setattr(guide_data, "get_guide_path", lambda version=POE1: str(path))

    guide_data.save_guide_data({"saved": True}, POE1)

    assert not list(tmp_path.glob("guide_data.backup-before-guide-edit-*.json"))


def test_poe2_dev_save_creates_backup_before_overwriting(monkeypatch, tmp_path):
    path = tmp_path / "guide_data_poe2.json"
    original = {"poe2_act1_area02": {"default": {"objective": "before"}}}
    updated = {"poe2_act1_area02": {"default": {"objective": "after"}}}
    path.write_text(json.dumps(original), encoding="utf-8")

    monkeypatch.setenv("POENAVI_POE2_GUIDE_DEV", "1")
    monkeypatch.setattr(guide_data, "get_guide_path", lambda version=POE2: str(path))

    guide_data.save_guide_data(updated, POE2)

    backups = list(tmp_path.glob("guide_data_poe2.backup-before-guide-edit-*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == original


def test_requested_zone_dev_save_creates_backup(monkeypatch, tmp_path):
    path = tmp_path / "guide_data.json"
    original = {"act10_area12": {"objective": "before"}}
    updated = {"act10_area12": {"objective": "after"}}
    path.write_text(json.dumps(original), encoding="utf-8")

    monkeypatch.delenv("POENAVI_ACT1_GUIDE_DEV", raising=False)
    monkeypatch.setenv("POENAVI_GUIDE_DEV_ZONE_ID", "act10_area12")
    monkeypatch.setattr(guide_data, "get_guide_path", lambda version=POE1: str(path))

    guide_data.save_guide_data(updated, POE1)

    backups = list(tmp_path.glob("guide_data.backup-before-guide-edit-*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == original
