import json
from pathlib import Path
import tarfile

from scripts.archive_awakened_source import sha256


def test_preserved_awakened_source_matches_manifest_and_contains_dependencies():
    archive = Path("vendor-sources/awakened-poe-trade-31b3e0e8.tar.gz")
    manifest = json.loads(Path(
        "vendor-sources/awakened-poe-trade-31b3e0e8.json"
    ).read_text(encoding="utf-8"))

    assert manifest["revision"] == "31b3e0e8ba0a6bac2266603c2e170925c8f02b81"
    assert sha256(archive) == manifest["archive_sha256"]
    with tarfile.open(archive, "r:gz") as source:
        names = {name.rsplit("/", 1)[-1] for name in source.getnames()}
        full_names = source.getnames()
    assert {"LICENSE", "stats.ndjson", "items.ndjson", "item-drop.json"} <= names
    assert any(name.endswith("/filters/create-presets.ts") for name in full_names)
    assert any(name.endswith("/filters/create-stat-filters.ts") for name in full_names)
