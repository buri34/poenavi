from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re


DEFAULT_INPUT = Path("data/poetore/mod_metadata.json")
DEFAULT_OUTPUT = Path("docs/poetore-multi-value-stat-review.csv")
DEFAULT_RULES_OUTPUT = Path("data/poetore/multi_value_rules.json")
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


def merge_review_decisions(rows: list[dict], reviewed_path: Path) -> None:
    with reviewed_path.open(encoding="utf-8-sig", newline="") as handle:
        reviewed = {
            (row["stat_id"], row["kind"], row["japanese_template"]): row
            for row in csv.DictReader(handle)
        }
    for row in rows:
        key = (str(row["stat_id"]), str(row["kind"]), str(row["japanese_template"]))
        source = reviewed.get(key)
        if source:
            row["reviewer_decision"] = source.get("reviewer_decision", "").strip()
            row["review_notes"] = source.get("review_notes", "").strip()


def _percent_placeholder_index(template: str) -> int:
    suffixes = template.split("#")[1:]
    indexes = [index for index, suffix in enumerate(suffixes) if suffix.lstrip().startswith("%")]
    if len(indexes) != 1:
        raise ValueError(f"expected one percentage placeholder: {template}")
    return indexes[0]


def build_rules(rows: list[dict]) -> dict:
    decision_map = {
        "１つ目の値と２つ目の値は同じ値になるため、現状と同じ仕様でよい": "first",
        "検索条件がまったく意味わからないので、検索値のデフォルトは空白でよい": "blank",
        "平均値でいい": "mean",
        "２番目の数字を２で割った値": "half_second",
    }
    rules = []
    for row in rows:
        decision = str(row.get("reviewer_decision", "")).strip()
        if not decision:
            raise ValueError(f"empty reviewer_decision: {row['stat_id']}")
        if decision == "「#%」のほうの値を使う":
            operation = "index"
            value_index = _percent_placeholder_index(str(row["japanese_template"]))
        else:
            operation = decision_map.get(decision, "")
            value_index = None
        if not operation:
            raise ValueError(f"unknown reviewer_decision: {decision}")
        rule = {
            "stat_id": str(row["stat_id"]),
            "operation": operation,
            "decision": decision,
        }
        if value_index is not None:
            rule["value_index"] = value_index
        rules.append(rule)
    return {"schema_version": 1, "rules": rules}


def export_review(
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
    reviewed_path: Path | None = None,
    rules_output: Path | None = None,
) -> int:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    rows = build_rows(payload)
    if reviewed_path is not None:
        merge_review_decisions(rows, reviewed_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    if rules_output is not None:
        rules_payload = build_rules(rows)
        rules_output.parent.mkdir(parents=True, exist_ok=True)
        rules_output.write_text(
            json.dumps(rules_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="複数可変値Statの手動レビュー用CSVを生成する")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reviewed", type=Path)
    parser.add_argument("--rules-output", type=Path)
    args = parser.parse_args()
    rules_output = args.rules_output or (DEFAULT_RULES_OUTPUT if args.reviewed else None)
    count = export_review(args.input, args.output, args.reviewed, rules_output)
    print(f"exported={count} output={args.output}")


if __name__ == "__main__":
    main()
