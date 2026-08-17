from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QCheckBox

from src.poetore.parser import parse_item_text
from src.poetore import trade
from src.poetore.ui import PoetoreWindow, _MOD_COLUMN_CHECK


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
    {"id": "mercenary.support_64271", "text": "ブルータリティ (ティア 2)", "type": "mercenary"},
    {"id": "mercenary.support_62638", "text": "マルチストライク (ティア 2)", "type": "mercenary"},
    {"id": "mercenary.support_29562", "text": "金色の鈍重の使者 (ティア 3)", "type": "mercenary"},
    {"id": "mercenary.skill_21523", "text": "デセクレート", "type": "mercenary"},
    {"id": "mercenary.skill_relic", "text": "レリックオブバインディング", "type": "mercenary"},
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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


def test_awakened_mercenary_group_support_family_and_six_link(monkeypatch):
    item = parse_item_text(SAMPLE)
    monkeypatch.setattr(trade, "_stat_entries_cache", STAT_ENTRIES)
    monkeypatch.setattr(trade, "_stat_entry_indexes_cache", None)
    monkeypatch.setattr(trade, "_jp_item_entries_cache", ({
        "type": "ChaosMinionWitchInstabilityNoble",
        "text": "傭兵の召喚状 (悪名高きリアニメーター)",
        "disc": "mercenary_warrant",
    },))
    monkeypatch.setattr(trade, "_item_entries_cache", ({
        "type": "ChaosMinionWitchInstabilityNoble",
        "text": "Mercenary's Warrant (Reanimator)",
        "disc": "mercenary_warrant",
    },))

    filters = trade.resolve_trade_stat_filters(item)
    zombie = next(row for row in filters if row.stat_id == "mercenary.skill_52491")
    minion_life = next(row for row in filters if row.stat_id == "mercenary.support_20579")
    six_link = next(row for row in filters if row.mercenary_role == "six_link")
    assert zombie.mercenary_role == "primary_skill"
    assert minion_life.mercenary_group == zombie.mercenary_group
    assert minion_life.mercenary_ids == (
        "mercenary.support_20579", "mercenary.support_31863",
    )
    assert six_link.min_value == 2

    selected = tuple(
        replace(row, enabled=row is six_link or row is minion_life)
        for row in filters
    )
    query = trade.build_search_query(item, stat_filters=selected)["query"]
    groups = [group for group in query["stats"] if group["type"] == "mercenary"]
    assert len(groups) == 2
    assert groups[0]["value"]["min"] >= 6
    assert sum(
        row["id"] == "mercenary.skill_52491"
        for row in groups[0]["filters"]
    ) > 1
    assert groups[1]["value"]["min"] >= 3


def test_excluding_unlinked_support_forces_six_link_search(monkeypatch):
    item = parse_item_text(SAMPLE)
    monkeypatch.setattr(trade, "_stat_entries_cache", STAT_ENTRIES)
    monkeypatch.setattr(trade, "_stat_entry_indexes_cache", None)
    filters = trade.resolve_trade_stat_filters(item)
    excluded = next(row for row in filters if row.mercenary_role == "not_support")
    selected = tuple(replace(row, enabled=row is excluded) for row in filters)

    query = trade.build_search_query(item, stat_filters=selected)["query"]
    groups = [group for group in query["stats"] if group["type"] == "mercenary"]
    assert len(groups) == 1
    sent_ids = {row["id"] for row in groups[0]["filters"]}
    assert not sent_ids.intersection(excluded.mercenary_ids)


def test_kineticist_bad_skill_is_excluded_by_default(monkeypatch):
    sample = """アイテムクラス: マップフラグメント
レアリティ: ノーマル
傭兵の召喚状
--------
テスト傭兵
--------
ビルド: テスト
傭兵のレベル: 83
--------
エレメンタルウィークネス
--------
フレイムウォール
--------
このアイテムを右クリックして傭兵の詳細を見る。
""".strip()
    monkeypatch.setattr(trade, "_stat_entries_cache", (
        {"id": "mercenary.skill_5689", "text": "エレメンタルウィークネス", "type": "mercenary"},
        {"id": "mercenary.skill_57450", "text": "フレイムウォール", "type": "mercenary"},
    ))
    monkeypatch.setattr(trade, "_stat_entry_indexes_cache", None)
    monkeypatch.setattr(trade, "_jp_item_entries_cache", ({
        "type": "KineticistVariant", "text": "傭兵の召喚状 (テスト)",
        "disc": "mercenary_warrant",
    },))
    monkeypatch.setattr(trade, "_item_entries_cache", ())
    filters = trade.resolve_trade_stat_filters(parse_item_text(sample))
    kinetic_bolt = next(row for row in filters if row.ref == "Kinetic Bolt")
    assert kinetic_bolt.mercenary_role == "missing_skill"
    assert kinetic_bolt.enabled

    query = trade.build_search_query(
        parse_item_text(sample), stat_filters=filters,
    )["query"]
    not_group = next(group for group in query["stats"] if group["type"] == "not")
    assert {row["id"] for row in not_group["filters"]} == {"mercenary.skill_12583"}


def test_rejects_unknown_build_variant(monkeypatch):
    item = parse_item_text(SAMPLE)
    monkeypatch.setattr(trade, "_jp_item_entries_cache", ())
    monkeypatch.setattr(trade, "_item_entries_cache", ())
    with pytest.raises(ValueError, match="公式Tradeデータ"):
        trade.build_search_query(item)


def test_warrant_ui_reveals_supports_without_losing_selected_skills(
    qapp, monkeypatch,
):
    monkeypatch.setattr(trade, "_stat_entries_cache", STAT_ENTRIES)
    monkeypatch.setattr(trade, "_stat_entry_indexes_cache", None)
    window = PoetoreWindow()
    try:
        window.input_edit.setPlainText(SAMPLE)
        window.parse_current_text()

        rows = [
            window.mod_filter_tree.topLevelItem(index)
            for index in range(window.mod_filter_tree.topLevelItemCount())
        ]
        main_rows = [
            row for row in rows
            if row.data(0, Qt.UserRole + 4).mercenary_role in {
                "skill", "primary_skill",
            }
        ]
        support_rows = [
            row for row in rows
            if row.data(0, Qt.UserRole + 4).mercenary_role == "support"
        ]
        six_link_rows = [
            row for row in rows
            if row.data(0, Qt.UserRole + 4).mercenary_role == "six_link"
        ]
        assert main_rows and support_rows
        assert six_link_rows
        assert all(not row.isHidden() for row in main_rows)
        assert all(row.isHidden() for row in support_rows)
        assert all(row.isHidden() for row in six_link_rows)
        assert not window.mercenary_supports_toggle.isHidden()
        assert window.mercenary_supports_toggle.text() == "傭兵のサポートジェムを表示"
        window.show()
        qapp.processEvents()
        mod_actions_bottom = max(
            widget.mapTo(window, QPoint(0, 0)).y() + widget.height()
            for widget in (
                window.mod_conditions_toggle,
                window.clear_mod_conditions_button,
                window.hidden_mods_toggle,
                window.mod_sources_toggle,
            )
        )
        support_button_top = window.mercenary_supports_toggle.mapTo(
            window, QPoint(0, 0),
        ).y()
        assert support_button_top > mod_actions_bottom
        assert (
            window.mercenary_supports_toggle.width()
            >= window.mercenary_supports_toggle.sizeHint().width()
        )

        main_checkbox = window.mod_filter_tree.itemWidget(
            main_rows[0], _MOD_COLUMN_CHECK,
        ).findChild(QCheckBox, "modFilterCheckbox")
        main_checkbox.setChecked(True)
        window.mercenary_supports_toggle.click()

        assert all(not row.isHidden() for row in main_rows + support_rows + six_link_rows)
        assert main_checkbox.isChecked()
        selected = {
            row.stat_id for row in window._selected_stat_filters() if row.enabled
        }
        assert main_rows[0].data(0, Qt.UserRole + 4).stat_id in selected
    finally:
        window.close()


def test_mercenary_support_toggle_is_hidden_for_other_items(qapp):
    window = PoetoreWindow()
    try:
        window._populate_stat_filters(())
        assert window.mercenary_supports_toggle.isHidden()
        assert window.mercenary_supports_actions_widget.isHidden()
    finally:
        window.close()
