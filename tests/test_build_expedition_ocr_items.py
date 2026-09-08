from scripts.build_expedition_ocr_items import build_aliases


def test_build_aliases_pairs_supported_groups_and_drops_ambiguous_names():
    japanese = {"result": [
        {"id": "currency", "entries": [
            {"type": "高貴なオーブ"},
            {"type": "共通名"},
            {"type": "[DNT] 非表示"},
        ]},
        {"id": "gem", "entries": [{"type": "共通名"}]},
        {"id": "weapon", "entries": [{"type": "無視"}]},
    ]}
    english = {"result": [
        {"id": "currency", "entries": [
            {"type": "Exalted Orb"},
            {"type": "First"},
            {"type": "[DNT] Hidden"},
        ]},
        {"id": "gem", "entries": [{"type": "Second"}]},
        {"id": "weapon", "entries": [{"type": "Ignored"}]},
    ]}

    assert build_aliases(japanese, english) == [
        {"ja": "高貴なオーブ", "en": "Exalted Orb"},
    ]
