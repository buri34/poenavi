from unittest.mock import patch

from src.poetore.poe2 import metadata


def _signature(rows):
    return tuple(
        (str(entry.get("id", "")), tuple(values))
        for entry, values in rows
    )


def test_shape_index_matches_legacy_full_scan_for_representative_templates():
    matchers = metadata.stat_matchers()
    templates = []
    seen = set()
    for entry, _pattern in matchers[::97]:
        for template in (entry.get("text") or {}).values():
            candidate = str(template).replace("#", "17")
            if candidate not in seen:
                seen.add(candidate)
                templates.append(candidate)

    assert len(templates) >= 100
    metadata.resolve_stat_line_candidates.cache_clear()
    indexed = {
        text: _signature(metadata.resolve_stat_line_candidates(text))
        for text in templates
    }

    metadata.resolve_stat_line_candidates.cache_clear()
    with patch.object(metadata, "stat_matcher_index", return_value={}):
        legacy = {
            text: _signature(metadata.resolve_stat_line_candidates(text))
            for text in templates
        }
    metadata.resolve_stat_line_candidates.cache_clear()

    assert indexed == legacy


def test_index_miss_falls_back_to_legacy_scan():
    text = "+37 to maximum Life"
    metadata.resolve_stat_line_candidates.cache_clear()
    expected = _signature(metadata.resolve_stat_line_candidates(text))
    metadata.resolve_stat_line_candidates.cache_clear()

    with patch.object(
        metadata,
        "stat_matcher_index",
        return_value={
            metadata._stat_shape(text): (metadata.stat_matchers()[0],),
        },
    ):
        actual = _signature(metadata.resolve_stat_line_candidates(text))
    metadata.resolve_stat_line_candidates.cache_clear()

    assert actual == expected


def test_index_preserves_preferred_type_ordering():
    text = "Minions deal 17% increased Damage"
    metadata.resolve_stat_line_candidates.cache_clear()
    indexed = _signature(
        metadata.resolve_stat_line_candidates(text, preferred_type="explicit"),
    )
    metadata.resolve_stat_line_candidates.cache_clear()

    with patch.object(metadata, "stat_matcher_index", return_value={}):
        legacy = _signature(
            metadata.resolve_stat_line_candidates(text, preferred_type="explicit"),
        )
    metadata.resolve_stat_line_candidates.cache_clear()

    assert indexed
    assert indexed == legacy
