from pathlib import Path

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from src.ui.cheat_sheets import (
    CheatSheetManagerDialog,
    CheatSheetOverlay,
    import_cheat_sheet_image,
    normalized_cheat_sheet_config,
    registered_image_path,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _write_test_image(path: Path):
    image = QImage(80, 40, QImage.Format_ARGB32)
    image.fill(QColor("#55aa77"))
    assert image.save(str(path))


def test_import_copies_image_into_user_data_with_uuid_name(tmp_path, monkeypatch):
    user_data = tmp_path / "user-data"
    source = tmp_path / "syndicate.png"
    _write_test_image(source)
    monkeypatch.setenv("POENAVI_USER_DATA_DIR", str(user_data))

    record = import_cheat_sheet_image(source)

    destination = registered_image_path(record)
    assert destination.parent == user_data / "cheat_sheets"
    assert destination.exists()
    assert destination.read_bytes() == source.read_bytes()
    assert record["name"] == "syndicate"
    assert record["filename"] != source.name


def test_registered_path_never_escapes_cheat_sheet_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("POENAVI_USER_DATA_DIR", str(tmp_path))
    path = registered_image_path({"filename": "../../outside.png"})
    assert path == tmp_path / "cheat_sheets" / "outside.png"


def test_normalization_selects_first_available_image():
    config = normalized_cheat_sheet_config(
        {
            "selected_id": "missing",
            "images": [
                {"id": "first", "name": "A", "filename": "a.png"},
                {"id": "second", "name": "B", "filename": "b.png"},
            ],
        }
    )
    assert config["selected_id"] == "first"


def test_empty_overlay_guides_user_to_main_window_button(qapp):
    overlay = CheatSheetOverlay({"images": []})

    assert "画像が登録されていません" in overlay.image_label.text()
    assert "🖼" in overlay.image_label.text()
    assert "画像を登録してください" in overlay.image_label.text()
    assert "rgba(0, 0, 0, 205)" in overlay.image_label.styleSheet()
    assert "font-size: 20px" in overlay.image_label.styleSheet()
    assert "画像タイトルをドラッグで移動" in overlay.title_label.text()
    overlay.close()


def test_manager_cancel_removes_only_newly_imported_files(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("POENAVI_USER_DATA_DIR", str(tmp_path / "user-data"))
    existing_source = tmp_path / "existing.png"
    new_source = tmp_path / "new.png"
    _write_test_image(existing_source)
    _write_test_image(new_source)
    existing = import_cheat_sheet_image(existing_source)
    new = import_cheat_sheet_image(new_source)
    dialog = CheatSheetManagerDialog({"images": [existing]})
    dialog.value["images"].append(new)
    dialog._new_records.append(new)

    dialog.reject()

    assert registered_image_path(existing).exists()
    assert not registered_image_path(new).exists()


def test_overlay_switches_images_and_saves_geometry(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("POENAVI_USER_DATA_DIR", str(tmp_path / "user-data"))
    first_source = tmp_path / "first.png"
    second_source = tmp_path / "second.png"
    _write_test_image(first_source)
    _write_test_image(second_source)
    first = import_cheat_sheet_image(first_source)
    second = import_cheat_sheet_image(second_source)
    overlay = CheatSheetOverlay(
        {
            "images": [first, second],
            "selected_id": first["id"],
            "position": {"x": 20, "y": 30},
            "position_initialized": True,
            "width": 500,
            "height": 350,
            "opacity": 80,
        }
    )
    saved = []
    overlay.config_changed.connect(saved.append)

    overlay.step_image(1)
    assert "background: transparent" in overlay.image_label.styleSheet()
    overlay.setGeometry(40, 50, 600, 420)
    overlay.hide_and_save()

    assert overlay.config["selected_id"] == second["id"]
    assert overlay.title_label.text() == "second（画像タイトルをドラッグで移動）"
    assert saved[-1]["position"] == {"x": 40, "y": 50}
    assert saved[-1]["width"] == 600
    assert saved[-1]["height"] == 420
    assert saved[-1]["position_initialized"] is True
    overlay.close()


def test_first_display_is_top_center_of_poe_monitor(qapp, monkeypatch):
    screens = QApplication.screens()
    assert screens
    target_screen = screens[0]
    available = target_screen.availableGeometry()
    monkeypatch.setattr(
        "src.ui.cheat_sheets.path_of_exile_client_rect",
        lambda: QRect(available.left(), available.top(), available.width(), available.height()),
    )

    overlay = CheatSheetOverlay(
        {
            "images": [],
            "position_initialized": False,
            "width": 900,
            "height": 650,
        }
    )

    assert overlay.geometry().center().x() == available.center().x()
    assert overlay.geometry().top() == available.top() + round(available.height() * 0.10)
    overlay.close()
