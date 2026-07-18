# GUI Auto-Update Implementation Plan

> **2026-07-18更新:** 更新マニフェストと編集済み公式ガイドの引き継ぎ設計は廃止した。以下に残るマニフェスト関連の詳細手順・コード例は当初実装の履歴であり、現行仕様ではない。現行仕様では公式ガイドを最新版へ置換し、別ファイルのエリア別ユーザーメモをユーザーデータとして保持する。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GitHub Release の安定版を、Windows exe 版の GUI から検出、ダウンロード、検証、置換、再起動できるようにする。

**Architecture:** GitHub API・バージョン比較・ZIP検証は Qt 非依存の `src/update` パッケージへ分離する。本体は Qt コントローラーを介して非同期処理とダイアログを扱い、インストール先の置換は一時領域へコピーした専用 `PoENaviUpdater.exe` が本体終了後に行う。`v*` タグの push から GitHub Actions がテスト、ビルド、チェックサム生成、Release 添付までを自動化する。

**Tech Stack:** Python 3.12、PySide6、標準ライブラリ（`urllib.request`、`hashlib`、`zipfile`、`tempfile`、`subprocess`、`ctypes`）、PyInstaller、pytest、GitHub Actions、GitHub CLI

## Global Constraints

- 更新元は `https://api.github.com/repos/buri34/poenavi/releases/latest` と GitHub 管理下の Release アセットに限定する。
- ドラフト、プレリリース、`main` の通常 push は更新対象にしない。
- Release の必須アセット名は `PoENavi.zip` と `PoENavi.zip.sha256` とする。
- 配布 ZIP は単一の `PoENavi/` ルートを持ち、その直下に `PoENavi.exe` と `PoENaviUpdater.exe` を含める。
- 自動置換は Windows の PyInstaller exe 版でのみ有効にし、ソース実行時は Release ページを案内する。
- SHA-256 不一致、危険な ZIP エントリー、書き込み権限不足では本体を終了しない。
- 更新失敗時は旧インストールを復元し、復元不能時はバックアップを削除しない。
- 公式ガイドとゾーンデータは最新版へ置換し、エリア別ユーザーメモはユーザーデータ領域で保持する。
- シェル文字列を組み立てず、プロセス起動は引数配列を使用する。

---

## File Map

- Create `src/version.py`: アプリの唯一のバージョン定義。
- Create `src/update/__init__.py`: 更新パッケージの公開型。
- Create `src/update/release_client.py`: SemVer 比較と GitHub Release API 解析。
- Create `src/update/artifacts.py`: ダウンロード、SHA-256、ZIP 安全性検証。
- Create `src/update/updater_engine.py`: 待機、ステージング、置換、復元、再起動。
- Create `src/update/qt_controller.py`: バックグラウンド確認・ダウンロードを Qt Signal へ変換。
- Create `src/ui/update_dialogs.py`: 更新通知と進捗ダイアログ。
- Create `updater_main.py`: `PoENaviUpdater.exe` のエントリーポイント。
- Create `scripts/build_release.ps1`: 再現可能な Windows リリースビルド。
- Create `.github/workflows/release.yml`: タグから Release を生成。
- Modify `main.py`: 一元化したバージョンを公開。
- Modify `src/ui/main_window.py`: 旧通知処理をコントローラーと GUI フローへ交換。
- Modify `build_exe.bat`: 対話的ラッパーとして PowerShell ビルドを呼ぶ。
- Modify `README.md`: GUI 更新とリリース手順を説明。
- Create `tests/test_release_client.py`, `tests/test_update_artifacts.py`, `tests/test_updater_engine.py`, `tests/test_update_qt_controller.py`, `tests/test_update_gui_flow.py`: 更新機能の単体・結合テスト。

---

### Task 1: Version Source and Release Parsing

**Files:**
- Create: `src/version.py`
- Create: `src/update/__init__.py`
- Create: `src/update/release_client.py`
- Modify: `main.py:1-6`
- Test: `tests/test_release_client.py`

**Interfaces:**
- Produces: `APP_VERSION: str`
- Produces: `parse_version(value: str) -> tuple[int, int, int]`
- Produces: `ReleaseInfo(version: str, notes: str, page_url: str, zip_url: str, checksum_url: str)`
- Produces: `parse_latest_release(payload: dict, current_version: str) -> ReleaseInfo | None`
- Produces: `fetch_latest_release(current_version: str, opener=urllib.request.urlopen) -> ReleaseInfo | None`

- [ ] **Step 1: Write version and Release parsing tests**

```python
# tests/test_release_client.py
import io
import json

import pytest

from src.update.release_client import fetch_latest_release, parse_latest_release, parse_version


def release_payload(tag="v2.5.0", *, draft=False, prerelease=False, assets=None):
    return {
        "tag_name": tag,
        "name": f"PoENavi {tag}",
        "body": "変更内容",
        "html_url": f"https://github.com/buri34/poenavi/releases/tag/{tag}",
        "draft": draft,
        "prerelease": prerelease,
        "assets": assets or [
            {"name": "PoENavi.zip", "browser_download_url": "https://github.com/buri34/poenavi/releases/download/v2.5.0/PoENavi.zip"},
            {"name": "PoENavi.zip.sha256", "browser_download_url": "https://github.com/buri34/poenavi/releases/download/v2.5.0/PoENavi.zip.sha256"},
        ],
    }


@pytest.mark.parametrize("value, expected", [("2.4.0", (2, 4, 0)), ("v10.2.3", (10, 2, 3))])
def test_parse_version(value, expected):
    assert parse_version(value) == expected


@pytest.mark.parametrize("value", ["2.4", "2.4.0-beta", "release-2.4.0", ""])
def test_parse_version_rejects_non_release_tags(value):
    with pytest.raises(ValueError):
        parse_version(value)


def test_parse_latest_release_returns_new_stable_release():
    release = parse_latest_release(release_payload(), "2.4.0")
    assert release is not None
    assert release.version == "2.5.0"
    assert release.notes == "変更内容"
    assert release.zip_url.endswith("PoENavi.zip")
    assert release.checksum_url.endswith("PoENavi.zip.sha256")


@pytest.mark.parametrize("payload", [
    release_payload(tag="v2.4.0"),
    release_payload(draft=True),
    release_payload(prerelease=True),
    release_payload(assets=[{"name": "PoENavi.zip", "browser_download_url": "https://github.com/file"}]),
])
def test_parse_latest_release_ignores_ineligible_release(payload):
    assert parse_latest_release(payload, "2.4.0") is None


def test_fetch_latest_release_sends_user_agent_and_timeout():
    calls = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def opener(request, timeout):
        calls.append((request, timeout))
        return Response(json.dumps(release_payload()).encode("utf-8"))

    release = fetch_latest_release("2.4.0", opener=opener)
    assert release.version == "2.5.0"
    assert calls[0][0].get_header("User-agent") == "PoENavi-Updater"
    assert calls[0][1] == 10
```

- [ ] **Step 2: Run the test and confirm the missing module failure**

Run: `python -m pytest tests/test_release_client.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'src.update'`.

- [ ] **Step 3: Add the version source and Release client**

```python
# src/version.py
APP_VERSION = "2.4.0"
```

```python
# src/update/__init__.py
from src.update.release_client import ReleaseInfo

__all__ = ["ReleaseInfo"]
```

```python
# src/update/release_client.py
from dataclasses import dataclass
import json
import re
import urllib.request

RELEASES_API = "https://api.github.com/repos/buri34/poenavi/releases/latest"
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    notes: str
    page_url: str
    zip_url: str
    checksum_url: str


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError(f"不正なバージョン形式です: {value}")
    return tuple(int(part) for part in match.groups())


def parse_latest_release(payload: dict, current_version: str) -> ReleaseInfo | None:
    if payload.get("draft") or payload.get("prerelease"):
        return None
    tag = str(payload.get("tag_name", ""))
    try:
        latest = parse_version(tag)
        current = parse_version(current_version)
    except ValueError:
        return None
    if latest <= current:
        return None
    assets = {asset.get("name"): asset.get("browser_download_url") for asset in payload.get("assets", [])}
    zip_url = assets.get("PoENavi.zip")
    checksum_url = assets.get("PoENavi.zip.sha256")
    if not zip_url or not checksum_url:
        return None
    return ReleaseInfo(
        version=".".join(str(part) for part in latest),
        notes=str(payload.get("body") or "変更内容はリリースページで確認できます。"),
        page_url=str(payload.get("html_url") or "https://github.com/buri34/poenavi/releases/latest"),
        zip_url=str(zip_url),
        checksum_url=str(checksum_url),
    )


def fetch_latest_release(current_version: str, opener=urllib.request.urlopen) -> ReleaseInfo | None:
    request = urllib.request.Request(RELEASES_API, headers={"User-Agent": "PoENavi-Updater"})
    with opener(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_latest_release(payload, current_version)
```

Change `main.py` to import rather than define the version:

```python
from src.version import APP_VERSION

__version__ = APP_VERSION
```

- [ ] **Step 4: Run the focused tests**

Run: `python -m pytest tests/test_release_client.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add main.py src/version.py src/update/__init__.py src/update/release_client.py tests/test_release_client.py
git commit -m "feat: add versioned release discovery"
```

---

### Task 2: Download, Checksum, and Safe ZIP Validation

**Files:**
- Create: `src/update/artifacts.py`
- Test: `tests/test_update_artifacts.py`

**Interfaces:**
- Consumes: `ReleaseInfo.zip_url`, `ReleaseInfo.checksum_url`
- Produces: `DownloadCancelled`
- Produces: `download_file(url: str, destination: Path, progress: Callable[[int, int], None], cancelled: Callable[[], bool], opener=urllib.request.urlopen) -> Path`
- Produces: `parse_checksum(text: str, filename: str = "PoENavi.zip") -> str`
- Produces: `verify_sha256(path: Path, expected: str) -> bool`
- Produces: `validate_update_archive(path: Path) -> None`

- [ ] **Step 1: Write artifact validation tests**

```python
# tests/test_update_artifacts.py
import hashlib
import io
from pathlib import Path
import zipfile

import pytest

from src.update.artifacts import DownloadCancelled, download_file, parse_checksum, validate_update_archive, verify_sha256


def write_zip(path: Path, names: list[str]):
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"content")


def test_parse_checksum_and_verify_file(tmp_path):
    archive = tmp_path / "PoENavi.zip"
    archive.write_bytes(b"release")
    digest = hashlib.sha256(b"release").hexdigest()
    assert parse_checksum(f"{digest}  PoENavi.zip\n") == digest
    assert verify_sha256(archive, digest)


@pytest.mark.parametrize("text", ["bad PoENavi.zip", "a" * 64 + "  Other.zip", ""])
def test_parse_checksum_rejects_invalid_content(text):
    with pytest.raises(ValueError):
        parse_checksum(text)


def test_validate_update_archive_accepts_release_layout(tmp_path):
    archive = tmp_path / "PoENavi.zip"
    write_zip(archive, ["PoENavi/PoENavi.exe", "PoENavi/PoENaviUpdater.exe", "PoENavi/update-manifest.json"])
    validate_update_archive(archive)


@pytest.mark.parametrize("entry", ["../outside", "PoENavi/../../outside", "/absolute", "C:/absolute"])
def test_validate_update_archive_rejects_path_escape(tmp_path, entry):
    archive = tmp_path / "PoENavi.zip"
    write_zip(archive, ["PoENavi/PoENavi.exe", "PoENavi/PoENaviUpdater.exe", "PoENavi/update-manifest.json", entry])
    with pytest.raises(ValueError):
        validate_update_archive(archive)


def test_download_reports_progress_and_honors_cancel(tmp_path):
    class Response(io.BytesIO):
        headers = {"Content-Length": "7"}
        def __enter__(self): return self
        def __exit__(self, *_args): self.close()

    progress = []
    target = download_file(
        "https://github.com/file",
        tmp_path / "file",
        lambda done, total: progress.append((done, total)),
        lambda: False,
        opener=lambda _request, timeout: Response(b"release"),
    )
    assert target.read_bytes() == b"release"
    assert progress[-1] == (7, 7)

    with pytest.raises(DownloadCancelled):
        download_file(
            "https://github.com/file",
            tmp_path / "cancelled",
            lambda _done, _total: None,
            lambda: True,
            opener=lambda _request, timeout: Response(b"release"),
        )
```

- [ ] **Step 2: Run the tests and confirm failure**

Run: `python -m pytest tests/test_update_artifacts.py -v`

Expected: collection fails because `src.update.artifacts` does not exist.

- [ ] **Step 3: Implement the artifact module**

```python
# src/update/artifacts.py
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Callable
import urllib.request
import zipfile

CHECKSUM_PATTERN = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(.+)$")
GITHUB_HOSTS = {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}


class DownloadCancelled(Exception):
    pass


def _validate_url(url: str) -> None:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in GITHUB_HOSTS:
        raise ValueError("GitHub 管理外のダウンロード URL です")


def _request(url: str) -> urllib.request.Request:
    _validate_url(url)
    return urllib.request.Request(url, headers={"User-Agent": "PoENavi-Updater"})


def download_file(
    url: str,
    destination: Path,
    progress: Callable[[int, int], None],
    cancelled: Callable[[], bool],
    opener=urllib.request.urlopen,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with opener(_request(url), timeout=30) as response, destination.open("wb") as output:
            _validate_url(getattr(response, "geturl", lambda: url)())
            total = int(response.headers.get("Content-Length", "0"))
            done = 0
            while True:
                if cancelled():
                    raise DownloadCancelled()
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                output.write(chunk)
                done += len(chunk)
                progress(done, total)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def parse_checksum(text: str, filename: str = "PoENavi.zip") -> str:
    match = CHECKSUM_PATTERN.fullmatch(text.strip())
    if not match or Path(match.group(2)).name != filename:
        raise ValueError("チェックサムファイルの形式が不正です")
    return match.group(1).lower()


def verify_sha256(path: Path, expected: str) -> bool:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected.lower()


def validate_update_archive(path: Path) -> None:
    required = {"PoENavi/PoENavi.exe", "PoENavi/PoENaviUpdater.exe", "PoENavi/update-manifest.json"}
    with zipfile.ZipFile(path) as archive:
        names = set()
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != "PoENavi" or ".." in parts or PurePosixPath(name).is_absolute() or re.match(r"^[A-Za-z]:", name):
                raise ValueError(f"危険な ZIP エントリーです: {name}")
            unix_mode = info.external_attr >> 16
            if unix_mode and (unix_mode & 0o170000) == 0o120000:
                raise ValueError(f"リンクを含む ZIP は使用できません: {name}")
            names.add(name.rstrip("/"))
    missing = required - names
    if missing:
        raise ValueError(f"更新 ZIP に必須ファイルがありません: {', '.join(sorted(missing))}")
```

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_update_artifacts.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/update/artifacts.py tests/test_update_artifacts.py
git commit -m "feat: validate update artifacts"
```

---

### Task 3: Mutable-File Manifest and Preservation

**Files:**
- Create: `src/update/manifest.py`
- Create: `scripts/generate_update_manifest.py`
- Test: `tests/test_update_manifest.py`

**Interfaces:**
- Produces: `MUTABLE_PATHS: tuple[Path, ...]`
- Produces: `build_manifest(root: Path, version: str) -> dict`
- Produces: `write_manifest(root: Path, version: str) -> Path`
- Produces: `preserve_modified_files(old_root: Path, new_root: Path) -> list[Path]`

- [ ] **Step 1: Write manifest behavior tests**

```python
# tests/test_update_manifest.py
import hashlib
import json
from pathlib import Path

from src.update.manifest import preserve_modified_files, write_manifest


def seed(root: Path, relative: str, content: str):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_unmodified_mutable_file_uses_new_release_content(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    seed(old, "guide_data.json", "old-default")
    seed(new, "guide_data.json", "new-default")
    write_manifest(old, "2.4.0")
    assert preserve_modified_files(old, new) == []
    assert (new / "guide_data.json").read_text(encoding="utf-8") == "new-default"


def test_modified_mutable_file_is_copied_to_new_release(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    seed(old, "guide_data.json", "old-default")
    write_manifest(old, "2.4.0")
    (old / "guide_data.json").write_text("user-edit", encoding="utf-8")
    seed(new, "guide_data.json", "new-default")
    assert preserve_modified_files(old, new) == [Path("guide_data.json")]
    assert (new / "guide_data.json").read_text(encoding="utf-8") == "user-edit"


def test_missing_old_manifest_preserves_known_mutable_files(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    seed(old, "_internal/data/zone_data.json", "legacy-user-data")
    seed(new, "_internal/data/zone_data.json", "new-default")
    assert preserve_modified_files(old, new) == [Path("_internal/data/zone_data.json")]
```

- [ ] **Step 2: Run tests and confirm the missing module failure**

Run: `python -m pytest tests/test_update_manifest.py -v`

Expected: collection fails because `src.update.manifest` does not exist.

- [ ] **Step 3: Implement manifest generation and preservation**

```python
# src/update/manifest.py
import hashlib
import json
from pathlib import Path
import shutil

MANIFEST_NAME = "update-manifest.json"
MUTABLE_PATHS = tuple(Path(value) for value in (
    "guide_data.json",
    "guide_data_poe2.json",
    "data/zone_data.json",
    "_internal/guide_data.json",
    "_internal/guide_data_poe2.json",
    "_internal/data/zone_data.json",
))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path, version: str) -> dict:
    files = {path.as_posix(): _sha256(root / path) for path in MUTABLE_PATHS if (root / path).is_file()}
    return {"schema": 1, "version": version, "mutable_files": files}


def write_manifest(root: Path, version: str) -> Path:
    target = root / MANIFEST_NAME
    target.write_text(json.dumps(build_manifest(root, version), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def preserve_modified_files(old_root: Path, new_root: Path) -> list[Path]:
    manifest_path = old_root / MANIFEST_NAME
    try:
        old_hashes = json.loads(manifest_path.read_text(encoding="utf-8")).get("mutable_files", {})
        has_manifest = True
    except (OSError, ValueError, TypeError):
        old_hashes = {}
        has_manifest = False
    preserved = []
    for relative in MUTABLE_PATHS:
        source = old_root / relative
        destination = new_root / relative
        if not source.is_file() or not destination.is_file():
            continue
        expected = old_hashes.get(relative.as_posix())
        modified = not has_manifest or expected is None or _sha256(source) != expected
        if modified:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            preserved.append(relative)
    return preserved
```

```python
# scripts/generate_update_manifest.py
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.update.manifest import write_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("version")
    args = parser.parse_args()
    write_manifest(args.root.resolve(), args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_update_manifest.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/update/manifest.py scripts/generate_update_manifest.py tests/test_update_manifest.py
git commit -m "feat: preserve edited data during updates"
```

---

### Task 4: External Updater Engine and Entry Point

**Files:**
- Create: `src/update/updater_engine.py`
- Create: `updater_main.py`
- Test: `tests/test_updater_engine.py`

**Interfaces:**
- Consumes: `validate_update_archive(path)` and `preserve_modified_files(old_root, new_root)`
- Produces: `wait_for_process_exit(pid: int, timeout: float, process_running: Callable[[int], bool]) -> bool`
- Produces: `apply_update(archive: Path, install_dir: Path, work_dir: Path, launcher: Callable[[Path], object], startup_check: Callable[[object], bool]) -> Path`
- Produces: updater CLI arguments `--pid`, `--archive`, `--install-dir`, `--work-dir`

- [ ] **Step 1: Write updater engine tests**

```python
# tests/test_updater_engine.py
from pathlib import Path
import zipfile

import pytest

from src.update.updater_engine import UpdateApplyError, apply_update, wait_for_process_exit


def make_release(path: Path, marker="new"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("PoENavi/PoENavi.exe", marker)
        archive.writestr("PoENavi/PoENaviUpdater.exe", "updater")
        archive.writestr("PoENavi/update-manifest.json", '{"schema": 1, "version": "2.5.0", "mutable_files": {}}')


def test_wait_for_process_exit_stops_when_process_finishes():
    states = iter([True, True, False])
    assert wait_for_process_exit(42, 1, lambda _pid: next(states), sleep=lambda _seconds: None)


def test_apply_update_replaces_install_and_launches_new_exe(tmp_path):
    install = tmp_path / "ぽえなび" / "PoENavi"
    install.mkdir(parents=True)
    (install / "PoENavi.exe").write_text("old", encoding="utf-8")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)
    launched = []
    backup = apply_update(archive, install, tmp_path / "work", lambda exe: launched.append(exe))
    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "new"
    assert launched == [install / "PoENavi.exe"]
    assert backup.exists()


def test_apply_update_restores_old_install_when_launch_fails(tmp_path):
    install = tmp_path / "PoENavi"
    install.mkdir()
    (install / "PoENavi.exe").write_text("old", encoding="utf-8")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)
    with pytest.raises(UpdateApplyError):
        apply_update(archive, install, tmp_path / "work", lambda _exe: (_ for _ in ()).throw(OSError("launch failed")))
    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "old"


def test_apply_update_restores_old_install_when_new_app_exits_immediately(tmp_path):
    install = tmp_path / "PoENavi"
    install.mkdir()
    (install / "PoENavi.exe").write_text("old", encoding="utf-8")
    archive = tmp_path / "PoENavi.zip"
    make_release(archive)
    with pytest.raises(UpdateApplyError):
        apply_update(archive, install, tmp_path / "work", lambda _exe: object(), startup_check=lambda _process: False)
    assert (install / "PoENavi.exe").read_text(encoding="utf-8") == "old"
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `python -m pytest tests/test_updater_engine.py -v`

Expected: collection fails because `src.update.updater_engine` does not exist.

- [ ] **Step 3: Implement the updater engine**

```python
# src/update/updater_engine.py
from pathlib import Path
import shutil
import time
from typing import Callable
import zipfile

from src.update.artifacts import validate_update_archive
from src.update.manifest import preserve_modified_files


class UpdateApplyError(RuntimeError):
    def __init__(self, message: str, backup: Path | None = None):
        super().__init__(message)
        self.backup = backup


def wait_for_process_exit(pid: int, timeout: float, process_running: Callable[[int], bool], sleep=time.sleep) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_running(pid):
            return True
        sleep(0.2)
    return not process_running(pid)


def apply_update(
    archive: Path,
    install_dir: Path,
    work_dir: Path,
    launcher: Callable[[Path], object],
    startup_check: Callable[[object], bool] = lambda _process: True,
) -> Path:
    archive = archive.resolve()
    install_dir = install_dir.resolve()
    work_dir = work_dir.resolve()
    validate_update_archive(archive)
    stage = work_dir / "stage"
    backup = install_dir.with_name(f"{install_dir.name}.backup")
    shutil.rmtree(stage, ignore_errors=True)
    if backup.exists():
        raise UpdateApplyError(f"既存のバックアップがあります: {backup}", backup)
    stage.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(stage)
    replacement = stage / "PoENavi"
    if not (replacement / "PoENavi.exe").is_file():
        raise UpdateApplyError("更新後の PoENavi.exe がありません")
    preserve_modified_files(install_dir, replacement)
    try:
        install_dir.rename(backup)
        shutil.move(str(replacement), str(install_dir))
        process = launcher(install_dir / "PoENavi.exe")
        if not startup_check(process):
            raise RuntimeError("更新後のぽえなびが起動直後に終了しました")
        return backup
    except Exception as exc:
        if install_dir.exists():
            failed = install_dir.with_name(f"{install_dir.name}.failed")
            if failed.exists():
                shutil.rmtree(failed)
            install_dir.rename(failed)
        if backup.exists():
            backup.rename(install_dir)
        raise UpdateApplyError(f"更新に失敗したため旧版を復元しました: {exc}", backup) from exc
```

- [ ] **Step 4: Implement the updater executable entry point**

```python
# updater_main.py
import argparse
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import time

from PySide6.QtWidgets import QApplication, QMessageBox
from src.update.updater_engine import UpdateApplyError, apply_update, wait_for_process_exit


def process_running(pid: int) -> bool:
    SYNCHRONIZE = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x00000102
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def show_error(message: str):
    app = QApplication.instance() or QApplication([])
    QMessageBox.critical(None, "ぽえなび アップデート", message)
    app.processEvents()


def startup_stable(process) -> bool:
    time.sleep(3)
    return process.poll() is None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--install-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    if not (args.install_dir.resolve() / "PoENavi.exe").is_file():
        show_error("更新対象の PoENavi.exe が見つかりません。")
        return 2
    if not wait_for_process_exit(args.pid, 30, process_running):
        show_error("ぽえなびを終了できなかったため、更新を中止しました。")
        return 3
    try:
        backup = apply_update(
            args.archive,
            args.install_dir,
            args.work_dir,
            lambda exe: subprocess.Popen([str(exe)], cwd=str(exe.parent)),
            startup_check=startup_stable,
        )
    except UpdateApplyError as exc:
        suffix = f"\nバックアップ: {exc.backup}" if exc.backup else ""
        show_error(f"{exc}{suffix}")
        return 4
    shutil.rmtree(backup, ignore_errors=True)
    shutil.rmtree(args.work_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_updater_engine.py -v`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/update/updater_engine.py updater_main.py tests/test_updater_engine.py
git commit -m "feat: add rollback-safe external updater"
```

---

### Task 5: Qt Update Controller

**Files:**
- Create: `src/update/qt_controller.py`
- Test: `tests/test_update_qt_controller.py`

**Interfaces:**
- Consumes: `APP_VERSION`, `ReleaseInfo`, `fetch_latest_release`, `download_file`, `parse_checksum`, `verify_sha256`, `validate_update_archive`
- Produces: `UpdateController.check_finished(object, bool)`, `check_failed(str, bool)`, `download_progress(int, int)`, `download_ready(object, object)`, `download_failed(str)`, `download_cancelled()`
- Produces: `check(manual: bool)`, `download(release: ReleaseInfo)`, `cancel_download()`, `launch_updater(archive: Path) -> None`

- [ ] **Step 1: Write controller tests with all network and process effects mocked**

```python
# tests/test_update_qt_controller.py
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication

from src.update.qt_controller import UpdateController
from src.update.release_client import ReleaseInfo


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    return QCoreApplication.instance() or QCoreApplication([])


def test_check_emits_release_and_manual_flag(monkeypatch):
    release = ReleaseInfo("2.5.0", "notes", "https://github.com/page", "https://github.com/a.zip", "https://github.com/a.sha256")
    class ImmediateThread:
        def __init__(self, target):
            self.target = target
        def start(self):
            self.target()
    controller = UpdateController(thread_factory=ImmediateThread)
    received = []
    controller.check_finished.connect(lambda value, manual: received.append((value, manual)))
    monkeypatch.setattr("src.update.qt_controller.fetch_latest_release", lambda _version: release)
    controller.check(True)
    assert received == [(release, True)]


def test_launch_updater_copies_executable_and_uses_argument_list(tmp_path, monkeypatch):
    install = tmp_path / "ぽえなび" / "PoENavi"
    install.mkdir(parents=True)
    (install / "PoENavi.exe").write_text("app", encoding="utf-8")
    (install / "PoENaviUpdater.exe").write_text("updater", encoding="utf-8")
    archive = tmp_path / "PoENavi.zip"
    archive.write_bytes(b"zip")
    launched = []
    controller = UpdateController()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(install / "PoENavi.exe"))
    monkeypatch.setattr("src.update.qt_controller.subprocess.Popen", lambda args, cwd: launched.append((args, cwd)))
    controller.launch_updater(archive)
    assert launched[0][0][0].endswith("PoENaviUpdater.exe")
    assert "--install-dir" in launched[0][0]
    assert launched[0][0][launched[0][0].index("--install-dir") + 1] == str(install)
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `python -m pytest tests/test_update_qt_controller.py -v`

Expected: collection fails because `src.update.qt_controller` does not exist.

- [ ] **Step 3: Implement the Qt controller**

```python
# src/update/qt_controller.py
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import threading

from PySide6.QtCore import QObject, Signal

from src.update.artifacts import DownloadCancelled, download_file, parse_checksum, validate_update_archive, verify_sha256
from src.update.release_client import ReleaseInfo, fetch_latest_release
from src.version import APP_VERSION


class UpdateController(QObject):
    check_finished = Signal(object, bool)
    check_failed = Signal(str, bool)
    download_progress = Signal(int, int)
    download_ready = Signal(object, object)
    download_failed = Signal(str)
    download_cancelled = Signal()

    def __init__(self, parent=None, thread_factory=None):
        super().__init__(parent)
        self._thread_factory = thread_factory or (lambda target: threading.Thread(target=target, daemon=True))
        self._checking = False
        self._downloading = False
        self._cancel = threading.Event()
        self._work_dir = None

    def check(self, manual: bool) -> None:
        if self._checking:
            return
        self._checking = True
        def work():
            try:
                self.check_finished.emit(fetch_latest_release(APP_VERSION), manual)
            except Exception as exc:
                self.check_failed.emit(str(exc), manual)
            finally:
                self._checking = False
        self._thread_factory(work).start()

    def download(self, release: ReleaseInfo) -> None:
        if self._downloading:
            return
        self._downloading = True
        self._cancel.clear()
        self._work_dir = Path(tempfile.mkdtemp(prefix=f"PoENavi-{release.version}-"))
        def work():
            try:
                archive = download_file(release.zip_url, self._work_dir / "PoENavi.zip", self.download_progress.emit, self._cancel.is_set)
                checksum_file = download_file(release.checksum_url, self._work_dir / "PoENavi.zip.sha256", lambda _done, _total: None, self._cancel.is_set)
                expected = parse_checksum(checksum_file.read_text(encoding="utf-8"))
                if not verify_sha256(archive, expected):
                    raise ValueError("ダウンロードした ZIP の SHA-256 が一致しません。")
                validate_update_archive(archive)
                self.download_ready.emit(archive, release)
            except DownloadCancelled:
                self.download_cancelled.emit()
            except Exception as exc:
                self.download_failed.emit(str(exc))
            finally:
                self._downloading = False
        self._thread_factory(work).start()

    def cancel_download(self) -> None:
        self._cancel.set()

    def launch_updater(self, archive: Path) -> None:
        if not getattr(sys, "frozen", False) or sys.platform != "win32":
            raise RuntimeError("自動更新は Windows exe 版でのみ利用できます。")
        install_dir = Path(sys.executable).resolve().parent
        source = install_dir / "PoENaviUpdater.exe"
        if not source.is_file():
            raise RuntimeError("PoENaviUpdater.exe が見つかりません。")
        work_dir = Path(tempfile.mkdtemp(prefix="PoENavi-Updater-"))
        updater = work_dir / "PoENaviUpdater.exe"
        shutil.copy2(source, updater)
        subprocess.Popen([
            str(updater), "--pid", str(os.getpid()), "--archive", str(Path(archive).resolve()),
            "--install-dir", str(install_dir), "--work-dir", str(work_dir),
        ], cwd=str(work_dir))
```

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_update_qt_controller.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/update/qt_controller.py tests/test_update_qt_controller.py
git commit -m "feat: coordinate background updates"
```

---

### Task 6: GUI Dialogs and Main Window Integration

**Files:**
- Create: `src/ui/update_dialogs.py`
- Modify: `src/ui/main_window.py:1-28,2452-2456,2645-2653,2691-2763,5250-5262`
- Test: `tests/test_update_gui_flow.py`

**Interfaces:**
- Consumes: `UpdateController` signals and `ReleaseInfo`
- Produces: `UpdateAvailableDialog.release`, `UpdateAvailableDialog.accepted` for immediate update
- Produces: `UpdateProgressDialog.set_progress(done: int, total: int)` and `cancel_requested` signal
- Produces MainWindow methods: `_check_for_updates(manual=False)`, `_on_update_check_finished(release, manual)`, `_start_update_download(release)`, `_on_update_download_ready(archive, release)`

- [ ] **Step 1: Write GUI flow tests without showing real dialogs**

```python
# tests/test_update_gui_flow.py
import sys
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow
from src.update.release_client import ReleaseInfo


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


def test_startup_check_skips_already_notified_release():
    window = MainWindow.__new__(MainWindow)
    window.config = {"notified_update_version": "2.5.0"}
    window._show_update_available = Mock()
    release = ReleaseInfo("2.5.0", "notes", "https://github.com/page", "https://github.com/a.zip", "https://github.com/a.sha256")
    window._on_update_check_finished(release, False)
    window._show_update_available.assert_not_called()


def test_manual_check_shows_same_release_again():
    window = MainWindow.__new__(MainWindow)
    window.config = {"notified_update_version": "2.5.0"}
    window._show_update_available = Mock()
    release = ReleaseInfo("2.5.0", "notes", "https://github.com/page", "https://github.com/a.zip", "https://github.com/a.sha256")
    window._on_update_check_finished(release, True)
    window._show_update_available.assert_called_once_with(release)


def test_manual_check_without_release_reports_latest():
    window = MainWindow.__new__(MainWindow)
    with patch("src.ui.main_window.QMessageBox.information") as information:
        window._on_update_check_finished(None, True)
    information.assert_called_once()
```

- [ ] **Step 2: Run tests and confirm missing integration failure**

Run: `python -m pytest tests/test_update_gui_flow.py -v`

Expected: tests fail because `_on_update_check_finished` does not exist.

- [ ] **Step 3: Add focused update dialogs**

Create `src/ui/update_dialogs.py` with two classes:

```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QProgressBar, QPushButton, QTextBrowser, QVBoxLayout

from src.ui.styles import Styles
from src.update.release_client import ReleaseInfo


class UpdateAvailableDialog(QDialog):
    def __init__(self, release: ReleaseInfo, auto_update_supported: bool, parent=None):
        super().__init__(parent)
        self.release = release
        self.setWindowTitle("ぽえなび アップデート")
        self.setMinimumSize(480, 360)
        self.setStyleSheet(Styles.MAIN_WINDOW)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"新しいバージョン v{release.version} を利用できます。"))
        notes = QTextBrowser()
        notes.setPlainText(release.notes)
        layout.addWidget(notes)
        buttons = QDialogButtonBox()
        update = buttons.addButton("今すぐアップデート" if auto_update_supported else "リリースページを開く", QDialogButtonBox.AcceptRole)
        later = buttons.addButton("後で", QDialogButtonBox.RejectRole)
        update.clicked.connect(self.accept)
        later.clicked.connect(self.reject)
        layout.addWidget(buttons)


class UpdateProgressDialog(QDialog):
    cancel_requested = Signal()

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ぽえなび アップデート")
        self.setModal(True)
        layout = QVBoxLayout(self)
        self.label = QLabel(f"v{version} をダウンロードしています…")
        self.progress = QProgressBar()
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        layout.addWidget(self.label)
        layout.addWidget(self.progress)
        layout.addWidget(self.cancel_button)

    def set_progress(self, done: int, total: int):
        self.progress.setRange(0, total if total > 0 else 0)
        self.progress.setValue(done)
        self.label.setText(f"ダウンロード中: {done / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB" if total else f"ダウンロード中: {done / 1024 / 1024:.1f} MB")
```

- [ ] **Step 4: Replace the old MainWindow update implementation**

At module imports, remove `json`, `urllib.request` only if no other use remains, and add:

```python
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from src.ui.update_dialogs import UpdateAvailableDialog, UpdateProgressDialog
from src.update.qt_controller import UpdateController
```

In `MainWindow.__init__`, before the startup check:

```python
self.update_controller = UpdateController(self)
self.update_controller.check_finished.connect(self._on_update_check_finished)
self.update_controller.check_failed.connect(self._on_update_check_failed)
self.update_controller.download_progress.connect(self._on_update_download_progress)
self.update_controller.download_ready.connect(self._on_update_download_ready)
self.update_controller.download_failed.connect(self._on_update_download_failed)
self.update_controller.download_cancelled.connect(self._on_update_download_cancelled)
self._update_progress_dialog = None
self._check_for_updates(manual=False)
```

Delete `_update_signal`, the old nested-thread `_check_for_updates`, and `_show_update_dialog`. Add:

```python
def _check_for_updates(self, manual=False):
    self.update_controller.check(manual)

def _on_update_check_finished(self, release, manual):
    if release is None:
        if manual:
            QMessageBox.information(self, "アップデート", "最新バージョンです。")
        return
    if not manual and self.config.get("notified_update_version") == release.version:
        return
    self._show_update_available(release)

def _on_update_check_failed(self, message, manual):
    if manual:
        QMessageBox.warning(self, "アップデート", f"更新を確認できませんでした。\n{message}")

def _show_update_available(self, release):
    self.config["notified_update_version"] = release.version
    ConfigManager.save_config(self.config)
    supported = getattr(sys, "frozen", False) and sys.platform == "win32"
    dialog = UpdateAvailableDialog(release, supported, self)
    if not dialog.exec():
        return
    if not supported:
        QDesktopServices.openUrl(QUrl(release.page_url))
        return
    self._start_update_download(release)

def _start_update_download(self, release):
    self._update_progress_dialog = UpdateProgressDialog(release.version, self)
    self._update_progress_dialog.cancel_requested.connect(self.update_controller.cancel_download)
    self.update_controller.download(release)
    self._update_progress_dialog.show()

def _on_update_download_progress(self, done, total):
    if self._update_progress_dialog:
        self._update_progress_dialog.set_progress(done, total)

def _on_update_download_cancelled(self):
    if self._update_progress_dialog:
        self._update_progress_dialog.reject()
        self._update_progress_dialog = None

def _on_update_download_failed(self, message):
    self._on_update_download_cancelled()
    QMessageBox.warning(self, "アップデート", f"更新をダウンロードできませんでした。\n{message}")

def _on_update_download_ready(self, archive, release):
    if self._update_progress_dialog:
        self._update_progress_dialog.accept()
        self._update_progress_dialog = None
    answer = QMessageBox.question(
        self,
        "アップデートを適用",
        f"v{release.version} の検証が完了しました。\nぽえなびを終了して更新しますか？",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes,
    )
    if answer != QMessageBox.Yes:
        return
    try:
        self.update_controller.launch_updater(archive)
    except Exception as exc:
        QMessageBox.critical(self, "アップデート", str(exc))
        return
    QApplication.instance().quit()
```

Add the manual action between settings and the separator in `contextMenuEvent`:

```python
update_action = menu.addAction("アップデートを確認")
update_action.triggered.connect(lambda: self._check_for_updates(manual=True))
```

- [ ] **Step 5: Run GUI flow and existing startup tests**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_update_gui_flow.py tests/test_startup_selection_flow.py -v`

Expected: all tests pass without opening visible windows.

- [ ] **Step 6: Commit**

```powershell
git add src/ui/update_dialogs.py src/ui/main_window.py tests/test_update_gui_flow.py
git commit -m "feat: add GUI update workflow"
```

---

### Task 7: Reproducible Release Build and Tag Workflow

**Files:**
- Create: `scripts/build_release.ps1`
- Create: `.github/workflows/release.yml`
- Modify: `build_exe.bat:1-75`

**Interfaces:**
- Consumes: `src.version.APP_VERSION`, `updater_main.py`, `scripts/generate_update_manifest.py`
- Produces: `PoENavi.zip`, `PoENavi.zip.sha256`
- Produces: GitHub Release for `vX.Y.Z`

- [ ] **Step 1: Create a non-interactive release build script**

```powershell
# scripts/build_release.ps1
param([string]$Python = ".venv-build\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
if ($Python -eq ".venv-build\Scripts\python.exe" -and -not (Test-Path $Python)) { py -3 -m venv .venv-build }
& $Python -m pip install --upgrade pip setuptools wheel
& $Python -m pip install --upgrade -r requirements.txt pyinstaller pytest
Remove-Item -Recurse -Force build,dist -ErrorAction SilentlyContinue
& $Python -m PyInstaller --noconfirm --clean --noupx --onedir --windowed `
  --name PoENavi --icon icon.ico `
  --add-data "icon.ico;." --add-data "default_config.json;." `
  --add-data "guide_data.json;." --add-data "guide_data_poe2.json;." `
  --add-data "monster_levels.json;." --add-data "data;data" `
  --add-data "assets;assets" --add-data "maps;maps" `
  --hidden-import PySide6.QtWidgets --hidden-import PySide6.QtCore `
  --hidden-import PySide6.QtGui --hidden-import pynput `
  --hidden-import pynput.keyboard --hidden-import pynput.keyboard._win32 `
  --hidden-import keyboard main.py
& $Python -m PyInstaller --noconfirm --clean --noupx --onefile --windowed `
  --name PoENaviUpdater --distpath dist\PoENavi `
  --hidden-import PySide6.QtWidgets --hidden-import PySide6.QtCore `
  --hidden-import PySide6.QtGui updater_main.py
$version = & $Python -c "from src.version import APP_VERSION; print(APP_VERSION)"
& $Python scripts\generate_update_manifest.py dist\PoENavi $version
if (-not (Test-Path dist\PoENavi\PoENavi.exe)) { throw "PoENavi.exe was not built" }
if (-not (Test-Path dist\PoENavi\PoENaviUpdater.exe)) { throw "PoENaviUpdater.exe was not built" }
Remove-Item PoENavi.zip,PoENavi.zip.sha256 -ErrorAction SilentlyContinue
Compress-Archive -Path dist\PoENavi -DestinationPath PoENavi.zip
$hash = (Get-FileHash PoENavi.zip -Algorithm SHA256).Hash.ToLower()
Set-Content -Path PoENavi.zip.sha256 -Value "$hash  PoENavi.zip" -Encoding ascii
```

- [ ] **Step 2: Replace the local batch build with a wrapper**

```bat
@echo off
chcp 65001 >nul
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_release.ps1"
if errorlevel 1 goto :error
echo.
echo BUILD SUCCESS: PoENavi.zip and PoENavi.zip.sha256
pause
exit /b 0
:error
echo.
echo BUILD FAILED. Check errors above.
pause
exit /b 1
```

- [ ] **Step 3: Add the tag-triggered GitHub Actions workflow**

```yaml
# .github/workflows/release.yml
name: Release Windows App

on:
  push:
    tags:
      - "v[0-9]+.[0-9]+.[0-9]+"

permissions:
  contents: write

jobs:
  release:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install test dependencies
        run: python -m pip install -r requirements.txt pytest
      - name: Verify tag matches app version
        shell: pwsh
        run: |
          $version = python -c "from src.version import APP_VERSION; print(APP_VERSION)"
          if ($env:GITHUB_REF_NAME -ne "v$version") {
            throw "Tag $env:GITHUB_REF_NAME does not match APP_VERSION $version"
          }
      - name: Run tests
        env:
          QT_QPA_PLATFORM: offscreen
        run: python -m pytest -q
      - name: Build release assets
        shell: pwsh
        run: .\scripts\build_release.ps1 -Python python
      - name: Create GitHub Release
        shell: pwsh
        env:
          GH_TOKEN: ${{ github.token }}
        run: gh release create $env:GITHUB_REF_NAME PoENavi.zip PoENavi.zip.sha256 --verify-tag --generate-notes --title "PoENavi $env:GITHUB_REF_NAME"
```

- [ ] **Step 4: Validate scripts locally without publishing**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1`

Expected: exit code 0; `PoENavi.zip` and `PoENavi.zip.sha256` exist; the ZIP contains `PoENavi/PoENavi.exe`, `PoENavi/PoENaviUpdater.exe`, and `PoENavi/update-manifest.json`.

Run: `python -c "from pathlib import Path; from src.update.artifacts import parse_checksum, verify_sha256, validate_update_archive; p=Path('PoENavi.zip'); assert verify_sha256(p, parse_checksum(Path('PoENavi.zip.sha256').read_text())); validate_update_archive(p); print('release artifacts valid')"`

Expected: `release artifacts valid`.

- [ ] **Step 5: Commit**

```powershell
git add scripts/build_release.ps1 .github/workflows/release.yml build_exe.bat
git commit -m "ci: build releases from version tags"
```

---

### Task 8: Documentation, Regression Verification, and Windows Smoke Test

**Files:**
- Modify: `README.md:224-251`
- Modify: `README.md` contributor/release section near the end

**Interfaces:**
- Consumes: completed GUI update and tag release workflow
- Produces: user instructions and maintainer release checklist

- [ ] **Step 1: Update user-facing installation documentation**

Add after the exe installation steps:

```markdown
### アップデート

exe版は起動時にGitHub Releasesの安定版を確認します。新版の通知で「今すぐアップデート」を選ぶと、ダウンロードとSHA-256検証を行い、ぽえなびを終了してファイルを更新した後、自動で再起動します。

通知を閉じた後は、ぽえなびを右クリックして「アップデートを確認」を選ぶと再確認できます。ソースから実行している場合は、自動置換の代わりにReleaseページを案内します。
```

- [ ] **Step 2: Add the maintainer release procedure**

```markdown
### リリース手順

1. `src/version.py` の `APP_VERSION` を次の `X.Y.Z` に更新する。
2. `python -m pytest -q` を実行する。
3. バージョン更新を `main` へマージする。
4. 同じコミットへ `vX.Y.Z` タグを作成してpushする。
5. `Release Windows App` workflowが成功し、`PoENavi.zip` と `PoENavi.zip.sha256` がReleaseへ添付されたことを確認する。

タグと `APP_VERSION` が一致しない場合、workflowはReleaseを作成せず失敗します。
```

- [ ] **Step 3: Run the full automated test suite**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`

Expected: exit code 0 and zero failed tests.

- [ ] **Step 4: Run source-mode smoke test**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -c "from PySide6.QtWidgets import QApplication; from src.ui.main_window import MainWindow; app=QApplication([]); window=MainWindow(); print(type(window.update_controller).__name__); window.close()"`

Expected: prints `UpdateController` and exits without an exception.

- [ ] **Step 5: Run built-app Windows smoke test**

Run `PoENavi.exe` from the extracted `PoENavi.zip`, then verify manually:

1. Right-click → `アップデートを確認` opens a result dialog.
2. A mocked/newer test Release shows version and release notes.
3. Download cancellation leaves the current app running.
4. A checksum mismatch does not close the app.
5. A valid test release replaces the app, preserves config and edited guide data, and restarts.
6. A forced launch failure restores the backup and leaves its location in the error message.

Expected: all six checks pass. Record the tested Windows version, source version, target version, and result in the PR description.

- [ ] **Step 6: Confirm only intended changes remain**

Run: `git status --short; git diff --check; git log --oneline --decorate origin/main..HEAD`

Expected: no uncommitted generated `build/`, `dist/`, `PoENavi.zip`, or checksum files; no whitespace errors; only the design, plan, and update feature commits appear.

- [ ] **Step 7: Commit documentation**

```powershell
git add README.md
git commit -m "docs: explain automatic updates and releases"
```

---

## Final Verification Gate

- [ ] Run `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q` and confirm zero failures.
- [ ] Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1` and confirm exit code 0.
- [ ] Validate `PoENavi.zip` with `validate_update_archive` and the generated SHA-256 file.
- [ ] Inspect `git diff origin/main...HEAD --stat` and `git status --short`.
- [ ] Do not push or open a PR until the user explicitly requests publication.
