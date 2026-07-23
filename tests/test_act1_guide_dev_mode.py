import json

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from src.ui.settings_dialog import SettingsDialog, _act1_guide_dev_editor_enabled
from src.utils import guide_data
from src.utils.i18n import EN, JA, get_locale, set_locale
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
    original_locale = get_locale()
    set_locale(JA)
    try:
        dialog = SettingsDialog(current_config={"poe_version": POE1})

        tooltips = [button.toolTip() for button in dialog.findChildren(QPushButton)]

        assert tooltips.count("Act 1公式ガイドを編集") == 15
        assert tooltips.count("Act 1みになびを編集") == 15
        dialog.close()
    finally:
        set_locale(original_locale)


def test_settings_hides_official_editor_buttons_in_normal_mode(monkeypatch, qapp):
    monkeypatch.delenv("POENAVI_ACT1_GUIDE_DEV", raising=False)
    dialog = SettingsDialog(current_config={"poe_version": POE1})

    tooltips = [button.toolTip() for button in dialog.findChildren(QPushButton)]

    assert "Act 1公式ガイドを編集" not in tooltips
    assert "Act 1みになびを編集" not in tooltips
    dialog.close()


def test_settings_translates_act1_editor_tooltips_in_english(monkeypatch, qapp):
    monkeypatch.setenv("POENAVI_ACT1_GUIDE_DEV", "1")
    original_locale = get_locale()
    set_locale(EN)
    try:
        dialog = SettingsDialog(current_config={"poe_version": POE1})
        tooltips = [button.toolTip() for button in dialog.findChildren(QPushButton)]

        assert tooltips.count("Edit the official Act 1 guide") == 15
        assert tooltips.count("Edit Act 1 mini navigation") == 15
        dialog.close()
    finally:
        set_locale(original_locale)


def test_dev_save_creates_backup_before_overwriting(monkeypatch, tmp_path):
    path = tmp_path / "guide_data.json"
    original = {"act1_area1": {"objective": "before"}}
    updated = {"act1_area1": {"objective": "after"}}
    path.write_text(json.dumps(original), encoding="utf-8")

    monkeypatch.setenv("POENAVI_ACT1_GUIDE_DEV", "1")
    monkeypatch.setattr(
        guide_data,
        "get_guide_path",
        lambda version=POE1, language="ja": str(path),
    )

    guide_data.save_guide_data(updated, POE1)

    backups = list(tmp_path.glob("guide_data.backup-before-act1-guide-edit-*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == original
    assert json.loads(path.read_text(encoding="utf-8")) == updated


def test_normal_save_does_not_create_dev_backup(monkeypatch, tmp_path):
    path = tmp_path / "guide_data.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("POENAVI_ACT1_GUIDE_DEV", raising=False)
    monkeypatch.setattr(
        guide_data,
        "get_guide_path",
        lambda version=POE1, language="ja": str(path),
    )

    guide_data.save_guide_data({"saved": True}, POE1)

    assert not list(tmp_path.glob("guide_data.backup-before-act1-guide-edit-*.json"))
