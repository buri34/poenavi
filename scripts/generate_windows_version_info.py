"""Generate PyInstaller VERSIONINFO files from the application version."""

from __future__ import annotations

import argparse
from pathlib import Path


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError("APP_VERSION must use numeric X.Y.Z format")
    return tuple(int(part) for part in parts) + (0,)


def render_version_info(*, version: str, description: str, original_filename: str) -> str:
    numeric = version_tuple(version)
    tuple_text = ", ".join(str(part) for part in numeric)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({tuple_text}),
    prodvers=({tuple_text}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'PoENavi Open Source Project'),
         StringStruct('FileDescription', '{description}'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', '{Path(original_filename).stem}'),
         StringStruct('LegalCopyright', 'Copyright (c) 2026 Buri_Isono'),
         StringStruct('OriginalFilename', '{original_filename}'),
         StringStruct('ProductName', 'PoENavi'),
         StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--filename", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_version_info(
            version=args.version,
            description=args.description,
            original_filename=args.filename,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
