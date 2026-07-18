from __future__ import annotations

from .parser import parse_item_text


def merge_normal_and_detailed_copy(normal_text: str, detailed_text: str) -> str:
    """詳細コピーのMod情報を保ち、名前とベースだけ通常コピー側へ置換する。"""
    normal_item = parse_item_text(normal_text)
    detailed_item = parse_item_text(detailed_text)

    lines = detailed_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    separator_index = next((index for index, line in enumerate(lines) if line.strip() == "--------"), None)
    if separator_index is None:
        return detailed_text

    header = lines[:separator_index]
    for old, new in (
        (detailed_item.name, normal_item.name),
        (detailed_item.base_type, normal_item.base_type),
    ):
        if not old or not new:
            continue
        for index in range(2, len(header)):
            if header[index].strip() == old.strip():
                header[index] = new
                break

    return "\n".join(header + lines[separator_index:])
