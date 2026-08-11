import csv
import json

from scripts.export_poetore_multi_value_review import build_rows, build_rules, export_review


def test_build_rows_excludes_single_and_handled_added_damage_ranges():
    payload = {"mods": [
        {"stat_id": "implicit.one", "kind": "implicit", "ref": "one",
         "japanese": ["1個ごとに#%回復する"]},
        {"stat_id": "explicit.damage", "kind": "explicit", "ref": "damage",
         "japanese": ["#から#の雷ダメージをアタックに追加する"]},
        {"stat_id": "explicit.review", "kind": "explicit", "ref": "duration/effect",
         "japanese": ["#秒間、効果が#%増加する"]},
    ]}

    rows = build_rows(payload)

    assert len(rows) == 1
    assert rows[0]["stat_id"] == "explicit.review"
    assert rows[0]["placeholder_count"] == 2
    assert rows[0]["reviewer_decision"] == ""


def test_export_review_writes_excel_friendly_csv(tmp_path):
    source = tmp_path / "metadata.json"
    output = tmp_path / "review.csv"
    source.write_text(json.dumps({"mods": [{
        "stat_id": "explicit.review", "kind": "explicit", "ref": "duration/effect",
        "japanese": ["#秒間、効果が#%増加する"],
    }]}, ensure_ascii=False), encoding="utf-8")

    assert export_review(source, output) == 1
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["japanese_template"] == "#秒間、効果が#%増加する"


def test_build_rules_maps_review_decisions_and_percentage_position():
    rows = [
        {"stat_id": "explicit.percent", "japanese_template": "#秒間、効果が#%増加する",
         "reviewer_decision": "「#%」のほうの値を使う"},
        {"stat_id": "explicit.blank", "japanese_template": "毎秒#を#秒間与える",
         "reviewer_decision": "検索条件がまったく意味わからないので、検索値のデフォルトは空白でよい"},
    ]

    rules = build_rules(rows)["rules"]

    assert rules[0]["operation"] == "index"
    assert rules[0]["value_index"] == 1
    assert rules[1]["operation"] == "blank"
