import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_poetore_distribution_contains_only_minimal_derived_data():
    data_dir = ROOT / "data" / "poetore"
    names = {path.name for path in data_dir.iterdir() if path.is_file()}
    expected = {"mod_metadata.json", "pseudo_relations.json", "pseudo_definitions.json"}
    if os.environ.get("POETORE_CANDIDATE_BUILD") == "1":
        expected.add(".mod_metadata.json.candidate")
    assert names == expected
    index_path = Path(os.environ.get("POETORE_METADATA_PATH", data_dir / "mod_metadata.json"))
    assert index_path.stat().st_size < 8 * 1024 * 1024
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert payload["scope"] == "PoE1 trade stat matching for equipment and gems"
    assert 8000 <= len(payload["mods"]) <= 12000
    assert 500 <= len(payload["gems"]) <= 1000
    allowed = {
        "ref", "stat_id", "kind", "japanese", "better", "inverted",
        "exact", "local", "decimal", "tiers", "options",
    }
    assert all(set(row) == allowed for row in payload["mods"])
    relations = json.loads((data_dir / "pseudo_relations.json").read_text(encoding="utf-8"))
    assert relations["source_revision"] and len(relations["source_sha256"]) == 64
    assert 10 <= len(relations["relations"]) <= 30


def test_release_build_includes_legal_notices_but_not_development_fixtures():
    script = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
    for filename in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"):
        assert f'"--add-data", "{filename};."' in script
    for filename in ("guide_data_en.json", "guide_data_poe2_en.json"):
        assert f'"--add-data", "{filename};."' in script
    assert '"--add-data", "data;data"' in script
    assert '"--add-data", "data\\i18n;data\\i18n"' in script
    assert '"--add-data", "tests;' not in script
    assert '"--add-data", "build;' not in script
    assert "poetore-sources\\.lock\\.json" in script
    assert "stats\\.min\\.json" in script and "mods\\.min\\.json" in script
    assert "exceeds 8 MiB" in script


def test_readme_notices_and_app_wording_cover_required_attribution():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    poetore_ui = (ROOT / "src" / "poetore" / "ui.py").read_text(encoding="utf-8")
    settings_ui = (ROOT / "src" / "ui" / "settings_dialog.py").read_text(encoding="utf-8")
    assert "Patreon" in readme
    assert "公認・承認を受けたものではありません" in readme
    assert "Awakened PoE Trade" in notices and "MIT License" in notices
    assert "RePoE" in notices and "全データはアプリへ同梱しません" in notices
    assert "無料の非公式ツール" not in poetore_ui
    assert "ぽえなびは無料の非公式ツール" in settings_ui
    assert "提携・承認関係はありません" in settings_ui
    assert "ぽえとれについて" not in settings_ui


def test_source_lock_is_development_only_and_pins_revision_and_hashes():
    lock = json.loads((ROOT / "scripts" / "poetore-sources.lock.json").read_text(encoding="utf-8"))
    sources = lock["sources"]
    assert sources["awakened_poe_trade"]["revision"]
    assert "/master/" not in sources["awakened_poe_trade"]["url"]
    assert all(len(row["sha256"]) == 64 for row in sources.values())
    assert not (ROOT / "data" / "poetore" / "poetore-sources.lock.json").exists()
