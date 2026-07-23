"""ゾーン・街エリアのマスタデータ管理。"""

import json
import os
import sys

from src.utils.poe_version_data import POE1, POE2, get_town_zones
from src.utils.zone_data_poe2 import DEFAULT_ZONE_DATA_POE2

ZONE_MASTER_FILE = os.path.join("data", "zone_data.json")
_ZONE_MASTER_CACHE: tuple[str, int, dict] | None = None


def get_zone_master_dir() -> str:
    """マスタデータの基準ディレクトリ（exeフォルダ優先 → _MEIPASS）。"""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        exe_data_path = os.path.join(exe_dir, ZONE_MASTER_FILE)
        if os.path.exists(exe_data_path):
            return exe_dir
        return getattr(sys, "_MEIPASS", exe_dir)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_zone_master_path() -> str:
    return os.path.join(get_zone_master_dir(), ZONE_MASTER_FILE)


def default_zone_master_data() -> dict:
    return {
        "zone_data_by_version": {
            POE1: {},
            POE2: DEFAULT_ZONE_DATA_POE2,
        },
        "town_zones_by_version": {
            POE1: get_town_zones(POE1),
            POE2: get_town_zones(POE2),
        },
    }


def load_zone_master_data() -> dict:
    """data/zone_data.json を読み込む。なければコード内デフォルトを返す。"""
    global _ZONE_MASTER_CACHE
    path = get_zone_master_path()
    default = default_zone_master_data()
    try:
        modified_ns = os.stat(path).st_mtime_ns
    except OSError:
        return default

    if _ZONE_MASTER_CACHE and _ZONE_MASTER_CACHE[:2] == (path, modified_ns):
        return _ZONE_MASTER_CACHE[2]
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ZoneMasterData] Failed to load: {e}")
        return default

    result = {
        "zone_data_by_version": data.get("zone_data_by_version", default["zone_data_by_version"]),
        "town_zones_by_version": data.get("town_zones_by_version", default["town_zones_by_version"]),
    }
    _ZONE_MASTER_CACHE = (path, modified_ns, result)
    return result


def save_zone_master_data(zone_data_by_version: dict, town_zones_by_version: dict) -> None:
    """ゾーン・街エリアのマスタデータを保存する。"""
    global _ZONE_MASTER_CACHE
    path = get_zone_master_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "zone_data_by_version": zone_data_by_version,
        "town_zones_by_version": town_zones_by_version,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    _ZONE_MASTER_CACHE = None
    print(f"[ZoneMasterData] Saved: {path}")


def load_zone_data_by_version() -> dict:
    return load_zone_master_data()["zone_data_by_version"]


def load_town_zones_by_version() -> dict:
    return load_zone_master_data()["town_zones_by_version"]
