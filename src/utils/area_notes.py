import json
import os
from pathlib import Path
import tempfile
import re

from src.utils.config_manager import ConfigManager
from src.utils.poe_version_data import POE1, POE2


SCHEMA_VERSION = 1


def qt_html_to_storage_html(html: str) -> str:
    """QTextEditのHTMLを、色タグと意図した改行だけの保存形式へ変換する。"""
    match = re.search(r"<body[^>]*>(.*)</body>", html, re.DOTALL)
    body = match.group(1).strip() if match else html

    # Qtは段落タグ間に整形用の改行を挿入する。先に取り除かないと、
    # </p>由来の改行と重なり、1回のEnterが空行として保存される。
    body = re.sub(r"</p>\s*<p", "</p><p", body, flags=re.IGNORECASE)
    body = re.sub(r"<p[^>]*>", "", body, flags=re.IGNORECASE)
    body = re.sub(r"</p>", "\n", body, flags=re.IGNORECASE)
    body = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)

    def span_to_tags(span_match):
        style = span_match.group(1)
        text = span_match.group(2)
        is_bold = "font-weight" in style and ("700" in style or "bold" in style)
        color_match = re.search(r"color:(#[0-9a-fA-F]{6})", style)
        if is_bold and color_match:
            return f"<b style='color:{color_match.group(1)}'>{text}</b>"
        if is_bold:
            return f"<b>{text}</b>"
        if color_match:
            return f"<span style='color:{color_match.group(1)}'>{text}</span>"
        return text

    body = re.sub(r'<span style="([^"]*)">(.*?)</span>', span_to_tags, body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return (
        body.replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&amp;", "&")
        .strip()
    )


def notes_filename(poe_version: str) -> str:
    suffix = "poe2" if poe_version == POE2 else "poe1"
    return f"area_notes_{suffix}.json"


def notes_path(poe_version: str) -> Path:
    return ConfigManager.get_user_data_path(notes_filename(poe_version))


def load_area_notes(poe_version: str) -> dict[str, str]:
    path = notes_path(poe_version)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"エリアメモを読み込めません: {path}") from exc
    raw_notes = payload.get("notes", {}) if isinstance(payload, dict) else {}
    if not isinstance(raw_notes, dict):
        raise ValueError(f"エリアメモの形式が不正です: {path}")
    return {
        str(zone_id): content
        for zone_id, content in raw_notes.items()
        if isinstance(content, str) and content.strip()
    }


def save_area_notes(poe_version: str, notes: dict[str, str]) -> Path:
    path = notes_path(poe_version)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {
        str(zone_id): content.strip()
        for zone_id, content in notes.items()
        if isinstance(content, str) and content.strip()
    }
    payload = {"schema": SCHEMA_VERSION, "notes": cleaned}
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def get_area_note(poe_version: str, zone_id: str | None) -> str:
    if not zone_id:
        return ""
    return load_area_notes(poe_version).get(zone_id, "")


def set_area_note(poe_version: str, zone_id: str, content: str) -> Path:
    if not zone_id:
        raise ValueError("エリアIDがありません")
    notes = load_area_notes(poe_version)
    if content.strip():
        notes[zone_id] = content.strip()
    else:
        notes.pop(zone_id, None)
    return save_area_notes(poe_version, notes)
