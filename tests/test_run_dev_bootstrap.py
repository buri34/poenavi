from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_run_dev_installs_missing_ocr_dependencies_before_starting_app():
    script = (ROOT / "run_dev.bat").read_text(encoding="utf-8")

    dependency_check = 'python -c "from winrt.windows.globalization import Language;'
    install = "python -m pip install -r requirements.txt"
    launch = "python -B main.py"

    assert dependency_check in script
    assert install in script
    assert "if errorlevel 1 (" in script
    assert "exit /b 1" in script
    assert script.index(dependency_check) < script.index(install) < script.index(launch)
