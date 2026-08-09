from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.poetore.poe2.local_global_audit import DEFAULT_STATE_DIR, build_candidates, run_one_step


def main() -> int:
    parser = argparse.ArgumentParser(description="PoE2 Local／Global Statを1 API呼び出しずつ監査")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--league", default="Runes of Aldur")
    parser.add_argument("--list", action="store_true", help="APIを使わず監査候補だけ表示")
    args = parser.parse_args()
    result = (
        {"status": "listed", "api_call": False, "candidates": build_candidates()}
        if args.list else run_one_step(args.state_dir, args.league)
    )
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
