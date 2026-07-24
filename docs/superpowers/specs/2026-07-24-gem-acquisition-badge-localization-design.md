# Gem Acquisition Badge Localization Design

## Goal

Remove the Japanese `報酬` and `購入` acquisition badges from English-mode gem
rows while preserving Japanese mode and canonical English gem names.

## Implementation

The gem row already has access to the keyed locale catalog. Replace the
hard-coded `TYPE_LABELS` lookup with:

- `tr("gems.reward")` for quest rewards; and
- `tr("gems.vendor")` for vendor and Lilly purchases.

The existing catalog values remain authoritative:

- English: `Quest` and `Buy`
- Japanese: `報酬` and `購入`

Remove the now-unused hard-coded mapping. Do not change imported PoB data,
gem identity, checked-state keys, search paste values, ordering, or the
English/Japanese gem-name display rules.

## Testing

Add a focused PySide6 widget regression that renders quest, vendor, and Lilly
gem rows in English mode and asserts that their badges are `Quest`, `Buy`, and
`Buy`, with no Japanese acquisition labels.

The previously completed visit-guide tooltip remains in the same implementation
commit. Its behavior and tests are otherwise unchanged.
