# Expedition Windows OCR audit (2026-09-08)

## Scope

- Engine: Windows.Media.Ocr (`ja-JP`)
- Input: 25 Japanese screenshots, 146 reward rows
- Excluded: one English sample screenshot (10 rows)
- Ground truth: the human-transcribed `expected` rows stored in the `c1` through `c6` benchmark summaries

## Results

- Trusted item names: 104 / 146 (71.2%)
- Wrong trusted item names: 0 / 104 (0%)
- Rows with an explicit expected quantity: 112
- Correctly detected quantities: 99 / 112 (88.4%)
- Wrong detected quantities: 0
- False-positive quantities on rows without an explicit quantity: 0
- Rows where both the trusted name and quantity result were correct: 95 / 146 (65.1%)

## Ground-truth correction

Three apparent trusted-name mismatches were caused by a transcription error in the benchmark truth. The source screenshot reads `ヴェリシウム`, while the existing truth uses `ヴェリジウム`. The Windows OCR and Trade item dictionary both selected the source-image spelling, so these are counted as correct recognitions.

## Remaining quantity misses

Thirteen explicit quantities were not detected. In these cases Windows OCR either omitted the count glyph entirely or placed leading decoration before a recognized count. No wrong quantity was accepted. The next experiment should target the quantity area independently, while retaining Windows OCR as the only OCR engine.
