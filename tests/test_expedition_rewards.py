import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage

from src.poetore.expedition_ocr_probe import RowBand
from src.poetore.expedition_rewards import (
    ExpeditionRewardController,
    RewardIdentity,
    RewardPriceRow,
    SafeRewardNameResolver,
    expedition_capture_rect,
    expedition_exalted_icon_path,
    format_exalted_unit_price,
    highlight_highest_price_rows,
    load_reward_alias_bundle,
    load_reward_aliases,
    price_label_x,
    reward_cards_still_visible,
    reward_price_text_color,
    stable_reward_identities,
)


def test_controller_closes_ocr_helper_when_application_quits():
    app = SimpleNamespace(aboutToQuit=Mock())
    overlay = Mock()
    ocr = Mock()
    with patch(
        "src.poetore.expedition_rewards.QCoreApplication.instance",
        return_value=app,
    ), patch(
        "src.poetore.expedition_rewards.ExpeditionPriceOverlay",
        return_value=overlay,
    ), patch(
        "src.poetore.expedition_rewards.WindowsOcrServer",
        return_value=ocr,
    ):
        controller = ExpeditionRewardController(lambda: "Test League")

    app.aboutToQuit.connect.assert_called_once_with(controller.close)
    app.aboutToQuit.connect.call_args.args[0]()
    overlay.hide.assert_called_once_with()
    ocr.close.assert_called_once_with()


def test_load_reward_aliases_and_format_prices(tmp_path):
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps({"items": [{"ja": "高貴", "en": "Exalted"}]}))
    assert load_reward_aliases(path) == {"高貴": "Exalted"}
    assert format_exalted_unit_price(0.004) == "<0.01"
    assert format_exalted_unit_price(0.85) == "0.85"
    assert format_exalted_unit_price(5.25) == "5.2"
    assert format_exalted_unit_price(12.4) == "12"


def test_expedition_price_colors_only_highest_row_green():
    rows = highlight_highest_price_rows([
        RewardPriceRow(10, 20, "2.5", 2.5),
        RewardPriceRow(30, 40, "8.2", 8.2),
        RewardPriceRow(50, 60, "8.2", 8.2),
    ])

    assert [row.highlighted for row in rows] == [False, True, True]
    assert reward_price_text_color(rows[0]).name() == "#ffffff"
    assert reward_price_text_color(rows[1]).name() == "#b0ff7b"


def test_expedition_exalted_icon_uses_poe2_asset():
    path = expedition_exalted_icon_path()

    assert path.name == "ExaltedOrb2.png"
    assert path.is_file()


def test_reward_alias_bundle_versions_exact_dictionary_bytes(tmp_path):
    path = tmp_path / "aliases.json"
    path.write_text('{"items":[{"ja":"高貴","en":"Exalted"}]}', encoding="utf-8")

    aliases, first_version = load_reward_alias_bundle(path)
    path.write_text('{"items":[{"ja":"混沌","en":"Chaos"}]}', encoding="utf-8")
    _, second_version = load_reward_alias_bundle(path)

    assert aliases == {"高貴": "Exalted"}
    assert first_version != second_version


def test_safe_reward_name_resolver_caches_only_trusted_matches():
    resolver = SafeRewardNameResolver({"高貴": "Exalted"}, "dictionary-v1")
    with patch(
        "src.poetore.expedition_rewards.match_item_name",
        side_effect=[
            ("高貴", 1.0, 1.0, True),
            ("", 0.5, 0.0, False),
            ("", 0.5, 0.0, False),
        ],
    ) as matcher:
        assert resolver.resolve("1x 高貴") == ("高貴", "Exalted", True)
        assert resolver.resolve("1x 高貴") == ("高貴", "Exalted", True)
        assert resolver.resolve("不明") is None
        assert resolver.resolve("不明") is None

    assert matcher.call_count == 3


def test_expedition_capture_rect_uses_only_left_panel_area():
    client = QRect(100, 200, 1920, 1080)

    capture = expedition_capture_rect(client)

    assert capture == QRect(100, 200, 756, 1080)


def test_stable_reward_identities_requires_two_matching_frames():
    a = RewardIdentity(10, 30, "高貴", "Exalted")
    shifted = RewardIdentity(11, 31, "高貴", "Exalted")
    wrong = RewardIdentity(10, 30, "混沌", "Chaos")
    result = stable_reward_identities([[a], [shifted], [wrong]])
    assert result == [shifted]


def test_stable_reward_identities_accepts_one_exact_read_when_others_are_unresolved():
    exact = RewardIdentity(10, 30, "旋風の合金", "Cyclonic Alloy", exact_match=True)
    unresolved = RewardIdentity(11, 31, "", "")

    assert stable_reward_identities([[exact], [unresolved], [unresolved]]) == [exact]


def test_stable_reward_identities_rejects_one_fuzzy_read_when_others_are_unresolved():
    fuzzy = RewardIdentity(10, 30, "旋風の合金", "Cyclonic Alloy")
    unresolved = RewardIdentity(11, 31, "", "")

    assert stable_reward_identities([[fuzzy], [unresolved], [unresolved]]) == []


def test_stable_reward_identities_rejects_conflicting_exact_reads():
    first = RewardIdentity(10, 30, "旋風の合金", "Cyclonic Alloy", exact_match=True)
    second = RewardIdentity(11, 31, "神秘の合金", "Mystic Alloy", exact_match=True)
    unresolved = RewardIdentity(12, 32, "", "")

    assert stable_reward_identities([[first], [second], [unresolved]]) == []


def test_price_label_is_placed_next_to_detected_panel_at_any_aspect_ratio():
    assert price_label_x(1920, 1920, 600) == 608
    assert price_label_x(3440, 3440, 600) == 608
    assert price_label_x(1920, 3840, 1200) == 608


def test_reward_card_visibility_samples_expected_bands():
    image = QImage(120, 100, QImage.Format.Format_RGB888)
    image.fill(QColor(20, 20, 20))
    for y in range(20, 40):
        for x in range(60):
            image.setPixelColor(x, y, QColor(190, 190, 190))
    assert reward_cards_still_visible(image, [RowBand(20, 40)], 60)
    assert not reward_cards_still_visible(image, [RowBand(60, 80)], 60)
