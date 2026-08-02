"""既存の監査済みindexからPoENavi独自Stat判断台帳を初期化する。

通常更新では使わない。台帳の初回分離、または明示的な再監査時だけ実行する。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


RULE_FIELDS = (
    "ref", "stat_id", "kind", "better", "inverted", "negated", "exact",
    "decimal", "options", "category_select",
)


def extract_rules(payload: dict, source_sha256: str | None = None) -> dict:
    rules = [
        {field: row[field] for field in RULE_FIELDS if field in row}
        for row in payload.get("mods", ())
    ]
    return {
        "schema_version": 1,
        "description": "PoENavi-reviewed trade stat semantics; runtime Japanese text comes from the official Trade API.",
        "initial_source_sha256": source_sha256,
        "rules": rules,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/poetore/mod_metadata.json"))
    parser.add_argument("--output", type=Path, default=Path("scripts/poetore-stat-rules.json"))
    args = parser.parse_args()
    source_bytes = args.input.read_bytes()
    payload = json.loads(source_bytes)
    rules = extract_rules(payload, hashlib.sha256(source_bytes).hexdigest())
    args.output.write_text(
        json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"wrote {len(rules['rules'])} rules: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
