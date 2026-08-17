import json

from scripts.build_poetore_mercenary_data import build_mercenary_data


def test_builds_compact_mercenary_metadata(tmp_path):
    stats = tmp_path / "stats.ndjson"
    stats.write_text("\n".join((
        json.dumps({"ref": "Skill", "mercenary": {"supports": ["Support"]},
                    "matchers": [{"string": "Skill"}],
                    "trade": {"ids": {"pseudo": ["mercenary.skill_1"]}}}),
        json.dumps({"ref": "Support", "modFamily": ["Support"],
                    "mercenary": {"tier": 3, "canonical": "Support"},
                    "matchers": [{"string": "Support", "advanced": "Support (Tier: 3)"}],
                    "trade": {"ids": {"pseudo": ["mercenary.support_1"]}}}),
        json.dumps({"ref": "Other", "matchers": [{"string": "Other"}]}),
    )), encoding="utf-8")
    builds = tmp_path / "builds.json"
    builds.write_text('[{"name":"Build","skills":[]}]', encoding="utf-8")

    payload = build_mercenary_data(stats, builds)

    assert payload["builds"][0]["name"] == "Build"
    assert [row["ref"] for row in payload["stats"]] == ["Skill", "Support"]
    assert payload["stats"][1]["tier"] == 3
    assert payload["stats"][1]["advanced"] == "Support (Tier: 3)"
