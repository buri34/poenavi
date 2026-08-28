import subprocess
import sys

from src import app_composition
from src.app_mode import POENAVI_MODE, POETORE_MODE
from src.utils.poe_version_data import POE1, POE2


def test_poetore_mode_resolves_only_poetore_shell():
    resolved = app_composition.resolve_window_class(POETORE_MODE, POE1)

    assert resolved.__module__ == "src.ui.poetore_mode_window"
    assert resolved.__name__ == "PoetoreModeWindow"


def test_poennavi_mode_resolves_only_existing_main_window():
    resolved = app_composition.resolve_window_class(POENAVI_MODE)

    assert resolved.__module__ == "src.ui.main_window"
    assert resolved.__name__ == "MainWindow"


def test_poetore_mode_fails_closed_for_poe2():
    import pytest

    with pytest.raises(ValueError, match="では利用できません"):
        app_composition.resolve_window_class(POETORE_MODE, POE2)

def test_real_poetore_composition_does_not_import_poennavi_runtime_modules():
    script = (
        "import sys;"
        "from src.app_composition import resolve_window_class;"
        "resolve_window_class('poetore', 'poe1');"
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


def test_importing_composition_does_not_eagerly_import_either_mode_window():
    script = (
        "import sys;"
        "import src.app_composition;"
        "blocked=['src.ui.main_window','src.ui.poetore_mode_window'];"
        "print(','.join(name for name in blocked if name in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == ""


def test_real_poennavi_composition_does_not_import_poetore_shell():
    script = (
        "import sys;"
        "from src.app_composition import resolve_window_class;"
        "resolve_window_class('poenavi');"
        "print('src.ui.poetore_mode_window' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_composition_uses_static_imports_for_pyinstaller_discovery():
    source = app_composition.__loader__.get_source(app_composition.__name__)

    assert "from src.ui.main_window import MainWindow" in source
    assert "from src.ui.poetore_mode_window import PoetoreModeWindow" in source
    assert "importlib.import_module" not in source
