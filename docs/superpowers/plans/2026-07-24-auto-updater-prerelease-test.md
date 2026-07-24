# Auto-Updater Prerelease Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a hidden v2.6.3 prerelease that an existing packaged v2.6.2 installation can discover, download, apply, and restart through the real auto-updater.

**Architecture:** Keep the updater unchanged and use its existing `POENAVI_UPDATE_TEST_TAG` opt-in channel. Make the one live Trade API-dependent UI test deterministic, bump the application version, tag a workflow commit that creates a prerelease, then immediately restore the normal stable-release workflow on `main` after the prerelease exists.

**Tech Stack:** Python 3.12, pytest/pytest-qt, PySide6, PowerShell, GitHub Actions, GitHub CLI on the Actions runner.

## Global Constraints

- Preserve the pending localized visit-toggle tooltip and gem acquisition badge fix.
- The release version and tag are exactly `2.6.3` and `v2.6.3`.
- Do not change Poetrieve production behavior or broadly disable network-backed tests.
- Normal updater launches must not discover v2.6.3 before manual validation.
- Never force-move the v2.6.3 tag after publication.

---

### Task 1: Make the cluster-jewel UI test deterministic

**Files:**
- Modify: `tests/test_poetore_ui.py:1765`

**Interfaces:**
- Consumes: `src.poetore.trade._trade_stat_entries() -> tuple[dict, ...]`
- Produces: a UI test that supplies the two representative enchant stat entries without contacting the live Trade API

- [ ] **Step 1: Reproduce the current failure**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest tests/test_poetore_ui.py::test_cluster_special_chips_do_not_duplicate_passive_or_enchant_filters -q
```

Expected: FAIL because `cluster_enchant_chip.text()` does not contain `範囲ダメージが10%増加する` when the current live stat dataset no longer resolves that modifier.

- [ ] **Step 2: Add a local Trade API fixture and patch the resolver dependency**

Inside `test_cluster_special_chips_do_not_duplicate_passive_or_enchant_filters`, define:

```python
entries = (
    {
        "id": "enchant.stat_3086156145",
        "text": "パッシブスキルを#個追加する",
        "type": "enchant",
    },
    {
        "id": "enchant.stat_3948993189",
        "text": "追加される通常パッシブスキルは付与: 範囲ダメージが#%増加する",
        "type": "enchant",
    },
)
```

Wrap `_configure_special_filter_chips`, `_selected_special_chip_filters`, and the direct `resolve_trade_stat_filters` assertion in:

```python
with patch("src.poetore.trade._trade_stat_entries", return_value=entries):
    ...
```

- [ ] **Step 3: Verify the focused test**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest tests/test_poetore_ui.py::test_cluster_special_chips_do_not_duplicate_passive_or_enchant_filters -q
```

Expected: `1 passed`.

- [ ] **Step 4: Commit the deterministic test**

```powershell
git add -- tests/test_poetore_ui.py
git commit -m "test: stabilize cluster jewel UI coverage"
```

### Task 2: Prepare the v2.6.3 prerelease commit

**Files:**
- Modify: `src/version.py:1`
- Modify: `.github/workflows/release.yml:49`

**Interfaces:**
- Consumes: release workflow tag/version equality check and packaged updater semantic-version comparison
- Produces: `APP_VERSION == "2.6.3"` and a tagged workflow that passes `--prerelease` to `gh release create`

- [ ] **Step 1: Bump the application version**

Change:

```python
APP_VERSION = "2.6.2"
```

to:

```python
APP_VERSION = "2.6.3"
```

- [ ] **Step 2: Make the tagged release a prerelease**

Add this argument to the existing `gh release create` command:

```powershell
--prerelease
```

- [ ] **Step 3: Run release verification**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest -q
python scripts/validate_locales.py
git diff --check
```

Expected: the full pytest suite and locale validator pass, and `git diff --check` prints no errors.

- [ ] **Step 4: Commit the prerelease preparation**

```powershell
git add -- src/version.py .github/workflows/release.yml
git commit -m "chore: prepare v2.6.3 prerelease"
```

### Task 3: Push, tag, and monitor the build

**Files:**
- No source-file changes

**Interfaces:**
- Consumes: `main` at the verified v2.6.3 prerelease commit
- Produces: remote annotated tag `v2.6.3` and a GitHub prerelease containing `PoENavi.zip` and `PoENavi.zip.sha256`

- [ ] **Step 1: Confirm the release target**

Run:

```powershell
git status --short
git log -1 --oneline
git ls-remote --tags origin refs/tags/v2.6.3
```

Expected: only the pre-existing untracked task-artifact directories remain, the release-preparation commit is at `HEAD`, and the remote tag query is empty.

- [ ] **Step 2: Push main and the annotated tag**

Run:

```powershell
git push origin main
git tag -a v2.6.3 -m "PoENavi v2.6.3"
git push origin v2.6.3
```

Expected: both pushes succeed without force.

- [ ] **Step 3: Monitor the GitHub Actions release workflow**

Poll the repository Actions API until the run for `head_branch == "v2.6.3"` reaches `status == "completed"`.

Expected: `conclusion == "success"`.

- [ ] **Step 4: Verify release safety and assets**

Inspect `https://api.github.com/repos/fuubox/poenavi-localisation/releases/tags/v2.6.3`.

Expected:

```text
prerelease: true
draft: false
assets: PoENavi.zip, PoENavi.zip.sha256
```

### Task 4: Restore the stable release workflow

**Files:**
- Modify: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: the already published v2.6.3 prerelease and immutable v2.6.3 tag
- Produces: `main` configured for ordinary stable releases again

- [ ] **Step 1: Remove only the temporary flag**

Delete:

```powershell
--prerelease
```

from `gh release create`; leave the v2.6.3 tag untouched.

- [ ] **Step 2: Verify and commit cleanup**

Run:

```powershell
git diff --check
git diff -- .github/workflows/release.yml
git add -- .github/workflows/release.yml
git commit -m "chore: restore stable release workflow"
git push origin main
```

Expected: the diff removes exactly one argument, then the cleanup commit pushes successfully.

### Task 5: Run the manual packaged updater test

**Files:**
- No repository changes

**Interfaces:**
- Consumes: an extracted fork v2.6.2 Windows release and the v2.6.3 GitHub prerelease
- Produces: a manual pass/fail result for the full updater handoff

- [ ] **Step 1: Launch the old packaged application with the opt-in tag**

From the extracted v2.6.2 directory, run:

```powershell
$env:POENAVI_UPDATE_TEST_TAG="v2.6.3"
.\PoENavi.exe
```

- [ ] **Step 2: Accept and verify the update**

Confirm the v2.6.3 prompt appears, the download and checksum succeed, the app exits and restarts, the UI reports v2.6.3, user data remains intact, the visit-toggle tooltip appears, and English gem acquisition badges display `Quest` / `Buy`.

- [ ] **Step 3: Promote only after success**

If every check passes, edit the existing v2.6.3 GitHub release to clear its prerelease status and mark it latest. If any check fails, leave v2.6.3 as a prerelease and keep v2.6.2 as the latest stable release.
