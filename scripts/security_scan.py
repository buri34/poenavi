#!/usr/bin/env python3
"""Scan Git-tracked files for secrets and invisible Unicode payloads."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path


VARIATION_SELECTOR_SUPPLEMENT = range(0xE0100, 0xE01F0)
TEXT_EMOJI_BASES = {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139}
BIDI_CONTROLS = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))
OTHER_INVISIBLE_CONTROLS = {0x200B, 0x200C, 0x2060}
TEXT_EXTENSIONS = {
    ".bat", ".cfg", ".css", ".csv", ".env", ".html", ".ini", ".js",
    ".json", ".md", ".ps1", ".py", ".qml", ".sh", ".toml", ".ts",
    ".tsx", ".txt", ".vue", ".xml", ".yaml", ".yml",
}
SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    detail: str


def _looks_like_emoji_base(codepoint: int) -> bool:
    return (
        codepoint in TEXT_EMOJI_BASES
        or (codepoint >= 0 and unicodedata.category(chr(codepoint)).startswith("S"))
        or
        0x2300 <= codepoint <= 0x23FF
        or 0x2600 <= codepoint <= 0x27BF
        or 0x1F000 <= codepoint <= 0x1FAFF
    )


def scan_text(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    selector_count = 0
    previous_selector = False
    line = 1

    for offset, char in enumerate(text):
        codepoint = ord(char)
        is_selector = 0xFE00 <= codepoint <= 0xFE0F or codepoint in VARIATION_SELECTOR_SUPPLEMENT

        if codepoint in VARIATION_SELECTOR_SUPPLEMENT:
            findings.append(Finding(path, line, "GlassWorm variation selector", f"U+{codepoint:05X}"))
        elif 0xFE00 <= codepoint <= 0xFE0E:
            findings.append(Finding(path, line, "unexpected variation selector", f"U+{codepoint:04X}"))
        elif codepoint == 0xFE0F:
            previous = ord(text[offset - 1]) if offset else -1
            if not _looks_like_emoji_base(previous):
                findings.append(Finding(path, line, "variation selector outside emoji", "U+FE0F"))
        elif codepoint in BIDI_CONTROLS:
            findings.append(Finding(path, line, "bidirectional control", f"U+{codepoint:04X}"))
        elif codepoint in OTHER_INVISIBLE_CONTROLS:
            findings.append(Finding(path, line, "invisible control", f"U+{codepoint:04X}"))
        elif codepoint == 0xFEFF and offset != 0:
            findings.append(Finding(path, line, "embedded byte-order mark", "U+FEFF"))

        if is_selector:
            selector_count += 1
            if previous_selector:
                findings.append(Finding(path, line, "consecutive variation selectors", f"U+{codepoint:04X}"))
        previous_selector = is_selector
        if char == "\n":
            line += 1

    if selector_count > 64:
        findings.append(Finding(path, 1, "excessive variation selectors", f"{selector_count} selectors"))

    for label, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(Finding(path, line, label, "credential-like value"))
    return findings


def tracked_files(root: Path) -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    return [root / raw.decode("utf-8") for raw in output.split(b"\0") if raw]


def scan_repository(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in tracked_files(root):
        relative = path.relative_to(root).as_posix()
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            findings.append(Finding(relative, 1, "tracked environment file", "credentials may be exposed"))
        if path.suffix.lower() not in TEXT_EXTENSIONS and path.name not in {"Dockerfile", "Makefile"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        findings.extend(scan_text(relative, text))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = args.root.resolve()
    findings = scan_repository(root)
    if findings:
        print("Security scan failed:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding.path}:{finding.line}: {finding.kind} ({finding.detail})", file=sys.stderr)
        return 1
    print("Security scan passed: tracked files contain no suspicious secrets or invisible Unicode payloads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
