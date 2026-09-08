import json
from unittest.mock import patch

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage

from src.poetore.expedition_ocr_probe import RowBand
from src.poetore.expedition_rewards import (
    RewardIdentity,
    SafeRewardNameResolver,
    expedition_capture_rect,
    format_exalted_unit_price,
    load_reward_alias_bundle,
    load_reward_aliases,
    price_label_x,
    reward_cards_still_visible,
    stable_reward_identities,
)


def test_load_reward_aliases_and_format_prices(tmp_path):
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps({"items": [{"ja": "高貴", "en": "Exalted"}]}))
    assert load_reward_aliases(path) == {"高貴": "Exalted"}
    assert format_exalted_unit_price(0.004) == "<0.01 高貴/個"
    assert format_exalted_unit_price(0.85) == "0.85 高貴/個"
    assert format_exalted_unit_price(5.25) == "5.2 高貴/個"
    assert format_exalted_unit_price(12.4) == "12 高貴/個"


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
        assert resolver.resolve("1x 高貴") == ("高貴", "Exalted")
        assert resolver.resolve("1x 高貴") == ("高貴", "Exalted")
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
