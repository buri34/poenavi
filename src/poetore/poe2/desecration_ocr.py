"""PoE2 Desecration Reveal capture preparation and safe OCR resolution."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PySide6.QtGui import QColor, QImage

from src.poetore.poe2.desecration_tiers import (
    RESCUE_REASONS,
    AffixTierOption,
    FuzzyTierResolution,
    TierValue,
    available_categories,
    resolve_desecration_choices_fuzzy,
)


@dataclass(frozen=True)
class ChoiceBand:
    top: int
    bottom: int


@dataclass(frozen=True)
class PreparedDesecrationFrame:
    bands: tuple[ChoiceBand, ...]
    variants: tuple[tuple[QImage, ...], ...]
    valid_panel: bool


@dataclass(frozen=True)
class OcrRevealResolution:
    categories: tuple[str, ...]
    tiers_by_category: dict[str, tuple[TierValue, ...]]
    texts_by_category: dict[str, tuple[str, ...]]
    ranges_by_category: dict[str, tuple[tuple[str, ...], ...]]
    affix_options_by_category: dict[
        str, tuple[tuple[AffixTierOption, ...], ...]
    ]
    statuses_by_category: dict[str, tuple[str, ...]]
    fallback_statuses: tuple[str, ...] = ()
    fallback_texts: tuple[str, ...] = ()
    fallback_tiers: tuple[TierValue, ...] = ()
    fallback_ranges: tuple[tuple[str, ...], ...] = ()
    fallback_affix_options: tuple[tuple[AffixTierOption, ...], ...] = ()
    category_conflict: bool = False

    @property
    def needs_category_choice(self) -> bool:
        display_results = {
            (
                tiers,
                self.affix_options_by_category.get(category, ()),
            )
            for category, tiers in self.tiers_by_category.items()
        }
        return len(display_results) > 1

    @property
    def tiers(self) -> tuple[TierValue, ...] | None:
        unique = set(self.tiers_by_category.values())
        return next(iter(unique)) if len(unique) == 1 else None

    @property
    def ranges(self) -> tuple[tuple[str, ...], ...] | None:
        unique = set(self.ranges_by_category.values())
        return next(iter(unique)) if len(unique) == 1 else None

    @property
    def statuses(self) -> tuple[str, ...] | None:
        unique = set(self.statuses_by_category.values())
        return next(iter(unique)) if len(unique) == 1 else None

    @property
    def affix_options(self) -> tuple[tuple[AffixTierOption, ...], ...] | None:
        unique = set(self.affix_options_by_category.values())
        return next(iter(unique)) if len(unique) == 1 else None


def image_bytes(image: QImage, image_format: str = "BMP") -> bytes:
    payload = QByteArray()
    buffer = QBuffer(payload)
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, image_format):
        raise RuntimeError("OCR用画像を変換できませんでした。")
    return bytes(payload)


def choice_bands(image: QImage) -> tuple[ChoiceBand, ...]:
    height = image.height()
    width = image.width()
    if image.isNull() or height < 60 or width < 120:
        return ()
    radius = max(4, round(height * .09))
    separators = []
    sample_step = max(1, image.width() // 180)
    rgba = image.convertToFormat(QImage.Format_RGBA8888)
    pixels = rgba.bits()
    stride = rgba.bytesPerLine()
    for fraction in (1 / 3, 2 / 3):
        center = round(height * fraction)
        left, right = max(1, center - radius), min(height - 1, center + radius)
        means = []
        for y in range(left, right):
            total = 0
            count = 0
            for x in range(0, image.width(), sample_step):
                offset = y * stride + x * 4
                total += pixels[offset] + pixels[offset + 1] + pixels[offset + 2]
                count += 3
            means.append(total / max(1, count))
        # A uniformly coloured or badly clipped crop still has a mathematical
        # minimum, but it does not contain the two dark card separators.
        if max(means) - min(means) < 4:
            return ()
        separators.append(left + min(range(len(means)), key=means.__getitem__))
    edges = (0, *separators, height)
    if not (edges[0] < edges[1] < edges[2] < edges[3]):
        return ()
    return tuple(ChoiceBand(edges[index] + (1 if index else 0), edges[index + 1]) for index in range(3))


def _green_text_rect(image: QImage, padding: int = 8) -> tuple[QRect | None, int]:
    left, top, right, bottom = image.width(), image.height(), -1, -1
    count = 0
    rgba = image.convertToFormat(QImage.Format_RGBA8888)
    pixels = rgba.bits()
    stride = rgba.bytesPerLine()
    for y in range(image.height()):
        row = y * stride
        for x in range(image.width()):
            offset = row + x * 4
            red, green, blue = pixels[offset], pixels[offset + 1], pixels[offset + 2]
            if green >= 75 and green - blue >= 10 and green - red >= 5:
                left, top = min(left, x), min(top, y)
                right, bottom = max(right, x), max(bottom, y)
                count += 1
    if right < left or bottom < top:
        return None, 0
    return QRect(
        max(0, left - padding), max(0, top - padding),
        min(image.width() - 1, right + padding) - max(0, left - padding) + 1,
        min(image.height() - 1, bottom + padding) - max(0, top - padding) + 1,
    ), count


def desecration_panel_diagnostics(image: QImage) -> dict[str, object]:
    """Return sanitized structural metrics used by the shared OCR router."""
    result: dict[str, object] = {
        "image_width": image.width(),
        "image_height": image.height(),
        "probe_width": 0,
        "probe_height": 0,
        "band_count": 0,
        "min_band_height": 0,
        "max_band_height": 0,
        "green_pixel_counts": [],
        "green_text_widths": [],
        "matched": False,
    }
    if image.isNull():
        return result
    image = (
        image.scaledToWidth(360, Qt.FastTransformation)
        if image.width() > 360 else image
    )
    result["probe_width"] = image.width()
    result["probe_height"] = image.height()
    bands = choice_bands(image)
    result["band_count"] = len(bands)
    if len(bands) != 3:
        return result
    heights = [band.bottom - band.top for band in bands]
    result["min_band_height"] = min(heights, default=0)
    result["max_band_height"] = max(heights, default=0)
    if min(heights) <= 0 or max(heights) / min(heights) > 1.45:
        return result
    pixel_counts = []
    text_widths = []
    for band in bands:
        card = image.copy(0, band.top, image.width(), max(1, band.bottom - band.top))
        text_rect, pixels = _green_text_rect(card, padding=0)
        pixel_counts.append(pixels)
        text_widths.append(text_rect.width() if text_rect is not None else 0)
        if (
            text_rect is None
            or pixels < 20
            or text_rect.width() < max(24, round(image.width() * 0.08))
        ):
            result["green_pixel_counts"] = pixel_counts
            result["green_text_widths"] = text_widths
            return result
    result["green_pixel_counts"] = pixel_counts
    result["green_text_widths"] = text_widths
    result["matched"] = True
    return result


def looks_like_desecration_panel(image: QImage) -> bool:
    """Return whether a registered crop has three balanced green-text choices."""
    return bool(desecration_panel_diagnostics(image)["matched"])


def _green_mask(image: QImage) -> QImage:
    source = image.convertToFormat(QImage.Format_RGBA8888)
    source_pixels = source.bits()
    source_stride = source.bytesPerLine()
    result = QImage(image.size(), QImage.Format_RGBA8888)
    result.fill(QColor("white"))
    result_pixels = result.bits()
    result_stride = result.bytesPerLine()
    for y in range(image.height()):
        source_row = y * source_stride
        result_row = y * result_stride
        for x in range(image.width()):
            source_offset = source_row + x * 4
            red = source_pixels[source_offset]
            green = source_pixels[source_offset + 1]
            blue = source_pixels[source_offset + 2]
            if green >= 75 and green - blue >= 10 and green - red >= 5:
                result_offset = result_row + x * 4
                result_pixels[result_offset] = 0
                result_pixels[result_offset + 1] = 0
                result_pixels[result_offset + 2] = 0
    return result.convertToFormat(QImage.Format_RGB32)


def prepare_desecration_frame(image: QImage) -> PreparedDesecrationFrame:
    bands = choice_bands(image)
    all_variants = []
    valid = len(bands) == 3
    for band in bands:
        card = image.copy(0, band.top, image.width(), max(1, band.bottom - band.top))
        text_rect, pixels = _green_text_rect(card)
        if text_rect is None or pixels < 20:
            valid = False
            crop = card
        else:
            crop = card.copy(text_rect)
        all_variants.append((
            crop.scaled(crop.width() * 4, crop.height() * 4, Qt.IgnoreAspectRatio, Qt.SmoothTransformation),
            crop.scaled(crop.width() * 6, crop.height() * 6, Qt.IgnoreAspectRatio, Qt.SmoothTransformation),
            _green_mask(crop).scaled(crop.width() * 4, crop.height() * 4),
        ))
    return PreparedDesecrationFrame(bands, tuple(all_variants), valid)


def _unmatched_status(outputs: tuple[str, ...]) -> str:
    """Separate unstable/garbled OCR from stable text absent from our data."""
    normalized = [re.sub(r"\s+", "", text) for text in outputs if text.strip()]
    readable = [
        text for text in normalized
        if re.search(r"\d", text) and re.search(r"[ぁ-んァ-ヶ一-龯]", text)
        and len(text) >= 5
    ]
    if readable and Counter(readable).most_common(1)[0][1] >= 2:
        return "unsupported"
    return "read_failed"


def _tier_value(result: FuzzyTierResolution) -> TierValue:
    if result.tier is not None:
        return result.tier
    return result.tier_candidates or None


def _variant_identity(text: str, result: FuzzyTierResolution) -> tuple:
    numbers = tuple(re.findall(r"[+-]?\d+(?:\.\d+)?", text))
    return _tier_value(result), result.mod_ids, numbers


def resolve_ocr_variants(
    variant_texts: tuple[tuple[str, ...], ...],
    categories: tuple[str, ...] | None = None,
) -> OcrRevealResolution:
    """Choose OCR variants by score; numeric conflicts remain unresolved."""
    category_pool = categories or available_categories()
    candidate_rows = {}
    fallback_statuses = tuple(_unmatched_status(outputs) for outputs in variant_texts)
    fallback_texts = tuple(
        next((text.strip() for text in outputs if text.strip()), "")
        for outputs in variant_texts
    )
    unique_texts = tuple(dict.fromkeys(
        text.strip()
        for outputs in variant_texts for text in outputs
        if text.strip()
    ))
    resolutions_by_text = {
        text: resolve_desecration_choices_fuzzy(text, category_pool)
        for text in unique_texts
    }
    for category in category_pool:
        tiers = []
        texts = []
        ranges = []
        affix_options = []
        statuses = []
        identities_by_choice = []
        for outputs in variant_texts:
            attempts: list[tuple[str, FuzzyTierResolution]] = [
                (text, resolutions_by_text[text.strip()][category])
                for text in outputs if text.strip()
            ]
            matched = [
                (text, result) for text, result in attempts
                if _tier_value(result) is not None
            ]
            if not matched:
                tiers.append(None)
                texts.append(outputs[0].strip() if outputs else "")
                ranges.append(())
                affix_options.append(())
                statuses.append(_unmatched_status(outputs))
                identities_by_choice.append(None)
                continue
            identities = Counter(
                _variant_identity(text, result) for text, result in matched
            )
            if len(identities) > 1:
                highest = max(identities.values())
                majorities = [
                    identity for identity, count in identities.items()
                    if count == highest
                ]
                if highest < 2 or len(majorities) != 1:
                    tiers.append(None)
                    texts.append(matched[0][0])
                    ranges.append(())
                    affix_options.append(())
                    statuses.append("read_failed")
                    identities_by_choice.append(None)
                    continue
                majority = majorities[0]
                matched = [
                    (text, result) for text, result in matched
                    if _variant_identity(text, result) == majority
                ]
                identities = Counter({majority: len(matched)})
            if len(identities) != 1:
                tiers.append(None)
                texts.append(matched[0][0])
                ranges.append(())
                affix_options.append(())
                statuses.append("read_failed")
                identities_by_choice.append(None)
                continue
            if any(result.reason in RESCUE_REASONS for _text, result in matched):
                agreeing = sum(
                    1 for _text, result in matched
                    if _variant_identity(_text, result) == next(iter(identities))
                )
                if agreeing < 2:
                    tiers.append(None)
                    texts.append(matched[0][0])
                    ranges.append(())
                    affix_options.append(())
                    statuses.append("read_failed")
                    identities_by_choice.append(None)
                    continue
            best_score = max(result.score or 0 for _text, result in matched)
            finalists = [
                (text, result) for text, result in matched
                if best_score - (result.score or 0) <= .035
            ]
            finalist_tiers = {_tier_value(result) for _text, result in finalists}
            if len(finalist_tiers) != 1:
                tiers.append(None)
                texts.append(finalists[0][0])
                ranges.append(())
                affix_options.append(())
                statuses.append("read_failed")
                identities_by_choice.append(None)
                continue
            chosen = max(finalists, key=lambda item: item[1].score or 0)
            tier_value = _tier_value(chosen[1])
            tiers.append(tier_value)
            texts.append(chosen[0])
            ranges.append(chosen[1].range_labels)
            affix_options.append(chosen[1].affix_options)
            statuses.append(
                "multiple_tiers" if chosen[1].tier_candidates else "matched"
            )
            identities_by_choice.append((tier_value, chosen[1].mod_ids))
        resolved = sum(identity is not None for identity in identities_by_choice)
        candidate_rows[category] = (
            resolved, tuple(tiers), tuple(texts), tuple(ranges), tuple(statuses),
            tuple(affix_options), tuple(identities_by_choice),
        )

    fallback_tiers = []
    fallback_ranges = []
    fallback_affix_options = []
    resolved_fallback_statuses = list(fallback_statuses)
    resolved_fallback_texts = list(fallback_texts)
    for index in range(len(variant_texts)):
        outcomes = {
            (row[6][index], row[3][index], row[5][index])
            for row in candidate_rows.values() if row[6][index] is not None
        }
        if len(outcomes) == 1:
            identity, labels, options = next(iter(outcomes))
            fallback_tiers.append(identity[0])
            fallback_ranges.append(labels)
            fallback_affix_options.append(options)
            resolved_fallback_statuses[index] = (
                "multiple_tiers" if isinstance(identity[0], tuple) else "matched"
            )
            resolved_fallback_texts[index] = next(
                row[2][index] for row in candidate_rows.values()
                if row[6][index] == identity
            )
        else:
            fallback_tiers.append(None)
            fallback_ranges.append(())
            fallback_affix_options.append(())
            if outcomes:
                resolved_fallback_statuses[index] = "category_unselected"
                resolved_fallback_texts[index] = next(
                    row[2][index] for row in candidate_rows.values()
                    if row[6][index] is not None
                )

    recognized_choices = {
        index for index in range(len(variant_texts))
        if any(row[6][index] is not None for row in candidate_rows.values())
    }
    winners = {
        category: row for category, row in candidate_rows.items()
        if recognized_choices
        and (len(recognized_choices) >= 2 or len(category_pool) == 1)
        and all(row[6][index] is not None for index in recognized_choices)
    }
    if not winners:
        return OcrRevealResolution(
            categories=(), tiers_by_category={}, texts_by_category={},
            ranges_by_category={}, affix_options_by_category={},
            statuses_by_category={},
            fallback_statuses=tuple(resolved_fallback_statuses),
            fallback_texts=tuple(resolved_fallback_texts),
            fallback_tiers=tuple(fallback_tiers),
            fallback_ranges=tuple(fallback_ranges),
            fallback_affix_options=tuple(fallback_affix_options),
            category_conflict=len(recognized_choices) >= 2,
        )
    return OcrRevealResolution(
        categories=tuple(winners),
        tiers_by_category={category: row[1] for category, row in winners.items()},
        texts_by_category={category: row[2] for category, row in winners.items()},
        ranges_by_category={category: row[3] for category, row in winners.items()},
        affix_options_by_category={category: row[5] for category, row in winners.items()},
        statuses_by_category={category: row[4] for category, row in winners.items()},
        fallback_statuses=tuple(resolved_fallback_statuses),
        fallback_texts=tuple(resolved_fallback_texts),
        fallback_tiers=tuple(fallback_tiers),
        fallback_ranges=tuple(fallback_ranges),
        fallback_affix_options=tuple(fallback_affix_options),
    )
