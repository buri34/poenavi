from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from ..models import ItemModifier, ParsedItem
from ..trade import PRESET_BASE, PRESET_FINISHED, available_trade_presets
from .parser import TRADE_CATEGORY_BY_CATEGORY, parse_item_text
from .trade import build_search_query, poe2_trade_filters


_EQUIPMENT_FIXTURES = {
    "bow": ("Bows", "Rider Bow"),
    "crossbow": ("Crossbows", "Advanced Crossbow"),
    "spear": ("Spears", "Flying Spear"),
    "flail": ("Flails", "Advanced Flail"),
    "staff": ("Staves", "Advanced Staff"),
    "quarterstaff": ("Quarterstaves", "Advanced Quarterstaff"),
    "wand": ("Wands", "Imbued Wand"),
    "sceptre": ("Sceptres", "Advanced Sceptre"),
    "one_mace": ("One Hand Maces", "Advanced Mace"),
    "two_mace": ("Two Hand Maces", "Advanced Great Mace"),
    "one_sword": ("One Hand Swords", "Advanced Sword"),
    "two_sword": ("Two Hand Swords", "Advanced Greatsword"),
    "one_axe": ("One Hand Axes", "Advanced Axe"),
    "two_axe": ("Two Hand Axes", "Advanced Greataxe"),
    "dagger": ("Daggers", "Advanced Dagger"),
    "talisman": ("Talismans", "Nettle Talisman"),
    "focus": ("Foci", "Crystal Focus"),
    "buckler": ("Bucklers", "Advanced Buckler"),
    "shield": ("Shields", "Advanced Shield"),
    "body_armour": ("Body Armours", "Sacred Chainmail"),
    "helmet": ("Helmets", "Advanced Helmet"),
    "gloves": ("Gloves", "Grand Bracers"),
    "boots": ("Boots", "Advanced Greaves"),
    "quiver": ("Quivers", "Advanced Quiver"),
    "ring": ("Rings", "Prismatic Ring"),
    "amulet": ("Amulets", "Gold Amulet"),
    "belt": ("Belts", "Utility Belt"),
}
_RARITIES = ("normal", "magic", "rare", "unique")


@dataclass(frozen=True)
class AuditRow:
    case_id: str
    category: str
    item_class: str
    rarity: str
    preset: str
    scope: str
    fixture_kind: str
    status: str
    ui_status: str
    expected_trade_category: str
    observed_trade_category: str
    expected_type: str
    observed_type: str
    expected_name: str
    observed_name: str
    expected_rarity: str
    observed_rarity: str
    expected_stat_count: int
    observed_stat_count: int
    notes: str


def _item(category: str, rarity: str) -> ParsedItem:
    item_class, base_type = _EQUIPMENT_FIXTURES[category]
    modifier = ItemModifier(
        "Synthetic audit modifier", (17.0,), stat_id="explicit.stat_2923486259",
    )
    return ParsedItem(
        item_class=item_class,
        rarity=rarity,
        name="Synthetic Unique" if rarity == "unique" else "Synthetic Item",
        base_type=base_type,
        category=category,
        item_level=85,
        modifiers=() if rarity == "normal" else (modifier,),
        raw_text=f"audit:{category}:{rarity}",
    )


def _observed_rarity(query: dict) -> str:
    type_filters = query["filters"]["type_filters"]["filters"]
    return str((type_filters.get("rarity") or {}).get("option", ""))


def _stat_count(query: dict) -> int:
    return sum(len(group.get("filters", ())) for group in query.get("stats", ()))


def build_audit_rows() -> list[AuditRow]:
    rows: list[AuditRow] = []
    for category, (item_class, base_type) in _EQUIPMENT_FIXTURES.items():
        for rarity in _RARITIES:
            item = _item(category, rarity)
            presets = available_trade_presets(item)
            for preset in (PRESET_FINISHED, PRESET_BASE):
                if preset not in presets:
                    rows.append(AuditRow(
                        f"{category}:{rarity}:{preset}:n/a", category, item_class,
                        rarity, preset, "n/a", "synthetic", "仕様上対象外", "仕様上対象外",
                        TRADE_CATEGORY_BY_CATEGORY[category], "", base_type, "",
                        item.name if rarity == "unique" else "", "",
                        "unique" if rarity == "unique" else "nonunique", "",
                        0, 0, "このレアリティではベースプリセットを提供しない",
                    ))
                    continue
                scopes = ("exact",) if rarity == "unique" else ("exact", "class")
                for scope in scopes:
                    filters = poe2_trade_filters(item, preset=preset)
                    query = build_search_query(
                        item, stat_filters=filters, exact_base_type=scope == "exact",
                    )["query"]
                    observed_category = str(
                        query["filters"]["type_filters"]["filters"]["category"]["option"]
                    )
                    expected_type = base_type if scope == "exact" else ""
                    observed_type = str(query.get("type", ""))
                    expected_name = item.name if rarity == "unique" else ""
                    observed_name = str(query.get("name", ""))
                    # Named uniques are already fully identified by name + type, so
                    # Trade2's minimal query intentionally omits a redundant rarity.
                    expected_rarity = "" if rarity == "unique" else "nonunique"
                    observed_rarity = _observed_rarity(query)
                    expected_stats = 1 if preset == PRESET_FINISHED and rarity != "normal" else 0
                    observed_stats = _stat_count(query)
                    checks = (
                        observed_category == TRADE_CATEGORY_BY_CATEGORY[category],
                        observed_type == expected_type,
                        observed_name == expected_name,
                        observed_rarity == expected_rarity,
                        observed_stats == expected_stats,
                    )
                    rows.append(AuditRow(
                        f"{category}:{rarity}:{preset}:{scope}", category, item_class,
                        rarity, preset, scope, "synthetic",
                        "自動検証済み" if all(checks) else "不具合",
                        "自動UI監査対象・Windows実機確認待ち",
                        TRADE_CATEGORY_BY_CATEGORY[category], observed_category,
                        expected_type, observed_type, expected_name, observed_name,
                        expected_rarity, observed_rarity, expected_stats, observed_stats,
                        "構造総当たり。実コピー固有の翻訳・同定は別監査",
                    ))
    return rows


def audit_real_copy_pairs(csv_source: Path) -> list[dict]:
    audited = []
    with csv_source.open(encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    for source in source_rows:
        fixture_id = source["fixture_id"]
        ja_text = source["日本語設定の詳細コピー全文"].strip()
        en_text = source["英語設定の詳細コピー全文"].strip()
        placeholder = any(
            marker in f"{ja_text}\n{en_text}".upper()
            for marker in ("INCOMPLETE", "未完", "WIP", "保留")
        )
        row = {
            "fixture_id": fixture_id,
            "target": source["収集対象"],
            "source_status": source["状態"],
            "audit_status": "実コピー待ち",
            "ja_category": "", "en_category": "",
            "ja_base_type": "", "en_base_type": "",
            "trade_category": "", "exact_type": "",
            "notes": "日英いずれかが空欄またはプレースホルダー",
        }
        if ja_text and en_text and not placeholder:
            try:
                ja_item = parse_item_text(ja_text)
                en_item = parse_item_text(en_text)
                payload = build_search_query(ja_item)["query"]
                trade_category = str(
                    payload["filters"]["type_filters"]["filters"]
                    .get("category", {}).get("option", "")
                )
                row.update({
                    "ja_category": ja_item.category,
                    "en_category": en_item.category,
                    "ja_base_type": ja_item.base_type,
                    "en_base_type": en_item.base_type,
                    "trade_category": trade_category,
                    "exact_type": str(payload.get("type", "")),
                })
                matched = (
                    ja_item.category == en_item.category
                    and ja_item.base_type == en_item.base_type
                    and payload.get("type") == ja_item.base_type
                )
                row["audit_status"] = "自動検証済み" if matched else "不具合"
                row["notes"] = "日英解析と最終Trade2 identityが一致" if matched else "日英またはTrade2 identity不一致"
            except (ValueError, KeyError) as exc:
                row["audit_status"] = "不具合"
                row["notes"] = f"{type(exc).__name__}: {exc}"
        audited.append(row)
    return audited


def write_reports(output_dir: Path) -> tuple[Path, Path, list[AuditRow]]:
    rows = build_audit_rows()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "search-matrix-audit.csv"
    json_path = output_dir / "search-matrix-audit.json"
    real_csv_path = output_dir / "search-real-copy-audit.csv"
    fieldnames = list(asdict(rows[0]))
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    repo_root = Path(__file__).resolve().parents[3]
    real_rows = audit_real_copy_pairs(
        repo_root / "tests" / "fixtures" / "poe2" / "real_copy_bilingual.csv"
    )
    with real_csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(real_rows[0]), lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(real_rows)
    summary = {
        "schema_version": 1,
        "scope": "PoE2 equipment rarity × preset × base scope structural audit",
        "limitations": [
            "Synthetic fixtures verify branching and final Trade2 JSON structure.",
            "Japanese/English identity and real-client copy coverage remains bounded by captured fixtures.",
            "Windows visual/interaction verification is tracked separately in ui_status.",
        ],
        "counts": {
            status: sum(row.status == status for row in rows)
            for status in ("自動検証済み", "仕様上対象外", "不具合")
        },
        "real_copy_counts": {
            status: sum(row["audit_status"] == status for row in real_rows)
            for status in ("自動検証済み", "実コピー待ち", "不具合")
        },
        "real_copy_report": real_csv_path.name,
        "rows": [asdict(row) for row in rows],
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return csv_path, json_path, rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit PoE2 Trade2 search-pattern matrix")
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("docs/poetore-poe2-testing"),
    )
    args = parser.parse_args()
    csv_path, json_path, rows = write_reports(args.output_dir)
    failures = [row for row in rows if row.status == "不具合"]
    summary = json.loads(json_path.read_text(encoding="utf-8"))
    real_failures = int(summary["real_copy_counts"]["不具合"])
    print(
        f"rows={len(rows)} failures={len(failures)} csv={csv_path} "
        f"real_csv={args.output_dir / 'search-real-copy-audit.csv'} json={json_path}"
    )
    return bool(failures or real_failures)


if __name__ == "__main__":
    raise SystemExit(main())
