"""Resolve the GitHub repository used by packaged self-updates."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


DEFAULT_RELEASE_REPOSITORY = "buri34/poenavi"
CHANNEL_FILENAME = "update_channel.json"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def validate_release_repository(value: str) -> str:
    repository = str(value or "").strip()
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError(f"Invalid GitHub release repository: {value!r}")
    owner, name = repository.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise ValueError(f"Invalid GitHub release repository: {value!r}")
    return repository


def update_channel_path() -> Path:
    """Return the build-generated channel metadata path."""
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        beside_executable = executable_dir / "data" / CHANNEL_FILENAME
        if beside_executable.is_file():
            return beside_executable
        bundle_dir = Path(getattr(sys, "_MEIPASS", executable_dir))
        return bundle_dir / "data" / CHANNEL_FILENAME
    return Path(__file__).resolve().parents[2] / "data" / CHANNEL_FILENAME


def load_release_repository(
    path: Path | None = None,
    *,
    require_metadata: bool | None = None,
) -> str:
    """Load the build-pinned release repository.

    Source checkouts retain the historical upstream default. Frozen builds
    fail closed if their generated metadata is missing or malformed, avoiding
    an accidental cross-repository update.
    """
    metadata_path = path or update_channel_path()
    if require_metadata is None:
        require_metadata = bool(getattr(sys, "frozen", False))
    if not metadata_path.is_file():
        if require_metadata:
            raise RuntimeError(
                f"Packaged update-channel metadata is missing: {metadata_path}"
            )
        return DEFAULT_RELEASE_REPOSITORY
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("metadata root must be an object")
        return validate_release_repository(payload.get("release_repository", ""))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if require_metadata:
            raise RuntimeError(
                f"Packaged update-channel metadata is invalid: {metadata_path}"
            ) from exc
        return DEFAULT_RELEASE_REPOSITORY


def releases_api_url(repository: str | None = None) -> str:
    repository = validate_release_repository(
        repository or load_release_repository()
    )
    return f"https://api.github.com/repos/{repository}/releases/latest"


def release_by_tag_api_url(tag: str, repository: str | None = None) -> str:
    repository = validate_release_repository(
        repository or load_release_repository()
    )
    return f"https://api.github.com/repos/{repository}/releases/tags/{tag}"


def releases_page_url(repository: str | None = None) -> str:
    repository = validate_release_repository(
        repository or load_release_repository()
    )
    return f"https://github.com/{repository}/releases"
