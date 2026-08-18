from pathlib import Path

from src.utils.new_character_history import inspect_client_log_history

KNOWN_ZONES = {
    "黄昏の岸辺",
    "The Twilight Strand",
    "海岸",
    "The Coast",
    "西の森",
    "The Western Forest",
    "ライオンアイの見張り場",
}
TOWNS = {"ライオンアイの見張り場"}


def _inspect(
    tmp_path: Path,
    lines: list[str],
    anchor="西の森",
    max_bytes=128 * 1024 * 1024,
):
    log_path = tmp_path / "Client.txt"
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return inspect_client_log_history(log_path, anchor, KNOWN_ZONES, TOWNS, max_bytes)


def test_detects_twilight_then_level_two_after_last_anchor(tmp_path):
    result = _inspect(tmp_path, [
        "あなたは西の森に入場しました。",
        "あなたは黄昏の岸辺に入場しました。",
        "new (Ranger) はレベル2になりました",
    ])
    assert result.anchor_found
    assert result.new_character_start_found
    assert result.latest_non_town_zone == "黄昏の岸辺"


def test_other_zone_cancels_twilight_candidate(tmp_path):
    result = _inspect(tmp_path, [
        "あなたは西の森に入場しました。",
        "あなたは黄昏の岸辺に入場しました。",
        "あなたは海岸に入場しました。",
        "new (Ranger) はレベル2になりました",
    ])
    assert result.anchor_found
    assert not result.new_character_start_found
    assert result.latest_non_town_zone == "海岸"


def test_level_two_without_twilight_is_not_enough(tmp_path):
    result = _inspect(tmp_path, [
        "あなたは西の森に入場しました。",
        "new (Ranger) はレベル2になりました",
    ])
    assert result.anchor_found
    assert not result.new_character_start_found


def test_last_same_named_anchor_is_used(tmp_path):
    result = _inspect(tmp_path, [
        "あなたは西の森に入場しました。",
        "あなたは黄昏の岸辺に入場しました。",
        "new (Ranger) はレベル2になりました",
        "あなたは西の森に入場しました。",
    ])
    assert result.anchor_found
    assert not result.new_character_start_found


def test_english_and_set_source_lines_are_supported(tmp_path):
    result = _inspect(tmp_path, [
        "[SCENE] Set Source [The Western Forest]",
        "2026/01/01 : You have entered The Twilight Strand.",
        "new (Ranger) is now level 2",
    ], anchor="The Western Forest")
    assert result.anchor_found
    assert result.new_character_start_found
    assert result.latest_non_town_zone == "The Twilight Strand"


def test_town_is_not_returned_as_latest_non_town(tmp_path):
    result = _inspect(tmp_path, [
        "あなたは西の森に入場しました。",
        "あなたはライオンアイの見張り場に入場しました。",
    ])
    assert result.latest_non_town_zone == "西の森"


def test_missing_anchor_within_size_limit_does_not_detect(tmp_path):
    result = _inspect(tmp_path, [
        "あなたは西の森に入場しました。",
        "x" * 100,
        "あなたは黄昏の岸辺に入場しました。",
        "new (Ranger) はレベル2になりました",
    ], max_bytes=160)
    assert not result.anchor_found
    assert not result.new_character_start_found
    assert result.latest_non_town_zone == "黄昏の岸辺"


def test_no_anchor_establishes_baseline_without_historical_detection(tmp_path):
    result = _inspect(tmp_path, [
        "あなたは黄昏の岸辺に入場しました。",
        "new (Ranger) はレベル2になりました",
    ], anchor=None)
    assert not result.anchor_found
    assert not result.new_character_start_found
    assert result.latest_non_town_zone == "黄昏の岸辺"
