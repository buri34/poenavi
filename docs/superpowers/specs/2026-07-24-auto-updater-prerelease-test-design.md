# Auto-Updater Prerelease Test Design

## Goal

Exercise the complete Windows updater path from the fork's packaged v2.6.2
release to a packaged v2.6.3 release without exposing an untested update to
normal users.

## Release Preparation

The v2.6.3 release includes the pending localized visit-toggle tooltip and gem
acquisition badge fix. Update `APP_VERSION` to `2.6.3`.

The release workflow currently runs the entire test suite before building. Its
only known failure is a Poetrieve UI test whose expected cluster-jewel stat is
resolved from the live Trade API. Make that test deterministic by supplying
the representative Trade API stat entry inside the test. Do not change
Poetrieve production behavior or broadly disable network-backed tests.

For the v2.6.3 tag only, add `--prerelease` to `gh release create`. The tag must
remain the normal semantic version `v2.6.3`, because both the workflow and the
updater require `vMAJOR.MINOR.PATCH`.

## Build and Channel Safety

Push `main`, create annotated tag `v2.6.3`, and push the tag. The release
workflow must:

1. verify the tag matches `APP_VERSION`;
2. pass the test suite;
3. build `PoENavi.zip` and `PoENavi.zip.sha256`;
4. pin `update_channel.json` to `fuubox/poenavi-localisation`; and
5. publish v2.6.3 as a prerelease.

After the prerelease is available, remove the temporary `--prerelease` workflow
flag from `main` and push that cleanup. The v2.6.3 tag remains on the tested
release commit.

## Manual End-to-End Test

From the user's existing extracted v2.6.2 release directory, launch:

```powershell
$env:POENAVI_UPDATE_TEST_TAG="v2.6.3"
.\PoENavi.exe
```

The packaged v2.6.2 updater requests the named prerelease only for this
explicitly opted-in process. Normal launches continue to use GitHub's latest
stable release and therefore do not see v2.6.3 during testing.

Accept the update and verify:

- the v2.6.3 prompt appears;
- the archive downloads and its SHA-256 checksum validates;
- PoENavi exits, applies the archive, and restarts;
- the restarted UI reports v2.6.3;
- settings, notes, presets, imported data, and other user data remain intact;
- the visit-toggle tooltip appears; and
- English gem acquisition badges show `Quest` / `Buy`.

## Promotion and Failure Handling

If the manual test succeeds, promote the existing v2.6.3 GitHub prerelease to
the latest stable release without rebuilding or moving the tag.

If it fails, leave v2.6.3 as a prerelease, retain the v2.6.2 stable release,
and diagnose from the updater error before publishing another version. Never
force-move the v2.6.3 tag after users may have downloaded it.
