import json
from pathlib import Path
import tarfile

from scripts.archive_awakened_source import sha256


def test_preserved_awakened_source_matches_manifest_and_contains_dependencies():
    archive = Path("vendor-sources/awakened-poe-trade-1e2225af.tar.gz")
    manifest = json.loads(Path(
        "vendor-sources/awakened-poe-trade-1e2225af.json"
    ).read_text(encoding="utf-8"))

    assert manifest["revision"] == "1e2225af8cfe04ccc5676d00eede81d7ee071240"
    assert sha256(archive) == manifest["archive_sha256"]
    with tarfile.open(archive, "r:gz") as source:
        names = {name.rsplit("/", 1)[-1] for name in source.getnames()}
        full_names = source.getnames()
    assert {"LICENSE", "stats.ndjson", "items.ndjson", "item-drop.json"} <= names
    assert any(name.endswith("/filters/create-presets.ts") for name in full_names)
    assert any(name.endswith("/filters/create-stat-filters.ts") for name in full_names)
