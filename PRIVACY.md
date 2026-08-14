# Privacy policy

Last updated: 2026-08-14

PoENavi is a local desktop application. It does not include telemetry, advertising, user accounts, or analytics, and the project operator does not run a server that receives PoENavi user data.

## Data processed on the user's computer

Depending on the enabled features, PoENavi processes the following information locally:

- Path of Exile `Client.txt` entries used to detect area, level, and campaign progress
- item text copied to the Windows clipboard when the user requests a price search
- PoENavi settings, notes, guide edits, timer records, window positions, and cached prices
- the Path of Exile process name and window position used to identify the target game window

These records are stored under `%APPDATA%\PoENavi\` or remain in the user's selected Path of Exile log location. PoENavi does not transmit `Client.txt`, personal notes, timer records, or Path of Exile credentials to the project operator.

## Network connections

PoENavi connects only for the functions described below:

- **GitHub Releases**: checks for stable PoENavi updates at startup and, after user confirmation, downloads the release archive and SHA-256 checksum.
- **Path of Exile official Trade API**: after the user requests a price search, sends item names, modifiers, numeric filters, league, and related search criteria.
- **poe.ninja**: after a price-related operation, obtains public currency and item reference prices.
- **Path of Exile official CDN and PoE Wiki image endpoints**: obtains public item images used in search results.
- **PoELab and external information pages**: opens a page in the user's default browser only after the user selects the corresponding action.

As with ordinary web requests, these external services can receive the user's IP address, request time, user-agent information, and the request data described above. Their processing is governed by their own privacy policies and terms.

## Input and system interaction

PoENavi can monitor configured global hotkeys. In response to a user action, it can send key input for copying item text, pasting search text, or sending a configured Path of Exile chat command. If the user enables and invokes the logout feature, PoENavi deletes the Path of Exile client's matching TCP connection through the Windows API.

PoENavi does not read or modify game memory, inject code into the game, intercept or alter network packets, collect Path of Exile authentication data, or perform autonomous gameplay.

## Updates and system changes

PoENavi is distributed as a portable ZIP and does not install a Windows service. An update is applied only after the user accepts the update prompt. The updater verifies the downloaded SHA-256 checksum, replaces files in the PoENavi application folder, and preserves a rollback copy while confirming that the updated application starts.

## Deletion and uninstallation

Delete the extracted PoENavi application folder to remove the program. To remove local settings, notes, caches, and records as well, delete `%APPDATA%\PoENavi\`. Users should back up any records they want to keep before deletion.

## Contact

Privacy questions can be submitted through [GitHub Issues](https://github.com/buri34/poenavi/issues). Do not include account credentials, private log content, or other sensitive information in a public issue.
