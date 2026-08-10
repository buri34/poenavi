"""ぽえとれTradeデータの総合監査・候補生成・安全反映。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:
    from scripts.build_poetore_map_mods import build_catalog
    from scripts.extract_poetore_pseudo_relations import extract_relations
except ModuleNotFoundError:  # `python scripts/update_*.py`で直接起動する場合
    from build_poetore_map_mods import build_catalog
    from extract_poetore_pseudo_relations import extract_relations


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build"
CANDIDATE_DIR = BUILD_DIR / "poetore-update-candidate"
REPORT_JSON = BUILD_DIR / "poetore-update-report.json"
REPORT_MD = BUILD_DIR / "poetore-update-report.md"
MANIFEST_PATH = CANDIDATE_DIR / "manifest.json"

OFFICIAL_URLS = {
    "items_en": "https://www.pathofexile.com/api/trade/data/items",
    "items_ja": "https://jp.pathofexile.com/api/trade/data/items",
    "stats_en": "https://www.pathofexile.com/api/trade/data/stats",
    "stats_ja": "https://jp.pathofexile.com/api/trade/data/stats",
}

AUTHORITATIVE = {
    "mod_metadata": Path("data/poetore/mod_metadata.json"),
    "map_mods": Path("data/poetore/map_mods.json"),
    "source_lock": Path("scripts/poetore-sources.lock.json"),
    "official_stats_baseline": Path("scripts/poetore-official-stats-baseline.json"),
    "pseudo_relations": Path("data/poetore/pseudo_relations.json"),
}
PSEUDO_FILES = (
    Path("data/poetore/pseudo_definitions.json"),
    Path("data/poetore/pseudo_relations.json"),
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_json(url: str) -> tuple[dict, str]:
    request = Request(url, headers={"User-Agent": "PoENavi/trade-data-audit"})
    with urlopen(request, timeout=120) as response:
        blob = response.read()
    return json.loads(blob), sha256_bytes(blob)


def post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        url, data=body,
        headers={
            "User-Agent": "PoENavi/trade-data-audit",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    for attempt in range(4):
        try:
            with urlopen(request, timeout=120) as response:
                return json.loads(response.read())
        except HTTPError as error:
            if error.code != 429 or attempt == 3:
                raise
            retry_after = error.headers.get("Retry-After", "")
            try:
                wait_seconds = max(1.0, min(float(retry_after), 60.0))
            except (TypeError, ValueError):
                wait_seconds = 10.0
            time.sleep(wait_seconds)
    raise RuntimeError("Trade API retry loop ended unexpectedly")


def _option_ids(entry: dict) -> tuple[str, ...]:
    return tuple(sorted(
        str(row.get("id")) for row in entry.get("option", {}).get("options", ())
        if row.get("id") is not None
    ))


def stat_snapshot(payload: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for group in payload.get("result", ()):
        group_id = str(group.get("id", ""))
        for entry in group.get("entries", ()):
            stat_id = str(entry.get("id", ""))
            if not stat_id:
                continue
            result[stat_id] = {
                "group": group_id,
                "type": str(entry.get("type", "")),
                "options": _option_ids(entry),
                "text": str(entry.get("text", "")),
            }
    return result


def audit_bilingual_stats(english: dict, japanese: dict) -> dict:
    en = stat_snapshot(english)
    ja = stat_snapshot(japanese)
    shared = sorted(set(en) & set(ja))
    option_mismatches = [
        {"id": stat_id, "english": en[stat_id]["options"], "japanese": ja[stat_id]["options"]}
        for stat_id in shared if en[stat_id]["options"] != ja[stat_id]["options"]
    ]
    type_mismatches = [
        {"id": stat_id, "english": en[stat_id]["type"], "japanese": ja[stat_id]["type"]}
        for stat_id in shared if en[stat_id]["type"] != ja[stat_id]["type"]
    ]
    return {
        "english_count": len(en),
        "japanese_count": len(ja),
        "english_only": sorted(set(en) - set(ja)),
        "japanese_only": sorted(set(ja) - set(en)),
        "option_mismatches": option_mismatches,
        "type_mismatches": type_mismatches,
    }


def _item_shapes(payload: dict) -> dict[str, Counter]:
    groups: dict[str, Counter] = {}
    for group in payload.get("result", ()):
        group_id = str(group.get("id", ""))
        shapes = Counter()
        for entry in group.get("entries", ()):
            flags = entry.get("flags") or {}
            shape = (
                str(entry.get("disc", "")),
                tuple(sorted(str(key) for key in flags)),
                bool(entry.get("name")),
                bool(entry.get("text")),
            )
            shapes[shape] += 1
        groups[group_id] = shapes
    return groups


def _shape_rows(values: Counter) -> list[dict]:
    return [
        {"disc": key[0], "flags": list(key[1]), "has_name": key[2],
         "has_text": key[3], "count": count}
        for key, count in sorted(values.items())
    ]


def audit_bilingual_items(english: dict, japanese: dict) -> dict:
    """順序や翻訳文字列に依存せず、カテゴリと構造の片側欠落を検出する。"""
    en = _item_shapes(english)
    ja = _item_shapes(japanese)
    mismatches = []
    for group_id in sorted(set(en) & set(ja)):
        if en[group_id] != ja[group_id]:
            mismatches.append({
                "group": group_id,
                "english": _shape_rows(en[group_id]),
                "japanese": _shape_rows(ja[group_id]),
            })
    return {
        "english_groups": len(en),
        "japanese_groups": len(ja),
        "english_only_groups": sorted(set(en) - set(ja)),
        "japanese_only_groups": sorted(set(ja) - set(en)),
        "structure_mismatches": mismatches,
    }


def audit_pseudo_files(root: Path = ROOT) -> dict:
    definitions = load_json(root / PSEUDO_FILES[0])
    relations = load_json(root / PSEUDO_FILES[1])
    definition_ids = {
        str(row.get("stat_id")) for row in definitions.get("definitions", ())
        if row.get("stat_id")
    }
    errors = []
    seen = set()
    for row in relations.get("relations", ()):
        stat_id = str(row.get("stat_id", ""))
        if not stat_id:
            errors.append("pseudo relation without stat_id")
        key = (row.get("pseudo_ref"), row.get("group"), row.get("replaces"))
        if key in seen:
            errors.append(f"duplicate pseudo relation: {key}")
        seen.add(key)
    return {
        "definitions": len(definitions.get("definitions", ())),
        "relations": len(relations.get("relations", ())),
        "definition_ids": len(definition_ids),
        "source_revisions": sorted({
            str(definitions.get("source_revision", "")),
            str(relations.get("source_revision", "")),
        }),
        "errors": errors,
    }


def build_pseudo_relations_candidate(
    archive: Path, revision: str,
) -> dict:
    with tarfile.open(archive, "r:gz") as source:
        index_member = next(
            row for row in source.getmembers()
            if row.name.endswith("/renderer/src/web/price-check/filters/pseudo/index.ts")
        )
        stats_member = next(
            row for row in source.getmembers()
            if row.name.endswith("/renderer/public/data/en/stats.ndjson")
        )
        index_handle = source.extractfile(index_member)
        stats_handle = source.extractfile(stats_member)
        if index_handle is None or stats_handle is None:
            raise ValueError("Awakened pseudo source was not found in archive")
        index_bytes = index_handle.read()
        stats_lines = stats_handle.read().decode("utf-8").splitlines()
    ids = {}
    for line in stats_lines:
        row = json.loads(line)
        for candidate in row.get("stats", [row]):
            values = candidate.get("trade", {}).get("ids", {}).get("pseudo", ())
            if values:
                ids[str(candidate["ref"])] = str(values[0])
    relations = extract_relations(index_bytes.decode("utf-8"))
    for row in relations:
        if row["pseudo_ref"] not in ids:
            raise ValueError(f"pseudo Trade ID not found: {row['pseudo_ref']}")
        row["stat_id"] = ids[row["pseudo_ref"]]
    return {
        "schema_version": 1,
        "source_revision": revision,
        "source_sha256": sha256_bytes(index_bytes),
        "relations": relations,
    }


def diff_pseudo_relations(previous: dict, candidate: dict) -> dict:
    def keyed(payload: dict) -> dict[str, dict]:
        return {
            str(row.get("pseudo_ref")): row
            for row in payload.get("relations", ()) if row.get("pseudo_ref")
        }
    old = keyed(previous)
    new = keyed(candidate)
    return {
        "added": [new[key] for key in sorted(set(new) - set(old))],
        "removed": [old[key] for key in sorted(set(old) - set(new))],
        "changed": [
            {"pseudo_ref": key, "old": old[key], "new": new[key]}
            for key in sorted(set(old) & set(new)) if old[key] != new[key]
        ],
    }


def overall_status(report: dict) -> str:
    if report.get("failures"):
        return "BLOCKED"
    stats = report["official_trade"]["stats"]
    items = report["official_trade"]["items"]
    review = any((
        stats["english_only"], stats["japanese_only"],
        stats["option_mismatches"], stats["type_mismatches"],
        items["english_only_groups"], items["japanese_only_groups"],
        items["structure_mismatches"],
    ))
    metadata = report.get("metadata", {})
    metadata_diff = metadata.get("diff", {})
    review = review or any(metadata_diff.get(key) for key in ("added", "removed", "changed"))
    pseudo_diff = report.get("pseudo", {}).get("diff", {})
    review = review or any(pseudo_diff.get(key) for key in ("added", "removed", "changed"))
    return "REVIEW REQUIRED" if review else "PASS"


def render_markdown(report: dict) -> str:
    stats = report["official_trade"]["stats"]
    items = report["official_trade"]["items"]
    metadata = report.get("metadata", {})
    diff = metadata.get("diff", {})
    pseudo = report["pseudo"]
    lines = [
        "# ぽえとれ Tradeデータ更新レポート", "",
        f"- 判定: **{report['status']}**",
        f"- モード: `{report['mode']}`",
        f"- 生成時刻: `{report['generated_at']}`", "",
        "## 公式Trade日英監査", "",
        f"- Stats: EN {stats['english_count']} / JA {stats['japanese_count']}",
        f"- Stats片側欠落: ENのみ {len(stats['english_only'])} / JAのみ {len(stats['japanese_only'])}",
        f"- option差分 {len(stats['option_mismatches'])} / type差分 {len(stats['type_mismatches'])}",
        f"- Itemsカテゴリ: EN {items['english_groups']} / JA {items['japanese_groups']}",
        f"- Items構造差分: {len(items['structure_mismatches'])}", "",
        "## Modメタデータ", "",
        f"- 追加 {len(diff.get('added', ())) } / 削除 {len(diff.get('removed', ())) } / 変更 {len(diff.get('changed', ())) }",
        f"- 未解決日本語Stat: {len(metadata.get('unresolved_japanese_stats', ())) }", "",
        "## pseudo", "",
        f"- definitions {pseudo['definitions']} / relations {pseudo['relations']}",
        f"- relations追加 {len(pseudo.get('diff', {}).get('added', ())) } / 削除 {len(pseudo.get('diff', {}).get('removed', ())) } / 変更 {len(pseudo.get('diff', {}).get('changed', ())) }",
        f"- エラー: {len(pseudo['errors'])}", "",
    ]
    if report.get("manifest"):
        lines.extend(["## 候補", "", f"- manifest: `{report['manifest']}`", ""])
    if report.get("representative_api") is not None:
        api = report["representative_api"]
        lines.extend([
            "## 代表Trade API確認", "",
            f"- リーグ: `{api['league']}`",
            f"- 成功 {len(api['passed'])} / 失敗 {len(api['failures'])}", "",
        ])
    if report.get("failures"):
        lines.extend(["## 停止理由", ""] + [f"- {value}" for value in report["failures"]] + [""])
    return "\n".join(lines)


def write_report(report: dict, json_path: Path = REPORT_JSON, md_path: Path = REPORT_MD) -> None:
    report["status"] = overall_status(report)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")


def _run(command: list[str], *, cwd: Path = ROOT) -> None:
    print("running:", " ".join(command))
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) if not existing else os.pathsep.join((str(ROOT), existing))
    subprocess.run(command, cwd=cwd, check=True, env=env)


def _fetch_official(fetcher: Callable[[str], tuple[dict, str]] = fetch_json) -> dict:
    payloads = {}
    hashes = {}
    for name, url in OFFICIAL_URLS.items():
        payloads[name], hashes[name] = fetcher(url)
    return {
        "sources": {name: {"url": OFFICIAL_URLS[name], "sha256": hashes[name]} for name in OFFICIAL_URLS},
        "stats": audit_bilingual_stats(payloads["stats_en"], payloads["stats_ja"]),
        "items": audit_bilingual_items(payloads["items_en"], payloads["items_ja"]),
    }


def verify_representative_trade_api(
    *, league: str = "Standard", cases: list[dict] | None = None,
    sender: Callable[[str, dict], dict] = post_json,
    pause: Callable[[float], None] = time.sleep,
) -> dict:
    """代表fixtureを本体と同じ英語公式Trade検索APIへ送って受理を確認する。"""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.poetore.parser import parse_item_text
    from src.poetore.trade import build_search_query, resolve_trade_stat_filters

    if cases is None:
        cases = load_json(ROOT / "tests/fixtures/poetore/step10_cases.json")
    results = []
    failures = []
    url = f"https://www.pathofexile.com/api/trade/search/{league}"
    for index, case in enumerate(cases):
        try:
            item = parse_item_text(case["text"])
            trade_name = case.get("trade_name")
            filters = resolve_trade_stat_filters(
                item, trade_base_type=case["trade_base"], trade_name=trade_name,
            )
            payload = build_search_query(
                item, case["trade_base"], filters, trade_name=trade_name,
            )
            response = sender(url, payload)
            query_id = str(response.get("id", ""))
            if not query_id:
                raise ValueError(str(response.get("error") or "search ID was not returned"))
            results.append({
                "id": case["id"], "query_id": query_id,
                "candidates": len(response.get("result", ())),
            })
        except Exception as error:  # noqa: BLE001 - 全ケースのAPI結果をまとめて返す
            failures.append({"id": case.get("id", f"case-{index}"), "error": str(error)})
        if index + 1 < len(cases):
            pause(2.5)
    return {"league": league, "passed": results, "failures": failures}


def _base_hashes(root: Path = ROOT) -> dict[str, str]:
    return {name: sha256_file(root / path) for name, path in AUTHORITATIVE.items()}


def _metadata_command(candidate: bool, official_mods_only: bool = False) -> list[str]:
    command = [sys.executable, "scripts/build_poetore_metadata.py"]
    if candidate:
        command.extend([
            "--lock", str(CANDIDATE_DIR / "poetore-sources.lock.json"),
            "--output", str(CANDIDATE_DIR / "mod_metadata.json"),
            "--report", str(CANDIDATE_DIR / "metadata-report.json"),
            "--official-baseline", str(CANDIDATE_DIR / "poetore-official-stats-baseline.json"),
            "--refresh-lock", "--apply",
        ])
    if official_mods_only:
        command.append("--official-mods-only")
    return command


def create_refresh_candidate(official: dict, official_mods_only: bool = False) -> tuple[dict, Path]:
    if CANDIDATE_DIR.exists():
        shutil.rmtree(CANDIDATE_DIR)
    CANDIDATE_DIR.mkdir(parents=True)
    base_hashes = _base_hashes()
    for name, source in AUTHORITATIVE.items():
        if name == "map_mods":
            continue
        shutil.copy2(ROOT / source, CANDIDATE_DIR / source.name)
    _run(_metadata_command(candidate=True, official_mods_only=official_mods_only))
    map_payload = build_catalog(
        ROOT / "vendor-sources/awakened-poe-trade-1e2225af.tar.gz",
        CANDIDATE_DIR / "mod_metadata.json",
    )
    (CANDIDATE_DIR / "map_mods.json").write_text(
        json.dumps(map_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lock = load_json(CANDIDATE_DIR / "poetore-sources.lock.json")
    awakened_revision = str(lock["sources"]["awakened_poe_trade"]["revision"])
    pseudo_payload = build_pseudo_relations_candidate(
        ROOT / "vendor-sources/awakened-poe-trade-1e2225af.tar.gz",
        awakened_revision,
    )
    (CANDIDATE_DIR / "pseudo_relations.json").write_text(
        json.dumps(pseudo_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata_report = load_json(CANDIDATE_DIR / "metadata-report.json")
    target_files = {
        name: {"target": str(path), "candidate": str((CANDIDATE_DIR / path.name).relative_to(ROOT))}
        for name, path in AUTHORITATIVE.items()
    }
    for name, row in target_files.items():
        row["base_sha256"] = base_hashes[name]
        row["candidate_sha256"] = sha256_file(ROOT / row["candidate"])
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "refresh",
        "root": str(ROOT),
        "files": target_files,
        "official_source_hashes": {name: row["sha256"] for name, row in official["sources"].items()},
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata_report, MANIFEST_PATH


def verify_manifest(manifest_path: Path, root: Path = ROOT) -> dict:
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != 1 or manifest.get("mode") != "refresh":
        raise ValueError("unsupported candidate manifest")
    if Path(str(manifest.get("root"))).resolve() != root.resolve():
        raise ValueError("candidate manifest belongs to another repository")
    for name, row in manifest.get("files", {}).items():
        target = (root / row["target"]).resolve()
        candidate = (root / row["candidate"]).resolve()
        if root.resolve() not in target.parents or root.resolve() not in candidate.parents:
            raise ValueError(f"manifest path escapes repository: {name}")
        if sha256_file(target) != row["base_sha256"]:
            raise ValueError(f"authoritative file changed after review: {name}")
        if sha256_file(candidate) != row["candidate_sha256"]:
            raise ValueError(f"candidate file hash mismatch: {name}")
    return manifest


def atomic_apply_manifest(
    manifest_path: Path, root: Path = ROOT,
    replace: Callable[[str | os.PathLike, str | os.PathLike], None] = os.replace,
) -> list[Path]:
    manifest = verify_manifest(manifest_path, root)
    rows = list(manifest["files"].values())
    applied: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="poetore-apply-", dir=root) as temp_name:
        temp = Path(temp_name)
        backups = {}
        staged = {}
        for index, row in enumerate(rows):
            target = root / row["target"]
            candidate = root / row["candidate"]
            backup = temp / f"{index}.backup"
            stage = target.with_name(f".{target.name}.poetore-apply")
            shutil.copy2(target, backup)
            shutil.copy2(candidate, stage)
            backups[target], staged[target] = backup, stage
        try:
            for target in backups:
                replace(staged[target], target)
                applied.append(target)
        except Exception:
            for target in reversed(applied):
                shutil.copy2(backups[target], target)
            raise
        finally:
            for stage in staged.values():
                stage.unlink(missing_ok=True)
    return applied


def run_audit(
    refresh: bool, official_mods_only: bool = False, verify_api: bool = False,
) -> dict:
    official = _fetch_official()
    pseudo = audit_pseudo_files()
    failures = list(pseudo["errors"])
    metadata = {}
    manifest = None
    try:
        if refresh:
            metadata, manifest = create_refresh_candidate(
                official, official_mods_only=official_mods_only,
            )
        else:
            _run(_metadata_command(candidate=False, official_mods_only=official_mods_only))
            metadata = load_json(ROOT / "build/poetore-metadata-report.json")
    except subprocess.CalledProcessError as error:
        failures.append(f"Modメタデータ監査が終了コード{error.returncode}で停止した")
    if not refresh:
        manifest = None
        with tempfile.TemporaryDirectory(prefix="poetore-map-audit-"):
            generated = build_catalog(
                ROOT / "vendor-sources/awakened-poe-trade-1e2225af.tar.gz",
                ROOT / AUTHORITATIVE["mod_metadata"],
            )
            current = load_json(ROOT / AUTHORITATIVE["map_mods"])
            if generated != current:
                failures.append("Map Mod派生データが固定入力からの再生成結果と一致しない")
            source_lock = load_json(ROOT / AUTHORITATIVE["source_lock"])
            pseudo_generated = build_pseudo_relations_candidate(
                ROOT / "vendor-sources/awakened-poe-trade-1e2225af.tar.gz",
                str(source_lock["sources"]["awakened_poe_trade"]["revision"]),
            )
            pseudo_current = load_json(ROOT / AUTHORITATIVE["pseudo_relations"])
            if pseudo_generated != pseudo_current:
                failures.append("pseudo relationsが固定Awakened原本からの再生成結果と一致しない")
            pseudo["diff"] = diff_pseudo_relations(pseudo_current, pseudo_generated)
    elif manifest is not None:
        pseudo["diff"] = diff_pseudo_relations(
            load_json(ROOT / AUTHORITATIVE["pseudo_relations"]),
            load_json(CANDIDATE_DIR / "pseudo_relations.json"),
        )
    api_result = None
    if verify_api and not failures:
        api_result = verify_representative_trade_api()
        if api_result["failures"]:
            failures.append(
                f"代表Trade API確認に{len(api_result['failures'])}件失敗した"
            )
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "refresh" if refresh else "audit",
        "official_mods_only": official_mods_only,
        "official_trade": official,
        "metadata": metadata,
        "pseudo": pseudo,
        "representative_api": api_result,
        "failures": failures,
        "manifest": str(manifest.relative_to(ROOT)) if manifest else None,
    }
    write_report(report)
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ぽえとれTradeデータを一括監査・安全更新")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--refresh", action="store_true", help="最新候補と差分レポートを生成する")
    group.add_argument("--apply", type=Path, metavar="MANIFEST", help="レビュー済み候補を原子的に反映する")
    parser.add_argument(
        "--official-mods-only", action="store_true",
        help="Awakened取得不能時に公式Trade＋RePoE＋独自台帳だけで監査・更新する",
    )
    parser.add_argument(
        "--verify-api", action="store_true",
        help="代表12 fixtureを公式Trade検索APIへ実送信して受理を確認する",
    )
    args = parser.parse_args(argv)
    if args.apply:
        if args.official_mods_only or args.verify_api:
            parser.error("--official-mods-only/--verify-api cannot be combined with --apply")
        applied = atomic_apply_manifest(args.apply.resolve())
        print("applied reviewed candidate:")
        for path in applied:
            print(f"  {path.relative_to(ROOT)}")
        return 0
    report = run_audit(
        refresh=args.refresh, official_mods_only=args.official_mods_only,
        verify_api=args.verify_api,
    )
    print(f"{report['status']}: {REPORT_MD.relative_to(ROOT)}")
    return 2 if report["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
