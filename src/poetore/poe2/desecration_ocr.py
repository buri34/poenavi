"""PoE2 Desecration Reveal capture preparation and safe OCR resolution."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PySide6.QtGui import QColor, QImage

from src.poetore.poe2.desecration_tiers import (
    RESCUE_REASONS,
    FuzzyTierResolution,
    available_categories,
    resolve_desecration_choice_fuzzy,
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
    tiers_by_category: dict[str, tuple[int | None, ...]]
    texts_by_category: dict[str, tuple[str, ...]]
    ranges_by_category: dict[str, tuple[tuple[str, ...], ...]]
    statuses_by_category: dict[str, tuple[str, ...]]
    fallback_statuses: tuple[str, ...] = ()
    fallback_texts: tuple[str, ...] = ()
    fallback_tiers: tuple[int | None, ...] = ()
    fallback_ranges: tuple[tuple[str, ...], ...] = ()

    @property
    def needs_category_choice(self) -> bool:
        return len(set(self.tiers_by_category.values())) > 1

    @property
    def tiers(self) -> tuple[int | None, ...] | None:
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
    for fraction in (1 / 3, 2 / 3):
        center = round(height * fraction)
        left, right = max(1, center - radius), min(height - 1, center + radius)
        means = []
        for y in range(left, right):
            total = 0
            count = 0
            for x in range(0, image.width(), sample_step):
                color = image.pixelColor(x, y)
                total += color.red() + color.green() + color.blue()
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
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.green() >= 75 and color.green() - color.blue() >= 10 and color.green() - color.red() >= 5:
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


def _green_mask(image: QImage) -> QImage:
    result = QImage(image.size(), QImage.Format_RGB32)
    result.fill(QColor("white"))
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.green() >= 75 and color.green() - color.blue() >= 10 and color.green() - color.red() >= 5:
                result.setPixelColor(x, y, QColor("black"))
    return result


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
    for category in category_pool:
        tiers = []
        texts = []
        ranges = []
        statuses = []
        identities_by_choice = []
        for outputs in variant_texts:
            attempts: list[tuple[str, FuzzyTierResolution]] = [
                (text, resolve_desecration_choice_fuzzy(text, category))
                for text in outputs if text.strip()
            ]
            matched = [(text, result) for text, result in attempts if result.tier is not None]
            if not matched:
                tiers.append(None)
                texts.append(outputs[0].strip() if outputs else "")
                ranges.append(())
                statuses.append(_unmatched_status(outputs))
                identities_by_choice.append(None)
                continue
            identities = {
                (result.tier, result.mod_ids)
                for _text, result in matched
            }
            if len(identities) != 1:
                tiers.append(None)
                texts.append(matched[0][0])
                ranges.append(())
                statuses.append("read_failed")
                identities_by_choice.append(None)
                continue
            if any(result.reason in RESCUE_REASONS for _text, result in matched):
                agreeing = sum(
                    1 for _text, result in matched
                    if (result.tier, result.mod_ids) == next(iter(identities))
                )
                if agreeing < 2:
                    tiers.append(None)
                    texts.append(matched[0][0])
                    ranges.append(())
                    statuses.append("read_failed")
                    identities_by_choice.append(None)
                    continue
            best_score = max(result.score or 0 for _text, result in matched)
            finalists = [
                (text, result) for text, result in matched
                if best_score - (result.score or 0) <= .035
            ]
            finalist_tiers = {result.tier for _text, result in finalists}
            if len(finalist_tiers) != 1:
                tiers.append(None)
                texts.append(finalists[0][0])
                ranges.append(())
                statuses.append("read_failed")
                identities_by_choice.append(None)
                continue
            chosen = max(finalists, key=lambda item: item[1].score or 0)
            tiers.append(chosen[1].tier)
            texts.append(chosen[0])
            ranges.append(chosen[1].range_labels)
            statuses.append("matched")
            identities_by_choice.append((chosen[1].tier, chosen[1].mod_ids))
        resolved = sum(tier is not None for tier in tiers)
        candidate_rows[category] = (
            resolved, tuple(tiers), tuple(texts), tuple(ranges), tuple(statuses),
            tuple(identities_by_choice),
        )

    fallback_tiers = []
    fallback_ranges = []
    resolved_fallback_statuses = list(fallback_statuses)
    resolved_fallback_texts = list(fallback_texts)
    for index in range(len(variant_texts)):
        outcomes = {
            (row[5][index], row[3][index])
            for row in candidate_rows.values() if row[5][index] is not None
        }
        if len(outcomes) == 1:
            identity, labels = next(iter(outcomes))
            fallback_tiers.append(identity[0])
            fallback_ranges.append(labels)
            resolved_fallback_statuses[index] = "matched"
            resolved_fallback_texts[index] = next(
                row[2][index] for row in candidate_rows.values()
                if row[5][index] == identity
            )
        else:
            fallback_tiers.append(None)
            fallback_ranges.append(())

    required = len(variant_texts)
    winners = {
        category: row for category, row in candidate_rows.items()
        if row[0] == required
    }
    if not winners:
        return OcrRevealResolution(
            categories=(), tiers_by_category={}, texts_by_category={},
            ranges_by_category={}, statuses_by_category={},
            fallback_statuses=tuple(resolved_fallback_statuses),
            fallback_texts=tuple(resolved_fallback_texts),
            fallback_tiers=tuple(fallback_tiers),
            fallback_ranges=tuple(fallback_ranges),
        )
    return OcrRevealResolution(
        categories=tuple(winners),
        tiers_by_category={category: row[1] for category, row in winners.items()},
        texts_by_category={category: row[2] for category, row in winners.items()},
        ranges_by_category={category: row[3] for category, row in winners.items()},
        statuses_by_category={category: row[4] for category, row in winners.items()},
        fallback_statuses=tuple(resolved_fallback_statuses),
        fallback_texts=tuple(resolved_fallback_texts),
        fallback_tiers=tuple(fallback_tiers),
        fallback_ranges=tuple(fallback_ranges),
    )
