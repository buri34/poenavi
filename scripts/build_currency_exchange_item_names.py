"""Build the minimal runtime ID/name dictionaries from verified RePoE caches."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.poetore.official_exchange import CHAOS, DIVINE, EXALTED, normalize_name


def load_source(path: Path) -> dict[str, str]:
    opener = gzip.open if path.suffix == ".gz" else path.open
    with opener(path, "rt", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected object in {path}")
    return {
        str(item_id): str(name).strip()
        for item_id, name in payload.items() if str(name).strip()
    }


def validate(names: dict[str, str]) -> None:
    expected = {
        CHAOS: "chaos orb",
        DIVINE: "divine orb",
        EXALTED: "exalted orb",
    }
    for item_id, name in expected.items():
        if normalize_name(names.get(item_id, "")) != name:
            raise ValueError(f"Golden ID mismatch for {item_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    names = load_source(args.source)
    validate(names)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dict(sorted(names.items())), ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(names)} names to {args.output}")


if __name__ == "__main__":
    main()
