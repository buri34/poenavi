from src import app_composition
from src.app_mode import POENAVI_MODE, POETORE_MODE
import subprocess
import sys


def test_poetore_mode_resolves_only_poetore_shell(monkeypatch):
    imported = []
    sentinel = object()

    class Module:
        PoetoreModeWindow = sentinel

    def fake_import(name):
        imported.append(name)
        return Module

    monkeypatch.setattr(app_composition.importlib, "import_module", fake_import)

    assert app_composition.resolve_window_class(POETORE_MODE) is sentinel
    assert imported == ["src.ui.poetore_mode_window"]


def test_poennavi_mode_resolves_only_existing_main_window(monkeypatch):
    imported = []
    sentinel = object()

    class Module:
        MainWindow = sentinel

    def fake_import(name):
        imported.append(name)
        return Module

    monkeypatch.setattr(app_composition.importlib, "import_module", fake_import)

    assert app_composition.resolve_window_class(POENAVI_MODE) is sentinel
    assert imported == ["src.ui.main_window"]


def test_real_poetore_composition_does_not_import_poennavi_runtime_modules():
    script = (
        "import sys;"
        "from src.app_composition import resolve_window_class;"
        "resolve_window_class('poetore');"
        "blocked=['src.ui.main_window','src.utils.log_watcher','src.ui.mini_navi'];"
        "print(','.join(name for name in blocked if name in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == ""
