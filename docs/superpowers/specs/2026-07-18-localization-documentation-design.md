# Localization Documentation Design

## Purpose

Add a single authoritative guide that explains both how localization was introduced
and how future maintainers should extend it safely. The guide must serve two
audiences:

- upstream reviewers who need to understand the change set and its design choices;
- maintainers who need a practical workflow for changing translations and localized
  data.

The guide will document application localization only. Path of Exile client data may
be described as an optional terminology reference, but no developer-specific
installation path will appear in the repository.

## Documentation Structure

Create `docs/localization.md` and add a short link to it from `README.md` and
`README.en.md`. The READMEs will remain concise; implementation details and
maintenance instructions will not be duplicated between them.

The guide will contain the following sections.

### Overview

Summarize the supported languages, first-run language selection, restart behavior,
and the distinction between translated display text and stable internal data.

### How Localization Was Added

Describe the implementation by concern rather than as a commit-by-commit changelog:

- locale configuration, migration, and first-run selection;
- semantic application strings;
- exact-source translation support for legacy UI text;
- localized guide, zone, gem, and updater-facing resources;
- packaging changes that include every localized resource;
- validation and runtime tests added to prevent regressions.

This section will also explain the later hardening work that found untranslated
strings, placeholder mismatches, and UI imports that were too broadly scoped.

### Architecture

Document the role of each resource:

- `data/i18n/ja.json` and `data/i18n/en.json` are semantic keyed catalogs;
- `data/i18n/ui_ja.json` and `data/i18n/ui_en.json` translate exact Japanese source
  templates and legacy dynamic UI values;
- `guide_data.json`, `guide_data_poe2.json`, and their English counterparts contain
  language-specific guide content;
- `data/zone_data.json` keeps stable zone identity while exposing localized display
  names;
- `src/utils/i18n.py` loads catalogs, applies the selected locale, and falls back to
  canonical Japanese text when a translation is absent.

The guide will emphasize that lookup keys, asset filenames, and other stable
identifiers remain Japanese where compatibility requires it. Display text is
localized at the UI boundary.

### Maintainer Workflow

Provide task-oriented instructions for:

1. adding or changing semantic strings;
2. translating exact legacy UI templates;
3. updating localized guide content while preserving structure, protected tokens,
   placeholders, HTML, and line layout;
4. adding localized zone names without changing stable identifiers;
5. checking terminology against an optional local Path of Exile installation;
6. running localization validation and focused tests before the full test suite.

Any example game-data path will use a neutral placeholder such as
`<PATH_TO_POE_INSTALLATION>`. The guide will identify relevant client data tables
conceptually without recording a contributor's machine-specific directory.

### Design Constraints and Failure Modes

Call out the rules most likely to cause functional regressions:

- do not translate lookup keys or Japanese-keyed map assets;
- preserve format placeholders, markup, protected tokens, and guide structure;
- do not resolve or cache translated UI text before locale initialization;
- keep UI imports scoped so headless tests and optional components remain usable;
- use “waypoint” when expanding the project abbreviation “WP”;
- update both language resources together unless intentionally relying on the
  documented Japanese fallback.

### Validation and Tests

Explain what `scripts/validate_locales.py` checks:

- catalog shape and key parity;
- format-placeholder compatibility;
- guide structure and protected content;
- localized zone coverage;
- statically referenced translation keys;
- remaining raw Japanese UI literals;
- import-scoping regressions;
- inclusion of localized resources in packaged builds.

List the focused localization test modules and provide the repository's canonical
commands for running the validator, focused tests, and complete suite.

### Upstream Review Map

Group files into reviewable concerns:

- localization runtime and configuration;
- UI integration;
- translated catalogs and datasets;
- validation and tests;
- build and packaging support;
- documentation.

This makes a future upstream pull request understandable without binding the guide
to the fork's current commit history.

## README Changes

Add one brief “Localization development” reference to each README. Each link will
describe the guide as the source for architecture, translation maintenance, and
validation. No localization instructions will be copied into both files.

## Verification

Before completing the documentation change:

- confirm every referenced file and command exists in the current repository;
- run the documented commands exactly as written;
- search the new and modified documentation for developer-specific absolute paths;
- verify both README links resolve to `docs/localization.md`;
- review the rendered Markdown structure for clear heading order and readable code
  examples.

## Out of Scope

- changing localization behavior or translation content;
- adding another supported language;
- extracting data automatically from a Path of Exile installation;
- documenting a contributor's local filesystem layout;
- rewriting the general development guide.
