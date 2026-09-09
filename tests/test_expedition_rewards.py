import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage

from src.poetore.expedition_ocr_probe import RowBand
from src.poetore.expedition_rewards import (
    EXPEDITION_DIAGNOSTIC_FLAG,
    EXPEDITION_PRICE_FONT_SIZE,
    ExpeditionRewardController,
    RewardIdentity,
    RewardPriceRow,
    SafeRewardNameResolver,
    expedition_capture_rect,
    expedition_diagnostics_enabled,
    expedition_exalted_icon_path,
    format_exalted_unit_price,
    format_expedition_diagnostic_report,
    highlight_highest_price_rows,
    load_reward_alias_bundle,
    load_reward_aliases,
    price_label_x,
    reward_cards_still_visible,
    reward_price_text_color,
    stable_reward_identities,
)


def test_expedition_diagnostics_can_be_enabled_by_environment_or_marker(tmp_path):
    with patch.dict("os.environ", {"POENAVI_EXPEDITION_DIAGNOSTICS": "1"}):
        assert expedition_diagnostics_enabled(tmp_path)

    with patch.dict("os.environ", {}, clear=True):
        assert not expedition_diagnostics_enabled(tmp_path)
        (tmp_path / EXPEDITION_DIAGNOSTIC_FLAG).write_text("enabled")
        assert expedition_diagnostics_enabled(tmp_path)


def test_expedition_diagnostic_report_is_screenshot_ready():
    report = format_expedition_diagnostic_report([
        "✅ 1. ゲーム画面検出: 1920x1080",
        "❌ 4. Windows日本語OCR起動: 利用できません",
    ])

    assert "ゲーム画面検出" in report
    assert "Windows日本語OCR起動" in report
    assert "スクリーンショットして送ってください" in report


def test_controller_emits_diagnostic_report_on_failure():
    overlay = Mock()
    ocr = Mock()
    with patch(
        "src.poetore.expedition_rewards.QCoreApplication.instance",
        return_value=None,
    ), patch(
        "src.poetore.expedition_rewards.ExpeditionPriceOverlay",
        return_value=overlay,
    ), patch(
        "src.poetore.expedition_rewards.WindowsOcrServer",
        return_value=ocr,
    ), patch(
        "src.poetore.expedition_rewards.path_of_exile_client_rect",
        return_value=None,
    ):
        controller = ExpeditionRewardController(
            lambda: "Test League", diagnostics_enabled=True,
        )
        reports = []
        controller.diagnostic.connect(reports.append)
        assert not controller.request_scan()

    assert len(reports) == 1
    assert "❌ 1. ゲーム画面検出" in reports[0]
    assert "Path of Exileのゲーム画面が見つかりませんでした" in reports[0]


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
    assert format_exalted_unit_price(0.004) == "<0.01 高貴/個"
    assert format_exalted_unit_price(0.85) == "0.85 高貴/個"
    assert format_exalted_unit_price(5.25) == "5.2 高貴/個"
    assert format_exalted_unit_price(12.4) == "12 高貴/個"
    assert EXPEDITION_PRICE_FONT_SIZE == 14


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


def test_packaged_reward_aliases_are_limited_to_expedition_reward_pool():
    aliases = load_reward_aliases()

    assert len(aliases) == 281
    assert aliases["旋風の合金"] == "Cyclonic Alloy"
    assert aliases["サカワルの浸食のルーン"] == "Saqawal's Rune of Erosion"
    assert aliases["スルードの力"] == "Thrud's Might"
    assert aliases["カトラの陰鬱"] == "Katla's Gloom"
    assert "グリムピラー" not in aliases


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


@pytest.mark.parametrize(
    ("raw_text", "japanese_name", "english_name"),
    (
        (
            "1 , サ カ ワ ル の 浸 良 の ル ー ン 一",
            "サカワルの浸食のルーン",
            "Saqawal's Rune of Erosion",
        ),
        ("lx ス ル ー ド の カ", "スルードの力", "Thrud's Might"),
    ),
)
def test_safe_reward_name_resolver_marks_corrected_exact_ocr_reads(
    raw_text, japanese_name, english_name,
):
    resolver = SafeRewardNameResolver({japanese_name: english_name}, "dictionary-v1")

    assert resolver.resolve(raw_text) == (japanese_name, english_name, True)


def test_safe_reward_name_resolver_requires_matching_reward_level():
    resolver = SafeRewardNameResolver({
        "ソーマタージ・フラックス（レベル18）": "Thaumaturge's Flux (Level 18)",
        "ソーマタージ・フラックス（レベル19）": "Thaumaturge's Flux (Level 19)",
    }, "dictionary-v1")

    assert resolver.resolve("1x ソーマタージ・フラックス（レベル18）") == (
        "ソーマタージ・フラックス（レベル18）",
        "Thaumaturge's Flux (Level 18)",
        True,
    )
    assert resolver.resolve("1x ソーマタージ・フラックス（レベル17）") is None
    assert resolver.resolve("1x ソーマタージ・フラックス") is None


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


def test_stable_reward_identities_prefers_one_exact_read_over_fuzzy_conflict():
    exact = RewardIdentity(10, 30, "カトラの陰鬱", "Katla's Gloom", exact_match=True)
    fuzzy = RewardIdentity(11, 31, "別候補", "Other Candidate")
    unresolved = RewardIdentity(12, 32, "", "")

    assert stable_reward_identities([[exact], [fuzzy], [unresolved]]) == [exact]


def test_stable_reward_identities_rejects_three_different_fuzzy_candidates():
    first = RewardIdentity(10, 30, "迅速の合金", "Swift Alloy")
    second = RewardIdentity(11, 31, "旋風の合金", "Cyclonic Alloy")
    third = RewardIdentity(12, 32, "拡張の合金", "Expansive Alloy")

    assert stable_reward_identities([[first], [second], [third]]) == []


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
