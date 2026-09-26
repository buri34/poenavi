from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/poetore-poe2-testing/windows-test-cases.csv"
TARGET = ROOT / "docs/poetore-poe2-testing/windows-test-run.csv"


FIELDNAMES = [
    "実施順",
    "ケースID",
    "優先度",
    "試験グループ",
    "対象アイテム",
    "操作",
    "確認A_識別・ヘッダー",
    "【記入】A結果",
    "確認B_チップ・初期状態",
    "【記入】B結果",
    "確認C_検索先・条件",
    "【記入】C結果",
    "詳細コピー要件",
    "【記入】詳細コピー保存名",
    "【記入】実施日",
    "【記入】PoENaviコミット",
    "【記入】検索応答",
    "【記入】表示件数",
    "【記入】価格表示",
    "【記入】公式Trade・Ninja URL",
    "【記入】画像名",
    "【記入】総合結果",
    "【記入】見えた差分・メモ",
]


def copy_requirement(row: dict[str, str]) -> str:
    if row["日本語設定の詳細コピー全文"].startswith("@"):
        return "収集済みfixtureを使用（日英の新規貼付不要）"
    if row["ケースID"] in {"P2-WIN-057", "P2-WIN-067"}:
        if row["ケースID"] == "P2-WIN-067":
            return "同じ現物の日本語通常コピーと詳細コピーを保存（両方必須）"
        return "同じ現物の日本語・英語を保存（両方必須）"
    return "使用した現物の日本語を保存（英語は差分発生時に追加依頼）"


def build_rows(source: Path = SOURCE) -> list[dict[str, str]]:
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    output: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        output.append(
            {
                "実施順": str(index),
                "ケースID": row["ケースID"],
                "優先度": row["優先度"],
                "試験グループ": row["試験グループ"],
                "対象アイテム": row["対象アイテム・入手条件"],
                "操作": row["事前条件・操作"],
                "確認A_識別・ヘッダー": row["期待する識別・ヘッダー"],
                "【記入】A結果": "未確認",
                "確認B_チップ・初期状態": row["期待する検索チップ・初期状態"],
                "【記入】B結果": "未確認",
                "確認C_検索先・条件": row["期待する検索先・クエリ要点"],
                "【記入】C結果": "未確認",
                "詳細コピー要件": copy_requirement(row),
                "【記入】詳細コピー保存名": "",
                "【記入】実施日": "",
                "【記入】PoENaviコミット": "",
                "【記入】検索応答": "未検索",
                "【記入】表示件数": "",
                "【記入】価格表示": "未確認",
                "【記入】公式Trade・Ninja URL": "",
                "【記入】画像名": "",
                "【記入】総合結果": "未実施",
                "【記入】見えた差分・メモ": "",
            }
        )
    return output


def write_sheet(target: Path = TARGET) -> None:
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(build_rows())


if __name__ == "__main__":
    write_sheet()
