import json
from pathlib import Path

import pytest

from src.update.release_channel import (
    DEFAULT_RELEASE_REPOSITORY,
    load_release_repository,
    release_by_tag_api_url,
    releases_api_url,
    releases_page_url,
    validate_release_repository,
)


def test_build_metadata_selects_fork_release_repository(tmp_path):
    metadata = tmp_path / "update_channel.json"
    metadata.write_text(
        json.dumps({"release_repository": "fuubox/poenavi-localisation"}),
        encoding="utf-8",
    )

    repository = load_release_repository(metadata, require_metadata=True)

    assert repository == "fuubox/poenavi-localisation"
    assert releases_api_url(repository) == (
        "https://api.github.com/repos/"
        "fuubox/poenavi-localisation/releases/latest"
    )
    assert release_by_tag_api_url("v3.0.0", repository).endswith(
        "/fuubox/poenavi-localisation/releases/tags/v3.0.0"
    )
    assert releases_page_url(repository) == (
        "https://github.com/fuubox/poenavi-localisation/releases"
    )


def test_source_checkout_without_metadata_retains_upstream_default(tmp_path):
    assert load_release_repository(
        tmp_path / "missing.json",
        require_metadata=False,
    ) == DEFAULT_RELEASE_REPOSITORY


@pytest.mark.parametrize(
    "contents",
    [
        "not json",
        json.dumps([]),
        json.dumps({"release_repository": "missing-owner"}),
        json.dumps({"release_repository": "https://github.com/owner/repo"}),
    ],
)
def test_packaged_build_rejects_invalid_channel_metadata(tmp_path, contents):
    metadata = tmp_path / "update_channel.json"
    metadata.write_text(contents, encoding="utf-8")

    with pytest.raises(RuntimeError, match="metadata is invalid"):
        load_release_repository(metadata, require_metadata=True)


def test_packaged_build_rejects_missing_channel_metadata(tmp_path):
    with pytest.raises(RuntimeError, match="metadata is missing"):
        load_release_repository(
            tmp_path / "missing.json",
            require_metadata=True,
        )


@pytest.mark.parametrize(
    "repository",
    [
        "",
        "owner",
        "owner/repo/extra",
        "../repo",
        "owner/repo?tab=releases",
    ],
)
def test_release_repository_validation_rejects_unsafe_values(repository):
    with pytest.raises(ValueError):
        validate_release_repository(repository)


def test_build_script_generates_and_packages_channel_metadata():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "build_release.ps1").read_text(
        encoding="utf-8"
    )
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "GITHUB_REPOSITORY" in script
    assert "git remote get-url origin" in script
    assert "build\\generated\\update_channel.json;data" in script
    assert "-ReleaseRepository $env:GITHUB_REPOSITORY" in workflow
