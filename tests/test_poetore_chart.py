import pytest

from src.poetore.parser import parse_item_text
from src.poetore.trade import build_search_query, resolve_trade_stat_filters


CHART_CASES = (
    ("砂の海底の海図", "深海平原", 83, 32, 76, 18, None),
    ("サンゴの森の海図", "海底の木立", 82, 64, 20, None, 60),
    ("サンゴ礁の海図", "海底の尾根", 82, 32, 40, 16, None),
)


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
