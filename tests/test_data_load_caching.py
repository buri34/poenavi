import json
import os
from pathlib import Path
from unittest.mock import patch

from src.utils import guide_data, zone_master_data
from src.utils.poe_version_data import POE1


def test_load_guide_data_reuses_unchanged_file(tmp_path, monkeypatch):
    path = tmp_path / "guide_data.json"
    path.write_text(json.dumps({"zone": {}}), encoding="utf-8")
    monkeypatch.setattr(
        guide_data,
        "get_guide_path",
        lambda _version, _language="ja": str(path),
    )
    guide_data._GUIDE_DATA_CACHE.clear()

    with patch("builtins.open", wraps=open) as mocked_open:
        guide_data.load_guide_data(POE1)
        guide_data.load_guide_data(POE1)

    assert mocked_open.call_count == 1


def test_load_zone_master_data_reloads_when_file_changes(tmp_path, monkeypatch):
    path = Path(tmp_path) / "zone_data.json"
    path.write_text(json.dumps({"zone_data_by_version": {}, "town_zones_by_version": {}}), encoding="utf-8")
    monkeypatch.setattr(zone_master_data, "get_zone_master_path", lambda: str(path))
    zone_master_data._ZONE_MASTER_CACHE = None

    first = zone_master_data.load_zone_master_data()
    path.write_text(json.dumps({"zone_data_by_version": {"poe1": {"x": "X"}}, "town_zones_by_version": {}}), encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1))

    assert zone_master_data.load_zone_master_data() != first
