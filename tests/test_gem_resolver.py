from src.utils.gem_resolver import resolve_gem_acquisition


def test_breaking_some_eggs_reward_appears_before_vendor():
    plan = resolve_gem_acquisition(["frostblink", "shield charge"], "shadow", library_route=True)
    entries = [entry for entry in plan if entry["quest"] in ("breaking some eggs1", "breaking some eggs2")]

    assert [entry["quest"] for entry in entries] == ["breaking some eggs2", "breaking some eggs1"]
    assert entries[0]["gems"][0]["type"] == "quest"
    assert entries[1]["gems"][0]["type"] == "vendor"


def test_quest_reward_gem_keeps_same_act_vendor_availability():
    plan = resolve_gem_acquisition(["momentum support"], "duelist", library_route=True)

    gem = plan[0]["gems"][0]

    assert gem["type"] == "quest"
    assert gem["vendor_acts"] == [1, 3]


def test_resolver_excludes_starter_support_gems():
    for char_class, gem_name in [
        ("witch", "arcane surge support"),
        ("shadow", "chance to poison support"),
        ("ranger", "momentum support"),
        ("duelist", "chance to bleed support"),
        ("marauder", "ruthless support"),
    ]:
        plan = resolve_gem_acquisition(
            [gem_name],
            char_class,
            gems_db={
                "_quests": {"mercy mission": {"act": 1}},
                gem_name: {"attribute": 1, "quests": {"mercy mission": {"vendor": []}}},
            },
        )

        assert plan == [], gem_name


def test_resolver_excludes_starter_support_gem_when_pob_omits_support_suffix():
    plan = resolve_gem_acquisition(
        ["chance to bleed"],
        "duelist",
        gems_db={
            "_quests": {"mercy mission": {"act": 1}},
            "chance to bleed support": {
                "attribute": 1,
                "quests": {"mercy mission": {"vendor": []}},
            },
        },
    )

    assert plan == []


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
