"""固定済みAwakened PoE Trade原本を、上流消失に備えて保存・検証する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

DEFAULT_LOCK = Path("scripts/poetore-sources.lock.json")


def locked_revision(lock_path: Path = DEFAULT_LOCK) -> str:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    return str(lock["sources"]["awakened_poe_trade"]["revision"])


def default_archive_paths(revision: str) -> tuple[Path, Path]:
    stem = Path("vendor-sources") / f"awakened-poe-trade-{revision[:8]}"
    return stem.with_suffix(".tar.gz"), stem.with_suffix(".json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    revision = args.revision or locked_revision()
    default_archive, default_manifest = default_archive_paths(revision)
    archive = args.archive or default_archive
    manifest_path = args.manifest or default_manifest
    if args.verify:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual = sha256(archive)
        if actual != manifest["archive_sha256"]:
            raise SystemExit(f"archive hash mismatch: {actual}")
        if manifest["revision"] != revision:
            raise SystemExit(
                f"archive revision mismatch: expected={revision} actual={manifest['revision']}"
            )
        print(f"verified {archive}: {actual}")
        return 0

    url = f"https://codeload.github.com/SnosMe/awakened-poe-trade/tar.gz/{revision}"
    request = Request(url, headers={"User-Agent": "PoENavi/source-archiver"})
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    with urlopen(request, timeout=120) as response, temporary.open("wb") as target:
        while chunk := response.read(1024 * 1024):
            target.write(chunk)
    temporary.replace(archive)
    manifest = {
        "project": "Awakened PoE Trade",
        "license": "MIT",
        "revision": revision,
        "source_url": url,
        "archive_sha256": sha256(archive),
        "purpose": "Development-only recovery source; excluded from PoENavi releases.",
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"archived {revision}: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
