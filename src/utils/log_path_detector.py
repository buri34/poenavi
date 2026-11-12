"""Path of Exile の Client.txt を既知のインストール先から検出する。"""

import os
import re
from pathlib import Path


POE_GAME_DIRS = {"poe1": "Path of Exile", "poe2": "Path of Exile 2"}


def _known_install_version(client_log_path: str) -> str | None:
    """Identify official/Steam install directory names without guessing custom paths."""
    for part in re.split(r"[\\/]+", str(client_log_path or "")):
        compact = re.sub(r"[\s_-]+", "", part).casefold()
        if compact == "pathofexile2":
            return "poe2"
        if compact == "pathofexile":
            return "poe1"
    return None


def steam_library_roots() -> list[Path]:
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    steam_root = Path(program_files_x86) / "Steam"
    roots = [steam_root]
    library_file = steam_root / "steamapps" / "libraryfolders.vdf"
    try:
        content = library_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return roots
    for value in re.findall(r'"path"\s+"([^"]+)"', content):
        root = Path(value.replace(r"\\", "\\"))
        if root not in roots:
            roots.append(root)
    return roots


def launcher_candidates(version: str) -> list[Path]:
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    if version == "poe1":
        return [
            program_files_x86 / "Grinding Gear Games" / "Path of Exile" / "logs" / "Client.txt",
            program_files / "Epic Games" / "PathOfExile" / "logs" / "Client.txt",
        ]
    return [
        program_files_x86 / "Grinding Gear Games" / "Path of Exile 2" / "logs" / "Client.txt",
        program_files / "Epic Games" / "PathOfExile2" / "logs" / "Client.txt",
    ]


def detect_client_log_paths() -> dict[str, str]:
    detected = {"poe1": "", "poe2": ""}
    for version, game_dir in POE_GAME_DIRS.items():
        candidates = [root / "steamapps" / "common" / game_dir / "logs" / "Client.txt" for root in steam_library_roots()]
        candidates.extend(launcher_candidates(version))
        for candidate in candidates:
            if candidate.is_file():
                detected[version] = str(candidate)
                break
    return detected


def fill_missing_client_log_paths(config: dict) -> bool:
    paths = config.setdefault("client_log_paths", {})
    detected_paths = detect_client_log_paths()
    changed = False
    for version, detected_path in detected_paths.items():
        configured_path = str(paths.get(version, "") or "")
        configured_version = _known_install_version(configured_path)
        is_cross_saved = (
            configured_version is not None and configured_version != version
        )
        if detected_path and (not configured_path or is_cross_saved):
            paths[version] = detected_path
            changed = True
    return changed
