from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen

from src.poetore.metadata_builder import (
    build_minimal_index,
    diff_minimal_indexes,
    excessive_removal,
    unresolved_trade_entries,
    validate_minimal_index,
)


DEFAULT_LOCK = Path("scripts/poetore-sources.lock.json")
DEFAULT_OUTPUT = Path("data/poetore/mod_metadata.json")
DEFAULT_REPORT = Path("build/poetore-metadata-report.json")


def _get(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "PoENavi/poetore-metadata-builder"})
    with urlopen(request, timeout=120) as response:
        return response.read()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _serialized(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _run_regression_tests(candidate: Path) -> None:
    env = os.environ.copy()
    env["POETORE_METADATA_PATH"] = str(candidate.resolve())
    env["POETORE_CANDIDATE_BUILD"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    command = [sys.executable, "-m", "pytest", "-q"]
    print(f"running candidate regression tests: {' '.join(command)}")
    subprocess.run(command, check=True, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="ぽえとれ用Modメタデータを安全に検証・生成")
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--apply", action="store_true", help="検査成功後に正本を原子的に置換する")
    parser.add_argument(
        "--refresh-lock", action="store_true",
        help="新しい取得内容で候補を検査する（--apply時のみlockも更新）",
    )
    parser.add_argument(
        "--allow-large-removal", action="store_true",
        help="10%%超または100件超の削除をレビュー済みとして許可する",
    )
    args = parser.parse_args()
    lock = _load_json(args.lock)
    source_rows = lock.get("sources", {})
    required = {"awakened_poe_trade", "jp_trade_api", "repoe_stats", "repoe_mods"}
    if set(source_rows) != required:
        raise SystemExit(f"source lock keys mismatch: expected={sorted(required)} actual={sorted(source_rows)}")

    blobs: dict[str, bytes] = {}
    hashes: dict[str, str] = {}
    changed_sources: list[str] = []
    for name, row in source_rows.items():
        blob = _get(str(row["url"]))
        digest = hashlib.sha256(blob).hexdigest()
        blobs[name], hashes[name] = blob, digest
        marker = "changed" if digest != row.get("sha256") else "locked"
        revision = f" revision={row['revision']}" if row.get("revision") else ""
        print(f"source {name}: {marker} sha256={digest}{revision} url={row['url']}")
        if marker == "changed":
            changed_sources.append(name)
    if changed_sources and not args.refresh_lock:
        raise SystemExit(
            "source hashes changed: " + ", ".join(changed_sources)
            + "; review upstream changes, then dry-run with --refresh-lock"
        )

    effective_lock = json.loads(json.dumps(lock))
    if args.refresh_lock:
        refreshed_at = datetime.now(timezone.utc)
        effective_lock["generated_at"] = refreshed_at.isoformat()
        for name, digest in hashes.items():
            effective_lock["sources"][name]["sha256"] = digest
            if "version" in effective_lock["sources"][name]:
                effective_lock["sources"][name]["version"] = f"snapshot-{refreshed_at.date().isoformat()}"

    sources = {
        name: {
            key: value for key, value in row.items()
            if key in {"url", "revision", "version", "sha256"}
        }
        for name, row in effective_lock["sources"].items()
    }
    awakened = blobs["awakened_poe_trade"].decode("utf-8").splitlines()
    jp_trade = json.loads(blobs["jp_trade_api"])
    candidate = build_minimal_index(
        awakened,
        jp_trade,
        json.loads(blobs["repoe_stats"]),
        json.loads(blobs["repoe_mods"]),
        sources=sources,
        generated_at=str(effective_lock["generated_at"]),
    )
    previous = _load_json(args.output) if args.output.exists() else {"mods": []}
    integrity = validate_minimal_index(candidate)
    differences = diff_minimal_indexes(previous, candidate)
    unresolved = unresolved_trade_entries(candidate, jp_trade)
    candidate_bytes = _serialized(candidate)
    too_many_removed, removal_limit = excessive_removal(differences)
    failures = list(integrity["errors"])
    if too_many_removed and not args.allow_large_removal:
        failures.append(
            f"large removal detected: {len(differences['removed'])} > {removal_limit}"
        )
    report = {
        "generated_at": effective_lock["generated_at"],
        "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "candidate_size": len(candidate_bytes),
        "sources": sources,
        "integrity": integrity,
        "diff": differences,
        "unresolved_japanese_stats": unresolved,
        "failures": failures,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"candidate records={integrity['record_count']} size={len(candidate_bytes)} "
        f"added={len(differences['added'])} removed={len(differences['removed'])} "
        f"changed={len(differences['changed'])} ambiguous={len(integrity['ambiguous_matchers'])} "
        f"unresolved={len(unresolved)} report={args.report}"
    )
    if failures:
        raise SystemExit("candidate rejected: " + "; ".join(failures))

    candidate_path = args.output.with_name(f".{args.output.name}.candidate")
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_bytes(candidate_bytes)
    try:
        _run_regression_tests(candidate_path)
        if args.apply:
            candidate_path.replace(args.output)
            if args.refresh_lock:
                args.lock.write_text(
                    json.dumps(effective_lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            print(f"applied {integrity['record_count']} records atomically: {args.output}")
        else:
            print("dry-run complete;正本は変更していません（反映には --apply）")
    finally:
        if candidate_path.exists():
            candidate_path.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
