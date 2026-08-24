import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate_poe2_windows_test_sheet.py"
SPEC = importlib.util.spec_from_file_location("generate_poe2_windows_test_sheet", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

FIELDNAMES = MODULE.FIELDNAMES
build_rows = MODULE.build_rows
copy_requirement = MODULE.copy_requirement


def test_build_rows_preserves_all_detailed_cases() -> None:
    rows = build_rows()

    assert len(rows) == 64
    assert rows[0]["ケースID"] == "P2-WIN-001"
    assert rows[-1]["ケースID"] == "P2-WIN-064"
    assert list(rows[0]) == FIELDNAMES

    flail = next(row for row in rows if row["ケースID"] == "P2-WIN-004")
    assert "Unique Flail" in flail["対象アイテム"]
    assert "Rare Flail" not in flail["対象アイテム"]
    assert "weapon.flail" in flail["確認C_検索先・条件"]

    logbook = next(row for row in rows if row["ケースID"] == "P2-WIN-051")
    assert logbook["対象アイテム"] == "エクスペディションログブック"
    assert "Area/Faction/明示Mod条件を表示しない" in logbook["確認B_チップ・初期状態"]
    assert "poe.ninja Expedition" in logbook["確認C_検索先・条件"]


def test_copy_requirements_are_explicit() -> None:
    assert copy_requirement(
        {
            "ケースID": "P2-WIN-001",
            "日本語設定の詳細コピー全文": "",
        }
    ).startswith("使用した現物の日本語")
    assert copy_requirement(
        {
            "ケースID": "P2-WIN-057",
            "日本語設定の詳細コピー全文": "",
        }
    ).startswith("同じ現物の日本語・英語")
    assert copy_requirement(
        {
            "ケースID": "P2-WIN-062",
            "日本語設定の詳細コピー全文": "@mageblood_ja.txt",
        }
    ).startswith("収集済みfixture")
