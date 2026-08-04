import json
from pathlib import Path

from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import QPoint, QRect, QSize

from src.poetore.map_check import (
    decision_for, default_map_check_config, is_map_check_item,
    load_map_mod_catalog, next_color_decision, normalized_map_check_config,
    set_decision,
)
from src.poetore.models import ParsedItem
from src.poetore.parser import parse_item_text
from src.poetore.window_position import (
    PlacementContext, position_for_context_at_cursor_y,
)
from unittest.mock import patch

from src.ui.map_check import MapCheckWindow, MapModManagerDialog
from scripts.build_poetore_map_mods import build_catalog


def item(category="map", rarity="レア"):
    return ParsedItem("マップ", rarity, "テスト", "テストマップ", category)


def test_map_check_position_keeps_side_and_centers_at_cursor_y_with_clamping():
    target = QRect(100, 50, 1920, 1080)
    size = QSize(560, 360)

    middle = position_for_context_at_cursor_y(
        PlacementContext(target, QPoint(1700, 700)), size,
    )
    top = position_for_context_at_cursor_y(
        PlacementContext(target, QPoint(1700, 60)), size,
    )
    bottom = position_for_context_at_cursor_y(
        PlacementContext(target, QPoint(1700, 1120)), size,
    )

    assert middle == QPoint(794, 520)
    assert top == QPoint(794, 66)
    assert bottom == QPoint(794, 754)


def test_catalog_matches_locked_awakened_area_mod_population():
    catalog = load_map_mod_catalog()
    assert len(catalog) == 229
    assert sum(row.scope == "normal" for row in catalog) == 169
    assert sum(row.scope == "heist_exclusive" for row in catalog) == 27
    assert sum(row.scope == "ubermap_exclusive" for row in catalog) == 33
    assert all(row.stat_ids and row.japanese for row in catalog)
    assert all("stat_1953432004" not in row.stat_ids for row in catalog)


def test_catalog_is_reproducible_from_locked_awakened_and_poetore_metadata():
    generated = build_catalog(
        Path("vendor-sources/awakened-poe-trade-31b3e0e8.tar.gz"),
        Path("data/poetore/mod_metadata.json"),
    )
    stored = json.loads(
        Path("data/poetore/map_mods.json").read_text(encoding="utf-8")
    )
    assert generated == stored


def test_awakened_defaults_and_three_numeric_profiles_are_preserved():
    config = default_map_check_config()
    assert config["profile"] == 1
    assert len(config["decisions"]) == 4
    assert sorted(config["decisions"].values()) == ["d--", "d--", "g--", "w--"]
    key = next(iter(config["decisions"]))
    set_decision(config, key, "g", profile=2)
    assert decision_for(config, key, profile=2) == "g"
    assert decision_for(config, key, profile=1) != "g" or config["decisions"][key][0] == "g"


def test_normalization_rejects_invalid_profile_and_decision():
    config = normalized_map_check_config({
        "profile": 9, "show_new_stats": True,
        "decisions": {"bad": "danger", "ok": "dwg"},
    })
    assert config["profile"] == 1
    assert config["show_new_stats"] is True
    assert "bad" not in config["decisions"]
    assert config["decisions"]["ok"] == "dwg"


def test_map_like_scope_matches_awakened_and_excludes_unique_map():
    assert is_map_check_item(item())
    assert is_map_check_item(item("invitation"))
    assert is_map_check_item(item("heist_contract"))
    assert is_map_check_item(item("heist_blueprint"))
    assert is_map_check_item(item("expedition_logbook"))
    assert not is_map_check_item(item("map", "ユニーク"))
    assert not is_map_check_item(item("armour"))


def test_color_cycle_matches_awakened_without_seen_state_in_color_button():
    assert [next_color_decision(value) for value in ("-", "d", "w", "g", "s")] == [
        "d", "w", "g", "-", "d",
    ]


def test_real_japanese_map_mods_resolve_to_area_catalog():
    parsed = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Glyph Stone
Map (Tier 16)
--------
アイテムレベル: 83
--------
{ プレフィックスモッド「装甲付き」 (ティア: 1) — 物理 }
モンスターの物理ダメージ軽減率 +40%
{ プレフィックスモッド「電撃の」 (ティア: 1) — ダメージ, 物理, 元素, 雷 }
モンスターは物理ダメージの97(90-110)%を追加雷ダメージとして与える
{ サフィックスモッド 「干魃の」 (ティア: 1) }
全てのプレイヤーの獲得フラスコチャージが50%減少する
""")
    catalog_ids = {
        stat_id for row in load_map_mod_catalog() for stat_id in row.stat_ids
    }
    assert len(parsed.modifiers) == 3
    assert all(modifier.stat_id in catalog_ids for modifier in parsed.modifiers)


def test_japanese_map_copy_aliases_resolve_boss_damage_and_implicit_hinder_chance():
    parsed = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Alias Test
Map (Tier 16)
--------
アイテムレベル: 83
--------
{ プレフィックスモッド (ティア: 1) }
ユニークボスのダメージが25%増加する
{ サフィックスモッド (ティア: 1) }
モンスターはスペルによるヒット時に阻害を付与する
""")
    assert [(modifier.stat_id, modifier.values) for modifier in parsed.modifiers] == [
        ("explicit.stat_124877078", (25.0,)),
        ("explicit.stat_962720646", (100.0,)),
    ]


def test_additional_real_japanese_map_copy_aliases_resolve_to_area_mods():
    parsed = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Alias Test 2
Map (Tier 16)
--------
アイテムレベル: 83
--------
{ プレフィックスモッド (ティア: 1) }
マジックモンスターの数が23(20-30)%増加する
{ サフィックスモッド (ティア: 1) }
モンスターはヒット時にパワーチャージ、フレンジーチャージおよびエンデュランスチャージのスタックを盗む
{ サフィックスモッド (ティア: 1) }
モンスターはアタックによるヒット時に重傷を付与する
{ サフィックスモッド (ティア: 1) }
全てのプレイヤーの命中力が25%低下する
{ サフィックスモッド (ティア: 1) }
モンスターはヒット時に盲目を付与する
{ サフィックスモッド (ティア: 1) }
モンスターはヒット時にパワーチャージを1個獲得する
{ サフィックスモッド (ティア: 1) }
モンスターはヒット時にフレンジーチャージを1個獲得する
""")
    assert [(modifier.stat_id, modifier.values) for modifier in parsed.modifiers] == [
        ("explicit.stat_1821565133", (23.0, 20.0, -30.0)),
        ("explicit.stat_3222482040", (100.0,)),
        ("explicit.stat_4164174520", (100.0,)),
        ("explicit.stat_3667574329", (25.0,)),
        ("explicit.stat_1629869774", (100.0,)),
        ("explicit.stat_406353061", (100.0,)),
        ("explicit.stat_1742567045", (100.0,)),
    ]
    assert parsed.modifiers[3].inverted is True


def test_reported_japanese_map_copy_aliases_resolve_to_area_mods():
    parsed = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Reported Alias Test
Map (Tier 16)
--------
アイテムレベル: 83
--------
{ プレフィックスモッド (ティア: 1) }
レアモンスターの数が25%増加する
{ プレフィックスモッド (ティア: 1) }
ユニークボスのライフが40%増加する
{ サフィックスモッド (ティア: 1) }
全てのプレイヤーのクールダウン解消レートが25%低下する
""")
    catalog_ids = {
        stat_id for row in load_map_mod_catalog() for stat_id in row.stat_ids
    }
    assert [(modifier.stat_id, modifier.values) for modifier in parsed.modifiers] == [
        ("explicit.stat_3126771445", (25.0,)),
        ("explicit.stat_1959158336", (40.0,)),
        ("explicit.stat_941368244", (25.0,)),
    ]
    assert all(modifier.stat_id in catalog_ids for modifier in parsed.modifiers)
    assert parsed.modifiers[2].inverted is True


def test_seen_column_is_hidden_when_new_mod_notifications_are_disabled():
    QApplication.instance() or QApplication([])
    parsed = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
UI Test
Map (Tier 16)
--------
アイテムレベル: 83
--------
{ プレフィックスモッド (ティア: 1) }
レアモンスターの数が25%増加する
""")
    window = MapCheckWindow(default_map_check_config())
    window._render(parsed)
    assert not [
        button for button in window.body.findChildren(QPushButton)
        if button.property("map_seen_key")
    ]
    window.close()


def test_seen_column_uses_clear_labels_and_preserves_colored_decisions():
    QApplication.instance() or QApplication([])
    parsed = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
UI Test
Map (Tier 16)
--------
アイテムレベル: 83
--------
{ プレフィックスモッド (ティア: 1) }
レアモンスターの数が25%増加する
""")
    config = default_map_check_config()
    config["show_new_stats"] = True
    window = MapCheckWindow(config)
    window._render(parsed)
    seen = next(
        button for button in window.body.findChildren(QPushButton)
        if button.property("map_seen_key")
    )
    key = seen.property("map_seen_key")
    assert seen.text() == "未確認"
    assert "確認済み" in seen.toolTip()

    seen.click()
    assert seen.text() == "確認済"
    set_decision(window.config, key, "d")
    window._refresh_seen_buttons(key)
    assert seen.text() == "設定済"
    assert not seen.isEnabled()
    assert decision_for(window.config, key) == "d"
    window.close()


def test_map_check_grows_to_show_all_mod_rows_and_caps_at_screen_height():
    QApplication.instance() or QApplication([])
    parsed = parse_item_text("""アイテムクラス: マップ
レアリティ: レア
Tall UI Test
Map (Tier 16)
--------
アイテムレベル: 83
--------
{ プレフィックスモッド (ティア: 1) }
マジックモンスターの数が23(20-30)%増加する
{ サフィックスモッド (ティア: 1) }
モンスターはヒット時にパワーチャージ、フレンジーチャージおよびエンデュランスチャージのスタックを盗む
{ サフィックスモッド (ティア: 1) }
モンスターはアタックによるヒット時に重傷を付与する
{ サフィックスモッド (ティア: 1) }
全てのプレイヤーの命中力が25%低下する
{ サフィックスモッド (ティア: 1) }
モンスターはヒット時に盲目を付与する
{ サフィックスモッド (ティア: 1) }
モンスターはヒット時にパワーチャージを1個獲得する
{ サフィックスモッド (ティア: 1) }
モンスターはヒット時にフレンジーチャージを1個獲得する
{ サフィックスモッド (ティア: 1) }
モンスターはヒット時にエンデュランスチャージを1個獲得する
{ サフィックスモッド (ティア: 1) }
全てのプレイヤーの獲得フラスコチャージが50%減少する
""")
    window = MapCheckWindow(default_map_check_config())
    window._render(parsed)

    large_screen = PlacementContext(QRect(0, 0, 1920, 1080), QPoint(800, 500))
    window._resize_to_content(large_screen)
    expanded_height = window.height()
    assert expanded_height > window.DEFAULT_HEIGHT
    assert window.scroll.verticalScrollBar().maximum() == 0

    small_screen = PlacementContext(QRect(0, 0, 800, 300), QPoint(400, 150))
    window._resize_to_content(small_screen)
    window.show()
    QApplication.processEvents()
    assert window.height() == 300 - window.SCREEN_EDGE_MARGIN * 2
    assert window.scroll.verticalScrollBar().maximum() > 0
    window.close()


def test_manager_uses_numeric_profiles_and_lists_current_plus_outdated_defaults():
    QApplication.instance() or QApplication([])
    dialog = MapModManagerDialog(default_map_check_config())
    assert [button.text() for button in dialog.profile_buttons] == ["1", "2", "3"]
    assert dialog.table.rowCount() == 231
    assert "全229件" in dialog.count_label.text()
    dialog.close()


def test_manager_orders_normal_then_uber_map_then_heist_mods():
    QApplication.instance() or QApplication([])
    dialog = MapModManagerDialog(default_map_check_config())
    scopes = [entry.scope for entry, _tag in dialog._rows()]
    assert scopes == sorted(
        scopes,
        key={
            "normal": 0,
            "ubermap_exclusive": 1,
            "heist_exclusive": 2,
            "outdated": 3,
        }.get,
    )
    assert scopes.index("ubermap_exclusive") > scopes.index("normal")
    assert scopes.index("heist_exclusive") > scopes.index("ubermap_exclusive")
    dialog.close()


def test_non_map_clipboard_is_rejected_without_trade_search():
    app = QApplication.instance() or QApplication([])
    app.clipboard().setText("""アイテムクラス: 指輪
レアリティ: ノーマル
鉄の指輪
--------
アイテムレベル: 1
""")
    window = MapCheckWindow(default_map_check_config())
    with patch("src.ui.map_check.QMessageBox.information") as information:
        window._consume_clipboard()
    information.assert_called_once()
    assert "Map系アイテムではありません" in information.call_args.args[2]
    assert not window.isVisible()
    window.close()
def test_map_check_uses_shared_result_font_size():
    QApplication.instance() or QApplication([])
    config = default_map_check_config()
    config["_font_size"] = "large"
    window = MapCheckWindow(config)
    assert "font-size:16px" in window.styleSheet()
