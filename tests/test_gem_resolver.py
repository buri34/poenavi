from src.utils.gem_resolver import resolve_gem_acquisition


def test_breaking_some_eggs_reward_appears_before_vendor():
    plan = resolve_gem_acquisition(["frostblink", "shield charge"], "shadow", library_route=True)
    entries = [entry for entry in plan if entry["quest"] in ("breaking some eggs1", "breaking some eggs2")]

    assert [entry["quest"] for entry in entries] == ["breaking some eggs2", "breaking some eggs1"]
    assert entries[0]["gems"][0]["type"] == "quest"
    assert entries[1]["gems"][0]["type"] == "vendor"


def test_frozen_data_dir_falls_back_to_meipass(monkeypatch, tmp_path):
    import sys
    from src.utils import gem_resolver

    exe_dir = tmp_path / "dist" / "PoENavi"
    meipass = exe_dir / "_internal"
    (meipass / "data").mkdir(parents=True)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "PoENavi.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)

    assert gem_resolver._get_data_dir() == str(meipass / "data")
