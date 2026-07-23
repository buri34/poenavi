# Localization Development

PoENavi supports Japanese (`ja`) and English (`en`). This document explains
how localization was added, why the data is split across several resource
types, and how to maintain it without breaking guide lookup, map assets, or
startup behavior.

The guide is intended for both future maintainers and reviewers considering an
upstream pull request. It describes the current design by concern rather than
depending on this fork's commit history.

## User-visible behavior

- A new installation shows a bilingual language dialog before the normal UI is
  constructed.
- Existing installations retain Japanese behavior during configuration
  migration.
- The selected language is stored as `language` in the user configuration, and
  `language_selected` records whether the first-run choice has been handled.
- The language can be changed in Settings. A restart is required because the
  application does not live-retranslate existing widgets.
- Missing or invalid locale values normalize to Japanese.

## How localization was added

Localization was introduced in layers so that visible text could change
without changing the Japanese identifiers already used by route logic, guide
lookups, logs, and map folders.

1. `src/utils/i18n.py` added a Qt-independent JSON catalog service with
   Japanese fallback.
2. `src/ui/language_dialog.py`, `main.py`, and configuration migration added
   first-run language selection and persisted locale startup.
3. Stable application messages moved to semantic keys accessed through
   `tr(...)`.
4. Existing Japanese UI source strings were wrapped with `tr_ui(...)` and
   mirrored in exact-source catalogs. This compatibility layer allowed broad
   UI coverage without changing every call site to a new semantic key at once.
5. English guide files and `zone_en` display names were added while Japanese
   guide keys, zone identity, and map asset folders stayed stable.
6. Gem, settings, update, and other runtime UI paths were made locale-aware.
7. PyInstaller build inputs were expanded to include catalogs and all four
   guide datasets.
8. Static validation and runtime UI tests were added, then strengthened to
   catch untranslated literals, placeholder drift, missing packaged
   resources, and local imports that shadow earlier uses of the same name.

## Resource architecture

### Semantic catalogs

`data/i18n/ja.json` and `data/i18n/en.json` contain nested semantic keys.
Application code calls `tr("section.message", name=value)`. Both catalogs must
have the same flattened key set and the same named placeholders for each key.

Japanese is the canonical fallback. If the selected catalog is unavailable or
a key is missing, `tr(...)` checks the Japanese catalog before returning the
key itself. Missing keys are logged once per locale.

Use semantic keys for new UI text whenever practical:

```python
label.setText(tr("settings.language"))
status.setText(tr("update.download_progress", percent=percent))
```

### Exact UI catalogs

`data/i18n/ui_ja.json` and `data/i18n/ui_en.json` support existing
application-owned Japanese source strings passed to `tr_ui(...)`.

- The Japanese catalog key and value are the exact Japanese source template.
- The English catalog uses the same source key and an English value.
- Dynamic f-string expressions are represented as `{value_0}`, `{value_1}`,
  and so on.
- Placeholders must be identical between the source template and translation.
- Arbitrary word replacement is not performed; only catalogued exact strings
  and templates are translated.

Example:

```python
message = tr_ui(f"エリア: {zone_name}")
```

Catalog entries:

```json
// ui_ja.json
"エリア: {value_0}": "エリア: {value_0}"

// ui_en.json
"エリア: {value_0}": "Area: {value_0}"
```

JSON does not support comments; the comments above identify the files and
must not be copied into the actual catalogs.

Use `tr_ui(...)` when maintaining an existing exact-source call site. Prefer a
semantic `tr(...)` key for new, reusable application messages.

### Guide datasets

The bundled guide resources are language-specific:

| Game | Japanese | English |
| --- | --- | --- |
| PoE 1 | `guide_data.json` | `guide_data_en.json` |
| PoE 2 | `guide_data_poe2.json` | `guide_data_poe2_en.json` |

`src/utils/guide_data.py` chooses the file for the active game and locale.
English load failure may fall back to Japanese for display, but editor saves
remain pointed at the requested locale-specific file so an English edit never
overwrites the Japanese guide.

Only prose fields such as `objective`, `layout`, `tips`, `summary`, and `text`
are translated. Structure, route keys, visit branches, flags, direction
values, mini-navigation tokens, placeholders, and supported HTML spans remain
aligned between languages.

### Zones and map assets

Entries in `data/zone_data.json` keep the Japanese `zone` value and add
`zone_en` for English display. Stable `id` values drive identity.
`src/utils/zone_lookup.py` accepts either language when resolving a zone and
selects the display name at the UI boundary.

Map folders remain keyed by Japanese zone names. Do not rename those folders
or replace lookup keys with translated display text. The separation between
stable identity and display language is what keeps logs, routing, guide data,
and existing assets compatible.

### Packaging

`poenavi.spec` and `scripts/build_release.ps1` register:

- `data/i18n`;
- `guide_data.json`;
- `guide_data_poe2.json`;
- `guide_data_en.json`;
- `guide_data_poe2_en.json`.

The standalone updater also uses the Qt-independent localization service, so
catalogs must be present in both source and packaged layouts.

## Maintainer workflows

### Add or change a semantic message

1. Add the same dotted key to `data/i18n/ja.json` and
   `data/i18n/en.json`.
2. Keep named placeholders identical in both values.
3. Call `tr("the.new.key", value=name)` from the application.
4. Run the locale validator and focused tests below.

### Translate an existing exact UI string

1. Wrap the complete application-owned source string in `tr_ui(...)`.
2. For an f-string, use the complete f-string at the call site.
3. Add its static template to both `ui_ja.json` and `ui_en.json`.
4. Keep the Japanese value equal to the source key.
5. Use `{value_0}`, `{value_1}`, and later fields in source-expression order.
6. Preserve every dynamic placeholder in the English translation.

Do not wrap domain identifiers, regex search tokens, log values, user-entered
notes, or other content that is not owned UI copy.

### Update guide translations

1. Make the corresponding change in the Japanese and English guide files.
2. Translate only prose fields.
3. Preserve object keys, list lengths, scalar types, route and visit branches,
   flags, direction values, and other protected values.
4. Preserve tokens such as `[quest]`, `[boss]`, `[town]`, `[move]`, `[logout]`,
   `[note]`, `[star]`, `[trial]`, `[craft]`, `[wp]`, and `[portal]`.
5. Preserve named placeholders, line layout, and supported `<span>` markup.
6. When prose expands “WP”, translate it as “waypoint”.
7. Run `python scripts/validate_locales.py` before launching the app.

### Add or correct a zone name

1. Keep the stable `id` unchanged.
2. Add or update `zone_en`. Change the Japanese `zone` value only when
   current game data confirms that the in-game Japanese name changed.
3. Confirm code uses `get_zone_display_name(...)` or otherwise separates
   lookup from display.
4. Do not rename the matching Japanese map folder.
5. Run the validator and localized-resource tests.

### Reconcile Path of Exile terminology

Prefer terminology used by the game client over literal translation. When a
local Path of Exile installation is available, its language data can be used
as a read-only reference under:

```text
<PATH_TO_POE_INSTALLATION>
```

Useful reference tables include `WorldAreas`, `NPCs`, and
`MonsterVarieties`. Installation layouts and extracted data formats can vary,
so this is a terminology cross-check rather than a build dependency. Never
commit a contributor's installation path or copied proprietary game data.

Confirmed names for both games are recorded in
`data/authoritative_guide_terms.json`. Each entry contains only the game,
originating table, stable game identifier, and paired Japanese and English
terms needed for review. The same fixture retains the reviewed PoE 2 zone
pairs and known incorrect English forms that must not return. When updating it:

1. Pair languages through the same internal game identifier; do not match
   translated strings heuristically.
2. Include only terms that occur in PoENavi resources.
3. Update both `data/zone_data.json` and `src/utils/zone_data_poe2.py` for a
   confirmed zone change.
4. Correct every corresponding guide leaf while preserving its structure,
   line count, tokens, and markup.
5. Do not add short or ambiguous terms to global substring validation. Cover
   those with a path-specific regression test instead.
6. Run the locale validator without requiring the local game installation.

## Constraints and common failure modes

- Do not translate stable IDs, lookup keys, route keys, or Japanese-keyed map
  paths.
- Do not remove or rename format placeholders.
- Do not alter guide structure, protected tokens, or supported markup while
  translating prose.
- Do not compute translated widget text at module import time or before
  `set_locale(...)` runs.
- Avoid a function-local import that gives a name local scope after that name
  has already been used; Python will raise `UnboundLocalError`.
- Keep the first-run language dialog bilingual because it appears before a
  locale has been selected.
- Do not add raw Japanese text directly to common Qt display APIs outside the
  intentional bilingual language dialog; route it through `tr(...)` or
  `tr_ui(...)`.
- Change both language resources together unless Japanese fallback is
  deliberate and documented.

## Validation and tests

Run the read-only validator first:

```powershell
python scripts/validate_locales.py
```

It checks:

- semantic catalog key and placeholder parity;
- exact UI catalog coverage and dynamic placeholders;
- guide structure, protected values, tokens, HTML, and translated leaves;
- `zone_en` coverage;
- authoritative guide terminology for both games and PoE 2 zone parity;
- statically referenced semantic keys;
- function-local import shadowing;
- raw Japanese literals passed to common Qt display APIs;
- packaged localization resource registration.

Run the focused localization tests in an offscreen Qt environment:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests/test_i18n.py tests/test_language_startup_flow.py tests/test_locale_validation.py tests/test_localized_resources.py tests/test_localized_ui.py tests/test_settings_area_notes.py
```

Then run the complete suite:

```powershell
python -m pytest -q
```

The focused tests cover catalog lookup and fallback, first-run migration,
guide-file isolation, localized zone display, construction of important UI in
both locales, Settings access, and the release validator.

## Upstream review map

| Concern | Principal files |
| --- | --- |
| Runtime and fallback | `src/utils/i18n.py`, `main.py` |
| Configuration and first run | `src/utils/config_manager.py`, `src/ui/language_dialog.py` |
| UI integration | `src/ui/`, `src/update/`, other `tr(...)` and `tr_ui(...)` call sites |
| Catalog data | `data/i18n/*.json` |
| Guide and zone data | `guide_data*.json`, `data/zone_data.json`, `data/authoritative_guide_terms.json`, `src/utils/guide_data.py`, `src/utils/zone_lookup.py` |
| Validation and tests | `scripts/validate_locales.py`, `tests/test_authoritative_guide_terminology.py`, `tests/test_poe2_authoritative_terminology.py`, `tests/test_i18n.py`, `tests/test_language_startup_flow.py`, `tests/test_locale_validation.py`, `tests/test_localized_resources.py`, `tests/test_localized_ui.py`, `tests/test_settings_area_notes.py` |
| Packaging | `poenavi.spec`, `scripts/build_release.ps1` |
| User documentation | `README.md`, `README.en.md`, this guide |

For upstream review, the exact-source UI catalog can be considered a
compatibility layer separate from the semantic catalog API. Data translations
can likewise be reviewed independently from runtime locale selection and
packaging support.
