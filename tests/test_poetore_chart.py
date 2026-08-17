import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.poetore.parser import parse_item_text
from src.poetore import trade
from src.poetore.trade import (
    PRESET_BULK, PRESET_FINISHED, available_trade_presets,
    build_search_query, is_special_chart_area, resolve_trade_stat_filters,
)
from src.poetore.ui import PoetoreWindow


CHART_CASES = (
    ("砂の海底の海図", "深海平原", 83, 32, 76, 18, None),
    ("サンゴの森の海図", "海底の木立", 82, 64, 20, None, 60),
    ("サンゴ礁の海図", "海底の尾根", 82, 32, 40, 16, None),
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def chart_text(base, area, level, quantity=None, rarity=None, pack=None, sulphur=None):
    props = [area, f"エリアレベル: {level}"]
    for label, value in (
        ("アイテム数量", quantity), ("アイテムレアリティ", rarity),
        ("モンスターパックサイズ", pack), ("死人の硫黄", sulphur),
    ):
        if value is not None:
            props.append(f"{label}: +{value}% (augmented)")
    return "\n".join((
        "アイテムクラス: 海図", "レアリティ: レア", "深海の探求", base,
        "--------", *props, "--------", f"アイテムレベル: {level}",
        "--------", "{ 暗黙モッド }", "海図作成すると航海モッドが公開される",
        "--------", "海図の形状: 交差", "--------",
        "{ プレフィックスモッド「電撃の」 (ティア: 1) — ダメージ, 物理, 元素, 雷 }",
        "モンスターは物理ダメージの29(21-35)%を追加雷ダメージとして与える",
        "--------", "ソブリン号の船上でヴァレリーにこのアイテムを持っていき、このエリアの海図を作成する",
    ))


@pytest.mark.parametrize("base,area,level,quantity,rarity,pack,sulphur", CHART_CASES)
def test_chart_copy_parses_properties_and_search_filters(base, area, level, quantity, rarity, pack, sulphur):
    item = parse_item_text(chart_text(base, area, level, quantity, rarity, pack, sulphur))
    assert item.category == "chart"
    assert item.base_type == base
    assert item.properties["マップエリア"] == area
    rows = {row.stat_id: row for row in resolve_trade_stat_filters(item)}
    assert rows["property.area_level"].min_value == level
    for stat_id, expected in (
        ("property.map_quantity", quantity), ("property.map_rarity", rarity),
        ("property.map_pack_size", pack), ("property.chart_sulphur", sulphur),
    ):
        assert (rows.get(stat_id).min_value if stat_id in rows else None) == expected
    assert all(
        modifier.text != "海図作成すると航海モッドが公開される"
        for modifier in item.modifiers
    )
    assert trade.unresolved_modifier_warnings(item, tuple(rows.values())) == ()


def test_unidentified_chart_has_only_area_level_property_filter():
    text = chart_text("砂の海底の海図", "深海平原", 83).replace("深海の探求\n", "").replace(
        "--------\n{ プレフィックスモッド", "--------\n未鑑定\n--------\n{ プレフィックスモッド",
    )
    item = parse_item_text(text)
    assert "unidentified" in item.flags
    rows = {row.stat_id for row in resolve_trade_stat_filters(item)}
    assert "property.area_level" in rows
    assert not rows & {"property.map_quantity", "property.map_rarity", "property.map_pack_size", "property.chart_sulphur"}


def test_chart_exact_and_same_area_queries_use_official_trade_shape():
    item = parse_item_text(chart_text("サンゴの森の海図", "海底の木立", 82, 64, 20, None, 60))
    rows = resolve_trade_stat_filters(item)
    exact = build_search_query(item, "Coral Forest Chart", rows, exact_base_type=True)["query"]
    assert exact["type"] == "Coral Forest Chart"
    relaxed = build_search_query(item, "Coral Forest Chart", rows, exact_base_type=False)["query"]
    assert relaxed["type"] == {"option": "UnderseaGroves", "discriminator": "chart"}
    chart_filters = relaxed["filters"]["map_filters"]["filters"]
    assert chart_filters["area_level"] == {"min": 82.0}
    assert chart_filters["chart_sulphur"] == {"min": 60.0}
    all_charts = build_search_query(
        item, "Coral Forest Chart", rows,
        exact_base_type=False, chart_area_exact=False,
    )["query"]
    assert "type" not in all_charts
    assert all_charts["filters"]["type_filters"]["filters"]["category"] == {
        "option": "chart",
    }


def test_special_chart_uses_bulk_same_area_query_without_copy_properties():
    item = parse_item_text(chart_text(
        "錨海域の海図", "錨海域", 83, 64, 20, 18, 60,
    ))
    assert is_special_chart_area(item)
    assert available_trade_presets(item) == (PRESET_FINISHED, PRESET_BULK)
    query = build_search_query(
        item, "Anchorfield Chart", resolve_trade_stat_filters(item),
        preset=PRESET_BULK, exact_base_type=False,
    )["query"]
    assert query["type"] == {"option": "Anchorfield", "discriminator": "chart"}
    assert query["filters"]["map_filters"]["filters"] == {
        "area_level": {"min": 83.0},
    }


def test_regular_chart_is_not_special():
    item = parse_item_text(chart_text(
        "サンゴの森の海図", "海底の木立", 82, 64, 20, None, 60,
    ))
    assert not is_special_chart_area(item)


@pytest.mark.parametrize("exact_base,area_exact,expected_scope", (
    (True, True, "base"),
    (False, True, "area"),
    (False, False, "all"),
))
@pytest.mark.parametrize("preset,uses_numbers", (
    (PRESET_FINISHED, True),
    (PRESET_BULK, False),
))
def test_chart_scope_and_numeric_conditions_are_independent(
    exact_base, area_exact, expected_scope, preset, uses_numbers,
):
    item = parse_item_text(chart_text(
        "サンゴの森の海図", "海底の木立", 82, 64, 20, 18, 60,
    ))
    rows = resolve_trade_stat_filters(item, preset)
    query = build_search_query(
        item, "Coral Forest Chart", rows, preset=preset,
        exact_base_type=exact_base, chart_area_exact=area_exact,
    )["query"]
    if expected_scope == "base":
        assert query["type"] == "Coral Forest Chart"
    elif expected_scope == "area":
        assert query["type"] == {"option": "UnderseaGroves", "discriminator": "chart"}
    else:
        assert "type" not in query
        assert query["filters"]["type_filters"]["filters"]["category"] == {
            "option": "chart",
        }
    chart_filters = query["filters"]["map_filters"]["filters"]
    assert chart_filters["area_level"] == {"min": 82.0}
    assert ("chart_sulphur" in chart_filters) is uses_numbers


def test_chart_scope_and_numeric_presets_have_independent_defaults(qapp):
    window = PoetoreWindow()
    try:
        special = parse_item_text(chart_text(
            "錨海域の海図", "錨海域", 83, 64, 20, 18, 60,
        ))
        window._configure_trade_presets(special)
        window._update_item_header(special)
        assert not window.base_scope_toggle.isHidden()
        assert window.base_scope_toggle.currentData() is False
        assert not window.chart_area_chip.isHidden()
        assert window.chart_area_chip.isChecked()
        assert window.chart_area_chip.text() == "錨海域"
        assert window.trade_preset_combo.currentData() == PRESET_BULK
        assert window.trade_preset_combo.currentText() == "数値を問わない"

        regular = parse_item_text(chart_text(
            "サンゴの森の海図", "海底の木立", 82, 64, 20, None, 60,
        ))
        window._configure_trade_presets(regular)
        window._update_item_header(regular)
        assert window.base_scope_toggle.currentData() is False
        assert window.chart_area_chip.isChecked()
        assert window.trade_preset_combo.currentData() == PRESET_FINISHED
        assert window.trade_preset_combo.currentText() == "数値で絞る"
    finally:
        window.close()


def test_chart_area_chip_click_switches_from_area_to_all_charts(qapp):
    window = PoetoreWindow()
    try:
        item = parse_item_text(chart_text(
            "サンゴの森の海図", "海底の木立", 83, 90, 50, None, 45,
        ))
        window._parsed_item = item
        window._trade_base_type = "Coral Forest Chart"
        window._update_item_header(item)
        window.show()
        qapp.processEvents()

        assert window.chart_area_chip.isChecked()
        assert window._searches_exact_chart_area(item)
        assert window.chart_area_chip.objectName() == "secondaryActionButton"

        QTest.mouseClick(window.chart_area_chip, Qt.LeftButton)
        qapp.processEvents()

        assert not window.chart_area_chip.isChecked()
        assert not window._searches_exact_chart_area(item)
        assert window.price_status.text() == "すべての海図を検索します。"
        query = build_search_query(
            item, window._trade_base_type, resolve_trade_stat_filters(item),
            exact_base_type=window._searches_exact_base_type(item),
            chart_area_exact=window._searches_exact_chart_area(item),
        )["query"]
        assert "type" not in query
        assert query["filters"]["type_filters"]["filters"]["category"] == {
            "option": "chart",
        }
    finally:
        window.close()


def test_chart_preset_switch_regenerates_bulk_and_property_filters(qapp, monkeypatch):
    monkeypatch.setattr(trade, "_stat_entries_cache", ())
    monkeypatch.setattr(trade, "_stat_entry_indexes_cache", None)
    item = parse_item_text(chart_text(
        "錨海域の海図", "錨海域", 83, 64, 20, 18, 60,
    ))
    window = PoetoreWindow()
    try:
        window._parsed_item = item
        window._trade_base_type = "Anchorfield Chart"
        window._configure_trade_presets(item)
        window._update_item_header(item)
        assert window.trade_preset_combo.currentData() == PRESET_BULK
        assert window.mod_filter_tree.topLevelItemCount() == 0

        window.trade_preset_combo.setCurrentIndex(0)
        filters = window._selected_stat_filters()
        assert {row.stat_id for row in filters} >= {
            "property.map_quantity", "property.map_rarity",
            "property.map_pack_size", "property.chart_sulphur",
        }
        assert window.price_status.text() == "海図の数量・レアリティなどを検索条件に含めます。"

        window.trade_preset_combo.setCurrentIndex(1)
        assert window.mod_filter_tree.topLevelItemCount() == 0
        assert window.price_status.text() == "海図の数量・レアリティなどを指定せずに検索します。"

        window.base_scope_toggle.setCurrentIndex(0)
        assert window._searches_exact_base_type(item)
        assert window.chart_area_chip.isHidden()
        window.base_scope_toggle.setCurrentIndex(1)
        assert window._searches_exact_chart_area(item)
        window.chart_area_chip.setChecked(False)
        assert not window._searches_exact_chart_area(item)
        assert window.price_status.text() == "すべての海図を検索します。"
    finally:
        window.close()


def test_chart_bulk_preset_hides_irrelevant_unresolved_mod_warning(qapp):
    text = chart_text(
        "サンゴの森の海図", "海底の木立", 83, 90, 50, None, 45,
    ).replace(
        "モンスターは物理ダメージの29(21-35)%を追加雷ダメージとして与える",
        "このエリアで見つかる死人の硫黄が30%増加する",
    )
    item = parse_item_text(text)
    assert trade.unresolved_modifier_warnings(item)

    window = PoetoreWindow()
    try:
        window._parsed_item = item
        window._configure_trade_presets(item)
        window._update_mod_warning(item)
        assert window.trade_preset_combo.currentData() == PRESET_FINISHED
        assert not window.mod_warning.isHidden()

        window.trade_preset_combo.setCurrentIndex(1)

        assert window.trade_preset_combo.currentData() == PRESET_BULK
        assert window.mod_warning.isHidden()
        assert window.mod_warning.text() == ""

    finally:
        window.close()
