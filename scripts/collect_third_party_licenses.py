"""Collect complete license texts for components shipped in PoENavi releases."""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import re
import shutil
import sys
from pathlib import Path


RUNTIME_DISTRIBUTIONS = (
    "PySide6", "PySide6-Addons", "PySide6-Essentials", "shiboken6",
    "pynput", "six", "urllib3", "PyInstaller", "altgraph",
    "pyinstaller-hooks-contrib", "packaging", "pefile", "pywin32-ctypes",
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_LICENSES = (
    (
        "Noto-Sans-JP",
        PROJECT_ROOT / "assets" / "fonts" / "NotoSansJP-OFL.txt",
        "OFL.txt",
    ),
)
LICENSE_BASENAME = re.compile(
    r"^(?:licen[cs]e|copying|notice|authors?)(?:[._-].*)?$", re.IGNORECASE
)


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")


def _license_files(distribution: metadata.Distribution) -> list[Path]:
    matches: list[Path] = []
    for entry in distribution.files or ():
        parts = tuple(part.lower() for part in entry.parts)
        if "licenses" in parts or LICENSE_BASENAME.match(entry.name):
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                matches.append(source)
    return sorted(set(matches), key=lambda path: str(path).lower())


def _python_license() -> Path:
    for candidate in (
        Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE",
        Path(sys.prefix) / "LICENSE.txt", Path(sys.prefix) / "LICENSE",
    ):
        if candidate.is_file():
            return candidate
    raise RuntimeError("Python license file was not found in the active interpreter")


def collect(
    output_dir: Path,
    distribution_names: tuple[str, ...] = RUNTIME_DISTRIBUTIONS,
    static_licenses: tuple[tuple[str, Path, str], ...] = STATIC_LICENSES,
) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    index_lines = [
        "# Third-party license texts", "",
        "These files are copied from the exact packages used by the release build.", "",
    ]

    python_source = _python_license()
    python_target = output_dir / "Python-LICENSE.txt"
    shutil.copyfile(python_source, python_target)
    index_lines.append(f"- Python {sys.version.split()[0]}: `{python_target.name}`")

    for component, source, target_name in static_licenses:
        if not source.is_file():
            raise RuntimeError(f"Required static license was not found: {source}")
        component_dir = output_dir / _safe_name(component)
        component_dir.mkdir()
        shutil.copyfile(source, component_dir / target_name)
        index_lines.append(f"- {component}: `{component_dir.name}/{target_name}`")

    for requested_name in distribution_names:
        try:
            distribution = metadata.distribution(requested_name)
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"Required distribution is not installed: {requested_name}") from exc
        project_name = distribution.metadata.get("Name", requested_name)
        version = distribution.version
        sources = _license_files(distribution)
        if not sources:
            raise RuntimeError(f"No complete license text found for {project_name} {version}")

        component_dir = output_dir / f"{_safe_name(project_name)}-{_safe_name(version)}"
        component_dir.mkdir()
        copied_names: list[str] = []
        used_names: set[str] = set()
        for source in sources:
            name = source.name
            if name.lower() in used_names:
                name = f"{len(used_names) + 1}-{name}"
            used_names.add(name.lower())
            shutil.copyfile(source, component_dir / name)
            copied_names.append(name)
        listed_paths = "`, `".join(f"{component_dir.name}/{name}" for name in copied_names)
        index_lines.append(f"- {project_name} {version}: `{listed_paths}`")

    (output_dir / "README.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collect(args.output)
    print(f"Collected third-party licenses in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
