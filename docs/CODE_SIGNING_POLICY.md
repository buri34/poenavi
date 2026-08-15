# Code signing policy

Free code signing provided by [SignPath.io](https://signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

## Project

- Project: PoENavi
- Source repository: <https://github.com/buri34/poenavi>
- Release page: <https://github.com/buri34/poenavi/releases>
- License: MIT

Official releases are built from tagged source revisions by the repository's GitHub Actions workflow on GitHub-hosted Windows runners.

## Team roles

- Committer and author: [Buri_Isono (`buri34`)](https://github.com/buri34)
- Reviewer for contributions from non-committers: [Buri_Isono (`buri34`)](https://github.com/buri34)
- Approver for signing requests: [Buri_Isono (`buri34`)](https://github.com/buri34)

All members in these roles must use multi-factor authentication for GitHub and SignPath access.

## Signed artifacts

The project signs only executables produced from PoENavi's own source code:

- `PoENavi.exe`
- `PoENaviUpdater.exe`

The `ProductName` metadata is fixed to `PoENavi`. `ProductVersion` and `FileVersion` are generated from `src/version.py` and must match the release tag. Third-party runtime DLLs and Python extension modules included by PyInstaller are not signed as PoENavi project binaries.

## Build and approval process

1. Changes are committed to the public source repository.
2. A release tag must match `APP_VERSION` in `src/version.py`.
3. GitHub Actions runs the test suite on a GitHub-hosted Windows runner.
4. The workflow builds unsigned artifacts from the tagged revision with pinned runtime and build dependencies.
5. The unsigned artifact is submitted to SignPath from the GitHub workflow.
6. The designated approver manually reviews and approves each signing request.
7. The workflow verifies the returned signatures and required version metadata before packaging the release ZIP.
8. The release ZIP and its SHA-256 checksum are published on GitHub Releases.

The project does not permit signing local, manually uploaded, or third-party binaries with its SignPath configuration.

## Privacy policy

PoENavi's data processing and network behavior are documented in the [Privacy policy](../PRIVACY.md).

## Reporting concerns

Security, signing, or release-integrity concerns can be reported through [GitHub Issues](https://github.com/buri34/poenavi/issues). Sensitive vulnerability reports should not include secrets or private user data in a public issue; request a private contact channel first.
