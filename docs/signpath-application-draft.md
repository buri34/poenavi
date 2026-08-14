# SignPath Foundation application draft

This document is an internal submission draft. Do not publish contact details or submit the application until the repository readiness changes have been reviewed.

## Project name

PoENavi

## Repository

<https://github.com/buri34/poenavi>

## Release page

<https://github.com/buri34/poenavi/releases>

## License

MIT License

## Project description

PoENavi is a free and open-source Windows desktop companion for Path of Exile 1 and Path of Exile 2. It reads the game's local `Client.txt` log to display campaign guidance, map references, experience guidance, and an RTA timer. Its PoE1 mode also provides user-initiated item price searches using the official Path of Exile Trade API and public poe.ninja data.

PoENavi is an independent community project and is not affiliated with or endorsed by Grinding Gear Games. It does not read or modify game memory, inject code, modify game files, intercept network packets, collect account credentials, or automate gameplay.

## Why code signing is requested

PoENavi is distributed as a PyInstaller-built portable Windows application. The unsigned executables can show an unknown-publisher SmartScreen warning and can be subject to antivirus false positives. We want authenticated releases whose signatures are technically linked to the public source repository and GitHub-hosted build workflow.

## Current release format

- Portable `PoENavi.zip` published on GitHub Releases
- `PoENavi.exe`: PyInstaller onedir GUI application
- `PoENaviUpdater.exe`: PyInstaller onefile updater
- SHA-256 checksum published next to the ZIP
- Existing released form: <https://github.com/buri34/poenavi/releases/tag/v3.3.8>

## Proposed trusted build and signing flow

1. A `vX.Y.Z` Git tag triggers the public GitHub Actions release workflow.
2. The workflow verifies that the tag matches `src/version.py`.
3. Tests run on a GitHub-hosted Windows runner.
4. Runtime and build dependencies are installed at pinned versions.
5. PyInstaller builds both PoENavi executables with enforced ProductName and ProductVersion metadata.
6. The GitHub workflow submits the unsigned artifact to SignPath.
7. The project approver manually approves every signing request.
8. Only `PoENavi.exe` and `PoENaviUpdater.exe` are signed; upstream runtime DLLs are not signed under the PoENavi project.
9. The workflow verifies signatures and metadata, creates the ZIP and checksum, and publishes the GitHub Release.

## Maintainer and roles

The repository is owned and maintained by Buri_Isono (`buri34`). The same maintainer is the project committer, reviewer for outside contributions, and signing-request approver. Multi-factor authentication is enabled for the GitHub account and will also be enabled for SignPath.

## Privacy and system behavior

The project has no telemetry, advertising, analytics, user accounts, or operator-controlled data collection server. Network connections and locally processed data are documented in the repository privacy policy. Updates require user confirmation and are checksum-verified. The application is portable and can be uninstalled by deleting its application folder; local user data can separately be removed from `%APPDATA%\PoENavi\`.

PoENavi monitors only user-configured global hotkeys. The hotkeys initiate visible user actions such as copying an item's text, opening a price search, or sending a user-configured in-game chat command. PoENavi does not record general keystrokes or transmit keyboard input.

PoENavi also offers an optional, user-initiated logout hotkey. When invoked, it asks Windows to delete the Path of Exile process's matching TCP connection. This is a local connection-close operation; it does not inspect packet contents, intercept traffic, scan other systems, bypass authentication, or exploit a vulnerability.

## Third-party components and game data disclosure

PoENavi's own source code is MIT licensed. The PyInstaller package contains upstream open-source runtime components such as Python, PySide6/Qt, pynput, urllib3, and OpenSSL; these remain upstream binaries and are not signed as PoENavi project binaries. Their license families and upstream sources are documented in the distribution, and the release process is being updated to include all complete license texts required by those dependencies before signed releases are published.

The application also contains Path of Exile names, public game metadata, and user-created map-reference images. Rights in Path of Exile and related game data belong to Grinding Gear Games. These data files are not executable code and are not signed as project binaries. We would appreciate confirmation that this separation is acceptable for a SignPath Foundation OSS subscription.

## Requested signed files

- `PoENavi.exe`
- `PoENaviUpdater.exe`

## Likely reviewer follow-up: reproducible build

The release is built in a public GitHub Actions workflow on a GitHub-hosted Windows runner. Python and Python-package versions are pinned, the release tag is checked against the application version, and the source revision and workflow logs remain publicly inspectable. The two project executables are produced directly by PyInstaller from `main.py` and `src/updater_main.py`. No prebuilt PoENavi executable is taken from the repository or a maintainer machine.

PyInstaller bundles upstream runtime libraries into the portable application directory. These dependencies and their licenses are listed in `THIRD_PARTY_NOTICES.md`; they are not submitted for signing as binaries authored by PoENavi.

## Remaining steps before submission

- Publish the code-signing policy, privacy policy, pinned build dependencies, and Windows version metadata changes on the public repository.
- Run the updated public Windows workflow and confirm both EXEs contain `ProductName=PoENavi` and the expected version.
- Confirm the release archive includes the required third-party license materials.
- Enter the maintainer contact email in the SignPath Foundation form.
- Submit this disclosure and wait for SignPath Foundation's eligibility decision before adding signing credentials or publishing a signed release.

## Contact

Enter the maintainer's contact email directly in the SignPath application form. Do not commit it to this document unless the maintainer explicitly chooses to publish it.
