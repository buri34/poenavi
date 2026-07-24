# PoE 2 Authoritative Terminology Design

## Goal

Align PoENavi's Path of Exile 2 zone and guide terminology with the English
and Japanese names shipped by the game, and reject future drift during release
validation.

## Scope

- Correct the three confirmed stale Act 2 zone records in both the runtime
  zone master and the in-code fallback.
- Correct confirmed official NPC, monster, item, and area names wherever they
  occur in the English PoE 2 guide.
- Keep route IDs, guide structure, protected values, markup, line counts, and
  Japanese-keyed map assets unchanged.
- Add deterministic validation without making a local game installation a
  development or build dependency.

Free-form prose editing and comprehensive game-data extraction are outside
this change. Prose immediately surrounding a corrected name may be repaired
only when needed to make the resulting instruction grammatical or to fix a
meaning-changing mistranslation identified by the audit.

## Authoritative fixture

Add a small JSON fixture containing only the shared internal identifier,
Japanese name, and English name for terminology used by PoENavi. The initial
entries come from the current game client's `WorldAreas`, `NPCs`,
`MonsterVarieties`, and `BaseItemTypes` tables.

The fixture must not contain a contributor's installation path, extracted
binary tables, or unrelated proprietary game data. It is a reviewable list of
names, not a bundled extractor or data dump.

## Validation

Extend the existing read-only locale validator with two checks:

1. Zone entries identified by stable PoENavi IDs must exactly match the
   authoritative Japanese and English fixture values in both
   `data/zone_data.json` and `src/utils/zone_data_poe2.py`.
2. When an authoritative Japanese term occurs in the Japanese PoE 2 guide's
   corresponding prose leaf, the paired English leaf must contain the
   authoritative English term. This comparison is leaf-local so a name used
   elsewhere cannot conceal a mistranslation.

Terms that are too short or ambiguous for safe substring matching are not
added until they have an unambiguous validation rule. The initial fixture uses
only terms confirmed manually during the audit.

## Testing

Tests first establish failures for:

- the three stale zone records;
- a guide leaf containing an official Japanese name but a non-authoritative
  English rendering;
- disagreement between the JSON zone master and the Python fallback.

After correcting data, run the focused locale and PoE 2 zone tests, the
read-only validator, and the complete test suite. The test environment must
not require access to a local Path of Exile installation.

## Upstream compatibility

The change is isolated to localization data, its validator, focused tests, and
maintainer documentation. It introduces no runtime dependency and no game
installation discovery. This keeps the localization work understandable as an
upstream pull request and allows authoritative terms to be reviewed
independently from the broader English prose.
