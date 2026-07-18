"""Small, editable JSON-backed localization service for PoENavi.

The service deliberately has no Qt dependency so it can also be used by the
standalone updater and by data/validation tools.  Japanese is the canonical
fallback for both missing catalogs and missing individual keys.
"""

from __future__ import annotations

import json
import logging
import os
import re
import string
import sys
from pathlib import Path
from typing import Any


JA = "ja"
EN = "en"
DEFAULT_LOCALE = JA
SUPPORTED_LOCALES = (JA, EN)

_logger = logging.getLogger(__name__)
_locale = DEFAULT_LOCALE
_catalog_cache: dict[str, dict[str, Any]] = {}
_ui_catalog_cache: dict[str, dict[str, str]] = {}
_ui_pattern_cache: dict[str, list[tuple[re.Pattern[str], str]]] = {}
_missing_keys: set[tuple[str, str]] = set()


def _catalog_dir() -> Path:
    """Return the locale directory in source and PyInstaller layouts."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidate = exe_dir / "data" / "i18n"
        if candidate.is_dir():
            return candidate
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
        return meipass / "data" / "i18n"
    return Path(__file__).resolve().parents[2] / "data" / "i18n"


def normalize_locale(locale: str | None) -> str:
    """Normalize a persisted code or an OS locale to ``ja`` or ``en``."""
    value = str(locale or "").strip().lower().replace("_", "-")
    if value.startswith("en"):
        return EN
    if value.startswith("ja"):
        return JA
    return DEFAULT_LOCALE


def set_locale(locale: str | None) -> str:
    """Set and return the active locale, falling back safely to Japanese."""
    global _locale
    _locale = normalize_locale(locale)
    return _locale


def get_locale() -> str:
    return _locale


def get_supported_locales() -> tuple[str, ...]:
    return SUPPORTED_LOCALES


def clear_cache() -> None:
    """Clear catalog and missing-key state (primarily useful for tests)."""
    _catalog_cache.clear()
    _ui_catalog_cache.clear()
    _ui_pattern_cache.clear()
    _missing_keys.clear()


def _load_catalog(locale: str) -> dict[str, Any]:
    locale = normalize_locale(locale)
    if locale in _catalog_cache:
        return _catalog_cache[locale]

    path = _catalog_dir() / f"{locale}.json"
    catalog: dict[str, Any] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            catalog = loaded
        else:
            raise ValueError("catalog root must be an object")
    except Exception as exc:  # a broken optional catalog must not stop startup
        _logger.warning("Failed to load locale catalog %s: %s", path, exc)
    _catalog_cache[locale] = catalog
    return catalog


def _lookup(catalog: dict[str, Any], key: str) -> Any:
    value: Any = catalog
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _format(value: str, key: str, values: dict[str, Any]) -> str:
    if not values and "{" not in value:
        return value
    try:
        # format_map makes missing named fields fail loudly and keeps the API
        # independent from the locale's ordering or punctuation.
        return value.format_map(values)
    except KeyError as exc:
        raise KeyError(f"Missing translation value {exc.args[0]!r} for key {key!r}") from exc
    except ValueError as exc:
        raise ValueError(f"Invalid format string for translation key {key!r}: {exc}") from exc


def tr(key: str, **values: Any) -> str:
    """Translate a dotted key and format its named placeholders.

    Missing runtime keys are logged once per locale.  The Japanese catalog is
    consulted before returning the key itself, which keeps release builds
    usable even when a newly added English entry is forgotten.
    """
    if not isinstance(key, str) or not key:
        raise ValueError("translation key must be a non-empty string")

    locale = get_locale()
    value = _lookup(_load_catalog(locale), key)
    if not isinstance(value, str):
        value = _lookup(_load_catalog(DEFAULT_LOCALE), key)
    if not isinstance(value, str):
        marker = (locale, key)
        if marker not in _missing_keys:
            _missing_keys.add(marker)
            _logger.warning("Missing translation key: %s (%s)", key, locale)
        value = key
    return _format(value, key, values)


def catalog_path(locale: str) -> Path:
    """Expose a deterministic path for validators and packaging checks."""
    return _catalog_dir() / f"{normalize_locale(locale)}.json"


def named_placeholders(value: str) -> set[str]:
    """Return named ``str.format`` fields used by a catalog value."""
    fields: set[str] = set()
    for _, field_name, _, _ in string.Formatter().parse(value):
        if field_name:
            fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return fields


_UI_TEMPLATE_FIELD = re.compile(r"\{value_(\d+)\}")


def _load_ui_catalog(locale: str) -> dict[str, str]:
    locale = normalize_locale(locale)
    if locale in _ui_catalog_cache:
        return _ui_catalog_cache[locale]
    path = _catalog_dir() / f"ui_{locale}.json"
    catalog: dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in loaded.items()
        ):
            raise ValueError("UI catalog must be a string-to-string object")
        catalog = loaded
    except Exception as exc:
        _logger.warning("Failed to load UI locale catalog %s: %s", path, exc)
    _ui_catalog_cache[locale] = catalog
    return catalog


def _ui_patterns(locale: str) -> list[tuple[re.Pattern[str], str]]:
    locale = normalize_locale(locale)
    if locale in _ui_pattern_cache:
        return _ui_pattern_cache[locale]
    patterns: list[tuple[re.Pattern[str], str]] = []
    for source, translated in _load_ui_catalog(locale).items():
        if not _UI_TEMPLATE_FIELD.search(source):
            continue
        cursor = 0
        regex_parts = ["^"]
        seen: set[str] = set()
        for match in _UI_TEMPLATE_FIELD.finditer(source):
            regex_parts.append(re.escape(source[cursor : match.start()]))
            field = f"value_{match.group(1)}"
            if field in seen:
                regex_parts.append(f"(?P={field})")
            else:
                regex_parts.append(f"(?P<{field}>.*?)")
                seen.add(field)
            cursor = match.end()
        regex_parts.extend((re.escape(source[cursor:]), "$"))
        patterns.append((re.compile("".join(regex_parts), re.DOTALL), translated))
    patterns.sort(key=lambda item: len(item[0].pattern), reverse=True)
    _ui_pattern_cache[locale] = patterns
    return patterns


def tr_ui(source: str) -> str:
    """Translate an application-owned UI source string exactly.

    The source-string catalogs are gettext-style: Japanese is both the stable
    message identity and the Japanese display value. Dynamic f-string values
    are matched only against catalogued templates and copied into the
    corresponding English placeholders. No word replacement or generated
    fallback is performed.
    """
    if get_locale() == JA or not isinstance(source, str):
        return source
    locale = get_locale()
    direct = _load_ui_catalog(locale).get(source)
    if direct is not None:
        return direct
    for pattern, translated in _ui_patterns(locale):
        match = pattern.fullmatch(source)
        if match:
            try:
                return translated.format_map(match.groupdict())
            except (KeyError, ValueError) as exc:
                _logger.warning("Invalid dynamic UI translation for %r: %s", source, exc)
                return source
    marker = (locale, f"ui:{source}")
    if marker not in _missing_keys:
        _missing_keys.add(marker)
        _logger.warning("Missing exact UI translation: %r (%s)", source, locale)
    return source
