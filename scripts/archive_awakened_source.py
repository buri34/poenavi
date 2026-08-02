"""固定済みAwakened PoE Trade原本を、上流消失に備えて保存・検証する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


DEFAULT_REVISION = "3c8e0320ab3ea22d6dccc6cad48b5efaf94d1fe2"
DEFAULT_ARCHIVE = Path("vendor-sources/awakened-poe-trade-3c8e0320.tar.gz")
DEFAULT_MANIFEST = Path("vendor-sources/awakened-poe-trade-3c8e0320.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        actual = sha256(args.archive)
        if actual != manifest["archive_sha256"]:
            raise SystemExit(f"archive hash mismatch: {actual}")
        print(f"verified {args.archive}: {actual}")
        return 0

    url = f"https://codeload.github.com/SnosMe/awakened-poe-trade/tar.gz/{args.revision}"
    request = Request(url, headers={"User-Agent": "PoENavi/source-archiver"})
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.archive.with_suffix(args.archive.suffix + ".tmp")
    with urlopen(request, timeout=120) as response, temporary.open("wb") as target:
        while chunk := response.read(1024 * 1024):
            target.write(chunk)
    temporary.replace(args.archive)
    manifest = {
        "project": "Awakened PoE Trade",
        "license": "MIT",
        "revision": args.revision,
        "source_url": url,
        "archive_sha256": sha256(args.archive),
        "purpose": "Development-only recovery source; excluded from PoENavi releases.",
    }
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"archived {args.revision}: {args.archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
