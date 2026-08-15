from __future__ import annotations

import importlib.util
from importlib.metadata import PackageNotFoundError
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "collect_third_party_licenses.py"
SPEC = importlib.util.spec_from_file_location("collect_third_party_licenses", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class FakeDistribution:
    def __init__(self, root: Path, name: str = "Example", version: str = "1.2.3") -> None:
        self.root = root
        self.metadata = {"Name": name}
        self.version = version
        self.files = [
            PurePosixPath(f"{name}-{version}.dist-info/licenses/LICENSE.txt"),
            PurePosixPath(f"{name}/module.py"),
        ]

    def locate_file(self, entry: PurePosixPath) -> Path:
        return self.root / Path(*entry.parts)


def test_collect_copies_python_and_distribution_license_texts(tmp_path, monkeypatch):
    package_root = tmp_path / "site-packages"
    license_path = package_root / "Example-1.2.3.dist-info/licenses/LICENSE.txt"
    license_path.parent.mkdir(parents=True)
    license_path.write_text("complete example license", encoding="utf-8")
    python_license = tmp_path / "Python-LICENSE.txt"
    python_license.write_text("complete python license", encoding="utf-8")
    monkeypatch.setattr(collector, "_python_license", lambda: python_license)
    monkeypatch.setattr(collector.metadata, "distribution", lambda name: FakeDistribution(package_root, name=name))

    output = tmp_path / "output"
    collector.collect(output, ("Example",))

    assert (output / "Python-LICENSE.txt").read_text() == "complete python license"
    assert (output / "Example-1.2.3/LICENSE.txt").read_text() == "complete example license"
    assert "Example-1.2.3/LICENSE.txt" in (output / "README.md").read_text(encoding="utf-8")


def test_collect_fails_when_required_distribution_is_missing(tmp_path, monkeypatch):
    python_license = tmp_path / "Python-LICENSE.txt"
    python_license.write_text("python", encoding="utf-8")
    monkeypatch.setattr(collector, "_python_license", lambda: python_license)

    def missing(_name):
        raise PackageNotFoundError

    monkeypatch.setattr(collector.metadata, "distribution", missing)
    with pytest.raises(RuntimeError, match="Required distribution is not installed"):
        collector.collect(tmp_path / "output", ("Missing",))


def test_collect_fails_when_complete_license_text_is_absent(tmp_path, monkeypatch):
    python_license = tmp_path / "Python-LICENSE.txt"
    python_license.write_text("python", encoding="utf-8")
    distribution = SimpleNamespace(
        metadata={"Name": "NoLicense"}, version="1.0",
        files=[PurePosixPath("NoLicense/module.py")],
        locate_file=lambda entry: tmp_path / Path(*entry.parts),
    )
    monkeypatch.setattr(collector, "_python_license", lambda: python_license)
    monkeypatch.setattr(collector.metadata, "distribution", lambda _name: distribution)
    with pytest.raises(RuntimeError, match="No complete license text found"):
        collector.collect(tmp_path / "output", ("NoLicense",))
