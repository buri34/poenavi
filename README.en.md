# PoENavi

[日本語](README.md) | [English](README.en.md)

PoENavi is a lightweight leveling guide and timer for Path of Exile 1 and
Path of Exile 2. It watches the game’s `Client.txt` log, identifies area
changes, and displays guides, map images, and an RTA timer.

> This product is not affiliated with or endorsed by Grinding Gear Games in
> any way.

## Features

- PoE1 and PoE2 area guides with objectives, layout information, tips, and
  basic direction arrows.
- Map image thumbnails with click-to-zoom and keyboard navigation.
- Mini Navi overlay for PoE1, including quests, bosses, waypoints, portals,
  notes, and experience-level advice.
- Automatic area detection from the PoE `Client.txt` log, including Japanese
  and English client output.
- RTA timer with automatic Act/lap transitions, manual controls, and saved
  timer state.
- Gem acquisition tracking from imported Path of Building data. Search text
  remains canonical English so it can be pasted into the PoE search field.
- Poetrieve price checking for PoE1 items through the official Trade API,
  with optional poe.ninja reference prices.
- Editable Japanese and English guide datasets. User notes, presets, imported
  PoB data, and run history remain user-owned content.

## Installation

Download the latest Windows release, extract `PoENavi.zip`, and launch
`PoENavi.exe`. On the first run, choose 日本語 or English before the other
startup dialogs. Existing installations remain Japanese unless a language is
selected in Settings. Language changes take effect after restarting PoENavi.

The application needs access to the PoE `Client.txt` file. Configure the log
path in Settings if it is not detected automatically.

## Configuration and controls

Open Settings from the gear button or the tray/menu action. Configure PoE1 or
PoE2, the client log paths, hotkeys, guide detail, timer size, overlays,
window behavior, maps, routes, and language there.

The default hotkeys are:

- `F1`: start/stop timer
- `F2`: reset timer
- `F3`: next Act/lap
- `F4`: undo lap
- `F5`: log out
- `F6`: toggle click-through
- `F11`: `/hideout`
- `F12`: `/monastery`
- `Alt+D`: Poetrieve price check (PoE1)

### PoE1: Poetrieve price checking

With PoENavi running in PoE1 mode, hover over an item in your stash or
inventory and press `Alt+D`. Poetrieve captures the item's normal and detailed
copy text, then opens a price-check window where you can review the parsed
item, modifiers, league, listing age, currency, and other search filters.

Searches use the official Path of Exile Trade API, with poe.ninja prices shown
as an additional reference where available. Poetrieve reads copied item text;
it does not connect to the game client or read game memory. The window leaves
Path of Exile focused after a capture, so you can move to another item and
press `Alt+D` again. Click inside Poetrieve when you want to edit its filters.
The hotkey can be changed or cleared under **Settings → Hotkeys → Poetrieve
price check**.

> [!NOTE]
> - Poetrieve is available only for PoE1.
> - Searches require network access to the official Trade API; poe.ninja
>   reference prices also require access to poe.ninja.
> - Valdo's Puzzle Box reward conditions, Inscribed Ultimatum challenge and
>   reward conditions, and unidentified Unique candidate selection are not
>   supported in this release. Poetrieve explains unsupported conditions in
>   the window and omits them where a useful search can still be made.

## Guide and map data

The official datasets are `guide_data.json`, `guide_data_poe2.json`,
`guide_data_en.json`, and `guide_data_poe2_en.json`. Japanese filenames and
the existing Japanese map folders are intentionally preserved for
compatibility. English display names come from the stable zone master data;
map lookup continues to use the Japanese asset folders.

Guide edits are saved only to the currently selected locale’s file. The
application keeps zone IDs, route keys, visit variants, flags, mini-Navi
tokens, and progression logic locale-neutral.

## Development

```powershell
python -m pip install -r requirements.txt pytest
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest -q
python scripts/validate_locales.py
```

For localization architecture, translation maintenance, validation, and
upstream review guidance, see [Localization Development](docs/localization.md).

Build a Windows release with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1 -Python python
```

The build creates `PoENavi.zip` and `PoENavi.zip.sha256` and packages both
locale catalogs plus all four guide datasets.

## Disclaimer

Path of Exile and its assets are property of Grinding Gear Games. PoENavi is
an independent community tool and is not affiliated with, endorsed by, or
approved by Grinding Gear Games.

## License and credits

MIT License — see [LICENSE](LICENSE).

- [Path of Exile](https://www.pathofexile.com/) by Grinding Gear Games
- Built with ❤️ by [Buri](https://github.com/buri34)
- Poetrieve data sources and third-party licenses are documented in
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Support

- [OFUSE](https://ofuse.me/48eca107)
- [Ko-fi](https://ko-fi.com/buri8857)

## Feature details

### Guides and area detection

PoENavi watches `Client.txt` and recognizes both Japanese and English area
messages. The detected area is resolved by its stable ID, so the client
language and PoENavi display language can be chosen independently. The guide
view supports objectives, route-specific visits, flag-specific branches,
summaries, layout notes, direction arrows, and level advice.

![Main guide window](docs/screenshot1.png)

### Mini Navi overlay

The PoE1 Mini Navi can stay above the game while the main window is minimized.
It shows short quest and boss steps, town/waypoint/portal markers, notes, and
the current experience penalty state.

![Mini Navi overlay](docs/screenshot3.png)

### Timer and progression

The RTA timer records elapsed time and supports manual lap controls, automatic
Act transitions, Act 1-5 / Act 6-10 mode selection, and saved timer state. The
default controls are F1-F6, F11, and F12 as listed above; every hotkey can be
changed in Settings.

For PoE 1, pressing `Ready` with a reset timer waits for the new character to
enter **The Twilight Strand**, then starts the timer automatically when that
entry appears in `Client.txt`. While Ready is active, the log polling interval
temporarily changes to 100 ms and returns to normal after the timer starts.
Press `Ready` again to cancel; Ready state is not retained across restarts.
Reset any existing timer data before enabling Ready. Manual Start remains
available. Path of Exile must have **Local** chat logging enabled for the area
entry to be detected.

![RTA timer](docs/screenshot6.png)

### Gem tracking and search

PoB import creates a gem-acquisition checklist for the active character. Gem
identity, checked-state keys, ordering, and PoE search paste values remain
English-canonical in both UI languages. Japanese mode shows Japanese names
with English secondary labels; English mode shows the canonical English
labels.

![Gem tracker](docs/screenshot11.png)

### Maps, notes, and accessibility

- Map thumbnails are loaded from `maps/PoE1/<Japanese zone>/` and
  `maps/PoE2/<Japanese zone>/`; the existing folder names are preserved.
- Click a thumbnail to zoom and use keyboard navigation to move between
  layouts.
- Area notes, game notes, search presets, and imported PoB data are saved as
  user content and are never translated automatically.
- Window opacity, click-through mode, always-on-top behavior, collapsible
  panels, multi-monitor placement, and text selection/copy are supported.
- The TCP logout helper only disconnects matching PoE connections and reports
  its result before the application exits.

![Map layout viewer](docs/screenshot5.png)

## Installation details

### Windows release

1. Download the newest release from the [GitHub Releases](../../releases)
   page.
2. Extract `PoENavi.zip` to a folder where the user can run applications.
3. Start `PoENavi.exe`.
4. On a new installation, choose Japanese or English in the bilingual first
   dialog. Existing installations keep Japanese behavior unless a language
   is selected in Settings.

The updater is included as `PoENaviUpdater.exe`. It verifies the downloaded
SHA-256 checksum, preserves user data, replaces only official release files,
and rolls back safely if the new application cannot start.

### Running from source

```powershell
git clone https://github.com/buri34/poenavi.git
Set-Location poenavi
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

On Windows, normal user data is stored in `%APPDATA%\PoENavi`. For isolated
development or test runs, set `POENAVI_USER_DATA_DIR` to a temporary folder.
The bundled official files remain beside the application; user-edited data
is kept in the user-data directory.

## Guide editing and data compatibility

Guide editors are available from Settings. Select PoE version, locale, zone,
visit, route, or flag branch before editing. Japanese edits are saved to
`guide_data.json` or `guide_data_poe2.json`; English edits are saved to the
matching `_en` file. The files retain the same stable IDs, route keys, visit
branches, direction values, mini-navigation tokens, and HTML color spans.

Do not rename the Japanese guide files or map folders. If you distribute a
modified guide, keep the JSON structure and protected command tokens intact.
Run the read-only locale validator before packaging:

```powershell
python scripts/validate_locales.py
```

## Safety and transparency

PoENavi is designed to keep progression and update behavior explicit:

- It parses local client-log output and does not send game credentials to a
  server.
- It does not automate gameplay, inject code, or modify game files.
- It keeps route logic, stable IDs, flags, timers, notes, presets, and user
  guide edits locale-neutral.
- Release archives are checksum-verified before the updater replaces files.

## Roadmap

Possible future work includes more map assets, additional editor ergonomics,
and further guide maintenance. Additional UI languages and live
retranslation are intentionally outside the current localization design;
language changes require an application restart so state is not lost.

## Maintainer release checklist

From a clean working tree, update the version, run the full test suite, run
`scripts/validate_locales.py`, and build the archive:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest -q
python scripts/validate_locales.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_release.ps1 -Python python
python -m zipfile -l PoENavi.zip
```

The resulting `PoENavi.zip.sha256` must be distributed with the archive. The
release contains both locale catalogs and all four guide datasets under the
packaged application's `_internal` directory.

The build also pins the packaged updater to a GitHub repository. It uses an
explicit `-ReleaseRepository owner/repo`, then `GITHUB_REPOSITORY` in Actions,
then the local `origin` URL. The release build fails if none is valid, so fork
artifacts cannot silently update from a different repository.
