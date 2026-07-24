# Visit Guide Toggle Tooltip Design

## Goal

Explain the `Automatic / First time / Second time` guide toggle without
changing its behavior.

## User Experience

Hovering over the visit toggle shows a localized multiline tooltip explaining:

- the toggle only changes the guide displayed for the current area;
- Automatic uses PoENavi's recorded visit count;
- First time forces the initial-visit guide;
- Second time forces the revisit guide;
- a missing revisit guide falls back to the first-visit guide; and
- a manual override resets after entering another non-town area.

The tooltip is attached directly to the existing button and remains the same
while its label cycles through the three modes.

## Localization

The Japanese source text is passed through `tr_ui`. Exact Japanese and English
entries are added to the UI catalogs so the Japanese behavior remains
unchanged and English mode never exposes raw Japanese text.

## Testing

A localized UI regression test constructs the main window in English and
asserts that the visit-toggle tooltip contains the essential Automatic,
First time, Second time, fallback, and reset explanations.

No configuration, guide-selection logic, or saved user data changes.
