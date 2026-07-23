# English Guide Correction Design

## Goal

Bring the Path of Exile 1 and Path of Exile 2 English guides to release quality by using each game's installed English and Japanese data as the authority for game terminology, editing the remaining prose into clear and faithful English, and expanding repository validation so corrected terminology cannot regress.

## Scope

- Correct `guide_data_en.json` in one implementation commit.
- Correct `guide_data_poe2_en.json` in a second implementation commit.
- Expand authoritative fixtures, validation, and tests in a third implementation commit.
- Preserve every guide key, protected value, mini-navigation token, supported HTML tag, and source line count.
- Preserve the Japanese guides as the source of guide intent.
- Never store installation-specific local paths in repository files.
- Never stage or commit anything under `plans/` or `docs/superpowers/plans/`.

## Correction Strategy

Each guide is corrected in two passes. The terminology pass maps Japanese strings to official English strings through stable game-data identifiers from `WorldAreas`, `NPCs`, `MonsterVarieties`, `BaseItemTypes`, and `QuestStates`. Ambiguous generic substrings are reviewed rather than replaced automatically.

The editorial pass rewrites literal or malformed machine translation while preserving the Japanese meaning, formatting boundaries, and navigation instructions. It fixes incorrect point of view, sentence fragments, missing spacing, mistranslated abbreviations, and misleading literal translations. It does not modernize or independently change routing advice.

## Validation Design

The repository stores reviewed authoritative mappings, not extracted game files. Each mapping records its source table and stable game identifier alongside Japanese and English names. Validation finds every guide leaf containing a mapped Japanese term and requires the corresponding English leaf to contain the official English term.

Coverage includes both games. Tests must demonstrate failure for a terminology regression in each guide and for missing or unused fixture entries. Existing structural, protected-value, token, markup, and line-count checks remain mandatory.

## Verification and Commits

Before each guide commit:

1. Run the guide-specific terminology and quality checks.
2. Run locale validation.
3. Run the full test suite.
4. Inspect the staged diff and confirm only that game's English guide is staged.

Before the validator commit:

1. Demonstrate new regression tests fail before implementation.
2. Run the authoritative tests and locale validation.
3. Run the full test suite.
4. Confirm no plan files or machine-local paths are staged.

The final audit compares both guide pairs structurally, reruns the complete authoritative sweep, checks representative editorial defects, and verifies the three implementation commits have the intended separation.
