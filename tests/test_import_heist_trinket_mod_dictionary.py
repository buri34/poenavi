import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path("scripts/import_heist_trinket_mod_dictionary.py")
SPEC = importlib.util.spec_from_file_location("import_heist_trinket_mod_dictionary", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _entry(index: int, *, active: bool = True) -> dict:
    return {
        "availability": "active" if active else "legacy",
        "status": "searchable",
        "trade_stat_id": f"explicit.stat_{index}",
        "text_ja": f"Mod {index} が#%増加する",
        "active_valid_ranges": [
            {"values": [{"stat_internal_id": f"stat_{index}", "min": 1, "max": 3}]}
        ],
    }


def test_build_runtime_payload_keeps_only_39_active_searchable_mods():
    source = {
        "generated_at": "2026-09-30T00:00:00+00:00",
        "base": "Thief's Trinket",
        "sources": {
            "repoe_mods": {"sha256": "abc"},
            "trade_stats_en": {"sha256": "def"},
            "trade_stats_ja": {"sha256": "ghi"},
        },
        "entries": [_entry(index) for index in range(39)] + [_entry(99, active=False)],
    }

    payload = MODULE.build_runtime_payload(source)

    assert payload["schema_version"] == 1
    assert payload["base_type_ja"] == "盗賊のトリンケット"
    assert payload["source"]["repoe_mods"]["sha256"] == "abc"
    assert len(payload["mods"]) == 39
    assert payload["mods"][0]["valid_values"] == [1, 2, 3]


def test_build_runtime_payload_rejects_incomplete_candidate_set():
    with pytest.raises(ValueError, match="39種類"):
        MODULE.build_runtime_payload({"entries": [_entry(index) for index in range(38)]})
