import pytest

from scripts.generate_windows_version_info import render_version_info, version_tuple


def test_version_tuple_adds_windows_revision_component():
    assert version_tuple("3.3.8") == (3, 3, 8, 0)


@pytest.mark.parametrize("value", ["3.3", "3.3.8.1", "v3.3.8", "3.x.8"])
def test_version_tuple_rejects_non_release_versions(value):
    with pytest.raises(ValueError):
        version_tuple(value)


def test_render_version_info_sets_signpath_required_metadata():
    text = render_version_info(
        version="3.3.8",
        description="PoENavi Updater",
        original_filename="PoENaviUpdater.exe",
    )
    assert "filevers=(3, 3, 8, 0)" in text
    assert "prodvers=(3, 3, 8, 0)" in text
    assert "StringStruct('ProductName', 'PoENavi')" in text
    assert "StringStruct('ProductVersion', '3.3.8')" in text
    assert "StringStruct('OriginalFilename', 'PoENaviUpdater.exe')" in text
    assert "StringStruct('FileDescription', 'PoENavi Updater')" in text
