import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_poetore_distribution_contains_only_minimal_derived_data():
    data_dir = ROOT / "data" / "poetore"
    names = {path.name for path in data_dir.iterdir() if path.is_file()}
    expected = {
        "mod_metadata.json", "pseudo_relations.json", "pseudo_definitions.json",
        "map_mods.json", "divination_cards_ja.json", "multi_value_rules.json",
    }
    if os.environ.get("POETORE_CANDIDATE_BUILD") == "1":
        expected.add(".mod_metadata.json.candidate")
    assert names == expected
    index_path = Path(os.environ.get("POETORE_METADATA_PATH", data_dir / "mod_metadata.json"))
    assert index_path.stat().st_size < 8 * 1024 * 1024
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 3
    assert payload["scope"] == "PoE1 trade stat matching for equipment and gems"
    assert 8000 <= len(payload["mods"]) <= 12000
    assert 500 <= len(payload["gems"]) <= 1000
    required = {
        "ref", "stat_id", "kind", "japanese", "better", "inverted", "negated",
        "exact", "local", "decimal", "tiers", "options",
    }
    assert all(
        required <= set(row) <= required | {"category_select"}
        for row in payload["mods"]
    )
    assert all(isinstance(row["negated"], bool) for row in payload["mods"])
    assert sum(row["negated"] for row in payload["mods"]) == 145
    relations = json.loads((data_dir / "pseudo_relations.json").read_text(encoding="utf-8"))
    assert relations["source_revision"] and len(relations["source_sha256"]) == 64
    assert 10 <= len(relations["relations"]) <= 30


def test_release_build_includes_legal_notices_but_not_development_fixtures():
    script = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
    for filename in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"):
        assert f'"--add-data", "{filename};."' in script
    assert '"--add-data", "build\\third-party-licenses;THIRD_PARTY_LICENSES"' in script
    assert "collect_third_party_licenses.py" in script
    assert "THIRD_PARTY_LICENSES/Python-LICENSE.txt" in script
    assert '"--add-data", "data;data"' in script
    assert '"--add-data", "tests;' not in script
    assert '"--add-data", "build;' not in script
    assert "poetore-sources\\.lock\\.json" in script
    assert "stats\\.min\\.json" in script and "mods\\.min\\.json" in script
    assert "exceeds 8 MiB" in script
    assert '"--version-file", "build\\version\\PoENavi-version.txt"' in script
    assert '"--version-file", "build\\version\\PoENaviUpdater-version.txt"' in script
    assert '"--hidden-import", "keyboard"' not in script


def test_readme_notices_and_app_wording_cover_required_attribution():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    poetore_ui = (ROOT / "src" / "poetore" / "ui.py").read_text(encoding="utf-8")
    app_info_ui = (ROOT / "src" / "ui" / "app_info_widget.py").read_text(encoding="utf-8")
    assert "Patreon" in readme
    assert "公認・承認を受けたものではありません" in readme
    assert "Awakened PoE Trade" in notices and "MIT License" in notices
    assert "RePoE" in notices and "全データはアプリへ同梱しません" in notices
    assert "無料の非公式ツール" not in poetore_ui
    assert "ぽえなびは無料の非公式ツール" in app_info_ui
    assert "提携・承認関係はありません" in app_info_ui
    assert "ぽえとれについて" not in app_info_ui


def test_signpath_policy_and_privacy_documents_are_linked_and_complete():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    policy = (ROOT / "docs" / "CODE_SIGNING_POLICY.md").read_text(encoding="utf-8")
    privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
    assert "Code signing policy" in readme
    assert "Privacy policy" in readme
    assert "Free code signing provided by" in policy
    assert "SignPath.io" in policy and "SignPath Foundation" in policy
    assert "PoENavi.exe" in policy and "PoENaviUpdater.exe" in policy
    assert "manually reviews and approves each signing request" in policy
    assert "does not include telemetry" in privacy
    assert "%APPDATA%\\PoENavi\\" in privacy


def test_windows_build_verifies_executable_product_and_version_metadata():
    workflow = (ROOT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert 'python-version: "3.12.10"' in workflow
    assert "ProductName" in workflow and '"PoENavi"' in workflow
    assert "ProductVersion" in workflow and "FileVersion" in workflow
    assert "PoENavi.exe" in workflow and "PoENaviUpdater.exe" in workflow


def test_source_lock_is_development_only_and_pins_revision_and_hashes():
    lock = json.loads((ROOT / "scripts" / "poetore-sources.lock.json").read_text(encoding="utf-8"))
    sources = lock["sources"]
    assert sources["awakened_poe_trade"]["revision"]
    assert "/master/" not in sources["awakened_poe_trade"]["url"]
    assert all(len(row["sha256"]) == 64 for row in sources.values())
    assert not (ROOT / "data" / "poetore" / "poetore-sources.lock.json").exists()
