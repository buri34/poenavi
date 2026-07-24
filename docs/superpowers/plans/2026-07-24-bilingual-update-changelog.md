# Bilingual Update Changelog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish useful bilingual v2.6.3 release notes and make future updater dialogs render curated Markdown with working external links.

**Architecture:** Keep the GitHub release body as the updater's single notes payload. Store that body in a versioned repository file, require the matching file in the tag workflow, render it through Qt's built-in Markdown support, and update the existing prerelease body without rebuilding or moving its tag.

**Tech Stack:** Python 3.12, PySide6 `QTextBrowser`, pytest/pytest-qt, PowerShell, GitHub Actions, GitHub Releases.

## Global Constraints

- Release-note files live at `docs/releases/vMAJOR.MINOR.PATCH.md`.
- Release notes are bilingual with English first, Japanese second, and a full-changelog URL last.
- Keep `ReleaseInfo.notes` as the raw GitHub release-body string.
- Do not add an HTML fetch, Markdown dependency, or custom link handler.
- Do not rebuild or move the existing v2.6.3 tag.
- Preserve v2.6.3 as a prerelease with `PoENavi.zip` and `PoENavi.zip.sha256` attached.

---

### Task 1: Render updater release notes as Markdown

**Files:**
- Create: `tests/test_update_dialogs.py`
- Modify: `src/ui/update_dialogs.py:37-39`

**Interfaces:**
- Consumes: `ReleaseInfo.notes: str`
- Produces: an `UpdateAvailableDialog` whose `QTextBrowser` renders Markdown and opens external links

- [ ] **Step 1: Write the failing Qt test**

Create `tests/test_update_dialogs.py`:

```python
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QTextBrowser

from src.ui.update_dialogs import UpdateAvailableDialog
from src.update.release_client import ReleaseInfo


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_update_notes_render_markdown_with_external_links(qapp):
    release = ReleaseInfo(
        "2.6.3",
        "**Release notes**\n\n- Fixed labels\n\n"
        "https://github.com/fuubox/poenavi-localisation/releases/tag/v2.6.3",
        "https://github.com/fuubox/poenavi-localisation/releases/tag/v2.6.3",
        "https://github.com/fuubox/poenavi-localisation/PoENavi.zip",
        "https://github.com/fuubox/poenavi-localisation/PoENavi.zip.sha256",
    )
    dialog = UpdateAvailableDialog(release, auto_update_supported=True)
    try:
        notes = dialog.findChild(QTextBrowser)

        assert notes is not None
        assert "**Release notes**" not in notes.toPlainText()
        assert "Release notes" in notes.toPlainText()
        assert "<a href=" in notes.toHtml()
        assert notes.openExternalLinks()
    finally:
        dialog.close()
```

- [ ] **Step 2: Run the test and verify the red state**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest tests/test_update_dialogs.py -q
```

Expected: FAIL because the current dialog uses `setPlainText()` and does not enable external links.

- [ ] **Step 3: Implement the minimal renderer change**

Replace:

```python
notes = QTextBrowser()
notes.setPlainText(release.notes)
layout.addWidget(notes)
```

with:

```python
notes = QTextBrowser()
notes.setMarkdown(release.notes)
notes.setOpenExternalLinks(True)
layout.addWidget(notes)
```

- [ ] **Step 4: Verify the green state**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest tests/test_update_dialogs.py tests/test_update_gui_flow.py tests/test_release_client.py -q
```

Expected: all updater dialog, flow, and release-client tests pass.

- [ ] **Step 5: Commit the renderer**

```powershell
git add -- src/ui/update_dialogs.py tests/test_update_dialogs.py
git commit -m "fix: render updater changelog markdown"
```

### Task 2: Require curated bilingual release notes

**Files:**
- Create: `docs/releases/v2.6.3.md`
- Modify: `tests/test_release_channel.py`
- Modify: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: tag name from `$env:GITHUB_REF_NAME`
- Produces: `docs/releases/$env:GITHUB_REF_NAME.md` as the required `gh release create --notes-file` input

- [ ] **Step 1: Write the failing workflow test**

Append to `tests/test_release_channel.py`:

```python
def test_release_workflow_requires_curated_versioned_notes():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    notes = root / "docs" / "releases" / "v2.6.3.md"

    assert notes.is_file()
    assert '$notes = "docs/releases/$env:GITHUB_REF_NAME.md"' in workflow
    assert "Test-Path -LiteralPath $notes -PathType Leaf" in workflow
    assert '--notes-file "docs/releases/$env:GITHUB_REF_NAME.md"' in workflow
    assert "--generate-notes" not in workflow
```

- [ ] **Step 2: Run the test and verify the red state**

Run:

```powershell
python -m pytest tests/test_release_channel.py::test_release_workflow_requires_curated_versioned_notes -q
```

Expected: FAIL because `docs/releases/v2.6.3.md` does not exist and the workflow still uses `--generate-notes`.

- [ ] **Step 3: Add the exact bilingual v2.6.3 notes**

Create `docs/releases/v2.6.3.md` with:

```markdown
# English

## What's changed

- Added a tooltip explaining the Automatic / First time / Second time guide toggle.
- Fixed Japanese acquisition badges appearing beside gems in the English interface. They now display Quest or Buy.

## Testing

- This prerelease is being used to validate the complete v2.6.2 to v2.6.3 automatic-update flow.

# 日本語

## 変更内容

- ガイドの「自動 / 1回目 / 2回目」切り替えの動作を説明するツールチップを追加しました。
- 英語インターフェースのジェム入手情報に日本語のバッジが表示される問題を修正しました。英語では Quest または Buy と表示されます。

## テスト

- このプレリリースは、v2.6.2 から v2.6.3 への自動更新フロー全体を検証するために使用しています。

Full changelog / 完全な変更履歴:
https://github.com/fuubox/poenavi-localisation/compare/v2.6.2...v2.6.3
```

- [ ] **Step 4: Enforce the notes file before release builds**

After the tag/version check in `.github/workflows/release.yml`, add:

```yaml
      - name: Verify release notes exist
        shell: pwsh
        run: |
          $notes = "docs/releases/$env:GITHUB_REF_NAME.md"
          if (-not (Test-Path -LiteralPath $notes -PathType Leaf)) {
            throw "Missing release notes: $notes"
          }
```

In `gh release create`, replace:

```powershell
--verify-tag --generate-notes
```

with:

```powershell
--verify-tag --notes-file "docs/releases/$env:GITHUB_REF_NAME.md"
```

- [ ] **Step 5: Verify the workflow contract**

Run:

```powershell
python -m pytest tests/test_release_channel.py -q
git diff --check
```

Expected: all release-channel tests pass and the diff check reports no errors.

- [ ] **Step 6: Commit the curated-notes workflow**

```powershell
git add -- .github/workflows/release.yml docs/releases/v2.6.3.md tests/test_release_channel.py
git commit -m "ci: require curated bilingual release notes"
```

### Task 3: Verify and publish the repository changes

**Files:**
- No additional source changes

**Interfaces:**
- Consumes: Tasks 1 and 2
- Produces: a verified and pushed `main` containing Markdown rendering and curated-note enforcement

- [ ] **Step 1: Run the complete verification gate**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest -q
python scripts/validate_locales.py
git diff --check
```

Expected: the full test suite, locale validation, and diff check pass.

- [ ] **Step 2: Audit repository state**

Run:

```powershell
git status --short
git log -4 --oneline
git diff v2.6.3..HEAD -- src/ui/update_dialogs.py .github/workflows/release.yml docs/releases/v2.6.3.md tests/test_update_dialogs.py tests/test_release_channel.py
```

Expected: only the pre-existing `.test-tmp/` and `plans/` directories remain untracked, and the scoped diff matches Tasks 1 and 2.

- [ ] **Step 3: Push main**

Run:

```powershell
git push origin main
```

Expected: `main` pushes without force; do not move or recreate `v2.6.3`.

### Task 4: Update the existing GitHub prerelease

**Files:**
- Source: `docs/releases/v2.6.3.md`
- External target: GitHub release `v2.6.3`

**Interfaces:**
- Consumes: the exact UTF-8 contents of `docs/releases/v2.6.3.md`
- Produces: the same body on the existing GitHub prerelease without changing its tag or assets

- [ ] **Step 1: Open the authenticated GitHub release editor**

Open:

```text
https://github.com/fuubox/poenavi-localisation/releases/edit/v2.6.3
```

Use the existing signed-in browser session. Do not create another release.

- [ ] **Step 2: Replace only the release body**

Set the release description to the exact contents of
`docs/releases/v2.6.3.md`. Keep:

```text
Tag: v2.6.3
Prerelease: enabled
Assets: PoENavi.zip, PoENavi.zip.sha256
```

Save the existing release.

- [ ] **Step 3: Verify the public release object**

Query:

```text
https://api.github.com/repos/fuubox/poenavi-localisation/releases/tags/v2.6.3
```

Verify:

```text
body == docs/releases/v2.6.3.md
prerelease == true
draft == false
assets == PoENavi.zip, PoENavi.zip.sha256
```

- [ ] **Step 4: Reopen the v2.6.2 updater test**

Close the current dialog and application, then relaunch from the extracted
v2.6.2 directory:

```powershell
$env:POENAVI_UPDATE_TEST_TAG="v2.6.3"
.\PoENavi.exe
```

Expected: the existing plain-text dialog displays the full bilingual notes.
The next packaged release will render the same source as formatted Markdown
with clickable links.
