from dataclasses import replace

import pytest

from src.poetore.parser import parse_item_text
from src.poetore import trade


SAMPLE = """アイテムクラス: マップフラグメント
レアリティ: ノーマル
傭兵の召喚状
--------
シアクサンの暗殺者、ラゼス
--------
ビルド: 悪名高きリアニメーター
傭兵のレベル: 83
--------
巨人化のゾンビ蘇生
ミニオンライフ (ティア: 2)
ミニオンコースティックデス (ティア: 3)
ブルータリティ (ティア: 2)
マルチストライク (ティア: 2)
金色の鈍重の使者 (ティア: 3)
--------
デセクレート
セカンドウィンド (ティア: 3)
グレーター持続時間上昇 (ティア: 3)
--------
レリックオブバインディング
--------
このアイテムを右クリックして傭兵の詳細を見る。
マップデバイスでマップと共に使用する。
""".strip()


STAT_ENTRIES = (
    {"id": "mercenary.skill_52491", "text": "巨人化のゾンビ蘇生", "type": "mercenary"},
    {"id": "mercenary.support_wrong", "text": "ミニオンライフ (ティア 1)", "type": "mercenary"},
    {"id": "mercenary.support_20579", "text": "ミニオンライフ (ティア 2)", "type": "mercenary"},
    {"id": "mercenary.support_13016", "text": "ミニオンコースティックデス (ティア 3)", "type": "mercenary"},
    {"id": "mercenary.skill_21523", "text": "デセクレート", "type": "mercenary"},
    {"id": "mercenary.skill_relic", "text": "レリックオブバインディング", "type": "mercenary"},
)


def test_parses_warrant_build_skills_and_support_tiers():
    item = parse_item_text(SAMPLE)
    assert item.category == "invitation"
    assert item.properties == {
        "傭兵名": "シアクサンの暗殺者、ラゼス",
        "ビルド": "悪名高きリアニメーター",
        "傭兵のレベル": "83",
    }
    assert [row.text for row in item.modifiers[:2]] == [
        "巨人化のゾンビ蘇生", "ミニオンライフ (ティア: 2)",
    ]
    assert item.modifiers[0].tier is None
    assert item.modifiers[1].tier == 2
    assert item.modifiers[-1].text == "レリックオブバインディング"


def test_resolves_mercenary_stats_exactly_by_tier(monkeypatch):
    item = parse_item_text(SAMPLE)
    monkeypatch.setattr(trade, "_stat_entries_cache", STAT_ENTRIES)
    monkeypatch.setattr(trade, "_stat_entry_indexes_cache", None)
    filters = trade.resolve_trade_stat_filters(item)
    by_text = {row.text: row for row in filters}
    assert by_text["ミニオンライフ (ティア: 2)"].stat_id == "mercenary.support_20579"
    assert "mercenary.support_wrong" not in {row.stat_id for row in filters}
    assert all(not row.enabled for row in filters)
    assert trade.unresolved_modifier_warnings(item, filters) == ()


def test_builds_variant_identity_and_selected_skill_query(monkeypatch):
    item = parse_item_text(SAMPLE)
    monkeypatch.setattr(trade, "_stat_entries_cache", STAT_ENTRIES)
    monkeypatch.setattr(trade, "_stat_entry_indexes_cache", None)
    monkeypatch.setattr(trade, "_jp_item_entries_cache", ({
        "type": "ChaosMinionWitchInstabilityNoble",
        "text": "傭兵の召喚状 (悪名高きリアニメーター)",
        "disc": "mercenary_warrant",
    },))
    monkeypatch.setattr(trade, "_item_entries_cache", ())
    selected = tuple(
        replace(row, enabled=row.stat_id in {"mercenary.skill_52491", "mercenary.skill_21523"})
        for row in trade.resolve_trade_stat_filters(item)
    )
    query = trade.build_search_query(item, stat_filters=selected)["query"]
    assert query["type"] == {
        "option": "ChaosMinionWitchInstabilityNoble",
        "discriminator": "mercenary_warrant",
    }
    assert query["stats"][0]["filters"] == [
        {"id": "mercenary.skill_52491", "value": {}},
        {"id": "mercenary.skill_21523", "value": {}},
    ]


def test_rejects_unknown_build_variant(monkeypatch):
    item = parse_item_text(SAMPLE)
    monkeypatch.setattr(trade, "_jp_item_entries_cache", ())
    monkeypatch.setattr(trade, "_item_entries_cache", ())
    with pytest.raises(ValueError, match="公式Tradeデータ"):
        trade.build_search_query(item)
