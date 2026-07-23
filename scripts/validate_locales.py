"""Read-only release validation for PoENavi locale resources."""

from __future__ import annotations

import ast
import collections
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
TRANSLATABLE_GUIDE_FIELDS = {"objective", "layout", "tips", "summary", "text"}
ALLOWED_TAG = re.compile(r"^</?span(?:\s+style\s*=\s*['\"]\s*color\s*:\s*#[0-9a-fA-F]{3,8}\s*;?\s*['\"])?\s*>$")
TOKEN_RE = re.compile(r"\[(?:quest|boss|town|move|logout|note|star|trial|craft|wp|portal)\]")
TAG_RE = re.compile(r"</?[^>]+>")
UI_LITERAL_CONSTRUCTORS = {"QLabel", "QPushButton", "QCheckBox", "QGroupBox", "QRadioButton"}
UI_LITERAL_METHODS = {
    "setText",
    "setWindowTitle",
    "setToolTip",
    "setPlaceholderText",
    "addItem",
    "addTab",
    "addAction",
    "addButton",
}
MESSAGE_BOX_METHODS = {"information", "question", "warning", "critical"}
BANNED_ENGLISH_FILLERS = (
    "the relevant item",
    "the relevant guide step",
    "please provide the japanese text",
)
BANNED_WAYPOINT_MISTRANSLATIONS = re.compile(
    r"(?<!\[)\bWP\b(?!\])|Wiki page|Wikipedia|WordPress|website|Work Package|"
    r"work permit|World Points|World Wide Web|World of Warcraft",
    re.IGNORECASE,
)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _flatten_strings(value: Any, prefix: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            result.update(_flatten_strings(child, child_prefix))
    elif isinstance(value, str):
        result[prefix] = value
    return result


def _placeholders(value: str) -> set[str]:
    return {
        match.group(1).split(".", 1)[0].split("[", 1)[0]
        for match in re.finditer(r"\{([A-Za-z_][A-Za-z0-9_.\[\]]*)[^}]*\}", value)
    }


def validate_catalogs(root: Path = ROOT) -> list[str]:
    ja = _flatten_strings(_load_json(root / "data" / "i18n" / "ja.json"))
    en = _flatten_strings(_load_json(root / "data" / "i18n" / "en.json"))
    errors: list[str] = []
    if set(ja) != set(en):
        errors.append(f"catalog key sets differ: ja-only={sorted(set(ja)-set(en))}, en-only={sorted(set(en)-set(ja))}")
    for key in sorted(set(ja) & set(en)):
        if _placeholders(ja[key]) != _placeholders(en[key]):
            errors.append(f"placeholder mismatch for catalog key {key}")
    return errors


def _ui_template(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        value_index = 0
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                parts.append(part.value)
            elif isinstance(part, ast.FormattedValue):
                parts.append(f"{{value_{value_index}}}")
                value_index += 1
            else:
                return None
        return "".join(parts)
    return None


def _static_ui_templates(root: Path) -> tuple[set[str], list[str]]:
    templates: set[str] = set()
    errors: list[str] = []
    for path in (root / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(
                alias.name == "ui_text" for alias in node.names
            ):
                errors.append(f"legacy ui_text import: {path}:{node.lineno}")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "ui_text":
                errors.append(f"legacy ui_text definition: {path}:{node.lineno}")
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id == "ui_text":
                errors.append(f"legacy ui_text call: {path}:{node.lineno}")
            if node.func.id != "tr_ui":
                continue
            if not node.args:
                errors.append(f"tr_ui call without source: {path}:{node.lineno}")
                continue
            template = _ui_template(node.args[0])
            if template is None:
                errors.append(f"unsupported tr_ui expression: {path}:{node.lineno}")
            else:
                templates.add(template)
    return templates, errors


def validate_ui_catalogs(root: Path = ROOT) -> list[str]:
    templates, errors = _static_ui_templates(root)
    ja = _load_json(root / "data" / "i18n" / "ui_ja.json")
    en = _load_json(root / "data" / "i18n" / "ui_en.json")
    if not isinstance(ja, dict) or not isinstance(en, dict):
        return errors + ["UI catalogs must contain JSON objects"]
    if set(ja) != templates:
        errors.append(
            "Japanese UI catalog/source templates differ: "
            f"catalog-only={sorted(set(ja) - templates)!r}, "
            f"source-only={sorted(templates - set(ja))!r}"
        )
    if set(en) != templates:
        errors.append(
            "English UI catalog/source templates differ: "
            f"catalog-only={sorted(set(en) - templates)!r}, "
            f"source-only={sorted(templates - set(en))!r}"
        )
    for source in sorted(templates & set(ja) & set(en)):
        if ja[source] != source:
            errors.append(f"Japanese UI value must equal its source: {source!r}")
        if not isinstance(en[source], str) or not en[source]:
            errors.append(f"empty English UI translation: {source!r}")
            continue
        if _placeholders(source) != _placeholders(en[source]):
            errors.append(f"UI placeholder mismatch: {source!r}")
        if _contains_japanese(en[source]):
            errors.append(f"Japanese text remains in English UI translation: {source!r}")
        lowered = en[source].lower()
        for filler in BANNED_ENGLISH_FILLERS:
            if filler in lowered:
                errors.append(f"banned filler text in English UI translation: {source!r}")
    return errors


def _guide_walk(value: Any, path: str = "") -> Iterable[tuple[str, str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if key in TRANSLATABLE_GUIDE_FIELDS and isinstance(child, str):
                yield child_path, key, child
            else:
                yield from _guide_walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _guide_walk(child, f"{path}/{index}")


def _shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _shape(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_shape(child) for child in value]
    return type(value).__name__


def _protected_values(value: Any, path: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if key in TRANSLATABLE_GUIDE_FIELDS:
                continue
            result.update(_protected_values(child, child_path))
        return result
    if isinstance(value, list):
        result: dict[str, Any] = {}
        for index, child in enumerate(value):
            result.update(_protected_values(child, f"{path}/{index}"))
        return result
    return {path: value}


def _tags(value: str) -> list[str]:
    return TAG_RE.findall(value)


def validate_guides(root: Path = ROOT) -> list[str]:
    pairs = (
        ("guide_data.json", "guide_data_en.json"),
        ("guide_data_poe2.json", "guide_data_poe2_en.json"),
    )
    errors: list[str] = []
    for ja_name, en_name in pairs:
        ja = _load_json(root / ja_name)
        en = _load_json(root / en_name)
        if _shape(ja) != _shape(en):
            errors.append(f"guide structure differs: {ja_name} / {en_name}")
        if _protected_values(ja) != _protected_values(en):
            errors.append(f"protected guide values differ: {ja_name} / {en_name}")
        for path, field, ja_value in _guide_walk(ja):
            matching = {item_path: item_value for item_path, _item_field, item_value in _guide_walk(en)}.get(path, "")
            if ja_value and not matching:
                errors.append(f"empty English guide leaf: {en_name}{path}")
            if _contains_japanese(matching):
                errors.append(f"Japanese text remains in English guide leaf: {en_name}{path}")
            lowered = matching.lower()
            for filler in BANNED_ENGLISH_FILLERS:
                if filler in lowered:
                    errors.append(f"banned filler text in English guide leaf: {en_name}{path}")
            if BANNED_WAYPOINT_MISTRANSLATIONS.search(matching):
                errors.append(f"waypoint mistranslation in English guide leaf: {en_name}{path}")
            if collections.Counter(TOKEN_RE.findall(ja_value)) != collections.Counter(TOKEN_RE.findall(matching)):
                errors.append(f"mini-navi token mismatch: {en_name}{path}")
            for tag in _tags(matching):
                if not ALLOWED_TAG.match(tag):
                    errors.append(f"unsupported guide markup {tag!r}: {en_name}{path}")
            if len(ja_value.splitlines()) != len(matching.splitlines()):
                errors.append(f"guide line count changed: {en_name}{path}")
    return errors


def validate_zone_english(root: Path = ROOT) -> list[str]:
    data = _load_json(root / "data" / "zone_data.json")
    errors: list[str] = []
    versions = data.get("zone_data_by_version", data)
    for version, acts in versions.items():
        if not isinstance(acts, dict):
            continue
        for act, zones in acts.items():
            for zone in zones:
                if not zone.get("zone_en"):
                    errors.append(f"missing zone_en: {version}/{act}/{zone.get('id')}")
    return errors


def _python_literal_assignment(path: Path, name: str) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"{name} is not assigned in {path}")


def _zones_by_id(acts: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(acts, dict):
        return {}
    return {
        zone["id"]: zone
        for zones in acts.values()
        if isinstance(zones, list)
        for zone in zones
        if isinstance(zone, dict) and isinstance(zone.get("id"), str)
    }


def validate_authoritative_guide_terms(root: Path = ROOT) -> list[str]:
    fixture = _load_json(root / "data" / "authoritative_guide_terms.json")
    games = fixture.get("games", {})
    errors: list[str] = []

    identities: set[tuple[str, str, str]] = set()
    for game, config in games.items():
        for term in config.get("guide_terms", []):
            identity = (game, term["table"], term["game_id"])
            if identity in identities:
                errors.append(
                    "duplicate authoritative identity: "
                    f"{game}/{term['table']}/{term['game_id']}"
                )
            identities.add(identity)

    guide_paths = {
        "poe1": ("guide_data.json", "guide_data_en.json"),
        "poe2": ("guide_data_poe2.json", "guide_data_poe2_en.json"),
    }
    for game, config in games.items():
        paths = guide_paths.get(game)
        if paths is None:
            errors.append(f"unsupported authoritative guide game: {game}")
            continue
        japanese_name, english_name = paths
        japanese_guide = _load_json(root / japanese_name)
        english_guide = _load_json(root / english_name)
        japanese_leaves = {
            path: value for path, _field, value in _guide_walk(japanese_guide)
        }
        english_leaves = {
            path: value for path, _field, value in _guide_walk(english_guide)
        }

        for term in config.get("guide_terms", []):
            japanese_term = term["ja"]
            english_term = term["en"]
            matching_paths = [
                path
                for path, value in japanese_leaves.items()
                if japanese_term in value
            ]
            if not matching_paths:
                errors.append(
                    f"unused authoritative guide term for {game}: {japanese_term!r}"
                )
                continue
            for path in matching_paths:
                if english_term not in english_leaves.get(path, ""):
                    errors.append(
                        f"authoritative guide term mismatch for {game}: "
                        f"{english_name}{path} expected {english_term!r}"
                    )

        all_english = "\n".join(english_leaves.values()).casefold()
        for forbidden in config.get("forbidden_english", []):
            if forbidden.casefold() in all_english:
                errors.append(
                    f"forbidden English guide translation for {game}: {forbidden!r}"
                )

    poe2 = games.get("poe2", {})
    zone_master = _load_json(root / "data" / "zone_data.json")
    runtime_zones = _zones_by_id(
        zone_master.get("zone_data_by_version", zone_master).get("poe2", {})
    )
    fallback_zones = _zones_by_id(
        _python_literal_assignment(
            root / "src" / "utils" / "zone_data_poe2.py",
            "DEFAULT_ZONE_DATA_POE2",
        )
    )

    for expected in poe2.get("zones", []):
        zone_id = expected["poenavi_id"]
        expected_names = (expected["ja"], expected["en"])
        for source, zones in (
            ("data/zone_data.json", runtime_zones),
            ("src/utils/zone_data_poe2.py", fallback_zones),
        ):
            zone = zones.get(zone_id)
            if zone is None:
                errors.append(f"authoritative PoE2 zone missing from {source}: {zone_id}")
                continue
            actual_names = (zone.get("zone"), zone.get("zone_en"))
            if actual_names != expected_names:
                errors.append(
                    f"authoritative PoE2 zone mismatch in {source}: {zone_id} "
                    f"expected ja={expected_names[0]!r}, en={expected_names[1]!r}"
                )

    return errors
def _static_tr_keys(root: Path) -> tuple[set[str], list[str]]:
    keys: set[str] = set()
    errors: list[str] = []
    source_roots = [root / "main.py", root / "updater_main.py", root / "src"]
    paths = [path for base in source_roots if base.is_file() for path in [base]]
    paths += [path for base in source_roots if base.is_dir() for path in base.rglob("*.py")]
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    errors.append(f"non-literal tr key: {path}:{node.lineno}")
                else:
                    keys.add(node.args[0].value)
    return keys, errors


def validate_static_translation_keys(root: Path = ROOT) -> list[str]:
    keys, errors = _static_tr_keys(root)
    catalog = _flatten_strings(_load_json(root / "data" / "i18n" / "ja.json"))
    errors.extend(f"unknown translation key {key!r}" for key in sorted(keys) if key not in catalog)
    return errors


def _function_nodes(function: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterable[ast.AST]:
    """Walk one function body without mixing in nested function scopes."""
    stack = list(reversed(function.body))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


def validate_local_import_scoping(root: Path = ROOT) -> list[str]:
    """Reject local imports that shadow a name already used in that function.

    Python treats an imported name as local throughout the whole function, so
    using a module-level import before a same-name local import raises
    ``UnboundLocalError`` at runtime.
    """
    errors: list[str] = []
    paths = list((root / "src").rglob("*.py"))
    for entrypoint in (root / "main.py", root / "updater_main.py"):
        if entrypoint.is_file():
            paths.append(entrypoint)
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            nodes = list(_function_nodes(function))
            imports: dict[str, list[int]] = {}
            for node in nodes:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.setdefault(
                            alias.asname or alias.name.split(".", 1)[0], []
                        ).append(node.lineno)
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        imports.setdefault(alias.asname or alias.name, []).append(
                            node.lineno
                        )
            for name, lines in imports.items():
                first_import = min(lines)
                early_loads = sorted(
                    {
                        node.lineno
                        for node in nodes
                        if isinstance(node, ast.Name)
                        and isinstance(node.ctx, ast.Load)
                        and node.id == name
                        and node.lineno < first_import
                    }
                )
                if early_loads:
                    errors.append(
                        f"local import shadows earlier use of {name!r}: "
                        f"{path}:{early_loads[0]} (import at line {first_import})"
                    )
    return errors


def _contains_japanese(value: str) -> bool:
    return any(
        ("\u3040" <= character <= "\u30ff")
        or ("\u3400" <= character <= "\u9fff")
        for character in value
    )


def _literal_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(part.value for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str))
    return None


def validate_raw_ui_literals(root: Path = ROOT) -> list[str]:
    """Ensure user-facing Japanese literals are explicitly passed through tr_ui.

    The language picker is intentionally bilingual and is the sole UI exemption.
    Domain data and comments are outside this check; only arguments to common
    Qt display APIs are inspected.
    """
    errors: list[str] = []
    ui_paths = list((root / "src" / "ui").rglob("*.py"))
    poetore_ui = root / "src" / "poetore" / "ui.py"
    if poetore_ui.is_file():
        ui_paths.append(poetore_ui)
    for path in ui_paths:
        if path.name == "language_dialog.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            argument_indexes: tuple[int, ...] = ()
            if isinstance(node.func, ast.Name) and node.func.id in UI_LITERAL_CONSTRUCTORS:
                argument_indexes = (0,)
            elif isinstance(node.func, ast.Attribute) and node.func.attr in UI_LITERAL_METHODS:
                argument_indexes = (0, 1) if node.func.attr in {"addTab", "addButton"} else (0,)
            elif isinstance(node.func, ast.Attribute) and node.func.attr in MESSAGE_BOX_METHODS:
                argument_indexes = (1, 2)
            for index in argument_indexes:
                if index >= len(node.args):
                    continue
                value = _literal_text(node.args[index])
                if value is not None and _contains_japanese(value):
                    errors.append(f"raw Japanese UI literal: {path}:{node.lineno}")
    return errors


def validate_resources(root: Path = ROOT) -> list[str]:
    build_script = (root / "scripts" / "build_release.ps1").read_text(encoding="utf-8")
    required = (
        "data\\i18n",
        "build\\generated\\update_channel.json;data",
        "guide_data.json",
        "guide_data_poe2.json",
        "guide_data_en.json",
        "guide_data_poe2_en.json",
    )
    return [f"packaging script does not register {name}" for name in required if name not in build_script]


def validate_all(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for validator in (
        validate_catalogs,
        validate_ui_catalogs,
        validate_guides,
        validate_zone_english,
        validate_authoritative_guide_terms,
        validate_static_translation_keys,
        validate_local_import_scoping,
        validate_raw_ui_literals,
        validate_resources,
    ):
        try:
            errors.extend(validator(root))
        except Exception as exc:
            errors.append(f"{validator.__name__} failed: {exc}")
    return errors


if __name__ == "__main__":
    failures = validate_all()
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        raise SystemExit(1)
    print("Locale validation passed: keyed/UI catalogs, English guides, zone names, static keys, UI literals, and resources are valid.")
