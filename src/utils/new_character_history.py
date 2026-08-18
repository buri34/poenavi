"""Client.txtの過去ログからPoE1の新キャラクター開始を補助判定する。"""

from __future__ import annotations

import io
import os
import re
from collections.abc import Collection
from dataclasses import dataclass

MAX_HISTORY_BYTES = 128 * 1024 * 1024
TWILIGHT_STRAND_NAMES = {"黄昏の岸辺", "The Twilight Strand"}
_INVALID_ZONE_NAMES = {"(null)", "(unknown)"}

_ZONE_PATTERNS = (
    re.compile(r"あなたは(.+?)に入場しました。"),
    re.compile(r": You have entered (.+?)\."),
    re.compile(r"\[SCENE\] Set Source \[(.+?)\]"),
)
_LEVEL_PATTERNS = (
    re.compile(r"はレベル(\d+)になりました"),
    re.compile(r" is now level (\d+)"),
)


@dataclass(frozen=True)
class NewCharacterHistoryResult:
    anchor_found: bool
    new_character_start_found: bool
    latest_non_town_zone: str | None


def _extract_zone(line: str, known_zones: set[str]) -> str | None:
    for pattern in _ZONE_PATTERNS:
        match = pattern.search(line)
        if not match:
            continue
        zone_name = match.group(1).strip()
        if zone_name in _INVALID_ZONE_NAMES or zone_name not in known_zones:
            return None
        return zone_name
    return None


def _extract_level(line: str) -> int | None:
    for pattern in _LEVEL_PATTERNS:
        match = pattern.search(line)
        if match:
            return int(match.group(1))
    return None


def inspect_client_log_history(
    log_path: str,
    anchor_zone: str | None,
    known_zones: Collection[str],
    town_zones: Collection[str],
    max_bytes: int = MAX_HISTORY_BYTES,
) -> NewCharacterHistoryResult:
    """末尾から最大max_bytesを読み、最後のanchor以降を時系列で検査する。

    anchor_zoneがない初回起動では過去判定をせず、最新の非街エリアだけ返す。
    """
    known = set(known_zones)
    towns = set(town_zones)
    anchor_found = False
    candidate_active = False
    new_character_start_found = False
    latest_non_town_zone = None

    try:
        file_size = os.path.getsize(log_path)
        read_size = min(file_size, max(0, int(max_bytes)))
        with open(log_path, "rb") as log_file:
            log_file.seek(file_size - read_size)
            data = log_file.read(read_size)
    except (OSError, ValueError):
        return NewCharacterHistoryResult(False, False, None)

    # 読み始めが行の途中なら、その不完全な1行は捨てる。
    if read_size < file_size:
        newline = data.find(b"\n")
        data = data[newline + 1 :] if newline >= 0 else b""

    for raw_line in io.BytesIO(data):
        line = raw_line.decode("utf-8", errors="ignore")
        zone_name = _extract_zone(line, known)
        if zone_name:
            if zone_name not in towns:
                latest_non_town_zone = zone_name

            if anchor_zone and zone_name == anchor_zone:
                # 同名エリアが複数回あれば最後のものを基準にし直す。
                anchor_found = True
                candidate_active = zone_name in TWILIGHT_STRAND_NAMES
                new_character_start_found = False
                continue

            if anchor_found:
                candidate_active = zone_name in TWILIGHT_STRAND_NAMES
            continue

        if anchor_found and candidate_active and _extract_level(line) == 2:
            new_character_start_found = True

    return NewCharacterHistoryResult(
        anchor_found=anchor_found,
        new_character_start_found=new_character_start_found,
        latest_non_town_zone=latest_non_town_zone,
    )
