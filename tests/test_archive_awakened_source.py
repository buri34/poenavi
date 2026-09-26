import json
import tarfile

from scripts.archive_awakened_source import (
    default_archive_paths,
    locked_revision,
    sha256,
)


def test_preserved_awakened_source_matches_manifest_and_contains_dependencies():
    revision = locked_revision()
    archive, manifest_path = default_archive_paths(revision)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["revision"] == revision
    assert sha256(archive) == manifest["archive_sha256"]
    with tarfile.open(archive, "r:gz") as source:
        names = {name.rsplit("/", 1)[-1] for name in source.getnames()}
        full_names = source.getnames()
    assert {"LICENSE", "stats.ndjson", "items.ndjson", "item-drop.json"} <= names
    assert any(name.endswith("/filters/create-presets.ts") for name in full_names)
    assert any(name.endswith("/filters/create-stat-filters.ts") for name in full_names)
