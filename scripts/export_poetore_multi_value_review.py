from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re


DEFAULT_INPUT = Path("data/poetore/mod_metadata.json")
DEFAULT_OUTPUT = Path("docs/poetore-multi-value-stat-review.csv")
FIELDNAMES = (
    "review_id",
    "stat_id",
    "kind",
    "japanese_template",
    "english_ref",
    "placeholder_count",
    "fixed_numbers",
    "current_value_behavior",
    "reviewer_decision",
    "review_notes",
)


def is_added_damage_range(template: str) -> bool:
    return "#から#" in template and "ダメージ" in template and "反射する" not in template


def fixed_numbers(template: str) -> str:
    return " | ".join(re.findall(r"(?<!#)(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", template))


def build_rows(payload: dict) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    seen: set[tuple[str, str, str]] = set()
    for mod in payload.get("mods", ()):
        for template in mod.get("japanese", ()):
            placeholder_count = str(template).count("#")
            if placeholder_count < 2 or is_added_damage_range(str(template)):
                continue
            key = (str(mod.get("stat_id", "")), str(mod.get("kind", "")), str(template))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "review_id": 0,
                "stat_id": key[0],
                "kind": key[1],
                "japanese_template": key[2],
                "english_ref": str(mod.get("ref", "")),
                "placeholder_count": placeholder_count,
                "fixed_numbers": fixed_numbers(key[2]),
                "current_value_behavior": "未変更（従来どおり本文の先頭数値を検索値に使用）",
                "reviewer_decision": "",
                "review_notes": "",
            })
    rows.sort(key=lambda row: (str(row["kind"]), str(row["japanese_template"]), str(row["stat_id"])))
    for index, row in enumerate(rows, 1):
        row["review_id"] = index
    return rows


def export_review(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> int:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    rows = build_rows(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="複数可変値Statの手動レビュー用CSVを生成する")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    count = export_review(args.input, args.output)
    print(f"exported={count} output={args.output}")


if __name__ == "__main__":
    main()
