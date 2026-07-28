from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_run_dev_installs_missing_ocr_dependencies_before_starting_app():
    script = (ROOT / "run_dev.bat").read_text(encoding="utf-8")

    dependency_check = 'python -c "import winrt.windows.foundation;'
    install = "python -m pip install --upgrade -r requirements.txt"
    launch = "python -B main.py"

    assert script.count(dependency_check) == 2
    assert install in script
    assert "if errorlevel 1 (" in script
    assert "Windows OCR dependencies are still unavailable after installation." in script
    assert "exit /b 1" in script
    assert script.index(dependency_check) < script.index(install) < script.index(launch)


def test_windows_ocr_requirements_include_transitive_winrt_namespaces():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "winrt-Windows.Foundation;" in requirements
    assert "winrt-Windows.Foundation.Collections;" in requirements
    assert "winrt-Windows.Globalization[all]" in requirements
    assert "winrt-Windows.Graphics.Imaging[all]" in requirements
    assert "winrt-Windows.Media.Ocr[all]" in requirements
    assert "winrt-Windows.Storage.Streams[all]" in requirements
