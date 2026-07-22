from __future__ import annotations

import csv
from pathlib import Path

from src.poetore import parse_item_text
from src.poetore.trade import build_search_query, resolve_trade_stat_filters


SAMPLE_CSV = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "poetore-parser-sample-collection.csv"
)

EXPECTED = {
    "WPN": ("weapon", 5, 5),
    "ARM": ("armour", 4, 5),
    "ACC": ("accessory", 8, 8),
    "UNI": ("armour", 5, 5),
    "FLA": ("flask", 3, 3),
    "GEM": ("gem", 0, 0),
    "MAP": ("map", 6, 6),
    "JWL": ("jewel", 3, 3),
    "CLU": ("cluster_jewel", 7, 7),
    "VEI": ("weapon", 6, 6),
    "FRA": ("weapon", 5, 5),
    "INF": ("armour", 10, 10),
    "COR": ("armour", 8, 8),
    "BLI": ("map", 10, 10),
    "HEI": ("heist_blueprint", 1, 1),
    "LOG": ("expedition_logbook", 6, 6),
    "ENG": ("armour", 10, 10),
    "MIR": ("accessory", 5, 5),
    "SYN": ("weapon", 7, 7),
    "UID": ("weapon", 1, 1),
    "FOU": ("accessory", 5, 5),
    "ABY": ("abyss_jewel", 4, 4),
    "TIN": ("tincture", 4, 4),
    "VAL": ("map", 9, 9),
    "CUR": ("currency", 0, 0),
    "BST": ("captured_beast", 6, 6),
    "ULT": ("map", 0, 0),
}

EXPECTED_FLAGS = {
    "MIR": {"mirrored"},
    "SYN": {"synthesised"},
    "UID": {"unidentified"},
    "FOU": {"foulborn"},
    "VAL": {"unmodifiable", "foil"},
}

FORBIDDEN_HELP_TEXT = (
    "右クリックして飲む",
    "自身のマップデバイスで使用することで",
    "ローグハーバーにいる特定のNPC",
    "このアイテムをダニグに渡し",
    "右クリックしてソケットから取り外す",
    "管理者クォトラ",
    "最大リーチ速度に達するまで",
    "アタックダメージブロック率の最大値は",
    "テンポラルチェーンは呪術の一種",
    "Recently refers to the past",
    "右クリックで活性化する",
    "怪獣園に追加",
    "全モンスターの90%を倒すことで報酬",
    "このアイテムを右クリックした後",
    "トライアルマスターの領域",
)


def _samples():
    with SAMPLE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _filled_samples():
    return [row for row in _samples() if row["貼り付け本文"].strip()]


def test_all_collected_samples_parse_with_expected_category_and_mod_count():
    rows = _samples()
    assert len(rows) == 54
    rows = _filled_samples()
    assert len(rows) == 54

    for row in rows:
        item = parse_item_text(row["貼り付け本文"])
        family = row["ID"].split("-", 1)[0]
        expected_category, normal_count, detailed_count = EXPECTED[family]
        expected_count = detailed_count if row["ID"].endswith("-D") else normal_count
        assert item.category == expected_category, row["ID"]
        assert len(item.modifiers) == expected_count, row["ID"]


def test_collected_samples_detect_expected_item_flags():
    parsed = {
        row["ID"]: parse_item_text(row["貼り付け本文"])
        for row in _filled_samples()
    }
    for family, expected_flags in EXPECTED_FLAGS.items():
        for suffix in ("N", "D"):
            item = parsed[f"{family}-01-{suffix}"]
            assert expected_flags <= set(item.flags), f"{family}-01-{suffix}"


def test_collected_samples_never_expose_help_or_flavour_text_as_modifiers():
    for row in _filled_samples():
        item = parse_item_text(row["貼り付け本文"])
        modifier_text = "\n".join(modifier.text for modifier in item.modifiers)
        assert not any(text in modifier_text for text in FORBIDDEN_HELP_TEXT), row["ID"]


def test_normal_and_detailed_samples_resolve_the_same_known_trade_stats():
    parsed = {
        row["ID"]: parse_item_text(row["貼り付け本文"])
        for row in _filled_samples()
    }
    for family in EXPECTED:
        normal = parsed[f"{family}-01-N"]
        detailed = parsed[f"{family}-01-D"]
        normal_stats = {mod.stat_id for mod in normal.modifiers if mod.stat_id}
        detailed_stats = {mod.stat_id for mod in detailed.modifiers if mod.stat_id}
        # 詳細コピーだけがFractured／Veiledの専用stat IDを識別できる。
        assert normal_stats <= detailed_stats, family


def test_all_collected_samples_can_build_trade_queries():
    for row in _filled_samples():
        item = parse_item_text(row["貼り付け本文"])
        stat_filters = resolve_trade_stat_filters(item)
        payload = build_search_query(item, stat_filters=stat_filters)
        assert payload["query"]["status"]["option"], row["ID"]
        assert isinstance(payload["query"]["stats"], list), row["ID"]
